"""C1 scorecard 纯函数（Phase 10 探路阶 · C1-c）。

权威依据：`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§7（Scorecard 度量口径 A-E）+ §9（测试策略）。`score_candidate` 是纯函数：
只消费 `generated.payload`（`OpticalSampleData`）+ `generated.optical_extras`
（generator 阶段用 optic 预算的量，首要 RI），不自行触碰 optic/ZMX（§7 前言）。

度量提取路径（每个字段对应哪个 payload 字段，供审计）：
- A. Target 偏差：EFL ← `payload.paraxial.effective_focal_length_mm`；
  F# ← `payload.paraxial.f_number`；TTL ← `payload.paraxial.total_track_mm`；
  IMH ← 优先 `payload.metadata.image_height_mm`（全库 353/353 为 `None`，
  v2-02 未回填），缺则 `case_library._case_image_height_mm`（case-id token /
  index.json 解析链，纯 metadata 读取，不碰 optic/ZMX，见
  `_resolve_image_height_mm`）；FOV ← 优先
  `payload.metadata.fov_deg`（`optical_sample.py:32`），缺则由
  EFL+IMH 反算（`optical_calc.angular_field_of_view_deg`，见 `_resolve_fov_deg`）。
- B. 像质：MTF ← `payload.mtf`（`aberration.py::MTFResult`）；RMS 点列 ←
  优先 `payload.spot_diagram`（`spot_diagram.py::SpotDiagramResult`，全库
  353/353 为 `None`），缺则回退 `payload.mtf.rms_spot_radius_um_by_field`
  （E1-02 渐晕鲁棒口径，`MTFResult` 必填字段，见 `_spot_rms_summary`）；波前
  ← `payload.wavefront`（`wavefront_metrics.py::WavefrontMetricsResult`，
  可选，全库为 `None`）；场曲/畸变 ← `payload.field_analysis`
  （`field_analysis.py::FieldAnalysisResult`，可选，全库为 `None`）；
  RI ← `generated.optical_extras.ri_by_field`。
- C. 可制造性：TTL 同 A；片数 ← `payload.metadata.n_pieces`；玻璃类型 ←
  `payload.metadata.materials` + `zmx_materials.lookup_nd_vd`（真实 datasheet
  nd 表，非猜测）；非球面复杂度/CRA ← payload 结构性不携带，恒 unavailable
  （见下方"已知结构性缺口"）。
- E. 排序：由 A/B 组装，见 `_rank`。非有限（NaN/inf）achieved/violation/
  rel_violation 一律 fail closed：对应 target-deviation 行不产出，字段名进
  `_rank` 的 `missing_metrics`（无论该字段是否在 `_REQUIRED_TARGET_FIELDS`
  内）——非有限数值是比"结构性缺失"更严重的信号，绝不能悄悄参与
  `mean`/`clamp` 算出一个虚假分数（曾复现：NaN EFL 经
  `max(0.0, min(1.0, nan))` 掉进满分 1.0）。

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
from collections.abc import Mapping, Sequence

from app.core.aberration import MTFResult, mtf_values_at_index, nearest_mtf_freq_index
from app.core.case_library import _case_image_height_mm
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
    RepeatabilityMetrics,
    ScorecardRow,
    TargetDeviation,
    TargetSpec,
)
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


def _resolve_image_height_mm(payload: OpticalSampleData) -> float | None:
    """Achieved IMH: `metadata.image_height_mm` is `None` library-wide today
    (v2-02 wrote it to `index.json` but never back into each case's
    `CaseMetadata`, verified 353/353) — fall back to
    `case_library._case_image_height_mm`'s case-id-token / index.json
    resolution chain. That helper only reads static per-case metadata (the
    case's own fields plus a cached `index.json` manifest lookup) — no
    optic/ZMX touch, so calling it here stays inside `score_candidate`'s
    "payload + optical_extras only" contract (§7 前言). Its `0.0` return means
    "no resolvable IMH anywhere in the chain" — treated as unavailable, never
    fed into a `TargetDeviation.achieved` as a fabricated zero.
    """
    if payload.metadata is None:
        return None
    resolved = _case_image_height_mm(payload)
    return resolved if math.isfinite(resolved) and resolved > 0 else None


def _violation_is_finite(violation: float, rel_violation: float | None) -> bool:
    """Both the absolute and (when present) relative violation must be finite.
    A NaN/inf here means a corrupted achieved value slipped past the up-front
    `math.isfinite(achieved)` guard (e.g. an overflowing `abs(achieved - target)`);
    the caller fails closed (returns `None`) rather than let it reach `_rank`."""
    return math.isfinite(violation) and (rel_violation is None or math.isfinite(rel_violation))


def _exact_deviation(
    *, field: str, target_value: float, achieved: float, converged: bool
) -> TargetDeviation | None:
    """`None` when `achieved` (or a value derived from it) isn't finite —
    fail closed instead of letting a NaN/inf paraxial readout (Optiland edge
    case, see `AGENTS.md` "Optiland patching") propagate into `_rank` and
    silently win a perfect score (regression: NaN achieved used to clamp
    into `score=1.0` via `max(0.0, min(1.0, nan))`)."""
    if not math.isfinite(achieved):
        return None
    violation = abs(achieved - target_value)
    rel_violation = violation / abs(target_value) if target_value else None
    if not _violation_is_finite(violation, rel_violation):
        return None
    return TargetDeviation(
        field=field,
        constraint_kind="exact",
        target=target_value,
        achieved=achieved,
        violation=violation,
        rel_violation=rel_violation,
        converged_toward_target=converged,
    )


def _unconstrained_deviation(
    *, field: str, achieved: float, converged: bool
) -> TargetDeviation | None:
    if not math.isfinite(achieved):
        return None
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
) -> TargetDeviation | None:
    if target_value is None:
        return _unconstrained_deviation(field=field, achieved=achieved, converged=converged)
    return _exact_deviation(
        field=field, target_value=target_value, achieved=achieved, converged=converged
    )


def _ceiling_or_unconstrained_deviation(
    *, field: str, limit: float | None, achieved: float, converged: bool
) -> TargetDeviation | None:
    if limit is None:
        return _unconstrained_deviation(field=field, achieved=achieved, converged=converged)
    if not math.isfinite(achieved):
        return None
    violation = max(0.0, achieved - limit)  # short of ceiling never penalized
    rel_violation = violation / abs(limit) if limit else None
    if not _violation_is_finite(violation, rel_violation):
        return None
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
) -> tuple[list[TargetDeviation], list[str]]:
    """Returns `(rows, nonfinite_fields)`. `nonfinite_fields` lists every
    target-deviation field whose row was dropped because its achieved value
    (or a value derived from it) wasn't finite. `_rank` treats every entry in
    `nonfinite_fields` as a hard miss regardless of whether the field is
    nominally required (§7-E) — a corrupted number is categorically worse
    than a structurally absent one and must never silently pass through as a
    clean row (regression: TTL ceiling with NaN achieved used to compute
    `violation=max(0.0, nan-limit)=0.0`, a fabricated "within spec" reading).
    """
    conv = CONVERGED_FIELDS[mode]
    paraxial = payload.paraxial
    metadata = payload.metadata

    rows: list[TargetDeviation] = []
    nonfinite_fields: list[str] = []

    def _collect(field: str, dev: TargetDeviation | None) -> None:
        if dev is None:
            nonfinite_fields.append(field)
        else:
            rows.append(dev)

    _collect(
        "efl",
        _exact_or_unconstrained_deviation(
            field="efl",
            target_value=target.efl_mm,
            achieved=paraxial.effective_focal_length_mm,
            converged="efl" in conv,
        ),
    )
    _collect(
        "fnum",
        _exact_deviation(
            field="fnum",
            target_value=target.fnum,
            achieved=paraxial.f_number,
            converged="fnum" in conv,
        ),
    )

    achieved_imh = _resolve_image_height_mm(payload)

    achieved_fov = _resolve_fov_deg(
        metadata_fov_deg=(metadata.fov_deg if metadata is not None else None),
        efl_mm=paraxial.effective_focal_length_mm,
        image_height_mm=achieved_imh,
    )
    if achieved_fov is not None:
        _collect(
            "fov",
            _exact_or_unconstrained_deviation(
                field="fov",
                target_value=target.fov_deg,
                achieved=achieved_fov,
                converged="fov" in conv,
            ),
        )
    # else: FOV row omitted (achieved uncomputable, independent of whether
    # `target.fov_deg` is set) — `_rank` then has no "fov" row to read
    # `constraint_kind` off of, so it falls back to treating fov as required
    # and marks it missing. A target=None + achieved-uncomputable double-miss
    # is an edge case outside this fix's scope (target=None normally still
    # produces an `unconstrained` row whenever achieved *is* resolvable —
    # the path §7-E's oracle exercises, see `test_score_candidate_efl_target_
    # none_is_unconstrained_and_ranked`); not fixed here to keep this change
    # scoped to the same shape the `imh` fallback already has.

    if achieved_imh is not None:
        _collect(
            "imh",
            _exact_or_unconstrained_deviation(
                field="imh",
                target_value=target.image_height_mm,
                achieved=achieved_imh,
                converged="imh" in conv,
            ),
        )
    # else: IMH row omitted — IMH is never in `_REQUIRED_TARGET_FIELDS`, so
    # this doesn't affect coverage/withheld status (§7-E).

    _collect(
        "ttl",
        _ceiling_or_unconstrained_deviation(
            field="ttl",
            limit=target.max_total_track_mm,
            achieved=paraxial.total_track_mm,
            converged="ttl" in conv,
        ),
    )

    return rows, nonfinite_fields


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
    fields" convention (already used for optimizer promotion gating). Shares
    the nearest-frequency-index + per-field finite-value extraction with
    `local_optimizer.mtf_band_summary` via `aberration.nearest_mtf_freq_index`
    / `aberration.mtf_values_at_index` (was a third inline copy of the same
    pattern)."""
    idx = nearest_mtf_freq_index(mtf, _MTF_REPRESENTATIVE_LPMM)
    if idx is None:
        return _metric(None), _metric(None)
    sag_values = mtf_values_at_index(mtf, idx, ("sagittal",))
    tan_values = mtf_values_at_index(mtf, idx, ("tangential",))
    sag = min(sag_values) if sag_values else None
    tan = min(tan_values) if tan_values else None
    return _metric(sag), _metric(tan)


def _spot_rms_summary(payload: OpticalSampleData) -> tuple[MetricValue, MetricValue]:
    """Per-field RMS spot radius, then max/mean across fields. Prefers
    `payload.spot_diagram` (worst chromatic wavelength per field —
    `compute_spot_diagram`, `spot_diagram.py:131-233`) when present; falls
    back to `payload.mtf.rms_spot_radius_um_by_field` — the E1-02
    vignette-robust, single-wavelength per-field RMS that's already a
    *required* `MTFResult` field (`aberration.py:49`, same routing-floor
    metrology used elsewhere in the codebase) — when `spot_diagram` is
    unavailable. `spot_diagram` is `None` for the entire 353-case library
    today (v2-02 gap); without this fallback every RMS row in the scorecard
    reported a structural `unavailable` that wasn't true (real RMS data
    exists, just under a different already-required field)."""
    spot = payload.spot_diagram
    if spot is not None and spot.fields:
        per_field_rms: list[float] = []
        for field in spot.fields:
            wavelength_rms = [
                w.rms_radius_um for w in field.spots_by_wavelength if math.isfinite(w.rms_radius_um)
            ]
            if wavelength_rms:
                per_field_rms.append(max(wavelength_rms))
        if per_field_rms:
            return _metric(max(per_field_rms)), _metric(sum(per_field_rms) / len(per_field_rms))

    fallback_values = [v for v in payload.mtf.rms_spot_radius_um_by_field if math.isfinite(v)]
    if not fallback_values:
        return _metric(None), _metric(None)
    return _metric(max(fallback_values)), _metric(sum(fallback_values) / len(fallback_values))


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
    rms_max, rms_mean = _spot_rms_summary(payload)
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
    deviations: list[TargetDeviation],
    image_quality: ImageQualityMetrics,
    nonfinite_fields: Sequence[str] = (),
    *,
    rel_tolerances: Mapping[str, float] = _REL_TOLERANCE,
    rank_weights: Mapping[str, float] | None = None,
    min_coverage_pct: float = _MIN_COVERAGE_PCT,
) -> tuple[RankResult, str]:
    """`rel_tolerances` / `rank_weights` / `min_coverage_pct` are the §7-E
    "documented, not buried" tunables (module `Tunables` section) made
    configurable at the call boundary — defaults are the module constants,
    so every existing 2/3-positional-arg call site is unaffected.
    `rank_weights` keys: `"deviation"` / `"image_quality"` (a missing key
    falls back to that field's module default, not to 0)."""
    weights = rank_weights or {}  # None or empty -> all keys fall back to module defaults below
    weight_deviation = weights.get("deviation", _RANK_WEIGHT_DEVIATION)
    weight_image_quality = weights.get("image_quality", _RANK_WEIGHT_IMAGE_QUALITY)

    by_field = {d.field: d for d in deviations}
    missing: list[str] = []

    def _mark_missing(name: str) -> None:
        if name not in missing:
            missing.append(name)

    # Non-finite achieved values (§7-E doc note above) are always a hard
    # miss, regardless of whether the field is nominally "required" —
    # dropping a corrupted number silently would be worse than reporting it
    # missing.
    for field in nonfinite_fields:
        _mark_missing(field)

    mtf_ok = (
        image_quality.mtf_sag.status == "available"
        and image_quality.mtf_tan.status == "available"
    )
    if not mtf_ok:
        _mark_missing("mtf")

    required_target_fields: list[str] = []
    for field in _REQUIRED_TARGET_FIELDS:
        dev = by_field.get(field)
        if dev is not None and dev.constraint_kind == "unconstrained":
            continue  # target=None -> not required, not in denominator (§7-E)
        required_target_fields.append(field)
        if dev is None:
            _mark_missing(field)

    required_count = 1 + len(required_target_fields)  # MTF + constrained {efl, fov}
    coverage_pct = (required_count - len(missing)) / required_count if required_count else 1.0
    coverage_pct = max(0.0, min(1.0, coverage_pct))

    if missing or coverage_pct < min_coverage_pct:
        reason = ", ".join(missing) if missing else f"coverage_pct={coverage_pct:.0%}"
        return (
            RankResult(
                score=None, status="withheld", coverage_pct=coverage_pct, missing_metrics=missing
            ),
            f"withheld: 必需维覆盖不足 ({reason})",
        )

    dev_norms = [
        min(dev.rel_violation / rel_tolerances.get(dev.field, 0.05), 1.0)
        for dev in deviations
        if dev.constraint_kind != "unconstrained" and dev.rel_violation is not None
    ]
    iq_norms = _image_quality_norms(image_quality)

    mean_dev_norm = sum(dev_norms) / len(dev_norms) if dev_norms else 0.0
    mean_iq_goodness = sum(iq_norms) / len(iq_norms) if iq_norms else 0.0
    dev_component = 1.0 - mean_dev_norm
    iq_component = mean_iq_goodness

    score = weight_deviation * dev_component + weight_image_quality * iq_component
    score = max(0.0, min(1.0, score))

    explanation = (
        f"score={score:.3f} = {weight_deviation:.2f}*(1-mean_target_dev_norm"
        f"={mean_dev_norm:.3f}) + {weight_image_quality:.2f}*mean_iq_goodness"
        f"={mean_iq_goodness:.3f}; coverage={coverage_pct:.0%}"
        f" (dev fields n={len(dev_norms)}, iq fields n={len(iq_norms)})"
    )
    return (
        RankResult(score=score, status="ranked", coverage_pct=coverage_pct, missing_metrics=[]),
        explanation,
    )


