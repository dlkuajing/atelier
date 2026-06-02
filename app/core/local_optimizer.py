"""Guarded Optiland local-optimization probe for real phone-camera seeds.

This does not replace the selected seed payload. It runs a tightly scoped,
auditable first-order EFL refinement attempt on the source zmx and returns
evidence: either a safe radius-tweak proposal, or a diagnostic explaining why
the optimizer was not trustworthy for this seed/target.
"""

from __future__ import annotations

import math
import time
import warnings
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
from itertools import combinations

import numpy as np
from optiland.optimization import LeastSquares, OptimizationProblem
from optiland.solves.thickness import ChiefRayHeightThicknessSolve

from app.core.aberration import compute_mtf
from app.core.image_quality_floor import image_quality_floor_gap_score
from app.core.mtf_fields import MTF_FIELD_FALLBACK_SETS, format_mtf_field_fraction
from app.core.optical_engine import compute_paraxial_summary, trace_optic
from app.core.optical_sample import (
    EdgeFieldStabilityPoint,
    FullFieldRecoveryTrial,
    OptimizationAttempt,
    OptimizationMeritProbe,
    OptimizationMetricSnapshot,
    OptimizationVariableCandidate,
    OptimizationVariableChange,
    OptimizationVariableTrial,
    OptimizationVerification,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx, regularize_fields_to_angle

_PRIMARY_WL_NM = 587.6
_PRIMARY_WL_UM = _PRIMARY_WL_NM / 1000.0
_RADIUS_BOUND_FRAC = 0.05
_MERIT_RADIUS_BOUND_FRAC = 0.02
_MERIT_THICKNESS_BOUND_FRAC = 0.05
_MERIT_MIN_THICKNESS_MM = 0.025
_MAX_SURFACES_TO_TRY = 8
_MAX_OPTIMIZER_ITER = 8
_MAX_MERIT_SURFACES_TO_TRY = 4
_MAX_MERIT_THICKNESSES_TO_TRY = 4
_MAX_ASPHERE_CANDIDATES_TO_REPORT = 8
_MAX_ASPHERE_PRESCREEN_TRIALS = 16
_MAX_ASPHERE_AUDIT_CANDIDATES_TO_VERIFY = 2
_MAX_ASPHERE_AUDIT_TRIALS = 4
_MAX_JOINT_ASPHERE_AUDIT_TRIALS = 2
_MAX_COMPOUND_MERIT_VARIABLES = 3
_COMPOUND_MERIT_MIN_EXTRA_RMS_UM = 0.10
_ASPHERE_AUDIT_STEP_FRACTIONS: tuple[float, ...] = (1.0, 0.125)
_ASPHERE_AUDIT_BOUND_FRAC = 0.10
_ASPHERE_AUDIT_APERTURE_MM = 1.0
_ASPHERE_AUDIT_MAX_EDGE_SAG_DELTA_UM = 5.0
_ASPHERE_AUDIT_MAX_EDGE_SLOPE_DELTA_MRAD = 20.0
_ASPHERE_AUDIT_MIN_HALF_WIDTH = 1e-12
_MAX_MERIT_OPTIMIZER_ITER = 6
_MERIT_FIELD_SAMPLES: tuple[float, ...] = (0.0, 0.2, 0.3, 0.4)
_MERIT_OPD_WEIGHT = 0.05
_MERIT_OPD_FIELD_WEIGHTED_THRESHOLD = 0.035
_OPD_ASSISTED_MERIT_PURPOSES = {"image_quality_floor_recovery", "replay_gate_remediation"}
_STOP_POSITION_REPLAY_PURPOSES = {"image_quality_floor_recovery", "replay_gate_remediation"}
_FOCUS_POSITION_REPLAY_PURPOSES = {"image_quality_floor_recovery", "replay_gate_remediation"}
_COMPOUND_CONTINUATION_PURPOSES = {"replay_gate_remediation"}
_MAX_COMPOUND_CONTINUATION_FOCUS_TRIALS = 2
_MAX_COMPOUND_CONTINUATION_RADIUS_SURFACES = 2
_COMPOUND_CONTINUATION_RADIUS_DELTAS: tuple[float, ...] = (0.005, 0.010)
_MERIT_STOP_POSITION_DELTAS_MM: tuple[float, ...] = (
    -0.24,
    -0.16,
    -0.08,
    0.08,
    0.16,
    0.24,
)
_MERIT_FOCUS_POSITION_DELTAS_MM: tuple[float, ...] = (
    -0.30,
    -0.26,
    -0.22,
    -0.20,
    -0.18,
    -0.14,
    -0.10,
    -0.08,
    -0.06,
    -0.04,
    0.10,
    0.20,
)
_MTF_BANDS_LPMM: tuple[float, ...] = (50.0, 100.0, 150.0, 200.0, 250.0)
_MTF_BAND_WEIGHTS: tuple[float, ...] = (0.18, 0.24, 0.24, 0.20, 0.14)
_MTF_NON_REGRESSION_TOL = 0.002
_FULL_FIELD_STOP_DELTAS_MM: tuple[float, ...] = (-0.08, -0.04, 0.04, 0.08)
_FULL_FIELD_CHIEF_RAY_HEIGHT_DELTAS: tuple[float, ...] = (-0.10, 0.50)
_FULL_FIELD_MAX_CHIEF_RAY_Z_SHIFT_MM = 0.20
_FULL_FIELD_COMPOUND_EXTENSION_TRIALS: tuple[tuple[tuple[str, int, float], ...], ...] = (
    (("thickness", 6, -0.03), ("radius_pct", 9, 0.20), ("thickness", 12, 0.02)),
    (("thickness", 6, -0.03), ("radius_pct", 9, 0.20), ("thickness", 12, 0.04)),
    (("thickness", 6, -0.12), ("radius_pct", 9, 0.05)),
    (("thickness", 6, -0.12), ("radius_pct", 9, 0.02)),
    (("thickness", 6, -0.12), ("thickness", 5, -0.04)),
    (("thickness", 6, -0.12), ("stop_position", 2, -0.04)),
)
_EDGE_FIELD_SCAN_FRACS: tuple[float, ...] = (0.80, 0.85, 0.90, 0.95, 1.0)
_FLOOR_GAP_PROMOTION_WEIGHT = 10.0
_VARIABLE_PRIORITY_ALIASES = {
    "air gap": "thickness",
    "air gaps": "thickness",
    "thickness": "thickness",
    "radius": "radius",
    "radii": "radius",
    "stop position": "stop_position",
    "focus position": "focus_position",
    "image plane": "focus_position",
    "image plane position": "focus_position",
    "back focal distance": "focus_position",
    "asphere coefficient": "asphere_coefficient",
    "asphere coefficients": "asphere_coefficient",
    "field weighting": "field_weighting",
}


@dataclass(frozen=True)
class MtfBandMetrics:
    """Conservative MTF summary across the phone-camera review bands."""

    min_50: float | None = None
    avg_50: float | None = None
    min_100: float | None = None
    avg_100: float | None = None
    min_150: float | None = None
    avg_150: float | None = None
    min_200: float | None = None
    avg_200: float | None = None
    min_250: float | None = None
    avg_250: float | None = None
    multiband_min_score: float | None = None
    field_weighted_score: float | None = None

    @property
    def min_values(self) -> tuple[float | None, ...]:
        return (self.min_50, self.min_100, self.min_150, self.min_200, self.min_250)


@dataclass(frozen=True)
class AsphereAuditGuard:
    bounds: tuple[float, float]
    power: int
    aperture_mm: float
    edge_sag_delta_um: float
    edge_slope_delta_mrad: float
    status: str


@dataclass(frozen=True)
class AsphereAuditPrescreen:
    candidate: OptimizationVariableCandidate
    target_value: float
    merit_before: float
    merit_after: float
    merit_improvement: float
    field_samples: tuple[float, ...]


def _finite_float(value: object) -> float | None:
    try:
        out = float(np.asarray(value).flatten()[0])
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _candidate_radius_surfaces(source_zmx: str) -> list[int]:
    optic = _load_probe_optic(source_zmx, None)
    radii = np.asarray(optic.surfaces.radii).flatten()
    candidates: list[int] = []
    for idx, raw in enumerate(radii):
        value = _finite_float(raw)
        if value is None:
            continue
        if idx == 0 or idx == len(radii) - 1:
            continue
        if abs(value) < 0.05 or abs(value) > 1e4:
            continue
        candidates.append(idx)
    return candidates[:_MAX_SURFACES_TO_TRY]


def _surface_thickness(optic, surface_index: int) -> float | None:
    try:
        return _finite_float(optic.surfaces.get_thickness(surface_index))
    except Exception:
        return None


def _candidate_air_gap_surfaces(source_zmx: str) -> list[int]:
    optic = _load_probe_optic(source_zmx, None)
    radii = np.asarray(optic.surfaces.radii).flatten()
    curved: list[int] = []
    for idx, raw in enumerate(radii):
        value = _finite_float(raw)
        if value is None:
            continue
        if idx == 0 or idx == len(radii) - 1:
            continue
        if abs(value) < 0.05 or abs(value) > 1e4:
            continue
        curved.append(idx)

    candidates: list[int] = []
    for idx in curved[1::2]:
        thickness = _surface_thickness(optic, idx)
        if thickness is None:
            continue
        if thickness <= _MERIT_MIN_THICKNESS_MM or thickness > 2.0:
            continue
        candidates.append(idx)
    return candidates[:_MAX_MERIT_THICKNESSES_TO_TRY]


def _candidate_stop_position(optic) -> OptimizationVariableCandidate | None:
    stop_idx = _stop_surface_index(optic)
    if stop_idx is None:
        return None
    before = _surface_thickness(optic, stop_idx)
    if before is None:
        return _variable_candidate(
            variable="stop_position",
            surface_index=stop_idx,
            before=None,
            bounds=None,
            status="skipped",
            reason="stop surface thickness is non-finite",
        )
    trial_values = [before + delta for delta in _MERIT_STOP_POSITION_DELTAS_MM]
    return _variable_candidate(
        variable="stop_position",
        surface_index=stop_idx,
        before=before,
        bounds=(min(trial_values), max(trial_values)),
        status="eligible",
        reason="stop position allowed for guarded replay within +/-0.24 mm",
    )


def _candidate_focus_position(optic) -> OptimizationVariableCandidate | None:
    focus_idx = _image_surface_index(optic) - 1
    if focus_idx < 0:
        return None
    before = _surface_thickness(optic, focus_idx)
    if before is None:
        return _variable_candidate(
            variable="focus_position",
            surface_index=focus_idx,
            before=None,
            bounds=None,
            status="skipped",
            reason="image-plane compensation thickness is non-finite",
        )
    trial_values = [
        before + delta
        for delta in _MERIT_FOCUS_POSITION_DELTAS_MM
        if before + delta > _MERIT_MIN_THICKNESS_MM
    ]
    if not trial_values:
        return _variable_candidate(
            variable="focus_position",
            surface_index=focus_idx,
            before=before,
            bounds=None,
            status="skipped",
            reason="image-plane compensation bounds would cross minimum thickness",
        )
    return _variable_candidate(
        variable="focus_position",
        surface_index=focus_idx,
        before=before,
        bounds=(min(trial_values), max(trial_values)),
        status="eligible",
        reason="image-plane refocus allowed for guarded floor recovery replay",
    )


def _variable_candidate(
    *,
    variable: str,
    surface_index: int,
    before: float | None,
    bounds: tuple[float, float] | None,
    status: str,
    reason: str,
    coefficient_index: int | None = None,
    asphere_power: int | None = None,
    audit_aperture_mm: float | None = None,
    edge_sag_delta_um: float | None = None,
    edge_slope_delta_mrad: float | None = None,
    manufacturability_status: str | None = None,
) -> OptimizationVariableCandidate:
    return OptimizationVariableCandidate(
        variable=variable,
        surface_index=surface_index,
        coefficient_index=coefficient_index,
        before=before,
        min_value=bounds[0] if bounds is not None else None,
        max_value=bounds[1] if bounds is not None else None,
        status=status,
        reason=reason,
        asphere_power=asphere_power,
        audit_aperture_mm=audit_aperture_mm,
        edge_sag_delta_um=edge_sag_delta_um,
        edge_slope_delta_mrad=edge_slope_delta_mrad,
        manufacturability_status=manufacturability_status,
    )


def _bounded_variable_candidate(
    optic,
    *,
    variable: str,
    surface_index: int,
    merit: bool,
) -> OptimizationVariableCandidate:
    before = _variable_value(optic, variable, surface_index)
    if before is None:
        return _variable_candidate(
            variable=variable,
            surface_index=surface_index,
            before=None,
            bounds=None,
            status="skipped",
            reason="current value is non-finite",
        )

    bounds = (
        _bounded_merit_variable(variable, before)
        if merit
        else (_bounded_radius(before) if variable == "radius" else None)
    )
    if bounds is None:
        return _variable_candidate(
            variable=variable,
            surface_index=surface_index,
            before=before,
            bounds=None,
            status="skipped",
            reason="bounded search interval could not be formed",
        )

    if merit:
        reason = (
            "curved radius allowed for RMS merit probe within +/-2%"
            if variable == "radius"
            else "air-gap thickness allowed for RMS merit probe within +/-5%"
        )
    else:
        reason = "curved radius allowed for EFL refinement within +/-5%"
    return _variable_candidate(
        variable=variable,
        surface_index=surface_index,
        before=before,
        bounds=bounds,
        status="eligible",
        reason=reason,
    )


def _asphere_power(coefficient_index: int) -> int:
    return 2 * (coefficient_index + 1)


def _asphere_audit_guard(value: float, coefficient_index: int) -> AsphereAuditGuard:
    power = _asphere_power(coefficient_index)
    aperture = _ASPHERE_AUDIT_APERTURE_MM
    frac_width = abs(value) * _ASPHERE_AUDIT_BOUND_FRAC
    sag_limited_width = _ASPHERE_AUDIT_MAX_EDGE_SAG_DELTA_UM / 1000.0 / (aperture**power)
    slope_limited_width = (_ASPHERE_AUDIT_MAX_EDGE_SLOPE_DELTA_MRAD / 1000.0) / (
        power * (aperture ** (power - 1))
    )
    half_width = max(
        min(frac_width, sag_limited_width, slope_limited_width),
        _ASPHERE_AUDIT_MIN_HALF_WIDTH,
    )
    lo = value - half_width
    hi = value + half_width
    edge_sag_delta_um = half_width * (aperture**power) * 1000.0
    edge_slope_delta_mrad = half_width * power * (aperture ** (power - 1)) * 1000.0
    status = (
        "guarded"
        if edge_sag_delta_um <= _ASPHERE_AUDIT_MAX_EDGE_SAG_DELTA_UM
        and edge_slope_delta_mrad <= _ASPHERE_AUDIT_MAX_EDGE_SLOPE_DELTA_MRAD
        else "over_guard"
    )
    return AsphereAuditGuard(
        bounds=(lo, hi) if lo < hi else (hi, lo),
        power=power,
        aperture_mm=aperture,
        edge_sag_delta_um=edge_sag_delta_um,
        edge_slope_delta_mrad=edge_slope_delta_mrad,
        status=status,
    )


def _candidate_asphere_coefficients(source_zmx: str) -> list[OptimizationVariableCandidate]:
    optic = _load_probe_optic(source_zmx, None)
    candidates: list[OptimizationVariableCandidate] = []
    for surface_index, surface in enumerate(optic.surfaces.surfaces):
        geometry = getattr(surface, "geometry", None)
        coefficients = getattr(geometry, "coefficients", None)
        if coefficients is None:
            continue
        for coeff_index, raw in enumerate(coefficients):
            value = _finite_float(raw)
            if value is None or abs(value) < 1e-8:
                continue
            guard = _asphere_audit_guard(value, coeff_index)
            candidates.append(
                _variable_candidate(
                    variable="asphere_coefficient",
                    surface_index=surface_index,
                    coefficient_index=coeff_index,
                    before=value,
                    bounds=guard.bounds,
                    status="audited_only",
                    reason=(
                        f"asphere r^{guard.power} coefficient observed with order-aware "
                        "sag/slope audit bounds; requires full manufacturability guard "
                        "before optimization"
                    ),
                    asphere_power=guard.power,
                    audit_aperture_mm=guard.aperture_mm,
                    edge_sag_delta_um=guard.edge_sag_delta_um,
                    edge_slope_delta_mrad=guard.edge_slope_delta_mrad,
                    manufacturability_status=guard.status,
                )
            )
            if len(candidates) >= _MAX_ASPHERE_CANDIDATES_TO_REPORT:
                return candidates
    return candidates


def _candidate_label(candidate: OptimizationVariableCandidate) -> str:
    if candidate.variable == "asphere_coefficient":
        coeff = candidate.coefficient_index if candidate.coefficient_index is not None else -1
        value = "n/a" if candidate.before is None else f"{candidate.before:.3g}"
        if candidate.min_value is None or candidate.max_value is None:
            return f"S{candidate.surface_index}:c{coeff}={value}"
        return (
            f"S{candidate.surface_index}:c{coeff}={value} "
            f"[{candidate.min_value:.3g},{candidate.max_value:.3g}] "
            f"r^{candidate.asphere_power or '?'} "
            f"sag={candidate.edge_sag_delta_um or 0:.2f}um "
            f"slope={candidate.edge_slope_delta_mrad or 0:.2f}mrad "
            f"{candidate.manufacturability_status or 'unguarded'}"
        )
    value = "n/a" if candidate.before is None else f"{candidate.before:.4f}"
    if candidate.min_value is None or candidate.max_value is None:
        return f"{candidate.variable} S{candidate.surface_index}={value}/{candidate.status}"
    return (
        f"{candidate.variable} S{candidate.surface_index}={value} "
        f"[{candidate.min_value:.4f},{candidate.max_value:.4f}]"
    )


def _variable_trial(
    *,
    variable: str,
    surface_index: int,
    status: str,
    reason: str,
    before: float | None = None,
    after: float | None = None,
    merit_before: float | None = None,
    merit_after: float | None = None,
    efl_improvement_mm: float | None = None,
    rms_improvement_um: float | None = None,
    rms_improvement_pct: float | None = None,
    promotion_score: float | None = None,
    image_quality_floor_gap_before: float | None = None,
    image_quality_floor_gap_after: float | None = None,
    image_quality_floor_gap_closure: float | None = None,
    verification_status: str | None = None,
    mtf_field_non_regressed: bool | None = None,
    mtf_band_non_regressed: bool | None = None,
    mtf_field_weighted_non_regressed: bool | None = None,
    efl_locked: bool | None = None,
    coefficient_index: int | None = None,
    coupled_variable: str | None = None,
    coupled_surface_index: int | None = None,
    coupled_before: float | None = None,
    coupled_after: float | None = None,
    prescreen_rank: int | None = None,
    step_fraction: float | None = None,
) -> OptimizationVariableTrial:
    return OptimizationVariableTrial(
        variable=variable,
        surface_index=surface_index,
        coefficient_index=coefficient_index,
        coupled_variable=coupled_variable,
        coupled_surface_index=coupled_surface_index,
        coupled_before=coupled_before,
        coupled_after=coupled_after,
        prescreen_rank=prescreen_rank,
        step_fraction=step_fraction,
        status=status,
        reason=reason,
        before=before,
        after=after,
        merit_before=merit_before,
        merit_after=merit_after,
        efl_improvement_mm=efl_improvement_mm,
        rms_improvement_um=rms_improvement_um,
        rms_improvement_pct=rms_improvement_pct,
        promotion_score=promotion_score,
        image_quality_floor_gap_before=image_quality_floor_gap_before,
        image_quality_floor_gap_after=image_quality_floor_gap_after,
        image_quality_floor_gap_closure=image_quality_floor_gap_closure,
        verification_status=verification_status,
        mtf_field_non_regressed=mtf_field_non_regressed,
        mtf_band_non_regressed=mtf_band_non_regressed,
        mtf_field_weighted_non_regressed=mtf_field_weighted_non_regressed,
        efl_locked=efl_locked,
    )


def _merit_promotion_score(
    *,
    accepted: bool,
    verification_status: str,
    rms_improvement_um: float,
    mtf_field_non_regressed: bool,
    mtf_band_non_regressed: bool,
    mtf_field_weighted_non_regressed: bool,
    efl_locked: bool,
    image_quality_floor_gap_closure: float | None = None,
) -> float:
    score = 0.0
    if accepted:
        score += 1000.0
    if verification_status == "passed":
        score += 100.0
    if mtf_field_non_regressed:
        score += 25.0
    if mtf_band_non_regressed:
        score += 25.0
    if mtf_field_weighted_non_regressed:
        score += 25.0
    if efl_locked:
        score += 25.0
    if image_quality_floor_gap_closure is not None:
        score += max(image_quality_floor_gap_closure, 0.0) * _FLOOR_GAP_PROMOTION_WEIGHT
    score += max(rms_improvement_um, 0.0)
    return score


def _merit_probe_rank(
    *,
    accepted: bool,
    rms_improvement_um: float,
    promotion_score: float,
    image_quality_floor_gap_closure: float | None,
    probe_purpose: str,
) -> tuple[int, int, float, float, float]:
    accepted_rank = 1 if accepted else 0
    rms_nonnegative_rank = 1 if rms_improvement_um >= 0 else 0
    floor_rank = (
        image_quality_floor_gap_closure
        if image_quality_floor_gap_closure is not None
        else -math.inf
    )
    if probe_purpose in {"image_quality_floor_recovery", "replay_gate_remediation"}:
        return (
            accepted_rank,
            rms_nonnegative_rank,
            floor_rank,
            promotion_score,
            rms_improvement_um,
        )
    return (
        accepted_rank,
        rms_nonnegative_rank,
        promotion_score,
        rms_improvement_um,
        floor_rank,
    )


def _floor_gap_closure(
    before_metrics: object | None,
    after_metrics: object | None,
) -> tuple[float | None, float | None, float | None]:
    before_gap = image_quality_floor_gap_score(before_metrics)
    after_gap = image_quality_floor_gap_score(after_metrics)
    if before_gap is None or after_gap is None:
        return before_gap, after_gap, None
    return before_gap, after_gap, round(before_gap - after_gap, 3)


def _remaining_floor_gap(metrics: object | None) -> float | None:
    gap = image_quality_floor_gap_score(metrics)
    if gap is None or not math.isfinite(gap):
        return None
    return gap


def _floor_metric_snapshot(
    mtf_bands: MtfBandMetrics,
    max_rms_spot_radius_um: float | None,
) -> OptimizationMetricSnapshot:
    return OptimizationMetricSnapshot(
        mtf_50lpmm_min=mtf_bands.min_50,
        mtf_50lpmm_avg=mtf_bands.avg_50,
        mtf_100lpmm_min=mtf_bands.min_100,
        mtf_100lpmm_avg=mtf_bands.avg_100,
        mtf_150lpmm_min=mtf_bands.min_150,
        mtf_150lpmm_avg=mtf_bands.avg_150,
        mtf_200lpmm_min=mtf_bands.min_200,
        mtf_200lpmm_avg=mtf_bands.avg_200,
        mtf_250lpmm_min=mtf_bands.min_250,
        mtf_250lpmm_avg=mtf_bands.avg_250,
        mtf_multiband_min_score=mtf_bands.multiband_min_score,
        mtf_field_weighted_score=mtf_bands.field_weighted_score,
        max_rms_spot_radius_um=max_rms_spot_radius_um,
    )


def _normalized_variable_priority(variable_priority: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in variable_priority:
        variable = _VARIABLE_PRIORITY_ALIASES.get(item, item)
        if variable not in normalized:
            normalized.append(variable)
    return tuple(normalized)


def _priority_index(variable: str, variable_priority: tuple[str, ...]) -> int:
    try:
        return variable_priority.index(variable)
    except ValueError:
        return len(variable_priority)


def _change_from_trial(trial: OptimizationVariableTrial) -> OptimizationVariableChange | None:
    if trial.variable not in {"radius", "thickness", "stop_position", "focus_position"}:
        return None
    if trial.before is None or trial.after is None:
        return None
    delta = trial.after - trial.before
    return OptimizationVariableChange(
        variable=trial.variable,
        surface_index=trial.surface_index,
        before=trial.before,
        after=trial.after,
        delta=delta,
        delta_pct=(delta / trial.before * 100.0 if trial.before else 0.0),
    )


def _change_set_label(changes: list[OptimizationVariableChange]) -> str:
    return " + ".join(f"{change.variable} S{change.surface_index}" for change in changes)


def _set_asphere_coefficient(
    optic,
    surface_index: int,
    coefficient_index: int,
    value: float,
) -> float:
    surface = optic.surfaces.surfaces[surface_index]
    geometry = getattr(surface, "geometry", None)
    coefficients = getattr(geometry, "coefficients", None)
    if coefficients is None:
        raise ValueError("surface has no asphere coefficients")
    coefficients[coefficient_index] = value
    written = _finite_float(coefficients[coefficient_index])
    if written is None or not math.isclose(written, value, rel_tol=1e-12, abs_tol=1e-18):
        raise ValueError("asphere coefficient write-back check failed")
    return written


def _asphere_trial_values(candidate: OptimizationVariableCandidate) -> list[float]:
    if candidate.before is None:
        return []
    raw_values = [candidate.min_value, candidate.max_value]
    values: list[float] = []
    for value in raw_values:
        if value is None or not math.isfinite(value):
            continue
        if math.isclose(value, candidate.before, rel_tol=1e-12, abs_tol=1e-18):
            continue
        if any(math.isclose(value, existing, rel_tol=1e-12, abs_tol=1e-18) for existing in values):
            continue
        values.append(value)
    values.sort(key=lambda value: abs(value - candidate.before), reverse=True)
    return values


def _asphere_prescreen_merit(optic, field_samples: tuple[float, ...]) -> float | None:
    values: list[float] = []
    for field_sample in field_samples:
        value = _rms_operand_value(optic, field_sample)
        if value is None or value < 0:
            return None
        values.append(value)
    return sum(values)


def _asphere_prescreen_candidates(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    asphere_candidates: list[OptimizationVariableCandidate],
) -> list[AsphereAuditPrescreen]:
    base = _load_probe_optic(source_zmx, nominal_fov_deg)
    _apply_radius_changes(base, radius_changes)
    _apply_baseline_variable_changes(base, baseline_variable_changes)
    field_samples = _finite_merit_field_samples(base)
    if not field_samples:
        return []
    merit_before = _asphere_prescreen_merit(base, field_samples)
    if merit_before is None:
        return []

    rows: list[AsphereAuditPrescreen] = []
    guarded_candidates = [
        candidate
        for candidate in asphere_candidates
        if candidate.status == "audited_only"
        and candidate.manufacturability_status == "guarded"
        and candidate.before is not None
        and candidate.coefficient_index is not None
    ]
    for candidate in guarded_candidates:
        if len(rows) >= _MAX_ASPHERE_PRESCREEN_TRIALS:
            break
        for target_value in _asphere_trial_values(candidate):
            if len(rows) >= _MAX_ASPHERE_PRESCREEN_TRIALS:
                break
            assert candidate.coefficient_index is not None
            try:
                optic = _load_probe_optic(source_zmx, nominal_fov_deg)
                _apply_radius_changes(optic, radius_changes)
                _apply_baseline_variable_changes(optic, baseline_variable_changes)
                _set_asphere_coefficient(
                    optic,
                    candidate.surface_index,
                    candidate.coefficient_index,
                    target_value,
                )
                merit_after = _asphere_prescreen_merit(optic, field_samples)
            except Exception:
                merit_after = None
            if merit_after is None:
                continue
            rows.append(
                AsphereAuditPrescreen(
                    candidate=candidate,
                    target_value=target_value,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    merit_improvement=merit_before - merit_after,
                    field_samples=field_samples,
                )
            )
    return sorted(rows, key=lambda row: row.merit_improvement, reverse=True)


def _asphere_audit_trials(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    before_mtf_max_field_frac: float | None,
    before_mtf_bands: MtfBandMetrics,
    before_max_rms_spot_radius_um: float,
    prescreen_rows: list[AsphereAuditPrescreen],
) -> list[OptimizationVariableTrial]:
    trials: list[OptimizationVariableTrial] = []
    before_floor_metrics = _floor_metric_snapshot(
        before_mtf_bands,
        before_max_rms_spot_radius_um,
    )
    ranked_rows = prescreen_rows[:_MAX_ASPHERE_AUDIT_CANDIDATES_TO_VERIFY]
    for prescreen_rank, row in enumerate(ranked_rows, start=1):
        candidate = row.candidate
        assert candidate.coefficient_index is not None
        for step_fraction in _ASPHERE_AUDIT_STEP_FRACTIONS:
            if len(trials) >= _MAX_ASPHERE_AUDIT_TRIALS:
                return trials
            assert candidate.before is not None
            target_value = candidate.before + (row.target_value - candidate.before) * step_fraction
            try:
                optic = _load_probe_optic(source_zmx, nominal_fov_deg)
                _apply_radius_changes(optic, radius_changes)
                _apply_baseline_variable_changes(optic, baseline_variable_changes)
                written = _set_asphere_coefficient(
                    optic,
                    candidate.surface_index,
                    candidate.coefficient_index,
                    target_value,
                )
                merit_after = _asphere_prescreen_merit(optic, row.field_samples)
                after_paraxial = compute_paraxial_summary(optic)
                verification = _verify_probe_optic(
                    optic,
                    nominal_fov_deg,
                    max_total_track_mm,
                )
                after_rms = verification.max_rms_spot_radius_um
                if after_rms is None:
                    floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                        before_floor_metrics,
                        verification,
                    )
                    trials.append(
                        _variable_trial(
                            variable="asphere_coefficient",
                            surface_index=candidate.surface_index,
                            coefficient_index=candidate.coefficient_index,
                            prescreen_rank=prescreen_rank,
                            step_fraction=step_fraction,
                            before=candidate.before,
                            after=written,
                            merit_before=row.merit_before,
                            merit_after=merit_after,
                            image_quality_floor_gap_before=floor_gap_before,
                            image_quality_floor_gap_after=floor_gap_after,
                            image_quality_floor_gap_closure=floor_gap_closure,
                            verification_status=verification.status,
                            status="failed",
                            reason="audit-only verification had no max RMS",
                        )
                    )
                    continue

                rms_improvement = before_max_rms_spot_radius_um - after_rms
                rms_improvement_pct = (
                    rms_improvement / before_max_rms_spot_radius_um * 100.0
                    if before_max_rms_spot_radius_um
                    else 0.0
                )
                mtf_non_regressed = before_mtf_max_field_frac is None or (
                    verification.mtf_max_field_frac is not None
                    and verification.mtf_max_field_frac >= before_mtf_max_field_frac
                )
                after_bands = mtf_bands_from_snapshot(verification)
                mtf_band_non_regressed = mtf_multiband_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                    before_floor_metrics,
                    verification,
                )
                field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                efl_locked = (
                    after_paraxial.effective_focal_length_mm is not None
                    and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
                )
                improved = (
                    verification.status == "passed"
                    and rms_improvement >= 0.0
                    and mtf_non_regressed
                    and mtf_band_non_regressed
                    and field_weighted_non_regressed
                    and efl_locked
                )
                promotion_score = _merit_promotion_score(
                    accepted=False,
                    verification_status=verification.status,
                    rms_improvement_um=rms_improvement,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    image_quality_floor_gap_closure=floor_gap_closure,
                )
                if improved:
                    trial_status = "improved"
                    trial_reason = (
                        f"step={step_fraction:.3f} audit-only asphere perturbation "
                        "passed prescreen and improved/non-regressed checked gates; "
                        "not promotable until coefficient optimizer is enabled"
                    )
                else:
                    failed_gates: list[str] = []
                    if verification.status != "passed":
                        failed_gates.append(f"verification={verification.status}")
                    if rms_improvement < 0.0:
                        failed_gates.append("RMS regressed after full verification")
                    if not mtf_non_regressed:
                        failed_gates.append("MTF field fraction regressed")
                    if not mtf_band_non_regressed:
                        failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                    if not field_weighted_non_regressed:
                        failed_gates.append("field-weighted MTF regressed")
                    if not efl_locked:
                        failed_gates.append("EFL not locked")
                    trial_status = "rejected"
                    trial_reason = (
                        f"step={step_fraction:.3f}; "
                        f"{'; '.join(failed_gates) or 'audit-only gates did not pass'}"
                    )
                trials.append(
                    _variable_trial(
                        variable="asphere_coefficient",
                        surface_index=candidate.surface_index,
                        coefficient_index=candidate.coefficient_index,
                        prescreen_rank=prescreen_rank,
                        step_fraction=step_fraction,
                        before=candidate.before,
                        after=written,
                        merit_before=row.merit_before,
                        merit_after=merit_after,
                        rms_improvement_um=rms_improvement,
                        rms_improvement_pct=rms_improvement_pct,
                        promotion_score=promotion_score,
                        image_quality_floor_gap_before=floor_gap_before,
                        image_quality_floor_gap_after=floor_gap_after,
                        image_quality_floor_gap_closure=floor_gap_closure,
                        verification_status=verification.status,
                        mtf_field_non_regressed=mtf_non_regressed,
                        mtf_band_non_regressed=mtf_band_non_regressed,
                        mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                        efl_locked=efl_locked,
                        status=trial_status,
                        reason=trial_reason,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                trials.append(
                    _variable_trial(
                        variable="asphere_coefficient",
                        surface_index=candidate.surface_index,
                        coefficient_index=candidate.coefficient_index,
                        prescreen_rank=prescreen_rank,
                        step_fraction=step_fraction,
                        before=candidate.before,
                        after=target_value,
                        merit_before=row.merit_before,
                        status="failed",
                        reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                    )
                )
    return trials


def _joint_asphere_merit_trials(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    merit_variable_changes: list[OptimizationVariableChange],
    asphere_trials: list[OptimizationVariableTrial],
    joint_baseline_metrics: OptimizationMetricSnapshot | None,
) -> list[OptimizationVariableTrial]:
    if not merit_variable_changes or joint_baseline_metrics is None:
        return []
    if joint_baseline_metrics.max_rms_spot_radius_um is None:
        return []

    merit_change = next(
        (change for change in merit_variable_changes if change.variable in {"radius", "thickness"}),
        None,
    )
    if merit_change is None:
        return []

    ranked_asphere_trials = sorted(
        [
            trial
            for trial in asphere_trials
            if trial.after is not None and trial.coefficient_index is not None
        ],
        key=lambda trial: (
            1 if trial.status == "improved" else 0,
            trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf,
        ),
        reverse=True,
    )
    trials: list[OptimizationVariableTrial] = []
    before_mtf_bands = mtf_bands_from_snapshot(joint_baseline_metrics)
    before_max_rms = joint_baseline_metrics.max_rms_spot_radius_um
    before_mtf_frac = joint_baseline_metrics.mtf_max_field_frac

    for asphere_trial in ranked_asphere_trials[:_MAX_JOINT_ASPHERE_AUDIT_TRIALS]:
        try:
            optic = _load_probe_optic(source_zmx, nominal_fov_deg)
            _apply_radius_changes(optic, radius_changes)
            _apply_baseline_variable_changes(optic, baseline_variable_changes)
            coupled_written = merit_change.after
            for change in merit_variable_changes:
                written_change = _apply_variable_change(optic, change)
                if change is merit_change:
                    coupled_written = written_change
            field_samples = _finite_merit_field_samples(optic)
            merit_before = _asphere_prescreen_merit(optic, field_samples) if field_samples else None
            written = _set_asphere_coefficient(
                optic,
                asphere_trial.surface_index,
                asphere_trial.coefficient_index,
                asphere_trial.after,
            )
            merit_after = _asphere_prescreen_merit(optic, field_samples) if field_samples else None
            after_paraxial = compute_paraxial_summary(optic)
            verification = _verify_probe_optic(
                optic,
                nominal_fov_deg,
                max_total_track_mm,
            )
            after_rms = verification.max_rms_spot_radius_um
            if after_rms is None:
                floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                    joint_baseline_metrics,
                    verification,
                )
                trials.append(
                    _variable_trial(
                        variable="joint_asphere_merit",
                        surface_index=asphere_trial.surface_index,
                        coefficient_index=asphere_trial.coefficient_index,
                        coupled_variable=merit_change.variable,
                        coupled_surface_index=merit_change.surface_index,
                        coupled_before=merit_change.before,
                        coupled_after=coupled_written,
                        prescreen_rank=asphere_trial.prescreen_rank,
                        step_fraction=asphere_trial.step_fraction,
                        before=asphere_trial.before,
                        after=written,
                        merit_before=merit_before,
                        merit_after=merit_after,
                        image_quality_floor_gap_before=floor_gap_before,
                        image_quality_floor_gap_after=floor_gap_after,
                        image_quality_floor_gap_closure=floor_gap_closure,
                        verification_status=verification.status,
                        status="failed",
                        reason="joint audit verification had no max RMS",
                    )
                )
                continue

            rms_improvement = before_max_rms - after_rms
            rms_improvement_pct = (
                rms_improvement / before_max_rms * 100.0 if before_max_rms else 0.0
            )
            mtf_non_regressed = before_mtf_frac is None or (
                verification.mtf_max_field_frac is not None
                and verification.mtf_max_field_frac >= before_mtf_frac
            )
            after_bands = mtf_bands_from_snapshot(verification)
            mtf_band_non_regressed = mtf_multiband_non_regressed(
                before_mtf_bands,
                after_bands,
            )
            floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                joint_baseline_metrics,
                verification,
            )
            field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                before_mtf_bands,
                after_bands,
            )
            efl_locked = (
                after_paraxial.effective_focal_length_mm is not None
                and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
            )
            improved = (
                verification.status == "passed"
                and rms_improvement >= 0.0
                and mtf_non_regressed
                and mtf_band_non_regressed
                and field_weighted_non_regressed
                and efl_locked
            )
            promotion_score = _merit_promotion_score(
                accepted=False,
                verification_status=verification.status,
                rms_improvement_um=rms_improvement,
                mtf_field_non_regressed=mtf_non_regressed,
                mtf_band_non_regressed=mtf_band_non_regressed,
                mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                efl_locked=efl_locked,
                image_quality_floor_gap_closure=floor_gap_closure,
            )
            if improved:
                trial_status = "improved"
                trial_reason = (
                    f"joint audit {merit_change.variable} S{merit_change.surface_index} "
                    "plus asphere step passed checked gates; still evidence-only"
                )
            else:
                failed_gates: list[str] = []
                if verification.status != "passed":
                    failed_gates.append(f"verification={verification.status}")
                if rms_improvement < 0.0:
                    failed_gates.append("joint RMS regressed")
                if not mtf_non_regressed:
                    failed_gates.append("MTF field fraction regressed")
                if not mtf_band_non_regressed:
                    failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                if not field_weighted_non_regressed:
                    failed_gates.append("field-weighted MTF regressed")
                if not efl_locked:
                    failed_gates.append("EFL not locked")
                trial_status = "rejected"
                trial_reason = (
                    f"joint audit {merit_change.variable} S{merit_change.surface_index}; "
                    f"{'; '.join(failed_gates) or 'joint audit gates did not pass'}"
                )
            trials.append(
                _variable_trial(
                    variable="joint_asphere_merit",
                    surface_index=asphere_trial.surface_index,
                    coefficient_index=asphere_trial.coefficient_index,
                    coupled_variable=merit_change.variable,
                    coupled_surface_index=merit_change.surface_index,
                    coupled_before=merit_change.before,
                    coupled_after=coupled_written,
                    prescreen_rank=asphere_trial.prescreen_rank,
                    step_fraction=asphere_trial.step_fraction,
                    before=asphere_trial.before,
                    after=written,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    rms_improvement_um=rms_improvement,
                    rms_improvement_pct=rms_improvement_pct,
                    promotion_score=promotion_score,
                    image_quality_floor_gap_before=floor_gap_before,
                    image_quality_floor_gap_after=floor_gap_after,
                    image_quality_floor_gap_closure=floor_gap_closure,
                    verification_status=verification.status,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    status=trial_status,
                    reason=trial_reason,
                )
            )
        except Exception as exc:  # noqa: BLE001
            trials.append(
                _variable_trial(
                    variable="joint_asphere_merit",
                    surface_index=asphere_trial.surface_index,
                    coefficient_index=asphere_trial.coefficient_index,
                    coupled_variable=merit_change.variable,
                    coupled_surface_index=merit_change.surface_index,
                    coupled_before=merit_change.before,
                    coupled_after=merit_change.after,
                    prescreen_rank=asphere_trial.prescreen_rank,
                    step_fraction=asphere_trial.step_fraction,
                    before=asphere_trial.before,
                    after=asphere_trial.after,
                    status="failed",
                    reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                )
            )
    return trials


