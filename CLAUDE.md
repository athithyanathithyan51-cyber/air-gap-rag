# CLAUDE.md — Project rules (persist across sessions)

## Working rules
- Act as lead engineer. Be direct and brief.
- Write complete, runnable code: no placeholders, TODOs or pseudo-code.
- Never invent benchmarks, test results, packet counts or citations. Anything we have not measured is labelled "untested".
- Correct the user's English mistakes briefly.
- The user has granted autonomy: make routine decisions without asking. Ask one short question only when truly blocked.

---

# PROJECT BRIEF

## PRODUCT
**Official title:** Offline LLM-Based Intelligent Conversational Assistant for Secure Air-Gapped Networks.
**Key feature:** Self-contained attestation of network isolation.

A fully offline, document-grounded assistant for air-gapped machines:
- It runs a local open-weight language model with retrieval over a private document set.
- It cites the source of every answer, and declines to answer when the documents do not support one.
- It writes each answer to a signed hash chain, together with a snapshot of the machine's network-interface state. An auditor can later check, offline and without re-running anything, that the answer was generated while no non-loopback network interface was active.

**Use case:** answering questions from an organisation's internal technical manuals and policy documents. Demo document set: BIT lab manuals, the syllabus and department policy documents.

**Context:** S5 Mini Project I, Bannari Amman Institute of Technology, CSE, BIP ID IT11196, guide Manisha G.

**Team:**
- Athithyan G: backend, RAG, attestation
- Praneeth C P: frontend, integration
- Atchayaraj M: ingestion, verification, documentation

## DEADLINES (project start: Sat 10 Oct 2026)
- **RC1 (review release):** tagged by Tue 13 Oct night, for the second review Wed 14 to Fri 16 Oct.
- **ICAI-CEME 2026 online presentation:** 21–22 Oct.
- **v1.0.0 final:** Sat 31 Oct.

RC1 is a thin vertical slice that works end to end and installs offline. Do not build everything halfway. Anything that does not fit moves to v1.0.0. Say early when something will not fit. Cut scope, never quality or honesty.

RC1 scope cuts, moved to v1.0.0:
- local TLS CA
- nftables enforcement
- Prometheus metrics
- bge-reranker
- encryption at rest for chunk text
- systemd install path
- full Playwright tests
- SBOM and licence report
- backup, restore and rollback
- full 50-question gold set (RC1 has about 20 questions)

## HARD REQUIREMENTS
1. Zero network calls at runtime: no telemetry, no CDN assets, no downloads after install.
2. Answers come only from ingested documents, with citations (document and page/section). Below the confidence threshold, refuse (a templated "not in the documents" reply, never model-invented content).
3. Installs on a clean air-gapped machine from one transfer bundle, following the README alone.
4. Multi-user login with roles (admin, user), secure sessions, encryption at rest and an audit log.
5. Isolation attestation on every answer.
6. Runs on a normal laptop or small server. No GPU required.
7. Every claim in the docs, slides and report is backed by a test or measurement we ran. If a claim is not measured yet, it says "untested".

## TARGET ENVIRONMENT (locked)
- **Primary:** Ubuntu 22.04/24.04 LTS.
- **Secondary:** Windows 11 via Docker Desktop.
- **Floor:** 4 cores, 16 GB RAM, 30 GB disk.
- **Scale:** one machine, 1 to 10 users.

## STACK (pin exact versions in lockfiles)
- **Inference:** Ollama.
  - Default model (RC1): llama3.2:3b-instruct-q4_K_M. Optional larger model: qwen2.5:7b-instruct-q4_K_M (2x slower on 16 GB; candidate default for the semester-end review). Decision and evidence: docs/architecture.md.
  - Embeddings: nomic-embed-text.
  - Optional offline reranker: bge-reranker.
- **Backend:** Python 3.11, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy 2 + Alembic, SQLite (WAL).
- **Vector store:** Qdrant, local, with metadata for citations.
- **Ingestion:**
  - Parsers: pypdf, pdfplumber, python-docx, text/markdown, with a Tesseract OCR fallback using offline data.
  - Chunking: structure-aware chunks (~800 tokens, 100 overlap), content-hash dedup, incremental re-ingest.
- **Frontend:**
  - React + TypeScript + Vite + Tailwind, built once and served by FastAPI.
  - SSE streaming.
  - No external fonts or CDNs. Vendored npm cache.
- **Security:**
  - argon2id password hashing.
  - Short-lived JWT, with rotating refresh tokens in httpOnly cookies.
  - CSRF protection, rate limiting, upload limits and type sniffing.
  - AES-GCM or Fernet at rest, with the key derived from an admin passphrase.
  - Local TLS CA and security headers.
- **RAG safety:** document text is untrusted (prompt-injection defence), a citation grounding check, and a refusal threshold tuned on the evaluation set.
- **Ops:** JSON logs with rotation, /health and /ready, local Prometheus metrics.
- **Packaging:**
  - Docker Compose (app, qdrant, ollama) with `docker save` images, plus a systemd install script.
  - The bundle holds the images or a wheelhouse, the built frontend, model files with a SHA-256 manifest, Tesseract data, install/uninstall/rollback scripts and the README.