# ---------------------------------------------------------------------------
# F. Repeatability (Phase 17 子项3 — §7 之外的新增维，见 candidate.py
# `RepeatabilityMetrics` docstring for scope/历史依据)
# ---------------------------------------------------------------------------


def _repeatability_series(samples: Sequence[float]) -> tuple[MetricValue, MetricValue, MetricValue]:
    """(min, max, spread) across ≥2 finite samples; all-unavailable otherwise
    (fail closed — a single sample or all-NaN is not a distribution)."""
    finite = [v for v in samples if math.isfinite(v)]
    if len(finite) < 2:
        return _metric(None), _metric(None), _metric(None)
    lo, hi = min(finite), max(finite)
    return _metric(lo), _metric(hi), _metric(hi - lo)


def _repeatability(
    repeat_rms_samples_um: Sequence[float], repeat_wfe_samples_waves: Sequence[float]
) -> RepeatabilityMetrics:
    """Pure aggregation of caller-supplied repeat-run samples (mock-chain
    testable — no CODE V, no `generators.py` involvement: a caller collects
    samples from however many real/independent runs it chooses and hands
    them here). `run_count` = the larger of the two series' lengths (a
    caller supplying only one series still gets an honest count, and
    non-finite samples still count toward it — "how many runs happened" is
    a different question from "how many produced a usable number"). `status`
    is `"available"` iff `run_count >= 2` AND at least one series actually
    resolved a finite min/max (otherwise `run_count=5` of all-NaN samples
    would misleadingly read as "available" with six N/A fields) — otherwise
    every field is forced unavailable by `RepeatabilityMetrics`'s own
    validator."""
    run_count = max(len(repeat_rms_samples_um), len(repeat_wfe_samples_waves), 1)
    rms_min, rms_max, rms_spread = _repeatability_series(repeat_rms_samples_um)
    wfe_min, wfe_max, wfe_spread = _repeatability_series(repeat_wfe_samples_waves)
    has_finite_distribution = rms_min.status == "available" or wfe_min.status == "available"
    if run_count >= 2 and has_finite_distribution:
        return RepeatabilityMetrics(
            run_count=run_count,
            status="available",
            rms_spot_radius_um_min=rms_min,
            rms_spot_radius_um_max=rms_max,
            rms_spot_radius_um_spread=rms_spread,
            wfe_waves_min=wfe_min,
            wfe_waves_max=wfe_max,
            wfe_waves_spread=wfe_spread,
            note=f"run_count={run_count}，跨 {run_count} 次独立跑取分布",
        )
    unavailable = _metric(None)
    return RepeatabilityMetrics(
        run_count=run_count,
        status="unavailable",
        rms_spot_radius_um_min=unavailable,
        rms_spot_radius_um_max=unavailable,
        rms_spot_radius_um_spread=unavailable,
        wfe_waves_min=unavailable,
        wfe_waves_max=unavailable,
        wfe_waves_spread=unavailable,
        note=f"run_count={run_count}，未做重复性验证",
    )


