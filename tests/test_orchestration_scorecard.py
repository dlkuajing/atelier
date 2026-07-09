"""Tests for `app.core.orchestration.scorecard` — C1 §7 Scorecard 度量口径.

权威依据：C1 spec §7（Scorecard 度量口径 A-E）+ §9（测试策略）。
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

覆盖（§9）：
- TTL ceiling 方向：短 TTL 不罚（violation=0），超上限才罚。
- per-field converged：RETRIEVED 全维 false（`ScoredCandidate` validator 校验）。
- 必需维 unavailable → withheld（MTF unavailable；EFL/FOV row 缺失）。
- EFL `target=None` 但 FOV+MTF 可用 → ranked：既有 `_rank` 直测（`_rank`
  覆盖率门算法本身的通用性），也有真实 `TargetSpec(efl_mm=None)` 经
  `score_candidate` 的端到端覆盖（`TargetSpec.efl_mm` 现为 `float | None`，
  见下方 `test_score_candidate_efl_target_none_is_unconstrained_and_ranked`）。
- MTF unavailable → withheld。
- RI 缺失路径（`optical_extras.ri_by_field=None` / 全 unavailable）。
- 极端偏差 clamp（norm 不超过 1.0，score 落在 [0,1]）。
- RI 数值锚（真实渐晕见 `test_relative_illumination.py`；此处验证
  `relative_illumination` 汇总正确接进 scorecard）。

关于 `_rank` 直测：即使 `TargetSpec.efl_mm`/`fov_deg` 现在允许 `None`
（`candidate.py`，`fnum` 仍恒必填），下方仍保留几个直接构造
`TargetDeviation`/`ImageQualityMetrics` 单测 `_rank` 的用例——它们测的是
`RankResult` 覆盖率门算法本身对任意 `constraint_kind="unconstrained"` 行
的通用处理，不依赖某个具体字段是否可选（模块私有函数直测，代码库既有
先例：`generators.py` 直接测试 `case_library._candidate_scenarios`）。
`test_score_candidate_efl_target_none_is_unconstrained_and_ranked` 补上了
经真实 `TargetSpec(efl_mm=None)` + `score_candidate` 的端到端路径。
"""

from __future__ import annotations

import math

import pytest

from app.core.case_library import _case_image_height_mm, load_case_library
from app.core.lens_system import Scenario
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import (
    CONVERGED_FIELDS,
    GeneratedCandidate,
    GenerationMode,
    ImageQualityMetrics,
    MetricValue,
    OpticalExtras,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
)
from app.core.orchestration.generators import RetrievalGenerator
from app.core.orchestration.scorecard import (
    _has_special_glass,
    _rank,
    _resolve_fov_deg,
    score_candidate,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _first_case_with_metadata() -> OpticalSampleData:
    for case in load_case_library():
        if case.metadata is not None:
            return case
    raise AssertionError("case library has no case with metadata")


_CASE = _first_case_with_metadata()

_WIDE_REQUEST: dict[str, object] = {
    "efl_mm": 2.8,
    "fov_deg": 78.0,
    "fnum": 2.4,
    "image_height_mm": 3.3,
    "priority": "cost",
}


def _wide_target_spec(**overrides: object) -> TargetSpec:
    kwargs = dict(_WIDE_REQUEST)
    kwargs.update(overrides)
    return TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, **kwargs)


def _metric(value: float | None = None) -> MetricValue:
    if value is None:
        return MetricValue(value=None, status="unavailable")
    return MetricValue(value=value, status="available")


def _full_image_quality(**overrides: MetricValue) -> ImageQualityMetrics:
    base = {
        "mtf_sag": _metric(0.5),
        "mtf_tan": _metric(0.5),
        "diffraction_cutoff_lp_per_mm": _metric(300.0),
        "rms_spot_radius_max_um": _metric(2.0),
        "rms_spot_radius_mean_um": _metric(1.0),
        "min_strehl_ratio": _metric(0.8),
        "rms_wavefront_error_waves": _metric(0.1),
        "field_curvature_tangential_delta_mm": _metric(0.05),
        "field_curvature_sagittal_delta_mm": _metric(0.05),
        "max_distortion_pct": _metric(1.5),
        "relative_illumination": _metric(0.7),
    }
    base.update(overrides)
    return ImageQualityMetrics(**base)