def _stop_position_replay_trials(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    before_metrics: OptimizationMetricSnapshot,
    before_mtf_max_field_frac: float | None,
    before_mtf_bands: MtfBandMetrics,
    before_max_rms_spot_radius_um: float,
    variable_candidates: list[OptimizationVariableCandidate],
    variable_priority: tuple[str, ...],
    probe_purpose: str,
    base_diagnostics: list[str],
) -> tuple[
    list[OptimizationVariableTrial],
    list[tuple[OptimizationMeritProbe, tuple[int, int, float, float, float]]],
    list[str],
]:
    if probe_purpose not in _STOP_POSITION_REPLAY_PURPOSES:
        return [], [], []

    stop_candidates = [
        candidate
        for candidate in variable_candidates
        if candidate.variable == "stop_position" and candidate.status == "eligible"
    ]
    if not stop_candidates:
        return [], [], ["stop-position replay trials=0"]

    trials: list[OptimizationVariableTrial] = []
    probe_ranks: list[tuple[OptimizationMeritProbe, tuple[int, int, float, float, float]]] = []
    for candidate in stop_candidates:
        if candidate.before is None:
            trials.append(
                _variable_trial(
                    variable="stop_position",
                    surface_index=candidate.surface_index,
                    status="failed",
                    reason="stop surface thickness is non-finite",
                )
            )
            continue

        try:
            base_optic = _load_probe_optic(source_zmx, nominal_fov_deg)
            _apply_radius_changes(base_optic, radius_changes)
            _apply_baseline_variable_changes(base_optic, baseline_variable_changes)
            field_samples = _finite_merit_field_samples(base_optic)
            merit_before = (
                _asphere_prescreen_merit(base_optic, field_samples) if field_samples else None
            )
        except Exception as exc:  # noqa: BLE001
            trials.append(
                _variable_trial(
                    variable="stop_position",
                    surface_index=candidate.surface_index,
                    before=candidate.before,
                    status="failed",
                    reason=f"stop-position replay setup failed: {type(exc).__name__}: {str(exc)[:120]}",
                )
            )
            continue

        for delta in _MERIT_STOP_POSITION_DELTAS_MM:
            target_value = candidate.before + delta
            try:
                optic = _load_probe_optic(source_zmx, nominal_fov_deg)
                _apply_radius_changes(optic, radius_changes)
                _apply_baseline_variable_changes(optic, baseline_variable_changes)
                written = _set_surface_thickness(
                    optic,
                    candidate.surface_index,
                    target_value,
                )
                merit_after = (
                    _asphere_prescreen_merit(optic, field_samples) if field_samples else None
                )
                after_paraxial = compute_paraxial_summary(optic)
                verification = _verify_probe_optic(
                    optic,
                    nominal_fov_deg,
                    max_total_track_mm,
                )
                after_bands = mtf_bands_from_snapshot(verification)
                after_metrics = _metric_snapshot(
                    after_paraxial,
                    mtf_max_field_frac=verification.mtf_max_field_frac,
                    mtf_bands=after_bands,
                    max_rms_spot_radius_um=verification.max_rms_spot_radius_um,
                )
                after_rms = verification.max_rms_spot_radius_um
                if after_rms is None:
                    floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                        before_metrics,
                        after_metrics,
                    )
                    trials.append(
                        _variable_trial(
                            variable="stop_position",
                            surface_index=candidate.surface_index,
                            before=candidate.before,
                            after=written,
                            merit_before=merit_before,
                            merit_after=merit_after,
                            image_quality_floor_gap_before=floor_gap_before,
                            image_quality_floor_gap_after=floor_gap_after,
                            image_quality_floor_gap_closure=floor_gap_closure,
                            verification_status=verification.status,
                            status="failed",
                            reason="stop-position replay verification had no max RMS",
                        )
                    )
                    continue

                rms_improvement = before_max_rms_spot_radius_um - after_rms
                rms_improvement_pct = (
                    rms_improvement / before_max_rms_spot_radius_um * 100.0
                    if before_max_rms_spot_radius_um
                    else 0.0
                )
                mtf_non_regressed = before_mtf_max_field_frac is None or (
                    verification.mtf_max_field_frac is not None
                    and verification.mtf_max_field_frac >= before_mtf_max_field_frac
                )
                mtf_band_non_regressed = mtf_multiband_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                    before_metrics,
                    after_metrics,
                )
                field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                efl_locked = (
                    after_paraxial.effective_focal_length_mm is not None
                    and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
                )
                accepted = (
                    verification.status == "passed"
                    and rms_improvement >= 0.10
                    and mtf_non_regressed
                    and mtf_band_non_regressed
                    and field_weighted_non_regressed
                    and efl_locked
                )
                promotion_score = _merit_promotion_score(
                    accepted=accepted,
                    verification_status=verification.status,
                    rms_improvement_um=rms_improvement,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    image_quality_floor_gap_closure=floor_gap_closure,
                )
                if accepted:
                    trial_status = "accepted"
                    trial_reason = "stop-position replay passed RMS/MTF/EFL promotion gates"
                else:
                    failed_gates: list[str] = []
                    if verification.status != "passed":
                        failed_gates.append(f"verification={verification.status}")
                    if rms_improvement < 0.10:
                        failed_gates.append("RMS improvement below 0.10 um")
                    if not mtf_non_regressed:
                        failed_gates.append("MTF field fraction regressed")
                    if not mtf_band_non_regressed:
                        failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                    if not field_weighted_non_regressed:
                        failed_gates.append("field-weighted MTF regressed")
                    if not efl_locked:
                        failed_gates.append("EFL not locked")
                    trial_status = "rejected"
                    trial_reason = "; ".join(failed_gates) or "promotion gates did not pass"

                trial = _variable_trial(
                    variable="stop_position",
                    surface_index=candidate.surface_index,
                    before=candidate.before,
                    after=written,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    rms_improvement_um=rms_improvement,
                    rms_improvement_pct=rms_improvement_pct,
                    promotion_score=promotion_score,
                    image_quality_floor_gap_before=floor_gap_before,
                    image_quality_floor_gap_after=floor_gap_after,
                    image_quality_floor_gap_closure=floor_gap_closure,
                    verification_status=verification.status,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    status=trial_status,
                    reason=trial_reason,
                )
                trials.append(trial)

                change = _change_from_trial(trial)
                if change is None:
                    continue
                probe = OptimizationMeritProbe(
                    status="proposal" if accepted else "warning",
                    engine="optiland.stop_position_replay",
                    summary=(
                        "protected stop-position replay found a verified image-quality improvement"
                        if accepted
                        else "stop-position replay ran, but verification did not pass promotion gates"
                    ),
                    operand="rms_spot_size",
                    probe_purpose=probe_purpose,
                    variable_priority=list(variable_priority),
                    field_samples=list(field_samples),
                    target_efl_mm=target_efl_mm,
                    target_total_track_mm=max_total_track_mm,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    rms_improvement_um=rms_improvement,
                    rms_improvement_pct=rms_improvement_pct,
                    variable_candidates=variable_candidates,
                    candidate_trials=[],
                    variable_changes=[change],
                    verification=verification,
                    before_metrics=before_metrics,
                    after_metrics=after_metrics,
                    diagnostics=[
                        *base_diagnostics,
                        f"finite RMS operand fields: {field_samples}",
                        f"stop-position replay delta={delta:+.3f} mm",
                        f"MTF 50/100/150/200/250 lp/mm non-regressed={mtf_band_non_regressed}",
                        f"MTF field-weighted score non-regressed={field_weighted_non_regressed}",
                        f"image-quality floor gap closure={floor_gap_closure}",
                        f"promotion score={promotion_score:.3f}",
                    ],
                    applied_to_payload=False,
                )
                rank = _merit_probe_rank(
                    accepted=accepted,
                    rms_improvement_um=rms_improvement,
                    promotion_score=promotion_score,
                    image_quality_floor_gap_closure=floor_gap_closure,
                    probe_purpose=probe_purpose,
                )
                probe_ranks.append((probe, rank))
            except Exception as exc:  # noqa: BLE001
                trials.append(
                    _variable_trial(
                        variable="stop_position",
                        surface_index=candidate.surface_index,
                        before=candidate.before,
                        after=target_value,
                        merit_before=merit_before,
                        status="failed",
                        reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                    )
                )

    diagnostics = [f"stop-position replay trials={len(trials)}"]
    accepted_trials = [trial for trial in trials if trial.status == "accepted"]
    if accepted_trials:
        best = max(
            accepted_trials,
            key=lambda trial: (
                trial.image_quality_floor_gap_closure
                if trial.image_quality_floor_gap_closure is not None
                else -math.inf,
                trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf,
            ),
        )
        best_delta = (
            best.after - best.before if best.after is not None and best.before is not None else 0.0
        )
        diagnostics.append(
            f"best stop-position replay=S{best.surface_index} "
            f"delta={best_delta:+.3f} mm "
            f"closure={best.image_quality_floor_gap_closure:+.3f}"
        )
    return trials, probe_ranks, diagnostics


