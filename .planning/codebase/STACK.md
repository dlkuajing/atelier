# Technology Stack

**Analysis Date:** 2026-07-03

## Languages

**Primary:**
- Python 3.12 - Full backend implementation, optical calculations, ray tracing, LLM integration

## Runtime

**Environment:**
- Python 3.12 (specified in `.python-version`)

**Package Manager:**
- uv (Astral's fast Python package manager)
- Lockfile: `uv.lock` (frozen, pinned dependencies)

## Frameworks

**Core:**
- FastAPI 0.115.0+ - HTTP API server, CORS, routing
- Uvicorn 0.32.0+ - ASGI application server (2 workers on Fly.io shared-cpu-2x)

**Data & Configuration:**
- Pydantic 2.9.0+ - Data validation, request/response schemas
- Pydantic-settings 2.5.0+ - Environment-based configuration management

**Testing:**
- pytest 8.3.0+ - Test runner
- pytest-asyncio 0.24.0+ - Async test support
- Coverage target: 131 tests across health, optical math, Optiland integration, parameter guards, RAG, LLM parsing, FastAPI contracts

**Build/Dev:**
- ruff 0.7.0+ - Fast Python linter (rules: E, F, W, I, UP, B, C4, SIM; line-length 100)
- mypy 1.13.0+ - Static type checking
- Docker multi-stage build (optimized for optical dependencies)

## Key Dependencies

**Critical:**
- numpy 2.0.0+ - Numerical computing, matrix operations for optical calculations
- scipy 1.14.0+ - Scientific computation (Snell's law, matrix operations)
- openai 1.50.0+ - OpenAI-compatible relay client (Claude, GPT, Gemini models)
- anthropic 0.40.0+ - Anthropic SDK (not currently active; kept for potential future use)
- httpx 0.27.0+ - Async HTTP client (used by Pydantic)
- python-multipart 0.0.10 - Multipart form/file upload support

**Optical Libraries:**
- optiland 0.6.0+ - Ray tracing, MTF/PSF, Zernike polynomials, aberration analysis
- rayoptics 0.9.5 - Alternative optical engine, SVG renderer hook (currently unused)
- opticalglass 1.1.0+ - Lens material refractive index data (CC0 refractiveindex.info)

**Observability:**
- structlog 24.4.0+ - Structured logging with JSON output

**Database (Wave 2, not yet live):**
- psycopg[binary] 3.2.0+ - PostgreSQL async driver
- pgvector 0.3.0+ - PostgreSQL vector extension client for RAG embeddings

## Configuration

**Environment:**
- `.env` file (gitignored, contains secrets)
- Case-insensitive environment variable loading via `app/core/config.py`
- Required vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`
- Optional: `DATABASE_URL`, `EPO_OPS_KEY`, `EPO_OPS_SECRET`, `CF_ACCOUNT_ID`, `CF_AI_GATEWAY_URL`, `CF_AI_GATEWAY_TOKEN`, `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
- Production baked-in: `ENV=production`, `LOG_LEVEL=INFO`, `CORS_ALLOWED_ORIGINS=https://lumirahq.com,...`

**Build:**
- `Dockerfile` - Multi-stage (base, deps, final)
- `fly.toml` - Fly.io deployment config (Singapore region, 2 vCPU shared, 2GB RAM, uvicorn 2 workers)
- `pyproject.toml` - Project metadata, dependency groups (core, dev, optical)

## Platform Requirements

**Development:**
- Python 3.12
- uv package manager
- BLAS/LAPACK libraries for numpy/scipy (Debian: `libopenblas-dev liblapack-dev`)
- libffi-dev, libssl-dev for binary packages
- Windows: `PYTHONUTF8=1` environment variable required for UTF-8 test data (Chinese characters)

**Production:**
- Docker container on Fly.io (shared-cpu-2x, 2GB RAM, Singapore region)
- OpenAI-compatible relay endpoint (`api.openbili.com/v1` default, configurable)
- Optional: PostgreSQL 14+ with pgvector extension (Wave 2)
- Health check endpoint: `GET /health` (container readiness)

**Performance Notes:**
- Cold start: ~100s (12s uv bytecode compile + 8s uvicorn boot + Optiland/scipy/numpy imports)
- Keep 1 machine always running to avoid cold-start 503 errors
- LLM relay round-trip (~200-400ms) is the primary bottleneck, not CPU math
- Optiland peak memory: ~1.2GB during raytrace; 2GB headroom for concurrent requests

---

*Stack analysis: 2026-07-03*
