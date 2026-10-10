# Requirements

Status key: **planned** (not built), **built** (code exists, tests listed), **measured** (evidence file saved). Nothing is marked measured until we have run it.

| ID | Requirement | Acceptance test | Release | Status |
|----|-------------|-----------------|---------|--------|
| R1 | Zero network calls at runtime: no telemetry, CDN assets or downloads after install | `backend/tests/test_net_guard.py` (in-process guard); `frontend/scripts/check-no-external.mjs` (built UI); Qdrant telemetry disabled in compose; packet capture during startup, ingest, 100 queries and shutdown counted by `scripts/verify_isolation.py` | RC1 | guard + UI check built; capture **untested** |
| R2 | Answers only from ingested documents, with citations (document + page/section); "I don't know" below the threshold | Gold-set evaluation (`eval/run_eval.py`): citation accuracy, refusal precision/recall | RC1 | planned |
| R3 | Installs on a clean air-gapped machine from one bundle using only the README | Fresh Ubuntu VM with the network adapter disabled, install log saved | v1.0.0 (RC1: WSL with network off) | planned |
| R4 | Multi-user login, roles (admin, user), secure sessions, encryption at rest, audit log | Auth API tests; encryption at rest test | RC1 minimal; encryption v1.0.0 | planned |
| R5 | Isolation attestation on every answer | `verify_chain.py` passes on a clean chain, fails on a tampered block, flags a simulated interface-up | RC1 MVP | planned |
| R6 | Runs on a normal laptop or small server, no GPU | Measured RAM/CPU/latency on the 4-core/16 GB floor | v1.0.0 | **untested** |
| R7 | Every claim in docs, slides and report is backed by a test or measurement | Review checklist before each tag; `docs/limits.md` lists all untested claims | every tag | ongoing |

## Target environment (locked 10 Oct 2026)
- **OS:** Ubuntu 22.04/24.04 LTS is primary. Windows 11 with Docker Desktop is secondary (attestation limits apply; see `limits.md`).
- **Minimum hardware:** 4 CPU cores, 16 GB RAM, 30 GB disk, no GPU.
- **Scale:** one machine serving 1–10 users.

## Non-goals
- No cloud fallback of any kind.
- No proof that packets were never sent. Attestation records interface state only (see `attestation-spec.md`).
- No fine-tuning of models.
