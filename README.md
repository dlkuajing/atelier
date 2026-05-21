# Lumira Atelier · Backend

Python FastAPI backend for the Lumira Atelier Optical Co-Pilot. Owns the heavy
work that can't (or shouldn't) run on Cloudflare Workers:

- **Deterministic optical calculations** — `app/core/optical_calc.py` (thin lens,
  paraxial, FOV, Airy disk, depth of field) — ground truth math the LLM is
  forbidden to estimate.
- **Optiland / prysm / rayoptics** — `app/api/optical.py` (Phase 2 wiring; Phase 0
  ships placeholder 501 routes).
- **pgvector + BGE-M3 + SigLIP-2 RAG** — `app/api/rag.py` (Phase 2 wiring).
- **Patent crawler** — `scripts/patent_crawler.py` (USPTO + Espacenet OPS, with
  `--dry-run`).
- **LiteLLM gateway config** — `litellm/` (HK VPS stack, see OWNER-CHECKLIST.md).

## Architecture role

```
┌───────────────┐  HTTPS+SSE  ┌─────────────────┐  HTTPS  ┌──────────────┐
│ Next.js (CF)  │ ──────────▶ │ FastAPI backend │ ──────▶ │ Optiland     │
│ Wizard UI     │             │ (this repo)     │         │ pgvector     │
└───────────────┘             └─────────────────┘         └──────────────┘
       │                              │
       ▼                              ▼
┌──────────────────┐           ┌─────────────────┐
│ LiteLLM HK proxy │           │ refractiveindex │
│ (Opus/GPT/Gemini)│           │ .info (CC0)     │
└──────────────────┘           └─────────────────┘
```

## Local development

```bash
cd lumira-backend
uv sync                       # core deps
uv sync --extra optical       # Optiland/prysm/rayoptics (slow first sync — needs BLAS)
cp .env.example .env          # fill in API keys (see ../.planning/phases/00-skeleton-data-prep/OWNER-CHECKLIST.md)
uv run uvicorn app.main:app --reload
```

OpenAPI explorer: http://localhost:8000/docs

## Tests

```bash
uv run pytest -v
```

Phase 0 ships:
- FastAPI health smoke test
- Deterministic optical math unit tests (analytic ground truth: thin-lens,
  FOV at 50mm full-frame, Airy disk at 550nm f/4, hyperfocal DOF)

## Patent crawler

```bash
# Dry run (no network — produces sample JSONL)
uv run python scripts/patent_crawler.py --dry-run --out data/sample.jsonl

# Real USPTO PatentsView search (no auth required)
uv run python scripts/patent_crawler.py --source uspto \
    --query "telephoto lens largan" --limit 20 \
    --out data/uspto-largan.jsonl

# Real Espacenet search (needs EPO_OPS_KEY/EPO_OPS_SECRET — see Owner Checklist)
uv run python scripts/patent_crawler.py --source espacenet \
    --query "imaging lens assembly" --limit 20 \
    --out data/espacenet.jsonl
```

Output JSONL feeds Phase 2's RAG ingestion pipeline.

## Docker

```bash
docker build -t lumira-atelier-backend .
docker run -p 8000:8000 --env-file .env lumira-atelier-backend
```

## LiteLLM gateway

See `litellm/` — Docker-Compose stack for the HK VPS, exposing a single
OpenAI-compatible endpoint that fans out to Anthropic / OpenAI / Google with
fallback. Config: `litellm/config.yaml`.

## Phase status

- **Phase 0** (this commit) — skeleton, deterministic optics, patent crawler,
  LiteLLM config template, Dockerfile + fly.toml
- **Phase 1** — Wizard 5-step LLM orchestration (Next.js side, Vercel AI SDK 5)
- **Phase 2** — Optiland/prysm/rayoptics integration + pgvector RAG retrieval
- **Phase 3** — R3F 3D visualization (frontend)
- **Phase 4** — Seedance 2.0 Pro + GPT-Image-2 media generation
- **Phase 5** — PDF report + launch
