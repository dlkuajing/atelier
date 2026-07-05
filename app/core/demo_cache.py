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

from app.core.case_library import load_case_library, match_case
from app.core.field_analysis import FieldAnalysisResult, compute_field_analysis
from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData
from app.core.spot_diagram import SpotDiagramResult, compute_spot_diagram
from app.core.wavefront_metrics import WavefrontMetricsResult, compute_wavefront_metrics
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx, regularize_fields_to_angle

ROOT = Path(__file__).resolve().parents[2]
DEMO_CACHE_DIR = ROOT / "data" / "demo_cache"
DEMO_CACHE_SCHEMA_VERSION = 1
DEFAULT_DEMO_CASE_IDS = ("3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56",)

_IMH_RE = re.compile(r"_IMH(?P<imh>\d+(?:\.\d+)?)")
_FLOAT_DIGITS = 6


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
    generated_at_utc: str
    source: Literal["demo-precompute", "runtime-fallback"] = "demo-precompute"
    source_case_id: str
    source_zmx: str
    request: DemoCacheRequest
    sample: OpticalSampleData
    spot_diagram: SpotDiagramResult
    field_analysis: FieldAnalysisResult
    wavefront: WavefrontMetricsResult
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


def _request_key_payload(request: DemoCacheRequest) -> dict[str, object]:
    return {
        "schema": DEMO_CACHE_SCHEMA_VERSION,
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


def demo_cache_key(request: DemoCacheRequest) -> str:
    """Stable content-address for one demo request."""

    payload = json.dumps(_request_key_payload(request), sort_keys=True, separators=(",", ":"))
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
    """Load an exact cache hit, returning None when the bundle is absent."""

    path = demo_cache_path(request, cache_dir=cache_dir)
    if not path.exists():
        return None
    return DemoAnalysisBundle.model_validate_json(path.read_text(encoding="utf-8"))


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
    return name.rsplit(".", 1)[0]


def _image_height_from_case_id(case_id: str) -> float:
    match = _IMH_RE.search(case_id)
    if match is None:
        return 1.0
    return float(match.group("imh"))


def _request_from_sample(sample: OpticalSampleData) -> DemoCacheRequest:
    if sample.metadata is None:
        raise ValueError("demo cache sample requires metadata")
    case_id = sample.metadata.case_id
    return DemoCacheRequest(
        scenario=sample.metadata.scenario,
        focal_length_mm=sample.metadata.nominal_efl_mm,
        f_number=sample.paraxial.f_number,
        field_of_view_deg=sample.metadata.fov_deg,
        image_height_mm=_image_height_from_case_id(case_id),
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
    cache_key = demo_cache_key(cache_request)
    spot, field, wavefront = _compute_analysis_family(sample)
    return DemoAnalysisBundle(
        cache_key=cache_key,
        generated_at_utc=datetime.now(UTC).isoformat(),
        source=source,
        source_case_id=sample.metadata.case_id,
        source_zmx=sample.metadata.source_zmx,
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
