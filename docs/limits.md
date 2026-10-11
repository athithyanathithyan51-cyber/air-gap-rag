# Known limits and untested claims

Each line stays here until a test or measurement replaces it. The evidence file is linked when it exists.

## Untested (no measurement yet)
| Claim | How it will be measured |
|-------|-------------------------|
| Zero non-loopback packets at runtime | tcpdump during startup, ingest, 100 queries and shutdown; `scripts/verify_isolation.py` |
| Runs on 4 cores / 16 GB with acceptable latency | `eval/run_eval.py` latency p50/p95, plus RAM/CPU sampling |
| Answer quality (hit-rate@k, citation accuracy, refusal precision/recall, hallucination rate) | Gold set over the real BIT documents |
| Prompt-injection resistance | Injection cases in the gold set |
| Clean install from the bundle using only the README | Fresh VM with networking disabled |
| Isolation monitor detection latency | Bring an interface up and time the break event |

## Design limits (permanent, by design)
- **Attestation is tamper-evident, not tamper-proof.** Host access plus the key allows forgery.
- **Attestation records interface state at a moment, not all traffic.**
- **Clock changes affect timestamps.** The monotonic counter keeps order.
- **Docker Desktop (Windows/macOS):** attestation reflects the Docker VM, not the physical host.
- **General answers are not grounded.** With `AIRGAP_GENERAL_CHAT=true`, questions that match no document are answered from the model's own training data. They carry no citations, can be wrong or out of date (the 3B model especially), and are labelled as such in the UI and in the attestation outcome (`answered:general`).
- **`net_guard` scope:** it covers Python socket use in the app process only. It does not cover native code that bypasses Python's socket module, or other processes.
- **Qdrant vectors are stored unencrypted.** Chunk-text encryption arrives in v1.0.0.

## Deferred from RC1 to v1.0.0
- Local TLS CA
- nftables enforcement
- Prometheus metrics
- bge-reranker
- Encryption at rest
- systemd install
- Full Playwright suite
- SBOM and licence report
- Backup, restore and rollback
- Full 50-question gold set
