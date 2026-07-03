<!-- refreshed: 2026-07-03 -->
# Architecture

**Analysis Date:** 2026-07-03

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (this repo)                       │
│                     app/main.py                                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                  API Layer (app/api/)                            │ │
│  │  ┌──────────────┬──────────────┬──────────────────────────────┐ │ │
│  │  │  /optical    │  /wizard     │  /rag                        │ │ │
│  │  │  (raytrace,  │  (LLM-backed │  (patent search mock)        │ │ │
│  │  │   aberration,│   scenario   │                              │ │ │
│  │  │   layout-svg,│   extraction)│                              │ │ │
│  │  │   matching)  │              │                              │ │ │
│  │  └──────────────┴──────────────┴──────────────────────────────┘ │ │
│  └──────────────────────────┬───────────────────────────────────────┘ │
│                             │                                         │
│  ┌──────────────────────────▼───────────────────────────────────────┐ │
│  │                    Core Layer (app/core/)                         │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │  Optical Computation                                       │  │ │
│  │  │  ├── optical_calc.py (thin-lens, paraxial, diffraction)   │  │ │
│  │  │  ├── optical_engine.py (Optiland orchestration)           │  │ │
│  │  │  ├── optiland_patches.py (Optiland 0.6 bug fixes)         │  │ │
│  │  │  ├── zmx_ingest.py (Zemax loader + normalization)         │  │ │
│  │  │  ├── aberration.py (MTF/PSF/Zernike wrappers)             │  │ │
│  │  │  └── mtf_fields.py (field fraction definitions)           │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │  Design & Case Management                                 │  │ │
│  │  │  ├── case_library.py (real 39-case library loader)        │  │ │
│  │  │  ├── optical_sample.py (composite payload + metadata)     │  │ │
│  │  │  ├── lens_system.py (Pydantic schema: Scenario/Assembly)  │  │ │
│  │  │  └── local_optimizer.py (merit/field/yield scoring)       │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │  Rendering & Analysis                                      │  │ │
│  │  │  ├── layout_svg.py (Optiland → SVG layout)                │  │ │
│  │  │  ├── image_quality_floor.py (RMS/MTF acceptance gates)    │  │ │
│  │  │  └── parameter_guards.py (scenario bounds validation)     │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │  External Integrations                                     │  │ │
│  │  │  ├── llm_relay.py (OpenAI-compatible relay station)       │  │ │
│  │  │  ├── rag/store.py (patent search: mock → pgvector)        │  │ │
│  │  │  └── zmx_materials.py (glass datasheet index)             │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  │  ┌────────────────────────────────────────────────────────────┐  │ │
│  │  │  Config                                                    │  │ │
│  │  │  └── config.py (pydantic-settings, env parsing)           │  │ │
│  │  └────────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  Data Layer                                                     │  │
│  │  ├── app/data/optical_cases/ (39 case .json library)          │  │
│  │  └── data/zmx/ (39 Zemax source files)                         │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                        │
└─────────────┬──────────────────────────────────┬────────────────────┘
              │                                  │
              ▼                                  ▼
    ┌──────────────────┐           ┌──────────────────────┐
    │   Optiland 0.6   │           │ OpenAI-compatible    │
    │ (raytrace, MTF,  │           │ relay station        │
    │  PSF, SVG)       │           │ (Claude/GPT/Gemini)  │
    └──────────────────┘           └──────────────────────┘
              │
              ▼
   ┌──────────────────────────┐
   │ refractiveindex.info      │
   │ (glass material database) │
   └──────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| API Router (optical) | HTTP endpoints for raytrace, MTF, SVG, seed matching | `app/api/optical.py` |
