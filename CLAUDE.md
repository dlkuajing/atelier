@AGENTS.md

<!-- GSD:project-start source:PROJECT.md -->

## Project

**Atelier — 光学设计 Agent 独立演示产品**

Atelier 是一个可独立部署的产品级**手机镜头**光学设计 Agent 软件：客户在浏览器界面里用自然语言输入需求，系统实时给出设计（光路图 / MTF / 专家级评估报告），并展示由 Code V 深度优化产出的专业级设计成果。设计能力植根于规模化的手机镜头专利底库（目标 ≥500 颗可路由 seed）——底库规模是说服力的基础。目标用户是镜头/模组厂的工程团队与决策者，用于现场客户演示。它从 lumira 官网后端剥离而来，现在是独立产品线，与官网可不互通。

**Core Value:** 资深光学设计师看了演示产出不能觉得"比不过"——专家级可信度是唯一不可失守的东西；观感和流畅度服务于它，不能替代它。

### Constraints

- **平台**: 演示机为 Windows（Code V Windows-only），后端本地跑，浏览器访问 localhost
- **Tech stack**: Python 只用 uv；Code V 集成走宏批处理（.seq 生成 → 批跑 → 解析），不走交互式 API
- **性能**: 在线交互路径（追迹/MTF/SVG/路由）必须保持亚秒级；Code V 深度计算只在离线/后台层
- **降级能力**: 无 Code V 环境（CI、其他开发机）全链路可降级纯 Optiland 跑通测试
- **数据锚**: 全部资产以 ZMX 格式为锚，Code V 产物必须回到 ZMX 走现有 ingest 流水线
- **依赖**: Code V 安装由主公负责；集成开发在安装完成后才能实测（前置可先做接口设计与 mock）

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python 3.12 - Full backend implementation, optical calculations, ray tracing, LLM integration

## Runtime

