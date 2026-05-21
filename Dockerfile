# Lumira Atelier Backend — production image for Fly.io.
#
# Multi-stage:
#  1. base   — python:3.12-slim + uv binary + system BLAS/LAPACK (numpy/scipy
#              wheels usually carry their own BLAS, but we keep dev libraries
#              so the optical group's bigger native deps still build cleanly).
#  2. deps   — install runtime deps without the project source, so docker
#              layer cache survives every code-only change.
#  3. final  — copy app/ + scripts/, install the project itself, run uvicorn.
#
# Optiland 0.6+ now covers MTF/PSF/Zernike natively — prysm and LiteLLM are
# both gone (see .planning/STATE.md "反悔与修正记录" §修正 7 + §修正 9).

# ──────────────────────────────────────────────────────────────────────
# Stage 1 — base
# ──────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

# uv = Astral's fast Python package manager. Copying the static binary out
# of the official uv image keeps the final layer thin (~25MB for uv itself).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Scientific Python deps (numpy / scipy / Optiland). Most wheels ship with
# bundled BLAS so libopenblas-dev is belt-and-suspenders — leaves us covered
# if a transitive dep needs to build from source.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libopenblas-dev \
        liblapack-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# ──────────────────────────────────────────────────────────────────────
# Stage 2 — runtime deps (cached layer)
# ──────────────────────────────────────────────────────────────────────
FROM base AS deps

COPY pyproject.toml uv.lock .python-version ./

# Production install: lock-file pinned, no dev group, plus the optical
# group (Optiland + rayoptics + opticalglass).
RUN uv sync \
        --frozen \
        --no-install-project \
        --no-dev \
        --group optical

# ──────────────────────────────────────────────────────────────────────
# Stage 3 — final image
# ──────────────────────────────────────────────────────────────────────
FROM deps AS final

COPY app ./app
COPY scripts ./scripts

# Install the project itself on top of the cached deps layer.
RUN uv sync --frozen --no-dev --group optical

EXPOSE 8000

# Health check matches fly.toml's [[http_service.checks]] path.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)" || exit 1

# uvicorn workers: Fly.io shared-cpu-2x has 2 vCPU, so 2 workers utilises both.
# `--proxy-headers` is required because Fly's front-door terminates TLS and
# forwards X-Forwarded-* to the container.
CMD ["uv", "run", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