def _generated_candidate(
    mode: GenerationMode = GenerationMode.RETRIEVED,
    *,
    candidate_id: str = "test",
    ri_by_field: dict[str, MetricValue] | None = None,
) -> GeneratedCandidate:
    assert _CASE.metadata is not None
    return GeneratedCandidate(
        candidate_id=candidate_id,
        mode=mode,
        source_case_id=_CASE.metadata.case_id,
        payload=_CASE,
        optical_extras=OpticalExtras(ri_by_field=ri_by_field),
        generation_notes=["test fixture"],
    )


# ---------------------------------------------------------------------------
# A. Target deviations — extraction + constraint direction (§7-A, §9)
# ---------------------------------------------------------------------------


def test_score_candidate_produces_efl_fnum_ttl_rows_for_real_case():
    target = _wide_target_spec()
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    fields = {d.field for d in row.target_deviations}
    assert {"efl", "fnum", "ttl"}.issubset(fields)


def test_score_candidate_efl_deviation_matches_paraxial():
    target = _wide_target_spec(efl_mm=2.8)
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    efl_dev = next(d for d in row.target_deviations if d.field == "efl")
    assert efl_dev.constraint_kind == "exact"
    assert efl_dev.achieved == pytest.approx(_CASE.paraxial.effective_focal_length_mm)
    assert efl_dev.violation == pytest.approx(
        abs(_CASE.paraxial.effective_focal_length_mm - 2.8)
    )


def test_ttl_ceiling_short_ttl_not_penalized():
    """TTL below the ceiling limit -> violation=0 (not a symmetric target)."""
    high_limit = _CASE.paraxial.total_track_mm + 10.0  # far above actual TTL
    target = _wide_target_spec(max_total_track_mm=high_limit)
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    ttl_dev = next(d for d in row.target_deviations if d.field == "ttl")
    assert ttl_dev.constraint_kind == "ceiling"
    assert ttl_dev.violation == 0.0
    assert ttl_dev.rel_violation == 0.0


def test_ttl_ceiling_over_limit_is_penalized():
    low_limit = _CASE.paraxial.total_track_mm - 0.5  # below actual TTL
    target = _wide_target_spec(max_total_track_mm=low_limit)
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    ttl_dev = next(d for d in row.target_deviations if d.field == "ttl")
    assert ttl_dev.constraint_kind == "ceiling"
    assert ttl_dev.violation == pytest.approx(0.5)
    assert ttl_dev.violation > 0.0


def test_ttl_unconstrained_when_target_omits_limit():
    target = _wide_target_spec(max_total_track_mm=None)
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    ttl_dev = next(d for d in row.target_deviations if d.field == "ttl")
    assert ttl_dev.constraint_kind == "unconstrained"
    assert ttl_dev.target is None
    assert ttl_dev.violation == 0.0
    assert ttl_dev.rel_violation is None


# ---------------------------------------------------------------------------
# Non-finite (NaN/inf) achieved values fail closed, never fake a clean row
# (regression — see task report for the two reproduced bugs).
# ---------------------------------------------------------------------------


