# Testing Patterns

**Analysis Date:** 2026-07-03

## Test Framework

**Runner:**
- `pytest` ≥8.3.0
- Config: `pyproject.toml` `[tool.pytest.ini_options]`
  - `asyncio_mode = "auto"` (enables async test support via `pytest-asyncio`)
  - `testpaths = ["tests"]` (scans only `tests/` directory)

**Assertion Library:**
- Built-in `assert` statements (no separate library)
- `pytest.raises()` context manager for exception testing
- `math.isclose()` for floating-point comparison with tolerance

**Run Commands:**
```bash
# Install dev dependencies (includes pytest)
uv sync --frozen --group dev --group optical

# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_optical_engine.py

# Run specific test function
uv run pytest tests/test_optical_engine.py::test_build_smartphone_telephoto_hits_target_efl

# Watch mode (requires pytest-watch, not in deps)
uv run pytest --lf

# Coverage (if coverage plugin installed)
uv run pytest --cov=app --cov-report=html
```

**Environment:**
- **Windows-specific:** Must set `PYTHONUTF8=1` when running tests locally on Windows machines
  - Without this, JSON with UTF-8 characters fails parsing in test data (GBK codec mismatch)
  - CI runs on Ubuntu, so no issue in GitHub Actions
  - Example: `PYTHONUTF8=1 uv run pytest`

## Test File Organization

**Location:**
- Co-located in parallel tree: `tests/` directory mirrors `app/` structure
- `tests/test_optical_engine.py` tests `app/core/optical_engine.py`
- `tests/test_api_optical.py` tests `app/api/optical.py`
- `tests/data/` contains test data fixtures and manifests

**Naming:**
- Test files: `test_*.py`
- Test functions: `test_*` (descriptive name indicating what is tested)
- Test classes: Not used; all tests are module-level functions

**Structure:**
```
tests/
├── __init__.py
├── conftest.py              (if needed; currently no project-level fixtures)
├── data/
│   ├── __init__.py
│   └── zmx_manifest.py      (test data index: ZMX_AMMO dict)
├── test_aberration.py
├── test_api_optical.py
├── test_case_library.py
├── test_lens_system.py
├── test_llm_relay.py
├── test_optical_calc_extensions.py
├── test_optical_engine.py
├── test_parameter_guards.py
├── test_wizard.py
└── ...
```

## Test Structure

**Suite Organization:**
Each test file uses section headers (`# ` repeated) to group related tests:

```python
"""Tests for app.core.optical_engine — Optiland integration."""

import math
import pytest
from app.core.lens_system import Scenario
from app.core.optical_engine import build_optic_for_scenario, compute_paraxial_summary

# ---------------------------------------------------------------------------
# build_optic_for_scenario
# ---------------------------------------------------------------------------

def test_build_smartphone_telephoto_hits_target_efl():
    optic = build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO,
        target_efl_mm=7.0,
        target_f_number=2.4,
    )
    summary = compute_paraxial_summary(optic)
    assert math.isclose(summary.effective_focal_length_mm, 7.0, rel_tol=1e-3)

# ---------------------------------------------------------------------------
# Paraxial summary
# ---------------------------------------------------------------------------

def test_paraxial_summary_has_sane_values_smartphone_tele():
    ...
```

**Patterns:**

**Setup (AAA - Arrange, Act, Assert):**
```python
def test_raytrace_valid_input_returns_full_payload():
    """Good input → 200 + paraxial summary + surfaces + ray paths."""
    # Arrange
    r = client.post("/api/optical/raytrace", json=_good_request())
    
    # Act (POST already happened)
    
    # Assert
    assert r.status_code == 200, r.text
    data = r.json()
    assert "paraxial" in data and "surfaces" in data and "trace" in data
```

**Teardown:**
- Minimal; no explicit cleanup needed in most tests
- FastAPI `TestClient` handles request/response lifecycle
- Optiland objects garbage-collected automatically

**Assertion Patterns:**
- Direct assertions: `assert condition`
- Equality: `assert x == y`, `assert result.scenario == Scenario.SMARTPHONE_TELEPHOTO`
- Membership: `assert "telephoto" in data["description"].lower()`
- Ranges: `assert 5.0 <= lo < hi <= 18.0` (chained comparisons)
- Exceptions: `with pytest.raises(ValueError): func(bad_arg)`
- Floating-point: `math.isclose(value, expected, rel_tol=1e-3)` or `abs_tol=1e-9`
- Collections: `assert len(items) > 0`, `assert sum(1 for x in items if x.is_stop) == 1`

## Mocking

**Framework:** `unittest.mock` (built-in)

**Patterns:**
LLM calls are mocked or stubbed (not tested with live API):
- Example: `app/core/llm_relay.py` routes to a relay endpoint; tests use `model_for_role()` and `is_available()` invariants, not actual LLM calls
- Environment: CI uses placeholder API keys (`OPENAI_API_KEY=sk-test-...`); live calls would fail with invalid key
- Test: `test_llm_relay.py` checks role-to-model mapping and availability heuristics, not network

**What to Mock:**
- External API calls (OpenAI, Anthropic, EPO OPS)
- Network I/O (HTTP requests, database connections)
- Expensive computations (if needed for speed)