| API Router (wizard) | LLM-driven scenario extraction + parameter clamping | `app/api/wizard.py` |
| API Router (rag) | Patent search interface (mock keyword → pgvector) | `app/api/rag.py` |
| Optical Engine | Optiland orchestration: build optic, trace, scale by EFL | `app/core/optical_engine.py` |
| Optical Calc | Deterministic thin-lens math (ground truth, unit-tested) | `app/core/optical_calc.py` |
| Case Library | Load 39 real designs from JSON, match user specs, score | `app/core/case_library.py` |
| Lens System | Pydantic schema for Scenario/LensAssembly/RayTraceResult | `app/core/lens_system.py` |
| Parameter Guards | Reject physically impossible specs (scenario bounds) | `app/core/parameter_guards.py` |
| ZMX Ingest | Load Zemax files, normalize for Optiland computation | `app/core/zmx_ingest.py` |
| Aberration | MTF/PSF/Zernike computation wrappers | `app/core/aberration.py` |
| Layout SVG | Render Optiland system as 2D visualization | `app/core/layout_svg.py` |
| LLM Relay | Single OpenAI client for all Claude/GPT/Gemini calls | `app/core/llm_relay.py` |
| RAG Store | Abstract interface + mock keyword-overlap patent search | `app/core/rag/store.py` |
| Config | Centralized settings via pydantic-settings (.env) | `app/core/config.py` |

## Pattern Overview

**Overall:** Layered API → Core → Data, with strong type contracts via Pydantic.

**Key Characteristics:**
- **Type-safe schema-driven design** — All data in/out is Pydantic BaseModel with strict validation; LLM never touches numeric computation directly
- **Deterministic ground truth** — Optical calculations live in `optical_calc.py` with analytic formulas and unit tests; Optiland integration is orchestrated, not trusted
- **Parameter guards at boundary** — Every external numeric input (LLM, user, API) hits `parameter_guards.validate_scenario_params()` before reaching optical engine
- **Real-case library-driven routing** — 39 real designs in `app/data/optical_cases/index.json` provide evidence-based seed selection; patent crawler feeds the RAG store
- **Single LLM client** — All Claude/GPT/Gemini calls fan through `llm_relay.py`; one relay station (owner-provided, OpenAI-compatible)
- **Mock-pluggable architecture** — RAG store is abstract; keyword mock v1 swaps to pgvector+BGE-M3 when embedding channel comes online

## Layers

**HTTP Entry Point:**
- Purpose: REST API surface, CORS, lifespan management
- Location: `app/main.py`
- Contains: FastAPI app definition, middleware setup, route inclusion
- Depends on: fastapi, pydantic, structlog
- Used by: Next.js frontend (Cloudflare Workers)

**API Layer:**
- Purpose: Request validation, response serialization, HTTP exception handling
- Location: `app/api/` (optical.py, wizard.py, rag.py)
- Contains: Route handlers, request/response schemas, helpers (parameter window resolution, seed preflight)
- Depends on: Core layer, Pydantic models
- Used by: HTTP clients

**Core Layer:**
- Purpose: Business logic, optical computation, data access
- Location: `app/core/`
- Contains: Optiland orchestration, thin-lens math, case matching, LLM integration, rendering
- Depends on: numpy, scipy, optiland, openai, pydantic
- Used by: API layer

**Data Layer:**
- Purpose: Static assets (case library, ZMX files)
- Location: `app/data/optical_cases/` (JSON), `data/zmx/` (Zemax)
- Contains: 39 real optical designs + metadata, 39 source ZMX files
- Depends on: File system
- Used by: Case library loader

## Data Flow

### Primary Request Path (Wizard → Raytrace)

1. Frontend sends free-text user input → `POST /api/wizard/extract-scenario` (`app/api/wizard.py::extract_scenario`)
2. LLM (Claude Opus 4.7 via relay) parses intent → returns JSON (scenario, focal_length, f_number, etc.)
3. `_strip_markdown_fences()` removes markdown wrapping; `parse_response()` validates schema
4. `parameter_guards.validate_scenario_params()` clamps numerics to scenario bounds (e.g., if LLM proposes EFL=0.5mm for smartphone-telephoto, raise to 5mm)
5. Response object (`ExtractScenarioResponse`) delivered to frontend
6. Frontend shows scenario + parameter sliders (from `GET /api/optical/suggest/{scenario}`)
7. User adjusts, submits → `POST /api/optical/raytrace` (OpticalSpecRequest)
8. `app/api/optical.py::raytrace()` validates again via `_validate_or_400()`
9. Calls `optical_engine.raytrace_from_spec()`:
   - `build_optic_for_scenario()` loads reference (Telephoto/CookeTriplet/WideAngle100/DoubleGauss)
   - Scales to target EFL via `optic.updater.scale_system()`
   - Resizes aperture for target f-number
   - `trace_optic()` runs ray trace, collects surfaces + chief/marginal rays
   - `compute_paraxial_summary()` extracts EFL, f-number, EPD, entrance-pupil location
