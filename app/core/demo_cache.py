"""Demo analysis cache bundles for offline-friendly result playback."""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.case_library import _case_image_height_mm, load_case_library, match_case
from app.core.field_analysis import FieldAnalysisResult, compute_field_analysis
from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData
from app.core.spot_diagram import SpotDiagramResult, compute_spot_diagram
from app.core.wavefront_metrics import WavefrontMetricsResult, compute_wavefront_metrics
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx, regularize_fields_to_angle

ROOT = Path(__file__).resolve().parents[2]
DEMO_CACHE_DIR = ROOT / "data" / "demo_cache"
DEMO_CACHE_SCHEMA_VERSION = 2
DEMO_CACHE_ANALYSIS_VERSION = "optiland-demo-analysis-v2"
DEFAULT_DEMO_CASE_IDS = (
    "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56",
    "US20170003482A1",
)

_IMH_RE = re.compile(r"_IMH(?P<imh>\d+(?:\.\d+)?)")
_FNUM_RE = re.compile(r"(?:^|_)F(?P<fnum>\d+(?:\.\d+)?)(?=_FOV|_)")
_FLOAT_DIGITS = 6
_EXACT_FLOAT_TOLERANCE = 10**-_FLOAT_DIGITS
_F_NUMBER_CACHE_LOOKUP_TOLERANCE = 0.075
_ANALYSIS_PARAMETERS = {
    "spot_diagram": {"num_rings": 3},
    "field_analysis": {"num_points": 32},
    "wavefront": {"num_rays": 6, "num_zernike_terms": 12},
}


