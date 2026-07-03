# Coding Conventions

**Analysis Date:** 2026-07-03

## Naming Patterns

**Files:**
- Module files use snake_case: `optical_engine.py`, `parameter_guards.py`, `llm_relay.py`
- Test files use `test_*.py` pattern: `test_optical_engine.py`, `test_parameter_guards.py`
- API route files grouped in `app/api/`: `optical.py`, `rag.py`, `wizard.py`
- Core domain logic in `app/core/`: `optical_calc.py`, `lens_system.py`, `aberration.py`

**Functions and Methods:**
- Use snake_case exclusively: `build_optic_for_scenario()`, `compute_paraxial_summary()`, `extract_surface_descriptors()`, `validate_scenario_params()`
- Private functions prefixed with underscore: `_robust_clip_spot_data()`, `_validate_or_400()`, `_strip_markdown_fences()`, `_load_probe_optic()`
- Async functions follow same snake_case: `async def health()`, no special prefix

**Variables:**
- Use snake_case: `scenario`, `target_efl_mm`, `target_f_number`, `entrance_pupil_diameter_mm`
- Unit-qualified names in parameters/fields: `focal_length_mm`, `f_number`, `field_of_view_deg`, `image_height_mm`, `wavelength_nm`, `total_track_mm`, `airy_disc_diameter_um`, `rms_spot_radius_um`
- Suffixes convey units: `_mm` (millimeters), `_deg` (degrees), `_nm` (nanometers), `_um` (microns), `_lp_per_mm` (line pairs per mm)
- Boolean predicates: `is_stop`, `is_image`, `is_object`, `is_available`

**Types and Classes:**
- PascalCase for class names: `Scenario`, `SurfaceType`, `LensSurface`, `LensElement`, `LensAssembly`, `RayTraceResult`, `RayPath`, `ParaxialSummary`, `SurfaceDescriptor`, `MTFResult`, `MTFFieldData`, `OpticalSpecRequest`, `SuggestResponse`
- Enum values use UPPER_SNAKE_CASE for enums backed by StrEnum (values are lowercase kebab-case): 
  - Example: `Scenario.SMARTPHONE_TELEPHOTO = "smartphone-telephoto"`
  - Example: `SurfaceType.SPHERICAL = "spherical"`
- Dataclass names: `ThinLensSpec`, `ScenarioBounds`, `Settings`

## Code Style

**Formatting:**
- Line length: 100 characters (configured in `pyproject.toml`)
- Indentation: 4 spaces (Python standard)
- Tool: `ruff` (configured in `pyproject.toml`)

**Linting:**
- Ruff rules enabled: `["E", "F", "W", "I", "UP", "B", "C4", "SIM"]`
  - `E`: PEP 8 errors
  - `F`: PyFlakes (undefined names, unused imports)
  - `W`: PyFlakes warnings
  - `I`: isort (import sorting)
  - `UP`: pyupgrade (Python syntax modernization)
  - `B`: flake8-bugbear (common bugs and design problems)
  - `C4`: flake8-comprehensions (list/dict/set comprehension simplification)
  - `SIM`: flake8-simplify (code simplification)
- Line length ignored (`E501`): Allows docstrings and long strings to exceed 100 chars

**Type Hints:**
- Type hints used throughout: `def build_optic_for_scenario(scenario: Scenario, target_efl_mm: float, target_f_number: float | None = None) -> Optic:`
- Union types use `|` syntax (Python 3.10+): `float | None`, `str | None`, `Literal["full", "lightweight", "none"]`
- Import future annotations for forward references: `from __future__ import annotations` (seen in most core modules)
- Generic types: `list[float]`, `dict[Scenario, ScenarioBounds]`, `tuple[float, float]`

## Import Organization

**Order:**
1. Future imports: `from __future__ import annotations`
2. Built-in standard library: `import os`, `import logging`, `from pathlib import Path`, `import math`, `from contextlib import asynccontextmanager`, `from collections.abc import AsyncIterator`
3. Third-party external: `import numpy as np`, `import structlog`, `from fastapi import FastAPI`, `from pydantic import BaseModel`, `from optiland.optic import Optic`
4. Local/relative imports: `from app.core.config import settings`, `from app.core.lens_system import Scenario`, `from tests.data.zmx_manifest import ZMX_AMMO`

**Path Aliases:**
- No path aliases configured; all imports use absolute paths from package root
- FastAPI routers import from `app.api` and `app.core` explicitly

**Special Import Handling:**
- Optiland deprecation warnings suppressed on import:
  ```python
  with warnings.catch_warnings():
      warnings.simplefilter("ignore", DeprecationWarning)
      from optiland.optic import Optic
  ```
  Seen in `app/core/optical_engine.py`, `app/core/aberration.py`, and other optical modules
