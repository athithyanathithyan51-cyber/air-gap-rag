#!/usr/bin/env bash
# Offline installer / upgrader. Run from the unpacked bundle directory on the air-gapped host:
#
#   sudo ./install.sh
#
# Needs no network. Verifies every bundle file against manifest.sha256 first.
# Re-running with a newer bundle upgrades in place (data volume backed up first).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${AIRGAP_PREFIX:-/opt/airgap}"
ETC="${AIRGAP_ETC:-/etc/airgap}"
BACKUPS="${AIRGAP_BACKUPS:-/var/backups/airgap}"
APP_UID=57439   # mambauser in the app image
VERSION="$(cat "$HERE/VERSION")"

die() { echo "ERROR: $*" >&2; exit 1; }
log() { printf '\n==> %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "run with sudo"

log "Checking bundle integrity (manifest.sha256)"
(cd "$HERE" && sha256sum -c --quiet manifest.sha256) || die "bundle files do not match manifest.sha256; do not install"

log "Checking host"
. /etc/os-release
case "${VERSION_CODENAME:-}" in jammy|noble) ;; *) die "supported: Ubuntu 22.04 (jammy) or 24.04 (noble); found ${PRETTY_NAME:-unknown}";; esac
[ "$(uname -m)" = "x86_64" ] || die "amd64 (x86_64) required"
cores=$(nproc); mem_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)
disk_gb=$(df -BG --output=avail /var/lib | tail -1 | tr -dc 0-9)
echo "cores=$cores ram=${mem_gb}GB free_disk(/var/lib)=${disk_gb}GB"
[ "$cores" -ge 4 ] || echo "WARNING: fewer than 4 cores; answers will be slow"
[ "$mem_gb" -ge 15 ] || echo "WARNING: less than 16 GB RAM; set AIRGAP_CHAT_MODEL=llama3.2:3b-instruct-q4_K_M in $ETC/airgap.env"
[ "$disk_gb" -ge 20 ] || die "need at least 20 GB free under /var/lib"

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker Engine from bundled packages ($VERSION_CODENAME)"
  dpkg -i "$HERE"/debs/"$VERSION_CODENAME"/containerd.io_*.deb "$HERE"/debs/"$VERSION_CODENAME"/docker-ce-cli_*.deb \
    "$HERE"/debs/"$VERSION_CODENAME"/docker-ce_*.deb "$HERE"/debs/"$VERSION_CODENAME"/docker-compose-plugin_*.deb \
    "$HERE"/debs/"$VERSION_CODENAME"/docker-buildx-plugin_*.deb \
    || die "dpkg failed (missing base packages such as iptables?). See docs/runbook.md"
  systemctl enable --now docker
fi
docker compose version >/dev/null || die "docker compose plugin not available"

log "Loading container images"
for img in qdrant ollama app; do docker load -q -i "$HERE/images/$img.tar"; done

log "Configuration in $ETC"
install -d -m 0750 "$ETC"
if [ ! -f "$ETC/attestation.pass" ]; then
  if [ -n "${AIRGAP_ATTESTATION_PASSPHRASE:-}" ]; then
    printf '%s' "$AIRGAP_ATTESTATION_PASSPHRASE" > "$ETC/attestation.pass"
  else
    head -c 32 /dev/urandom | base64 | tr -d '\n' > "$ETC/attestation.pass"
    echo "Generated a random attestation-key passphrase in $ETC/attestation.pass (root-only). Back it up offline."
  fi
fi
chown root:"$APP_UID" "$ETC/attestation.pass"; chmod 0440 "$ETC/attestation.pass"
[ -f "$ETC/airgap.env" ] || cat > "$ETC/airgap.env" <<EOF
# Edit and run: sudo docker compose -f $PREFIX/docker-compose.yml --env-file $ETC/airgap.env up -d
AIRGAP_CHAT_MODEL=qwen2.5:7b-instruct-q4_K_M
AIRGAP_BIND_HOST=127.0.0.1
AIRGAP_BIND_PORT=8000
EOF
previous="$(cat "$PREFIX/VERSION" 2>/dev/null || true)"
sed -i '/^AIRGAP_VERSION=/d' "$ETC/airgap.env"; echo "AIRGAP_VERSION=$VERSION" >> "$ETC/airgap.env"

install -d "$PREFIX"
install -m 0644 "$HERE/deploy/docker-compose.yml" "$PREFIX/docker-compose.yml"
install -m 0644 "$HERE/tools/verify_chain.py" "$PREFIX/verify_chain.py"
COMPOSE=(docker compose -p airgap -f "$PREFIX/docker-compose.yml" --env-file "$ETC/airgap.env")

if [ -n "$previous" ] && [ "$previous" != "$VERSION" ]; then
  log "Upgrade $previous -> $VERSION: backing up app data first"
  install -d -m 0700 "$BACKUPS"
  "${COMPOSE[@]}" stop app || true
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  docker run --rm -v airgap_app_data:/data:ro -v "$BACKUPS:/backup" --entrypoint tar "ollama/ollama:0.40.2" \
    -C /data -czf "/backup/app_data-$previous-$ts.tgz" .
  echo "$previous" > "$PREFIX/PREVIOUS_VERSION"
  echo "backup: $BACKUPS/app_data-$previous-$ts.tgz"
fi

log "Model weights"
docker volume create airgap_ollama_models >/dev/null
docker run --rm -v airgap_ollama_models:/root/.ollama -v "$HERE/models:/in:ro" --entrypoint tar "ollama/ollama:0.40.2" \
  -C /root/.ollama -xf /in/ollama-models.tar

log "Starting services"
"${COMPOSE[@]}" up -d
echo "$VERSION" > "$PREFIX/VERSION"

log "Waiting for readiness"
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$(grep -oP '^AIRGAP_BIND_PORT=\K.*' "$ETC/airgap.env")/ready" >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 2
done
[ "${ready:-0}" = 1 ] || { "${COMPOSE[@]}" ps; "${COMPOSE[@]}" logs --tail 50 app; die "service not ready after 3 minutes"; }

if ! "${COMPOSE[@]}" exec -T app python -c "
import sys; from sqlalchemy import select, func
from app.config import get_settings; from db.session import Database; from db.models import User
s = Database(get_settings().db_path).session(); sys.exit(0 if s.scalar(select(func.count()).select_from(User)) else 1)"; then
  log "Create the first admin account"
  if [ -n "${AIRGAP_ADMIN_PASSWORD_FILE:-}" ]; then
    # Unattended install: password read from a root-only file, never from the command line.
    "${COMPOSE[@]}" exec -T app python -m app.cli create-user "${AIRGAP_ADMIN_USER:-admin}" --role admin \
      < "$AIRGAP_ADMIN_PASSWORD_FILE"
  else
    "${COMPOSE[@]}" exec app python -m app.cli create-user "${AIRGAP_ADMIN_USER:-admin}" --role admin
  fi
fi

log "Installed $VERSION. Open http://127.0.0.1:$(grep -oP '^AIRGAP_BIND_PORT=\K.*' "$ETC/airgap.env")/ on this machine."
echo "Rollback: sudo $HERE/rollback.sh    Uninstall: sudo $HERE/uninstall.sh"
