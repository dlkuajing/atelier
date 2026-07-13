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
    FnumAcceptedFinalEvidence,
    FnumLadderEvidence,
    GeneratedCandidate,
    GenerationMode,
    ImageQualityMetrics,
    ManufacturabilityProxy,
    MetricValue,
    OpticalExtras,
    RankResult,
    RepeatabilityMetrics,
    ScorecardRow,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
    fnum_gate_from_ladder_result,
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


def _fnum_evidence(achieved: bool | None) -> FnumLadderEvidence | None:
    if achieved is None:
        return None
    accepted = (
        FnumAcceptedFinalEvidence(
            status="measured",
            measured_fnum=2.4,
            fno_param_achieved=True,
            aut_converged=True,
            ray_traceable=True,
            effective_edge_used=0.3,
            ray_grid={
                "category": "ok",
                "refl_count": 0,
                "miss_count": 0,
                "ray_aiming_warning": False,
                "aperture_conflict_matched": None,
                "excerpt": None,
                "note": "positive measured listing evidence",
                "normal_completion": True,
                "abnormal_completion_matched": None,
            },
            quality_note="measured on accepted vignetted pupil",
            optimized_zmx_path="accepted.zmx",
        )
        if achieved
        else None
    )
    return FnumLadderEvidence(
        schema="atelier-p15-fno-ladder-v1",
        target_achieved=achieved,
        accepted_final=accepted,
        target_efl_mm=4.0,
        fnum_target=2.4,
        stage="B",
        rung_count=3,
        fnum_tolerance_pct=8.0,
        vig_ladder=(0.0, 0.2),
        ray_retry_vig_ladder=(0.2, 0.3),
        num_fields=3,
        extra_dof="both",
    )


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
        aspheric_term_count=_metric(4),
        aspheric_surface_count=_metric(6),
        chief_ray_angle_deg=_metric(),
    )


def _dummy_rank_withheld() -> RankResult:
    return RankResult(score=None, status="withheld", coverage_pct=0.0, missing_metrics=["mtf"])


def _target_deviations(
    mode: GenerationMode, *, fnum_ladder_achieved: bool | None = None
) -> list[TargetDeviation]:
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
            # 与 ScoredCandidate._enforce_consistency 期望公式同构：fnum 带
            # per-candidate 证据 gate（P15 带条件扩），其余维纯查表。
            converged_toward_target=(f in conv) and (f != "fnum" or fnum_ladder_achieved is True),
        )
        for f in fields
    ]


def _generated_candidate(
    mode: GenerationMode,
    candidate_id: str = "test",
    *,
    fnum_ladder_achieved: bool | None = None,
) -> GeneratedCandidate:
    assert _CASE.metadata is not None
    return GeneratedCandidate(
        candidate_id=candidate_id,
        mode=mode,
        source_case_id=_CASE.metadata.case_id,
        payload=_CASE,
        optical_extras=OpticalExtras(),
        generation_notes=["test fixture"],
        fnum_ladder_evidence=_fnum_evidence(fnum_ladder_achieved),
    )


def _scorecard_row(
    mode: GenerationMode,
    candidate_id: str = "test",
    *,
    fnum_ladder_achieved: bool | None = None,
) -> ScorecardRow:
    return ScorecardRow(
        candidate_id=candidate_id,
        mode=mode,
        target_deviations=_target_deviations(mode, fnum_ladder_achieved=fnum_ladder_achieved),
        image_quality=_dummy_image_quality(),
        manufacturability=_dummy_manufacturability(),
        rank=_dummy_rank_withheld(),
        rank_explanation="test fixture, no real ranking",
    )


def _scored_candidate(
    mode: GenerationMode,
    candidate_id: str = "test",
    *,
    fnum_ladder_achieved: bool | None = None,
) -> ScoredCandidate:
    return ScoredCandidate(
        generated=_generated_candidate(
            mode, candidate_id, fnum_ladder_achieved=fnum_ladder_achieved
        ),
        scorecard=_scorecard_row(mode, candidate_id, fnum_ladder_achieved=fnum_ladder_achieved),
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
    # P15 带条件扩（orchestrator 裁决 2026-07-11）：表语义=能力上限。efl 无条件
    # （接缝1 真机验证）；fnum **带条件**——converged=Yes 还需该候选自己的
    # ladder 四条件 target_achieved=True（fnum_ladder_achieved gate，全矩阵
    # 14 真机 ladder 验证 0 假阳性），ladder 未跑/未达标恒 No。
    assert CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED] == frozenset({"efl", "fnum"})
    # TTL 恒不在收敛维内（Mode3 六接缝不含 TTL，§10）
    assert "ttl" not in CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED]
    # IMH 可由 Stage C RIH/receipt 验证 achieved，FOV 可同源派生/实测；
    # 二者仍不属于 Stage B optimizer 的 converged 维，不得偷换语义。
    assert "imh" not in CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED]
    assert "fov" not in CONVERGED_FIELDS[GenerationMode.TARGET_CONVERGED]


