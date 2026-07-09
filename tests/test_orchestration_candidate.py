"""Tests for `app.core.orchestration.candidate` — C1 数据模型 + 诚实不变量。

权威依据：C1 spec §5（数据模型）+ §9（测试策略，诚实不变量测试锚）。
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

覆盖（§9）：
- `ScorecardRow` 无合格字段（结构断言）。
- `ScoredCandidate` 中 `scorecard.mode != generated.mode` → validator `raise`。
- per-field converged 一致性：RETRIEVED 全维 false；TARGET_CONVERGED 仅
  efl/fov/fnum/imh=true 而 ttl=false（不一致 → raise）。
- `CandidateSet` 全 `RETRIEVED` → `honesty_banner` 自动为
  `NO_TARGET_CONVERGED_BANNER`（派生、无法置空/伪造）。
- `CandidateSet` 含 `TARGET_CONVERGED` → 无 banner。
"""

from __future__ import annotations

import pytest

from app.core.case_library import load_case_library
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration.candidate import (
    CONVERGED_FIELDS,
    NO_TARGET_CONVERGED_BANNER,
    CandidateSet,
    CandidateSetSummary,
    GeneratedCandidate,
    GenerationMode,
    ImageQualityMetrics,
    ManufacturabilityProxy,
    MetricValue,
    OpticalExtras,
    RankResult,
    ScorecardRow,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
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


def _metric(value: float | None = None) -> MetricValue:
    if value is None:
        return MetricValue(value=None, status="unavailable")
    return MetricValue(value=value, status="available")


def _dummy_image_quality() -> ImageQualityMetrics:
    return ImageQualityMetrics(
        mtf_sag=_metric(),
        mtf_tan=_metric(),
        diffraction_cutoff_lp_per_mm=_metric(),
        rms_spot_radius_max_um=_metric(),
        rms_spot_radius_mean_um=_metric(),
        min_strehl_ratio=_metric(),
        rms_wavefront_error_waves=_metric(),
        field_curvature_tangential_delta_mm=_metric(),
        field_curvature_sagittal_delta_mm=_metric(),
        max_distortion_pct=_metric(),
        relative_illumination=_metric(),
    )


def _dummy_manufacturability() -> ManufacturabilityProxy:
    return ManufacturabilityProxy(
        total_track_mm=_CASE.paraxial.total_track_mm,
        n_pieces=_CASE.metadata.n_pieces if _CASE.metadata else 5,
        has_special_glass=False,
        aspheric_term_count=4,
        aspheric_surface_count=6,
        chief_ray_angle_deg=_metric(),
    )


def _dummy_rank_withheld() -> RankResult:
    return RankResult(score=None, status="withheld", coverage_pct=0.0, missing_metrics=["mtf"])


def _target_deviations(mode: GenerationMode) -> list[TargetDeviation]:
    conv = CONVERGED_FIELDS[mode]
    fields = ["efl", "fov", "fnum", "imh", "ttl"]
    return [
        TargetDeviation(
            field=f,
            constraint_kind="ceiling" if f == "ttl" else "exact",
            target=5.0,
            achieved=5.0,
            violation=0.0,
            rel_violation=0.0,
            converged_toward_target=f in conv,
        )
        for f in fields
    ]


def _generated_candidate(mode: GenerationMode, candidate_id: str = "test") -> GeneratedCandidate:
    assert _CASE.metadata is not None
    return GeneratedCandidate(
        candidate_id=candidate_id,
        mode=mode,
        source_case_id=_CASE.metadata.case_id,
        payload=_CASE,
        optical_extras=OpticalExtras(),
        generation_notes=["test fixture"],
    )


def _scorecard_row(mode: GenerationMode, candidate_id: str = "test") -> ScorecardRow:
    return ScorecardRow(
        candidate_id=candidate_id,
        mode=mode,
        target_deviations=_target_deviations(mode),
        image_quality=_dummy_image_quality(),
        manufacturability=_dummy_manufacturability(),
        rank=_dummy_rank_withheld(),
        rank_explanation="test fixture, no real ranking",
    )


def _scored_candidate(mode: GenerationMode, candidate_id: str = "test") -> ScoredCandidate:
    return ScoredCandidate(
        generated=_generated_candidate(mode, candidate_id),
        scorecard=_scorecard_row(mode, candidate_id),
    )


def _target_spec() -> TargetSpec:
    assert _CASE.metadata is not None
    return TargetSpec(
        scenario=_CASE.metadata.scenario,
        efl_mm=_CASE.metadata.computed_efl_mm,
        fov_deg=_CASE.metadata.fov_deg,
        fnum=_CASE.paraxial.f_number,
    )


# ---------------------------------------------------------------------------
# GenerationMode / CONVERGED_FIELDS
# ---------------------------------------------------------------------------


def test_generation_mode_string_values():
    assert GenerationMode.RETRIEVED.value == "retrieved"
    assert GenerationMode.TARGET_CONVERGED.value == "target-converged"


def test_converged_fields_matches_spec():
    assert CONVERGED_FIELDS[GenerationMode.RETRIEVED] == frozenset()
    assert CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED] == frozenset(
        {"efl", "fnum", "imh", "fov"}
    )
    # TTL 恒不在收敛维内（Mode3 六接缝不含 TTL，§10）
    assert "ttl" not in CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED]


# ---------------------------------------------------------------------------
# GeneratedCandidate
# ---------------------------------------------------------------------------


def test_generated_candidate_is_target_converged_property():
    retrieved = _generated_candidate(GenerationMode.RETRIEVED)
    converged = _generated_candidate(GenerationMode.TARGET_CONVERGED)
    assert retrieved.is_target_converged is False
    assert converged.is_target_converged is True


