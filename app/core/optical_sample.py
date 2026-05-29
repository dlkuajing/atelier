"""OpticalSampleData composite model + per-case metadata (phase v2-02).

Mirrors the frontend contract in `src/app/[locale]/agent/_data/types.ts`. The
five-piece payload (paraxial / surfaces / trace / mtf / layout_svg) reuses the
existing backend models; `CaseMetadata` is new — honest provenance for each
real design (piece count, imaging-vs-filter split, materials, EFL accuracy).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.aberration import MTFResult
from app.core.lens_system import LayoutSVG, RayTraceResult, Scenario
from app.core.optical_engine import ParaxialSummary, SurfaceDescriptor


class CaseMetadata(BaseModel):
    """Honest provenance for one real design (BRIEF principle 3)."""

    case_id: str = Field(..., description="Source zmx filename without extension")
    source_zmx: str = Field(..., description="Original zmx filename")
    scenario: Scenario = Field(..., description="smartphone-wide / smartphone-ultrawide")
    n_pieces: int = Field(..., description="Imaging element count from filename (NP prefix)")
    n_imaging: int = Field(..., description="Imaging lens elements detected (curved, glass)")
    n_filter: int = Field(..., description="Flat IR-filter / cover-glass plates")
    materials: list[str] = Field(..., description="Distinct real material names used (datasheet)")
    fov_deg: float = Field(..., description="Nominal full FOV from the manifest")
    nominal_efl_mm: float = Field(..., description="Design-nominal EFL from filename")
    computed_efl_mm: float = Field(..., description="Optiland-recomputed EFL")
    efl_error_pct: float = Field(..., description="abs(computed-nominal)/nominal*100")
    mtf_max_field_frac: float = Field(
        1.0,
        description=(
            "Max field fraction MTF was computed to. <1.0 means full-field "
            "ray-aiming hit NaN and we fell back to a smaller field set."
        ),
    )


class OpticalSampleData(BaseModel):
    """Full per-design payload the /agent frontend consumes (types.ts mirror)."""

    paraxial: ParaxialSummary
    surfaces: list[SurfaceDescriptor]
    trace: RayTraceResult
    mtf: MTFResult
    layout_svg: LayoutSVG
    # Optional for backward-compat: pre-v2-02 consumers don't pass metadata.
    metadata: CaseMetadata | None = None
