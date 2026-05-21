"""Optical computation endpoints — Optiland / prysm / rayoptics wrappers.

Phase 0: placeholder routes returning 501. Real Optiland integration in Phase 2.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


router = APIRouter()


class RayTraceRequest(BaseModel):
    scenario: str = Field(..., description="e.g. 'smartphone-telephoto', 'ar-near-eye'")
    focal_length_mm: float = Field(..., gt=0)
    f_number: float = Field(..., gt=0)
    field_of_view_deg: float = Field(..., gt=0)
    image_height_mm: float = Field(..., gt=0)
    n_elements: int | None = Field(None, ge=2, le=20)


@router.post("/raytrace", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def raytrace(req: RayTraceRequest) -> dict:
    """Run optical ray trace via Optiland and return lens layout + ray paths.

    Phase 2 implementation. Currently returns 501.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: Optiland integration pending",
    )


@router.post("/aberration", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def aberration(req: RayTraceRequest) -> dict:
    """Compute MTF / PSF / Zernike via prysm.

    Phase 2 implementation.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: prysm integration pending",
    )


@router.post("/layout-svg", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def layout_svg(req: RayTraceRequest) -> dict:
    """Render 2D optical path SVG via rayoptics.

    Phase 2 implementation.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 2: rayoptics integration pending",
    )
