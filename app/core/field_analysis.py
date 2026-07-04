"""Field curvature and distortion curve data from Optiland ray tracing."""

from __future__ import annotations

import warnings
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from app.core.provenance import ProvenanceSource

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland.analysis import Distortion, FieldCurvature
    from optiland.optic import Optic


DistortionModel = Literal["f-tan", "f-theta"]


class FieldAnalysisResult(BaseModel):
    """Serializable field curvature and distortion curves for one wavelength."""

    provenance: ProvenanceSource = ProvenanceSource.OPTILAND_RAYTRACE
    field_fraction: list[float] = Field(..., description="Normalized field axis, 0 to 1")
    field_coordinate: list[float] = Field(
        ...,
        description="Field coordinate in field_unit, from axis to optic.fields.max_field",
    )
    field_unit: str = Field(
        ...,
        description="Unit of field_coordinate; angle fields use degrees",
    )
    wavelength_nm: float = Field(..., gt=0)
    distortion_model: DistortionModel = "f-tan"
    tangential_field_curvature_mm: list[float] = Field(
        ..., description="Tangential/meridional field curvature image-plane delta"
    )
    sagittal_field_curvature_mm: list[float] = Field(
        ..., description="Sagittal field curvature image-plane delta"
    )
    distortion_pct: list[float] = Field(..., description="Distortion relative to ideal image height")


def _to_float_list(value, *, name: str) -> list[float]:
    arr = np.asarray(value, dtype=float).flatten()
    if arr.size == 0:
        raise RuntimeError(f"Optiland returned an empty {name} curve")
    if not np.all(np.isfinite(arr)):
        raise RuntimeError(f"Optiland returned non-finite {name} values")
    return [float(x) for x in arr]


def _field_unit(optic: Optic) -> str:
    field_definition = getattr(optic.fields, "field_definition", None)
    class_name = field_definition.__class__.__name__ if field_definition is not None else ""
    return {
        "AngleField": "deg",
        "ObjectHeightField": "mm_object_height",
        "ParaxialImageHeightField": "mm_paraxial_image_height",
        "RealImageHeightField": "mm_real_image_height",
    }.get(class_name, "field_coordinate")


def _analysis_wavelength_arg(wavelength_nm: float | None) -> str | list[float]:
    if wavelength_nm is None:
        return "primary"
    if wavelength_nm <= 0:
        raise ValueError("wavelength_nm must be positive")
    # Optiland analysis APIs take raw wavelength lists in micrometres.
    return [float(wavelength_nm) / 1000.0]


def _resolved_wavelength_nm(analysis) -> float:
    return float(analysis.wavelengths[0].value) * 1000.0


def compute_field_analysis(
    optic: Optic,
    *,
    wavelength_nm: float | None = None,
    num_points: int = 128,
    distortion_model: DistortionModel = "f-tan",
) -> FieldAnalysisResult:
    """Compute field curvature and distortion curves for the optic's current fields.

    The optic's field definition is treated as the source of truth. Real ZMX
    phone designs should be converted to angle fields first with
    `regularize_fields_to_angle()` so Optiland avoids the slow RealImageHeight
    inverse-solve path.
    """
    if num_points < 2:
        raise ValueError("num_points must be at least 2")

    max_field = float(optic.fields.max_field)
    if max_field <= 0:
        raise ValueError("optic must define a positive max field")

    wavelengths = _analysis_wavelength_arg(wavelength_nm)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        curvature = FieldCurvature(optic, wavelengths=wavelengths, num_points=num_points)
        distortion = Distortion(
            optic,
            wavelengths=wavelengths,
            num_points=num_points,
            distortion_type=distortion_model,
        )

    tangential = _to_float_list(curvature.data[0][0], name="tangential field curvature")
    sagittal = _to_float_list(curvature.data[0][1], name="sagittal field curvature")
    distortion_pct = _to_float_list(distortion.data[0], name="distortion")

    if not (len(tangential) == len(sagittal) == len(distortion_pct) == num_points):
        raise RuntimeError("Optiland returned inconsistent field analysis curve lengths")

    fractions = [float(x) for x in np.linspace(0.0, 1.0, num_points)]
    coordinates = [float(max_field * fraction) for fraction in fractions]

    return FieldAnalysisResult(
        field_fraction=fractions,
        field_coordinate=coordinates,
        field_unit=_field_unit(optic),
        wavelength_nm=_resolved_wavelength_nm(curvature),
        distortion_model=distortion_model,
        tangential_field_curvature_mm=tangential,
        sagittal_field_curvature_mm=sagittal,
        distortion_pct=distortion_pct,
    )
