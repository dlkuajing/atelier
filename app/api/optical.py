"""Optical computation endpoints — Optiland / prysm / rayoptics wrappers.

Phase 2 wave 1: parameter validation + /suggest endpoint live.
Wave 2 (post-Optiland install): /raytrace, /aberration, /layout-svg implemented.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.aberration import MTFResult, compute_mtf
from app.core.layout_svg import render_layout_svg
from app.core.lens_system import LayoutSVG, RayTraceResult, Scenario
from app.core.optical_engine import (
    ParaxialSummary,
    SurfaceDescriptor,
    build_optic_for_scenario,
    raytrace_from_spec,
)
from app.core.parameter_guards import (
    SCENARIO_BOUNDS,
    ParameterGuardError,
    validate_scenario_params,
)


router = APIRouter()


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


# ---------------------------------------------------------------------------
# /suggest — used by Wizard step 2 to populate sensible default ranges
# ---------------------------------------------------------------------------


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
