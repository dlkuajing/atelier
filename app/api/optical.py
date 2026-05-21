"""Optical computation endpoints — Optiland / prysm / rayoptics wrappers.

Phase 2 wave 1: parameter validation + /suggest endpoint live.
Wave 2 (post-Optiland install): /raytrace, /aberration, /layout-svg implemented.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.lens_system import LayoutSVG, RayTraceResult, Scenario
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
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=RayTraceResult,
    responses={400: {"description": "Parameter guard violation"}},
)
async def raytrace(req: OpticalSpecRequest) -> RayTraceResult:
    """Run optical ray trace via Optiland and return lens layout + ray paths.

    Wave 2 implementation. Currently validates input then returns 501.
    """
    _validate_or_400(req)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2 wave 2: Optiland integration pending (libs installing)",
    )


@router.post(
    "/aberration",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={400: {"description": "Parameter guard violation"}},
)
async def aberration(req: OpticalSpecRequest) -> dict:
    """Compute MTF / PSF / Zernike via prysm.

    Wave 2 implementation.
    """
    _validate_or_400(req)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2 wave 2: prysm integration pending",
    )


@router.post(
    "/layout-svg",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=LayoutSVG,
    responses={400: {"description": "Parameter guard violation"}},
)
async def layout_svg(req: OpticalSpecRequest) -> LayoutSVG:
    """Render 2D optical path SVG via rayoptics.

    Wave 2 implementation.
    """
    _validate_or_400(req)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2 wave 2: rayoptics integration pending",
    )