def test_nan_efl_achieved_is_withheld_not_perfect_score():
    """Regression: a NaN paraxial readout (Optiland edge case) must never
    silently propagate through `_rank`'s norm/mean/clamp chain into a
    fabricated `score=1.0`. Previously the unguarded arithmetic clamped NaN
    into a perfect score via `max(0.0, min(1.0, nan))` (reproduced: achieved
    EFL=NaN -> ranked first with score=1.0)."""
    target = _wide_target_spec()
    nan_paraxial = _CASE.paraxial.model_copy(update={"effective_focal_length_mm": float("nan")})
    broken_case = _CASE.model_copy(update={"paraxial": nan_paraxial})
    assert _CASE.metadata is not None
    generated = GeneratedCandidate(
        candidate_id="nan-efl",
        mode=GenerationMode.RETRIEVED,
        source_case_id=_CASE.metadata.case_id,
        payload=broken_case,
        optical_extras=OpticalExtras(),
        generation_notes=["synthetic NaN EFL fixture"],
    )
    row = score_candidate(generated, target)
    assert not any(d.field == "efl" for d in row.target_deviations)
    assert row.rank.status == "withheld"
    assert row.rank.score is None
    assert "efl" in row.rank.missing_metrics


def test_nan_ttl_achieved_never_produces_zero_violation():
    """Regression: NaN TTL with a ceiling limit must not silently compute
    `violation=max(0.0, nan-limit)=0.0` — a fabricated "within spec" reading.
    The TTL row must be dropped and the field marked missing (§7-E), even
    though TTL isn't one of the nominally "required" coverage fields."""
    target = _wide_target_spec(max_total_track_mm=_CASE.paraxial.total_track_mm + 10.0)
    nan_paraxial = _CASE.paraxial.model_copy(update={"total_track_mm": float("nan")})
    broken_case = _CASE.model_copy(update={"paraxial": nan_paraxial})
    assert _CASE.metadata is not None
    generated = GeneratedCandidate(
        candidate_id="nan-ttl",
        mode=GenerationMode.RETRIEVED,
        source_case_id=_CASE.metadata.case_id,
        payload=broken_case,
        optical_extras=OpticalExtras(),
        generation_notes=["synthetic NaN TTL fixture"],
    )
    row = score_candidate(generated, target)
    assert not any(d.field == "ttl" for d in row.target_deviations)
    assert "ttl" in row.rank.missing_metrics
    assert row.rank.status == "withheld"


# ---------------------------------------------------------------------------
# RMS spot radius fallback to `mtf.rms_spot_radius_um_by_field` (§7-B)
# ---------------------------------------------------------------------------


def test_rms_spot_radius_falls_back_to_mtf_when_spot_diagram_absent():
    """Regression: `spot_diagram` is `None` for the entire 353-case library,
    but `payload.mtf.rms_spot_radius_um_by_field` (E1-02 vignette-robust,
    *required* `MTFResult` field) already carries real per-field RMS data —
    scorecard must surface it instead of reporting a structural
    `unavailable` that isn't true."""
    assert _CASE.spot_diagram is None
    target = _wide_target_spec()
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    iq = row.image_quality
    assert iq.rms_spot_radius_max_um.status == "available"
    assert iq.rms_spot_radius_mean_um.status == "available"
    finite_values = [v for v in _CASE.mtf.rms_spot_radius_um_by_field if math.isfinite(v)]
    assert finite_values
    assert iq.rms_spot_radius_max_um.value == pytest.approx(max(finite_values))
    assert iq.rms_spot_radius_mean_um.value == pytest.approx(
        sum(finite_values) / len(finite_values)
    )


def test_imh_row_present_when_metadata_has_image_height():
    """Real cases in this library have `metadata.image_height_mm=None`
    (verified — no case populates it today), so the IMH row is exercised
    here via a synthetic copy with the field filled in."""
    assert _CASE.metadata is not None
    enriched_metadata = _CASE.metadata.model_copy(update={"image_height_mm": 3.2})
    enriched_case = _CASE.model_copy(update={"metadata": enriched_metadata})
    generated = GeneratedCandidate(
        candidate_id="synthetic-imh",
        mode=GenerationMode.RETRIEVED,
        source_case_id=enriched_metadata.case_id,
        payload=enriched_case,
        optical_extras=OpticalExtras(),
        generation_notes=["synthetic imh fixture"],
    )
    target = _wide_target_spec(image_height_mm=3.3)
    row = score_candidate(generated, target)
    imh_dev = next((d for d in row.target_deviations if d.field == "imh"), None)
    assert imh_dev is not None
    assert imh_dev.constraint_kind == "exact"
    assert imh_dev.achieved == pytest.approx(3.2)
    assert imh_dev.violation == pytest.approx(0.1)


