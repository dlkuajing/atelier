# Lumira Atelier · Backend

> **Standalone repo since 2026-07-03.** Extracted from `dlkuajing/lumira`
> (`lumira-backend/` subtree, full history preserved). Production still
> deploys from the lumira repo; this repo is the R&D mainline.
> Note: `pyproject.toml` now publishes this local project as `atelier`;
> `lumira-backend/` remains the historical subtree name.

Python FastAPI backend for the Lumira Atelier Optical Co-Pilot. Owns the heavy
work that can't (or shouldn't) run on Cloudflare Workers:

- **Deterministic optical calculations** — `app/core/optical_calc.py` (thin
  lens, paraxial, Airy disc, depth of field, Snell, paraxial ABCD matrices) —
  ground-truth math the LLM is forbidden to estimate.
- **Optiland integration** — `app/core/optical_engine.py`, `app/core/aberration.py`,
  `app/core/layout_svg.py`. Optiland 0.6+ covers ray tracing, MTF / PSF /
  Zernike, and SVG layout natively — prysm was dropped in favour of
  Optiland's built-ins.
- **rayoptics 0.9** — alternative SVG renderer hook (currently unused).
- **pgvector + BGE-M3 + SigLIP-2 RAG** — `app/core/rag/` (v1 ships the
  keyword-overlap mock; pgvector swap is a one-class change).
- **Patent crawler** — `scripts/patent_crawler.py` (USPTO + Espacenet OPS,
  with `--dry-run`).
- **LLM / image relay** — all chat + image traffic exits via a single
  OpenAI-compatible relay station (see `app/core/llm_relay.py`). LiteLLM
  self-host was dropped in favour of the owner-provided relay.

## Architecture role

```
┌───────────────┐  HTTPS+SSE  ┌─────────────────┐  HTTPS  ┌──────────────┐
│ Next.js (CF)  │ ──────────▶ │ FastAPI backend │ ──────▶ │ Optiland     │
│ Wizard UI     │             │ (this repo)     │         │ pgvector     │
└───────────────┘             └─────────────────┘         └──────────────┘
       │                              │
       ▼                              ▼
┌──────────────────────┐        ┌─────────────────┐
│ OpenAI-compatible    │        │ refractiveindex │
│ relay (Claude / GPT /│        │ .info (CC0)     │
│ Gemini / gpt-image-2)│        └─────────────────┘
└──────────────────────┘
```

## Local development

```bash
cd lumira-backend
uv sync                       # core deps
uv sync --group optical       # Optiland + rayoptics (slow first sync — needs BLAS)
cp .env.example .env          # fill in OPENAI_BASE_URL + OPENAI_API_KEY
                              # (see ../.planning/phases/00-skeleton-data-prep/OWNER-CHECKLIST.md)
uv run uvicorn app.main:app --reload
```

OpenAPI explorer: http://localhost:8000/docs

## Tests

```bash
uv run pytest -v
```

131 tests cover health, deterministic optical math (analytic ground truth
on thin-lens, FOV, Airy disc, Snell, DOF, ABCD matrices), Optiland
integration, parameter guards, RAG keyword mock, the LLM scenario-extraction
parser, and FastAPI endpoint contracts.

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

## LLM / image relay

All chat (Claude Opus 4.7, GPT-5.5, Gemini 3.1 Pro Preview) and image
(gpt-image-2) calls go through the owner-provided relay at
`OPENAI_BASE_URL`. The relay is OpenAI-compatible — the OpenAI SDK is the
only client we use. Routing + fallback ladder lives in
`app/core/llm_relay.py::PRIMARY_CHAT / FALLBACK_CHAT / PRIMARY_IMAGE`.

## Phase status

- **Phase 0** — skeleton, deterministic optics, patent crawler
- **Phase 2** — Optiland (raytrace + MTF + SVG) + RAG keyword mock
- **Phase 1** — Wizard LLM extraction + cover-image + executive-summary
- **Phase 4** — gpt-image-2 cover banner
- **Phase 5** — react-pdf bilingual report (en + zh)
- **Owner remaining** — pgvector live store, Python backend deploy, DNS
