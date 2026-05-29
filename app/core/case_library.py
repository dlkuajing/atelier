"""Real-design optical case library (phase v2-02).

Turns the normalized real zmx designs into `OpticalSampleData` via the existing
Optiland pipeline (paraxial / surfaces / trace / MTF / layout-SVG), plus honest
per-case metadata. `build_sample_from_optic` builds one design;
`load_case_library` reads the generated JSON at runtime (cached).

Two real-design quirks are handled here (verified during ingest):
- **Field type**: real zmx files define ~12 RealImageHeight fields, which make
  GeometricMTF ray-aim by iterative inverse-solve → hangs. `regularize_fields_to_angle`
  (in zmx_ingest) switches to ANGLE fields at standard MTF fractions first.
- **Full-field NaN**: some designs' 1.0-field edge rays trace to NaN, crashing
  MTF. `_mtf_with_fallback` retries with progressively smaller field sets and
  records the max field reached in metadata (honest).
"""

from __future__ import annotations

import contextlib
import math
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.core.aberration import compute_mtf
from app.core.layout_svg import render_layout_svg
from app.core.lens_system import Scenario
from app.core.optical_engine import (
    compute_paraxial_summary,
    extract_surface_descriptors,
    trace_optic,
)
from app.core.optical_sample import CaseMetadata, OpticalSampleData
from app.core.zmx_ingest import ZMX_AMMO_DIR, regularize_fields_to_angle
from app.core.zmx_materials import _canon

# Generated case JSON lives under the backend root: core -> app -> <root>/data.
CASES_DIR = Path(__file__).resolve().parents[1] / "data" / "optical_cases"

_PRIMARY_WL_NM = 587.6  # d-line, matches zmx_ingest wavelength regularization
# JSON-safe stand-in for an infinite (flat) radius. Pydantic serializes
# float('inf') -> null, which then fails reload; 1e9 mm reads as effectively flat.
_PLANE_RADIUS_SENTINEL = 1e9

# Real ammo maxes at ~89.5° (no true 100°+ ultrawide); 85° is the wide/ultrawide
# divide we also calibrate parameter_guards bounds to (Plan 03).
_ULTRAWIDE_FOV_MIN = 85.0

# MTF field-fraction sets, tried widest-first; fall back when full-field rays NaN.
_MTF_FIELD_SETS: tuple[tuple[float, ...], ...] = (
    (0.0, 0.5, 0.7, 1.0),
    (0.0, 0.5, 0.7),
    (0.0, 0.5),
)


def _safe(value) -> float:
    """numpy-array-shaped scalar -> python float (optiland 0.6 / numpy 2.x)."""
    arr = np.asarray(value).flatten()
    return float(arr[0]) if arr.size else 0.0


def _classify_scenario(fov_deg: float) -> Scenario:
    if fov_deg >= _ULTRAWIDE_FOV_MIN:
        return Scenario.SMARTPHONE_ULTRAWIDE
    return Scenario.SMARTPHONE_WIDE


def _classify_surfaces(optic) -> tuple[int, int]:
    """Count imaging elements vs flat filter/cover-glass plates.

    An optical element is a surface whose *post* material is a real (non-air)
    medium — that's the front face of a lens or plate. If that face is curved
    (finite radius) it's an imaging element; if flat (radius inf) it's a filter /
    cover glass (the IR-cut plate, BRIEF 3.1). Object (0) and image (last) are
    skipped.
    """
    surfaces = optic.surface_group.surfaces
    n = len(surfaces)
    n_imaging = 0
    n_filter = 0
    for i, s in enumerate(surfaces):
        if i == 0 or i == n - 1:
            continue
        mat = getattr(s, "material_post", None)
        if mat is None or type(mat).__name__ == "IdealMaterial":
            continue  # air gap
        try:
            r = abs(_safe(s.geometry.radius))
        except Exception:
            r = float("inf")
        if (not np.isfinite(r)) or r > 1e4:
            n_filter += 1
        else:
            n_imaging += 1
    return n_imaging, n_filter


def _materials_from_zmx(filename: str) -> list[str]:
    """Distinct real material names from a zmx's GLAS rows (canonical, deduped).

    Read from the source file (not the loaded optic) because the loader resolves
    materials to nameless AbbeMaterial objects. Canonicalization strips the
    factory `_NN` suffix so ZEONEX-K26R_14 -> ZEONEX-K26R.
    """
    path = ZMX_AMMO_DIR / filename
    text = ""
    for enc in ("utf-16", "utf-16-le", "utf-8-sig", "latin-1"):
        try:
            text = path.read_text(encoding=enc)
            break
        except (UnicodeError, OSError):
            continue
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("GLAS"):
            continue
        tok = s.split()
        if len(tok) > 1 and tok[1] not in ("___BLANK", "0", "MIRROR"):
            canon = _canon(tok[1])
            if canon and canon not in seen:
                seen.add(canon)
                names.append(canon)
    return names


def _mtf_has_nan(mtf) -> bool:
    """True if any MTF value is NaN/None (full-field edge rays failed to trace).

    GeometricMTF can *return* (not raise) with NaN rms/curve entries when the
    outermost field's edge rays TIR or miss a surface; those can't serialize and
    aren't physically meaningful, so we treat them as a failed field set.
    """
    for v in mtf.rms_spot_radius_um_by_field:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return True
    for f in mtf.fields:
        for v in (*f.sagittal, *f.tangential):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return True
    return False


