# Build context: repository root.  docker build -f deploy/Dockerfile -t airgap-assistant:dev .
# Base images pinned by digest. Python packages come only from conda-forge via
# backend/conda-lock.yml (exact versions + sha256), the same lockfile used in dev and CI.
# The image keeps pytest/ruff/mypy so the test suite can be run on the air-gapped host.

FROM node:22-trixie-slim@sha256:154ba2f4d6fec323d28e4f4bb86bba4677f1223391a1979cf521304e03a98dfa AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

FROM mambaorg/micromamba:2.9.0-debian13@sha256:ed1bc6280b1eadf303610c00befaf9ba52dbacbc988ae4d7d9765801465f129e AS runtime
USER root
RUN mkdir -p /srv/data /opt/env && chown -R $MAMBA_USER:$MAMBA_USER /srv /opt/env
USER $MAMBA_USER
COPY --chown=$MAMBA_USER:$MAMBA_USER backend/conda-lock.yml /tmp/conda-lock.yml
RUN micromamba create -y -p /opt/env -f /tmp/conda-lock.yml \
 && micromamba clean -a -y \
 && rm /tmp/conda-lock.yml
COPY --chown=$MAMBA_USER:$MAMBA_USER backend/ /srv/backend/
COPY --chown=$MAMBA_USER:$MAMBA_USER scripts/ /srv/scripts/
COPY --from=frontend --chown=$MAMBA_USER:$MAMBA_USER /build/frontend/dist /srv/frontend/dist
ENV PATH=/opt/env/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AIRGAP_DATA_DIR=/srv/data \
    AIRGAP_LOG_DIR=/srv/data/logs
WORKDIR /srv/backend
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD ["/opt/env/bin/python", "-c", "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('AIRGAP_BIND_PORT','8000')+'/health', timeout=2)"]
ENTRYPOINT []
CMD ["/opt/env/bin/python", "-m", "app.main"]
