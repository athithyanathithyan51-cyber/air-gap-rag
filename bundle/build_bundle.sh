#!/usr/bin/env bash
# Builds the single offline transfer bundle. Run on a CONNECTED Linux/WSL machine with Docker.
#
#   bundle/build_bundle.sh [VERSION]
#
# Output: bundle/out/airgap-assistant-<VERSION>/ and a .tar of it, with manifest.sha256
# covering every file. Everything the air-gapped host needs is inside: Docker Engine .debs
# (Ubuntu 22.04 + 24.04, amd64), container images, model weights, scripts, docs.
set -euo pipefail

VERSION="${1:-$(git describe --tags --always 2>/dev/null || echo dev)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/bundle/out/airgap-assistant-$VERSION"
MODELS_VOLUME="${MODELS_VOLUME:-airgap-dev_ollama_models}"
REQUIRED_MODELS=(qwen2.5:7b-instruct-q4_K_M llama3.2:3b-instruct-q4_K_M nomic-embed-text)

QDRANT_IMAGE="qdrant/qdrant:v1.19.2@sha256:b7b0444c4c351c970b98e90a6f89c2ee4287c65b44e52b4cb503fa5b2aa927ad"
OLLAMA_IMAGE="ollama/ollama:0.40.2@sha256:b86366bb528bbf7f1424435d165028497a5b69bf6ddb4fa5a87102e2b79f44fb"

# Docker Engine packages: URL path under download.docker.com/linux/ubuntu/ and expected SHA-256.
DEBS=(
  "jammy dists/jammy/pool/stable/amd64/containerd.io_2.4.1-2~ubuntu.22.04~jammy_amd64.deb d29f8e47e0cc8c836247a9671ac917302afda050808048672d810398d02bb503"
  "jammy dists/jammy/pool/stable/amd64/docker-ce-cli_29.9.0-1~ubuntu.22.04~jammy_amd64.deb 622b7f65d377ab618918d590b84e61185c120c2c989a9092ced8dc6cd4aa6d1d"
  "jammy dists/jammy/pool/stable/amd64/docker-ce_29.9.0-1~ubuntu.22.04~jammy_amd64.deb 99cf99a74ebf3af40383fd5c49836285c0296094a04229176e8b9cec630b2409"
  "jammy dists/jammy/pool/stable/amd64/docker-compose-plugin_5.6.0-1~ubuntu.22.04~jammy_amd64.deb 2389d885e90df60ef9dcee0e1fae16b70ffa392d6f29d742469aa8ea63eb1daa"
  "jammy dists/jammy/pool/stable/amd64/docker-buildx-plugin_0.38.0-1~ubuntu.22.04~jammy_amd64.deb a4c24830c1b1b3dc24d600968be2dec21d9c0af8bad29ab16c7fac8a44f83f51"
  "noble dists/noble/pool/stable/amd64/containerd.io_2.4.1-2~ubuntu.24.04~noble_amd64.deb 893c9ddf70deacfb79db14ec3845164f1649807f82634bc453c12a1cc40a88c4"
  "noble dists/noble/pool/stable/amd64/docker-ce-cli_29.9.0-1~ubuntu.24.04~noble_amd64.deb 2bd67d414c0f555765a91833a505b3c5987cbf744c2836ea1f1563d2ffa4b980"
  "noble dists/noble/pool/stable/amd64/docker-ce_29.9.0-1~ubuntu.24.04~noble_amd64.deb 118bfd1762738db0f88848035eabfb79f735e7843af47f843e5567cd0cd780e5"
  "noble dists/noble/pool/stable/amd64/docker-compose-plugin_5.6.0-1~ubuntu.24.04~noble_amd64.deb 132266d499d9873aafcbe5b515997b8abd714914fa32a62ccac705c1ede7ca81"
  "noble dists/noble/pool/stable/amd64/docker-buildx-plugin_0.38.0-1~ubuntu.24.04~noble_amd64.deb 7094f8b50bc6b239292d475620424a531f7fa0763e466c52ffc3a4037e72bfc5"
)

