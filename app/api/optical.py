"""Optical computation endpoints — Optiland / prysm / rayoptics wrappers.

Phase 2 wave 1: parameter validation + /suggest endpoint live.
Wave 2 (post-Optiland install): /raytrace, /aberration, /layout-svg implemented.
"""

import json
import os
import re
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.aberration import MTFResult, compute_mtf
from app.core.case_library import (
    build_sample_from_optic,
    build_seed_intake_audit,
    load_case_library,
    match_case,
)
from app.core.demo_cache import (
    DemoAnalysisBundle,
    compute_demo_cache_bundle_for_request,
    demo_cache_request,
    load_demo_cache_bundle_for_request,
)
from app.core.engines import get_deep_engine
from app.core.job_store import JobNotFoundError, JobRecord, JobStatus, JobStore
from app.core.layout_svg import render_layout_svg
from app.core.lens_system import LayoutSVG, RayTraceResult, Scenario
from app.core.optical_engine import (
    ParaxialSummary,
    SurfaceDescriptor,
    build_optic_for_scenario,
    raytrace_from_spec,
)
from app.core.optical_sample import OpticalSampleData, SeedAcquisitionBrief, SeedIntakeAudit
from app.core.parameter_guards import (
    SCENARIO_BOUNDS,
    ParameterGuardError,
    validate_scenario_params,
)
from app.core.zmx_ingest import load_normalized_zmx

router = APIRouter()
job_store = JobStore()

_MAX_SEED_PREFLIGHT_BYTES = 2_000_000
_CANDIDATE_NAME_RE = re.compile(
    r"(?P<n>\d+)P_F(?P<fnum>\d+(?:\.\d+)?)_FOV(?P<fov>\d+(?:\.\d+)?)_"
    r"EFL(?P<efl>\d+(?:\.\d+)?)_IMH(?P<imh>\d+(?:\.\d+)?)_TTL(?P<ttl>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_SEED_ONLY_MODES = {"seed_only", "launch_seed_only", "fast_seed"}


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class OpticalSpecRequest(BaseModel):
    """Top-level paraxial spec from the Wizard. Used by raytrace/aberration/layout-svg."""

    scenario: Scenario
    focal_length_mm: float = Field(..., gt=0)
    f_number: float = Field(..., gt=0)
    field_of_view_deg: float = Field(..., gt=0, le=180)
    image_height_mm: float = Field(..., gt=0)
    n_elements: int | None = Field(None, ge=2, le=20)
    wavelength_nm: float = Field(550.0, gt=0)
    object_distance_mm: float | None = Field(None, gt=0)
    max_total_track_mm: float | None = Field(None, gt=0)
    max_weight_g: float | None = Field(None, gt=0)
    manufacturing_tier: str | None = None
    priority: str | None = None
    analysis_depth: Literal["full", "seed_only"] | None = None


class SuggestResponse(BaseModel):
    scenario: Scenario
    description: str
    efl_mm_range: tuple[float, float]
    f_number_range: tuple[float, float]
    fov_deg_range: tuple[float, float]
    image_height_mm_range: tuple[float, float]
    n_elements_range: tuple[int, int]


class RaytraceResponse(BaseModel):
    paraxial: ParaxialSummary
    surfaces: list[SurfaceDescriptor]
    trace: RayTraceResult


class EnginesResponse(BaseModel):
    available: bool
    default_engine: str
    engines: list[dict[str, object]]


class JobSubmitRequest(BaseModel):
    payload: dict[str, object] = Field(default_factory=dict)


class JobResponse(BaseModel):
    job_id: str
    engine: str
    status: JobStatus
    payload: dict[str, object]
    result: dict[str, object] | None = None
    error: str | None = None


def _resolve_optional_float_window(
    *,
    target: float | None,
    half_width: float,
    floor: float,
    explicit_lo: float | None,
    explicit_hi: float | None,
    label: str,
) -> list[float]:
    if target is None and explicit_lo is None and explicit_hi is None:
        return []
    if explicit_lo is not None and explicit_hi is not None:
        if explicit_lo > explicit_hi:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_seed_preflight_bounds", "message": f"{label} low > high"},
            )
        return [round(explicit_lo, 4), round(explicit_hi, 4)]
    if explicit_lo is not None or explicit_hi is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_seed_preflight_bounds",
                "message": f"{label} requires both low and high bounds",
            },
        )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_seed_preflight_bounds",
                "message": f"{label} target is required when explicit bounds are omitted",
            },
        )
    return [round(max(floor, target - half_width), 4), round(target + half_width, 4)]


