# Offline LLM-Based Intelligent Conversational Assistant for Secure Air-Gapped Networks

A fully offline, document-grounded assistant for air-gapped machines. It answers questions only from your own documents, cites the document and page for every answer, and replies "I don't know" when the documents do not support an answer.

Its key feature is **self-contained isolation attestation**. Every answer is written to a signed hash chain together with a snapshot of the machine's network interfaces. This makes it a *tamper-evident record of network-interface state at the moment of each answer*, which an auditor can check offline with `verify_chain.py`. It is **not** proof that no packet was ever sent; see [docs/attestation-spec.md](docs/attestation-spec.md) and [docs/limits.md](docs/limits.md).

> **Status:** Phase 1 (scaffold). The product is not usable yet. Performance and isolation claims are **untested** until measurements are published under `eval/results/` and `docs/evidence/`.

BIT S5 Mini Project I · BIP ID IT11196 · Guide: Manisha G
Team: Athithyan G (backend, RAG, attestation) · Praneeth C P (frontend, integration) · Atchayaraj M (ingestion, verification, documentation)

## Target environment
- **OS:** Ubuntu 22.04/24.04 LTS is primary. Windows 11 with Docker Desktop is secondary.
- **Hardware floor:** 4 cores, 16 GB RAM, 30 GB disk. No GPU.
- **Scale:** 1–10 users.

## Install (offline bundle)
The offline bundle and its install script arrive in Phase 2. These steps will be filled in once `bundle/build_bundle.sh` exists and has been tested.

## Development
Prerequisites: [micromamba](https://mamba.readthedocs.io/) 2.x, Node 22 and Docker.

Python packages come only from conda-forge. `backend/conda-lock.yml` pins exact versions with sha256 hashes for linux-64 and win-64, and the same lockfile is used in dev, CI and the Docker image.

```bash
# backend
cd backend
micromamba create -n airgap -f conda-lock.yml
micromamba run -n airgap ruff check .
micromamba run -n airgap mypy
micromamba run -n airgap pytest
micromamba run -n airgap python -m app.main      # http://127.0.0.1:8000/health

# after editing environment.yml, regenerate the lockfile:
conda-lock lock --micromamba -f environment.yml -p linux-64 -p win-64 --lockfile conda-lock.yml

# frontend
cd frontend
npm ci
npm run lint && npm test && npm run build
```

## Repository layout
| Path | Contents |
|------|----------|
| `backend/` | FastAPI app: `app`, `api`, `rag`, `ingest`, `auth`, `attestation`, `db`, `tests` |
| `frontend/` | React + TypeScript + Vite + Tailwind UI |
| `deploy/` | Dockerfile, docker-compose.yml, install scripts |
| `bundle/` | Offline bundle builder and SHA-256 manifest |
| `eval/` | Gold question set, evaluation runner, measured results |
| `docs/` | Requirements, architecture, threat model, attestation spec, limits |
| `scripts/` | Traffic capture and isolation verification |

## Licence
MIT. See [LICENSE](LICENSE). Model licences: Qwen2.5 (Apache-2.0), Llama 3.2 (Llama 3.2 Community License), nomic-embed-text (Apache-2.0).
