# Known limits and untested claims

Each line stays here until a test or measurement replaces it. The evidence file is linked when it exists.

## Untested (no measurement yet)
| Claim | How it will be measured |
|-------|-------------------------|
| Zero non-loopback packets at runtime | tcpdump during startup, ingest, 100 queries and shutdown; `scripts/verify_isolation.py` |
| Runs on the 4-core / 16 GB floor with acceptable latency | Measured on a 12-core, 15.7 GB laptop (`eval/results/20261028T103446Z-rc1-final`): total p50 1.58 s, p95 5.6 s; peak RAM 15.5 GB, peak CPU 87%. The 4-core floor itself is untested. |
| Hallucination rate | `review.csv` in the 28 Oct run is not yet hand-marked |
| Answer quality on the real BIT documents | The 28 Oct gold set (50 questions: 37 answerable, 13 not) used the DEMO documents only. Hit-rate@k 1.0, citation accuracy 1.0, refusal precision 0.93, recall 1.0 are measured on DEMO data. |
| Prompt-injection resistance | Not measured in the 28 Oct run |
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
- bge-reranker
- Encryption at rest
- systemd install
- Full Playwright suite
- SBOM and licence report
- Full gold set over the real BIT documents (the 28 Oct run used DEMO documents)
