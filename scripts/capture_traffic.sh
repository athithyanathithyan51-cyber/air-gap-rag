#!/usr/bin/env bash
# Records all traffic on ALL interfaces (including loopback) while the assistant goes
# through startup, ingestion, N questions and shutdown, then counts non-loopback packets.
#
#   sudo scripts/capture_traffic.sh --user admin --password-file pw.txt --docs DIR [--queries 100]
#
# Requires: tcpdump, curl, python3, and an installed assistant (install.sh) on this host.
# Output: evidence/<timestamp>/{capture.pcap, analysis.json, analysis.txt, run.log}
set -euo pipefail

PREFIX="${AIRGAP_PREFIX:-/opt/airgap}"
ETC="${AIRGAP_ETC:-/etc/airgap}"
HERE="$(cd "$(dirname "$0")" && pwd)"
QUERIES=100
USER_NAME=""; PW_FILE=""; DOCS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --user) USER_NAME="$2"; shift 2;;
    --password-file) PW_FILE="$2"; shift 2;;
    --docs) DOCS="$2"; shift 2;;
    --queries) QUERIES="$2"; shift 2;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "run with sudo (tcpdump needs root)" >&2; exit 1; }
[ -n "$USER_NAME" ] && [ -f "$PW_FILE" ] && [ -d "$DOCS" ] || { echo "need --user, --password-file, --docs" >&2; exit 2; }
command -v tcpdump >/dev/null || { echo "tcpdump not installed" >&2; exit 1; }

PORT="$(grep -oP '^AIRGAP_BIND_PORT=\K.*' "$ETC/airgap.env" 2>/dev/null || echo 8000)"
BASE="http://127.0.0.1:$PORT"
COMPOSE=(docker compose -p airgap -f "$PREFIX/docker-compose.yml" --env-file "$ETC/airgap.env")
OUT="evidence/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
JAR="$OUT/cookies.txt"
LOG="$OUT/run.log"
say() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

say "host: $(hostname) kernel: $(uname -r)"
ip -brief link | tee -a "$LOG"
ip route | tee -a "$LOG" || true

say "start tcpdump on all interfaces"
tcpdump -i any -n -U -w "$OUT/capture.pcap" >/dev/null 2>>"$LOG" &
TCPDUMP=$!
sleep 2

say "PHASE startup"
"${COMPOSE[@]}" up -d >>"$LOG" 2>&1
for _ in $(seq 1 90); do curl -fsS "$BASE/ready" >/dev/null 2>&1 && break; sleep 2; done
curl -fsS "$BASE/ready" | tee -a "$LOG"; echo >>"$LOG"

say "PHASE login"
curl -fsS -c "$JAR" -b "$JAR" -H 'Content-Type: application/json' \
  --data "$(python3 -c 'import json,sys; print(json.dumps({"username": sys.argv[1], "password": open(sys.argv[2]).read().strip()}))' "$USER_NAME" "$PW_FILE")" \
  "$BASE/api/auth/login" >/dev/null
CSRF="$(awk '$6=="airgap_csrf"{print $7}' "$JAR")"

say "PHASE ingestion ($DOCS)"
find "$DOCS" -maxdepth 1 -type f \( -iname '*.pdf' -o -iname '*.docx' -o -iname '*.md' -o -iname '*.txt' \) -print0 |
  while IFS= read -r -d '' f; do
    code=$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" -b "$JAR" -H "X-CSRF-Token: $CSRF" -F "file=@$f" "$BASE/api/documents")
    say "  upload $(basename "$f") -> HTTP $code"
  done

say "PHASE $QUERIES queries"
QUESTIONS=("What is the minimum attendance requirement?" "What are the lab safety rules?" "How are internal assessment marks calculated?" "What is the syllabus for the first unit?" "Who won the 1998 football world cup?")
ok=0
for i in $(seq 1 "$QUERIES"); do
  q="${QUESTIONS[$(( (i - 1) % ${#QUESTIONS[@]} ))]}"
  if curl -fsS -N -c "$JAR" -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Content-Type: application/json' \
      --data "{\"question\": \"$q (#$i)\"}" "$BASE/api/chat" | grep -q '"type": "final"'; then ok=$((ok + 1)); fi
done
say "  completed answers: $ok/$QUERIES"

say "PHASE shutdown"
"${COMPOSE[@]}" down >>"$LOG" 2>&1
sleep 2
kill -INT "$TCPDUMP"; wait "$TCPDUMP" || true

say "analysis"
python3 "$HERE/verify_isolation.py" "$OUT/capture.pcap" --json > "$OUT/analysis.json" || true
python3 "$HERE/verify_isolation.py" "$OUT/capture.pcap" | tee "$OUT/analysis.txt" || true
rm -f "$JAR"
sha256sum "$OUT"/capture.pcap "$OUT"/analysis.json | tee "$OUT/SHA256SUMS"
say "evidence saved in $OUT"