10. Returns `RayTraceResult` (paraxial summary + surfaces + ray paths)
11. Frontend renders 2D layout

### Secondary: Case Matching (Seed Selection)

1. Frontend sends target specs → `POST /api/optical/match` (OpticalSpecRequest, with `analysis_depth: 'seed_only'`)
2. `app/api/optical.py::match()` calls `case_library.load_case_library()` (cached `@lru_cache`)
   - Loads `app/data/optical_cases/index.json` (39 cases)
   - Each case: paraxial, surfaces, trace, MTF, metadata
3. `case_library.match_case()` scores each candidate:
   - EFL distance, f-number distance, FOV distance, image-height distance
   - Normalized, weighted, combined into one "match distance" score
   - Returns top-K sorted by score (best_match, cost_variant, performance_variant, etc.)
4. `case_library.build_sample_from_optic()` adds real-design details:
   - MTF via `aberration.compute_mtf()`
   - SVG layout via `layout_svg.render_layout_svg()`
   - Metadata: piece count, materials, EFL error, field fallback (honest)
5. Returns `OpticalSampleData` composite (paraxial + surfaces + trace + MTF + metadata)

### Tertiary: Patent Search (RAG)

1. Frontend sends query + scenario → `POST /api/rag/lens-patents` (LensPatentQuery)
2. `app/api/rag.py::lens_patents()` calls `get_default_store()` (returns MockLensPatentStore v1)
3. `store.search(query, scenario, top_k)`:
   - Filters corpus to scenario (e.g., only smartphone-wide patents)
   - Tokenizes query + each patent title/abstract/claim
   - Computes Jaccard overlap (keyword intersection)
   - Sorts, returns top_k hits
4. When pgvector+BGE-M3 comes online: store swaps to `PgVectorLensPatentStore` (no API changes)

### State Management

- **Stateless HTTP** — Each request is independent; no session state
- **Cached library** — Case library loaded once on first access (LRU cache), stays in memory
- **Immutable models** — Pydantic models are frozen (if defined as such); no mutable shared state
- **Configuration singleton** — `settings` in `config.py` is LRU-cached; single source of env truth

## Key Abstractions

**Scenario (StrEnum):**
- Purpose: First-class enum for use case (smartphone-telephoto, smartphone-wide, AR, DSLR, microscope)
- Examples: `app/core/lens_system.py::Scenario`
- Pattern: Used throughout to key bounds, reference designs, matching weights

**LensAssembly (Pydantic BaseModel):**
- Purpose: Full optical prescription — the contract between LLM output and Optical Engine input
- Examples: Produced by Wizard LLM, consumed by `raytrace_from_spec()`, serialized as JSON
- Pattern: Strongly typed, immutable in practice (JSON roundtrip); enforces surface index contiguity

**OpticalSampleData (Pydantic BaseModel composite):**
- Purpose: Full design payload for one real or simulated case
- Examples: `app/core/optical_sample.py`; contains `ParaxialSummary`, surfaces, `RayTraceResult`, `MTFResult`, `LayoutSVG`, `CaseMetadata`
- Pattern: Frontend contract; replaces individual endpoint calls with one unified response

**Optic (optiland.optic.Optic):**
- Purpose: Runtime representation of an optical system (Optiland library)
- Examples: Built by `optical_engine.build_optic_for_scenario()`, used for raytrace/MTF
- Pattern: External library; encapsulated by `optical_engine.py` to hide Optiland version complexity

**ParameterGuardError (exception):**
- Purpose: Capture why a spec violates scenario bounds (which fields, by how much)
- Examples: `parameter_guards.py`; caught in `_validate_or_400()` and converted to HTTP 400
- Pattern: Structured error response with violations list (not a string)

## Entry Points