log() { printf '\n==> %s\n' "$*"; }

log "Bundle $VERSION -> $OUT"
rm -rf "$OUT"
mkdir -p "$OUT"/{images,models,debs/jammy,debs/noble,deploy,tools,scripts,docs}

log "Docker Engine packages"
for entry in "${DEBS[@]}"; do
  read -r codename path sha <<<"$entry"
  file="$OUT/debs/$codename/$(basename "$path")"
  curl -fsSL --retry 3 -o "$file" "https://download.docker.com/linux/ubuntu/$path"
  echo "$sha  $file" | sha256sum -c --quiet -
done

log "Container images"
docker build -f "$ROOT/deploy/Dockerfile" -t "airgap-assistant:$VERSION" "$ROOT"
docker pull "$QDRANT_IMAGE"
docker pull "$OLLAMA_IMAGE"
docker tag "$QDRANT_IMAGE" qdrant/qdrant:v1.19.2
docker tag "$OLLAMA_IMAGE" ollama/ollama:0.40.2
docker save -o "$OUT/images/app.tar" "airgap-assistant:$VERSION"
docker save -o "$OUT/images/qdrant.tar" qdrant/qdrant:v1.19.2
docker save -o "$OUT/images/ollama.tar" ollama/ollama:0.40.2

log "Model weights from volume $MODELS_VOLUME"
docker run --rm -v "$MODELS_VOLUME:/root/.ollama" --entrypoint ollama "$OLLAMA_IMAGE" list >/dev/null 2>&1 || true
for m in "${REQUIRED_MODELS[@]}"; do
  docker run --rm -v "$MODELS_VOLUME:/src:ro" --entrypoint sh "$OLLAMA_IMAGE" -c \
    "name='$m'; repo=\${name%%:*}; tag=\${name#*:}; [ \"\$tag\" = \"\$name\" ] && tag=latest; \
     test -f /src/models/manifests/registry.ollama.ai/library/\$repo/\$tag" \
    || { echo "model $m missing from $MODELS_VOLUME; pull it first" >&2; exit 1; }
done
docker run --rm -v "$MODELS_VOLUME:/src:ro" -v "$OUT/models:/out" --entrypoint tar "$OLLAMA_IMAGE" \
  -C /src -cf /out/ollama-models.tar models

log "Scripts, configuration, docs"
cp "$ROOT/deploy/docker-compose.yml" "$ROOT/deploy/docker-compose.gpu.yml" "$OUT/deploy/"
cp "$ROOT/deploy/install.sh" "$ROOT/deploy/uninstall.sh" "$ROOT/deploy/rollback.sh" "$OUT/"
cp "$ROOT/backend/attestation/verify_chain.py" "$OUT/tools/"
cp "$ROOT/scripts/verify_isolation.py" "$ROOT/scripts/capture_traffic.sh" "$OUT/scripts/"
cp "$ROOT/README.md" "$ROOT/LICENSE" "$OUT/"
cp "$ROOT"/docs/*.md "$OUT/docs/"
echo "$VERSION" > "$OUT/VERSION"
chmod +x "$OUT"/*.sh "$OUT"/scripts/*.sh

log "Manifest"
(cd "$OUT" && find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > manifest.sha256)
cp "$OUT/manifest.sha256" "$ROOT/bundle/manifest.sha256"

log "Archive"
tar -C "$ROOT/bundle/out" -cf "$ROOT/bundle/out/airgap-assistant-$VERSION.tar" "airgap-assistant-$VERSION"
sha256sum "$ROOT/bundle/out/airgap-assistant-$VERSION.tar" | tee "$ROOT/bundle/out/airgap-assistant-$VERSION.tar.sha256"
du -sh "$OUT" "$ROOT/bundle/out/airgap-assistant-$VERSION.tar"
log "Done. Copy airgap-assistant-$VERSION.tar and its .sha256 to the air-gapped host."