**What NOT to Mock:**
- Optiland optical calculations — tests run the real engine (wave 2 design decision)
- Pydantic validation — test real validation behavior
- Parameter guards — test actual bounds checking
- Database queries — use in-memory fixtures or temporary test data

## Fixtures and Factories

**Test Data:**
Shared fixtures defined at module level (no `conftest.py` fixtures currently):

```python
# tests/test_aberration.py
@pytest.fixture
def smartphone_tele_optic():
    return build_optic_for_scenario(
        Scenario.SMARTPHONE_TELEPHOTO, target_efl_mm=7.0, target_f_number=2.4
    )

def test_compute_mtf_returns_valid_result(smartphone_tele_optic):
    result = compute_mtf(smartphone_tele_optic)
    assert isinstance(result, MTFResult)
```

**Location:**
- Test data manifests: `tests/data/zmx_manifest.py` (e.g., `ZMX_AMMO` dictionary)
- Fixtures defined in test file that uses them (not centralized in `conftest.py`)
- Some fixtures shared across files by copy-paste (not ideal, but current practice)

**Factories:**
- Test helper functions with underscore: `_good_request()` builds valid request payload in `test_api_optical.py`
- `_sample_floor_gap(sample)` in `test_optical_match.py` computes floor gap for assertion

## Coverage

**Requirements:** No explicit coverage target enforced (not checked in CI)

**View Coverage:**
```bash
uv run pytest --cov=app --cov-report=html --cov-report=term
```
Generates `htmlcov/index.html` and terminal summary.

**Current State:** Gap analysis suggests untested areas (see CONCERNS.md), but no CI gate blocks low coverage.

## Test Types

**Unit Tests:**
- Scope: Single function or method in isolation
- Approach: Direct function calls with controlled inputs
- Location: `tests/test_optical_calc.py` (mathematical formulas), `test_parameter_guards.py` (validation logic)
- Example:
  ```python
  def test_thin_lens_image_distance():
      result = thin_lens_image_distance(object_distance_mm=100.0, focal_length_mm=50.0)
      assert math.isclose(result, 100.0, rel_tol=1e-6)
  ```

**Integration Tests:**
- Scope: Multiple modules working together (e.g., parameter guards + optical engine)
- Approach: API endpoint testing via `TestClient`
- Location: `tests/test_api_optical.py` (full HTTP roundtrip), `test_optical_match.py` (case matching + assessment)
- Example:
  ```python
  def test_raytrace_valid_input_returns_full_payload():
      r = client.post("/api/optical/raytrace", json=_good_request())
      assert r.status_code == 200
      data = r.json()
      assert "paraxial" in data and "surfaces" in data
  ```

**E2E Tests:**
- Not implemented (no Selenium / Playwright tests for frontend)
- Acceptance tasks defined in `scripts/export_acceptance_tasks.py` (manual/semi-automated probe)

## Common Patterns

**Async Testing:**
Handled by `pytest-asyncio` with `asyncio_mode = "auto"`:
```python
# Tests of async endpoints work seamlessly
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
# TestClient wraps async runtime; no explicit await needed
```

**Error Testing:**
```python
def test_efl_too_small_for_smartphone_telephoto_rejected():
    """Classic LLM hallucination: proposing 0.5mm EFL for a phone tele."""
    with pytest.raises(ParameterGuardError) as exc:
        validate_scenario_params(
            Scenario.SMARTPHONE_TELEPHOTO,
            efl_mm=0.5,
            f_number=2.4,
            fov_deg=30.0,
            image_height_mm=3.7,
        )
    assert "EFL" in str(exc.value)
    assert "smartphone-telephoto" in str(exc.value)
```

**Parametrized Tests:**
```python
# tests/test_optical_match.py
@pytest.mark.parametrize(...)
def test_...():
    ...
```
Single example found; not widely used yet.

**Tolerance for Floating-Point:**
```python
# Relative tolerance for normalized values
assert math.isclose(summary.effective_focal_length_mm, 7.0, rel_tol=1e-3)

# Absolute tolerance for small values
assert math.isclose(freq[0], 0.0, abs_tol=1e-9)

# Range assertions
assert 0.0 <= v <= 1.0 + 1e-6  # Allow small numerical error
```

**Assertions on Collections:**
```python
# Check monotonic ordering
assert z_values == sorted(z_values)

# Check cardinality
assert sum(1 for s in surfs if s.is_stop) == 1

# Check set equality
ray_ids = {p.ray_id for p in result.sampled_paths}
assert ray_ids == {"chief-axial", "marginal-upper", "marginal-lower"}

# Check all items satisfy property
for rms in result.rms_spot_radius_um_by_field:
    assert rms >= 0
```

## Test Execution in CI

**GitHub Actions:**
- Workflow: `.github/workflows/pytest.yml` (adapted from lumira backend)
- Runs on Ubuntu (no Windows encoding issues)
- Environment: `PYTHONUTF8` not needed (UTF-8 is default on Linux)
- Matrix: Python 3.12 (only version)
- Mock LLM keys provided: Tests skip live network calls

---

*Testing analysis: 2026-07-03*