def _resolve_optional_int_window(
    *,
    target: int | None,
    half_width: int,
    floor: int,
    ceiling: int,
    explicit_lo: int | None,
    explicit_hi: int | None,
    label: str,
) -> list[int]:
    if target is None and explicit_lo is None and explicit_hi is None:
        return []
    if explicit_lo is not None and explicit_hi is not None:
        if explicit_lo > explicit_hi:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "invalid_seed_preflight_bounds", "message": f"{label} low > high"},
            )
        return [explicit_lo, explicit_hi]
    if explicit_lo is not None or explicit_hi is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_seed_preflight_bounds",
                "message": f"{label} requires both low and high bounds",
            },
        )
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_seed_preflight_bounds",
                "message": f"{label} target is required when explicit bounds are omitted",
            },
        )
    return [max(floor, target - half_width), min(ceiling, target + half_width)]


def _seed_preflight_brief(
    *,
    target_fov: float,
    target_efl: float,
    target_fnum: float,
    min_fov: float,
    required_field: float,
    target_image_height: float | None,
    image_height_lo: float | None,
    image_height_hi: float | None,
    target_elements: int | None,
    element_count_lo: int | None,
    element_count_hi: int | None,
    max_total_track: float | None,
) -> SeedAcquisitionBrief:
    return SeedAcquisitionBrief(
        target_regime="smartphone visible-light high-FOV main/wide camera",
        priority="required_for_full_field_claim",
        source_format="Zemax/Optiland-compatible visible-light prescription with material metadata",
        target_fov_deg=target_fov,
        minimum_fov_deg=min_fov,
        target_efl_mm=target_efl,
        efl_window_mm=[round(max(0.1, target_efl - 0.30), 4), round(target_efl + 0.30, 4)],
        target_f_number=target_fnum,
        f_number_window=[round(max(0.8, target_fnum - 0.20), 4), round(target_fnum + 0.25, 4)],
        target_image_height_mm=target_image_height,
        image_height_window_mm=_resolve_optional_float_window(
            target=target_image_height,
            half_width=0.35,
            floor=0.1,
            explicit_lo=image_height_lo,
            explicit_hi=image_height_hi,
            label="image-height window",
        ),
        target_n_elements=target_elements,
        element_count_window=_resolve_optional_int_window(
            target=target_elements,
            half_width=1,
            floor=3,
            ceiling=8,
            explicit_lo=element_count_lo,
            explicit_hi=element_count_hi,
            label="element-count window",
        ),
        max_total_track_mm=max_total_track,
        required_mtf_field_frac=required_field,
        validation_requirements=[
            "visible-light wavelength set, not IR-only",
            "finite sampled ray trace through the 1.0 field",
            "MTF evaluates at 1.0 field without falling back below full field",
            "materials resolve to refractive-index data used by the backend",
            "element count and filter/cover plates can be classified from the prescription",
        ],
        rejection_filters=[
            "IR-only or monochrome near-IR prescriptions",
            "MTF max stable field below 1.0",
            "missing stop, semi-aperture, material, or wavelength metadata",
            "non-phone or non-visible-light optical scenario",
        ],
        rationale=[
            "browser upload uses the same runtime seed-intake contract",
            "full-field claim requires accepted seed evidence before promotion",
        ],
    )