# ---------------------------------------------------------------------------
# ScorecardRow — no pass/fail fields (structural assertion, §9)
# ---------------------------------------------------------------------------


def test_scorecard_row_has_no_pass_fail_fields():
    forbidden = {"verdict", "passed", "qualified", "is_good", "pass", "fail", "ok", "good"}
    field_names = set(ScorecardRow.model_fields.keys())
    assert not (field_names & forbidden), field_names & forbidden


# ---------------------------------------------------------------------------
# ScoredCandidate consistency validator (§5.2, §9)
# ---------------------------------------------------------------------------


def test_scored_candidate_valid_retrieved_round_trips():
    sc = _scored_candidate(GenerationMode.RETRIEVED)
    assert sc.mode is GenerationMode.RETRIEVED


def test_scored_candidate_valid_target_converged_round_trips():
    sc = _scored_candidate(GenerationMode.TARGET_CONVERGED)
    assert sc.mode is GenerationMode.TARGET_CONVERGED


def test_scored_candidate_mode_mismatch_raises():
    generated = _generated_candidate(GenerationMode.RETRIEVED)
    mismatched_scorecard = _scorecard_row(GenerationMode.TARGET_CONVERGED)
    with pytest.raises(ValueError, match="scorecard.mode != generated.mode"):
        ScoredCandidate(generated=generated, scorecard=mismatched_scorecard)


def test_scored_candidate_retrieved_with_forged_converged_field_raises():
    generated = _generated_candidate(GenerationMode.RETRIEVED)
    deviations = _target_deviations(GenerationMode.RETRIEVED)
    # forge: claim "efl" converged even though RETRIEVED converges nothing
    deviations[0] = deviations[0].model_copy(update={"converged_toward_target": True})
    scorecard = ScorecardRow(
        candidate_id="test",
        mode=GenerationMode.RETRIEVED,
        target_deviations=deviations,
        image_quality=_dummy_image_quality(),
        manufacturability=_dummy_manufacturability(),
        rank=_dummy_rank_withheld(),
        rank_explanation="forged converged field",
    )
    with pytest.raises(ValueError, match="converged 与 mode"):
        ScoredCandidate(generated=generated, scorecard=scorecard)


def test_scored_candidate_target_converged_ttl_must_stay_false():
    generated = _generated_candidate(GenerationMode.TARGET_CONVERGED)
    deviations = _target_deviations(GenerationMode.TARGET_CONVERGED)
    ttl_dev = next(d for d in deviations if d.field == "ttl")
    assert ttl_dev.converged_toward_target is False  # sanity: fixture is honest
    # forge: claim ttl also converged (Mode3 六接缝不含 TTL，§10)
    forged = [
        d.model_copy(update={"converged_toward_target": True}) if d.field == "ttl" else d
        for d in deviations
    ]
    scorecard = ScorecardRow(
        candidate_id="test",
        mode=GenerationMode.TARGET_CONVERGED,
        target_deviations=forged,
        image_quality=_dummy_image_quality(),
        manufacturability=_dummy_manufacturability(),
        rank=_dummy_rank_withheld(),
        rank_explanation="forged ttl converged",
    )
    with pytest.raises(ValueError, match="ttl converged 与 mode"):
        ScoredCandidate(generated=generated, scorecard=scorecard)


# ---------------------------------------------------------------------------
# CandidateSet — honesty_banner / modes_present derivation (§5.4, §9)
# ---------------------------------------------------------------------------


def test_candidate_set_all_retrieved_gets_default_banner():
    candidates = [_scored_candidate(GenerationMode.RETRIEVED)]
    cs = CandidateSet(
        target=_target_spec(),
        candidates=candidates,
        summary=CandidateSetSummary(candidate_count=1),
    )
    assert cs.modes_present == {GenerationMode.RETRIEVED}
    assert cs.honesty_banner == NO_TARGET_CONVERGED_BANNER


def test_candidate_set_with_target_converged_candidate_has_no_banner():
    candidates = [_scored_candidate(GenerationMode.TARGET_CONVERGED)]
    cs = CandidateSet(
        target=_target_spec(),
        candidates=candidates,
        summary=CandidateSetSummary(candidate_count=1),
    )
    assert GenerationMode.TARGET_CONVERGED in cs.modes_present
    assert cs.honesty_banner is None


def test_candidate_set_banner_and_modes_present_not_settable_via_constructor():
    candidates = [_scored_candidate(GenerationMode.RETRIEVED)]
    # Attempt to forge computed_field values through the constructor — pydantic's
    # default extra="ignore" silently drops them; the properties stay derived.
    cs = CandidateSet(
        target=_target_spec(),
        candidates=candidates,
        summary=CandidateSetSummary(candidate_count=1),
        honesty_banner="FORGED — everything converged, trust me",
        modes_present={GenerationMode.TARGET_CONVERGED},
    )
    assert cs.honesty_banner == NO_TARGET_CONVERGED_BANNER
    assert cs.modes_present == {GenerationMode.RETRIEVED}


def test_candidate_set_mixed_modes_present_reflects_both():
    candidates = [
        _scored_candidate(GenerationMode.RETRIEVED, candidate_id="r1"),
        _scored_candidate(GenerationMode.TARGET_CONVERGED, candidate_id="t1"),
    ]
    cs = CandidateSet(
        target=_target_spec(),
        candidates=candidates,
        summary=CandidateSetSummary(candidate_count=2),
    )
    assert cs.modes_present == {GenerationMode.RETRIEVED, GenerationMode.TARGET_CONVERGED}
    assert cs.honesty_banner is None