- Conditional imports for mocking: LLM relay calls use mock in test mode (see `app/core/llm_relay.py`)
- Script-local path resolution: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` in `scripts/export_acceptance_tasks.py`

## Error Handling

**Patterns:**
- **Validation errors early**: Raise `ValueError` for invalid inputs before any computation
  - Example: `if focal_length_mm <= 0: raise ValueError("focal_length must be positive")`
  - Example in `app/core/optical_calc.py`: All functions begin with input validation
- **Domain-specific exceptions**: `ParameterGuardError` raised by `validate_scenario_params()` with `violations` list
  - Example: `raise ParameterGuardError(scenario, violations)` carries multiple violations
- **HTTP exceptions from FastAPI**: Use `HTTPException` with status codes and detailed error dicts
  - Example: `HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"error": "parameter_guard_failed", "violations": [...]})`
- **Try-except for optional operations**: Wrapped attempts to set aperture or ray aiming in Optiland
  - Example in `app/core/optical_engine.py`: Logs warning on aperture failure instead of propagating
  ```python
  try:
      optic.set_aperture(aperture_type="EPD", value=target_epd)
  except Exception as exc:
      logger.warning("aperture_resize_skipped", extra={"reason": str(exc)})
  ```
- **Finite value guards**: Check `np.isfinite()` before serializing Optiland results
  - Example: Sentinel values for infinity (e.g., `-1e9` for object plane Z position)

## Logging

**Framework:** `structlog` with `logging` (structured logging, not print statements)

**Patterns:**
- Retrieved via `logger = structlog.get_logger(__name__)` at module level
- Fallback to `logging` in some modules: `logger = logging.getLogger(__name__)`
- Structured logging with keyword arguments: `logger.warning("aperture_resize_skipped", extra={...})`
- Entry/exit logging in lifespan: `logger.info("lumira_backend_starting", env=settings.env, version="0.1.0")`
- No print() statements in production code; use logger for all messages

## Comments

**When to Comment:**
- Module-level docstrings on every `.py` file (except `__init__.py`)
- Section separators using `# ` repeated: `# ---------------------------------------------------------------------------` (79 chars)
- Inline comments for non-obvious logic or external dependencies
- Comments explain *why*, not *what* — code structure shows *what*
- Important caveats marked with `CRITICAL:` (seen in `app/core/optical_engine.py` and `app/api/optical.py`)

**Docstring Style:**
- Triple-quote docstrings (not Google/NumPy style strictly, but descriptive)
- Function docstrings describe parameters and return value:
  ```python
  def build_optic_for_scenario(scenario: Scenario, target_efl_mm: float, target_f_number: float | None = None) -> Optic:
      """Construct + scale an Optiland Optic for the given scenario.
      
      EFL is set exactly via `updater.scale_system`. F-number is best-effort —
      if `optic.set_aperture` works for the design, we resize the entrance pupil;
      otherwise we accept the natural F# induced by the scale.
      
      Raises ValueError on unknown scenario.
      """
  ```
- Method and class docstrings less detailed; focus on contract
- No automated docstring parsing (Sphinx-style RST not used)

## Function Design

**Size:** 
- Typical functions 15-50 lines; some core algorithms like `_robust_clip_spot_data()` ~100 lines
- No strict limit; keep to single responsibility

**Parameters:**
- Use keyword-only arguments for clarity when multiple parameters of same type exist:
  - Example: `def _resolve_optional_float_window(*, target: float | None, half_width: float, floor: float, explicit_lo: float | None, explicit_hi: float | None, label: str)`
- Type hints on every parameter
- Optional parameters use `| None` or `Literal[...]` for enums

**Return Values:**
- Always typed: `-> Optic`, `-> ParaxialSummary`, `-> list[SurfaceDescriptor]`
- Multiple return values as tuple: `-> tuple[float, float]` (near_limit_mm, far_limit_mm)
- Raises documented in docstring: `Raises ValueError when...`

## Module Design

**Exports:**
- No `__all__` declarations; entire public scope is exported
- Private functions prefixed with `_` (convention, not enforced by Python)
- Classes and type hints exported as-is for use in other modules

**Barrel Files:**
- `app/api/__init__.py` is minimal (just package marker)
- `app/core/__init__.py` is minimal (just package marker)
- Imports explicit: `from app.core.optical_engine import ...`

**Pydantic Models:**
- All request/response payloads derive from `BaseModel` or `BaseSettings`
- Field validators use `@field_validator(mode="before")` for preprocessing (e.g., CSV splitting in `app/core/config.py`)
- Model validators use `@model_validator(mode="after")` for cross-field validation (e.g., adjacent surface indices in `LensElement`)

---

*Convention analysis: 2026-07-03*
