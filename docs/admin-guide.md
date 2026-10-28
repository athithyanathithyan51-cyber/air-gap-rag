# Admin guide

## 1. Install on the air-gapped machine

**Requirements**
- Ubuntu 22.04 or 24.04 (amd64).
- At least 4 cores and 16 GB RAM. Below 16 GB, use the 3B model (section 5).
- 30 GB of free disk.
- Docker is not required beforehand: the bundle carries Docker Engine.

**Steps**
1. On the connected build machine, run `bundle/build_bundle.sh <version>`. Copy `airgap-assistant-<version>.tar` and its `.sha256` to removable media.
2. On the air-gapped machine:

```bash
sha256sum -c airgap-assistant-<version>.tar.sha256     # transfer integrity
tar -xf airgap-assistant-<version>.tar
cd airgap-assistant-<version>
sudo ./install.sh
```

`install.sh` performs these steps:
1. Verifies every file against `manifest.sha256`, and aborts on any mismatch.
2. Installs Docker Engine from the bundled `.deb` files if Docker is missing.
3. Loads the images.
4. Restores the model weights.
5. Generates the attestation-key passphrase in `/etc/airgap/attestation.pass`, readable by root only.
6. Starts the services and waits for `/ready`.
7. Asks you to create the first admin account.

**After install**
- Open `http://127.0.0.1:8000/` on that machine.
- Back up `/etc/airgap/attestation.pass` offline. Without it, the attestation signing key cannot be decrypted.

## 2. Users
- **Create users:** use the **Admin → Users** page (UI), or the CLI:
  `sudo docker compose -p airgap -f /opt/airgap/docker-compose.yml exec app python -m app.cli create-user NAME --role user`
- **Roles:** `admin` can upload or remove documents, manage users, read the audit log, export the attestation chain and acknowledge isolation breaks. `user` can ask questions, view citations and verify their own answers.
- **Passwords:** argon2id-hashed, minimum 10 characters.
- **Disabling a user** revokes their refresh tokens immediately. Their current access token stays valid for at most 15 minutes.

## 3. Documents
- **Formats:** PDF (text layer), DOCX, Markdown and plain text, up to 50 MB each.
- **Not supported yet:** scanned PDFs. OCR is planned for v1.0.0.
- **File type:** decided by content, not by extension. Executables and other formats are rejected.
- **Same filename:** uploading a changed file with the same filename replaces the old version, including its chunks and vectors.
- **Identical copies:** byte-identical files are recognised by SHA-256 and not processed twice.

## 4. Isolation monitor and attestation
- **Header badge:** shows `ISOLATED` or `NOT ISOLATED`. The monitor checks interfaces and default routes every second.
- **Breaks latch:** if any disallowed interface comes up, every later answer is recorded as NOT-ISOLATED until an admin presses **Acknowledge**. Acknowledging only works once the machine is isolated again, and the acknowledgement is audit-logged.
- **Export for an auditor:** use **Admin → Export chain** and **Public key**. The auditor runs:
  `python3 verify_chain.py attestation-chain.jsonl --pubkey attestation.pub`
  The script needs only Python 3 and the `cryptography` package. Exit codes: 0 = valid and all isolated, 1 = broken chain, 2 = valid but contains NOT-ISOLATED records.
