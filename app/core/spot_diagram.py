"""Serializable spot diagram data backed by Optiland ray tracing."""

from __future__ import annotations

import math
import warnings
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from app.core.provenance import ProvenanceSource

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland.analysis.spot_diagram import SpotDiagram as OptilandSpotDiagram
    from optiland.optic import Optic


SpotCoordinates = Literal["global", "local"]
SpotReference = Literal["chief_ray", "centroid"]


class SpotWavelengthData(BaseModel):
    """Spot points for one field and one wavelength."""

    wavelength_index: int = Field(..., ge=0)
    wavelength_nm: float = Field(..., gt=0)
    x_um: list[float] = Field(..., description="Centered x image-plane intercepts")
    y_um: list[float] = Field(..., description="Centered y image-plane intercepts")
    intensity: list[float] = Field(..., description="Ray intensities from Optiland")
    rms_radius_um: float = Field(..., ge=0, description="RMS spot radius")
    geometric_radius_um: float = Field(..., ge=0, description="Maximum geometric radius")


class SpotFieldData(BaseModel):
    """Spot data and diffraction reference for one field."""

    field_index: int = Field(..., ge=0)
    field_coordinate: tuple[float, float] = Field(
        ...,
        description="Normalized Optiland field coordinate (Hx, Hy)",
    )
    field_fraction: float = Field(..., ge=0, description="Radial normalized field")
    airy_radius_x_um: float = Field(..., gt=0)
    airy_radius_y_um: float = Field(..., gt=0)
    spots_by_wavelength: list[SpotWavelengthData]


class SpotDiagramResult(BaseModel):
    """Multi-field, multi-wavelength spot diagram payload."""

    provenance: ProvenanceSource = ProvenanceSource.OPTILAND_RAYTRACE
    coordinates: SpotCoordinates
    reference: SpotReference
    distribution: str
    num_rings: int = Field(..., ge=1)
    airy_reference_wavelength_nm: float = Field(..., gt=0)
    fields: list[SpotFieldData]

    @property
    def field_count(self) -> int:
        """Number of fields in the payload."""
        return len(self.fields)

    @property
    def wavelength_count(self) -> int:
        """Number of wavelengths per field."""
        return len(self.fields[0].spots_by_wavelength) if self.fields else 0


def _to_finite_array(value, *, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float).flatten()
    if arr.size == 0:
        raise RuntimeError(f"Optiland returned an empty {name} array")
    if not np.all(np.isfinite(arr)):
        raise RuntimeError(f"Optiland returned non-finite {name} values")
    return arr


def _to_float_list(value, *, name: str) -> list[float]:
    return [float(x) for x in _to_finite_array(value, name=name)]


def _spot_radius_um(value, *, name: str) -> float:
    arr = _to_finite_array(value, name=name)
    return float(arr[0]) * 1000.0


def _wavelength_arg(wavelengths_nm: list[float] | None) -> str | list[float]:
    if wavelengths_nm is None:
        return "all"
    if not wavelengths_nm:
        raise ValueError("wavelengths_nm must not be empty")
    if any(wavelength_nm <= 0 for wavelength_nm in wavelengths_nm):
        raise ValueError("wavelengths_nm values must be positive")
    return [float(wavelength_nm) / 1000.0 for wavelength_nm in wavelengths_nm]


def _airy_reference_wavelength_um(analysis: OptilandSpotDiagram) -> float:
    try:
        return float(analysis.optic.primary_wavelength)
    except Exception:
        return float(analysis.wavelengths[0].value)


def compute_spot_diagram(
    optic: Optic,
    *,
    fields: str | list[tuple[float, float]] = "all",
    wavelengths_nm: list[float] | None = None,
    num_rings: int = 6,
    distribution: str = "hexapolar",
    coordinates: SpotCoordinates = "local",
    reference: SpotReference = "chief_ray",
) -> SpotDiagramResult:
    """Compute centered spot points for every requested field and wavelength.

    Coordinates are returned in microns and centered using Optiland's native
    spot-diagram reference strategy. `wavelengths_nm=None` uses all wavelengths
    defined on the optic; explicit wavelengths are supplied in nanometres and
    converted to the micrometre unit expected by Optiland.
    """
    if num_rings < 1:
        raise ValueError("num_rings must be at least 1")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        analysis = OptilandSpotDiagram(
            optic,
            fields=fields,
            wavelengths=_wavelength_arg(wavelengths_nm),
            num_rings=num_rings,
            distribution=distribution,
            coordinates=coordinates,
            reference=reference,
        )

    centered = analysis._center_spots(analysis.data)
    rms_radius_mm = analysis.rms_spot_radius()
    geometric_radius_mm = analysis.geometric_spot_radius()
    airy_wavelength_um = _airy_reference_wavelength_um(analysis)
    airy_x_mm, airy_y_mm = analysis.airy_disc_x_y(wavelength=airy_wavelength_um)

    if not analysis.fields:
        raise RuntimeError("Optiland returned no spot fields")
    if len(airy_x_mm) != len(analysis.fields) or len(airy_y_mm) != len(analysis.fields):
        raise RuntimeError("Optiland returned inconsistent Airy radius counts")

    field_payloads: list[SpotFieldData] = []
    for field_index, field_data in enumerate(centered):
        if len(field_data) != len(analysis.wavelengths):
            raise RuntimeError("Optiland returned inconsistent spot wavelength counts")

        coord = analysis.fields[field_index].coord
        field_fraction = math.hypot(float(coord[0]), float(coord[1]))
        wavelength_payloads: list[SpotWavelengthData] = []
        for wavelength_index, spot_data in enumerate(field_data):
            x_um = _to_finite_array(spot_data.x, name="spot x") * 1000.0
            y_um = _to_finite_array(spot_data.y, name="spot y") * 1000.0
            intensity = _to_float_list(spot_data.intensity, name="spot intensity")
            if not (x_um.size == y_um.size == len(intensity)):
                raise RuntimeError("Optiland returned inconsistent spot point counts")

            wavelength_payloads.append(
                SpotWavelengthData(
                    wavelength_index=wavelength_index,
                    wavelength_nm=float(analysis.wavelengths[wavelength_index].value) * 1000.0,
                    x_um=[float(x) for x in x_um],
                    y_um=[float(y) for y in y_um],
                    intensity=intensity,
                    rms_radius_um=_spot_radius_um(
                        rms_radius_mm[field_index][wavelength_index],
                        name="RMS spot radius",
                    ),
                    geometric_radius_um=_spot_radius_um(
                        geometric_radius_mm[field_index][wavelength_index],
                        name="geometric spot radius",
                    ),
                )
            )

        field_payloads.append(
            SpotFieldData(
                field_index=field_index,
                field_coordinate=(float(coord[0]), float(coord[1])),
                field_fraction=field_fraction,
                airy_radius_x_um=_spot_radius_um(
                    airy_x_mm[field_index],
                    name="Airy x radius",
                ),
                airy_radius_y_um=_spot_radius_um(
                    airy_y_mm[field_index],
                    name="Airy y radius",
                ),
                spots_by_wavelength=wavelength_payloads,
            )
        )

    return SpotDiagramResult(
        coordinates=coordinates,
        reference=reference,
        distribution=distribution,
        num_rings=num_rings,
        airy_reference_wavelength_nm=airy_wavelength_um * 1000.0,
        fields=field_payloads,
    )