def _analysis_fingerprint() -> str:
    payload = {
        "schema": DEMO_CACHE_SCHEMA_VERSION,
        "analysis_version": DEMO_CACHE_ANALYSIS_VERSION,
        "parameters": _ANALYSIS_PARAMETERS,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


DEMO_CACHE_ANALYSIS_FINGERPRINT = _analysis_fingerprint()


class DemoCacheRequest(BaseModel):
    """Canonical optical request fields used to address one demo cache bundle."""

    scenario: Scenario
    focal_length_mm: float = Field(..., gt=0)
    f_number: float = Field(..., gt=0)
    field_of_view_deg: float = Field(..., gt=0, le=180)
    image_height_mm: float = Field(..., gt=0)
    n_elements: int | None = Field(None, ge=2, le=30)
    wavelength_nm: float = Field(550.0, gt=0)
    max_total_track_mm: float | None = Field(None, gt=0)
    max_weight_g: float | None = Field(None, gt=0)
    manufacturing_tier: str | None = None
    priority: str | None = None


class DemoAnalysisBundle(BaseModel):
    """Full cached analysis family for one demo request and selected seed."""

    cache_schema_version: int = DEMO_CACHE_SCHEMA_VERSION
    cache_key: str
    analysis_fingerprint: str = DEMO_CACHE_ANALYSIS_FINGERPRINT
    generated_at_utc: str
    source: Literal["demo-precompute", "runtime-fallback"] = "demo-precompute"
    source_case_id: str
    source_zmx: str
    source_zmx_sha256: str = Field(..., min_length=64, max_length=64)
    request: DemoCacheRequest
    sample: OpticalSampleData
    spot_diagram: SpotDiagramResult
    field_analysis: FieldAnalysisResult
    wavefront: WavefrontMetricsResult
    executive_summary: dict[str, Any] | None = Field(
        None,
        description="Precomputed bilingual executive summary for fast result-page playback.",
    )
    codev_artifact: dict[str, Any] | None = Field(
        None,
        description="Reserved slot for future CODE V output using the same cache address.",
    )


def demo_cache_request(
    *,
    scenario: Scenario,
    focal_length_mm: float,
    f_number: float,
    field_of_view_deg: float,
    image_height_mm: float,
    n_elements: int | None = None,
    wavelength_nm: float = 550.0,
    max_total_track_mm: float | None = None,
    max_weight_g: float | None = None,
    manufacturing_tier: str | None = None,
    priority: str | None = None,
) -> DemoCacheRequest:
    """Build a validated cache request from API/form fields."""

    return DemoCacheRequest(
        scenario=scenario,
        focal_length_mm=focal_length_mm,
        f_number=f_number,
        field_of_view_deg=field_of_view_deg,
        image_height_mm=image_height_mm,
        n_elements=n_elements,
        wavelength_nm=wavelength_nm,
        max_total_track_mm=max_total_track_mm,
        max_weight_g=max_weight_g,
        manufacturing_tier=manufacturing_tier,
        priority=priority,
    )


def _rounded(value: float | None) -> float | None:
    return round(float(value), _FLOAT_DIGITS) if value is not None else None


def _request_key_payload(
    request: DemoCacheRequest,
    *,
    source_case_id: str | None = None,
    source_zmx_sha256: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": DEMO_CACHE_SCHEMA_VERSION,
        "analysis_fingerprint": DEMO_CACHE_ANALYSIS_FINGERPRINT,
        "scenario": request.scenario.value,
        "focal_length_mm": _rounded(request.focal_length_mm),
        "f_number": _rounded(request.f_number),
        "field_of_view_deg": _rounded(request.field_of_view_deg),
        "image_height_mm": _rounded(request.image_height_mm),
        "n_elements": request.n_elements,
        "wavelength_nm": _rounded(request.wavelength_nm),
        "max_total_track_mm": _rounded(request.max_total_track_mm),
        "max_weight_g": _rounded(request.max_weight_g),
        "manufacturing_tier": request.manufacturing_tier,
        "priority": request.priority,
    }
    if source_case_id is not None:
        payload["source_case_id"] = source_case_id
    if source_zmx_sha256 is not None:
        payload["source_zmx_sha256"] = source_zmx_sha256
    return payload


def demo_cache_key(
    request: DemoCacheRequest,
    *,
    source_case_id: str | None = None,
    source_zmx_sha256: str | None = None,
) -> str:
    """Stable content-address for one demo request."""

    payload = json.dumps(
        _request_key_payload(
            request,
            source_case_id=source_case_id,
            source_zmx_sha256=source_zmx_sha256,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{request.scenario.value}-{digest}"


def demo_cache_path(request: DemoCacheRequest, cache_dir: Path | None = None) -> Path:
    """Return the JSON path for one request under the demo cache directory."""

    root = cache_dir or DEMO_CACHE_DIR
    return root / f"{demo_cache_key(request)}.json"


def load_demo_cache_bundle_for_request(
    request: DemoCacheRequest,
    *,
    cache_dir: Path | None = None,
) -> DemoAnalysisBundle | None:
    """Load a current cache hit, returning None when absent or stale."""

    root = cache_dir or DEMO_CACHE_DIR
    path = demo_cache_path(request, cache_dir=cache_dir)
    if path.exists():
        loaded = _load_current_bundle(path, request)
        if loaded is not None:
            return loaded

    if not root.exists():
        return None
    for candidate in sorted(root.glob(f"{request.scenario.value}-*.json")):
        if candidate == path:
            continue
        loaded = _load_current_bundle(candidate, request)
        if loaded is not None:
            return loaded
    return None


def write_demo_cache_bundle(
    bundle: DemoAnalysisBundle,
    *,
    cache_dir: Path | None = None,
) -> Path:
    """Persist a cache bundle to disk and return its path."""

    root = cache_dir or DEMO_CACHE_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{bundle.cache_key}.json"
    path.write_text(
        bundle.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )
    return path


def _case_id(value: str) -> str:
    name = Path(value).name
    suffix = Path(name).suffix.lower()
    if suffix in {".json", ".zmx"}:
        return name[: -len(suffix)]
    return name


def _image_height_from_case_id(case_id: str) -> float:
    match = _IMH_RE.search(case_id)
    if match is None:
        return 1.0
    return float(match.group("imh"))


def _nominal_f_number_from_case_id(case_id: str) -> float | None:
    match = _FNUM_RE.search(case_id)
    if match is None:
        return None
    return float(match.group("fnum"))


def _request_from_sample(sample: OpticalSampleData) -> DemoCacheRequest:
    if sample.metadata is None:
        raise ValueError("demo cache sample requires metadata")
    case_id = sample.metadata.case_id
    image_height_mm = _case_image_height_mm(sample) or _image_height_from_case_id(case_id)
    return DemoCacheRequest(
        scenario=sample.metadata.scenario,
        focal_length_mm=sample.metadata.nominal_efl_mm,
        f_number=_nominal_f_number_from_case_id(case_id) or sample.paraxial.f_number,
        field_of_view_deg=sample.metadata.fov_deg,
        image_height_mm=image_height_mm,
        n_elements=sample.metadata.n_pieces,
        wavelength_nm=550.0,
    )


def _find_case_sample(case_id: str) -> OpticalSampleData:
    normalized = _case_id(case_id)
    for sample in load_case_library():
        if sample.metadata is not None and sample.metadata.case_id == normalized:
            return sample
    raise ValueError(f"demo case not found in case library: {case_id}")


def _source_zmx_path(sample: OpticalSampleData) -> Path:
    if sample.metadata is None:
        raise ValueError("demo cache sample requires metadata")
    path = ZMX_AMMO_DIR / sample.metadata.source_zmx
    if not path.exists():
        raise FileNotFoundError(f"source ZMX not found: {path}")
    return path


def source_zmx_sha256(source_zmx: str | Path) -> str:
    """Return the SHA-256 digest for a source ZMX file."""

    path = Path(source_zmx)
    if not path.is_absolute():
        path = ZMX_AMMO_DIR / path
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_zmx_sha256_for_sample(sample: OpticalSampleData) -> str:
    return source_zmx_sha256(_source_zmx_path(sample))


def _float_close(left: float | None, right: float | None, *, tolerance: float) -> bool:
    if left is None or right is None:
        return left is right
    return abs(float(left) - float(right)) <= tolerance


def _cache_request_matches(cached: DemoCacheRequest, request: DemoCacheRequest) -> bool:
    if cached.scenario != request.scenario:
        return False
    exact_fields = (
        "n_elements",
        "manufacturing_tier",
        "priority",
    )
    if any(getattr(cached, field) != getattr(request, field) for field in exact_fields):
        return False
    numeric_tolerances = {
        "focal_length_mm": _EXACT_FLOAT_TOLERANCE,
        "f_number": _F_NUMBER_CACHE_LOOKUP_TOLERANCE,
        "field_of_view_deg": _EXACT_FLOAT_TOLERANCE,
        "image_height_mm": _EXACT_FLOAT_TOLERANCE,
        "wavelength_nm": _EXACT_FLOAT_TOLERANCE,
        "max_total_track_mm": _EXACT_FLOAT_TOLERANCE,
        "max_weight_g": _EXACT_FLOAT_TOLERANCE,
    }
    return all(
        _float_close(
            getattr(cached, field),
            getattr(request, field),
            tolerance=tolerance,
        )
        for field, tolerance in numeric_tolerances.items()
    )


def _bundle_cache_key(bundle: DemoAnalysisBundle) -> str:
    return demo_cache_key(
        bundle.request,
        source_case_id=bundle.source_case_id,
        source_zmx_sha256=bundle.source_zmx_sha256,
    )


def _bundle_is_current(bundle: DemoAnalysisBundle) -> bool:
    if bundle.cache_schema_version != DEMO_CACHE_SCHEMA_VERSION:
        return False
    if bundle.analysis_fingerprint != DEMO_CACHE_ANALYSIS_FINGERPRINT:
        return False
    try:
        current_source_sha = source_zmx_sha256(bundle.source_zmx)
    except FileNotFoundError:
        return False
    if bundle.source_zmx_sha256 != current_source_sha:
        return False
    return bundle.cache_key == _bundle_cache_key(bundle)


def _load_current_bundle(path: Path, request: DemoCacheRequest) -> DemoAnalysisBundle | None:
    try:
        bundle = DemoAnalysisBundle.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - cache load treats corrupt/stale files as a miss.
        return None
    if not _cache_request_matches(bundle.request, request):
        return None
    if not _bundle_is_current(bundle):
        return None
    return bundle


def _compute_analysis_family(sample: OpticalSampleData) -> tuple[
    SpotDiagramResult,
    FieldAnalysisResult,
    WavefrontMetricsResult,
]:
    if sample.metadata is None:
        raise ValueError("demo cache sample requires metadata")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(_source_zmx_path(sample))
        regularize_fields_to_angle(optic, sample.metadata.fov_deg)
        spot = compute_spot_diagram(optic, num_rings=3)
        field = compute_field_analysis(optic, num_points=32)
        wavefront = compute_wavefront_metrics(optic, num_rays=6, num_zernike_terms=12)
    return spot, field, wavefront


def build_demo_cache_bundle(
    *,
    sample: OpticalSampleData,
    request: DemoCacheRequest | None = None,
    source: Literal["demo-precompute", "runtime-fallback"] = "demo-precompute",
) -> DemoAnalysisBundle:
    """Compute the missing analysis artifacts and assemble a cache bundle."""

    if sample.metadata is None:
        raise ValueError("demo cache sample requires metadata")
    cache_request = request or _request_from_sample(sample)
    source_sha = _source_zmx_sha256_for_sample(sample)
    cache_key = demo_cache_key(
        cache_request,
        source_case_id=sample.metadata.case_id,
        source_zmx_sha256=source_sha,
    )
    spot, field, wavefront = _compute_analysis_family(sample)
    return DemoAnalysisBundle(
        cache_key=cache_key,
        analysis_fingerprint=DEMO_CACHE_ANALYSIS_FINGERPRINT,
        generated_at_utc=datetime.now(UTC).isoformat(),
        source=source,
        source_case_id=sample.metadata.case_id,
        source_zmx=sample.metadata.source_zmx,
        source_zmx_sha256=source_sha,
        request=cache_request,
        sample=sample,
        spot_diagram=spot,
        field_analysis=field,
        wavefront=wavefront,
    )


def build_demo_cache_bundle_for_case(
    case_id: str,
    *,
    request: DemoCacheRequest | None = None,
) -> DemoAnalysisBundle:
    """Build a precompute bundle for a named generated case-library seed."""

    return build_demo_cache_bundle(
        sample=_find_case_sample(case_id),
        request=request,
        source="demo-precompute",
    )


def compute_demo_cache_bundle_for_request(request: DemoCacheRequest) -> DemoAnalysisBundle:
    """Runtime fallback: compute the same bundle when no precomputed file exists."""

    sample = match_case(
        scenario=request.scenario,
        efl_mm=request.focal_length_mm,
        fnum=request.f_number,
        fov_deg=request.field_of_view_deg,
        image_height_mm=request.image_height_mm,
        n_elements=request.n_elements,
        max_total_track_mm=request.max_total_track_mm,
        max_weight_g=request.max_weight_g,
        manufacturing_tier=request.manufacturing_tier,
        priority=request.priority,
        include_design_assessment=False,
    )
    if sample is None:
        raise ValueError(f"no real demo case for scenario {request.scenario.value}")
    return build_demo_cache_bundle(sample=sample, request=request, source="runtime-fallback")
