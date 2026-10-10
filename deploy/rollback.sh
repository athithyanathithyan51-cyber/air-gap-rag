#!/usr/bin/env bash
# Rolls back to the previously installed version (its image must still be loaded)
# and restores the app-data backup taken by the upgrade.
#   sudo ./rollback.sh
set -euo pipefail
PREFIX="${AIRGAP_PREFIX:-/opt/airgap}"
ETC="${AIRGAP_ETC:-/etc/airgap}"
BACKUPS="${AIRGAP_BACKUPS:-/var/backups/airgap}"
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

prev="$(cat "$PREFIX/PREVIOUS_VERSION" 2>/dev/null)" || { echo "no previous version recorded" >&2; exit 1; }
docker image inspect "airgap-assistant:$prev" >/dev/null || { echo "image airgap-assistant:$prev not present" >&2; exit 1; }
backup="$(ls -1t "$BACKUPS"/app_data-"$prev"-*.tgz 2>/dev/null | head -1)" || true
[ -n "$backup" ] || { echo "no backup for $prev in $BACKUPS" >&2; exit 1; }

COMPOSE=(docker compose -p airgap -f "$PREFIX/docker-compose.yml" --env-file "$ETC/airgap.env")
"${COMPOSE[@]}" stop app
echo "Restoring $backup"
docker run --rm -v airgap_app_data:/data -v "$BACKUPS:/backup:ro" --entrypoint sh "ollama/ollama:0.40.2" \
  -c "find /data -mindepth 1 -delete && tar -C /data -xzf /backup/$(basename "$backup")"
sed -i "s/^AIRGAP_VERSION=.*/AIRGAP_VERSION=$prev/" "$ETC/airgap.env"
"${COMPOSE[@]}" up -d
echo "$prev" > "$PREFIX/VERSION"
rm -f "$PREFIX/PREVIOUS_VERSION"
echo "Rolled back to $prev. Vectors in Qdrant were not rolled back; re-upload documents changed since the upgrade."
