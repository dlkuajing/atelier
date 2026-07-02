"""Aberration analysis — Optiland-backed MTF + spot RMS + Airy disc.

Wave 2 of Phase 2 (continued). PSF and Zernike are deferred to v2 polish.
Geometric MTF is the workhorse for the v1 demo: a 256-point sagittal +
tangential curve per field, with the diffraction limit for comparison.

ECharts on the frontend consumes the flat shape:
    freq_lp_per_mm[256]     (shared X axis)
    fields[i].sagittal[256] (per-field curves)
    fields[i].tangential[256]
    diff_limited[256]
    airy_disc_diameter_um, cutoff_freq_lp_per_mm, rms_spot_radius_um[i]
"""

from __future__ import annotations

import warnings

import numpy as np
from pydantic import BaseModel, Field

from app.core.optical_calc import airy_disk_diameter_um

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from optiland import mtf as opt_mtf
    from optiland.optic import Optic


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class MTFFieldData(BaseModel):
    field_index: int = Field(..., ge=0)
    sagittal: list[float] = Field(..., description="Sagittal MTF values, one per freq point")
    tangential: list[float] = Field(..., description="Tangential MTF values, one per freq point")


class MTFResult(BaseModel):
    freq_lp_per_mm: list[float] = Field(..., description="Shared X axis — spatial frequency")
    fields: list[MTFFieldData]
    diff_limited: list[float] = Field(..., description="Diffraction-limited MTF (theoretical upper bound)")
    cutoff_freq_lp_per_mm: float = Field(..., description="Diffraction cutoff frequency")
    airy_disc_diameter_um: float = Field(..., description="Airy disc diameter at primary wavelength")
    rms_spot_radius_um_by_field: list[float] = Field(
        ..., description="RMS geometric spot radius per field, in microns"
    )


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------


# Vignette-robust metrology (E1-02). Production phone-lens edge fields vignette a
# large pupil fraction, and Optiland's ZMX reader drops vignette *decentering*
# (VDX/VDY) on ingest (keeps only compression VCX/VCY). The pupil grid therefore
# samples rays the physical lens would block; those trace to extreme positions and
# corrupt both the RMS (mean-square dominated by the tail) and the geometric MTF.
# Per field we drop non-finite rays and clip rays beyond median + k*MAD of the
# radius about the median centroid, so the surviving rays reflect the light that
# actually passes. Percentile clipping was rejected in the E1-02 threshold sweep
# (it left the artifact seeds at 3000+ um); the median/MAD estimator preserves the
# bulk spot and only trims the artifact tail.
_SPOT_MAD_CLIP_K = 5.0
_SPOT_MAD_SCALE = 1.4826  # normal-consistency: k is in robust sigma units
_SPOT_MIN_VALID_RAYS = 6


def _robust_clip_spot_data(geometric_mtf) -> None:
    """Trim vignette-artifact rays in a GeometricMTF's traced spot data in place.

    Both `rms_spot_radius()` and `_generate_mtf_data()` read the same per-field
    spot coordinates, so clipping here cleans the RMS and the MTF consistently.
    A fully-vignetted field (fewer than `_SPOT_MIN_VALID_RAYS` finite rays) keeps
    only its finite rays without further clipping — the near-dark edge is reported
    honestly rather than fabricated.
    """
    for field_data in geometric_mtf.data:
        for spot in field_data:
            x = np.asarray(spot.x, dtype=float)
            y = np.asarray(spot.y, dtype=float)
            finite = np.isfinite(x) & np.isfinite(y)
            if int(finite.sum()) < _SPOT_MIN_VALID_RAYS:
                keep = finite
            else:
                xf, yf = x[finite], y[finite]
                center_x, center_y = np.median(xf), np.median(yf)
                radius = np.hypot(x - center_x, y - center_y)
                radius_finite = radius[finite]
                median_r = np.median(radius_finite)
                mad = np.median(np.abs(radius_finite - median_r)) * _SPOT_MAD_SCALE
                threshold = median_r + _SPOT_MAD_CLIP_K * max(mad, 1e-12)
                keep = finite & (radius <= threshold)
                if int(keep.sum()) < _SPOT_MIN_VALID_RAYS:
                    keep = finite
            spot.x = x[keep]
            spot.y = y[keep]
            intensity = getattr(spot, "intensity", None)
            if intensity is not None:
                intensity_arr = np.asarray(intensity, dtype=float)
                if intensity_arr.shape == keep.shape:
                    spot.intensity = intensity_arr[keep]


def _to_list(arr) -> list[float]:
    """Coerce a numpy array (any shape) to a flat python list of floats."""
    return [float(x) for x in np.asarray(arr).flatten()]


def _scalar(value) -> float:
    """Coerce a (possibly array-of-1) numpy value to a float."""
    arr = np.asarray(value).flatten()
    return float(arr[0]) if arr.size > 0 else 0.0


def compute_mtf(
    optic: Optic, wavelength_nm: float = 550.0, num_rays: int = 32
) -> MTFResult:
    """Geometric MTF for every defined field, with diffraction limit overlay.

    `num_rays` controls the ray density in the entrance pupil grid; 32 is a
    good demo-quality default (256-point output, ~150ms on a 7-element optic).
    `wavelength_nm` flows from the Wizard's `OpticalSpecRequest` and is used
    to compute the analytic Airy disc diameter via our own verified formula
    (`app/core/optical_calc::airy_disk_diameter_um`) — we sidestep Optiland's
    `airy_radius(n_w, wavelength)` method to avoid coupling to its
    wavelength-indexing convention.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        m = opt_mtf.GeometricMTF(optic, num_rays=num_rays)
        # Drop vignette-artifact rays, then recompute the MTF from the cleaned
        # spot data (rms_spot_radius() below reads the same clipped data).
        _robust_clip_spot_data(m)
        m.mtf, m.diff_limited_mtf = m._generate_mtf_data()

    freq = _to_list(m.freq)
    mtf_arr = np.asarray(m.mtf)  # (n_fields, 2, n_freq) where 2 = (sagittal, tangential)

    if mtf_arr.ndim != 3 or mtf_arr.shape[1] != 2:
        raise RuntimeError(
            f"Unexpected MTF array shape from Optiland: {mtf_arr.shape}"
        )

    n_fields = mtf_arr.shape[0]

    # rms_spot_radius is a METHOD (not attr) — call it.
    rms_raw = np.asarray(m.rms_spot_radius()).flatten()

    fields_data: list[MTFFieldData] = []
    rms_per_field: list[float] = []
    for fi in range(n_fields):
        fields_data.append(
            MTFFieldData(
                field_index=fi,
                sagittal=[float(x) for x in mtf_arr[fi, 0, :]],
                tangential=[float(x) for x in mtf_arr[fi, 1, :]],
            )
        )
        # Optiland returns mm; frontend wants μm.
        rms_mm = float(rms_raw[fi]) if fi < rms_raw.size else 0.0
        rms_per_field.append(rms_mm * 1000.0)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        f_number = float(optic.paraxial.FNO())

    return MTFResult(
        freq_lp_per_mm=freq,
        fields=fields_data,
        diff_limited=_to_list(m.diff_limited_mtf),
        cutoff_freq_lp_per_mm=_scalar(m.cutoff_freq),
        airy_disc_diameter_um=airy_disk_diameter_um(wavelength_nm, f_number),
        rms_spot_radius_um_by_field=rms_per_field,
    )
