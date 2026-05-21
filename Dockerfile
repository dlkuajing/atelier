FROM python:3.12-slim AS base

# uv = fast Python package manager (Astral). Multi-stage copy keeps image lean.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# System deps for scientific Python (Optiland/prysm need BLAS/LAPACK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libffi-dev \
    libssl-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first (Docker layer cache friendliness)
COPY pyproject.toml ./
COPY .python-version ./

# Install runtime deps (without project itself, for cache stability)
RUN uv sync --no-install-project --extra optical

# Now copy source and install project
COPY app ./app
COPY scripts ./scripts
RUN uv sync --extra optical

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
