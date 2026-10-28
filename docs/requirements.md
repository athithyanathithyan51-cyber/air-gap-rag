# Requirements

Status key: **planned** (not built), **built** (code exists, tests listed), **measured** (evidence file saved). Nothing is marked measured until we have run it.

| ID | Requirement | Acceptance test | Release | Status |
|----|-------------|-----------------|---------|--------|
| R1 | Zero network calls at runtime: no telemetry, CDN assets or downloads after install | `backend/tests/test_net_guard.py` (in-process guard); `frontend/scripts/check-no-external.mjs` (built UI); Qdrant telemetry disabled in compose; packet capture during startup, ingest, 100 queries and shutdown counted by `scripts/verify_isolation.py` | RC1 | guard + UI check built; capture **untested** |
| R2 | Answers only from ingested documents, with citations (document + page/section); a refusal ("not in the documents") below the threshold. With general chat on (default), below the threshold the model answers small talk and general questions from its own knowledge, with no citations, labelled "General answer, not from your documents". `AIRGAP_GENERAL_CHAT=false` restores strict mode. The eval counts general answers as refusals | Gold-set evaluation (`eval/run_eval.py`): citation accuracy, refusal precision/recall | RC1 | measured on the 50-question set using DEMO documents, 28 Oct 2026 (`eval/results/20261028T103446Z-rc1-final`): citation accuracy 1.0, refusal precision 0.93, recall 1.0, 1 false refusal of 37 answerable; hallucination rate **untested** until `review.csv` is marked by hand; real BIT documents **untested** |
| R3 | Installs on a clean air-gapped machine from one bundle using only the README | Fresh Ubuntu VM with the network adapter disabled, install log saved | v1.0.0 (RC1: WSL with network off) | planned |
| R4 | Multi-user login, roles (admin, user), secure sessions, encryption at rest, audit log | Auth API tests (`test_api.py`: login, roles, CSRF, refresh rotation, rate limit, admin user management, audit export); encryption test for the signing key (`test_attestation.py`) | RC1 minimal; encryption v1.0.0 | built (chunk text not yet encrypted, see `limits.md`) |
| R5 | Isolation attestation on every answer | `verify_chain.py` passes on a clean chain, fails on a tampered block, flags a simulated interface-up (`test_attestation.py`: clean chain, tampered and deleted blocks, re-signed forgery, latching break, monitor thread, CLI) | RC1 MVP | built |
| R6 | Runs on a normal laptop or small server, no GPU | Measured RAM/CPU/latency on the 4-core/16 GB floor | v1.0.0 | 12-core, 15.7 GB laptop measured 28 Oct (see R2 evidence): total p50 1.58 s, p95 5.6 s, peak RAM 15.5 GB. **4-core floor untested** |
| R7 | Every claim in docs, slides and report is backed by a test or measurement | Review checklist before each tag; `docs/limits.md` lists all untested claims | every tag | ongoing |

## Target environment (locked 10 Oct 2026)
- **OS:** Ubuntu 22.04/24.04 LTS is primary. Windows 11 with Docker Desktop is secondary (attestation limits apply; see `limits.md`).
- **Minimum hardware:** 4 CPU cores, 16 GB RAM, 30 GB disk, no GPU.
- **Scale:** one machine serving 1–10 users.

## Non-goals
- No cloud fallback of any kind.
- No proof that packets were never sent. Attestation records interface state only (see `attestation-spec.md`).
- No fine-tuning of models.
