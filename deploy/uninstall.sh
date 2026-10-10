#!/usr/bin/env bash
# Stops and removes the assistant. Data volumes are KEPT unless --purge is given.
#   sudo ./uninstall.sh [--purge]
set -euo pipefail
PREFIX="${AIRGAP_PREFIX:-/opt/airgap}"
ETC="${AIRGAP_ETC:-/etc/airgap}"
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

if [ -f "$PREFIX/docker-compose.yml" ]; then
  docker compose -p airgap -f "$PREFIX/docker-compose.yml" --env-file "$ETC/airgap.env" down
fi
if [ "${1:-}" = "--purge" ]; then
  read -r -p "Delete ALL documents, users, attestation chain and models? Type 'delete' to confirm: " ans
  [ "$ans" = "delete" ] || { echo "aborted"; exit 1; }
  docker volume rm -f airgap_app_data airgap_qdrant_data airgap_ollama_models
  rm -rf "$ETC"
  echo "Purged data volumes and $ETC"
else
  echo "Data volumes kept (airgap_app_data, airgap_qdrant_data, airgap_ollama_models). Use --purge to delete."
fi
rm -rf "$PREFIX"
echo "Uninstalled. Docker Engine itself was left installed."