- **Quality:**
  - pytest, Playwright, ruff, mypy, pre-commit.
  - GitHub Actions. CI runs outside the air gap; the built artifact is what gets transferred.
  - CycloneDX SBOM and a licence report.
- **Evaluation:**
  - A 50-question gold set over our real documents, including unanswerable questions.
  - Report hit-rate@k, citation accuracy, refusal precision/recall, hallucination rate (manual review), latency p50/p95, RAM and CPU. All measured.

## ATTESTATION (attestation.py, isolation_monitor.py, verify_chain.py)
Each answer is recorded as a block containing:
- index
- UTC timestamp
- monotonic counter
- query hash
- retrieved-chunk hashes
- answer hash
- citations
- network snapshot: every non-loopback interface (up/down, addresses) and the default route
- previous block hash
- an Ed25519 signature from a local keypair (private key encrypted at rest)

How the pieces behave:
- `isolation_monitor` runs continuously. If any non-loopback interface comes up, it logs a break event and flags every later block NOT-ISOLATED until the admin acknowledges.
- `verify_chain.py` is a standalone offline CLI that reports the first broken or non-isolated block.
- The UI has a "Verify this answer" button.
- Optional enforcement with nftables rules for the app user.

Describe it exactly as: **a tamper-evident record of network-interface state at the moment of each answer.** Do NOT describe it as proof that no packet was ever sent.

Put these limits in the docs and the UI help text:
- It is tamper-evident, not tamper-proof: someone with host access and the key can forge blocks.
- A snapshot shows interface state at one moment, not all traffic.
- Clock manipulation affects timestamps. The monotonic counter mitigates this.
- Packet captures are the separate evidence for "no traffic".

Prior art found:
- an arXiv egress-monitor paper for LLM agents
- PyPI model-witness (cloud key and public blockchain anchor)
- Rebootix zero-egress marketing
- TEE-based schemes

The only gap we claim: self-contained on one machine with no anchor, cloud key or TEE, and binding each RAG answer's citations to the isolation state. This is a design contribution for the BIT IPR/IIC cell to evaluate, not a granted or confirmed patent. Section 3(k) of the Indian Patents Act excludes software per se, so any claim must stress the technical mechanism.

## OFFLINE PROOF
Capture traffic with tcpdump or Wireshark during startup, ingestion, 100 queries and shutdown, and save the captures as .pcap. Add a script that counts packets to non-loopback destinations. Until this is run, every statement about zero traffic is "untested".

## REPO STRUCTURE
- `/backend` (app, api, rag, ingest, auth, attestation, db, tests)
- `/frontend` (src, tests)
- `/deploy` (docker-compose.yml, systemd units, install.sh, uninstall.sh, rollback.sh, nftables.conf)
- `/bundle` (build_bundle.sh, manifest.sha256)
- `/eval` (gold_set.jsonl, run_eval.py, results/)
- `/docs` (architecture, threat-model, user-guide, admin-guide, runbook, attestation-spec, limits)
- `/scripts` (capture_traffic.sh, verify_isolation.py)

## PHASES (finish and test each before the next)
1. Requirements, threat model, architecture, scaffold, CI.
2. Offline environment and reproducible bundle.
3. Ingestion plus tests.
4. Retrieval, reranking, grounded generation, citations, refusal, evaluation.
5. Auth, roles, encryption, audit log, rate limiting.
6. Frontend.
7. Attestation, monitor, verifier, tamper tests.
8. Hardening: security review, dependency audit, failure handling (Ollama down, disk full, corrupt PDF), backup/restore, upgrade/rollback.
9. Clean-machine install with the network physically off, plus packet-capture proof.
10. Docs, report, slides, demo script, tag v1.0.0.

RC1 = phases 1 to 4, a minimal 5 and 6, and the MVP of 7.

## HOW WE WORK
- Plan each phase (file list) before building.
- Git:
  - one branch per phase
  - a commit after every passing module
  - tags rc1 and v1.0.0
- GitHub: the remote, issues per module, pull requests and Actions CI.
- Run tests and show the real output. Never claim a test passes without running it.
- After each module, report: purpose, files changed, run commands, test commands, real output, known limits.
- Never use the network inside product code. Downloading dependencies and models during development is fine. Record every downloaded artifact in the bundle manifest.

## ACCEPTANCE CRITERIA FOR "FINAL"
- A fresh Ubuntu VM with networking disabled installs and runs from the bundle by README alone.
- All tests pass in CI and on the VM.
- The capture shows zero non-loopback packets (measured, file saved).
- Evaluation results are measured and reported honestly, including failures.
- verify_chain.py detects a tampered block and an isolation break.
- The docs let someone else install, operate, back up, upgrade and troubleshoot without us.

## LATER DELIVERABLES (ask the user first)
- Weekly BIP work-log entries per member, written from what was actually done.
- Review slides in BIT's template:
  - 16:9, max 25 slides, Cambria, white background
  - headings: blue, uppercase, bold, 24
  - subheadings: maroon/violet/green, 24
  - content: black, 20
- Review speeches.
- Project report.
- A one-page technical summary for the IPR cell.