def test_imh_row_present_via_case_id_index_fallback_for_real_case():
    """Regression: `metadata.image_height_mm` is `None` for the entire
    353-case library (v2-02 gap — verified by grep, no case populates it),
    but `case_library._case_image_height_mm`'s case-id-token / index.json
    resolution chain recovers a real, positive value for every case in the
    library. `score_candidate` must use that fallback instead of reporting a
    structural `unavailable` that isn't true — the IMH row must be present."""
    assert _CASE.metadata is not None and _CASE.metadata.image_height_mm is None
    target = _wide_target_spec()
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    imh_dev = next((d for d in row.target_deviations if d.field == "imh"), None)
    assert imh_dev is not None
    expected = _case_image_height_mm(_CASE)
    assert expected > 0
    assert imh_dev.achieved == pytest.approx(expected)
    assert imh_dev.constraint_kind == "exact"
    # presence doesn't block ranking (imh isn't a required metric either way)
    assert row.rank.status == "ranked"


# ---------------------------------------------------------------------------
# _resolve_fov_deg — FOV back-calc fallback (§7-A)
# ---------------------------------------------------------------------------


def test_resolve_fov_deg_prefers_metadata():
    assert _resolve_fov_deg(metadata_fov_deg=78.0, efl_mm=2.8, image_height_mm=3.3) == 78.0


def test_resolve_fov_deg_falls_back_to_efl_imh_backcalc():
    result = _resolve_fov_deg(metadata_fov_deg=None, efl_mm=2.8, image_height_mm=3.3)
    assert result is not None
    expected = 2.0 * math.degrees(math.atan(3.3 / 2.8))
    assert result == pytest.approx(expected)


def test_resolve_fov_deg_none_when_no_data_available():
    assert _resolve_fov_deg(metadata_fov_deg=None, efl_mm=2.8, image_height_mm=None) is None


# ---------------------------------------------------------------------------
# per-field converged consistency (§5.2, §9) — full round trip through
# ScoredCandidate's validator using real score_candidate output.
# ---------------------------------------------------------------------------


def test_retrieved_scorecard_all_fields_unconverged():
    target = _wide_target_spec()
    generated = _generated_candidate(GenerationMode.RETRIEVED)
    row = score_candidate(generated, target)
    conv = CONVERGED_FIELDS[GenerationMode.RETRIEVED]
    for dev in row.target_deviations:
        assert dev.converged_toward_target == (dev.field in conv)
        assert dev.converged_toward_target is False
    # round-trips through the honesty-invariant validator without raising
    ScoredCandidate(generated=generated, scorecard=row)


def test_target_converged_scorecard_matches_converged_fields_and_round_trips():
    target = _wide_target_spec()
    generated = _generated_candidate(GenerationMode.TARGET_CONVERGED)
    row = score_candidate(generated, target)
    conv = CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED]
    for dev in row.target_deviations:
        assert dev.converged_toward_target == (dev.field in conv)
    ttl_dev = next(d for d in row.target_deviations if d.field == "ttl")
    assert ttl_dev.converged_toward_target is False  # TTL never in Mode3 six-splice
    ScoredCandidate(generated=generated, scorecard=row)


# ---------------------------------------------------------------------------
# E. Rank — coverage gate / withheld (§7-E, §9) via direct `_rank` unit tests
# ---------------------------------------------------------------------------


def _dev(field: str, *, constraint_kind: str = "exact", target=5.0, rel_violation=0.0) -> TargetDeviation:
    return TargetDeviation(
        field=field,
        constraint_kind=constraint_kind,
        target=target,
        achieved=5.0,
        violation=0.0,
        rel_violation=rel_violation,
        converged_toward_target=False,
    )