def test_converged_fields_is_immutable():
    """诚实不变量真值表运行时不可被绕过类型层改写（`MappingProxyType`）。"""
    with pytest.raises(TypeError):
        CONVERGED_FIELDS[GenerationMode.RETRIEVED] = frozenset({"efl"})


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
# RepeatabilityMetrics (Phase 17 子项3, §5.3 extension)
# ---------------------------------------------------------------------------


def test_scorecard_row_repeatability_defaults_to_unavailable_single_run():
    """Constructing a `ScorecardRow` without an explicit `repeatability` (as
    every pre-P17-3 fixture in this test suite still does) must land on the
    same honest fail-closed state `scorecard.py::score_candidate` produces
    for `repeat_runs=1` — not raise, not silently fabricate a distribution."""
    row = _scorecard_row(GenerationMode.RETRIEVED)
    r = row.repeatability
    assert r.run_count == 1
    assert r.status == "unavailable"
    assert r.rms_spot_radius_um_min.status == "unavailable"
    assert r.wfe_waves_max.status == "unavailable"


def test_repeatability_metrics_available_requires_matching_field_statuses():
    unavailable = MetricValue(value=None, status="unavailable")
    available = MetricValue(value=1.0, status="available")

    with pytest.raises(ValueError, match="全部分布字段必须 unavailable"):
        RepeatabilityMetrics(
            run_count=1,
            status="unavailable",
            rms_spot_radius_um_min=available,  # inconsistent: unavailable status, available field
            rms_spot_radius_um_max=unavailable,
            rms_spot_radius_um_spread=unavailable,
            wfe_waves_min=unavailable,
            wfe_waves_max=unavailable,
            wfe_waves_spread=unavailable,
            note="test",
        )


def test_repeatability_metrics_available_status_round_trips():
    metric = MetricValue(value=12.6, status="available")
    unavailable = MetricValue(value=None, status="unavailable")
    r = RepeatabilityMetrics(
        run_count=3,
        status="available",
        rms_spot_radius_um_min=metric,
        rms_spot_radius_um_max=metric,
        rms_spot_radius_um_spread=metric,
        wfe_waves_min=unavailable,
        wfe_waves_max=unavailable,
        wfe_waves_spread=unavailable,
        note="run_count=3",
    )
    assert r.status == "available"
    assert r.rms_spot_radius_um_min.value == 12.6


# ---------------------------------------------------------------------------
# ScoredCandidate consistency validator (§5.2, §9)
# ---------------------------------------------------------------------------


def test_scored_candidate_valid_retrieved_round_trips():
    sc = _scored_candidate(GenerationMode.RETRIEVED)
    assert sc.mode is GenerationMode.RETRIEVED


def test_scored_candidate_valid_target_converged_round_trips():
    sc = _scored_candidate(GenerationMode.TARGET_CONVERGED)
    assert sc.mode is GenerationMode.TARGET_CONVERGED


# ---------------------------------------------------------------------------
# P15 带条件扩：fnum per-candidate 证据 gate（orchestrator 裁决 2026-07-11）
# ---------------------------------------------------------------------------


def test_scored_candidate_fnum_gate_true_round_trips_with_fnum_yes():
    """gate=True（候选自己的 ladder 四条件达标）→ fnum converged=Yes 合法。"""
    sc = _scored_candidate(GenerationMode.TARGET_CONVERGED, fnum_ladder_achieved=True)
    fnum_dev = next(d for d in sc.scorecard.target_deviations if d.field == "fnum")
    assert fnum_dev.converged_toward_target is True