- **Policy:**
  - Strict mode is the default. A record is ISOLATED only if there is no default route, no physical interface is up, and every other up interface is allowlisted. The default allowlist is `docker0` and `br-*` (Docker's host-only bridges).
  - Tunnels (`tun*`, `wg*`, `ppp*` …) are never allowed.
  - Change the allowlist via `AIRGAP_ISOLATION_ALLOW` in `/etc/airgap/airgap.env`. It is a JSON list, for example `["docker0","br-*"]`.

## 5. Configuration (`/etc/airgap/airgap.env`)
| Variable | Default | Meaning |
|---|---|---|
| `AIRGAP_CHAT_MODEL` | `llama3.2:3b-instruct-q4_K_M` | `qwen2.5:7b-instruct-q4_K_M` gives better citations and resists prompt injection better, but is about 2x slower (p95 63 s vs 34 s on an i5-12450H / 16 GB laptop). Use it on machines with more than 16 GB RAM or a GPU |
| `AIRGAP_MIN_SCORE` | `0.55` | Retrieval similarity below which the question is refused ("not in the documents") without calling the model. Tune it with `eval/run_eval.py` |
| `AIRGAP_GENERAL_CHAT` | `true` | Below `AIRGAP_MIN_SCORE`, answer greetings and general questions from the model's own knowledge, labelled "General answer, not from your documents". Set `false` for strict documents-only mode (refusals only) |
| `AIRGAP_TOP_K` | `3` | Passages retrieved per question. Fewer passages make a shorter prompt and a faster answer. On the demo set, 3 finds the right document as often as 5 |
| `AIRGAP_MAX_CONTEXT_CHARS` | `8000` | Maximum document text sent to the model per question |
| `AIRGAP_LLM_NUM_CTX` | `4096` | Model context window, in tokens. Larger uses more RAM/VRAM and is slower |
| `AIRGAP_LLM_NUM_PREDICT` | `512` | Maximum answer length, in tokens |
| `AIRGAP_LLM_WARM_UP` | `true` | Load the models at startup, so the first question does not wait 30–40 s for them |
| `AIRGAP_METRICS_ENABLED` | `false` | Serve Prometheus text metrics at `/metrics`: request counts and latency by route template. The endpoint has no login, so turn it on only for a local scraper |
| `AIRGAP_BIND_HOST` | `127.0.0.1` | Keep this on loopback. Exposing it on a LAN needs TLS (v1.0.0) and LAN isolation mode |

Apply changes with:
`sudo docker compose -p airgap -f /opt/airgap/docker-compose.yml --env-file /etc/airgap/airgap.env up -d`

**NVIDIA GPU (optional, much faster).** If the host has an NVIDIA GPU, its driver and `nvidia-container-toolkit` installed, add `-f /opt/airgap/docker-compose.gpu.yml` after the first `-f`. The RC1 bundle does not ship the toolkit. Check with `sudo docker exec airgap-ollama-1 ollama ps`: the PROCESSOR column should say `100% GPU`.

## 6. Backup, upgrade, rollback
- **Upgrade:** unpack the new bundle and run `sudo ./install.sh`. The app-data volume (users, documents, audit, chain) is backed up to `/var/backups/airgap/` first.
- **Rollback:** run `sudo ./rollback.sh`. It restores the previous image version and the backup taken during the upgrade.
- **Backup (application data):** stop the app, then run
  `python -m app.cli backup OUT.tar.gz`
  It writes the database (a consistent snapshot), the attestation keys and the uploaded documents, with a SHA-256 for every file in `MANIFEST.json`. The archive is **not encrypted** and holds the JWT secret and the attestation key file, so store it like the rest of the sensitive data. Logs are not included.
- **Restore:** stop the app, then run `python -m app.cli restore IN.tar.gz`. Every hash is checked before anything is written, and the archive is rejected if a file was changed or an unexpected path appears. If data already exists, pass `--force`: the old database, keys and documents are moved aside as `*.before-restore-<time>`, not deleted.
- **Measured (dev laptop, Windows, not the target Ubuntu machine):** a backup of the demo data (10 files, 293 KB) restored into an empty folder with the database integrity check passing. Automated tests cover tampering, path traversal, missing manifests and overwrite refusal. Restoring on a clean Ubuntu machine is **untested**.
- **Disk full:** an upload that runs out of space returns HTTP 507 with "disk is full: free space, then upload again". Tested with a simulated `ENOSPC`. A real full disk is **untested**.
- **Manual backup (Docker volume):**
  `sudo docker run --rm -v airgap_app_data:/d:ro -v $PWD:/b --entrypoint tar ollama/ollama:0.40.2 -C /d -czf /b/app_data.tgz .`
  Also keep `/etc/airgap/`.
- **Uninstall:** `sudo ./uninstall.sh`, which keeps data. Use `--purge` to delete everything.

## 7. Evidence of offline operation
Run `sudo scripts/capture_traffic.sh --user admin --password-file pw.txt --docs <dir>`.

It captures all interfaces during startup, ingestion, 100 questions and shutdown, then counts non-loopback packets. The output is saved under `evidence/<timestamp>/`.