def test_rank_withheld_when_mtf_unavailable():
    deviations = [_dev("efl"), _dev("fov")]
    iq = _full_image_quality(mtf_sag=_metric(), mtf_tan=_metric())
    result, explanation = _rank(deviations, iq)
    assert result.status == "withheld"
    assert result.score is None
    assert "mtf" in result.missing_metrics
    assert "mtf" in explanation


def test_rank_withheld_when_required_efl_row_missing():
    deviations = [_dev("fov")]  # efl row entirely absent
    iq = _full_image_quality()
    result, _ = _rank(deviations, iq)
    assert result.status == "withheld"
    assert "efl" in result.missing_metrics


def test_rank_ranked_when_efl_unconstrained_but_fov_and_mtf_available():
    """spec §9 oracle: EFL target=None but FOV+MTF available -> ranked.
    (Constructed directly — real `TargetSpec.efl_mm` is always required, see
    module docstring; this exercises the coverage-gate algorithm itself.)"""
    deviations = [
        _dev("efl", constraint_kind="unconstrained", target=None, rel_violation=None),
        _dev("fov"),
    ]
    iq = _full_image_quality()
    result, _ = _rank(deviations, iq)
    assert result.status == "ranked"
    assert result.score is not None
    assert result.coverage_pct == 1.0
    assert result.missing_metrics == []


def test_score_candidate_efl_target_none_is_unconstrained_and_ranked():
    """spec §7-E oracle, now exercised through the real `TargetSpec` +
    `score_candidate` path (not just the direct `_rank` unit test above):
    `TargetSpec.efl_mm` is `float | None` — `None` means EFL is
    unconstrained, drops out of `_rank`'s required-field denominator, and
    the candidate still ranks off FOV + MTF alone."""
    target = _wide_target_spec(efl_mm=None)
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    efl_dev = next(d for d in row.target_deviations if d.field == "efl")
    assert efl_dev.constraint_kind == "unconstrained"
    assert efl_dev.target is None
    assert "efl" not in row.rank.missing_metrics
    assert row.rank.status == "ranked"
    assert row.rank.score is not None


def test_rank_withheld_when_fov_row_missing_but_efl_present():
    deviations = [_dev("efl")]  # fov row absent, fov is always constrained in real TargetSpec
    iq = _full_image_quality()
    result, _ = _rank(deviations, iq)
    assert result.status == "withheld"
    assert "fov" in result.missing_metrics


def test_rank_coverage_below_threshold_withholds():
    # efl row absent AND mtf unavailable -> 2 of 3 required metrics missing,
    # coverage = 1/3 ~= 0.33 < 0.8 threshold
    deviations = [_dev("fov")]
    iq = _full_image_quality(mtf_sag=_metric(), mtf_tan=_metric())  # mtf also missing
    result, _ = _rank(deviations, iq)
    assert result.coverage_pct < 0.8
    assert result.status == "withheld"


# ---------------------------------------------------------------------------
# Extreme deviation clamp (§9)
# ---------------------------------------------------------------------------


def test_extreme_target_deviation_clamps_score_into_unit_interval():
    wildly_off_target = _wide_target_spec(efl_mm=500.0, fov_deg=1.0, fnum=16.0)
    generated = _generated_candidate()
    row = score_candidate(generated, wildly_off_target)
    assert row.rank.status == "ranked"
    assert row.rank.score is not None
    assert 0.0 <= row.rank.score <= 1.0
    for dev in row.target_deviations:
        if dev.rel_violation is not None:
            # norm = min(rel_violation/tol, 1.0) never exceeds 1.0, so no dev
            # can individually blow the aggregate score below 0 or above 1
            assert dev.rel_violation >= 0.0


# ---------------------------------------------------------------------------
# D/B. RI consumption in image_quality (§7-D, §7-B)
# ---------------------------------------------------------------------------


def test_relative_illumination_unavailable_when_extras_none():
    target = _wide_target_spec()
    generated = _generated_candidate(ri_by_field=None)
    row = score_candidate(generated, target)
    assert row.image_quality.relative_illumination.status == "unavailable"
    assert row.image_quality.relative_illumination.value is None