def _focus_position_replay_trials(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    before_metrics: OptimizationMetricSnapshot,
    before_mtf_max_field_frac: float | None,
    before_mtf_bands: MtfBandMetrics,
    before_max_rms_spot_radius_um: float,
    variable_candidates: list[OptimizationVariableCandidate],
    variable_priority: tuple[str, ...],
    probe_purpose: str,
    base_diagnostics: list[str],
) -> tuple[
    list[OptimizationVariableTrial],
    list[tuple[OptimizationMeritProbe, tuple[int, int, float, float, float]]],
    list[str],
]:
    if probe_purpose not in _FOCUS_POSITION_REPLAY_PURPOSES:
        return [], [], []

    focus_candidates = [
        candidate
        for candidate in variable_candidates
        if candidate.variable == "focus_position" and candidate.status == "eligible"
    ]
    if not focus_candidates:
        return [], [], ["focus-position replay trials=0"]

    trials: list[OptimizationVariableTrial] = []
    probe_ranks: list[tuple[OptimizationMeritProbe, tuple[int, int, float, float, float]]] = []
    for candidate in focus_candidates:
        if candidate.before is None:
            trials.append(
                _variable_trial(
                    variable="focus_position",
                    surface_index=candidate.surface_index,
                    status="failed",
                    reason="focus-position thickness is non-finite",
                )
            )
            continue

        try:
            base_optic = _load_probe_optic(source_zmx, nominal_fov_deg)
            _apply_radius_changes(base_optic, radius_changes)
            _apply_baseline_variable_changes(base_optic, baseline_variable_changes)
            field_samples = _finite_merit_field_samples(base_optic)
            merit_before = (
                _asphere_prescreen_merit(base_optic, field_samples) if field_samples else None
            )
        except Exception as exc:  # noqa: BLE001
            trials.append(
                _variable_trial(
                    variable="focus_position",
                    surface_index=candidate.surface_index,
                    before=candidate.before,
                    status="failed",
                    reason=(
                        "focus-position replay setup failed: "
                        f"{type(exc).__name__}: {str(exc)[:120]}"
                    ),
                )
            )
            continue

        for delta in _MERIT_FOCUS_POSITION_DELTAS_MM:
            target_value = candidate.before + delta
            if target_value <= _MERIT_MIN_THICKNESS_MM:
                continue
            try:
                optic = _load_probe_optic(source_zmx, nominal_fov_deg)
                _apply_radius_changes(optic, radius_changes)
                _apply_baseline_variable_changes(optic, baseline_variable_changes)
                written = _set_surface_thickness(
                    optic,
                    candidate.surface_index,
                    target_value,
                )
                merit_after = (
                    _asphere_prescreen_merit(optic, field_samples) if field_samples else None
                )
                after_paraxial = compute_paraxial_summary(optic)
                verification = _verify_probe_optic(
                    optic,
                    nominal_fov_deg,
                    max_total_track_mm,
                )
                after_bands = mtf_bands_from_snapshot(verification)
                after_metrics = _metric_snapshot(
                    after_paraxial,
                    mtf_max_field_frac=verification.mtf_max_field_frac,
                    mtf_bands=after_bands,
                    max_rms_spot_radius_um=verification.max_rms_spot_radius_um,
                )
                after_rms = verification.max_rms_spot_radius_um
                if after_rms is None:
                    floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                        before_metrics,
                        after_metrics,
                    )
                    trials.append(
                        _variable_trial(
                            variable="focus_position",
                            surface_index=candidate.surface_index,
                            before=candidate.before,
                            after=written,
                            merit_before=merit_before,
                            merit_after=merit_after,
                            image_quality_floor_gap_before=floor_gap_before,
                            image_quality_floor_gap_after=floor_gap_after,
                            image_quality_floor_gap_closure=floor_gap_closure,
                            verification_status=verification.status,
                            status="failed",
                            reason="focus-position replay verification had no max RMS",
                        )
                    )
                    continue

                rms_improvement = before_max_rms_spot_radius_um - after_rms
                rms_improvement_pct = (
                    rms_improvement / before_max_rms_spot_radius_um * 100.0
                    if before_max_rms_spot_radius_um
                    else 0.0
                )
                mtf_non_regressed = before_mtf_max_field_frac is None or (
                    verification.mtf_max_field_frac is not None
                    and verification.mtf_max_field_frac >= before_mtf_max_field_frac
                )
                mtf_band_non_regressed = mtf_multiband_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                    before_metrics,
                    after_metrics,
                )
                field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                efl_locked = (
                    after_paraxial.effective_focal_length_mm is not None
                    and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
                )
                accepted = (
                    verification.status == "passed"
                    and rms_improvement >= 0.10
                    and mtf_non_regressed
                    and mtf_band_non_regressed
                    and field_weighted_non_regressed
                    and efl_locked
                )
                promotion_score = _merit_promotion_score(
                    accepted=accepted,
                    verification_status=verification.status,
                    rms_improvement_um=rms_improvement,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    image_quality_floor_gap_closure=floor_gap_closure,
                )
                if accepted:
                    trial_status = "accepted"
                    trial_reason = "focus-position replay passed RMS/MTF/EFL promotion gates"
                else:
                    failed_gates: list[str] = []
                    if verification.status != "passed":
                        failed_gates.append(f"verification={verification.status}")
                    if rms_improvement < 0.10:
                        failed_gates.append("RMS improvement below 0.10 um")
                    if not mtf_non_regressed:
                        failed_gates.append("MTF field fraction regressed")
                    if not mtf_band_non_regressed:
                        failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                    if not field_weighted_non_regressed:
                        failed_gates.append("field-weighted MTF regressed")
                    if not efl_locked:
                        failed_gates.append("EFL not locked")
                    trial_status = "rejected"
                    trial_reason = "; ".join(failed_gates) or "promotion gates did not pass"

                trial = _variable_trial(
                    variable="focus_position",
                    surface_index=candidate.surface_index,
                    before=candidate.before,
                    after=written,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    rms_improvement_um=rms_improvement,
                    rms_improvement_pct=rms_improvement_pct,
                    promotion_score=promotion_score,
                    image_quality_floor_gap_before=floor_gap_before,
                    image_quality_floor_gap_after=floor_gap_after,
                    image_quality_floor_gap_closure=floor_gap_closure,
                    verification_status=verification.status,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    status=trial_status,
                    reason=trial_reason,
                )
                trials.append(trial)

                change = _change_from_trial(trial)
                if change is None:
                    continue
                probe = OptimizationMeritProbe(
                    status="proposal" if accepted else "warning",
                    engine="optiland.focus_position_replay",
                    summary=(
                        "protected focus-position replay found a verified image-quality improvement"
                        if accepted
                        else "focus-position replay ran, but verification did not pass promotion gates"
                    ),
                    operand="rms_spot_size",
                    probe_purpose=probe_purpose,
                    variable_priority=list(variable_priority),
                    field_samples=list(field_samples),
                    target_efl_mm=target_efl_mm,
                    target_total_track_mm=max_total_track_mm,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    rms_improvement_um=rms_improvement,
                    rms_improvement_pct=rms_improvement_pct,
                    variable_candidates=variable_candidates,
                    candidate_trials=[],
                    variable_changes=[change],
                    verification=verification,
                    before_metrics=before_metrics,
                    after_metrics=after_metrics,
                    diagnostics=[
                        *base_diagnostics,
                        f"finite RMS operand fields: {field_samples}",
                        f"focus-position replay delta={delta:+.3f} mm",
                        f"MTF 50/100/150/200/250 lp/mm non-regressed={mtf_band_non_regressed}",
                        f"MTF field-weighted score non-regressed={field_weighted_non_regressed}",
                        f"image-quality floor gap closure={floor_gap_closure}",
                        f"promotion score={promotion_score:.3f}",
                    ],
                    applied_to_payload=False,
                )
                rank = _merit_probe_rank(
                    accepted=accepted,
                    rms_improvement_um=rms_improvement,
                    promotion_score=promotion_score,
                    image_quality_floor_gap_closure=floor_gap_closure,
                    probe_purpose=probe_purpose,
                )
                probe_ranks.append((probe, rank))
            except Exception as exc:  # noqa: BLE001
                trials.append(
                    _variable_trial(
                        variable="focus_position",
                        surface_index=candidate.surface_index,
                        before=candidate.before,
                        after=target_value,
                        merit_before=merit_before,
                        status="failed",
                        reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                    )
                )

    diagnostics = [f"focus-position replay trials={len(trials)}"]
    accepted_trials = [trial for trial in trials if trial.status == "accepted"]
    if accepted_trials:
        best = max(
            accepted_trials,
            key=lambda trial: (
                trial.image_quality_floor_gap_closure
                if trial.image_quality_floor_gap_closure is not None
                else -math.inf,
                trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf,
            ),
        )
        best_delta = (
            best.after - best.before if best.after is not None and best.before is not None else 0.0
        )
        diagnostics.append(
            f"best focus-position replay=S{best.surface_index} "
            f"delta={best_delta:+.3f} mm "
            f"closure={best.image_quality_floor_gap_closure:+.3f}"
        )
    return trials, probe_ranks, diagnostics


