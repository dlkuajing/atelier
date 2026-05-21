"""Lens system data model — pydantic schema for the Wizard's output and the
Optical Engine's input.

This is the *contract* between:
- LLM (produces LensAssembly JSON from Wizard answers, via GPT-5.5 structured output)
- Optiland engine (consumes LensAssembly, returns RayTraceResult)
- Frontend visualization (consumes RayTraceResult + RenderedLayout)

The contract is deterministic and strongly typed. The LLM may *propose*
LensAssembly values; the Optical Engine *validates* and *computes*. Critical
parameters never come from an LLM estimate — they come from formulas or from
Optiland's real ray trace.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


class Scenario(StrEnum):
    """First-class scenarios the Wizard offers. Each one carries
    scenario-specific parameter bounds (see parameter_guards.py)."""

    SMARTPHONE_TELEPHOTO = "smartphone-telephoto"
    SMARTPHONE_WIDE = "smartphone-wide"
    SMARTPHONE_ULTRAWIDE = "smartphone-ultrawide"
    AR_NEAR_EYE = "ar-near-eye"
    DSLR_PRIME = "dslr-prime"
    MICROSCOPE_OBJECTIVE = "microscope-objective"


# ---------------------------------------------------------------------------
# Surface geometry
# ---------------------------------------------------------------------------


class SurfaceType(StrEnum):
    SPHERICAL = "spherical"
    ASPHERIC = "aspheric"
    PLANE = "plane"
    APERTURE = "aperture"


class LensSurface(BaseModel):
    """A single optical surface (front or back of a lens element, or an aperture stop)."""

    surface_index: int = Field(..., ge=0, description="0-based index from object side")
    surface_type: SurfaceType
    radius_mm: float = Field(
        ...,
        description="Radius of curvature. Positive = center of curvature on image side. 0 or +inf = plane.",
    )
    thickness_mm: float = Field(
        ..., ge=0, description="Axial distance to next surface (mm)"
    )
    semi_diameter_mm: float = Field(..., gt=0, description="Clear aperture semi-diameter (mm)")
    conic: float = Field(0.0, description="Conic constant for aspheric (0 = sphere)")
    # Aspheric polynomial coefficients (4th, 6th, 8th, 10th order). Empty for spherical.
    aspheric_coeffs: list[float] = Field(default_factory=list)
    # Material to the right of this surface (between this and next). None = air.
    material_name: str | None = Field(
        None, description="Glass name (e.g. 'N-BK7', 'N-SF11', 'air')"
    )
    is_stop: bool = Field(False, description="True if this surface is the aperture stop")


class LensElement(BaseModel):
    """A single lens element = two surfaces + a glass material between them."""

    element_index: int = Field(..., ge=0)
    front_surface: LensSurface
    back_surface: LensSurface
    glass_name: str = Field(..., description="Glass type for this element")

    @model_validator(mode="after")
    def _surfaces_adjacent(self) -> LensElement:
        if self.back_surface.surface_index != self.front_surface.surface_index + 1:
            raise ValueError(
                f"back_surface.surface_index ({self.back_surface.surface_index}) "
                f"must equal front_surface.surface_index + 1 "
                f"({self.front_surface.surface_index + 1})"
            )
        return self


# ---------------------------------------------------------------------------
# Lens assembly (the Wizard output)
# ---------------------------------------------------------------------------


class LensAssembly(BaseModel):
    """The full optical prescription. This is what the LLM produces and what
    the Optical Engine consumes."""

    scenario: Scenario
    name: str = Field(..., description="Human-readable name, e.g. '7mm f/2.4 phone tele'")

    # Top-level paraxial specs — these come from deterministic formulas, not LLM estimates
    effective_focal_length_mm: float = Field(..., gt=0)
    f_number: float = Field(..., gt=0)
    field_of_view_deg: float = Field(..., gt=0, le=180)
    image_height_mm: float = Field(..., gt=0)
    wavelength_nm: float = Field(550.0, gt=0)

    # Optional but useful for downstream computations
    object_distance_mm: float | None = Field(
        None,
        description="Object plane distance (None = infinity for landscape)",
    )

    # Constituent elements
    elements: list[LensElement] = Field(..., min_length=1, max_length=20)

    # Aperture stop location (which element's surface)
    aperture_stop_surface_index: int = Field(
        ..., ge=0, description="surface_index of the aperture stop"
    )

    @model_validator(mode="after")
    def _validate(self) -> LensAssembly:
        # Element indices must be 0..N-1 and contiguous
        for i, el in enumerate(self.elements):
            if el.element_index != i:
                raise ValueError(
                    f"elements[{i}].element_index must be {i}, got {el.element_index}"
                )

        # Surface indices must be contiguous across elements
        expected_surface = 0
        for el in self.elements:
            if el.front_surface.surface_index != expected_surface:
                raise ValueError(
                    f"element {el.element_index}: front_surface.surface_index "
                    f"must be {expected_surface}, got {el.front_surface.surface_index}"
                )
            expected_surface = el.back_surface.surface_index + 1

        # Aperture stop must exist on a real surface
        max_surface_index = self.elements[-1].back_surface.surface_index
        if not 0 <= self.aperture_stop_surface_index <= max_surface_index:
            raise ValueError(
                f"aperture_stop_surface_index {self.aperture_stop_surface_index} "
                f"out of range [0, {max_surface_index}]"
            )

        # f/# ≥ 1.0 — F# < 1 is theoretically impossible for a single optical channel
        if self.f_number < 1.0:
            raise ValueError(f"f_number must be ≥ 1.0, got {self.f_number}")

        return self

    @property
    def n_elements(self) -> int:
        return len(self.elements)

    @property
    def n_surfaces(self) -> int:
        return self.elements[-1].back_surface.surface_index + 1

    @property
    def aperture_diameter_mm(self) -> float:
        """Entrance pupil diameter = EFL / f_number."""
        return self.effective_focal_length_mm / self.f_number


# ---------------------------------------------------------------------------
# Ray trace result (what Optical Engine returns)
# ---------------------------------------------------------------------------


class RayPath(BaseModel):
    """A single ray's path through the system."""

    ray_id: str
    wavelength_nm: float
    field_angle_deg: float
    # Sampled (x, z) positions along the axial direction
    points_mm: list[tuple[float, float]]
    # Did the ray reach the image plane successfully?
    reaches_image: bool


class RayTraceResult(BaseModel):
    """Output of the Optical Engine's ray trace."""

    assembly_name: str
    n_rays: int
    # Sampled ray paths (subset of all rays for visualization — usually 5-15)
    sampled_paths: list[RayPath]
    # Per-field RMS spot radius (μm) at sampled field angles
    rms_spot_radius_um: dict[float, float] = Field(
        default_factory=dict, description="field_angle_deg → RMS spot radius (μm)"
    )
    # Did any ray fail to reach the image plane?
    has_vignetting: bool = False


# ---------------------------------------------------------------------------
# Visualization layout (what rayoptics renders for SVG)
# ---------------------------------------------------------------------------


class LayoutSVG(BaseModel):
    """SVG layout output."""

    format: Literal["svg"] = "svg"
    width_px: int = Field(..., gt=0)
    height_px: int = Field(..., gt=0)
    svg_content: str = Field(..., description="Raw SVG string")
