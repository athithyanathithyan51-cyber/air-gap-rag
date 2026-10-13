#!/usr/bin/env bash
# Start the development server on a Windows laptop (Git Bash), from the repo root.
#
#   bash scripts/dev-server-windows.sh
#
# Allowlists the "vEthernet (WSL...)" adapter: the host-only virtual switch Docker Desktop and
# WSL need. It has no route off the machine; with Wi-Fi/Ethernet down there is no default route,
# which the monitor still checks. Development only: the Ubuntu deployment keeps its own policy
# in /etc/airgap/airgap.env.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=backend
export AIRGAP_ENVIRONMENT=development
export AIRGAP_ISOLATION_ALLOW='["docker0","br-*","vEthernet (WSL*"]'
PY="${AIRGAP_PYTHON:-$HOME/.local/micromamba/root/envs/airgap/python.exe}"
exec "$PY" -m app.main
