"""Wavefront RMS and Strehl metrics backed by Optiland wavefront analysis."""

from __future__ import annotations

import math
import warnings
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field

from app.core.provenance import ProvenanceSource

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland.optic import Optic
    from optiland.utils import resolve_fields, resolve_wavelengths
    from optiland.wavefront import OPD, Wavefront
    from optiland.zernike import ZernikeFit


ZernikeType = Literal["fringe", "standard", "noll"]


class WavefrontFieldMetric(BaseModel):
    """Wavefront quality metrics for one field at one wavelength."""

    field_index: int = Field(..., ge=0)
    field_coordinate: tuple[float, float] = Field(
        ...,
        description="Normalized Optiland field coordinate (Hx, Hy)",
    )
    field_fraction: float = Field(..., ge=0)
    wavelength_nm: float = Field(..., gt=0)
    rms_wavefront_error_waves: float = Field(
        ...,
        ge=0,
        description="RMS OPD in waves after configured piston/tilt removal",
    )
    strehl_ratio: float = Field(
        ...,
        ge=0,
        le=1,
        description="Marechal Strehl estimate exp(-(2*pi*RMS_waves)^2)",
    )
    valid_ray_count: int = Field(..., ge=1)
    zernike_type: ZernikeType
    zernike_coefficients_waves: list[float] = Field(
        default_factory=list,
        description="Optiland ZernikeFit coefficients over the same processed OPD samples",
    )


class WavefrontMetricsResult(BaseModel):
    """Serializable wavefront metrics for a single wavelength across fields."""

    provenance: ProvenanceSource = ProvenanceSource.OPTILAND_WAVEFRONT
    wavelength_nm: float = Field(..., gt=0)
    num_rays: int = Field(..., ge=2)
    distribution: str
    strategy: str
    remove_piston: bool
    remove_tilt: bool
    strehl_model: Literal["marechal"] = "marechal"
    fields: list[WavefrontFieldMetric]

    @property
    def max_rms_wavefront_error_waves(self) -> float | None:
        """Worst finite RMS wavefront error across fields."""
        values = [
            field.rms_wavefront_error_waves
            for field in self.fields
            if math.isfinite(field.rms_wavefront_error_waves)
        ]
        return max(values) if values else None

    @property
    def min_strehl_ratio(self) -> float | None:
        """Lowest finite Strehl estimate across fields."""
        values = [
            field.strehl_ratio for field in self.fields if math.isfinite(field.strehl_ratio)
        ]
        return min(values) if values else None


def strehl_from_rms_waves(rms_wavefront_error_waves: float) -> float:
    """Compute the Marechal Strehl estimate from RMS wavefront error in waves."""
    rms = float(rms_wavefront_error_waves)
    if not math.isfinite(rms) or rms < 0:
        raise ValueError("rms_wavefront_error_waves must be a finite non-negative value")
    exponent = -((2.0 * math.pi * rms) ** 2)
    if exponent < -745.0:
        return 0.0
    return float(math.exp(exponent))


def _wavelength_arg(wavelength_nm: float | None) -> str | list[float]:
    if wavelength_nm is None:
        return "primary"
    if wavelength_nm <= 0:
        raise ValueError("wavelength_nm must be positive")
    return [float(wavelength_nm) / 1000.0]


def _processed_opd(data, *, remove_piston: bool, remove_tilt: bool) -> tuple[np.ndarray, np.ndarray]:
    intensity = np.asarray(data.intensity, dtype=float).flatten()
    opd = np.asarray(data.opd, dtype=float).flatten()
    if opd.size == 0 or intensity.size == 0 or opd.shape != intensity.shape:
        raise RuntimeError("Optiland returned inconsistent wavefront OPD data")

    if remove_tilt:
        processed = np.asarray(
            Wavefront.fit_and_remove_tilt(data, remove_piston=remove_piston),
            dtype=float,
        ).flatten()
    else:
        processed = opd.copy()

    finite = np.isfinite(processed) & np.isfinite(intensity) & (intensity > 0)
    if not np.any(finite):
        raise RuntimeError("Optiland returned no valid wavefront rays")

    if remove_piston and not remove_tilt:
        processed[finite] = processed[finite] - float(np.mean(processed[finite]))
        finite = np.isfinite(processed) & np.isfinite(intensity) & (intensity > 0)
        if not np.any(finite):
            raise RuntimeError("Optiland returned no finite wavefront rays after piston removal")

    return processed, finite


def compute_wavefront_metrics(
    optic: Optic,
    *,
    fields: str | list[tuple[float, float]] = "all",
    wavelength_nm: float | None = None,
    num_rays: int = 12,
    distribution: str = "hexapolar",
    strategy: str = "chief_ray",
    remove_piston: bool = True,
    remove_tilt: bool = True,
    zernike_type: ZernikeType = "fringe",
    num_zernike_terms: int = 12,
) -> WavefrontMetricsResult:
    """Compute RMS wavefront error and Strehl ratio for every requested field."""
    if num_rays < 2:
        raise ValueError("num_rays must be at least 2")
    if num_zernike_terms < 0:
        raise ValueError("num_zernike_terms must be non-negative")

    resolved_fields = resolve_fields(optic, fields)
    resolved_wavelengths = resolve_wavelengths(optic, _wavelength_arg(wavelength_nm))
    if len(resolved_wavelengths) != 1:
        raise ValueError("compute_wavefront_metrics expects a single wavelength")
    wavelength_um = float(resolved_wavelengths[0].value)

    field_metrics: list[WavefrontFieldMetric] = []
    for field_index, field_point in enumerate(resolved_fields):
        field = (float(field_point.coord[0]), float(field_point.coord[1]))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            opd = OPD(
                optic,
                field=field,
                wavelength=wavelength_um,
                num_rays=num_rays,
                distribution=distribution,
                strategy=strategy,
                remove_tilt=False,
            )

        data = opd.get_data(opd.fields[0], opd.wavelengths[0])
        processed_opd, valid = _processed_opd(
            data,
            remove_piston=remove_piston,
            remove_tilt=remove_tilt,
        )
        valid_opd = processed_opd[valid]
        rms_waves = float(np.sqrt(np.mean(valid_opd**2)))

        zernike_coefficients: list[float] = []
        if num_zernike_terms > 0:
            pupil_x = np.asarray(opd.distribution.x, dtype=float).flatten()
            pupil_y = np.asarray(opd.distribution.y, dtype=float).flatten()
            if pupil_x.shape != valid.shape or pupil_y.shape != valid.shape:
                raise RuntimeError("Optiland returned inconsistent wavefront pupil data")
            fit = ZernikeFit(
                pupil_x[valid],
                pupil_y[valid],
                valid_opd,
                zernike_type,
                num_zernike_terms,
            )
            zernike_coefficients = [
                float(x) for x in np.asarray(fit.coeffs, dtype=float).flatten()
            ]

        field_metrics.append(
            WavefrontFieldMetric(
                field_index=field_index,
                field_coordinate=field,
                field_fraction=math.hypot(*field),
                wavelength_nm=wavelength_um * 1000.0,
                rms_wavefront_error_waves=rms_waves,
                strehl_ratio=strehl_from_rms_waves(rms_waves),
                valid_ray_count=int(valid.sum()),
                zernike_type=zernike_type,
                zernike_coefficients_waves=zernike_coefficients,
            )
        )

    return WavefrontMetricsResult(
        wavelength_nm=wavelength_um * 1000.0,
        num_rays=num_rays,
        distribution=distribution,
        strategy=strategy,
        remove_piston=remove_piston,
        remove_tilt=remove_tilt,
        fields=field_metrics,
    )