**`app/main.py::app` (FastAPI instance):**
- Location: `app/main.py` (lines 30-50)
- Triggers: Uvicorn startup (local: `uv run uvicorn app.main:app --reload`; prod: fly.io, docker)
- Responsibilities: CORS setup, route registration, lifespan hooks, health check

**`app/api/optical.py::router` (APIRouter):**
- Location: `app/api/optical.py` (lines 39+)
- Triggers: HTTP POST/GET to `/api/optical/*`
- Responsibilities: Parameter validation, seed matching, raytrace orchestration

**`app/api/wizard.py::router` (APIRouter):**
- Location: `app/api/wizard.py` (lines 27+)
- Triggers: HTTP POST to `/api/wizard/*`
- Responsibilities: LLM-driven scenario extraction, JSON parsing, clamping

**`app/api/rag.py::router` (APIRouter):**
- Location: `app/api/rag.py` (lines 17+)
- Triggers: HTTP POST to `/api/rag/*`
- Responsibilities: Patent search dispatch to pluggable store

**`scripts/patent_crawler.py` (CLI):**
- Location: `scripts/patent_crawler.py`
- Triggers: Manual `uv run python scripts/patent_crawler.py --source uspto --query "..."` 
- Responsibilities: USPTO/Espacenet crawl, output JSONL for RAG ingest

**`scripts/export_acceptance_tasks.py` (CLI):**
- Location: `scripts/export_acceptance_tasks.py`
- Triggers: Manual `uv run python scripts/export_acceptance_tasks.py --json`
- Responsibilities: Generate work packets for design-agent acceptance testing

## Architectural Constraints

- **Threading:** Single-threaded event loop (async/await only); no manual thread pools
- **Global state:** Configuration singleton (`settings` in `config.py`); case library LRU cache. No mutable module-level state otherwise.
- **Circular imports:** None detected; imports are acyclic (main → api → core → data)
- **Determinism:** Optical math is deterministic (no random initialization); Optiland sometimes produces NaN on edge cases (caught by `optical_sample.py` with fallback field sets)
- **LLM non-determinism:** LLM (Claude/GPT) can vary output; parameter guards catch nonsense but don't guarantee physical plausibility (e.g., a valid EFL that's still suboptimal)
- **Optiland patching:** 0.6 has bugs (xasphere reader, glass material resolution, angle/NaN field handling); patches in `optiland_patches.py` are applied first, before any other Optiland import

## Anti-Patterns

### LLM-Trusted Numerics

**What happens:** If LLM output bypasses `parameter_guards.validate_scenario_params()`, physically impossible specs reach Optiland (e.g., EFL=0.01mm for smartphone telephoto).
**Why it's wrong:** Optiland may crash, return NaN, or accept garbage → frontend shows nonsense. User loses trust.
**Do this instead:** All external numerics (LLM, user, API) must pass `_validate_or_400()` in `app/api/optical.py` before reaching optical engine.

### Unstructured Error Responses

**What happens:** Route handlers catch exceptions and return raw Python tracebacks or generic 500 errors.
**Why it's wrong:** Frontend can't programmatically distinguish parameter violation from engine failure; users see "Internal Server Error" instead of "EFL too high for this scenario".
**Do this instead:** Catch expected failures (ParameterGuardError, Optiland exceptions) and return structured HTTP 400/422 with error code + violation list, as in `_validate_or_400()` and `raytrace()`.

### Optiland Without Patches

**What happens:** Any new Optiland import in a file that doesn't import `optiland_patches` first will see buggy behavior (xasphere fails, glass index is wrong, angle fields hit NaN).
**Why it's wrong:** Real ZMX files are unreadable; MTF computation hangs or crashes.
**Do this instead:** Always import `app.core.optiland_patches` and call `apply_all()` before importing Optiland, as in `app/main.py` line 12–14 and `zmx_ingest.py`.

### Mutable Shared State in Case Library

**What happens:** If `case_library.py` cached a mutable dict and the cache was modified in-place, subsequent requests would see corrupted state.
**Why it's wrong:** Race conditions, non-determinism, debugging nightmare.
**Do this instead:** Case library returns Pydantic models (immutable by default); caching is read-only via `@lru_cache`.

---

*Architecture analysis: 2026-07-03*