def _compound_continuation_replay_trials(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    focus_trials: list[OptimizationVariableTrial],
    variable_candidates: list[OptimizationVariableCandidate],
    variable_priority: tuple[str, ...],
    probe_purpose: str,
    before_metrics: OptimizationMetricSnapshot,
    before_mtf_max_field_frac: float | None,
    before_mtf_bands: MtfBandMetrics,
    before_max_rms_spot_radius_um: float,
    base_diagnostics: list[str],
) -> tuple[
    list[OptimizationVariableTrial],
    list[tuple[OptimizationMeritProbe, tuple[int, int, float, float, float]]],
    list[str],
]:
    if probe_purpose not in _COMPOUND_CONTINUATION_PURPOSES:
        return [], [], []

    focus_candidates = [
        trial
        for trial in focus_trials
        if trial.variable == "focus_position"
        and trial.before is not None
        and trial.after is not None
        and trial.image_quality_floor_gap_closure is not None
        and trial.image_quality_floor_gap_closure > 0.0
        and trial.verification_status == "passed"
        and trial.mtf_field_non_regressed is True
        and trial.mtf_field_weighted_non_regressed is True
        and trial.efl_locked is True
        and trial.rms_improvement_um is not None
        and trial.rms_improvement_um >= 0.10
    ]
    ranked_focus_trials = sorted(
        focus_candidates,
        key=lambda trial: (
            1 if trial.status == "rejected" and trial.mtf_band_non_regressed is False else 0,
            trial.image_quality_floor_gap_closure or -math.inf,
            trial.rms_improvement_um or -math.inf,
        ),
        reverse=True,
    )[:_MAX_COMPOUND_CONTINUATION_FOCUS_TRIALS]
    radius_candidates = [
        candidate
        for candidate in variable_candidates
        if candidate.variable == "radius"
        and candidate.status == "eligible"
        and candidate.before is not None
    ][:_MAX_COMPOUND_CONTINUATION_RADIUS_SURFACES]
    if not ranked_focus_trials or not radius_candidates:
        return [], [], ["compound continuation trials=0"]

    try:
        base_optic = _load_probe_optic(source_zmx, nominal_fov_deg)
        _apply_radius_changes(base_optic, radius_changes)
        _apply_baseline_variable_changes(base_optic, baseline_variable_changes)
        field_samples = _finite_merit_field_samples(base_optic)
        merit_before = (
            _asphere_prescreen_merit(base_optic, field_samples) if field_samples else None
        )
    except Exception as exc:  # noqa: BLE001
        return (
            [
                _variable_trial(
                    variable="compound_continuation",
                    surface_index=0,
                    status="failed",
                    reason=(
                        "compound continuation setup failed: "
                        f"{type(exc).__name__}: {str(exc)[:120]}"
                    ),
                )
            ],
            [],
            ["compound continuation trials=1"],
        )

    trials: list[OptimizationVariableTrial] = []
    probe_ranks: list[tuple[OptimizationMeritProbe, tuple[int, int, float, float, float]]] = []
    for focus_trial in ranked_focus_trials:
        focus_change = _change_from_trial(focus_trial)
        if focus_change is None:
            continue
        for radius_candidate in radius_candidates:
            assert radius_candidate.before is not None
            for radius_delta_frac in _COMPOUND_CONTINUATION_RADIUS_DELTAS:
                radius_after = radius_candidate.before * (1.0 + radius_delta_frac)
                radius_change = OptimizationVariableChange(
                    variable="radius",
                    surface_index=radius_candidate.surface_index,
                    before=radius_candidate.before,
                    after=radius_after,
                    delta=radius_after - radius_candidate.before,
                    delta_pct=radius_delta_frac * 100.0,
                )
                label = _change_set_label([focus_change, radius_change])
                try:
                    optic = _load_probe_optic(source_zmx, nominal_fov_deg)
                    _apply_radius_changes(optic, radius_changes)
                    _apply_baseline_variable_changes(optic, baseline_variable_changes)
                    _apply_variable_change(optic, focus_change)
                    _apply_variable_change(optic, radius_change)
                    merit_after = (
                        _asphere_prescreen_merit(optic, field_samples) if field_samples else None
                    )
                    after_paraxial = compute_paraxial_summary(optic)
                    verification = _verify_probe_optic(
                        optic,
                        nominal_fov_deg,
                        max_total_track_mm,
                    )
                    after_bands = mtf_bands_from_snapshot(verification)
                    after_metrics = _metric_snapshot(
                        after_paraxial,
                        mtf_max_field_frac=verification.mtf_max_field_frac,
                        mtf_bands=after_bands,
                        max_rms_spot_radius_um=verification.max_rms_spot_radius_um,
                    )
                    after_rms = verification.max_rms_spot_radius_um
                    if after_rms is None:
                        floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                            before_metrics, after_metrics
                        )
                        trials.append(
                            _variable_trial(
                                variable="compound_continuation",
                                surface_index=focus_change.surface_index,
                                before=focus_change.before,
                                after=focus_change.after,
                                coupled_variable="radius",
                                coupled_surface_index=radius_change.surface_index,
                                coupled_before=radius_change.before,
                                coupled_after=radius_change.after,
                                merit_before=merit_before,
                                merit_after=merit_after,
                                image_quality_floor_gap_before=floor_gap_before,
                                image_quality_floor_gap_after=floor_gap_after,
                                image_quality_floor_gap_closure=floor_gap_closure,
                                verification_status=verification.status,
                                status="failed",
                                reason=f"compound continuation {label}; verification had no max RMS",
                            )
                        )
                        continue

                    rms_improvement = before_max_rms_spot_radius_um - after_rms
                    rms_improvement_pct = (
                        rms_improvement / before_max_rms_spot_radius_um * 100.0
                        if before_max_rms_spot_radius_um
                        else 0.0
                    )
                    mtf_non_regressed = before_mtf_max_field_frac is None or (
                        verification.mtf_max_field_frac is not None
                        and verification.mtf_max_field_frac >= before_mtf_max_field_frac
                    )
                    mtf_band_non_regressed = mtf_multiband_non_regressed(
                        before_mtf_bands,
                        after_bands,
                    )
                    floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                        before_metrics,
                        after_metrics,
                    )
                    field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                        before_mtf_bands,
                        after_bands,
                    )
                    efl_locked = (
                        after_paraxial.effective_focal_length_mm is not None
                        and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
                    )
                    accepted = (
                        verification.status == "passed"
                        and rms_improvement >= 0.10
                        and mtf_non_regressed
                        and mtf_band_non_regressed
                        and field_weighted_non_regressed
                        and efl_locked
                    )
                    promotion_score = _merit_promotion_score(
                        accepted=accepted,
                        verification_status=verification.status,
                        rms_improvement_um=rms_improvement,
                        mtf_field_non_regressed=mtf_non_regressed,
                        mtf_band_non_regressed=mtf_band_non_regressed,
                        mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                        efl_locked=efl_locked,
                        image_quality_floor_gap_closure=floor_gap_closure,
                    )
                    if accepted:
                        trial_status = "accepted"
                        trial_reason = f"compound continuation {label} passed RMS/MTF/EFL gates"
                    else:
                        failed_gates: list[str] = []
                        if verification.status != "passed":
                            failed_gates.append(f"verification={verification.status}")
                        if rms_improvement < 0.10:
                            failed_gates.append("RMS improvement below 0.10 um")
                        if not mtf_non_regressed:
                            failed_gates.append("MTF field fraction regressed")
                        if not mtf_band_non_regressed:
                            failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                        if not field_weighted_non_regressed:
                            failed_gates.append("field-weighted MTF regressed")
                        if not efl_locked:
                            failed_gates.append("EFL not locked")
                        trial_status = "rejected"
                        trial_reason = (
                            f"compound continuation {label}; "
                            f"{'; '.join(failed_gates) or 'promotion gates did not pass'}"
                        )
                    trial = _variable_trial(
                        variable="compound_continuation",
                        surface_index=focus_change.surface_index,
                        before=focus_change.before,
                        after=focus_change.after,
                        coupled_variable="radius",
                        coupled_surface_index=radius_change.surface_index,
                        coupled_before=radius_change.before,
                        coupled_after=radius_change.after,
                        merit_before=merit_before,
                        merit_after=merit_after,
                        rms_improvement_um=rms_improvement,
                        rms_improvement_pct=rms_improvement_pct,
                        promotion_score=promotion_score,
                        image_quality_floor_gap_before=floor_gap_before,
                        image_quality_floor_gap_after=floor_gap_after,
                        image_quality_floor_gap_closure=floor_gap_closure,
                        verification_status=verification.status,
                        mtf_field_non_regressed=mtf_non_regressed,
                        mtf_band_non_regressed=mtf_band_non_regressed,
                        mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                        efl_locked=efl_locked,
                        status=trial_status,
                        reason=trial_reason,
                    )
                    trials.append(trial)
                    probe = OptimizationMeritProbe(
                        status="proposal" if accepted else "warning",
                        engine="optiland.compound_continuation_replay",
                        summary=(
                            "protected compound continuation recovered MTF-band gates"
                            if accepted
                            else "compound continuation ran, but verification did not pass gates"
                        ),
                        operand="rms_spot_size",
                        probe_purpose=probe_purpose,
                        variable_priority=list(variable_priority),
                        field_samples=list(field_samples),
                        target_efl_mm=target_efl_mm,
                        target_total_track_mm=max_total_track_mm,
                        merit_before=merit_before,
                        merit_after=merit_after,
                        rms_improvement_um=rms_improvement,
                        rms_improvement_pct=rms_improvement_pct,
                        variable_candidates=variable_candidates,
                        candidate_trials=[],
                        variable_changes=[focus_change, radius_change],
                        verification=verification,
                        before_metrics=before_metrics,
                        after_metrics=after_metrics,
                        diagnostics=[
                            *base_diagnostics,
                            f"finite RMS operand fields: {field_samples}",
                            f"compound continuation branch={label}",
                            f"source focus trial status={focus_trial.status}",
                            f"MTF 50/100/150/200/250 lp/mm non-regressed={mtf_band_non_regressed}",
                            f"MTF field-weighted score non-regressed={field_weighted_non_regressed}",
                            f"image-quality floor gap closure={floor_gap_closure}",
                            f"promotion score={promotion_score:.3f}",
                        ],
                        applied_to_payload=False,
                    )
                    rank = _merit_probe_rank(
                        accepted=accepted,
                        rms_improvement_um=rms_improvement,
                        promotion_score=promotion_score,
                        image_quality_floor_gap_closure=floor_gap_closure,
                        probe_purpose=probe_purpose,
                    )
                    probe_ranks.append((probe, rank))
                except Exception as exc:  # noqa: BLE001
                    trials.append(
                        _variable_trial(
                            variable="compound_continuation",
                            surface_index=focus_change.surface_index,
                            before=focus_change.before,
                            after=focus_change.after,
                            coupled_variable="radius",
                            coupled_surface_index=radius_change.surface_index,
                            coupled_before=radius_change.before,
                            coupled_after=radius_change.after,
                            status="failed",
                            reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                        )
                    )

    diagnostics = [f"compound continuation trials={len(trials)}"]
    accepted_trials = [trial for trial in trials if trial.status == "accepted"]
    if accepted_trials:
        best = max(
            accepted_trials,
            key=lambda trial: (
                trial.image_quality_floor_gap_closure
                if trial.image_quality_floor_gap_closure is not None
                else -math.inf,
                trial.rms_improvement_um if trial.rms_improvement_um is not None else -math.inf,
            ),
        )
        diagnostics.append(
            f"best compound continuation=focus_position S{best.surface_index} + "
            f"{best.coupled_variable} S{best.coupled_surface_index} "
            f"closure={best.image_quality_floor_gap_closure:+.3f}"
        )
    return trials, probe_ranks, diagnostics