def _mtf_with_fallback(optic, fov_deg: float) -> tuple[object, float]:
    """Compute MTF, shrinking the field set until no value is NaN.

    Returns (MTFResult, max_field_fraction_reached). A <1.0 fraction is honest:
    the design's full-field edge rays couldn't be traced cleanly. Raises only if
    even the smallest field set yields NaN (we never ship NaN).
    """
    half = fov_deg / 2.0
    last_err: Exception | None = None
    for fracs in _MTF_FIELD_SETS:
        optic.set_field_type("angle")
        optic.fields.fields.clear()
        for frac in fracs:
            optic.add_field(y=half * frac)
        with contextlib.suppress(Exception):
            optic.ray_tracer.set_aiming("robust", max_iter=20)
        try:
            result = compute_mtf(optic, wavelength_nm=_PRIMARY_WL_NM)
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
        if not _mtf_has_nan(result):
            return result, fracs[-1]
        last_err = RuntimeError(f"MTF returned NaN at field set {fracs}")
    raise RuntimeError(f"MTF unusable for all field sets: {last_err}")


def build_sample_from_optic(
    optic,
    source_zmx: str,
    n_pieces: int,
    nominal_efl_mm: float,
    nominal_fov_deg: float,
) -> OpticalSampleData:
    """Build one OpticalSampleData from a normalized real optic + manifest nominals."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # ANGLE fields (full set) so trace / SVG aim fast; MTF may shrink it later.
        regularize_fields_to_angle(optic, nominal_fov_deg)
        paraxial = compute_paraxial_summary(optic)
        surfaces = extract_surface_descriptors(optic)
        # Flat filter/cover-glass faces have radius inf, which Pydantic serializes
        # to null (breaking reload). Replace with a JSON-safe flat sentinel.
        for sd in surfaces:
            if not math.isfinite(sd.radius_mm):
                sd.radius_mm = _PLANE_RADIUS_SENTINEL
        trace = trace_optic(optic, assembly_name=source_zmx, wavelength_nm=_PRIMARY_WL_NM)
        layout = render_layout_svg(optic)  # full fields (before any MTF shrink)
        mtf, mtf_frac = _mtf_with_fallback(optic, nominal_fov_deg)
        n_imaging, n_filter = _classify_surfaces(optic)

    materials = _materials_from_zmx(source_zmx)
    computed_efl = paraxial.effective_focal_length_mm
    efl_error_pct = abs(computed_efl - nominal_efl_mm) / nominal_efl_mm * 100.0

    metadata = CaseMetadata(
        case_id=source_zmx.rsplit(".", 1)[0],
        source_zmx=source_zmx,
        scenario=_classify_scenario(nominal_fov_deg),
        n_pieces=n_pieces,
        n_imaging=n_imaging,
        n_filter=n_filter,
        materials=materials,
        fov_deg=nominal_fov_deg,
        nominal_efl_mm=nominal_efl_mm,
        computed_efl_mm=computed_efl,
        efl_error_pct=efl_error_pct,
        mtf_max_field_frac=mtf_frac,
    )
    return OpticalSampleData(
        paraxial=paraxial,
        surfaces=surfaces,
        trace=trace,
        mtf=mtf,
        layout_svg=layout,
        metadata=metadata,
    )


@lru_cache(maxsize=1)
def load_case_library() -> list[OpticalSampleData]:
    """Load all generated case JSON (cached). Excludes index.json."""
    if not CASES_DIR.exists():
        return []
    cases: list[OpticalSampleData] = []
    for fp in sorted(CASES_DIR.glob("*.json")):
        if fp.name == "index.json":
            continue
        cases.append(OpticalSampleData.model_validate_json(fp.read_text()))
    return cases


# Parameter-distance weights — EFL dominates design intent, FOV next, F# loosest
# (same rationale as RealLensCaseStore in rag/store.py).
_MATCH_W_EFL, _MATCH_W_FOV, _MATCH_W_FNUM = 0.5, 0.3, 0.2


def match_case(
    scenario: Scenario, efl_mm: float, fnum: float, fov_deg: float
) -> OpticalSampleData | None:
    """Return the real case nearest to the requested params (same scenario).

    Ranks the scenario's cases by a min-max-normalized weighted Euclidean
    distance over (EFL, FOV, F#) — identical metric to the RAG store, but returns
    the full pre-generated OpticalSampleData (real paraxial/surfaces/trace/MTF/
    layout-SVG), not just a hit. Returns None if no case exists for the scenario.
    """
    cases = [
        c for c in load_case_library() if c.metadata is not None and c.metadata.scenario == scenario
    ]
    if not cases:
        return None

    efls = [c.metadata.computed_efl_mm for c in cases]
    fovs = [c.metadata.fov_deg for c in cases]
    fnums = [c.paraxial.f_number for c in cases]
    e_lo, e_hi = min(efls), max(efls)
    v_lo, v_hi = min(fovs), max(fovs)
    f_lo, f_hi = min(fnums), max(fnums)

    def _nd(target: float, value: float, lo: float, hi: float) -> float:
        return 0.0 if hi == lo else (target - value) / (hi - lo)

    def _distance(c: OpticalSampleData) -> float:
        de = _nd(efl_mm, c.metadata.computed_efl_mm, e_lo, e_hi)
        dv = _nd(fov_deg, c.metadata.fov_deg, v_lo, v_hi)
        df = _nd(fnum, c.paraxial.f_number, f_lo, f_hi)
        return (_MATCH_W_EFL * de**2 + _MATCH_W_FOV * dv**2 + _MATCH_W_FNUM * df**2) ** 0.5

    return min(cases, key=_distance)