def _candidate_nominals(
    *,
    filename: str,
    candidate_n_pieces: int | None,
    candidate_efl: float | None,
    candidate_fov: float | None,
) -> tuple[int, float, float]:
    match = _CANDIDATE_NAME_RE.search(filename)
    if match is not None:
        candidate_n_pieces = int(match.group("n"))
        candidate_efl = float(match.group("efl"))
        candidate_fov = float(match.group("fov"))
    missing: list[str] = []
    if candidate_n_pieces is None:
        missing.append("candidate_n_pieces")
    if candidate_efl is None:
        missing.append("candidate_efl")
    if candidate_fov is None:
        missing.append("candidate_fov")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "missing_seed_candidate_nominals",
                "message": f"missing {', '.join(missing)}",
            },
        )
    return candidate_n_pieces, candidate_efl, candidate_fov


def _job_response(record: JobRecord) -> JobResponse:
    return JobResponse(
        job_id=record.job_id,
        engine=record.engine,
        status=record.status,
        payload=dict(record.payload),
        result=dict(record.result) if record.result is not None else None,
        error=record.error,
    )


def _job_or_404(job_id: str) -> JobRecord:
    try:
        return job_store.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "job_not_found", "job_id": job_id},
        ) from exc


def _job_event_payload(record: JobRecord) -> dict[str, object]:
    return {
        "job_id": record.job_id,
        "engine": record.engine,
        "status": record.status.value,
        "result": dict(record.result) if record.result is not None else None,
        "error": record.error,
    }


def _sse_event(record: JobRecord) -> str:
    payload = json.dumps(_job_event_payload(record), separators=(",", ":"))
    return f"event: {record.status.value}\ndata: {payload}\n\n"


async def _job_event_stream(job_id: str) -> AsyncIterator[str]:
    async for record in job_store.events(job_id):
        yield _sse_event(record)


# ---------------------------------------------------------------------------
# /suggest — used by Wizard step 2 to populate sensible default ranges
# ---------------------------------------------------------------------------


