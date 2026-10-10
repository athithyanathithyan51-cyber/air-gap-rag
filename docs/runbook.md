# Runbook (troubleshooting)

All commands assume the following alias:

`alias ag='sudo docker compose -p airgap -f /opt/airgap/docker-compose.yml --env-file /etc/airgap/airgap.env'`

| Symptom | Check | Fix |
|---|---|---|
| Page does not load | `ag ps`, `curl -s 127.0.0.1:8000/health` | `ag up -d`; read `ag logs --tail 100 app` |
| `/ready` returns 503 for `ollama` | `ag logs ollama`; `ag exec ollama ollama list` | Model missing: re-run `install.sh` (it restores the weights). Not enough RAM: switch to the 3B model (admin guide §5) |
| `/ready` returns 503 for `qdrant` | `ag logs qdrant` | Disk full? Run `df -h /var/lib/docker`. Free space, then `ag restart qdrant` |
| Chat says "local language model is unavailable" | Ollama is down or timed out | `ag restart ollama`; the first answer after a restart loads the model and is slow |
| Every answer is "I don't know" | Admin → Documents: are they `ready` with chunks above 0? | Re-upload. Scanned PDFs have no text (OCR comes in v1.0.0). `AIRGAP_MIN_SCORE` may be too high |
| Upload rejected (415) | The message says why: corrupt PDF, encrypted PDF, unsupported type | Re-export the file as PDF or DOCX |
| Badge shows NOT ISOLATED | Admin → Isolation attestation shows the reasons (`ip -br link`, `ip route`) | Disconnect or disable the interface or default route, then **Acknowledge** |
| Login always fails after a password reset | Rate limit: 10 attempts per minute per client | Wait one minute |
| App will not start: "cannot decrypt attestation key" | `/etc/airgap/attestation.pass` changed or lost | Restore the passphrase from the offline backup. Without it, the old chain stays verifiable with the public key, but no new blocks can be signed by that key |
| `install.sh`: "bundle files do not match manifest" | The transfer is corrupted or the bundle was tampered with | Copy the bundle again and check the `.tar.sha256` |
| `install.sh`: dpkg fails | Missing base packages (e.g. `iptables`) on a minimal install | Install them from the Ubuntu install media, then re-run |

**Logs**
- `ag logs app` shows the JSON lines.
- Rotated files are in the `airgap_app_data` volume under `logs/`.

**Audit trail**
- Admin → Audit log shows logins, uploads, answers (question hash plus attestation index), isolation breaks and acknowledgements.
