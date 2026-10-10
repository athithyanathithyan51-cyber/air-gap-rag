# Threat model (STRIDE)

## Assets
- **A1 Documents:** ingested files and chunk text. These are confidential.
- **A2 Q&A history:** questions and answers. These are confidential.
- **A3 Attestation chain and signing key:** their integrity matters.
- **A4 User credentials and sessions.**
- **A5 Model weights and container images:** integrity of the supply chain.

## Trust boundaries
- **TB1 Browser ↔ app:** HTTP on loopback in RC1, local TLS in v1.0.0.
- **TB2 App ↔ Qdrant/Ollama:** loopback HTTP on the same host.
- **TB3 Document text ↔ LLM prompt:** document content is untrusted input.
- **TB4 Bundle transfer:** USB from a connected build machine to the air-gapped host.

## Adversaries
- **E1** An authenticated user overreaching their role.
- **E2** An unauthenticated local user, or a user on the isolated LAN.
- **E3** A malicious document author (prompt injection).
- **E4** A supply-chain attacker on the build side.
- **E5** An insider with root on the host. Mostly out of scope; see "Residual risks".

## Threats and mitigations

| STRIDE | Threat | Mitigation | Release |
|--------|--------|------------|---------|
| S | Session theft or forged JWT (E2) | argon2id passwords; short-lived JWT; rotating refresh token in an httpOnly SameSite=Strict cookie; CSRF token | RC1 minimal |
| S | Credential stuffing (E2) | Rate limiting on login | RC1 |
| T | Edit an attestation block (E1, E5) | Hash chain plus Ed25519 signatures; `verify_chain.py` | RC1 |
| T | Swapped model or image in the bundle (E4) | SHA-256 manifest of every artifact, checked by `install.sh`; images pinned by digest | RC1 manifest, v1.0.0 check |
| T | Prompt injection in documents makes the model ignore rules or leak data (E3) | Documents wrapped as quoted data with delimiters; system rules placed after the context; output restricted to cited chunk IDs; grounding check rejects uncited claims | RC1 |
| R | User denies asking a question (E1) | Append-only audit log; attestation block per answer | RC1 |
| I | Data exfiltration over the network (E3, E4) | In-process net guard; no external URLs in the UI plus a CSP; services bound to 127.0.0.1; Qdrant telemetry off; nftables egress drop for the app user | RC1; nftables v1.0.0 |
| I | Disk theft exposes documents (E2) | Encryption at rest with a key from the admin passphrase | v1.0.0 |
| I | User reads documents beyond their role (E1) | Role checks on every API route; admin-only ingestion | RC1 |
| D | Large or crafted uploads, PDF bombs (E1) | Upload size limits; MIME sniffing; parse timeouts and page caps | RC1 limits, v1.0.0 timeouts |
| D | Query flooding (E1) | Rate limits; Ollama parallelism caps | RC1 |
| E | XSS via document text or model output in the UI (E3) | React escaping; no `dangerouslySetInnerHTML`; strict CSP (`script-src 'self'`) | RC1 |
| E | Container breakout (E3) | Non-root user, `cap_drop: ALL`, `no-new-privileges`, read-only root filesystem | RC1 |

## Residual risks (stated, not solved)
- **Root or key holder can forge.** Root on the host, or anyone holding the admin passphrase, can forge attestation chains and read all data. Attestation is tamper-evident, not tamper-proof.
- **Snapshots, not traffic.** Snapshots miss interfaces that flap between polls.
- **Docker Desktop.** On Windows or macOS, attestation describes the Docker VM.
- **Vector leakage.** Qdrant vectors are not encrypted. Embeddings can leak some information about the text.
- **Unmeasured defence.** How well the prompt-injection defence works is **untested** until the evaluation set includes injection cases.