@pytest.mark.parametrize("gate", [None, False])
def test_scored_candidate_forged_fnum_yes_without_gate_raises(gate: bool | None):
    """ladder 未跑（None）/未达标（False）时伪造 fnum converged=Yes → 构造期
    拒绝（诚实不变量：无四条件证据不给收敛背书）。"""
    generated = _generated_candidate(GenerationMode.TARGET_CONVERGED, fnum_ladder_achieved=gate)
    deviations = [
        d.model_copy(update={"converged_toward_target": True}) if d.field == "fnum" else d
        for d in _target_deviations(GenerationMode.TARGET_CONVERGED, fnum_ladder_achieved=gate)
    ]
    scorecard = ScorecardRow(
        candidate_id="test",
        mode=GenerationMode.TARGET_CONVERGED,
        target_deviations=deviations,
        image_quality=_dummy_image_quality(),
        manufacturability=_dummy_manufacturability(),
        rank=_dummy_rank_withheld(),
        rank_explanation="forged fnum converged without ladder evidence",
    )
    with pytest.raises(ValueError, match="fnum converged 与 mode"):
        ScoredCandidate(generated=generated, scorecard=scorecard)


def test_scored_candidate_fnum_gate_true_but_scorecard_says_no_raises():
    """双向强一致：有证据（gate=True）却漏标 No 同样拒绝——converged 列必须
    与证据逐字段一致，防止展示层静默丢真实收敛信息。"""
    generated = _generated_candidate(GenerationMode.TARGET_CONVERGED, fnum_ladder_achieved=True)
    scorecard = _scorecard_row(
        GenerationMode.TARGET_CONVERGED,
        fnum_ladder_achieved=None,  # fixture 填 No
    )
    with pytest.raises(ValueError, match="fnum converged 与 mode"):
        ScoredCandidate(generated=generated, scorecard=scorecard)


def test_generated_candidate_retrieved_with_fnum_gate_raises():
    """RETRIEVED（零优化）候选携带 F# ladder 证据 = provenance 矛盾，构造期拒绝。"""
    assert _CASE.metadata is not None
    with pytest.raises(ValueError, match="fnum_ladder_evidence"):
        GeneratedCandidate(
            candidate_id="test",
            mode=GenerationMode.RETRIEVED,
            source_case_id=_CASE.metadata.case_id,
            payload=_CASE,
            optical_extras=OpticalExtras(),
            generation_notes=["test fixture"],
            fnum_ladder_evidence=_fnum_evidence(True),
        )


def test_fnum_gate_from_ladder_result_requires_four_condition_record():
    """gate 判定只认引擎四条件 target_achieved 记录（禁 aut_converged 单维）；
    fail-closed：非 Mapping/缺键/非 True 一律 False。"""
    valid = _fnum_evidence(True)
    assert valid is not None
    raw = valid.model_dump()
    assert fnum_gate_from_ladder_result(raw) is True
    negative = _fnum_evidence(False)
    assert negative is not None
    assert fnum_gate_from_ladder_result(negative.model_dump()) is False
    assert fnum_gate_from_ladder_result({**raw, "target_achieved": "True"}) is False
    assert fnum_gate_from_ladder_result({**raw, "accepted_final": None}) is False
    for missing in ("schema", "num_fields", "accepted_final"):
        forged = dict(raw)
        forged.pop(missing)
        assert fnum_gate_from_ladder_result(forged) is False
    forged_final = dict(raw["accepted_final"])
    forged_final["ray_traceable"] = "True"
    assert fnum_gate_from_ladder_result({**raw, "accepted_final": forged_final}) is False
    impossible_fnum = dict(raw["accepted_final"])
    impossible_fnum.update({"measured_fnum": 99.0, "fno_param_achieved": True})
    assert (
        fnum_gate_from_ladder_result(
            {
                **raw,
                "fnum_target": 2.0,
                "fnum_tolerance_pct": 8.0,
                "accepted_final": impossible_fnum,
            }
        )
        is False
    )
    contradictory_grid = dict(raw["accepted_final"])
    contradictory_grid["ray_grid"] = {
        **contradictory_grid["ray_grid"],
        "category": "ok",
        "refl_count": 7,
    }
    assert fnum_gate_from_ladder_result({**raw, "accepted_final": contradictory_grid}) is False
    unknown_grid = dict(raw["accepted_final"])
    unknown_grid["ray_grid"] = {**unknown_grid["ray_grid"], "unknown_failure_count": 0}
    assert fnum_gate_from_ladder_result({**raw, "accepted_final": unknown_grid}) is False
    # aut_converged 单维（P15 Stage 2 证明的双假阳性维度）绝不放行
    assert fnum_gate_from_ladder_result({"aut_converged": "1"}) is False
    assert fnum_gate_from_ladder_result({}) is False
    assert fnum_gate_from_ladder_result(None) is False
    assert fnum_gate_from_ladder_result("target_achieved") is False


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