- Python 3.12 (specified in `.python-version`)
- uv (Astral's fast Python package manager)
- Lockfile: `uv.lock` (frozen, pinned dependencies)

## Frameworks

- FastAPI 0.115.0+ - HTTP API server, CORS, routing
- Uvicorn 0.32.0+ - ASGI application server (2 workers on Fly.io shared-cpu-2x)
- Pydantic 2.9.0+ - Data validation, request/response schemas
- Pydantic-settings 2.5.0+ - Environment-based configuration management
- pytest 8.3.0+ - Test runner
- pytest-asyncio 0.24.0+ - Async test support
- Coverage target: 131 tests across health, optical math, Optiland integration, parameter guards, RAG, LLM parsing, FastAPI contracts
- ruff 0.7.0+ - Fast Python linter (rules: E, F, W, I, UP, B, C4, SIM; line-length 100)
- mypy 1.13.0+ - Static type checking
- Docker multi-stage build (optimized for optical dependencies)

## Key Dependencies

- numpy 2.0.0+ - Numerical computing, matrix operations for optical calculations
- scipy 1.14.0+ - Scientific computation (Snell's law, matrix operations)
- openai 1.50.0+ - OpenAI-compatible relay client (Claude, GPT, Gemini models)
- anthropic 0.40.0+ - Anthropic SDK (not currently active; kept for potential future use)
- httpx 0.27.0+ - Async HTTP client (used by Pydantic)
- python-multipart 0.0.10 - Multipart form/file upload support
- optiland 0.6.0+ - Ray tracing, MTF/PSF, Zernike polynomials, aberration analysis
- rayoptics 0.9.5 - Alternative optical engine, SVG renderer hook (currently unused)
- opticalglass 1.1.0+ - Lens material refractive index data (CC0 refractiveindex.info)
- structlog 24.4.0+ - Structured logging with JSON output
- psycopg[binary] 3.2.0+ - PostgreSQL async driver
- pgvector 0.3.0+ - PostgreSQL vector extension client for RAG embeddings

## Configuration

- `.env` file (gitignored, contains secrets)
- Case-insensitive environment variable loading via `app/core/config.py`
- Required vars: `OPENAI_API_KEY`, `OPENAI_BASE_URL`
- Optional: `DATABASE_URL`, `EPO_OPS_KEY`, `EPO_OPS_SECRET`, `CF_ACCOUNT_ID`, `CF_AI_GATEWAY_URL`, `CF_AI_GATEWAY_TOKEN`, `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
- Production baked-in: `ENV=production`, `LOG_LEVEL=INFO`, `CORS_ALLOWED_ORIGINS=https://lumirahq.com,...`
- `Dockerfile` - Multi-stage (base, deps, final)
- `fly.toml` - Fly.io deployment config (Singapore region, 2 vCPU shared, 2GB RAM, uvicorn 2 workers)
- `pyproject.toml` - Project metadata, dependency groups (core, dev, optical)

## Platform Requirements

- Python 3.12
- uv package manager
- BLAS/LAPACK libraries for numpy/scipy (Debian: `libopenblas-dev liblapack-dev`)
- libffi-dev, libssl-dev for binary packages
- Windows: `PYTHONUTF8=1` environment variable required for UTF-8 test data (Chinese characters)
- Docker container on Fly.io (shared-cpu-2x, 2GB RAM, Singapore region)
- OpenAI-compatible relay endpoint (`api.openbili.com/v1` default, configurable)
- Optional: PostgreSQL 14+ with pgvector extension (Wave 2)
- Health check endpoint: `GET /health` (container readiness)
- Cold start: ~100s (12s uv bytecode compile + 8s uvicorn boot + Optiland/scipy/numpy imports)
- Keep 1 machine always running to avoid cold-start 503 errors
- LLM relay round-trip (~200-400ms) is the primary bottleneck, not CPU math
- Optiland peak memory: ~1.2GB during raytrace; 2GB headroom for concurrent requests

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- Module files use snake_case: `optical_engine.py`, `parameter_guards.py`, `llm_relay.py`
- Test files use `test_*.py` pattern: `test_optical_engine.py`, `test_parameter_guards.py`
- API route files grouped in `app/api/`: `optical.py`, `rag.py`, `wizard.py`
- Core domain logic in `app/core/`: `optical_calc.py`, `lens_system.py`, `aberration.py`
- Use snake_case exclusively: `build_optic_for_scenario()`, `compute_paraxial_summary()`, `extract_surface_descriptors()`, `validate_scenario_params()`
- Private functions prefixed with underscore: `_robust_clip_spot_data()`, `_validate_or_400()`, `_strip_markdown_fences()`, `_load_probe_optic()`
- Async functions follow same snake_case: `async def health()`, no special prefix
- Use snake_case: `scenario`, `target_efl_mm`, `target_f_number`, `entrance_pupil_diameter_mm`
- Unit-qualified names in parameters/fields: `focal_length_mm`, `f_number`, `field_of_view_deg`, `image_height_mm`, `wavelength_nm`, `total_track_mm`, `airy_disc_diameter_um`, `rms_spot_radius_um`
- Suffixes convey units: `_mm` (millimeters), `_deg` (degrees), `_nm` (nanometers), `_um` (microns), `_lp_per_mm` (line pairs per mm)
- Boolean predicates: `is_stop`, `is_image`, `is_object`, `is_available`
- PascalCase for class names: `Scenario`, `SurfaceType`, `LensSurface`, `LensElement`, `LensAssembly`, `RayTraceResult`, `RayPath`, `ParaxialSummary`, `SurfaceDescriptor`, `MTFResult`, `MTFFieldData`, `OpticalSpecRequest`, `SuggestResponse`
- Enum values use UPPER_SNAKE_CASE for enums backed by StrEnum (values are lowercase kebab-case): 
- Dataclass names: `ThinLensSpec`, `ScenarioBounds`, `Settings`

## Code Style

- Line length: 100 characters (configured in `pyproject.toml`)
- Indentation: 4 spaces (Python standard)
- Tool: `ruff` (configured in `pyproject.toml`)
- Ruff rules enabled: `["E", "F", "W", "I", "UP", "B", "C4", "SIM"]`
- Line length ignored (`E501`): Allows docstrings and long strings to exceed 100 chars
- Type hints used throughout: `def build_optic_for_scenario(scenario: Scenario, target_efl_mm: float, target_f_number: float | None = None) -> Optic:`
- Union types use `|` syntax (Python 3.10+): `float | None`, `str | None`, `Literal["full", "lightweight", "none"]`
- Import future annotations for forward references: `from __future__ import annotations` (seen in most core modules)
- Generic types: `list[float]`, `dict[Scenario, ScenarioBounds]`, `tuple[float, float]`

## Import Organization

- No path aliases configured; all imports use absolute paths from package root
- FastAPI routers import from `app.api` and `app.core` explicitly
- Optiland deprecation warnings suppressed on import:
- Conditional imports for mocking: LLM relay calls use mock in test mode (see `app/core/llm_relay.py`)
- Script-local path resolution: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` in `scripts/export_acceptance_tasks.py`

## Error Handling

- **Validation errors early**: Raise `ValueError` for invalid inputs before any computation
- **Domain-specific exceptions**: `ParameterGuardError` raised by `validate_scenario_params()` with `violations` list
- **HTTP exceptions from FastAPI**: Use `HTTPException` with status codes and detailed error dicts
- **Try-except for optional operations**: Wrapped attempts to set aperture or ray aiming in Optiland
- **Finite value guards**: Check `np.isfinite()` before serializing Optiland results

## Logging

- Retrieved via `logger = structlog.get_logger(__name__)` at module level
- Fallback to `logging` in some modules: `logger = logging.getLogger(__name__)`
- Structured logging with keyword arguments: `logger.warning("aperture_resize_skipped", extra={...})`
- Entry/exit logging in lifespan: `logger.info("lumira_backend_starting", env=settings.env, version="0.1.0")`
- No print() statements in production code; use logger for all messages

## Comments

- Module-level docstrings on every `.py` file (except `__init__.py`)
- Section separators using `# ` repeated: `# ---------------------------------------------------------------------------` (79 chars)
- Inline comments for non-obvious logic or external dependencies
- Comments explain *why*, not *what* — code structure shows *what*
- Important caveats marked with `CRITICAL:` (seen in `app/core/optical_engine.py` and `app/api/optical.py`)
- Triple-quote docstrings (not Google/NumPy style strictly, but descriptive)
- Function docstrings describe parameters and return value:
- Method and class docstrings less detailed; focus on contract
- No automated docstring parsing (Sphinx-style RST not used)

## Function Design

- Typical functions 15-50 lines; some core algorithms like `_robust_clip_spot_data()` ~100 lines
- No strict limit; keep to single responsibility
- Use keyword-only arguments for clarity when multiple parameters of same type exist:
- Type hints on every parameter
- Optional parameters use `| None` or `Literal[...]` for enums
- Always typed: `-> Optic`, `-> ParaxialSummary`, `-> list[SurfaceDescriptor]`
- Multiple return values as tuple: `-> tuple[float, float]` (near_limit_mm, far_limit_mm)
- Raises documented in docstring: `Raises ValueError when...`

## Module Design

- No `__all__` declarations; entire public scope is exported
- Private functions prefixed with `_` (convention, not enforced by Python)
- Classes and type hints exported as-is for use in other modules
- `app/api/__init__.py` is minimal (just package marker)
- `app/core/__init__.py` is minimal (just package marker)
- Imports explicit: `from app.core.optical_engine import ...`
- All request/response payloads derive from `BaseModel` or `BaseSettings`
- Field validators use `@field_validator(mode="before")` for preprocessing (e.g., CSV splitting in `app/core/config.py`)
- Model validators use `@model_validator(mode="after")` for cross-field validation (e.g., adjacent surface indices in `LensElement`)

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```

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

- **Type-safe schema-driven design** — All data in/out is Pydantic BaseModel with strict validation; LLM never touches numeric computation directly
- **Deterministic ground truth** — Optical calculations live in `optical_calc.py` with analytic formulas and unit tests; Optiland integration is orchestrated, not trusted
- **Parameter guards at boundary** — Every external numeric input (LLM, user, API) hits `parameter_guards.validate_scenario_params()` before reaching optical engine
- **Real-case library-driven routing** — 39 real designs in `app/data/optical_cases/index.json` provide evidence-based seed selection; patent crawler feeds the RAG store
- **Single LLM client** — All Claude/GPT/Gemini calls fan through `llm_relay.py`; one relay station (owner-provided, OpenAI-compatible)
- **Mock-pluggable architecture** — RAG store is abstract; keyword mock v1 swaps to pgvector+BGE-M3 when embedding channel comes online

## Layers

- Purpose: REST API surface, CORS, lifespan management
- Location: `app/main.py`
- Contains: FastAPI app definition, middleware setup, route inclusion
- Depends on: fastapi, pydantic, structlog
- Used by: Next.js frontend (Cloudflare Workers)
- Purpose: Request validation, response serialization, HTTP exception handling
- Location: `app/api/` (optical.py, wizard.py, rag.py)
- Contains: Route handlers, request/response schemas, helpers (parameter window resolution, seed preflight)
- Depends on: Core layer, Pydantic models
- Used by: HTTP clients
- Purpose: Business logic, optical computation, data access
- Location: `app/core/`
- Contains: Optiland orchestration, thin-lens math, case matching, LLM integration, rendering
- Depends on: numpy, scipy, optiland, openai, pydantic
- Used by: API layer
- Purpose: Static assets (case library, ZMX files)
- Location: `app/data/optical_cases/` (JSON), `data/zmx/` (Zemax)
- Contains: 39 real optical designs + metadata, 39 source ZMX files
- Depends on: File system
- Used by: Case library loader

## Data Flow

### Primary Request Path (Wizard → Raytrace)

### Secondary: Case Matching (Seed Selection)

### Tertiary: Patent Search (RAG)

### State Management

- **Stateless HTTP** — Each request is independent; no session state
- **Cached library** — Case library loaded once on first access (LRU cache), stays in memory
- **Immutable models** — Pydantic models are frozen (if defined as such); no mutable shared state
- **Configuration singleton** — `settings` in `config.py` is LRU-cached; single source of env truth

## Key Abstractions

- Purpose: First-class enum for use case (smartphone-telephoto, smartphone-wide, AR, DSLR, microscope)
- Examples: `app/core/lens_system.py::Scenario`
- Pattern: Used throughout to key bounds, reference designs, matching weights
- Purpose: Full optical prescription — the contract between LLM output and Optical Engine input
- Examples: Produced by Wizard LLM, consumed by `raytrace_from_spec()`, serialized as JSON
- Pattern: Strongly typed, immutable in practice (JSON roundtrip); enforces surface index contiguity
- Purpose: Full design payload for one real or simulated case
- Examples: `app/core/optical_sample.py`; contains `ParaxialSummary`, surfaces, `RayTraceResult`, `MTFResult`, `LayoutSVG`, `CaseMetadata`
- Pattern: Frontend contract; replaces individual endpoint calls with one unified response
- Purpose: Runtime representation of an optical system (Optiland library)
- Examples: Built by `optical_engine.build_optic_for_scenario()`, used for raytrace/MTF
- Pattern: External library; encapsulated by `optical_engine.py` to hide Optiland version complexity
- Purpose: Capture why a spec violates scenario bounds (which fields, by how much)
- Examples: `parameter_guards.py`; caught in `_validate_or_400()` and converted to HTTP 400
- Pattern: Structured error response with violations list (not a string)

## Entry Points

- Location: `app/main.py` (lines 30-50)
- Triggers: Uvicorn startup (local: `uv run uvicorn app.main:app --reload`; prod: fly.io, docker)
- Responsibilities: CORS setup, route registration, lifespan hooks, health check
- Location: `app/api/optical.py` (lines 39+)
- Triggers: HTTP POST/GET to `/api/optical/*`
- Responsibilities: Parameter validation, seed matching, raytrace orchestration
- Location: `app/api/wizard.py` (lines 27+)
- Triggers: HTTP POST to `/api/wizard/*`
- Responsibilities: LLM-driven scenario extraction, JSON parsing, clamping
- Location: `app/api/rag.py` (lines 17+)
- Triggers: HTTP POST to `/api/rag/*`
- Responsibilities: Patent search dispatch to pluggable store
- Location: `scripts/patent_crawler.py`
- Triggers: Manual `uv run python scripts/patent_crawler.py --source uspto --query "..."` 
- Responsibilities: USPTO/Espacenet crawl, output JSONL for RAG ingest
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

### Unstructured Error Responses

### Optiland Without Patches

### Mutable Shared State in Case Library

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