# ---------------------------------------------------------------------------
# Public entry point (§7 前言)
# ---------------------------------------------------------------------------


def score_candidate(
    generated: GeneratedCandidate,
    target: TargetSpec,
    *,
    rel_tolerances: Mapping[str, float] = _REL_TOLERANCE,
    rank_weights: Mapping[str, float] | None = None,
    min_coverage_pct: float = _MIN_COVERAGE_PCT,
    repeat_rms_samples_um: Sequence[float] = (),
    repeat_wfe_samples_waves: Sequence[float] = (),
) -> ScorecardRow:
    """Pure function: `ScorecardRow` from `generated.payload` +
    `generated.optical_extras` only — never touches optic/ZMX (§7).

    `rel_tolerances` / `rank_weights` / `min_coverage_pct` are the §7-E
    tunables (see module `Tunables` section + `_rank` docstring) exposed as
    keyword args — default to the same module constants, so every existing
    caller (all current tests, `orchestrate`) is unaffected.

    `repeat_rms_samples_um` / `repeat_wfe_samples_waves` (Phase 17 子项3):
    optional cross-run repeat-verification samples, empty by default — a
    single `orchestrate()` pass (`repeat_runs=1`, today's only wired path)
    never supplies these, so `repeatability` stays the honest
    `run_count=1`/`unavailable` default for every existing caller (zero
    behavior change). See `_repeatability` / `candidate.py
    RepeatabilityMetrics`."""
    payload = generated.payload
    deviations, nonfinite_fields = _target_deviations(generated.mode, payload, target)
    image_quality = _image_quality(payload, generated.optical_extras)
    manufacturability = _manufacturability(payload)
    rank, explanation = _rank(
        deviations,
        image_quality,
        nonfinite_fields,
        rel_tolerances=rel_tolerances,
        rank_weights=rank_weights,
        min_coverage_pct=min_coverage_pct,
    )
    repeatability = _repeatability(repeat_rms_samples_um, repeat_wfe_samples_waves)

    return ScorecardRow(
        candidate_id=generated.candidate_id,
        mode=generated.mode,
        target_deviations=deviations,
        image_quality=image_quality,
        manufacturability=manufacturability,
        rank=rank,
        rank_explanation=explanation,
        repeatability=repeatability,
    )