def _compound_merit_replay(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
    accepted_trials: list[OptimizationVariableTrial],
    current_best_probe: OptimizationMeritProbe,
    variable_candidates: list[OptimizationVariableCandidate],
    before_metrics: OptimizationMetricSnapshot,
    before_mtf_max_field_frac: float | None,
    before_mtf_bands: MtfBandMetrics,
    before_max_rms_spot_radius_um: float,
) -> tuple[list[OptimizationVariableTrial], OptimizationMeritProbe | None, list[str]]:
    ranked_changes: list[tuple[OptimizationVariableTrial, OptimizationVariableChange]] = []
    seen_variables: set[tuple[str, int]] = set()
    for trial in sorted(
        accepted_trials,
        key=lambda item: (
            item.promotion_score if item.promotion_score is not None else -math.inf,
            (
                item.image_quality_floor_gap_closure
                if item.image_quality_floor_gap_closure is not None
                else -math.inf
            ),
            item.rms_improvement_um if item.rms_improvement_um is not None else -math.inf,
        ),
        reverse=True,
    ):
        change = _change_from_trial(trial)
        if change is None:
            continue
        change_key = (change.variable, change.surface_index)
        if change_key in seen_variables:
            continue
        seen_variables.add(change_key)
        ranked_changes.append((trial, change))
        if len(ranked_changes) >= _MAX_COMPOUND_MERIT_VARIABLES:
            break
    if len(ranked_changes) < 2:
        return [], None, []

    trials: list[OptimizationVariableTrial] = []
    best_probe: OptimizationMeritProbe | None = None
    best_rank: tuple[float, float, int] | None = None
    best_single_rms = current_best_probe.rms_improvement_um
    min_promoted_rms = (
        best_single_rms if best_single_rms is not None else 0.0
    ) + _COMPOUND_MERIT_MIN_EXTRA_RMS_UM

    max_size = min(_MAX_COMPOUND_MERIT_VARIABLES, len(ranked_changes))
    for size in range(2, max_size + 1):
        for combo in combinations(ranked_changes, size):
            combo_trials = [item[0] for item in combo]
            combo_changes = [item[1] for item in combo]
            label = _change_set_label(combo_changes)
            surface_index = combo_changes[0].surface_index
            try:
                optic = _load_probe_optic(source_zmx, nominal_fov_deg)
                _apply_radius_changes(optic, radius_changes)
                _apply_baseline_variable_changes(optic, baseline_variable_changes)
                for change in combo_changes:
                    _apply_variable_change(optic, change)
                after_paraxial = compute_paraxial_summary(optic)
                verification = _verify_probe_optic(
                    optic,
                    nominal_fov_deg,
                    max_total_track_mm,
                )
                after_rms = verification.max_rms_spot_radius_um
                if after_rms is None:
                    trials.append(
                        _variable_trial(
                            variable="compound_merit",
                            surface_index=surface_index,
                            verification_status=verification.status,
                            status="failed",
                            reason=f"{label}; compound verification had no max RMS",
                        )
                    )
                    continue

                rms_improvement = before_max_rms_spot_radius_um - after_rms
                rms_improvement_pct = (
                    rms_improvement / before_max_rms_spot_radius_um * 100.0
                    if before_max_rms_spot_radius_um
                    else 0.0
                )
                mtf_non_regressed = before_mtf_max_field_frac is None or (
                    verification.mtf_max_field_frac is not None
                    and verification.mtf_max_field_frac >= before_mtf_max_field_frac
                )
                after_bands = mtf_bands_from_snapshot(verification)
                after_metrics = _metric_snapshot(
                    after_paraxial,
                    mtf_max_field_frac=verification.mtf_max_field_frac,
                    mtf_bands=after_bands,
                    max_rms_spot_radius_um=after_rms,
                )
                mtf_band_non_regressed = mtf_multiband_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                    before_metrics,
                    after_metrics,
                )
                field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                    before_mtf_bands,
                    after_bands,
                )
                efl_locked = (
                    after_paraxial.effective_focal_length_mm is not None
                    and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
                )
                gate_passed = (
                    verification.status == "passed"
                    and rms_improvement >= 0.10
                    and mtf_non_regressed
                    and mtf_band_non_regressed
                    and field_weighted_non_regressed
                    and efl_locked
                )
                promotion_score = _merit_promotion_score(
                    accepted=gate_passed,
                    verification_status=verification.status,
                    rms_improvement_um=rms_improvement,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    image_quality_floor_gap_closure=floor_gap_closure,
                )
                beats_single = rms_improvement >= min_promoted_rms
                if gate_passed:
                    reason = f"compound branch {label} passed gates" + (
                        " and beats best single-variable branch"
                        if beats_single
                        else " but did not beat best single-variable branch"
                    )
                    trial_status = "accepted"
                else:
                    failed_gates: list[str] = []
                    if verification.status != "passed":
                        failed_gates.append(f"verification={verification.status}")
                    if rms_improvement < 0.10:
                        failed_gates.append("RMS improvement below 0.10 um")
                    if not mtf_non_regressed:
                        failed_gates.append("MTF field fraction regressed")
                    if not mtf_band_non_regressed:
                        failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                    if not field_weighted_non_regressed:
                        failed_gates.append("field-weighted MTF regressed")
                    if not efl_locked:
                        failed_gates.append("EFL not locked")
                    reason = f"compound branch {label}; {'; '.join(failed_gates)}"
                    trial_status = "rejected"

                trials.append(
                    _variable_trial(
                        variable="compound_merit",
                        surface_index=surface_index,
                        status=trial_status,
                        reason=reason,
                        rms_improvement_um=rms_improvement,
                        rms_improvement_pct=rms_improvement_pct,
                        promotion_score=promotion_score,
                        image_quality_floor_gap_before=floor_gap_before,
                        image_quality_floor_gap_after=floor_gap_after,
                        image_quality_floor_gap_closure=floor_gap_closure,
                        verification_status=verification.status,
                        mtf_field_non_regressed=mtf_non_regressed,
                        mtf_band_non_regressed=mtf_band_non_regressed,
                        mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                        efl_locked=efl_locked,
                    )
                )
                if gate_passed and beats_single:
                    probe = OptimizationMeritProbe(
                        status="proposal",
                        engine="optiland.least_squares",
                        summary=(
                            "protected RMS merit probe promoted a compound multi-variable branch"
                        ),
                        operand=current_best_probe.operand,
                        probe_purpose=current_best_probe.probe_purpose,
                        variable_priority=current_best_probe.variable_priority,
                        field_samples=current_best_probe.field_samples,
                        target_efl_mm=target_efl_mm,
                        target_total_track_mm=max_total_track_mm,
                        merit_before=current_best_probe.merit_before,
                        merit_after=None,
                        rms_improvement_um=rms_improvement,
                        rms_improvement_pct=rms_improvement_pct,
                        variable_candidates=variable_candidates,
                        candidate_trials=[],
                        variable_changes=combo_changes,
                        verification=verification,
                        before_metrics=before_metrics,
                        after_metrics=after_metrics,
                        diagnostics=current_best_probe.diagnostics,
                        failures=current_best_probe.failures,
                        applied_to_payload=False,
                    )
                    rank = (promotion_score, rms_improvement, len(combo_trials))
                    if best_rank is None or rank > best_rank:
                        best_probe = probe
                        best_rank = rank
            except Exception as exc:  # noqa: BLE001
                trials.append(
                    _variable_trial(
                        variable="compound_merit",
                        surface_index=surface_index,
                        status="failed",
                        reason=f"{label}; {type(exc).__name__}: {str(exc)[:120]}",
                    )
                )

    diagnostics = [f"compound merit trials={len(trials)}"]
    if best_probe is not None:
        diagnostics.append(
            f"best compound={_change_set_label(best_probe.variable_changes)} "
            f"rms_delta={best_probe.rms_improvement_um:+.2f}um"
        )
    return trials, best_probe, diagnostics


def _load_probe_optic(source_zmx: str, nominal_fov_deg: float | None):
    """Load a zmx for optimizer probing without leaking parser chatter."""
    sink = StringIO()
    with (
        warnings.catch_warnings(),
        redirect_stdout(sink),
        redirect_stderr(sink),
    ):
        warnings.simplefilter("ignore")
        optic = load_normalized_zmx(ZMX_AMMO_DIR / source_zmx)
        if nominal_fov_deg is not None:
            regularize_fields_to_angle(optic, nominal_fov_deg)
    return optic


def _bounded_radius(value: float) -> tuple[float, float] | None:
    return _bounded_fraction(value, _RADIUS_BOUND_FRAC)


def _bounded_merit_variable(
    variable: str,
    value: float,
) -> tuple[float, float] | None:
    if variable == "radius":
        return _bounded_fraction(value, _MERIT_RADIUS_BOUND_FRAC)
    if variable == "thickness":
        bounds = _bounded_fraction(value, _MERIT_THICKNESS_BOUND_FRAC)
        if bounds is None:
            return None
        lo = max(bounds[0], _MERIT_MIN_THICKNESS_MM)
        hi = bounds[1]
        return (lo, hi) if lo < hi else None
    return None


def _bounded_fraction(value: float, fraction: float) -> tuple[float, float] | None:
    lo = value * (1.0 - fraction)
    hi = value * (1.0 + fraction)
    lo, hi = min(lo, hi), max(lo, hi)
    return (lo, hi) if lo < hi else None


def _image_surface_index(optic) -> int:
    surfaces = getattr(optic.surfaces, "surfaces", None)
    if surfaces is not None:
        return len(surfaces) - 1
    return len(optic.surface_group.surfaces) - 1


def _apply_radius_changes(
    optic,
    radius_changes: tuple[tuple[int, float], ...],
) -> None:
    for surface_index, value in radius_changes:
        optic.surfaces.surfaces[surface_index].geometry.radius = value