@router.get("/engines", response_model=EnginesResponse)
async def engines() -> EnginesResponse:
    """Return the current deep-engine inventory and runtime availability."""
    engine = get_deep_engine()
    description = engine.describe()
    return EnginesResponse(
        available=engine.is_available(),
        default_engine=engine.name,
        engines=[description],
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(req: JobSubmitRequest) -> JobResponse:
    """Queue one deep-engine job for background execution."""
    job_id = job_store.submit(get_deep_engine(), req.payload)
    return _job_response(job_store.get(job_id))


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Return the latest background job snapshot."""
    return _job_response(_job_or_404(job_id))


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    """Stream status changes for one background job as server-sent events."""
    _job_or_404(job_id)
    return StreamingResponse(_job_event_stream(job_id), media_type="text/event-stream")


@router.get("/suggest/{scenario}", response_model=SuggestResponse)
async def suggest_bounds(scenario: Scenario) -> SuggestResponse:
    """Return scenario-specific parameter bounds so the Wizard can offer
    realistic defaults and validate user input."""
    bounds = SCENARIO_BOUNDS[scenario]
    return SuggestResponse(
        scenario=scenario,
        description=bounds.description,
        efl_mm_range=(bounds.efl_mm_min, bounds.efl_mm_max),
        f_number_range=(bounds.f_number_min, bounds.f_number_max),
        fov_deg_range=(bounds.fov_deg_min, bounds.fov_deg_max),
        image_height_mm_range=(bounds.image_height_mm_min, bounds.image_height_mm_max),
        n_elements_range=(bounds.n_elements_min, bounds.n_elements_max),
    )


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------


def _validate_or_400(req: OpticalSpecRequest) -> None:
    """Run parameter_guards and convert ParameterGuardError → HTTP 400."""
    try:
        validate_scenario_params(
            req.scenario,
            efl_mm=req.focal_length_mm,
            f_number=req.f_number,
            fov_deg=req.field_of_view_deg,
            image_height_mm=req.image_height_mm,
            n_elements=req.n_elements,
        )
    except ParameterGuardError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "parameter_guard_failed",
                "scenario": req.scenario,
                "violations": e.violations,
                "message": str(e),
            },
        ) from e


# ---------------------------------------------------------------------------
# /raytrace — Phase 2 wave 2 (Optiland)
# ---------------------------------------------------------------------------


@router.post(
    "/raytrace",
    response_model=RaytraceResponse,
    responses={
        400: {"description": "Parameter guard violation"},
        500: {"description": "Optiland engine failure"},
    },
)
async def raytrace(req: OpticalSpecRequest) -> RaytraceResponse:
    """Run optical ray trace via Optiland.

    Returns the paraxial summary, flattened surface descriptors, and sampled
    chief + marginal ray paths — everything the frontend needs to render a
    2D layout and report the realised f-number / EFL / EPD.
    """
    _validate_or_400(req)
    try:
        summary, surfaces, trace = raytrace_from_spec(
            scenario=req.scenario,
            target_efl_mm=req.focal_length_mm,
            target_f_number=req.f_number,
            wavelength_nm=req.wavelength_nm,
        )
    except Exception as e:  # noqa: BLE001 — Optiland leaks TypeError / IndexError
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "optical_engine_failure",
                "scenario": req.scenario,
                "message": str(e),
            },
        ) from e
    return RaytraceResponse(paraxial=summary, surfaces=surfaces, trace=trace)


@router.post(
    "/aberration",
    response_model=MTFResult,
    responses={
        400: {"description": "Parameter guard violation"},
        500: {"description": "Optiland engine failure"},
    },
)
async def aberration(req: OpticalSpecRequest) -> MTFResult:
    """Compute geometric MTF, spot RMS, and Airy disc via Optiland.

    PSF and Zernike are deferred to v2 polish; v1 demo needs MTF curves only.
    """
    _validate_or_400(req)
    try:
        optic = build_optic_for_scenario(
            scenario=req.scenario,
            target_efl_mm=req.focal_length_mm,
            target_f_number=req.f_number,
        )
        return compute_mtf(optic, wavelength_nm=req.wavelength_nm)
    except Exception as e:  # noqa: BLE001 — Optiland leaks TypeError / IndexError
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "aberration_compute_failure",
                "scenario": req.scenario,
                "message": str(e),
            },
        ) from e


@router.post(
    "/layout-svg",
    response_model=LayoutSVG,
    responses={
        400: {"description": "Parameter guard violation"},
        500: {"description": "Optiland engine failure"},
    },
)
async def layout_svg(req: OpticalSpecRequest) -> LayoutSVG:
    """Render the optic's 2D cross-section as an SVG.

    Uses Optiland's matplotlib-backed `draw()` and captures the result as
    a self-contained SVG string. The frontend renders this alongside the
    interactive R3F 3D scene.
    """
    _validate_or_400(req)
    try:
        optic = build_optic_for_scenario(
            scenario=req.scenario,
            target_efl_mm=req.focal_length_mm,
            target_f_number=req.f_number,
        )
        return render_layout_svg(optic)
    except Exception as e:  # noqa: BLE001 — Optiland leaks TypeError / IndexError
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "layout_render_failure",
                "scenario": req.scenario,
                "message": str(e),
            },
        ) from e


@router.post(
    "/seed-intake/preflight",
    response_model=SeedIntakeAudit,
    responses={
        400: {"description": "Invalid upload or seed-intake target"},
        413: {"description": "Uploaded ZMX exceeds size limit"},
        422: {"description": "Candidate ZMX could not be normalized or traced"},
    },
)
async def seed_intake_preflight(
    candidate_zmx: Annotated[UploadFile, File(..., description="Candidate ZMX file")],
    target_fov: Annotated[float, Form(gt=0, le=180)] = 88.0,
    target_efl: Annotated[float, Form(gt=0)] = 2.8,
    target_fnum: Annotated[float, Form(gt=0)] = 1.9,
    min_fov: Annotated[float, Form(gt=0, le=180)] = 85.0,
    required_field: Annotated[float, Form(gt=0, le=1.0)] = 1.0,
    target_image_height: Annotated[float | None, Form(gt=0)] = None,
    image_height_lo: Annotated[float | None, Form(gt=0)] = None,
    image_height_hi: Annotated[float | None, Form(gt=0)] = None,
    target_elements: Annotated[int | None, Form(ge=3, le=8)] = None,
    element_count_lo: Annotated[int | None, Form(ge=3, le=8)] = None,
    element_count_hi: Annotated[int | None, Form(ge=3, le=8)] = None,
    max_total_track: Annotated[float | None, Form(gt=0)] = None,
    candidate_n_pieces: Annotated[int | None, Form(ge=3, le=8)] = None,
    candidate_efl: Annotated[float | None, Form(gt=0)] = None,
    candidate_fov: Annotated[float | None, Form(gt=0, le=180)] = None,
) -> SeedIntakeAudit:
    """Preflight one uploaded high-FOV seed candidate without persisting it."""
    filename = Path(candidate_zmx.filename or "candidate.zmx").name
    if not filename.lower().endswith(".zmx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_seed_file_type", "message": "candidate must be a .zmx file"},
        )

    content = await candidate_zmx.read()
    if len(content) > _MAX_SEED_PREFLIGHT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "seed_file_too_large",
                "message": f"candidate exceeds {_MAX_SEED_PREFLIGHT_BYTES} bytes",
            },
        )

    n_pieces, nominal_efl, nominal_fov = _candidate_nominals(
        filename=filename,
        candidate_n_pieces=candidate_n_pieces,
        candidate_efl=candidate_efl,
        candidate_fov=candidate_fov,
    )
    brief = _seed_preflight_brief(
        target_fov=target_fov,
        target_efl=target_efl,
        target_fnum=target_fnum,
        min_fov=min_fov,
        required_field=required_field,
        target_image_height=target_image_height,
        image_height_lo=image_height_lo,
        image_height_hi=image_height_hi,
        target_elements=target_elements,
        element_count_lo=element_count_lo,
        element_count_hi=element_count_hi,
        max_total_track=max_total_track,
    )

    try:
        with TemporaryDirectory(prefix="lumira-seed-preflight-") as tmpdir:
            candidate_path = Path(tmpdir) / filename
            candidate_path.write_bytes(content)
            optic = load_normalized_zmx(candidate_path)
            candidate = build_sample_from_optic(
                optic,
                source_zmx=filename,
                n_pieces=n_pieces,
                nominal_efl_mm=nominal_efl,
                nominal_fov_deg=nominal_fov,
                source_path=candidate_path,
            )
    except Exception as e:  # noqa: BLE001 — candidate files fail in many parser/trace ways
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "seed_preflight_failed", "message": str(e)},
        ) from e

    cases = [sample for sample in load_case_library() if sample.metadata is not None]
    cases.append(candidate)
    return build_seed_intake_audit(cases=cases, brief=brief)


# ---------------------------------------------------------------------------
# /match — v2-03: retrieve the nearest REAL design from the case library
# ---------------------------------------------------------------------------


def _assessment_mode(req: OpticalSpecRequest) -> Literal["full", "lightweight", "none"]:
    if req.analysis_depth == "full":
        return "full"
    if req.analysis_depth == "seed_only":
        return "none"
    if os.getenv("LUMIRA_MATCH_MODE", "").strip().lower() in _SEED_ONLY_MODES:
        return "lightweight"
    return "full"


def _match_case_for_request(
    req: OpticalSpecRequest,
    *,
    assessment_mode: Literal["full", "lightweight", "none"],
) -> OpticalSampleData | None:
    return match_case(
        scenario=req.scenario,
        efl_mm=req.focal_length_mm,
        fnum=req.f_number,
        fov_deg=req.field_of_view_deg,
        image_height_mm=req.image_height_mm,
        n_elements=req.n_elements,
        max_total_track_mm=req.max_total_track_mm,
        max_weight_g=req.max_weight_g,
        manufacturing_tier=req.manufacturing_tier,
        priority=req.priority,
        include_design_assessment=assessment_mode != "none",
        lightweight_design_assessment=assessment_mode == "lightweight",
    )


def _no_real_case_error(req: OpticalSpecRequest) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "no_real_case_for_scenario",
            "scenario": req.scenario,
            "message": (
                f"No real design in the case library for scenario "
                f"{req.scenario.value}. This phase ships smartphone "
                f"wide / ultrawide only."
            ),
        },
    )


def _cached_match_sample(
    req: OpticalSpecRequest,
    cached: DemoAnalysisBundle,
    *,
    assessment_mode: Literal["full", "lightweight", "none"],
) -> OpticalSampleData:
    if assessment_mode == "none":
        return cached.sample.model_copy(update={"design_assessment": None}, deep=True)

    assessed = _match_case_for_request(req, assessment_mode=assessment_mode)
    if assessed is None:
        raise _no_real_case_error(req)
    return cached.sample.model_copy(
        update={"design_assessment": assessed.design_assessment},
        deep=True,
    )


@router.post(
    "/match",
    response_model=OpticalSampleData,
    responses={
        400: {"description": "Parameter guard violation"},
        404: {"description": "No real case for this scenario"},
    },
)
async def match(req: OpticalSpecRequest, response: Response) -> OpticalSampleData:
    """Retrieve the real production design nearest to the requested params.

    Unlike /raytrace + /aberration + /layout-svg (which scale a textbook
    reference design), this returns a **real** pre-computed design from the
    v2-02 case library — its actual prescription, Optiland-verified MTF, and
    2D layout, plus honest provenance metadata. v2-05 scores full design intent:
    EFL / FOV / F#, image height, element count, TTL, and coarse cost/performance
    stance, then attaches `design_assessment` with deltas and tradeoffs.
    """
    _validate_or_400(req)
    assessment_mode = _assessment_mode(req)
    cache_request = demo_cache_request(
        scenario=req.scenario,
        focal_length_mm=req.focal_length_mm,
        f_number=req.f_number,
        field_of_view_deg=req.field_of_view_deg,
        image_height_mm=req.image_height_mm,
        n_elements=req.n_elements,
        wavelength_nm=req.wavelength_nm,
        max_total_track_mm=req.max_total_track_mm,
        max_weight_g=req.max_weight_g,
        manufacturing_tier=req.manufacturing_tier,
        priority=req.priority,
    )
    cached = load_demo_cache_bundle_for_request(cache_request)
    if cached is not None:
        response.headers["X-Demo-Cache"] = "hit"
        return _cached_match_sample(req, cached, assessment_mode=assessment_mode)

    response.headers["X-Demo-Cache"] = "miss"
    case = _match_case_for_request(req, assessment_mode=assessment_mode)
    if case is None:
        raise _no_real_case_error(req)
    return case


@router.post(
    "/demo-cache",
    response_model=DemoAnalysisBundle,
    responses={
        400: {"description": "Parameter guard violation"},
        404: {"description": "No real case for this scenario"},
    },
)
async def demo_cache(req: OpticalSpecRequest, response: Response) -> DemoAnalysisBundle:
    """Return the complete demo analysis family, preferring precomputed cache."""

    _validate_or_400(req)
    cache_request = demo_cache_request(
        scenario=req.scenario,
        focal_length_mm=req.focal_length_mm,
        f_number=req.f_number,
        field_of_view_deg=req.field_of_view_deg,
        image_height_mm=req.image_height_mm,
        n_elements=req.n_elements,
        wavelength_nm=req.wavelength_nm,
        max_total_track_mm=req.max_total_track_mm,
        max_weight_g=req.max_weight_g,
        manufacturing_tier=req.manufacturing_tier,
        priority=req.priority,
    )
    cached = load_demo_cache_bundle_for_request(cache_request)
    if cached is not None:
        response.headers["X-Demo-Cache"] = "hit"
        return cached

    response.headers["X-Demo-Cache"] = "miss"
    try:
        return compute_demo_cache_bundle_for_request(cache_request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "no_real_case_for_scenario",
                "scenario": req.scenario,
                "message": str(exc),
            },
        ) from exc