def test_relative_illumination_unavailable_when_all_fields_unavailable():
    target = _wide_target_spec()
    generated = _generated_candidate(
        ri_by_field={"0.0": _metric(), "1.0": _metric()}
    )
    row = score_candidate(generated, target)
    assert row.image_quality.relative_illumination.status == "unavailable"


def test_relative_illumination_is_worst_field_min_across_available():
    target = _wide_target_spec()
    generated = _generated_candidate(
        ri_by_field={
            "0.0": _metric(1.0),
            "0.5": _metric(0.8),
            "1.0": _metric(0.4),
        }
    )
    row = score_candidate(generated, target)
    assert row.image_quality.relative_illumination.status == "available"
    assert row.image_quality.relative_illumination.value == pytest.approx(0.4)


def test_relative_illumination_real_generator_wiring_end_to_end():
    """Full integration: RetrievalGenerator -> score_candidate, RI actually
    computed from a real optic (see test_relative_illumination.py for the
    numeric anchor on the raw compute)."""
    target = _wide_target_spec()
    generator = RetrievalGenerator()
    candidates = generator.generate(target, target, n=2)
    assert candidates
    for candidate in candidates:
        row = score_candidate(candidate, target)
        # RI is either available (a real cos^4 value in (0, 1]) or explicitly
        # marked unavailable — never silently defaulted.
        ri = row.image_quality.relative_illumination
        assert ri.status in {"available", "unavailable"}
        if ri.status == "available":
            assert ri.value is not None
            assert 0.0 < ri.value <= 1.0


# ---------------------------------------------------------------------------
# C. Manufacturability (§7-C)
# ---------------------------------------------------------------------------


def test_manufacturability_has_special_glass_from_real_datasheet_table():
    # OKP1 is a real high-index resin in zmx_materials.MATERIAL_ND_VD (nd=1.636)
    assert _has_special_glass(["OKP1"]) is True
    # N-BK7 is a normal-index glass (nd=1.5168)
    assert _has_special_glass(["N-BK7"]) is False
    # unknown material contributes no evidence either way
    assert _has_special_glass(["totally-unknown-material-xyz"]) is False


def test_manufacturability_structural_gaps_are_unavailable_not_fabricated():
    target = _wide_target_spec()
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    mfg = row.manufacturability
    assert mfg.aspheric_term_count.status == "unavailable"
    assert mfg.aspheric_surface_count.status == "unavailable"
    assert mfg.chief_ray_angle_deg.status == "unavailable"
    assert mfg.is_proxy is True
    assert mfg.n_pieces == _CASE.metadata.n_pieces
    assert mfg.total_track_mm == pytest.approx(_CASE.paraxial.total_track_mm)


def test_manufacturability_raises_when_metadata_missing():
    stripped_case = _CASE.model_copy(update={"metadata": None})
    generated = GeneratedCandidate(
        candidate_id="no-metadata",
        mode=GenerationMode.RETRIEVED,
        source_case_id=None,
        payload=stripped_case,
        optical_extras=OpticalExtras(),
        generation_notes=["synthetic no-metadata fixture"],
    )
    target = _wide_target_spec()
    with pytest.raises(ValueError, match="requires payload.metadata"):
        score_candidate(generated, target)


# ---------------------------------------------------------------------------
# ScorecardRow — no pass/fail fields (structural re-assertion alongside
# candidate.py's own test; scorecard.py is the actual producer)
# ---------------------------------------------------------------------------


def test_score_candidate_output_has_no_pass_fail_fields():
    target = _wide_target_spec()
    generated = _generated_candidate()
    row = score_candidate(generated, target)
    forbidden = {"verdict", "passed", "qualified", "is_good", "pass", "fail", "ok", "good"}
    field_names = set(type(row).model_fields.keys())
    assert not (field_names & forbidden)
    assert row.rank_explanation  # non-empty explanation
