# syntax=docker/dockerfile:1
#
# FastAPI + the ML model (v3). Build from the repository root:
#   docker compose build api        (or: docker build -f backend/Dockerfile .)
#
# Layers are ordered by how rarely they change: Python packages (~1 GB) and the LaBSE text
# encoder (~1.8 GB) are cached, so editing backend code only rebuilds the small final layers.

ARG PYTHON_IMAGE=python:3.14.3-slim-trixie

# ---------------------------------------------------------------------------------------------
# 1. Python dependencies, pinned (backend/requirements-api.lock), CPU-only torch.
FROM ${PYTHON_IMAGE} AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
RUN pip install --only-binary=:all: --index-url https://download.pytorch.org/whl/cpu "torch==2.12.1"
COPY backend/requirements-api.lock /tmp/requirements-api.lock
RUN pip install --only-binary=:all: -r /tmp/requirements-api.lock

# ---------------------------------------------------------------------------------------------
# 2. The exact LaBSE revision, checksum-verified, into an offline Hugging Face cache.
FROM deps AS labse
COPY deploy/labse/ /tmp/labse/
RUN python /tmp/labse/fetch_labse.py /opt/hf/hub /tmp/labse/labse.sha256

# ---------------------------------------------------------------------------------------------
# 3. The model file (model/trending_model_v3.joblib), verified byte-for-byte.
FROM ${PYTHON_IMAGE} AS artifacts
COPY model/trending_model_v3.joblib /opt/model/
COPY tests/fixtures/artifact_sha256.json deploy/verify_artifacts.py /tmp/
RUN python /tmp/verify_artifacts.py /opt/model /tmp/artifact_sha256.json

# ---------------------------------------------------------------------------------------------
# 4. Runtime: no build tools, no tests, no secrets, non-root.
FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /nonexistent --shell /usr/sbin/nologin app
COPY --from=deps /opt/venv /opt/venv
COPY --from=labse /opt/hf /opt/hf
COPY --from=artifacts /opt/model /srv/model
COPY ml/ /srv/ml/
COPY backend/app/ /srv/backend/app/

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/srv/backend:/srv \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ML_ARTIFACT_PATH=/srv/model/trending_model_v3.joblib \
    HF_HOME=/opt/hf \
    HF_HUB_CACHE=/opt/hf/hub \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    APP_ENV=production

# Compile once at build time (the container filesystem is read-only at runtime).
RUN python -m compileall -q /srv/backend /srv/ml

USER app
WORKDIR /srv
EXPOSE 8000

# Liveness only (no database access, cheap). Compose uses readiness separately.
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4).status == 200 else 1)"]

# ONE worker on purpose: each worker process loads its own copy of LaBSE + the model (~1.2 GB
# peak RSS, measured); prediction calls are serialized by a lock in PredictionService anyway.
# Scale with more containers/replicas rather than more workers per container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--no-server-header", "--timeout-graceful-shutdown", "20", "--log-level", "info"]