def _set_surface_thickness(optic, surface_index: int, value: float) -> float:
    before = _surface_thickness(optic, surface_index)
    if before is None:
        raise ValueError("current surface thickness is non-finite")
    delta = value - before
    for surface in optic.surfaces.surfaces[surface_index + 1 :]:
        surface.geometry.cs.z += delta
    if 0 <= surface_index < len(optic.surfaces.surfaces):
        optic.surfaces.surfaces[surface_index].thickness = value
    written = _surface_thickness(optic, surface_index)
    if written is None or not math.isclose(written, value, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("surface thickness write-back check failed")
    return written


def _apply_variable_change(optic, change: OptimizationVariableChange) -> float:
    if change.variable == "radius":
        optic.surfaces.surfaces[change.surface_index].geometry.radius = change.after
        written = _finite_float(optic.surfaces.radii[change.surface_index])
    elif change.variable in {"thickness", "stop_position", "focus_position"}:
        written = _set_surface_thickness(optic, change.surface_index, change.after)
    else:
        raise ValueError(f"unsupported coupled variable: {change.variable}")
    if written is None or not math.isclose(written, change.after, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError(f"{change.variable} write-back check failed")
    return written


def _apply_baseline_variable_changes(
    optic,
    baseline_variable_changes: tuple[tuple[str, int, float], ...],
) -> None:
    for variable, surface_index, value in baseline_variable_changes:
        if variable == "radius":
            optic.surfaces.surfaces[surface_index].geometry.radius = value
            written = _finite_float(optic.surfaces.radii[surface_index])
        elif variable in {"thickness", "stop_position", "focus_position"}:
            written = _set_surface_thickness(optic, surface_index, value)
        else:
            raise ValueError(f"unsupported baseline variable: {variable}")
        if written is None or not math.isclose(written, value, rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError(f"{variable} baseline write-back check failed")


def _variable_value(optic, variable: str, surface_index: int) -> float | None:
    if variable == "radius":
        return _finite_float(optic.surfaces.radii[surface_index])
    if variable in {"thickness", "stop_position", "focus_position"}:
        return _surface_thickness(optic, surface_index)
    return None


def _mtf_has_nan(mtf) -> bool:
    for v in mtf.rms_spot_radius_um_by_field:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return True
    for f in mtf.fields:
        for v in (*f.sagittal, *f.tangential):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return True
    return False


def _mtf_with_fallback(optic, nominal_fov_deg: float):
    half = nominal_fov_deg / 2.0
    last_err: Exception | None = None
    for fracs in MTF_FIELD_FALLBACK_SETS:
        optic.set_field_type("angle")
        optic.fields.fields.clear()
        for frac in fracs:
            optic.add_field(y=half * frac)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                result = compute_mtf(optic, wavelength_nm=_PRIMARY_WL_NM)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        if not _mtf_has_nan(result):
            return result, fracs[-1]
        last_err = RuntimeError(f"MTF returned NaN at field set {fracs}")
    raise RuntimeError(f"MTF unusable for all field sets: {last_err}")


def _ray_trace_is_finite(trace) -> bool:
    if trace.has_vignetting or not trace.sampled_paths:
        return False
    for path in trace.sampled_paths:
        if not path.reaches_image:
            return False
        for x, z in path.points_mm:
            if not (math.isfinite(x) and math.isfinite(z)):
                return False
    return True


def _metric_snapshot(
    paraxial,
    *,
    mtf_max_field_frac: float | None = None,
    mtf_bands: MtfBandMetrics | None = None,
    max_rms_spot_radius_um: float | None = None,
) -> OptimizationMetricSnapshot:
    bands = mtf_bands or MtfBandMetrics()
    return OptimizationMetricSnapshot(
        effective_focal_length_mm=paraxial.effective_focal_length_mm,
        f_number=paraxial.f_number,
        total_track_mm=paraxial.total_track_mm,
        mtf_max_field_frac=mtf_max_field_frac,
        mtf_50lpmm_min=bands.min_50,
        mtf_50lpmm_avg=bands.avg_50,
        mtf_100lpmm_min=bands.min_100,
        mtf_100lpmm_avg=bands.avg_100,
        mtf_150lpmm_min=bands.min_150,
        mtf_150lpmm_avg=bands.avg_150,
        mtf_200lpmm_min=bands.min_200,
        mtf_200lpmm_avg=bands.avg_200,
        mtf_250lpmm_min=bands.min_250,
        mtf_250lpmm_avg=bands.avg_250,
        mtf_multiband_min_score=bands.multiband_min_score,
        mtf_field_weighted_score=bands.field_weighted_score,
        max_rms_spot_radius_um=max_rms_spot_radius_um,
    )


def mtf_band_summary(mtf, target_lpmm: float = 100.0) -> tuple[float | None, float | None]:
    """Return min/avg MTF near a target spatial frequency across fields and S/T."""
    if not mtf.freq_lp_per_mm or not mtf.fields:
        return None, None
    idx = min(
        range(len(mtf.freq_lp_per_mm)),
        key=lambda i: abs(mtf.freq_lp_per_mm[i] - target_lpmm),
    )
    values: list[float] = []
    for field in mtf.fields:
        for curve in (field.sagittal, field.tangential):
            if idx < len(curve):
                value = curve[idx]
                if math.isfinite(value):
                    values.append(value)
    if not values:
        return None, None
    return min(values), sum(values) / len(values)


def _field_weights(count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    raw = [1.0 + idx / (count - 1) for idx in range(count)]
    total = sum(raw)
    return [value / total for value in raw]


def _mtf_field_weighted_band_score(mtf, target_lpmm: float) -> float | None:
    if not mtf.freq_lp_per_mm or not mtf.fields:
        return None
    idx = min(
        range(len(mtf.freq_lp_per_mm)),
        key=lambda i: abs(mtf.freq_lp_per_mm[i] - target_lpmm),
    )
    weights = _field_weights(len(mtf.fields))
    weighted_sum = 0.0
    used_weight = 0.0
    for field, weight in zip(mtf.fields, weights, strict=True):
        values: list[float] = []
        for curve in (field.sagittal, field.tangential):
            if idx < len(curve):
                value = curve[idx]
                if math.isfinite(value):
                    values.append(value)
        if not values:
            continue
        weighted_sum += (sum(values) / len(values)) * weight
        used_weight += weight
    if used_weight == 0.0:
        return None
    return weighted_sum / used_weight


def mtf_multiband_summary(mtf) -> MtfBandMetrics:
    """Return conservative 50/100/150/200/250 lp/mm MTF metrics for proposal gating."""
    min_values: list[float | None] = []
    avg_values: list[float | None] = []
    field_weighted_values: list[float | None] = []
    for target in _MTF_BANDS_LPMM:
        min_value, avg_value = mtf_band_summary(mtf, target)
        min_values.append(min_value)
        avg_values.append(avg_value)
        field_weighted_values.append(_mtf_field_weighted_band_score(mtf, target))

    score: float | None = None
    if all(value is not None for value in min_values):
        score = min(value for value in min_values if value is not None)
    field_weighted_score: float | None = None
    if all(value is not None for value in field_weighted_values):
        field_weighted_score = sum(
            value * weight
            for value, weight in zip(field_weighted_values, _MTF_BAND_WEIGHTS, strict=True)
            if value is not None
        )

    return MtfBandMetrics(
        min_50=min_values[0],
        avg_50=avg_values[0],
        min_100=min_values[1],
        avg_100=avg_values[1],
        min_150=min_values[2],
        avg_150=avg_values[2],
        min_200=min_values[3],
        avg_200=avg_values[3],
        min_250=min_values[4],
        avg_250=avg_values[4],
        multiband_min_score=score,
        field_weighted_score=field_weighted_score,
    )


def mtf_bands_from_snapshot(snapshot: object | None) -> MtfBandMetrics:
    """Extract cached MTF band metrics from a pydantic snapshot/verification."""
    if snapshot is None:
        return MtfBandMetrics()
    return MtfBandMetrics(
        min_50=getattr(snapshot, "mtf_50lpmm_min", None),
        avg_50=getattr(snapshot, "mtf_50lpmm_avg", None),
        min_100=getattr(snapshot, "mtf_100lpmm_min", None),
        avg_100=getattr(snapshot, "mtf_100lpmm_avg", None),
        min_150=getattr(snapshot, "mtf_150lpmm_min", None),
        avg_150=getattr(snapshot, "mtf_150lpmm_avg", None),
        min_200=getattr(snapshot, "mtf_200lpmm_min", None),
        avg_200=getattr(snapshot, "mtf_200lpmm_avg", None),
        min_250=getattr(snapshot, "mtf_250lpmm_min", None),
        avg_250=getattr(snapshot, "mtf_250lpmm_avg", None),
        multiband_min_score=getattr(snapshot, "mtf_multiband_min_score", None),
        field_weighted_score=getattr(snapshot, "mtf_field_weighted_score", None),
    )


def _non_regressed(before: float | None, after: float | None) -> bool:
    return before is None or (after is not None and after + _MTF_NON_REGRESSION_TOL >= before)


def mtf_multiband_non_regressed(
    before: MtfBandMetrics,
    after: MtfBandMetrics,
) -> bool:
    return all(
        _non_regressed(before_value, after_value)
        for before_value, after_value in zip(before.min_values, after.min_values, strict=True)
    ) and _non_regressed(before.multiband_min_score, after.multiband_min_score)


def mtf_field_weighted_non_regressed(
    before: MtfBandMetrics,
    after: MtfBandMetrics,
) -> bool:
    return _non_regressed(before.field_weighted_score, after.field_weighted_score)


def _verify_probe_optic(
    optic,
    nominal_fov_deg: float,
    max_total_track_mm: float | None,
) -> OptimizationVerification:
    """Re-run first-order safety checks after a protected optimizer proposal."""
    diagnostics: list[str] = []
    paraxial_ok = False
    ray_trace_ok = False
    mtf_ok = False
    mtf_frac: float | None = None
    mtf_bands = MtfBandMetrics()
    max_rms: float | None = None

    try:
        paraxial = compute_paraxial_summary(optic)
        paraxial_ok = math.isfinite(paraxial.effective_focal_length_mm) and math.isfinite(
            paraxial.total_track_mm
        )
        if max_total_track_mm is not None and paraxial.total_track_mm > max_total_track_mm:
            paraxial_ok = False
            diagnostics.append(
                f"post-tweak TTL {paraxial.total_track_mm:.3f} mm exceeds "
                f"{max_total_track_mm:.3f} mm ceiling"
            )
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(f"paraxial check failed: {type(exc).__name__}: {str(exc)[:140]}")

    try:
        trace = trace_optic(
            optic,
            assembly_name="protected-optimizer-probe",
            wavelength_nm=_PRIMARY_WL_NM,
        )
        ray_trace_ok = _ray_trace_is_finite(trace)
        if not ray_trace_ok:
            diagnostics.append(
                "post-tweak ray trace had vignetting, missing paths, or non-finite points"
            )
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(f"ray trace check failed: {type(exc).__name__}: {str(exc)[:140]}")

    try:
        mtf, mtf_frac = _mtf_with_fallback(optic, nominal_fov_deg)
        mtf_ok = True
        mtf_bands = mtf_multiband_summary(mtf)
        finite_rms = [v for v in mtf.rms_spot_radius_um_by_field if math.isfinite(v)]
        max_rms = max(finite_rms) if finite_rms else None
    except Exception as exc:  # noqa: BLE001
        diagnostics.append(f"MTF check failed: {type(exc).__name__}: {str(exc)[:140]}")

    if not (paraxial_ok and ray_trace_ok and mtf_ok):
        return OptimizationVerification(
            status="failed",
            summary="post-tweak verification failed; proposal must remain diagnostic-only",
            paraxial_ok=paraxial_ok,
            ray_trace_ok=ray_trace_ok,
            mtf_ok=mtf_ok,
            mtf_max_field_frac=mtf_frac,
            mtf_50lpmm_min=mtf_bands.min_50,
            mtf_50lpmm_avg=mtf_bands.avg_50,
            mtf_100lpmm_min=mtf_bands.min_100,
            mtf_100lpmm_avg=mtf_bands.avg_100,
            mtf_150lpmm_min=mtf_bands.min_150,
            mtf_150lpmm_avg=mtf_bands.avg_150,
            mtf_200lpmm_min=mtf_bands.min_200,
            mtf_200lpmm_avg=mtf_bands.avg_200,
            mtf_250lpmm_min=mtf_bands.min_250,
            mtf_250lpmm_avg=mtf_bands.avg_250,
            mtf_multiband_min_score=mtf_bands.multiband_min_score,
            mtf_field_weighted_score=mtf_bands.field_weighted_score,
            max_rms_spot_radius_um=max_rms,
            diagnostics=diagnostics,
        )

    if mtf_frac is not None and mtf_frac < 1.0:
        return OptimizationVerification(
            status="warning",
            summary=(
                "post-tweak ray trace is finite and MTF evaluates to "
                f"{format_mtf_field_fraction(mtf_frac)} field; full-field MTF remains unproven"
            ),
            paraxial_ok=True,
            ray_trace_ok=True,
            mtf_ok=True,
            mtf_max_field_frac=mtf_frac,
            mtf_50lpmm_min=mtf_bands.min_50,
            mtf_50lpmm_avg=mtf_bands.avg_50,
            mtf_100lpmm_min=mtf_bands.min_100,
            mtf_100lpmm_avg=mtf_bands.avg_100,
            mtf_150lpmm_min=mtf_bands.min_150,
            mtf_150lpmm_avg=mtf_bands.avg_150,
            mtf_200lpmm_min=mtf_bands.min_200,
            mtf_200lpmm_avg=mtf_bands.avg_200,
            mtf_250lpmm_min=mtf_bands.min_250,
            mtf_250lpmm_avg=mtf_bands.avg_250,
            mtf_multiband_min_score=mtf_bands.multiband_min_score,
            mtf_field_weighted_score=mtf_bands.field_weighted_score,
            max_rms_spot_radius_um=max_rms,
            diagnostics=[*diagnostics, "full-field MTF fallback was required"],
        )

    return OptimizationVerification(
        status="passed",
        summary="post-tweak paraxial, ray trace, and full-field MTF checks passed",
        paraxial_ok=True,
        ray_trace_ok=True,
        mtf_ok=True,
        mtf_max_field_frac=mtf_frac,
        mtf_50lpmm_min=mtf_bands.min_50,
        mtf_50lpmm_avg=mtf_bands.avg_50,
        mtf_100lpmm_min=mtf_bands.min_100,
        mtf_100lpmm_avg=mtf_bands.avg_100,
        mtf_150lpmm_min=mtf_bands.min_150,
        mtf_150lpmm_avg=mtf_bands.avg_150,
        mtf_200lpmm_min=mtf_bands.min_200,
        mtf_200lpmm_avg=mtf_bands.avg_200,
        mtf_250lpmm_min=mtf_bands.min_250,
        mtf_250lpmm_avg=mtf_bands.avg_250,
        mtf_multiband_min_score=mtf_bands.multiband_min_score,
        mtf_field_weighted_score=mtf_bands.field_weighted_score,
        max_rms_spot_radius_um=max_rms,
        diagnostics=diagnostics,
    )


def _stop_surface_index(optic) -> int | None:
    for idx, surface in enumerate(optic.surfaces.surfaces):
        if getattr(surface, "is_stop", False):
            return idx
    return None


def _chief_ray_height(optic, surface_index: int) -> float | None:
    try:
        y, _ = optic.paraxial.chief_ray()
        return _finite_float(np.asarray(y)[surface_index])
    except Exception:
        return None


def _recovery_trial_status(
    verification: OptimizationVerification,
    *,
    before_mtf_max_field_frac: float | None,
    rms_delta_um: float | None,
) -> tuple[str, str]:
    recovered = (
        verification.status == "passed"
        and verification.mtf_max_field_frac is not None
        and verification.mtf_max_field_frac >= 1.0
    )
    if recovered:
        return "recovered", "full-field MTF reached 1.0 and verification passed"

    field_non_regressed = before_mtf_max_field_frac is None or (
        verification.mtf_max_field_frac is not None
        and verification.mtf_max_field_frac >= before_mtf_max_field_frac
    )
    rms_improved = rms_delta_um is not None and rms_delta_um >= 0.10
    if verification.ray_trace_ok and verification.mtf_ok and field_non_regressed and rms_improved:
        return (
            "improved",
            "RMS improved but full-field MTF still did not pass the 1.0 field gate",
        )
    return (
        "rejected",
        "full-field recovery gate did not pass or local image-quality evidence regressed",
    )


def _verification_metric_snapshot(
    paraxial,
    verification: OptimizationVerification,
) -> OptimizationMetricSnapshot | None:
    if verification.mtf_max_field_frac is None:
        return None
    return _metric_snapshot(
        paraxial,
        mtf_max_field_frac=verification.mtf_max_field_frac,
        mtf_bands=mtf_bands_from_snapshot(verification),
        max_rms_spot_radius_um=verification.max_rms_spot_radius_um,
    )


def _verification_floor_gap(
    paraxial,
    verification: OptimizationVerification,
) -> float | None:
    return image_quality_floor_gap_score(_verification_metric_snapshot(paraxial, verification))


@lru_cache(maxsize=64)
def protected_edge_field_stability_scan(
    source_zmx: str,
    nominal_fov_deg: float,
) -> tuple[EdgeFieldStabilityPoint, ...]:
    """Probe explicit edge-field fractions without mutating the delivered payload."""
    points: list[EdgeFieldStabilityPoint] = []
    half_fov = nominal_fov_deg / 2.0
    for field_frac in _EDGE_FIELD_SCAN_FRACS:
        try:
            optic = _load_probe_optic(source_zmx, nominal_fov_deg)
            optic.set_field_type("angle")
            optic.fields.fields.clear()
            for frac in (0.0, 0.5, 0.7, field_frac):
                optic.add_field(y=half_fov * frac)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mtf = compute_mtf(optic, wavelength_nm=_PRIMARY_WL_NM)
            rms_values = [
                value
                for value in mtf.rms_spot_radius_um_by_field
                if value is not None and math.isfinite(value)
            ]
            edge_rms = (
                mtf.rms_spot_radius_um_by_field[-1] if mtf.rms_spot_radius_um_by_field else None
            )
            if _mtf_has_nan(mtf) or edge_rms is None or not math.isfinite(edge_rms):
                points.append(
                    EdgeFieldStabilityPoint(
                        field_frac=field_frac,
                        status="unstable",
                        rms_spot_radius_um=None,
                        reason="MTF or RMS returned NaN at this edge-field fraction",
                    )
                )
                continue
            points.append(
                EdgeFieldStabilityPoint(
                    field_frac=field_frac,
                    status="pass",
                    rms_spot_radius_um=edge_rms,
                    reason=(
                        f"finite MTF/RMS through {format_mtf_field_fraction(field_frac)} field; "
                        f"max RMS {max(rms_values):.2f} um"
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001
            points.append(
                EdgeFieldStabilityPoint(
                    field_frac=field_frac,
                    status="failed",
                    rms_spot_radius_um=None,
                    reason=f"{type(exc).__name__}: {str(exc)[:140]}",
                )
            )
    return tuple(points)


def _full_field_recovery_trial(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    max_total_track_mm: float | None,
    before_effective_focal_length_mm: float | None,
    before_total_track_mm: float | None,
    before_mtf_max_field_frac: float | None,
    before_max_rms_spot_radius_um: float | None,
    variable_family: str,
    surface_index: int,
    before: float | None,
    after: float | None,
    delta: float | None,
) -> FullFieldRecoveryTrial:
    try:
        optic = _load_probe_optic(source_zmx, nominal_fov_deg)
        if variable_family == "stop_position":
            if after is None:
                raise ValueError("stop-position target is missing")
            _set_surface_thickness(optic, surface_index, after)
        elif variable_family == "chief_ray_height":
            if before is None or delta is None:
                raise ValueError("chief-ray target is missing")
            before_z = _finite_float(optic.surfaces.surfaces[surface_index].geometry.cs.z)
            ChiefRayHeightThicknessSolve(optic, surface_index, before + delta).apply()
            after_z = _finite_float(optic.surfaces.surfaces[surface_index].geometry.cs.z)
            if before_z is not None and after_z is not None:
                z_shift = after_z - before_z
                if abs(z_shift) > _FULL_FIELD_MAX_CHIEF_RAY_Z_SHIFT_MM:
                    return FullFieldRecoveryTrial(
                        variable_family=variable_family,
                        surface_index=surface_index,
                        before=before,
                        after=before + delta,
                        delta=delta,
                        status="skipped",
                        reason=(
                            f"chief-ray solve z-shift {z_shift:+.3f} mm exceeds "
                            f"{_FULL_FIELD_MAX_CHIEF_RAY_Z_SHIFT_MM:.3f} mm guard"
                        ),
                    )
        else:
            raise ValueError(f"unsupported recovery variable family: {variable_family}")

        paraxial = compute_paraxial_summary(optic)
        verification = _verify_probe_optic(optic, nominal_fov_deg, max_total_track_mm)
        rms_delta = (
            before_max_rms_spot_radius_um - verification.max_rms_spot_radius_um
            if before_max_rms_spot_radius_um is not None
            and verification.max_rms_spot_radius_um is not None
            else None
        )
        status, reason = _recovery_trial_status(
            verification,
            before_mtf_max_field_frac=before_mtf_max_field_frac,
            rms_delta_um=rms_delta,
        )
        metrics = _verification_metric_snapshot(paraxial, verification)
        floor_gap = image_quality_floor_gap_score(metrics)
        if variable_family == "chief_ray_height":
            reason = f"{reason}; height delta={delta:+.3f}"
        variable_changes: list[OptimizationVariableChange] = []
        if variable_family == "stop_position" and before is not None and after is not None:
            variable_changes.append(
                OptimizationVariableChange(
                    variable="stop_position",
                    surface_index=surface_index,
                    before=before,
                    after=after,
                    delta=after - before,
                    delta_pct=((after - before) / before * 100.0 if before else 0.0),
                )
            )
        return FullFieldRecoveryTrial(
            variable_family=variable_family,
            surface_index=surface_index,
            before=before,
            after=after if variable_family == "stop_position" else (before or 0.0) + (delta or 0.0),
            delta=delta,
            status=status,
            reason=reason,
            mtf_max_field_frac=verification.mtf_max_field_frac,
            rms_delta_um=rms_delta,
            efl_delta_mm=(
                paraxial.effective_focal_length_mm - before_effective_focal_length_mm
                if before_effective_focal_length_mm is not None
                and paraxial.effective_focal_length_mm is not None
                else None
            ),
            total_track_delta_mm=(
                paraxial.total_track_mm - before_total_track_mm
                if before_total_track_mm is not None and paraxial.total_track_mm is not None
                else None
            ),
            image_quality_floor_gap_score=floor_gap,
            metrics=metrics,
            variable_changes=variable_changes,
        )
    except Exception as exc:  # noqa: BLE001
        return FullFieldRecoveryTrial(
            variable_family=variable_family,
            surface_index=surface_index,
            before=before,
            after=after,
            delta=delta,
            status="failed",
            reason=f"{type(exc).__name__}: {str(exc)[:140]}",
        )


def _apply_compound_field_extension_change(
    optic,
    kind: str,
    surface_index: int,
    value: float,
) -> tuple[str, OptimizationVariableChange]:
    if surface_index < 0 or surface_index >= len(optic.surfaces.surfaces):
        raise ValueError(f"surface S{surface_index} is out of range")
    if kind in {"thickness", "stop_position", "focus_position"}:
        before = _surface_thickness(optic, surface_index)
        if before is None:
            raise ValueError(f"S{surface_index} thickness is non-finite")
        after = before + value
        _set_surface_thickness(optic, surface_index, after)
        label = {
            "focus_position": "focus",
            "stop_position": "stop",
            "thickness": "thickness",
        }[kind]
        return (
            f"{label} S{surface_index} {before:.4f}->{after:.4f}",
            OptimizationVariableChange(
                variable=kind,
                surface_index=surface_index,
                before=before,
                after=after,
                delta=after - before,
                delta_pct=((after - before) / before * 100.0 if before else 0.0),
            ),
        )
    if kind == "radius_pct":
        before_radius = _finite_float(optic.surfaces.radii[surface_index])
        if before_radius is None:
            raise ValueError(f"S{surface_index} radius is non-finite")
        after_radius = before_radius * (1.0 + value)
        _apply_radius_changes(optic, ((surface_index, after_radius),))
        return (
            f"radius S{surface_index} {before_radius:.4f}->{after_radius:.4f}",
            OptimizationVariableChange(
                variable="radius",
                surface_index=surface_index,
                before=before_radius,
                after=after_radius,
                delta=after_radius - before_radius,
                delta_pct=value * 100.0,
            ),
        )
    raise ValueError(f"unsupported compound field-extension change: {kind}")


def _compound_full_field_recovery_trial(
    *,
    source_zmx: str,
    nominal_fov_deg: float,
    max_total_track_mm: float | None,
    before_effective_focal_length_mm: float | None,
    before_total_track_mm: float | None,
    before_mtf_max_field_frac: float | None,
    before_max_rms_spot_radius_um: float | None,
    changes: tuple[tuple[str, int, float], ...],
) -> FullFieldRecoveryTrial:
    labels: list[str] = []
    variable_changes: list[OptimizationVariableChange] = []
    try:
        optic = _load_probe_optic(source_zmx, nominal_fov_deg)
        for kind, surface_index, value in changes:
            label, variable_change = _apply_compound_field_extension_change(
                optic, kind, surface_index, value
            )
            labels.append(label)
            variable_changes.append(variable_change)

        paraxial = compute_paraxial_summary(optic)
        verification = _verify_probe_optic(optic, nominal_fov_deg, max_total_track_mm)
        rms_delta = (
            before_max_rms_spot_radius_um - verification.max_rms_spot_radius_um
            if before_max_rms_spot_radius_um is not None
            and verification.max_rms_spot_radius_um is not None
            else None
        )
        status, reason = _recovery_trial_status(
            verification,
            before_mtf_max_field_frac=before_mtf_max_field_frac,
            rms_delta_um=rms_delta,
        )
        metrics = _verification_metric_snapshot(paraxial, verification)
        floor_gap = image_quality_floor_gap_score(metrics)
        if status == "recovered":
            reason = "compound field-extension reached 1.0 field"
            if floor_gap is not None and floor_gap <= 0.0:
                reason = f"{reason}; image-quality floor cleared"
            elif floor_gap is not None and floor_gap > 0.0:
                reason = f"{reason}; image-quality floor gap remains {floor_gap:.3f}"
        return FullFieldRecoveryTrial(
            variable_family="compound_field_extension",
            surface_index=-1,
            status=status,
            reason=f"{reason}; changes={'; '.join(labels)}",
            mtf_max_field_frac=verification.mtf_max_field_frac,
            rms_delta_um=rms_delta,
            efl_delta_mm=(
                paraxial.effective_focal_length_mm - before_effective_focal_length_mm
                if before_effective_focal_length_mm is not None
                and paraxial.effective_focal_length_mm is not None
                else None
            ),
            total_track_delta_mm=(
                paraxial.total_track_mm - before_total_track_mm
                if before_total_track_mm is not None and paraxial.total_track_mm is not None
                else None
            ),
            image_quality_floor_gap_score=floor_gap,
            metrics=metrics,
            variable_changes=variable_changes,
        )
    except Exception as exc:  # noqa: BLE001
        label = "; ".join(labels) if labels else "not applied"
        return FullFieldRecoveryTrial(
            variable_family="compound_field_extension",
            surface_index=-1,
            status="failed",
            reason=f"{type(exc).__name__}: {str(exc)[:120]}; changes={label}",
        )


@lru_cache(maxsize=64)
def protected_full_field_recovery_probe(
    source_zmx: str,
    nominal_fov_deg: float,
    max_total_track_mm: float | None,
    before_effective_focal_length_mm: float | None,
    before_total_track_mm: float | None,
    before_mtf_max_field_frac: float | None,
    before_max_rms_spot_radius_um: float | None,
) -> tuple[FullFieldRecoveryTrial, ...]:
    """Replay guarded stop/chief-ray perturbations for full-field recovery evidence."""
    optic = _load_probe_optic(source_zmx, nominal_fov_deg)
    stop_idx = _stop_surface_index(optic)
    if stop_idx is None:
        return (
            FullFieldRecoveryTrial(
                variable_family="stop_position",
                surface_index=-1,
                status="failed",
                reason="no stop surface detected",
            ),
        )

    trials: list[FullFieldRecoveryTrial] = []
    stop_before = _surface_thickness(optic, stop_idx)
    if stop_before is not None:
        for delta in _FULL_FIELD_STOP_DELTAS_MM:
            trials.append(
                _full_field_recovery_trial(
                    source_zmx=source_zmx,
                    nominal_fov_deg=nominal_fov_deg,
                    max_total_track_mm=max_total_track_mm,
                    before_effective_focal_length_mm=before_effective_focal_length_mm,
                    before_total_track_mm=before_total_track_mm,
                    before_mtf_max_field_frac=before_mtf_max_field_frac,
                    before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
                    variable_family="stop_position",
                    surface_index=stop_idx,
                    before=stop_before,
                    after=stop_before + delta,
                    delta=delta,
                )
            )

    chief_surface_indices: list[int] = []
    for idx in (stop_idx + 1, stop_idx + 3, stop_idx + 6):
        if 0 <= idx < len(optic.surfaces.surfaces) - 1 and idx not in chief_surface_indices:
            chief_surface_indices.append(idx)
    for surface_index in chief_surface_indices:
        before_height = _chief_ray_height(optic, surface_index)
        if before_height is None:
            trials.append(
                FullFieldRecoveryTrial(
                    variable_family="chief_ray_height",
                    surface_index=surface_index,
                    status="failed",
                    reason="chief ray height is non-finite",
                )
            )
            continue
        for delta in _FULL_FIELD_CHIEF_RAY_HEIGHT_DELTAS:
            trials.append(
                _full_field_recovery_trial(
                    source_zmx=source_zmx,
                    nominal_fov_deg=nominal_fov_deg,
                    max_total_track_mm=max_total_track_mm,
                    before_effective_focal_length_mm=before_effective_focal_length_mm,
                    before_total_track_mm=before_total_track_mm,
                    before_mtf_max_field_frac=before_mtf_max_field_frac,
                    before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
                    variable_family="chief_ray_height",
                    surface_index=surface_index,
                    before=before_height,
                    after=before_height + delta,
                    delta=delta,
                )
            )
    if before_mtf_max_field_frac is not None and before_mtf_max_field_frac >= 0.9:
        for changes in _FULL_FIELD_COMPOUND_EXTENSION_TRIALS:
            trials.append(
                _compound_full_field_recovery_trial(
                    source_zmx=source_zmx,
                    nominal_fov_deg=nominal_fov_deg,
                    max_total_track_mm=max_total_track_mm,
                    before_effective_focal_length_mm=before_effective_focal_length_mm,
                    before_total_track_mm=before_total_track_mm,
                    before_mtf_max_field_frac=before_mtf_max_field_frac,
                    before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
                    changes=changes,
                )
            )
    return tuple(trials)


def _rms_operand_value(optic, field_sample: float) -> float | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            problem = OptimizationProblem(batching=False)
            problem.add_operand(
                "rms_spot_size",
                target=0.0,
                weight=1.0,
                input_data={
                    "optic": optic,
                    "surface_number": _image_surface_index(optic),
                    "Hx": 0.0,
                    "Hy": field_sample,
                    "num_rays": 3,
                    "wavelength": _PRIMARY_WL_UM,
                    "distribution": "hexapolar",
                },
            )
            return _finite_float(problem.operands.operands[0].value)
    except Exception:
        return None


def _finite_merit_field_samples(optic) -> tuple[float, ...]:
    fields: list[float] = []
    for field_sample in _MERIT_FIELD_SAMPLES:
        value = _rms_operand_value(optic, field_sample)
        if value is not None and value >= 0:
            fields.append(field_sample)
    return tuple(fields)


def _before_metrics_from_values(
    effective_focal_length_mm: float | None,
    f_number: float | None,
    total_track_mm: float | None,
    mtf_max_field_frac: float | None,
    mtf_bands: MtfBandMetrics,
    max_rms_spot_radius_um: float | None,
) -> OptimizationMetricSnapshot:
    return OptimizationMetricSnapshot(
        effective_focal_length_mm=effective_focal_length_mm,
        f_number=f_number,
        total_track_mm=total_track_mm,
        mtf_max_field_frac=mtf_max_field_frac,
        mtf_50lpmm_min=mtf_bands.min_50,
        mtf_50lpmm_avg=mtf_bands.avg_50,
        mtf_100lpmm_min=mtf_bands.min_100,
        mtf_100lpmm_avg=mtf_bands.avg_100,
        mtf_150lpmm_min=mtf_bands.min_150,
        mtf_150lpmm_avg=mtf_bands.avg_150,
        mtf_200lpmm_min=mtf_bands.min_200,
        mtf_200lpmm_avg=mtf_bands.avg_200,
        mtf_250lpmm_min=mtf_bands.min_250,
        mtf_250lpmm_avg=mtf_bands.avg_250,
        mtf_multiband_min_score=mtf_bands.multiband_min_score,
        mtf_field_weighted_score=mtf_bands.field_weighted_score,
        max_rms_spot_radius_um=max_rms_spot_radius_um,
    )


@lru_cache(maxsize=64)
def protected_rms_merit_probe(
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None,
    radius_changes: tuple[tuple[int, float], ...],
    before_effective_focal_length_mm: float | None,
    before_f_number: float | None,
    before_total_track_mm: float | None,
    before_mtf_max_field_frac: float | None,
    before_mtf_bands: MtfBandMetrics,
    before_max_rms_spot_radius_um: float | None,
    baseline_variable_changes: tuple[tuple[str, int, float], ...] = (),
    variable_priority: tuple[str, ...] = (),
    probe_purpose: str | None = None,
) -> OptimizationMeritProbe:
    """Run a guarded RMS merit probe on the already first-order-corrected clone."""
    started = time.perf_counter()
    normalized_priority = _normalized_variable_priority(variable_priority)
    purpose = probe_purpose or "rms_merit"
    ranking_policy = (
        "floor_gap_first"
        if purpose in {"image_quality_floor_recovery", "replay_gate_remediation"}
        else "promotion_score_first"
    )
    use_opd_assist = (
        purpose in _OPD_ASSISTED_MERIT_PURPOSES
        and before_mtf_bands.field_weighted_score is not None
        and before_mtf_bands.field_weighted_score <= _MERIT_OPD_FIELD_WEIGHTED_THRESHOLD
    )
    before_metrics = _before_metrics_from_values(
        before_effective_focal_length_mm,
        before_f_number,
        before_total_track_mm,
        before_mtf_max_field_frac,
        before_mtf_bands,
        before_max_rms_spot_radius_um,
    )
    seed_baseline_floor_recovery = purpose == "image_quality_floor_recovery" and bool(
        normalized_priority
    )
    if not radius_changes and not seed_baseline_floor_recovery:
        return OptimizationMeritProbe(
            status="not_attempted",
            engine="optiland.least_squares",
            summary="no first-order radius proposal is available for RMS merit probing",
            operand="rms_spot_size",
            probe_purpose=purpose,
            variable_priority=list(normalized_priority),
            target_efl_mm=target_efl_mm,
            target_total_track_mm=max_total_track_mm,
            before_metrics=before_metrics,
            diagnostics=[
                "requires a verified first-order proposal clone",
                f"ranking policy={ranking_policy}",
            ],
        )
    if before_max_rms_spot_radius_um is None:
        return OptimizationMeritProbe(
            status="diagnostic_only",
            engine="optiland.least_squares",
            summary="RMS merit probe skipped because the branch has no verified RMS baseline",
            operand="rms_spot_size",
            probe_purpose=purpose,
            variable_priority=list(normalized_priority),
            target_efl_mm=target_efl_mm,
            target_total_track_mm=max_total_track_mm,
            before_metrics=before_metrics,
            diagnostics=[
                "before max RMS is missing",
                f"ranking policy={ranking_policy}",
            ],
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    failures: list[str] = []
    diagnostics = [
        "rms_spot_size operands are used only as a fast merit probe",
        "acceptance is gated by full-field MTF/RMS verification",
        "merit radius variables constrained to +/-2%; thickness variables to +/-5%",
        "selection ranks gate-clean proposals before raw RMS delta",
        "delivered seed payload is not mutated",
        f"probe purpose={purpose}",
        f"ranking policy={ranking_policy}",
    ]
    if seed_baseline_floor_recovery:
        diagnostics.append(
            "seed-baseline floor recovery enabled because first-order specs are already locked"
        )
    if use_opd_assist:
        diagnostics.append(
            "OPD_difference operand enabled as wavefront guard "
            f"weight={_MERIT_OPD_WEIGHT}; field-weighted MTF="
            f"{before_mtf_bands.field_weighted_score:.3f}"
        )
    if normalized_priority:
        diagnostics.append(f"variable priority: {','.join(normalized_priority)}")
    if baseline_variable_changes:
        diagnostics.append(
            "baseline variable changes: "
            + ",".join(
                f"{variable} S{surface_index}->{value:.6g}"
                for variable, surface_index, value in baseline_variable_changes
            )
        )
    best_probe: OptimizationMeritProbe | None = None
    best_probe_rank: tuple[int, int, float, float, float] | None = None
    radius_candidates = _candidate_radius_surfaces(source_zmx)[:_MAX_MERIT_SURFACES_TO_TRY]
    thickness_candidates = _candidate_air_gap_surfaces(source_zmx)[:_MAX_MERIT_THICKNESSES_TO_TRY]
    candidate_optic = _load_probe_optic(source_zmx, nominal_fov_deg)
    _apply_radius_changes(candidate_optic, radius_changes)
    _apply_baseline_variable_changes(candidate_optic, baseline_variable_changes)
    structured_variable_candidates = [
        _bounded_variable_candidate(
            candidate_optic,
            variable="radius",
            surface_index=idx,
            merit=True,
        )
        for idx in radius_candidates
    ] + [
        _bounded_variable_candidate(
            candidate_optic,
            variable="thickness",
            surface_index=idx,
            merit=True,
        )
        for idx in thickness_candidates
    ]
    stop_position_candidate = _candidate_stop_position(candidate_optic)
    if stop_position_candidate is not None:
        structured_variable_candidates.append(stop_position_candidate)
    focus_position_candidate = _candidate_focus_position(candidate_optic)
    if focus_position_candidate is not None:
        structured_variable_candidates.append(focus_position_candidate)
    asphere_candidates = _candidate_asphere_coefficients(source_zmx)
    structured_variable_candidates.extend(asphere_candidates)
    if normalized_priority:
        structured_variable_candidates = [
            candidate
            for _, candidate in sorted(
                enumerate(structured_variable_candidates),
                key=lambda item: (
                    _priority_index(item[1].variable, normalized_priority),
                    item[0],
                ),
            )
        ]
    diagnostics.extend(
        [
            f"radius candidates: {radius_candidates}",
            f"thickness candidates: {thickness_candidates}",
            f"stop-position candidates: "
            f"{[_candidate_label(candidate) for candidate in structured_variable_candidates if candidate.variable == 'stop_position']}",
            f"focus-position candidates: "
            f"{[_candidate_label(candidate) for candidate in structured_variable_candidates if candidate.variable == 'focus_position']}",
            f"asphere candidates: {[_candidate_label(candidate) for candidate in asphere_candidates]}",
        ]
    )
    variable_candidates = [
        (candidate.variable, candidate.surface_index)
        for candidate in structured_variable_candidates
        if candidate.status == "eligible" and candidate.variable in {"radius", "thickness"}
    ]
    candidate_trials: list[OptimizationVariableTrial] = []

    for variable, surface_index in variable_candidates:
        try:
            optic = _load_probe_optic(source_zmx, nominal_fov_deg)
            _apply_radius_changes(optic, radius_changes)
            _apply_baseline_variable_changes(optic, baseline_variable_changes)
            field_samples = _finite_merit_field_samples(optic)
            if not field_samples:
                failures.append(f"{variable} S{surface_index}: no finite RMS operand fields")
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        status="failed",
                        reason="no finite RMS operand fields",
                    )
                )
                continue

            before_value = _variable_value(optic, variable, surface_index)
            if before_value is None:
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        status="failed",
                        reason="current value is non-finite",
                    )
                )
                continue
            bounds = _bounded_merit_variable(variable, before_value)
            if bounds is None:
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        before=before_value,
                        status="skipped",
                        reason="bounded search interval could not be formed",
                    )
                )
                continue

            problem = OptimizationProblem(batching=False)
            problem.add_operand(
                "f2",
                target=target_efl_mm,
                weight=1.0,
                input_data={"optic": optic},
            )
            if max_total_track_mm is not None:
                problem.add_operand(
                    "total_track",
                    max_val=max_total_track_mm,
                    weight=0.15,
                    input_data={"optic": optic},
                )
            for field_sample in field_samples:
                problem.add_operand(
                    "rms_spot_size",
                    target=0.0,
                    weight=0.05,
                    input_data={
                        "optic": optic,
                        "surface_number": _image_surface_index(optic),
                        "Hx": 0.0,
                        "Hy": field_sample,
                        "num_rays": 3,
                        "wavelength": _PRIMARY_WL_UM,
                        "distribution": "hexapolar",
                    },
                )
                if use_opd_assist:
                    problem.add_operand(
                        "OPD_difference",
                        target=0.0,
                        weight=_MERIT_OPD_WEIGHT,
                        input_data={
                            "optic": optic,
                            "Hx": 0.0,
                            "Hy": field_sample,
                            "num_rays": 3,
                            "wavelength": _PRIMARY_WL_UM,
                            "distribution": "gaussian_quad",
                        },
                    )
            problem.add_variable(
                optic,
                variable,
                surface_number=surface_index,
                min_val=bounds[0],
                max_val=bounds[1],
            )

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                merit_before = float(problem.rss())
            if not math.isfinite(merit_before):
                failures.append(f"{variable} S{surface_index}: initial RMS merit was non-finite")
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        before=before_value,
                        status="failed",
                        reason="initial RMS merit was non-finite",
                    )
                )
                continue
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                result = LeastSquares(problem).optimize(
                    maxiter=_MAX_MERIT_OPTIMIZER_ITER,
                    disp=False,
                    method_choice="trf",
                )
                merit_after = float(problem.rss())
            if not math.isfinite(merit_after):
                failures.append(f"{variable} S{surface_index}: optimized RMS merit was non-finite")
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        before=before_value,
                        merit_before=merit_before,
                        status="failed",
                        reason="optimized RMS merit was non-finite",
                    )
                )
                continue
            after_value = _variable_value(optic, variable, surface_index)
            if after_value is None:
                failures.append(
                    f"{variable} S{surface_index}: merit optimizer produced non-finite value"
                )
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        before=before_value,
                        merit_before=merit_before,
                        merit_after=merit_after,
                        status="failed",
                        reason="merit optimizer produced non-finite value",
                    )
                )
                continue

            after_paraxial = compute_paraxial_summary(optic)
            verification = _verify_probe_optic(
                optic,
                nominal_fov_deg,
                max_total_track_mm,
            )
            after_bands = mtf_bands_from_snapshot(verification)
            after_metrics = _metric_snapshot(
                after_paraxial,
                mtf_max_field_frac=verification.mtf_max_field_frac,
                mtf_bands=after_bands,
                max_rms_spot_radius_um=verification.max_rms_spot_radius_um,
            )
            after_rms = verification.max_rms_spot_radius_um
            if after_rms is None:
                floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                    before_metrics,
                    after_metrics,
                )
                failures.append(f"S{surface_index}: verification had no max RMS")
                candidate_trials.append(
                    _variable_trial(
                        variable=variable,
                        surface_index=surface_index,
                        before=before_value,
                        after=after_value,
                        merit_before=merit_before,
                        merit_after=merit_after,
                        image_quality_floor_gap_before=floor_gap_before,
                        image_quality_floor_gap_after=floor_gap_after,
                        image_quality_floor_gap_closure=floor_gap_closure,
                        verification_status=verification.status,
                        status="failed",
                        reason="verification had no max RMS",
                    )
                )
                continue

            rms_improvement = before_max_rms_spot_radius_um - after_rms
            rms_improvement_pct = (
                rms_improvement / before_max_rms_spot_radius_um * 100.0
                if before_max_rms_spot_radius_um
                else 0.0
            )
            mtf_non_regressed = before_mtf_max_field_frac is None or (
                verification.mtf_max_field_frac is not None
                and verification.mtf_max_field_frac >= before_mtf_max_field_frac
            )
            mtf_band_non_regressed = mtf_multiband_non_regressed(
                before_mtf_bands,
                after_bands,
            )
            floor_gap_before, floor_gap_after, floor_gap_closure = _floor_gap_closure(
                before_metrics,
                after_metrics,
            )
            field_weighted_non_regressed = mtf_field_weighted_non_regressed(
                before_mtf_bands,
                after_bands,
            )
            efl_locked = (
                after_paraxial.effective_focal_length_mm is not None
                and abs(after_paraxial.effective_focal_length_mm - target_efl_mm) <= 0.10
            )
            accepted = (
                verification.status == "passed"
                and rms_improvement >= 0.10
                and mtf_non_regressed
                and mtf_band_non_regressed
                and field_weighted_non_regressed
                and efl_locked
            )
            status = "proposal" if accepted else "warning"
            promotion_score = _merit_promotion_score(
                accepted=accepted,
                verification_status=verification.status,
                rms_improvement_um=rms_improvement,
                mtf_field_non_regressed=mtf_non_regressed,
                mtf_band_non_regressed=mtf_band_non_regressed,
                mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                efl_locked=efl_locked,
                image_quality_floor_gap_closure=floor_gap_closure,
            )
            if accepted:
                trial_status = "accepted"
                trial_reason = "passed RMS/MTF/EFL promotion gates"
            else:
                failed_gates: list[str] = []
                if verification.status != "passed":
                    failed_gates.append(f"verification={verification.status}")
                if rms_improvement < 0.10:
                    failed_gates.append("RMS improvement below 0.10 um")
                if not mtf_non_regressed:
                    failed_gates.append("MTF field fraction regressed")
                if not mtf_band_non_regressed:
                    failed_gates.append("MTF 50/100/150/200/250 lp/mm regressed")
                if not field_weighted_non_regressed:
                    failed_gates.append("field-weighted MTF regressed")
                if not efl_locked:
                    failed_gates.append("EFL not locked")
                trial_status = "rejected"
                trial_reason = "; ".join(failed_gates) or "promotion gates did not pass"
            candidate_trials.append(
                _variable_trial(
                    variable=variable,
                    surface_index=surface_index,
                    before=before_value,
                    after=after_value,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    rms_improvement_um=rms_improvement,
                    rms_improvement_pct=rms_improvement_pct,
                    promotion_score=promotion_score,
                    image_quality_floor_gap_before=floor_gap_before,
                    image_quality_floor_gap_after=floor_gap_after,
                    image_quality_floor_gap_closure=floor_gap_closure,
                    verification_status=verification.status,
                    mtf_field_non_regressed=mtf_non_regressed,
                    mtf_band_non_regressed=mtf_band_non_regressed,
                    mtf_field_weighted_non_regressed=field_weighted_non_regressed,
                    efl_locked=efl_locked,
                    status=trial_status,
                    reason=trial_reason,
                )
            )
            probe = OptimizationMeritProbe(
                status=status,
                engine="optiland.least_squares",
                summary=(
                    "protected RMS merit probe found a verified image-quality improvement"
                    if accepted
                    else "RMS merit probe ran, but full-field verification did not pass promotion gates"
                ),
                operand="rms_spot_size",
                probe_purpose=purpose,
                variable_priority=list(normalized_priority),
                field_samples=list(field_samples),
                target_efl_mm=target_efl_mm,
                target_total_track_mm=max_total_track_mm,
                merit_before=merit_before,
                merit_after=merit_after,
                rms_improvement_um=rms_improvement,
                rms_improvement_pct=rms_improvement_pct,
                variable_candidates=structured_variable_candidates,
                candidate_trials=candidate_trials,
                variable_changes=[
                    OptimizationVariableChange(
                        variable=variable,
                        surface_index=surface_index,
                        before=before_value,
                        after=after_value,
                        delta=after_value - before_value,
                        delta_pct=(
                            (after_value - before_value) / before_value * 100.0
                            if before_value
                            else 0.0
                        ),
                    )
                ],
                verification=verification,
                before_metrics=before_metrics,
                after_metrics=after_metrics,
                diagnostics=[
                    *diagnostics,
                    f"finite RMS operand fields: {field_samples}",
                    f"MTF 50/100/150/200/250 lp/mm non-regressed={mtf_band_non_regressed}",
                    f"MTF field-weighted score non-regressed={field_weighted_non_regressed}",
                    f"image-quality floor gap closure={floor_gap_closure}",
                    f"promotion score={promotion_score:.3f}",
                    f"scipy message: {getattr(result, 'message', 'n/a')}",
                ],
                failures=failures[:4],
                applied_to_payload=False,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            probe_rank = _merit_probe_rank(
                accepted=accepted,
                rms_improvement_um=rms_improvement,
                promotion_score=promotion_score,
                image_quality_floor_gap_closure=floor_gap_closure,
                probe_purpose=purpose,
            )
            if best_probe_rank is None or probe_rank > best_probe_rank:
                best_probe = probe
                best_probe_rank = probe_rank
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{variable} S{surface_index}: {type(exc).__name__}: {str(exc)[:120]}")
            candidate_trials.append(
                _variable_trial(
                    variable=variable,
                    surface_index=surface_index,
                    status="failed",
                    reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                )
            )

    stop_trials, stop_probe_ranks, stop_diagnostics = _stop_position_replay_trials(
        source_zmx=source_zmx,
        nominal_fov_deg=nominal_fov_deg,
        target_efl_mm=target_efl_mm,
        max_total_track_mm=max_total_track_mm,
        radius_changes=radius_changes,
        baseline_variable_changes=baseline_variable_changes,
        before_metrics=before_metrics,
        before_mtf_max_field_frac=before_mtf_max_field_frac,
        before_mtf_bands=before_mtf_bands,
        before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
        variable_candidates=structured_variable_candidates,
        variable_priority=normalized_priority,
        probe_purpose=purpose,
        base_diagnostics=diagnostics,
    )
    candidate_trials.extend(stop_trials)
    for stop_probe, stop_probe_rank in stop_probe_ranks:
        if best_probe_rank is None or stop_probe_rank > best_probe_rank:
            best_probe = stop_probe
            best_probe_rank = stop_probe_rank

    focus_trials, focus_probe_ranks, focus_diagnostics = _focus_position_replay_trials(
        source_zmx=source_zmx,
        nominal_fov_deg=nominal_fov_deg,
        target_efl_mm=target_efl_mm,
        max_total_track_mm=max_total_track_mm,
        radius_changes=radius_changes,
        baseline_variable_changes=baseline_variable_changes,
        before_metrics=before_metrics,
        before_mtf_max_field_frac=before_mtf_max_field_frac,
        before_mtf_bands=before_mtf_bands,
        before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
        variable_candidates=structured_variable_candidates,
        variable_priority=normalized_priority,
        probe_purpose=purpose,
        base_diagnostics=diagnostics,
    )
    candidate_trials.extend(focus_trials)
    for focus_probe, focus_probe_rank in focus_probe_ranks:
        if best_probe_rank is None or focus_probe_rank > best_probe_rank:
            best_probe = focus_probe
            best_probe_rank = focus_probe_rank

    continuation_trials, continuation_probe_ranks, continuation_diagnostics = (
        _compound_continuation_replay_trials(
            source_zmx=source_zmx,
            nominal_fov_deg=nominal_fov_deg,
            target_efl_mm=target_efl_mm,
            max_total_track_mm=max_total_track_mm,
            radius_changes=radius_changes,
            baseline_variable_changes=baseline_variable_changes,
            focus_trials=focus_trials,
            variable_candidates=structured_variable_candidates,
            variable_priority=normalized_priority,
            probe_purpose=purpose,
            before_metrics=before_metrics,
            before_mtf_max_field_frac=before_mtf_max_field_frac,
            before_mtf_bands=before_mtf_bands,
            before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
            base_diagnostics=diagnostics,
        )
    )
    candidate_trials.extend(continuation_trials)
    for continuation_probe, continuation_probe_rank in continuation_probe_ranks:
        if best_probe_rank is None or continuation_probe_rank > best_probe_rank:
            best_probe = continuation_probe
            best_probe_rank = continuation_probe_rank

    compound_diagnostics: list[str] = []
    if best_probe is not None:
        compound_trials, compound_probe, compound_diagnostics = _compound_merit_replay(
            source_zmx=source_zmx,
            nominal_fov_deg=nominal_fov_deg,
            target_efl_mm=target_efl_mm,
            max_total_track_mm=max_total_track_mm,
            radius_changes=radius_changes,
            baseline_variable_changes=baseline_variable_changes,
            accepted_trials=[
                trial
                for trial in candidate_trials
                if trial.status == "accepted"
                and trial.variable in {"radius", "thickness", "stop_position", "focus_position"}
            ],
            current_best_probe=best_probe,
            variable_candidates=structured_variable_candidates,
            before_metrics=before_metrics,
            before_mtf_max_field_frac=before_mtf_max_field_frac,
            before_mtf_bands=before_mtf_bands,
            before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
        )
        candidate_trials.extend(compound_trials)
        if compound_probe is not None:
            best_probe = compound_probe

    if best_probe is not None:
        remaining_gap = _remaining_floor_gap(best_probe.after_metrics)
        run_asphere_audit = best_probe.status == "warning" or (
            purpose == "replay_gate_remediation"
            and remaining_gap is not None
            and remaining_gap > 0.0
            and bool(asphere_candidates)
        )
        if run_asphere_audit:
            asphere_prescreen_rows = _asphere_prescreen_candidates(
                source_zmx=source_zmx,
                nominal_fov_deg=nominal_fov_deg,
                radius_changes=radius_changes,
                baseline_variable_changes=baseline_variable_changes,
                asphere_candidates=asphere_candidates,
            )
            asphere_trials = _asphere_audit_trials(
                source_zmx=source_zmx,
                nominal_fov_deg=nominal_fov_deg,
                target_efl_mm=target_efl_mm,
                max_total_track_mm=max_total_track_mm,
                radius_changes=radius_changes,
                baseline_variable_changes=baseline_variable_changes,
                before_mtf_max_field_frac=before_mtf_max_field_frac,
                before_mtf_bands=before_mtf_bands,
                before_max_rms_spot_radius_um=before_max_rms_spot_radius_um,
                prescreen_rows=asphere_prescreen_rows,
            )
            joint_trials = _joint_asphere_merit_trials(
                source_zmx=source_zmx,
                nominal_fov_deg=nominal_fov_deg,
                target_efl_mm=target_efl_mm,
                max_total_track_mm=max_total_track_mm,
                radius_changes=radius_changes,
                baseline_variable_changes=baseline_variable_changes,
                merit_variable_changes=best_probe.variable_changes,
                asphere_trials=asphere_trials,
                joint_baseline_metrics=best_probe.after_metrics,
            )
            candidate_trials.extend([*asphere_trials, *joint_trials])
            audit_diagnostics = [
                (
                    "asphere audit trigger=remaining_floor_gap"
                    if best_probe.status != "warning"
                    else "asphere audit trigger=warning_probe"
                ),
                (
                    f"asphere audit remaining floor gap={remaining_gap:.3f}"
                    if remaining_gap is not None
                    else "asphere audit remaining floor gap unavailable"
                ),
                f"asphere prescreen trials={len(asphere_prescreen_rows)}",
                f"asphere audit trials={len(asphere_trials)}",
                f"joint asphere-merit audit trials={len(joint_trials)}",
                *(
                    [
                        f"top asphere audit trial={asphere_trials[0].status} "
                        f"S{asphere_trials[0].surface_index}:c"
                        f"{asphere_trials[0].coefficient_index}"
                    ]
                    if asphere_trials
                    else []
                ),
            ]
        else:
            audit_diagnostics = []
        return best_probe.model_copy(
            update={
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "candidate_trials": candidate_trials,
                "diagnostics": [
                    *best_probe.diagnostics,
                    *stop_diagnostics,
                    *focus_diagnostics,
                    *continuation_diagnostics,
                    *compound_diagnostics,
                    *audit_diagnostics,
                ],
            }
        )

    return OptimizationMeritProbe(
        status="diagnostic_only",
        engine="optiland.least_squares",
        summary="protected RMS merit probe did not find a trustworthy bounded improvement",
        operand="rms_spot_size",
        probe_purpose=purpose,
        variable_priority=list(normalized_priority),
        target_efl_mm=target_efl_mm,
        target_total_track_mm=max_total_track_mm,
        before_metrics=before_metrics,
        variable_candidates=structured_variable_candidates,
        candidate_trials=candidate_trials,
        diagnostics=diagnostics,
        failures=failures[:6],
        applied_to_payload=False,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


@lru_cache(maxsize=64)
def protected_efl_refinement(
    source_zmx: str,
    nominal_fov_deg: float,
    target_efl_mm: float,
    max_total_track_mm: float | None = None,
    before_mtf_max_field_frac: float | None = None,
    before_mtf_bands: MtfBandMetrics | None = None,
    before_max_rms_spot_radius_um: float | None = None,
) -> OptimizationAttempt:
    """Run a small, guarded EFL optimization attempt on a real source zmx.

    The function tries one radius variable at a time with ±5% bounds. It only
    reports a proposal when the post-optimization paraxial EFL is finite and
    improves the target miss by a meaningful amount. All failures are captured
    as diagnostics instead of bubbling into the user-facing generation path.
    """
    started = time.perf_counter()
    path = ZMX_AMMO_DIR / source_zmx
    if not path.exists():
        return OptimizationAttempt(
            status="not_attempted",
            engine="optiland.least_squares",
            summary="source zmx file is unavailable for local optimization",
            target_efl_mm=target_efl_mm,
            diagnostics=[f"missing source file: {source_zmx}"],
        )

    try:
        base = _load_probe_optic(source_zmx, nominal_fov_deg)
        before = compute_paraxial_summary(base)
        raw_surface_indices = _candidate_radius_surfaces(source_zmx)
        variable_candidates = [
            _bounded_variable_candidate(
                base,
                variable="radius",
                surface_index=idx,
                merit=False,
            )
            for idx in raw_surface_indices
        ]
        surface_indices = [
            candidate.surface_index
            for candidate in variable_candidates
            if candidate.status == "eligible"
        ]
        before_metrics = _metric_snapshot(
            before,
            mtf_max_field_frac=before_mtf_max_field_frac,
            mtf_bands=before_mtf_bands,
            max_rms_spot_radius_um=before_max_rms_spot_radius_um,
        )
    except Exception as exc:  # noqa: BLE001
        return OptimizationAttempt(
            status="diagnostic_only",
            engine="optiland.least_squares",
            summary="seed could not be prepared for protected local optimization",
            target_efl_mm=target_efl_mm,
            diagnostics=[f"{type(exc).__name__}: {str(exc)[:180]}"],
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    before_error = abs(before.effective_focal_length_mm - target_efl_mm)
    failures: list[str] = []
    diagnostics = [
        f"candidate radius surfaces: {raw_surface_indices}",
        "radius variables constrained to +/-5%; selected seed payload is not mutated",
    ]
    best_attempt: tuple[float, OptimizationAttempt, object] | None = None
    candidate_trials: list[OptimizationVariableTrial] = []

    for surface_index in surface_indices:
        try:
            optic = _load_probe_optic(source_zmx, nominal_fov_deg)
            before_radius = _finite_float(optic.surfaces.radii[surface_index])
            if before_radius is None:
                candidate_trials.append(
                    _variable_trial(
                        variable="radius",
                        surface_index=surface_index,
                        status="failed",
                        reason="current radius is non-finite",
                    )
                )
                continue
            bounds = _bounded_radius(before_radius)
            if bounds is None:
                candidate_trials.append(
                    _variable_trial(
                        variable="radius",
                        surface_index=surface_index,
                        before=before_radius,
                        status="skipped",
                        reason="bounded radius interval could not be formed",
                    )
                )
                continue

            problem = OptimizationProblem(batching=False)
            problem.add_operand(
                "f2",
                target=target_efl_mm,
                weight=1.0,
                input_data={"optic": optic},
            )
            if max_total_track_mm is not None:
                problem.add_operand(
                    "total_track",
                    max_val=max_total_track_mm,
                    weight=0.15,
                    input_data={"optic": optic},
                )
            problem.add_variable(
                optic,
                "radius",
                surface_number=surface_index,
                min_val=bounds[0],
                max_val=bounds[1],
            )

            merit_before = float(problem.rss())
            result = LeastSquares(problem).optimize(
                maxiter=_MAX_OPTIMIZER_ITER,
                disp=False,
                method_choice="trf",
            )
            after = compute_paraxial_summary(optic)
            after_radius = _finite_float(optic.surfaces.radii[surface_index])
            if after_radius is None:
                failures.append(f"S{surface_index}: optimizer produced non-finite radius")
                candidate_trials.append(
                    _variable_trial(
                        variable="radius",
                        surface_index=surface_index,
                        before=before_radius,
                        merit_before=merit_before,
                        status="failed",
                        reason="optimizer produced non-finite radius",
                    )
                )
                continue
            after_error = abs(after.effective_focal_length_mm - target_efl_mm)
            improvement_mm = before_error - after_error
            if improvement_mm <= 0:
                failures.append(f"S{surface_index}: no EFL improvement")
                candidate_trials.append(
                    _variable_trial(
                        variable="radius",
                        surface_index=surface_index,
                        before=before_radius,
                        after=after_radius,
                        merit_before=merit_before,
                        efl_improvement_mm=improvement_mm,
                        status="rejected",
                        reason="no EFL improvement",
                    )
                )
                continue

            merit_after = float(problem.rss())
            delta_pct = (
                (after_radius - before_radius) / before_radius * 100.0
                if before_radius != 0
                else 0.0
            )
            candidate_trials.append(
                _variable_trial(
                    variable="radius",
                    surface_index=surface_index,
                    before=before_radius,
                    after=after_radius,
                    merit_before=merit_before,
                    merit_after=merit_after,
                    efl_improvement_mm=improvement_mm,
                    status="improved",
                    reason="reduced first-order EFL miss before verification",
                )
            )
            attempt = OptimizationAttempt(
                status="proposal",
                engine="optiland.least_squares",
                summary=(
                    "protected local optimizer found a bounded radius tweak "
                    "that reduces first-order EFL miss"
                ),
                target_efl_mm=target_efl_mm,
                target_total_track_mm=max_total_track_mm,
                before_efl_mm=before.effective_focal_length_mm,
                after_efl_mm=after.effective_focal_length_mm,
                before_total_track_mm=before.total_track_mm,
                after_total_track_mm=after.total_track_mm,
                merit_before=merit_before,
                merit_after=merit_after,
                improvement_efl_mm=improvement_mm,
                improvement_pct=(improvement_mm / before_error * 100.0 if before_error else 0.0),
                variable_candidates=variable_candidates,
                candidate_trials=candidate_trials,
                variable_changes=[
                    OptimizationVariableChange(
                        variable="radius",
                        surface_index=surface_index,
                        before=before_radius,
                        after=after_radius,
                        delta=after_radius - before_radius,
                        delta_pct=delta_pct,
                    )
                ],
                before_metrics=before_metrics,
                after_metrics=_metric_snapshot(after),
                diagnostics=[
                    *diagnostics,
                    f"scipy message: {getattr(result, 'message', 'n/a')}",
                ],
                failures=failures[:4],
                applied_to_payload=False,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
            if best_attempt is None or improvement_mm > best_attempt[0]:
                best_attempt = (improvement_mm, attempt, optic)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"S{surface_index}: {type(exc).__name__}: {str(exc)[:120]}")
            candidate_trials.append(
                _variable_trial(
                    variable="radius",
                    surface_index=surface_index,
                    status="failed",
                    reason=f"{type(exc).__name__}: {str(exc)[:120]}",
                )
            )

    min_improvement = max(0.01, before_error * 0.10)
    if best_attempt is not None and best_attempt[0] >= min_improvement:
        verification = _verify_probe_optic(
            best_attempt[2],
            nominal_fov_deg,
            max_total_track_mm,
        )
        best_model = best_attempt[1]
        after_metrics = best_model.after_metrics
        if after_metrics is not None:
            after_metrics = after_metrics.model_copy(
                update={
                    "mtf_max_field_frac": verification.mtf_max_field_frac,
                    "mtf_50lpmm_min": verification.mtf_50lpmm_min,
                    "mtf_50lpmm_avg": verification.mtf_50lpmm_avg,
                    "mtf_100lpmm_min": verification.mtf_100lpmm_min,
                    "mtf_100lpmm_avg": verification.mtf_100lpmm_avg,
                    "mtf_150lpmm_min": verification.mtf_150lpmm_min,
                    "mtf_150lpmm_avg": verification.mtf_150lpmm_avg,
                    "mtf_multiband_min_score": verification.mtf_multiband_min_score,
                    "mtf_field_weighted_score": verification.mtf_field_weighted_score,
                    "max_rms_spot_radius_um": verification.max_rms_spot_radius_um,
                }
            )
        attempt = best_model.model_copy(
            update={
                "summary": (
                    "protected local optimizer found a bounded radius tweak; "
                    f"verification gate {verification.status}"
                ),
                "verification": verification,
                "after_metrics": after_metrics,
                "candidate_trials": candidate_trials,
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
            }
        )
        if verification.status != "failed":
            return attempt
        return OptimizationAttempt(
            status="diagnostic_only",
            engine="optiland.least_squares",
            summary="bounded EFL improvement failed post-tweak verification",
            target_efl_mm=target_efl_mm,
            target_total_track_mm=max_total_track_mm,
            before_efl_mm=before.effective_focal_length_mm,
            after_efl_mm=attempt.after_efl_mm,
            before_total_track_mm=before.total_track_mm,
            after_total_track_mm=attempt.after_total_track_mm,
            merit_before=attempt.merit_before,
            merit_after=attempt.merit_after,
            improvement_efl_mm=attempt.improvement_efl_mm,
            improvement_pct=attempt.improvement_pct,
            variable_candidates=attempt.variable_candidates,
            candidate_trials=candidate_trials,
            variable_changes=attempt.variable_changes,
            verification=verification,
            before_metrics=attempt.before_metrics,
            after_metrics=attempt.after_metrics,
            diagnostics=[*diagnostics, *verification.diagnostics],
            failures=[*failures[:4], verification.summary],
            applied_to_payload=False,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )

    return OptimizationAttempt(
        status="diagnostic_only",
        engine="optiland.least_squares",
        summary="protected local optimizer did not find a trustworthy bounded improvement",
        target_efl_mm=target_efl_mm,
        target_total_track_mm=max_total_track_mm,
        before_efl_mm=before.effective_focal_length_mm,
        before_total_track_mm=before.total_track_mm,
        before_metrics=before_metrics,
        variable_candidates=variable_candidates,
        candidate_trials=candidate_trials,
        diagnostics=diagnostics,
        failures=failures[:6],
        applied_to_payload=False,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )
