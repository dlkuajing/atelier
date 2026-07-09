"""C1 scorecard 纯函数（Phase 10 探路阶 · C1-c）。

权威依据：`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§7（Scorecard 度量口径 A-E）+ §9（测试策略）。`score_candidate` 是纯函数：
只消费 `generated.payload`（`OpticalSampleData`）+ `generated.optical_extras`
（generator 阶段用 optic 预算的量，首要 RI），不自行触碰 optic/ZMX（§7 前言）。

度量提取路径（每个字段对应哪个 payload 字段，供审计）：
- A. Target 偏差：EFL ← `payload.paraxial.effective_focal_length_mm`；
  F# ← `payload.paraxial.f_number`；TTL ← `payload.paraxial.total_track_mm`；
  IMH ← `payload.metadata.image_height_mm`；FOV ← 优先
  `payload.metadata.fov_deg`（`optical_sample.py:32`），缺则由
  EFL+IMH 反算（`optical_calc.angular_field_of_view_deg`，见 `_resolve_fov_deg`）。
- B. 像质：MTF ← `payload.mtf`（`aberration.py::MTFResult`）；RMS 点列 ←
  `payload.spot_diagram`（`spot_diagram.py::SpotDiagramResult`，可选字段，
  缺失 fail closed）；波前 ← `payload.wavefront`
  （`wavefront_metrics.py::WavefrontMetricsResult`，可选）；场曲/畸变 ←
  `payload.field_analysis`（`field_analysis.py::FieldAnalysisResult`，可选）；
  RI ← `generated.optical_extras.ri_by_field`。
- C. 可制造性：TTL 同 A；片数 ← `payload.metadata.n_pieces`；玻璃类型 ←
  `payload.metadata.materials` + `zmx_materials.lookup_nd_vd`（真实 datasheet
  nd 表，非猜测）；非球面复杂度/CRA ← payload 结构性不携带，恒 unavailable
  （见下方"已知结构性缺口"）。
- E. 排序：由 A/B 组装，见 `_rank`。

已知结构性缺口（payload 现有 schema 不携带，诚实标 unavailable，不猜测）：
- `aspheric_term_count` / `aspheric_surface_count`：`payload.surfaces` 是
  `SurfaceDescriptor`（`optical_engine.py`），只有 index/z/radius/is_stop/
  is_image/is_object，不含 `aspheric_coeffs`/`conic`。
- `chief_ray_angle_deg`：`payload.trace`（`RayTraceResult`）的
  `sampled_paths` 只在 `field_angle_deg=0.0` 采样 chief-axial/marginal 三条
  （`optical_engine.py::trace_optic`），没有满场主光线角数据。
"""

from __future__ import annotations

import math

from app.core.aberration import MTFResult
from app.core.field_analysis import FieldAnalysisResult
from app.core.optical_calc import angular_field_of_view_deg
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import (
    CONVERGED_FIELDS,
    GeneratedCandidate,
    GenerationMode,
    ImageQualityMetrics,
    ManufacturabilityProxy,
    MetricValue,
    OpticalExtras,
    RankResult,
    ScorecardRow,
    TargetDeviation,
    TargetSpec,
)
from app.core.spot_diagram import SpotDiagramResult
from app.core.zmx_materials import lookup_nd_vd

# ---------------------------------------------------------------------------
# Tunables (§7-E) — documented, not buried magic numbers.
# ---------------------------------------------------------------------------

# Relative-violation tolerance per target field (norm = min(rel_violation/tol, 1.0)).
_REL_TOLERANCE: dict[str, float] = {
    "efl": 0.05,
    "fov": 0.05,
    "imh": 0.05,
    "ttl": 0.05,
    "fnum": 0.08,
}

_RANK_WEIGHT_DEVIATION = 0.5
_RANK_WEIGHT_IMAGE_QUALITY = 0.5
_MIN_COVERAGE_PCT = 0.8

# §7-E: 必需维 = {MTF}（恒必需）∪ 受约束的 {EFL, FOV}（target=None 不计入）。
_REQUIRED_TARGET_FIELDS: tuple[str, ...] = ("efl", "fov")

# Image-quality fields with a physically well-defined [0,1] "higher=better"
# scale (MTF contrast, Strehl ratio, RI) — safe to fold into the single rank
# score without inventing a threshold. The remaining IQ fields (RMS spot µm,
# wavefront-error waves, field-curvature mm, distortion %, diffraction
# cutoff lp/mm) have no absolute-to-[0,1] "goodness" precedent anywhere in
# this codebase; making one up here would be exactly the kind of guess the
# project's fail-closed/no-speculation rule forbids. They stay visible in
# the reported `ImageQualityMetrics` for the human reviewer, just excluded
# from the scalar `rank.score` (documented deviation from a literal, but
# underspecified, reading of §7-E — see task report).
_BOUNDED_GOODNESS_IQ_FIELDS: tuple[str, ...] = (
    "mtf_sag",
    "mtf_tan",
    "min_strehl_ratio",
    "relative_illumination",
)

# Proxy threshold for "special/high-index" glass (§7-C has_special_glass).
# Consumer COP/PMMA-class plastics sit around nd~1.53-1.54; the datasheet
# table's high-index resins (OKP/EP families) start at nd>=1.60 — no
# established codebase precedent for this cutoff, chosen as a conservative
# proxy line documented here (not silently baked into the constant name).
_HIGH_INDEX_ND_THRESHOLD = 1.60


def _metric(value: float | None) -> MetricValue:
    if value is None or not math.isfinite(value):
        return MetricValue(value=None, status="unavailable")
    return MetricValue(value=float(value), status="available")


# ---------------------------------------------------------------------------
# A. Target deviations (§7-A)
# ---------------------------------------------------------------------------


def _resolve_fov_deg(
    *,
    metadata_fov_deg: float | None,
    efl_mm: float,
    image_height_mm: float | None,
) -> float | None:
    """Achieved FOV: prefer `metadata.fov_deg`; fallback EFL+IMH back-calc (§7-A).

    `image_height_mm` here is the case's half-diagonal (radial IMH) — the
    convention used throughout this payload (`_IMH` filename tokens,
    `CaseMetadata.image_height_mm`); `angular_field_of_view_deg` expects a
    full diagonal, hence the `2.0 *` factor.
    """
    if metadata_fov_deg is not None:
        return metadata_fov_deg
    if image_height_mm is None or efl_mm <= 0 or image_height_mm <= 0:
        return None
    return angular_field_of_view_deg(efl_mm, 2.0 * image_height_mm)


def _exact_deviation(
    *, field: str, target_value: float, achieved: float, converged: bool
) -> TargetDeviation:
    violation = abs(achieved - target_value)
    rel_violation = violation / abs(target_value) if target_value else None
    return TargetDeviation(
        field=field,
        constraint_kind="exact",
        target=target_value,
        achieved=achieved,
        violation=violation,
        rel_violation=rel_violation,
        converged_toward_target=converged,
    )


def _unconstrained_deviation(*, field: str, achieved: float, converged: bool) -> TargetDeviation:
    return TargetDeviation(
        field=field,
        constraint_kind="unconstrained",
        target=None,
        achieved=achieved,
        violation=0.0,
        rel_violation=None,
        converged_toward_target=converged,
    )


def _exact_or_unconstrained_deviation(
    *, field: str, target_value: float | None, achieved: float, converged: bool
) -> TargetDeviation:
    if target_value is None:
        return _unconstrained_deviation(field=field, achieved=achieved, converged=converged)
    return _exact_deviation(
        field=field, target_value=target_value, achieved=achieved, converged=converged
    )


def _ceiling_or_unconstrained_deviation(
    *, field: str, limit: float | None, achieved: float, converged: bool
) -> TargetDeviation:
    if limit is None:
        return _unconstrained_deviation(field=field, achieved=achieved, converged=converged)
    violation = max(0.0, achieved - limit)  # short of ceiling never penalized
    rel_violation = violation / abs(limit) if limit else None
    return TargetDeviation(
        field=field,
        constraint_kind="ceiling",
        target=limit,
        achieved=achieved,
        violation=violation,
        rel_violation=rel_violation,
        converged_toward_target=converged,
    )


def _target_deviations(
    mode: GenerationMode, payload: OpticalSampleData, target: TargetSpec
) -> list[TargetDeviation]:
    conv = CONVERGED_FIELDS[mode]
    paraxial = payload.paraxial
    metadata = payload.metadata

    rows: list[TargetDeviation] = [
        _exact_deviation(
            field="efl",
            target_value=target.efl_mm,
            achieved=paraxial.effective_focal_length_mm,
            converged="efl" in conv,
        ),
        _exact_deviation(
            field="fnum",
            target_value=target.fnum,
            achieved=paraxial.f_number,
            converged="fnum" in conv,
        ),
    ]

    achieved_fov = _resolve_fov_deg(
        metadata_fov_deg=(metadata.fov_deg if metadata is not None else None),
        efl_mm=paraxial.effective_focal_length_mm,
        image_height_mm=(metadata.image_height_mm if metadata is not None else None),
    )
    if achieved_fov is not None:
        rows.append(
            _exact_deviation(
                field="fov",
                target_value=target.fov_deg,
                achieved=achieved_fov,
                converged="fov" in conv,
            )
        )
    # else: FOV row omitted (achieved uncomputable) — `_rank` treats an
    # absent "fov" row for a target that always constrains it (TargetSpec.fov_deg
    # is required, never None) as a missing required metric.

    achieved_imh = metadata.image_height_mm if metadata is not None else None
    if achieved_imh is not None:
        rows.append(
            _exact_or_unconstrained_deviation(
                field="imh",
                target_value=target.image_height_mm,
                achieved=achieved_imh,
                converged="imh" in conv,
            )
        )
    # else: IMH row omitted — IMH is never in `_REQUIRED_TARGET_FIELDS`, so
    # this doesn't affect coverage/withheld status (§7-E).

    rows.append(
        _ceiling_or_unconstrained_deviation(
            field="ttl",
            limit=target.max_total_track_mm,
            achieved=paraxial.total_track_mm,
            converged="ttl" in conv,
        )
    )

    return rows


# ---------------------------------------------------------------------------
# B. Image quality (§7-B)
# ---------------------------------------------------------------------------

# Representative MTF frequency for the sag/tan summary — matches the existing
# `local_optimizer.mtf_band_summary(mtf, target_lpmm=100.0)` convention
# (reused pattern, not a new threshold).
_MTF_REPRESENTATIVE_LPMM = 100.0


def _representative_mtf(mtf: MTFResult) -> tuple[MetricValue, MetricValue]:
    """Conservative (worst-field) sag/tan MTF at the frequency point nearest
    `_MTF_REPRESENTATIVE_LPMM`, mirroring `mtf_band_summary`'s "min across
    fields" convention (already used for optimizer promotion gating)."""
    if not mtf.freq_lp_per_mm or not mtf.fields:
        return _metric(None), _metric(None)
    idx = min(
        range(len(mtf.freq_lp_per_mm)),
        key=lambda i: abs(mtf.freq_lp_per_mm[i] - _MTF_REPRESENTATIVE_LPMM),
    )
    sag_values = [
        f.sagittal[idx] for f in mtf.fields if idx < len(f.sagittal) and math.isfinite(f.sagittal[idx])
    ]
    tan_values = [
        f.tangential[idx]
        for f in mtf.fields
        if idx < len(f.tangential) and math.isfinite(f.tangential[idx])
    ]
    sag = min(sag_values) if sag_values else None
    tan = min(tan_values) if tan_values else None
    return _metric(sag), _metric(tan)


def _spot_rms_summary(spot: SpotDiagramResult | None) -> tuple[MetricValue, MetricValue]:
    """Per-field RMS spot radius (worst chromatic wavelength per field), then
    max/mean across fields. Sourced from `payload.spot_diagram`
    (`compute_spot_diagram`, `spot_diagram.py:131-233`) — fail closed
    (`unavailable`) when the payload didn't carry it."""
    if spot is None or not spot.fields:
        return _metric(None), _metric(None)
    per_field_rms: list[float] = []
    for field in spot.fields:
        wavelength_rms = [
            w.rms_radius_um for w in field.spots_by_wavelength if math.isfinite(w.rms_radius_um)
        ]
        if wavelength_rms:
            per_field_rms.append(max(wavelength_rms))
    if not per_field_rms:
        return _metric(None), _metric(None)
    return _metric(max(per_field_rms)), _metric(sum(per_field_rms) / len(per_field_rms))


def _field_curvature_peaks(fa: FieldAnalysisResult | None) -> tuple[MetricValue, MetricValue]:
    """Peak |delta| across the field for tangential/sagittal curvature."""
    if fa is None:
        return _metric(None), _metric(None)
    tan_values = [abs(v) for v in fa.tangential_field_curvature_mm if math.isfinite(v)]
    sag_values = [abs(v) for v in fa.sagittal_field_curvature_mm if math.isfinite(v)]
    return (
        _metric(max(tan_values) if tan_values else None),
        _metric(max(sag_values) if sag_values else None),
    )


def _max_distortion_pct(fa: FieldAnalysisResult | None) -> MetricValue:
    if fa is None:
        return _metric(None)
    values = [abs(v) for v in fa.distortion_pct if math.isfinite(v)]
    return _metric(max(values) if values else None)


def _relative_illumination_summary(extras: OpticalExtras) -> MetricValue:
    """Worst-field (min) RI across `optical_extras.ri_by_field` — the edge
    falloff is the risk signal a reviewer cares about. `None`/all-unavailable
    → unavailable (fail closed, §7-D)."""
    if extras.ri_by_field is None:
        return _metric(None)
    available = [
        m.value for m in extras.ri_by_field.values() if m.status == "available" and m.value is not None
    ]
    if not available:
        return _metric(None)
    return _metric(min(available))


def _image_quality(payload: OpticalSampleData, extras: OpticalExtras) -> ImageQualityMetrics:
    mtf_sag, mtf_tan = _representative_mtf(payload.mtf)
    rms_max, rms_mean = _spot_rms_summary(payload.spot_diagram)
    fc_tan, fc_sag = _field_curvature_peaks(payload.field_analysis)

    return ImageQualityMetrics(
        mtf_sag=mtf_sag,
        mtf_tan=mtf_tan,
        diffraction_cutoff_lp_per_mm=_metric(payload.mtf.cutoff_freq_lp_per_mm),
        rms_spot_radius_max_um=rms_max,
        rms_spot_radius_mean_um=rms_mean,
        min_strehl_ratio=_metric(
            payload.wavefront.min_strehl_ratio if payload.wavefront is not None else None
        ),
        rms_wavefront_error_waves=_metric(
            payload.wavefront.max_rms_wavefront_error_waves
            if payload.wavefront is not None
            else None
        ),
        field_curvature_tangential_delta_mm=fc_tan,
        field_curvature_sagittal_delta_mm=fc_sag,
        max_distortion_pct=_max_distortion_pct(payload.field_analysis),
        relative_illumination=_relative_illumination_summary(extras),
    )


# ---------------------------------------------------------------------------
# C. Manufacturability proxy (§7-C)
# ---------------------------------------------------------------------------


def _has_special_glass(materials: list[str]) -> bool:
    """True iff any *known* material (real datasheet nd, `zmx_materials`)
    has nd >= `_HIGH_INDEX_ND_THRESHOLD`. Unrecognized material names
    contribute nothing (neither true nor false evidence) — never guessed."""
    for name in materials:
        resolved = lookup_nd_vd(name)
        if resolved is not None and resolved[0] >= _HIGH_INDEX_ND_THRESHOLD:
            return True
    return False


def _manufacturability(payload: OpticalSampleData) -> ManufacturabilityProxy:
    if payload.metadata is None:
        raise ValueError(
            "score_candidate requires payload.metadata for manufacturability "
            "(n_pieces has no fallback source in this payload schema)"
        )
    return ManufacturabilityProxy(
        total_track_mm=payload.paraxial.total_track_mm,
        n_pieces=payload.metadata.n_pieces,
        has_special_glass=_has_special_glass(payload.metadata.materials),
        # Structural payload gap — see module docstring "已知结构性缺口".
        aspheric_term_count=_metric(None),
        aspheric_surface_count=_metric(None),
        chief_ray_angle_deg=_metric(None),
    )


# ---------------------------------------------------------------------------
# E. Rank (§7-E)
# ---------------------------------------------------------------------------


def _image_quality_norms(iq: ImageQualityMetrics) -> list[float]:
    values: list[float] = []
    for name in _BOUNDED_GOODNESS_IQ_FIELDS:
        metric: MetricValue = getattr(iq, name)
        if metric.status == "available" and metric.value is not None:
            values.append(max(0.0, min(1.0, metric.value)))
    return values


def _rank(
    deviations: list[TargetDeviation], image_quality: ImageQualityMetrics
) -> tuple[RankResult, str]:
    by_field = {d.field: d for d in deviations}
    missing: list[str] = []

    mtf_ok = (
        image_quality.mtf_sag.status == "available"
        and image_quality.mtf_tan.status == "available"
    )
    if not mtf_ok:
        missing.append("mtf")

    required_target_fields: list[str] = []
    for field in _REQUIRED_TARGET_FIELDS:
        dev = by_field.get(field)
        if dev is not None and dev.constraint_kind == "unconstrained":
            continue  # target=None -> not required, not in denominator (§7-E)
        required_target_fields.append(field)
        if dev is None:
            missing.append(field)

    required_count = 1 + len(required_target_fields)  # MTF + constrained {efl, fov}
    coverage_pct = (required_count - len(missing)) / required_count if required_count else 1.0
    coverage_pct = max(0.0, min(1.0, coverage_pct))

    if missing or coverage_pct < _MIN_COVERAGE_PCT:
        reason = ", ".join(missing) if missing else f"coverage_pct={coverage_pct:.0%}"
        return (
            RankResult(
                score=None, status="withheld", coverage_pct=coverage_pct, missing_metrics=missing
            ),
            f"withheld: 必需维覆盖不足 ({reason})",
        )

    dev_norms = [
        min(dev.rel_violation / _REL_TOLERANCE.get(dev.field, 0.05), 1.0)
        for dev in deviations
        if dev.constraint_kind != "unconstrained" and dev.rel_violation is not None
    ]
    iq_norms = _image_quality_norms(image_quality)

    mean_dev_norm = sum(dev_norms) / len(dev_norms) if dev_norms else 0.0
    mean_iq_goodness = sum(iq_norms) / len(iq_norms) if iq_norms else 0.0
    dev_component = 1.0 - mean_dev_norm
    iq_component = mean_iq_goodness

    score = _RANK_WEIGHT_DEVIATION * dev_component + _RANK_WEIGHT_IMAGE_QUALITY * iq_component
    score = max(0.0, min(1.0, score))

    explanation = (
        f"score={score:.3f} = {_RANK_WEIGHT_DEVIATION:.2f}*(1-mean_target_dev_norm"
        f"={mean_dev_norm:.3f}) + {_RANK_WEIGHT_IMAGE_QUALITY:.2f}*mean_iq_goodness"
        f"={mean_iq_goodness:.3f}; coverage={coverage_pct:.0%}"
        f" (dev fields n={len(dev_norms)}, iq fields n={len(iq_norms)})"
    )
    return (
        RankResult(score=score, status="ranked", coverage_pct=coverage_pct, missing_metrics=[]),
        explanation,
    )


# ---------------------------------------------------------------------------
# Public entry point (§7 前言)
# ---------------------------------------------------------------------------


def score_candidate(generated: GeneratedCandidate, target: TargetSpec) -> ScorecardRow:
    """Pure function: `ScorecardRow` from `generated.payload` +
    `generated.optical_extras` only — never touches optic/ZMX (§7)."""
    payload = generated.payload
    deviations = _target_deviations(generated.mode, payload, target)
    image_quality = _image_quality(payload, generated.optical_extras)
    manufacturability = _manufacturability(payload)
    rank, explanation = _rank(deviations, image_quality)

    return ScorecardRow(
        candidate_id=generated.candidate_id,
        mode=generated.mode,
        target_deviations=deviations,
        image_quality=image_quality,
        manufacturability=manufacturability,
        rank=rank,
        rank_explanation=explanation,
    )
