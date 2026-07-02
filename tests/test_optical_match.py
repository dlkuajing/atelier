"""Tests for /api/optical/match — real case retrieval (phase v2-03)."""

import math

import pytest
from fastapi.testclient import TestClient

from app.core.case_library import load_case_library, match_case
from app.core.image_quality_floor import image_quality_floor_gap_score
from app.core.lens_system import Scenario
from app.core.local_optimizer import (
    _apply_radius_changes,
    _finite_float,
    _load_probe_optic,
    mtf_multiband_summary,
)
from app.core.optical_sample import OptimizationMetricSnapshot
from app.main import app

client = TestClient(app)


def _sample_floor_gap(sample) -> float | None:
    bands = mtf_multiband_summary(sample.mtf)
    rms_values = [value for value in sample.mtf.rms_spot_radius_um_by_field if math.isfinite(value)]
    metrics = OptimizationMetricSnapshot(
        effective_focal_length_mm=sample.metadata.computed_efl_mm,
        f_number=sample.paraxial.f_number,
        total_track_mm=sample.paraxial.total_track_mm,
        mtf_max_field_frac=sample.metadata.mtf_max_field_frac,
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
        max_rms_spot_radius_um=max(rms_values) if rms_values else None,
    )
    return image_quality_floor_gap_score(metrics)


def test_probe_radius_change_writer_updates_geometry():
    optic = _load_probe_optic("5P_F2.0_FOV78.7_EFL3.8_IMH3.3_TTL4.35.zmx", 78.7)
    before = _finite_float(optic.surfaces.radii[6])
    assert before is not None
    after = before * 1.01

    _apply_radius_changes(optic, ((6, after),))

    assert _finite_float(optic.surfaces.radii[6]) == after
    assert _finite_float(optic.surfaces.surfaces[6].geometry.radius) == after


def test_match_case_nearest_wide():
    c = match_case(Scenario.SMARTPHONE_WIDE, 2.8, 2.4, 78.0)
    assert c is not None
    assert c.metadata.scenario == Scenario.SMARTPHONE_WIDE
    assert c.design_assessment is not None
    # nearest design to EFL 2.8 should land close to it
    assert abs(c.metadata.computed_efl_mm - 2.8) < 0.3


def test_match_case_seed_only_skips_heavy_design_assessment():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.8,
        2.4,
        78.0,
        image_height_mm=2.3,
        include_design_assessment=False,
    )
    assert c is not None
    assert c.metadata is not None
    assert c.metadata.scenario == Scenario.SMARTPHONE_WIDE
    assert c.design_assessment is None
    assert c.mtf.freq_lp_per_mm


def test_balanced_seed_only_selects_parameter_nearest_healthy_seed():
    # World-flip from the XASPHERE ingest fix: the whole ammo library is now
    # image-quality healthy, so balanced routing no longer chases the slow
    # floor-clean 3P seed. Parameter proximity (exact 5 elements + exact image
    # height) selects the exact real 5P seed; its high-frequency (250 lp/mm) MTF
    # is aperture-limited on the fast F/1.8 optic, which stays out of routing but
    # is still reported honestly by the floor gap.
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.0,
        2.0,
        78.0,
        image_height_mm=2.3,
        n_elements=5,
        priority="balanced",
        include_design_assessment=False,
    )
    assert c is not None
    assert c.metadata is not None
    assert c.design_assessment is None
    assert c.metadata.case_id == "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15"
    assert c.metadata.mtf_max_field_frac == pytest.approx(1.0)
    assert _sample_floor_gap(c) > 0.0
    assert mtf_multiband_summary(c.mtf).min_250 < 0.08


def test_match_case_high_fov_wide_can_cross_select_ultrawide_seed():
    """Phone short-focus matching can use the 89.5° real seed for high-FOV main requests."""
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.8,
        1.9,
        88.0,
        image_height_mm=2.9,
        n_elements=5,
        priority="performance",
    )
    assert c is not None
    assert c.metadata.scenario == Scenario.SMARTPHONE_ULTRAWIDE
    assert c.metadata.fov_deg == 89.5
    assert c.design_assessment is not None
    assert any("cross-selected" in r for r in c.design_assessment.rationale)


def test_covered_path_forbids_full_field_edge_performance_for_partial_winner():
    # E2-01 batch 1 (team-lead ruling): on the covered path a delivered winner that
    # only proves <1.0 field must explicitly forbid full-field edge-performance
    # claims -- the gap-path delivery gate carried this and the covered path must
    # too (expert-facing defense line, not just composite signals). A full-field
    # delivery must NOT carry it. NOTE: covered + real full-field delivery is
    # unroutable until the batch-2 patent-seed image-height fix, so the negative
    # case uses a full-field winner on the standard (non-covered) path.
    partial = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.8,
        1.9,
        88.0,
        image_height_mm=2.9,
        n_elements=5,
        priority="performance",
    )
    assert partial is not None and partial.design_assessment is not None
    assert partial.metadata.mtf_max_field_frac < 1.0
    coverage = partial.design_assessment.library_coverage_diagnostic
    assert coverage is not None and coverage.status == "covered"
    partial_gate = partial.design_assessment.draft_acceptance_gate
    assert partial_gate is not None
    assert any(
        "full-field edge-performance" in claim for claim in partial_gate.forbidden_claims
    )

    full_field = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.0,
        2.0,
        78.0,
        image_height_mm=2.3,
        n_elements=5,
        priority="balanced",
    )
    assert full_field is not None and full_field.design_assessment is not None
    assert full_field.metadata.mtf_max_field_frac == 1.0
    full_field_gate = full_field.design_assessment.draft_acceptance_gate
    assert full_field_gate is not None
    assert not any(
        "full-field edge-performance" in claim for claim in full_field_gate.forbidden_claims
    )


def test_faster_aperture_counts_as_requirement_met():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.7,
        2.0,
        60.0,
        image_height_mm=2.1,
        n_elements=4,
        priority="balanced",
    )
    assert c is not None
    assert c.design_assessment is not None
    coverage = {item.requirement_id: item for item in c.design_assessment.requirement_coverage}
    assert coverage["f_number"].status == "met"
    assert coverage["f_number"].delta is not None
    assert coverage["f_number"].delta < 0
    assert coverage["f_number"].next_action is None
    assert any("faster than or equal to target" in item for item in coverage["f_number"].evidence)


def test_balanced_fov_tradeoff_rejects_bad_fov_alternative_branch():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.0,
        2.0,
        78.0,
        image_height_mm=2.3,
        n_elements=5,
        priority="balanced",
    )
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    # World-flip from the XASPHERE ingest fix: the balanced default now routes to
    # the exact-element 5P F/1.8 seed, which meets F/# and element count; the
    # remaining gap is a minor FOV tradeoff (74.1 vs 78 deg) that the spec-repair
    # path auto-closes as a review note. A closer-FOV alternative is still
    # rejected for target-fit regressions.
    assert c.metadata.case_id == "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15"
    coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
    assert coverage["field_of_view"].status == "tradeoff"
    assert coverage["mtf_field_evidence"].status == "met"
    assert coverage["f_number"].status == "met"
    assert coverage["element_count"].status == "met"
    assert assessment.branch_selection_policy is not None
    # E2-01 batch 1: the enlarged 39-seed library surfaces the request's
    # first-order EFL/image-height/FOV inconsistency (EFL 3.0 vs first-order
    # 2.84 for image height 2.30 / FOV 78) more strongly, so the branch policy now
    # leads with the fov-spec-reconciliation repair rather than resolving straight
    # to the seed baseline. The winner is unchanged and the bad closer-FOV
    # alternative is still rejected (asserted below).
    assert assessment.branch_selection_policy.status == "strategy_resolution_required"
    assert assessment.branch_selection_policy.primary_candidate_id == "fov-spec-reconciliation"
    repair_preview = assessment.spec_repair_preview
    assert repair_preview is not None
    assert repair_preview.status == "tradeoff_after_repair"
    # E2-01 batch 1: the repaired-target replay now ranks 4P_F2.2_FOV74.7 first
    # (still a real GGG seed, no miss), so the preview carries more tradeoffs than
    # the pre-batch single-FOV note. NOTE: the enlarged pool includes patent seeds
    # whose runtime image height is 0.0 (case_id has no IMH token; see
    # _case_image_height_mm), which widens the image-height normalization range and
    # perturbs these secondary preview rankings. Delivered winner is unchanged.
    assert repair_preview.coverage_summary.met_count == 2
    assert repair_preview.coverage_summary.tradeoff_count == 4
    assert repair_preview.coverage_summary.miss_count == 0
    assert repair_preview.remaining_tradeoffs == [
        "F-number=tradeoff",
        "Field of view=tradeoff",
        "MTF field evidence=tradeoff",
        "Element count=tradeoff",
    ]
    repair_decision = assessment.spec_repair_decision
    assert repair_decision is not None
    assert repair_decision.status == "recommended_with_tradeoffs"
    assert repair_decision.rerun_contract is not None
    # E2-01 batch 1: the repaired-target replay ranks 4P_F2.2_FOV74.7 first, so the
    # rerun contract points there -- distinct from the delivered winner
    # (5P_F1.8_FOV74.1). Same imh-normalization perturbation noted above; delivery
    # is unchanged, only the advisory repaired-target ranking differs.
    assert (
        repair_decision.rerun_contract.expected_case_id
        == "4P_F2.2_FOV74.7_EFL2.9_IMH2.2_TTL3.90"
    )
    assert repair_decision.rerun_contract.expected_case_id != assessment.matched_case_id
    draft_candidates = {
        candidate.candidate_id: candidate for candidate in assessment.draft_candidates
    }
    assert draft_candidates["fov-alternative-review"].status == "blocked"
    assert draft_candidates["fov-alternative-review"].recommendation == "reject"
    assert draft_candidates["optimizer-proposal"].status == "warning"
    assert draft_candidates["optimizer-proposal"].recommendation == "hold"
    assert any("0-250 lp/mm" in risk for risk in draft_candidates["optimizer-proposal"].risks)


def test_spec_repair_rerun_contract_is_idempotent():
    initial = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.0,
        2.0,
        78.0,
        image_height_mm=2.3,
        n_elements=5,
        priority="balanced",
    )
    assert initial is not None
    assert initial.design_assessment is not None
    decision = initial.design_assessment.spec_repair_decision
    assert decision is not None
    contract = decision.rerun_contract
    assert contract is not None

    rerun = match_case(
        contract.target_scenario,
        contract.target_focal_length_mm,
        contract.target_f_number,
        contract.target_fov_deg,
        image_height_mm=contract.target_image_height_mm,
        n_elements=contract.target_n_elements,
        max_total_track_mm=contract.target_total_track_mm,
        priority=contract.priority,
        manufacturing_tier=contract.manufacturing_tier,
    )
    assert rerun is not None
    assert rerun.metadata.case_id == contract.expected_case_id
    assert rerun.design_assessment is not None
    assessment = rerun.design_assessment
    assert assessment.spec_repair_preview is None
    assert assessment.spec_repair_decision is None
    assert all(
        candidate.candidate_id != "fov-spec-reconciliation"
        for candidate in assessment.draft_candidates
    )
    coverage_ids = {item.requirement_id for item in assessment.requirement_coverage}
    assert "fov_spec_consistency" not in coverage_ids
    if assessment.branch_selection_policy is not None:
        assert assessment.branch_selection_policy.primary_candidate_id != "fov-spec-reconciliation"
    assert assessment.draft_acceptance_gate is not None
    assert assessment.draft_acceptance_gate.status == "blocked"
    # Post-XASPHERE-fix the repaired-target rerun keeps the same exact 5P seed,
    # which meets the aperture spec; the remaining block is the aperture-limited
    # 250 lp/mm high-frequency MTF/RMS review floor, not an aperture tradeoff.
    assert any(
        "MTF/RMS review floor" in action
        for action in assessment.draft_acceptance_gate.required_next_actions
    )
    checks = {check.check_id: check for check in assessment.draft_acceptance_gate.checks}
    assert checks["image_quality_floor"].status == "blocker"
    assert any(
        task.stage == "requirement_resolution" for task in assessment.acceptance_improvement_tasks
    )
    # E2-01 batch 1: the repaired-target rerun's exact seed reaches 0.85 field, so
    # full-field recovery now leads the optimization queue ahead of optimizer
    # stabilization.
    assert assessment.optimization_task_queue[0].task_id == "recover-full-field"
    assert assessment.optimization_task_runs[0].task_id == "recover-full-field"


def test_match_case_uses_ttl_and_design_intent():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.6,
        2.2,
        67.8,
        image_height_mm=1.8,
        n_elements=4,
        max_total_track_mm=3.4,
        priority="cost",
        manufacturing_tier="consumer",
    )
    assert c is not None
    assert c.metadata.case_id == "4P_F2.2_FOV68.0_EFL2.6_IMH1.8_TTL3.30"
    assert c.paraxial.total_track_mm <= 3.4
    assert c.design_assessment is not None
    assert c.design_assessment.delta_total_track_mm is not None
    assert c.design_assessment.delta_total_track_mm <= 0
    review = c.design_assessment.manufacturability_review
    assert review is not None
    assert review.tier == "consumer"
    assert review.status in {"pass", "warning", "blocked"}
    assert any(check.check_id == "minimum_axial_spacing" for check in review.checks)
    coverage = {item.requirement_id: item for item in c.design_assessment.requirement_coverage}
    assert coverage["manufacturing_tier"].status in {"met", "tradeoff", "miss"}
    proxy_branch = next(
        candidate
        for candidate in c.design_assessment.draft_candidates
        if candidate.candidate_id == "low-risk-candidate-review"
    )
    assert proxy_branch.source == "candidate_proxy"
    branch_policy = c.design_assessment.branch_selection_policy
    assert branch_policy is not None
    assert branch_policy.status == "resolved"
    assert branch_policy.primary_candidate_id == c.design_assessment.recommended_candidate_id
    assert "low-risk-candidate-review" in branch_policy.blocked_candidate_ids
    assert any("FOV miss" in item for item in branch_policy.rationale)
    assert c.design_assessment.recommended_candidate_id == "seed-baseline"
    assert c.design_assessment.prescription_change_set is None
    draft_candidates = {
        candidate.candidate_id: candidate for candidate in c.design_assessment.draft_candidates
    }
    assert draft_candidates["optimizer-proposal"].status == "warning"
    assert draft_candidates["optimizer-proposal"].recommendation == "hold"
    assert any("0-250 lp/mm" in risk for risk in draft_candidates["optimizer-proposal"].risks)
    assert c.design_assessment.optimization_task_queue[0].task_id == "stabilize-optimizer"
    assert c.design_assessment.optimization_task_runs[0].task_id == "stabilize-optimizer"
    assert c.design_assessment.draft_acceptance_gate is not None
    assert c.design_assessment.draft_acceptance_gate.status == "conditional"


def test_low_cost_exact_seed_baseline_can_be_ready_for_review():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.75,
        2.45,
        78.0,
        image_height_mm=2.3,
        n_elements=3,
        max_weight_g=0.05,
        priority="cost",
        manufacturing_tier="consumer",
    )
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert assessment.recommended_candidate_id == "seed-baseline"
    assert assessment.prescription_change_set is None
    gate = assessment.draft_acceptance_gate
    assert gate is not None
    assert gate.status == "ready_for_review"
    assert gate.score == 1.0
    quality = assessment.draft_quality_rubric
    assert quality is not None
    assert quality.level == "reviewable"
    assert quality.score > 0.9
    assert quality.weakest_dimension_id is not None
    assert quality.minimum_next_action is None
    assert quality.promotion_actions == []
    assert quality.promotion_target is not None
    quality_dims = {item.dimension_id: item for item in quality.dimensions}
    assert quality_dims["requirement_fit"].status == "pass"
    assert quality_dims["manufacturability"].status == "pass"
    assert quality_dims["workflow_closure"].status == "pass"
    assert quality_dims["claim_safety"].status == "pass"
    assert gate.upgrade_actions == []
    assert assessment.acceptance_improvement_tasks == []
    checks = {check.check_id: check for check in gate.checks}
    assert checks["requirement_coverage"].status == "pass"
    assert checks["manufacturability"].status == "pass"
    assert checks["optimizer_verification"].status == "pass"
    assert checks["image_quality_probe"].status == "pass"
    assert checks["task_run_evidence"].status == "pass"
    evidence_text = " ".join(check.evidence for check in checks.values())
    assert "unchanged seed-baseline hold accepted" in evidence_text
    assert "no protected optimizer change is required" in evidence_text
    assert assessment.optimization_task_queue[0].task_id == "package-seed-baseline-review"
    assert assessment.optimization_task_queue[0].status == "ready"
    assert assessment.optimization_task_queue[0].stage == "review_package"
    assert not any(
        task.task_id == "recover-image-quality-floor" for task in assessment.optimization_task_queue
    )
    assert assessment.optimization_task_runs[0].task_id == "package-seed-baseline-review"
    assert assessment.optimization_task_runs[0].status == "passed"
    assert any(
        "no optimizer proposal is required" in item
        for item in assessment.optimization_task_runs[0].evidence
    )
    reference_audit = assessment.reference_influence_audit
    assert reference_audit is not None
    assert reference_audit.status == "supported"
    assert reference_audit.selected_reference_id == assessment.matched_case_id
    assert reference_audit.data_gaps == []
    assert reference_audit.rejected_reference_ids == []
    assert "continue from" in reference_audit.safe_next_action
    sensitivity_audit = assessment.manufacturing_sensitivity_audit
    assert sensitivity_audit is not None
    assert sensitivity_audit.status == "clear"
    assert sensitivity_audit.dominant_factor_id is None
    assert sensitivity_audit.required_evidence == []
    assert "no immediate sensitivity closure" in sensitivity_audit.safe_next_action
    sensitivity_factors = {factor.factor_id: factor for factor in sensitivity_audit.factors}
    assert sensitivity_factors["tolerance_risk_proxy"].status == "pass"
    assert sensitivity_factors["process_yield_proxy"].status == "pass"
    assert sensitivity_factors["mass_proxy_budget"].status == "pass"
    clearance_checklist = assessment.manufacturing_clearance_checklist
    assert clearance_checklist is not None
    assert clearance_checklist.status == "clear"
    assert clearance_checklist.items == []
    assert clearance_checklist.review_blocking_count == 0
    assert clearance_checklist.production_blocking_count == 0
    assert "clear manufacturing proxy evidence" in clearance_checklist.next_clearance_action
    assert any("proxy evidence" in item for item in clearance_checklist.forbidden_claims)
    closeout_plan = assessment.evidence_closeout_plan
    assert closeout_plan is not None
    assert closeout_plan.status == "production_evidence_required"
    assert closeout_plan.review_blocking_count == 0
    assert closeout_plan.production_blocking_count == 1
    assert closeout_plan.items[0].item_id == "production-evidence-signoff"
    assert closeout_plan.items[0].status == "reminder"
    assert "production claims" in closeout_plan.items[0].required_evidence
    handoff = assessment.design_handoff_packet
    assert handoff is not None
    assert handoff.status == "ready_for_review"
    assert handoff.candidate_id == "seed-baseline"
    assert "unchanged selected real seed" in handoff.payload_policy
    assert any("production" in item for item in handoff.accepted_tradeoffs)
    assert any("production readiness" in item for item in handoff.forbidden_claims)
    assert handoff.next_decision == closeout_plan.safe_next_action
    constraint_ledger = assessment.design_constraint_ledger
    assert constraint_ledger is not None
    assert constraint_ledger.status == "ready_for_review"
    assert constraint_ledger.unresolved_count == 0
    assert constraint_ledger.accepted_tradeoff_count == 0
    ledger_variables = {item.variable_id: item for item in constraint_ledger.variables}
    assert ledger_variables["seed_payload"].status == "frozen"
    assert "selected real seed remains frozen" in constraint_ledger.variable_policy_summary
    coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
    assert coverage["mass_budget"].status == "met"
    assert coverage["mass_budget"].delta is not None
    assert coverage["mass_budget"].delta < 0
    assert "optical-stack proxy" in coverage["mass_budget"].actual
    mass_check = next(
        check
        for check in assessment.manufacturability_review.checks
        if check.check_id == "mass_proxy_budget"
    )
    assert mass_check.status == "pass"
    assert "proxy" in mass_check.actual
    assert any("density proxy" in item for item in mass_check.evidence)
    tolerance_check = next(
        check
        for check in assessment.manufacturability_review.checks
        if check.check_id == "tolerance_risk_proxy"
    )
    assert tolerance_check.status == "pass"
    assert "risk score" in tolerance_check.actual
    assert coverage["tolerance_risk"].status == "met"
    process_check = next(
        check
        for check in assessment.manufacturability_review.checks
        if check.check_id == "process_yield_proxy"
    )
    assert process_check.status == "pass"
    assert "process risk score" in process_check.actual
    assert coverage["process_yield_risk"].status == "met"
    best_candidate = assessment.candidate_comparison[0]
    assert best_candidate.tolerance_risk_level == "low"
    assert best_candidate.process_yield_level == "low"
    assert best_candidate.mass_proxy_g is not None
    assert best_candidate.review_proxy_notes


def test_relaxed_full_field_request_selects_exonerated_seed_and_blocks_on_mtf_floor():
    # E1-02 vignette-robust metrology exonerates the exact-parameter seed for this
    # relaxed request: its former max RMS ~1200um was a vignette-artifact tail (a
    # few edge rays sampled outside the physical clear aperture), not real
    # aberration. With the robust spot-data metric the seed reads healthy (max RMS
    # ~6.3um, 1.0 field), so routing now selects it exactly instead of steering to
    # a sibling. It stays honestly blocked on the aperture-limited high-frequency
    # (100-250 lp/mm) MTF floor -- RMS is clean.
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.8059,
        2.05,
        78.8,
        image_height_mm=3.2,
        n_elements=5,
    )
    assert c is not None
    assert c.metadata is not None
    assert c.metadata.case_id == "5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30"

    # The exonerated seed's RMS is now within the review floor; the block is the
    # high-frequency MTF, not blown-up RMS.
    exonerated = next(
        case
        for case in load_case_library()
        if case.metadata
        and case.metadata.case_id == "5P_F2.0_FOV78.8_EFL3.8_IMH3.2_TTL4.30"
    )
    exonerated_rms = max(
        v for v in exonerated.mtf.rms_spot_radius_um_by_field if math.isfinite(v)
    )
    assert exonerated_rms < 100.0

    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert assessment.recommended_candidate_id == "seed-baseline"
    assert assessment.prescription_change_set is None

    gate = assessment.draft_acceptance_gate
    assert gate is not None
    assert gate.status == "blocked"
    checks = {check.check_id: check for check in gate.checks}
    assert checks["image_quality_floor"].status == "blocker"
    assert "max RMS=6.3um" in checks["image_quality_floor"].evidence
    assert "minMTF=0.006" in checks["image_quality_floor"].evidence
    assert "multiband MTF minimum below review floor" in checks["image_quality_floor"].evidence
    assert any(action.source_check_id == "image_quality_floor" for action in gate.upgrade_actions)
    assert any("production-ready" in claim for claim in gate.forbidden_claims)
    assert any("MTF/RMS review floor" in action for action in gate.required_next_actions)

    # Floor recovery stays MTF-dominant (RMS already clean): asphere / stop.
    recovery_task = next(
        task
        for task in assessment.optimization_task_queue
        if task.task_id == "recover-image-quality-floor"
    )
    assert recovery_task.stage == "image_quality_recovery"
    assert recovery_task.candidate_id == "seed-baseline"
    assert recovery_task.variables[:2] == ["asphere coefficients", "stop position"]
    assert any(
        "dominant floor gap=mtf_100lpmm_floor_gap" in item for item in recovery_task.evidence
    )
    assert any("max_rms_floor_gap:0.000" in item for item in recovery_task.evidence)

    quality = assessment.draft_quality_rubric
    assert quality is not None
    assert quality.level == "blocked"
    quality_dims = {dimension.dimension_id: dimension for dimension in quality.dimensions}
    assert quality_dims["optical_evidence"].status == "blocker"
    assert any("minMTF=0.006" in item for item in quality_dims["optical_evidence"].evidence)
    assert any("max RMS=6.3um" in item for item in quality_dims["optical_evidence"].evidence)

    tolerance_audit = assessment.tolerance_sensitivity_audit
    assert tolerance_audit is not None
    assert tolerance_audit.status == "risk"
    assert tolerance_audit.dominant_item_id == "minimum-air-gap"

    closeout = assessment.evidence_closeout_plan
    assert closeout is not None
    assert closeout.status == "blocked"
    assert closeout.review_blocking_count == 3

    handoff = assessment.design_handoff_packet
    assert handoff is not None
    assert handoff.status == "blocked"
    assert handoff.candidate_id == "seed-baseline"

    ledger = assessment.design_constraint_ledger
    assert ledger is not None
    assert ledger.status == "blocked"

    readiness = assessment.designer_readiness_rubric
    assert readiness is not None
    assert readiness.status == "blocked"


def test_image_quality_floor_gate_still_blocks_synthetic_bad_metrics():
    # After E1-02 the whole ammo library is image-quality healthy (no natural
    # floor violation remains), so the floor-gate guard is exercised with a
    # synthetic bad snapshot: collapsed mid-frequency MTF and blown-up RMS must
    # still produce a large floor gap, while a healthy snapshot clears it. This
    # keeps the "genuinely bad data is still blocked" contract independent of the
    # real seeds.
    def _snapshot(min_mtf: float, max_rms_um: float) -> OptimizationMetricSnapshot:
        return OptimizationMetricSnapshot(
            effective_focal_length_mm=3.8,
            f_number=2.05,
            total_track_mm=4.3,
            mtf_max_field_frac=1.0,
            mtf_50lpmm_min=min_mtf,
            mtf_50lpmm_avg=min_mtf,
            mtf_100lpmm_min=min_mtf,
            mtf_100lpmm_avg=min_mtf,
            mtf_150lpmm_min=min_mtf,
            mtf_150lpmm_avg=min_mtf,
            mtf_200lpmm_min=min_mtf,
            mtf_200lpmm_avg=min_mtf,
            mtf_250lpmm_min=min_mtf,
            mtf_250lpmm_avg=min_mtf,
            mtf_multiband_min_score=min_mtf,
            mtf_field_weighted_score=min_mtf,
            max_rms_spot_radius_um=max_rms_um,
        )

    bad_gap = image_quality_floor_gap_score(_snapshot(min_mtf=0.0, max_rms_um=500.0))
    healthy_gap = image_quality_floor_gap_score(_snapshot(min_mtf=0.5, max_rms_um=5.0))
    assert bad_gap is not None and bad_gap > 1.0
    assert healthy_gap is not None and healthy_gap == pytest.approx(0.0)
    assert bad_gap > healthy_gap

@pytest.mark.parametrize(
    "match_request",
    [
        {
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 3.8,
            "fnum": 2.0,
            "fov_deg": 78.8,
            "image_height_mm": 3.3,
            "n_elements": 5,
            "priority": "balanced",
        },
    ],
)
def test_full_field_proposals_block_on_quality_floor_with_review_notes(match_request):
    c = match_case(**match_request)
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert assessment.recommended_candidate_id == "seed-baseline"
    gate = assessment.draft_acceptance_gate
    assert gate is not None
    assert gate.status == "blocked"
    assert gate.score >= 0.0
    assert gate.required_next_actions
    assert gate.upgrade_actions
    assert assessment.acceptance_improvement_tasks
    checks = {check.check_id: check for check in gate.checks}
    assert checks["image_quality_floor"].status == "blocker"
    assert "MTF/RMS review floor" in (checks["image_quality_floor"].required_action or "")
    assert any(action.source_check_id == "image_quality_floor" for action in gate.upgrade_actions)
    assert any(
        task.stage == "image_quality_recovery" for task in assessment.acceptance_improvement_tasks
    )
    assert assessment.optimization_task_queue[0].task_id == "stabilize-optimizer"
    assert assessment.optimization_task_queue[0].status == "ready"
    assert assessment.optimization_task_queue[0].stage == "optimizer_stabilization"
    assert assessment.optimization_task_runs[0].task_id == (
        assessment.optimization_task_queue[0].task_id
    )
    assert assessment.optimization_task_runs[0].status in {"diagnostic", "passed"}
    followup_tasks = [
        task
        for task in assessment.optimization_task_queue
        if task.task_id == "resolve-remediation-policy-block"
    ]
    if followup_tasks:
        followup_task = followup_tasks[0]
        assert followup_task.status == "queued"
        assert followup_task.depends_on == ["remediate-recovery-replay-gate"]
        assert any("do not resume local merit" in item for item in followup_task.evidence)
        for marker in [
            "resolution packet=remediation-policy-block",
            "resolution path=stronger-seed",
            "resolution path=alternate-variable-family",
            "resolution path=replay-evidence",
            "resume criterion=policy changes",
        ]:
            assert any(marker in item for item in followup_task.evidence)
        packet = followup_task.resolution_packet
        assert packet is not None
        assert packet.packet_id == "remediation-policy-block"
        assert packet.policy
        assert packet.policy_action
        assert {
            "stronger-seed",
            "alternate-variable-family",
            "replay-evidence",
        } <= {path.path_id for path in packet.paths}
        assert packet.resume_criteria
        followup_run = (
            next(
                run
                for run in assessment.optimization_task_runs
                if run.task_id == "resolve-remediation-policy-block"
            )
            if any(
                run.task_id == "resolve-remediation-policy-block"
                for run in assessment.optimization_task_runs
            )
            else None
        )
        if followup_run is not None:
            assert followup_run.status == "diagnostic"
            assert followup_run.next_action
            assert any(
                "resolution packet=remediation-policy-block" in item
                for item in followup_run.evidence
            )
            assert followup_run.resolution_packet is not None
            assert followup_run.resolution_packet.packet_id == packet.packet_id
        resolution_acceptance_task = next(
            (
                task
                for task in assessment.acceptance_improvement_tasks
                if task.task_id.startswith("resolve-task_run_evidence")
            ),
            None,
        )
        if resolution_acceptance_task is not None:
            assert resolution_acceptance_task.stage == "remediation_resolution"
            assert any(
                "resolution packet policy=" in item
                for item in resolution_acceptance_task.required_inputs
            )
            assert any(
                "policy changes to" in item for item in resolution_acceptance_task.exit_criteria
            )
            assert resolution_acceptance_task.evidence_probe is not None
            assert resolution_acceptance_task.evidence_probe.probe_id == (
                "remediation-resolution-packet"
            )
            assert resolution_acceptance_task.evidence_probe.missing_evidence
    checks = {check.check_id: check for check in gate.checks}
    assert checks["delivery_gate"].status == "pass"
    assert checks["optimizer_verification"].status == "pass"
    tolerance_check = next(
        check
        for check in assessment.manufacturability_review.checks
        if check.check_id == "tolerance_risk_proxy"
    )
    assert tolerance_check.status in {"pass", "warning"}
    coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
    assert coverage["tolerance_risk"].status in {"met", "tradeoff"}
    process_check = next(
        check
        for check in assessment.manufacturability_review.checks
        if check.check_id == "process_yield_proxy"
    )
    assert process_check.status in {"pass", "warning"}
    assert coverage["process_yield_risk"].status in {"met", "tradeoff"}


def test_match_case_returns_candidate_comparison_and_next_steps():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        3.0,
        2.0,
        78.0,
        image_height_mm=2.3,
        n_elements=5,
        priority="balanced",
    )
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert len(assessment.candidate_comparison) >= 3
    assert len(assessment.next_steps) >= 3
    roles = [item.role for item in assessment.candidate_comparison]
    assert len(roles) == len(set(roles))
    assert assessment.candidate_comparison[0].role == "best_match"
    assert assessment.candidate_comparison[0].case_id == c.metadata.case_id
    assert any(item.role == "thin_variant" for item in assessment.candidate_comparison)
    # Post-XASPHERE-fix the balanced default fills its comparison slots with the
    # cost / thin / performance tradeoff variants rather than filler
    # nearby_alternatives; assert diversity beyond the best match either way.
    assert any(
        item.role.startswith("nearby_alternative")
        or item.role in {"cost_variant", "performance_variant"}
        for item in assessment.candidate_comparison
    )
    assert all(item.strengths for item in assessment.candidate_comparison)
    assert all(item.tradeoffs for item in assessment.candidate_comparison)
    assert all(
        item.tolerance_risk_score is not None
        and item.tolerance_risk_level in {"low", "medium", "high"}
        for item in assessment.candidate_comparison
    )
    assert all(
        item.process_yield_score is not None
        and item.process_yield_level in {"low", "medium", "high"}
        for item in assessment.candidate_comparison
    )
    assert all(item.mass_proxy_g is not None for item in assessment.candidate_comparison)
    assert all(item.review_proxy_notes for item in assessment.candidate_comparison)
    assert c.metadata.case_id in assessment.next_steps[0]
    assert any("Candidate proxy check" in step for step in assessment.next_steps)
    assert assessment.requirement_coverage_summary is not None
    assert assessment.requirement_coverage_summary.status in {"met", "tradeoff", "blocked"}
    requirement_ids = {item.requirement_id for item in assessment.requirement_coverage}
    assert {
        "effective_focal_length",
        "f_number",
        "field_of_view",
        "mtf_field_evidence",
        "tolerance_risk",
        "process_yield_risk",
    }.issubset(requirement_ids)
    assert any(item.requirement_id == "image_height" for item in assessment.requirement_coverage)
    assert any(item.requirement_id == "element_count" for item in assessment.requirement_coverage)
    assert all(
        item.status in {"met", "tradeoff", "miss", "unscored"}
        for item in assessment.requirement_coverage
    )
    assert assessment.manufacturability_review is not None
    assert assessment.manufacturability_review.checks
    assert any(
        check.check_id == "minimum_curvature_radius"
        for check in assessment.manufacturability_review.checks
    )
    assert any(
        check.check_id == "tolerance_risk_proxy"
        for check in assessment.manufacturability_review.checks
    )
    assert any(
        check.check_id == "process_yield_proxy"
        for check in assessment.manufacturability_review.checks
    )
    assert assessment.draft_acceptance_gate is not None
    assert assessment.draft_acceptance_gate.status in {
        "ready_for_review",
        "conditional",
        "blocked",
    }
    acceptance_check_ids = {check.check_id for check in assessment.draft_acceptance_gate.checks}
    assert {
        "requirement_coverage",
        "optimizer_verification",
        "candidate_proxy_review",
        "task_run_evidence",
    }.issubset(acceptance_check_ids)
    candidate_proxy_check = next(
        check
        for check in assessment.draft_acceptance_gate.checks
        if check.check_id == "candidate_proxy_review"
    )
    if candidate_proxy_check.status == "warning":
        proxy_branch = next(
            candidate
            for candidate in assessment.draft_candidates
            if candidate.candidate_id == "low-risk-candidate-review"
        )
        assert proxy_branch.source == "candidate_proxy"
        assert proxy_branch.status == "fallback"
        assert any("review risk" in item for item in proxy_branch.evidence)
    if assessment.draft_acceptance_gate.status != "ready_for_review":
        assert assessment.draft_acceptance_gate.upgrade_actions
        first_upgrade = assessment.draft_acceptance_gate.upgrade_actions[0]
        assert first_upgrade.priority >= 1
        assert first_upgrade.source_check_id in acceptance_check_ids
        assert first_upgrade.action
        assert first_upgrade.acceptance_criteria
        assert first_upgrade.expected_effect
        assert assessment.acceptance_improvement_tasks
        first_acceptance_task = assessment.acceptance_improvement_tasks[0]
        assert first_acceptance_task.source_action_id == first_upgrade.action_id
        assert first_acceptance_task.priority == first_upgrade.priority
        assert first_acceptance_task.objective
        assert first_acceptance_task.required_inputs
        assert first_acceptance_task.validation_steps
        assert first_acceptance_task.exit_criteria
    assert assessment.readiness is not None
    assert assessment.readiness.level in {"green", "yellow", "red"}
    assert assessment.risk_register
    assert len(assessment.optimization_plan) >= 3
    assert assessment.optimization_attempt is not None
    assert assessment.optimization_attempt.status == "proposal"
    assert assessment.optimization_attempt.applied_to_payload is False
    assert assessment.optimization_attempt.variable_candidates
    assert any(
        candidate.variable == "radius"
        and candidate.status == "eligible"
        and candidate.min_value is not None
        and candidate.max_value is not None
        for candidate in assessment.optimization_attempt.variable_candidates
    )
    assert assessment.optimization_attempt.candidate_trials
    assert any(
        trial.variable == "radius" and trial.status in {"improved", "rejected", "failed"}
        for trial in assessment.optimization_attempt.candidate_trials
    )
    assert assessment.optimization_attempt.variable_changes
    assert assessment.optimization_attempt.improvement_efl_mm is not None
    assert assessment.optimization_attempt.improvement_efl_mm > 0
    assert assessment.optimization_attempt.verification is not None
    assert assessment.optimization_attempt.verification.status in {"passed", "warning"}
    assert assessment.optimization_attempt.verification.ray_trace_ok is True
    assert assessment.optimization_attempt.verification.mtf_ok is True
    assert assessment.optimization_attempt.before_metrics is not None
    assert assessment.optimization_attempt.after_metrics is not None
    assert assessment.optimization_attempt.after_metrics.mtf_max_field_frac is not None
    assert assessment.optimization_attempt.before_metrics.mtf_50lpmm_min is not None
    assert assessment.optimization_attempt.before_metrics.mtf_100lpmm_min is not None
    assert assessment.optimization_attempt.before_metrics.mtf_150lpmm_min is not None
    assert assessment.optimization_attempt.before_metrics.mtf_multiband_min_score is not None
    assert assessment.optimization_attempt.before_metrics.mtf_field_weighted_score is not None
    assert assessment.optimization_attempt.after_metrics.mtf_50lpmm_min is not None
    assert assessment.optimization_attempt.after_metrics.mtf_100lpmm_min is not None
    assert assessment.optimization_attempt.after_metrics.mtf_150lpmm_min is not None
    assert assessment.optimization_attempt.after_metrics.mtf_multiband_min_score is not None
    assert assessment.optimization_attempt.after_metrics.mtf_field_weighted_score is not None
    assert (
        assessment.optimization_attempt.after_metrics.effective_focal_length_mm
        == assessment.optimization_attempt.after_efl_mm
    )
    assert (
        assessment.optimization_attempt.after_metrics.total_track_mm
        == assessment.optimization_attempt.after_total_track_mm
    )
    assert assessment.merit_optimization_probe is not None
    assert assessment.merit_optimization_probe.status in {
        "proposal",
        "warning",
        "diagnostic_only",
    }
    assert assessment.merit_optimization_probe.before_metrics is not None
    assert assessment.merit_optimization_probe.variable_candidates
    assert any(
        candidate.variable in {"radius", "thickness"}
        and candidate.status == "eligible"
        and candidate.min_value is not None
        and candidate.max_value is not None
        for candidate in assessment.merit_optimization_probe.variable_candidates
    )
    assert any(
        candidate.variable == "asphere_coefficient"
        and candidate.status == "audited_only"
        and candidate.min_value is not None
        and candidate.max_value is not None
        and candidate.asphere_power is not None
        and candidate.audit_aperture_mm is not None
        and candidate.edge_sag_delta_um is not None
        and candidate.edge_sag_delta_um <= 5.0
        and candidate.edge_slope_delta_mrad is not None
        and candidate.edge_slope_delta_mrad <= 20.0
        and candidate.manufacturability_status == "guarded"
        for candidate in assessment.merit_optimization_probe.variable_candidates
    )
    assert assessment.merit_optimization_probe.candidate_trials
    assert any(
        trial.variable in {"radius", "thickness"} and trial.status in {"accepted", "rejected"}
        for trial in assessment.merit_optimization_probe.candidate_trials
    )
    assert any(
        trial.promotion_score is not None
        for trial in assessment.merit_optimization_probe.candidate_trials
    )
    if any(
        trial.status == "accepted" for trial in assessment.merit_optimization_probe.candidate_trials
    ):
        assert assessment.merit_optimization_probe.status == "proposal"
    elif any(
        trial.rms_improvement_um is not None and trial.rms_improvement_um >= 0
        for trial in assessment.merit_optimization_probe.candidate_trials
    ):
        assert assessment.merit_optimization_probe.rms_improvement_um is not None
        assert assessment.merit_optimization_probe.rms_improvement_um >= 0
    assert any(
        "asphere candidates:" in item for item in assessment.merit_optimization_probe.diagnostics
    )
    if assessment.merit_optimization_probe.status == "proposal":
        assert assessment.merit_optimization_probe.after_metrics is not None
        assert assessment.merit_optimization_probe.after_metrics.mtf_50lpmm_min is not None
        assert assessment.merit_optimization_probe.after_metrics.mtf_100lpmm_min is not None
        assert assessment.merit_optimization_probe.after_metrics.mtf_150lpmm_min is not None
        assert assessment.merit_optimization_probe.after_metrics.mtf_multiband_min_score is not None
        assert (
            assessment.merit_optimization_probe.after_metrics.mtf_field_weighted_score is not None
        )
        assert (
            assessment.merit_optimization_probe.after_metrics.max_rms_spot_radius_um
            < assessment.merit_optimization_probe.before_metrics.max_rms_spot_radius_um
        )
        accepted_merit_trials = [
            trial
            for trial in assessment.merit_optimization_probe.candidate_trials
            if trial.status == "accepted"
        ]
        assert accepted_merit_trials
        best_accepted_merit_trial = max(
            accepted_merit_trials,
            key=lambda trial: trial.rms_improvement_um or 0.0,
        )
        assert assessment.merit_optimization_probe.rms_improvement_um is not None
        assert best_accepted_merit_trial.rms_improvement_um is not None
        assert best_accepted_merit_trial.rms_improvement_um >= (
            assessment.merit_optimization_probe.rms_improvement_um - 1e-6
        )
        assert best_accepted_merit_trial.rms_improvement_um > 0
        assert best_accepted_merit_trial.image_quality_floor_gap_before is not None
        assert best_accepted_merit_trial.image_quality_floor_gap_after is not None
        assert best_accepted_merit_trial.image_quality_floor_gap_closure is not None
        assert best_accepted_merit_trial.image_quality_floor_gap_closure >= 0.0
        assert best_accepted_merit_trial.image_quality_floor_gap_closure == round(
            best_accepted_merit_trial.image_quality_floor_gap_before
            - best_accepted_merit_trial.image_quality_floor_gap_after,
            3,
        )
        assert best_accepted_merit_trial.mtf_band_non_regressed is True
        assert best_accepted_merit_trial.mtf_field_weighted_non_regressed is True
        assert best_accepted_merit_trial.efl_locked is True
        assert assessment.merit_optimization_probe.variable_changes
        assert assessment.merit_optimization_probe.variable_changes[0].variable in {
            "radius",
            "thickness",
            "stop_position",
            "focus_position",
        }
        assert assessment.merit_optimization_probe.verification is not None
        assert assessment.merit_optimization_probe.verification.status == "passed"
    assert assessment.draft_candidates
    assert assessment.recommended_candidate_id in {
        candidate.candidate_id for candidate in assessment.draft_candidates
    }
    assert any(
        candidate.candidate_id == "seed-baseline" for candidate in assessment.draft_candidates
    )
    assert any(
        candidate.candidate_id == "optimizer-proposal" for candidate in assessment.draft_candidates
    )
    if assessment.recommended_candidate_id == "optimizer-proposal":
        assert assessment.prescription_change_set is not None
        assert assessment.prescription_change_set.source_candidate_id == "optimizer-proposal"
        assert assessment.prescription_change_set.changes
        assert assessment.prescription_change_set.verification_checklist
    else:
        assert assessment.prescription_change_set is None
        optimizer_candidate = next(
            candidate
            for candidate in assessment.draft_candidates
            if candidate.candidate_id == "optimizer-proposal"
        )
        assert optimizer_candidate.status == "warning"
    assert len(assessment.optimization_task_queue) >= 3
    task_ids = {task.task_id for task in assessment.optimization_task_queue}
    assert {
        "apply-protected-change-set",
        "package-optimizer-proposal-review",
        "stabilize-optimizer",
    } & task_ids
    if "package-optimizer-proposal-review" in task_ids:
        review_task = next(
            task
            for task in assessment.optimization_task_queue
            if task.task_id == "package-optimizer-proposal-review"
        )
        assert review_task.stage == "review_package"
        assert review_task.status == "ready"
        assert review_task.candidate_id == assessment.recommended_candidate_id
        assert any("protected change set" in item for item in review_task.evidence)
    assert "lock-first-order" in task_ids
    assert all(
        dep in task_ids for task in assessment.optimization_task_queue for dep in task.depends_on
    )
    assert assessment.optimization_task_runs
    first_ready = next(
        task for task in assessment.optimization_task_queue if task.status == "ready"
    )
    first_run = assessment.optimization_task_runs[0]
    assert first_run.task_id == first_ready.task_id
    assert first_run.task_id in task_ids
    assert first_run.status in {"passed", "warning", "diagnostic"}
    assert first_run.next_action
    assert first_run.evidence
    if first_run.task_id == "record-spec-repair-target":
        assert any(
            metric.metric == "target_focal_length_mm"
            and metric.after == pytest.approx(2.84, abs=0.01)
            for metric in first_run.metric_updates
        )
        assert first_run.unlocked_tasks == []
        assert any("repaired-target replay" in item for item in first_run.evidence)
    elif first_run.task_id == "recover-full-field":
        assert any(metric.metric == "mtf_max_field_frac" for metric in first_run.metric_updates)
        assert any(
            metric.metric == "full_field_recovery_floor_gap_score"
            for metric in first_run.metric_updates
        )
        assert first_run.unlocked_tasks == ["record-spec-repair-target"]
        assert any("full-field" in item for item in first_run.evidence)
    else:
        assert any(metric.metric == "efl_error" for metric in first_run.metric_updates)
        if len(assessment.optimization_task_runs) < 2:
            assert first_run.status == "diagnostic"
            assert first_run.unlocked_tasks == []
            return
        second_run = assessment.optimization_task_runs[1]
        assert second_run.task_id == "lock-first-order"
        assert second_run.task_id in first_run.unlocked_tasks
        assert second_run.status in {"passed", "warning"}
        assert any(metric.metric == "f_number_delta" for metric in second_run.metric_updates)
        assert len(assessment.optimization_task_runs) >= 3
        third_run = assessment.optimization_task_runs[2]
        if "recover-image-quality-floor" in second_run.unlocked_tasks:
            assert third_run.task_id == "recover-image-quality-floor"
            assert third_run.status in {"passed", "warning", "diagnostic"}
            assert any(
                metric.metric == "image_quality_floor_gap_score"
                for metric in third_run.metric_updates
            )
            assert any(
                metric.metric == "recovery_probe_floor_gap_score"
                for metric in third_run.metric_updates
            )
            assert any("dominant floor gap=" in item for item in third_run.evidence)
            assert any("targeted recovery variables=" in item for item in third_run.evidence)
            assert any("floor recovery probe=" in item for item in third_run.evidence)
            assert any("probe ranking policy=" in item for item in third_run.evidence)
            if any("best floor-gap trial=" in item for item in third_run.evidence):
                recovery_branch = next(
                    candidate
                    for candidate in assessment.draft_candidates
                    if candidate.candidate_id == "floor-gap-recovery-candidate"
                )
                assert recovery_branch.source == "recovery_probe"
                assert recovery_branch.recommendation == "hold"
                assert "replay-floor-gap-recovery-candidate" in third_run.unlocked_tasks
                replay_run = assessment.optimization_task_runs[3]
                assert replay_run.task_id == "replay-floor-gap-recovery-candidate"
                assert replay_run.candidate_id == "floor-gap-recovery-candidate"
                accepted_floor_gap_trials = [
                    trial
                    for trial in assessment.merit_optimization_probe.candidate_trials
                    if trial.status == "accepted"
                    and trial.image_quality_floor_gap_closure is not None
                ]
                if accepted_floor_gap_trials:
                    assert any("trial status=accepted" in item for item in replay_run.evidence)
                assert any(
                    metric.metric == "recovery_candidate_floor_gap_score"
                    for metric in replay_run.metric_updates
                )
                assert replay_run.replay_gate is not None
                assert replay_run.replay_gate.gate_id == "floor-gap-recovery-replay"
                assert replay_run.replay_gate.promotion_allowed is False
                assert replay_run.replay_gate.failed_check_ids
                assert replay_run.replay_gate.recommended_variables
                assert replay_run.replay_gate.remediation_actions
                assert replay_run.next_action.startswith(
                    replay_run.replay_gate.remediation_actions[0]
                )
                assert "remediate-recovery-replay-gate" in replay_run.unlocked_tasks
                remediation_run = assessment.optimization_task_runs[4]
                assert remediation_run.task_id == "remediate-recovery-replay-gate"
                assert remediation_run.candidate_id == "floor-gap-recovery-candidate"
                assert "local-merit-tuning" in remediation_run.unlocked_tasks
                assert any(
                    metric.metric == "failed_replay_gate_checks"
                    for metric in remediation_run.metric_updates
                )
                assert any(
                    metric.metric == "remediation_probe_floor_gap_score"
                    for metric in remediation_run.metric_updates
                )
                assert any(
                    "bounded search variable priority=" in item for item in remediation_run.evidence
                )
                assert any(
                    "probe purpose=replay_gate_remediation" in item
                    for item in remediation_run.evidence
                )
                assert any("remediation policy=" in item for item in remediation_run.evidence)
                assert any(
                    "policy-selected downstream variables=" in item
                    for item in remediation_run.evidence
                )
                assert any(check.required_for_promotion for check in replay_run.replay_gate.checks)
            assert any(
                metric.metric == "mtf_multiband_floor_gap" for metric in third_run.metric_updates
            )
            assert any(
                metric.metric == "mtf_field_weighted_floor_gap"
                for metric in third_run.metric_updates
            )
            merit_index = (
                5 if any("best floor-gap trial=" in item for item in third_run.evidence) else 3
            )
            assert len(assessment.optimization_task_runs) > merit_index
            merit_run = assessment.optimization_task_runs[merit_index]
        else:
            merit_run = third_run
        assert merit_run.task_id == "local-merit-tuning"
        if any("best floor-gap trial=" in item for item in third_run.evidence):
            assert merit_run.task_id in remediation_run.unlocked_tasks
        else:
            assert merit_run.task_id in second_run.unlocked_tasks
        assert merit_run.status in {"passed", "warning"}
        assert any(metric.metric == "max_rms_spot_radius" for metric in merit_run.metric_updates)
        assert any(
            metric.metric == "mtf_multiband_min_score" for metric in merit_run.metric_updates
        )
        assert any(
            metric.metric == "mtf_field_weighted_score" for metric in merit_run.metric_updates
        )
        assert any(metric.metric == "mtf_100lpmm_min" for metric in merit_run.metric_updates)
        assert any("variable=" in item for item in merit_run.evidence)
        assert any("candidate trials=" in item for item in merit_run.evidence)
        assert any("asphere guarded count=" in item for item in merit_run.evidence)
        if merit_run.status == "warning":
            if "asphere-guarded-audit" in merit_run.unlocked_tasks:
                assert any(
                    trial.variable == "asphere_coefficient"
                    and trial.status in {"improved", "rejected", "failed"}
                    and trial.coefficient_index is not None
                    and trial.prescreen_rank is not None
                    and trial.step_fraction is not None
                    and trial.merit_before is not None
                    and trial.merit_after is not None
                    for trial in assessment.merit_optimization_probe.candidate_trials
                )
                merit_change_variable = (
                    assessment.merit_optimization_probe.variable_changes[0].variable
                    if assessment.merit_optimization_probe.variable_changes
                    else None
                )
                if merit_change_variable in {"radius", "thickness"}:
                    assert any(
                        trial.variable == "joint_asphere_merit"
                        and trial.status in {"improved", "rejected", "failed"}
                        and trial.coefficient_index is not None
                        and trial.coupled_variable in {"radius", "thickness"}
                        and trial.coupled_surface_index is not None
                        and trial.coupled_before is not None
                        and trial.coupled_after is not None
                        for trial in assessment.merit_optimization_probe.candidate_trials
                    )
                else:
                    assert merit_change_variable in {None, "stop_position", "focus_position"}
                audit_run = assessment.optimization_task_runs[
                    assessment.optimization_task_runs.index(merit_run) + 1
                ]
                assert audit_run.task_id == "asphere-guarded-audit"
                assert audit_run.status == "diagnostic"
                assert any("guarded asphere candidates=" in item for item in audit_run.evidence)
                assert any("asphere prescreen trials=" in item for item in audit_run.evidence)
                assert any("audit trials=" in item for item in audit_run.evidence)
                assert any("joint audit trials=" in item for item in audit_run.evidence)
                if merit_change_variable in {"radius", "thickness"}:
                    assert any("best joint=" in item for item in audit_run.evidence)
                assert any("best trial=" in item for item in audit_run.evidence)
                assert any("step=" in item for item in audit_run.evidence)
            else:
                assert any(
                    "merit probe source=policy-switched-remediation-probe" in item
                    or "merit probe source=second-pass-continuation-probe" in item
                    for item in merit_run.evidence
                )


def test_high_fov_candidate_comparison_exposes_performance_branch():
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.8,
        1.9,
        88.0,
        image_height_mm=2.9,
        n_elements=5,
        priority="performance",
    )
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert c.metadata.case_id == "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.29"
    # XASPHERE ingest fix pushed the 89.5 deg seed's stable field 0.8 -> 0.85
    # (corrected even-asphere sag traces one edge-field step further).
    assert c.metadata.mtf_max_field_frac == pytest.approx(0.85)
    assert c.metadata.mtf_max_field_frac < 1.0
    assert any("0.85 field" in warning for warning in assessment.warnings)
    assert any(item.role == "performance_variant" for item in assessment.candidate_comparison)
    coverage_by_id = {item.requirement_id: item for item in assessment.requirement_coverage}
    assert coverage_by_id["field_of_view"].status == "met"
    assert coverage_by_id["mtf_field_evidence"].status == "tradeoff"
    assert "full-field" in (coverage_by_id["mtf_field_evidence"].next_action or "")
    assert coverage_by_id["design_priority"].status == "tradeoff"
    scorecard = assessment.seed_selection_scorecard
    assert scorecard is not None
    assert scorecard.selected_case_id == assessment.matched_case_id
    assert scorecard.selected_rank == 1
    assert scorecard.selected_score == assessment.score
    assert scorecard.normalized_distance == assessment.normalized_distance
    assert scorecard.top_penalty_metric_id in {item.metric_id for item in scorecard.metric_scores}
    scorecard_metrics = {item.metric_id: item for item in scorecard.metric_scores}
    assert {"efl", "fov", "fnum", "imh", "nel", "quality"}.issubset(set(scorecard_metrics))
    assert scorecard_metrics["quality"].status in {"dominant", "tradeoff", "aligned"}
    assert "floor gap" in scorecard_metrics["quality"].actual
    assert "0.85 field" in scorecard_metrics["quality"].actual
    assert any("MTF field evidence" in item for item in scorecard.accepted_tradeoffs)
    assert scorecard.rejected_alternatives
    assert "full-field" in scorecard.next_action
    designer = assessment.designer_readiness_rubric
    assert designer is not None
    assert designer.status == "blocked"
    assert designer.score >= 0.44
    assert "not replacement-ready" in designer.claim_boundary
    assert any("full-field" in item for item in designer.blockers)
    designer_dims = {item.dimension_id: item for item in designer.dimensions}
    assert designer_dims["seed_evidence"].status == "blocker"
    assert designer_dims["handoff_completeness"].status == "blocker"
    assert "full-field" in designer.next_improvement_action
    intent_contract = assessment.design_intent_contract
    assert intent_contract is not None
    assert intent_contract.status == "blocked"
    assert "scenario=smartphone-wide" in intent_contract.normalized_query
    assert "FOV=88.0 deg" in intent_contract.normalized_query
    intent_hard = {item.requirement_id: item for item in intent_contract.hard_constraints}
    assert intent_hard["field_of_view"].status == "met"
    assert intent_hard["mtf_field_evidence"].status == "tradeoff"
    assert intent_hard["mtf_field_evidence"].negotiability == "explicit_review_required"
    assert any("mtf_field_evidence" in item for item in intent_contract.conflict_flags)
    assert any("selected seed" in item for item in intent_contract.inferred_assumptions)
    assert "full-field" in intent_contract.next_action
    assert any("full-field" in step for step in assessment.next_steps)
    assert assessment.optimization_attempt.verification.status == "warning"
    assert assessment.optimization_attempt.verification.mtf_max_field_frac >= 0.8
    assert assessment.merit_optimization_probe.status == "warning"
    assert assessment.merit_optimization_probe.variable_candidates
    assert assessment.merit_optimization_probe.candidate_trials
    diagnostic = assessment.full_field_recovery_diagnostic
    assert diagnostic is not None
    assert diagnostic.status == "warning"
    assert diagnostic.failure_mode == "partial_field_stability_gap"
    assert diagnostic.current_field_frac >= 0.8
    assert diagnostic.current_field_frac < 1.0
    assert diagnostic.field_gap is not None
    assert diagnostic.field_gap > 0
    assert "chief-ray aiming" in diagnostic.recommended_variable_family
    assert "stop position" in diagnostic.recommended_variable_family
    assert "radius" in diagnostic.local_variable_families_tested
    assert "thickness" in diagnostic.local_variable_families_tested
    assert "asphere_coefficient" in diagnostic.local_variable_families_tested
    assert diagnostic.rejected_trial_count > 0
    assert diagnostic.best_partial_rms_delta_um is not None
    # E1-02 vignette-robust metrology lowered this seed's baseline RMS (the edge
    # artifact tail is gone), so the recovery improvement is legitimately smaller
    # (~0.74 um) while still a real positive gain.
    assert diagnostic.best_partial_rms_delta_um > 0.5
    assert diagnostic.recovery_trials
    assert any(trial.variable_family == "stop_position" for trial in diagnostic.recovery_trials)
    assert any(trial.variable_family == "chief_ray_height" for trial in diagnostic.recovery_trials)
    assert diagnostic.best_recovery_trial is not None
    assert diagnostic.best_recovery_trial.variable_family in {"stop_position", "chief_ray_height"}
    assert diagnostic.best_recovery_trial.status == "improved"
    assert diagnostic.best_recovery_trial.mtf_max_field_frac == diagnostic.current_field_frac
    assert diagnostic.best_recovery_trial.rms_delta_um is not None
    assert diagnostic.best_recovery_trial.rms_delta_um > 0
    assert diagnostic.edge_field_scan
    edge_scan = {point.field_frac: point for point in diagnostic.edge_field_scan}
    # XASPHERE ingest fix: corrected even-asphere sag pushes the stable edge one
    # step further, so 0.85 now passes and the cliff moves 0.85 -> 0.9.
    assert edge_scan[0.8].status == "pass"
    assert edge_scan[0.85].status == "pass"
    assert edge_scan[0.9].status in {"unstable", "failed"}
    assert diagnostic.highest_scanned_stable_field_frac == pytest.approx(0.85)
    assert diagnostic.edge_field_cliff_frac == pytest.approx(0.9)
    assert any("edge-field scan=" in item for item in diagnostic.evidence)
    assert any("edge-field cliff starts at 0.9" in item for item in diagnostic.evidence)
    assert any("field gap=" in item for item in diagnostic.evidence)
    assert any("best recovery trial=" in item for item in diagnostic.evidence)
    assert any(
        trial.variable in {"radius", "thickness"}
        and trial.status == "rejected"
        and trial.verification_status == "warning"
        for trial in assessment.merit_optimization_probe.candidate_trials
    )
    assert any(
        trial.variable == "asphere_coefficient" and trial.status == "rejected"
        for trial in assessment.merit_optimization_probe.candidate_trials
    )
    assert assessment.recommended_candidate_id == "seed-baseline"
    coverage = assessment.library_coverage_diagnostic
    assert coverage is not None
    # E2-01 batch 1: real-patent >=85 deg full-field(1.0) seeds are now in the
    # library, so coverage flips gap -> covered and the seed-acquisition blocker
    # is cleared at the evidence layer. The winner is still the 0.85-field 89.5
    # deg seed (nearest params); the full-field claim stays gated below.
    assert coverage.status == "covered"
    assert coverage.high_fov_full_field_available is True
    assert coverage.nearest_full_field_case_id is not None
    assert coverage.nearest_full_field_case_id.startswith("US")
    assert coverage.nearest_full_field_fov_deg is not None
    assert coverage.nearest_high_fov_mtf_field_frac is not None
    assert coverage.nearest_high_fov_mtf_field_frac <= diagnostic.current_field_frac
    assert "high-FOV full-field seed" in coverage.recommended_strategy
    assert any("full-field high-FOV seeds=2" in item for item in coverage.evidence)
    reference_audit = assessment.reference_influence_audit
    assert reference_audit is not None
    assert reference_audit.status == "supported"
    assert reference_audit.selected_reference_id == assessment.matched_case_id
    assert assessment.matched_case_id in reference_audit.supporting_reference_ids
    sensitivity_audit = assessment.manufacturing_sensitivity_audit
    assert sensitivity_audit is not None
    assert sensitivity_audit.status == "risk"
    sensitivity_factors = {factor.factor_id: factor for factor in sensitivity_audit.factors}
    assert sensitivity_factors["guarded_asphere_coefficients"].status == "watch"
    assert sensitivity_factors["guarded_asphere_coefficients"].source == "protected_merit_probe"
    assert any("asphere" in item for item in sensitivity_audit.required_evidence)
    assert "protect tight gaps" in sensitivity_audit.safe_next_action
    clearance_checklist = assessment.manufacturing_clearance_checklist
    assert clearance_checklist is not None
    assert clearance_checklist.status == "production_evidence_required"
    assert clearance_checklist.review_blocking_count == 0
    assert clearance_checklist.production_blocking_count > 0
    assert clearance_checklist.dominant_item_id is not None
    assert (
        next(
            item
            for item in clearance_checklist.items
            if item.item_id == clearance_checklist.dominant_item_id
        ).source_factor_id
        == sensitivity_audit.dominant_factor_id
    )
    clearance_source_ids = {item.source_factor_id for item in clearance_checklist.items}
    assert "guarded_asphere_coefficients" in clearance_source_ids
    assert any(
        "asphere" in " ".join([*item.required_evidence, *item.validation_steps]).lower()
        for item in clearance_checklist.items
    )
    assert clearance_checklist.next_clearance_action
    closeout_plan = assessment.evidence_closeout_plan
    assert closeout_plan is not None
    assert closeout_plan.status == "blocked"
    assert closeout_plan.review_blocking_count > 0
    # Covered path: the review-blocking closeout item is sourced from the normal
    # draft acceptance gate (full-field recovery), not the gap-path delivery gate.
    assert any(item.source.startswith("draft_acceptance_gate") for item in closeout_plan.items)
    assert any("full-field" in item.required_evidence for item in closeout_plan.items)
    assert any(item.blocks_review for item in closeout_plan.items)
    handoff = assessment.design_handoff_packet
    assert handoff is not None
    assert handoff.status == "blocked"
    assert handoff.candidate_id == "seed-baseline"
    assert "unchanged selected real seed" in handoff.payload_policy
    assert any("full-field" in item for item in handoff.review_focus)
    assert any("production readiness" in item for item in handoff.forbidden_claims)
    assert handoff.next_decision == closeout_plan.safe_next_action
    manifest = assessment.design_traceability_manifest
    assert manifest is not None
    assert manifest.status == handoff.status
    assert manifest.source_case_id == assessment.matched_case_id
    assert manifest.source_zmx_path.endswith(manifest.source_zmx)
    assert manifest.generated_case_path.endswith(f"{assessment.matched_case_id}.json")
    assert manifest.delivered_candidate_id == handoff.candidate_id
    assert manifest.delivered_payload == "selected_real_seed"
    assert manifest.payload_policy == handoff.payload_policy
    assert manifest.surface_count == len(c.surfaces)
    assert manifest.material_count == len(c.metadata.materials)
    assert {"surface_table", "mtf_chart", "pdf_report"}.issubset(set(manifest.report_sections))
    assert any("MTF evidence reaches" in item for item in manifest.validation_evidence)
    assert any("evaluate_design_agent.py" in command for command in manifest.replay_commands)
    assert "do not edit selected seed payload in-place" in manifest.forbidden_mutations
    assert manifest.next_replay_action == handoff.next_decision
    constraint_ledger = assessment.design_constraint_ledger
    assert constraint_ledger is not None
    assert constraint_ledger.status == "blocked"
    assert constraint_ledger.unresolved_count > 0
    ledger_variables = {item.variable_id: item for item in constraint_ledger.variables}
    assert ledger_variables["seed_payload"].status == "frozen"
    # Full-field recovery is guarded (not blocked): the library now proves >=85
    # deg full-field is achievable, so the constraint is an open guard rather than
    # a hard block awaiting a missing seed.
    assert ledger_variables["full_field_recovery"].status == "guarded"
    assert any("silently mutate" in item for item in constraint_ledger.forbidden_actions)
    # E2-01 batch 1: once real full-field high-FOV evidence exists the gap-only
    # seed-acquisition scaffolding stands down -- strategy decision, seed-intake
    # audit, seed-acquisition contract, its delivery gate, and the branch policy
    # are no longer produced. The draft is gated by the normal acceptance gate.
    assert assessment.design_strategy_decision is None
    assert assessment.seed_intake_audit is None
    assert assessment.seed_acquisition_contract is None
    assert assessment.delivery_gate is None
    assert assessment.branch_selection_policy is None
    acceptance_gate = assessment.draft_acceptance_gate
    assert acceptance_gate is not None
    assert acceptance_gate.status == "blocked"
    assert acceptance_gate.candidate_id == "seed-baseline"
    assert acceptance_gate.deliverable_type == "initial optical draft"
    assert any(
        action and "full-field" in action for action in acceptance_gate.required_next_actions
    )
    assert any("production-ready" in claim for claim in acceptance_gate.forbidden_claims)
    # E2-01 batch 1: covered path also carries the explicit full-field forbidden
    # (winner is 0.85 field) -- keep the explicit expert-facing defense line.
    assert any(
        "full-field edge-performance" in claim for claim in acceptance_gate.forbidden_claims
    )
    acceptance_check_ids = {check.check_id for check in acceptance_gate.checks}
    assert {
        "requirement_coverage",
        "delivery_gate",
        "optimizer_verification",
        "image_quality_floor",
        "task_run_evidence",
    }.issubset(acceptance_check_ids)
    # Full-field recovery is still queued (winner is 0.85 field); the gap-path
    # strategy-resolution and seed-ingestion tasks are not.
    assert any(task.task_id == "recover-full-field" for task in assessment.optimization_task_queue)
    assert not any(
        task.task_id == "resolve-design-strategy" for task in assessment.optimization_task_queue
    )
    assert not any(
        task.task_id == "ingest-high-fov-full-field-seed"
        for task in assessment.acceptance_improvement_tasks
    )
    assert not any(
        run.task_id == "resolve-design-strategy" for run in assessment.optimization_task_runs
    )
    assert not any(
        task.task_id == "apply-protected-change-set" for task in assessment.optimization_task_queue
    )


def test_exact_seed_request_keeps_exact_healthy_seed():
    # World-flip from the XASPHERE ingest fix: the exact-parameter 5P F/1.8 seed
    # is image-quality healthy (max RMS ~8.1um, 1.0 field), so routing keeps it
    # instead of diverting to the slow 3P seed. Every first-order requirement is
    # met; the seed stays blocked only on the aperture-limited 250 lp/mm
    # high-frequency review floor.
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.9,
        1.8,
        74.1,
        image_height_mm=2.3,
        n_elements=5,
    )
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert c.metadata.case_id == "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15"
    assert assessment.recommended_candidate_id == "seed-baseline"
    assert assessment.prescription_change_set is None
    assert c.metadata.mtf_max_field_frac == pytest.approx(1.0)
    assert _sample_floor_gap(c) > 0.0
    assert mtf_multiband_summary(c.mtf).min_250 < 0.08
    coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
    assert coverage["f_number"].status == "met"
    assert coverage["element_count"].status == "met"
    assert coverage["field_of_view"].status == "met"
    assert coverage["mtf_field_evidence"].status == "met"
    assert assessment.draft_acceptance_gate is not None
    assert assessment.draft_acceptance_gate.status == "blocked"
    gate_checks = {check.check_id: check for check in assessment.draft_acceptance_gate.checks}
    assert gate_checks["image_quality_floor"].status == "blocker"
    draft_candidates = {item.candidate_id: item for item in assessment.draft_candidates}
    assert draft_candidates["optimizer-proposal"].status == "warning"
    assert draft_candidates["optimizer-proposal"].recommendation == "hold"
    assert any("0-250 lp/mm" in risk for risk in draft_candidates["optimizer-proposal"].risks)


def test_performance_priority_keeps_exact_aperture_seed():
    # World-flip from the XASPHERE ingest fix: the exact-aperture 5P F/1.8 seed is
    # now image-quality healthy (max RMS ~8.1um, 1.0 field), so a performance /
    # premium brief keeps it as the best match instead of diverting to a slow 3P
    # seed. F/#, element count, FOV and MTF field are all met; the only remaining
    # block is the aperture-limited 250 lp/mm high-frequency MTF/RMS review floor.
    c = match_case(
        Scenario.SMARTPHONE_WIDE,
        2.9,
        1.8,
        74.1,
        image_height_mm=2.3,
        n_elements=5,
        priority="performance",
        manufacturing_tier="premium",
    )
    assert c is not None
    assert c.design_assessment is not None
    assessment = c.design_assessment
    assert c.metadata.case_id == "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15"
    assert assessment.recommended_candidate_id == "seed-baseline"
    assert assessment.prescription_change_set is None
    assert _sample_floor_gap(c) > 0.0
    assert c.metadata.mtf_max_field_frac == pytest.approx(1.0)
    assert mtf_multiband_summary(c.mtf).min_250 < 0.08

    coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
    assert coverage["f_number"].status == "met"
    assert coverage["element_count"].status == "met"
    assert coverage["field_of_view"].status == "met"
    assert coverage["mtf_field_evidence"].status == "met"
    assert coverage["design_priority"].status == "met"

    gate = assessment.draft_acceptance_gate
    assert gate is not None
    assert gate.status == "blocked"
    gate_checks = {check.check_id: check for check in gate.checks}
    assert gate_checks["image_quality_floor"].status == "blocker"
    assert any("MTF/RMS review floor" in action for action in gate.required_next_actions)
    assert any("production-ready" in claim for claim in gate.forbidden_claims)

    # No spec repair is needed now that the seed matches the requested aperture.
    assert assessment.branch_selection_policy is None
    assert "fov-spec-reconciliation" not in {
        candidate.candidate_id for candidate in assessment.draft_candidates
    }

    scorecard = assessment.seed_selection_scorecard
    assert scorecard is not None
    assert scorecard.selected_case_id == c.metadata.case_id
    metrics = {item.metric_id: item for item in scorecard.metric_scores}
    assert metrics["quality"].label == "MTF/RMS floor evidence"
    assert (
        metrics["quality"].target == "0-250 lp/mm MTF/RMS floor gap 0.0; prefer 1.0-field evidence"
    )
    # E1-02 vignette-robust metrology slightly lowered this seed's stored floor
    # gap/min250 (0.976/0.002 -> 0.938/0.005); still aperture-floor-blocked.
    assert "floor gap 0.938" in metrics["quality"].actual
    assert "1.0 field" in metrics["quality"].actual
    assert "min250 0.005" in metrics["quality"].actual

    # The slower 3P alternative is still surfaced as a comparison variant, not
    # chosen as the deliverable.
    roles = {item.role: item for item in assessment.candidate_comparison}
    assert roles["best_match"].case_id == c.metadata.case_id
    assert any(item.case_id.startswith("3P_F2.5") for item in assessment.candidate_comparison)

    draft_candidates = {item.candidate_id: item for item in assessment.draft_candidates}
    assert draft_candidates["optimizer-proposal"].status == "warning"
    assert draft_candidates["optimizer-proposal"].recommendation == "hold"
    assert any("0-250 lp/mm" in risk for risk in draft_candidates["optimizer-proposal"].risks)
    assert "full-field-floor-clean-recovery-candidate" not in draft_candidates

    assert assessment.prescription_change_set is None
    task_by_id = {task.task_id: task for task in assessment.optimization_task_queue}
    assert "apply-protected-change-set" not in task_by_id
    assert "record-spec-repair-target" not in task_by_id
    assert task_by_id["stabilize-optimizer"].status in {"ready", "queued"}
    assert assessment.draft_quality_rubric is not None
    assert assessment.draft_quality_rubric.level == "blocked"
    assert assessment.designer_readiness_rubric is not None
    assert assessment.designer_readiness_rubric.status == "blocked"
    assert assessment.designer_readiness_rubric.blockers


def test_match_case_none_for_telephoto():
    # no real telephoto data in this phase (Phase A found zero long-focus ammo)
    assert match_case(Scenario.SMARTPHONE_TELEPHOTO, 7.0, 2.4, 30.0) is None


def test_match_endpoint_returns_real_case():
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 2.8,
            "f_number": 2.4,
            "field_of_view_deg": 78.0,
            "image_height_mm": 2.3,
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    for k in (
        "paraxial",
        "surfaces",
        "trace",
        "mtf",
        "layout_svg",
        "metadata",
        "design_assessment",
    ):
        assert k in d
    assert d["metadata"]["source_zmx"].lower().endswith(".zmx")
    assert d["metadata"]["n_imaging"] >= 3
    assert d["metadata"]["materials"]  # real datasheet material names
    assert d["design_assessment"]["matched_case_id"] == d["metadata"]["case_id"]
    assert d["design_assessment"]["target_image_height_mm"] == 2.3
    assert len(d["design_assessment"]["candidate_comparison"]) >= 3
    assert d["design_assessment"]["requirement_coverage_summary"]["status"] in {
        "met",
        "tradeoff",
        "blocked",
    }
    coverage_ids = {
        item["requirement_id"] for item in d["design_assessment"]["requirement_coverage"]
    }
    assert "effective_focal_length" in coverage_ids
    assert "f_number" in coverage_ids
    assert "field_of_view" in coverage_ids
    assert "mtf_field_evidence" in coverage_ids
    intent = d["design_assessment"]["design_intent_contract"]
    assert intent["status"] in {"ready", "review_required", "blocked"}
    assert "scenario=smartphone-wide" in intent["normalized_query"]
    assert "phone main/wide" in intent["scenario_family"]
    hard_ids = {item["requirement_id"] for item in intent["hard_constraints"]}
    assert {
        "effective_focal_length",
        "f_number",
        "field_of_view",
        "mtf_field_evidence",
    }.issubset(hard_ids)
    assert intent["safe_interpretation"]
    assert intent["next_action"]
    scorecard = d["design_assessment"]["seed_selection_scorecard"]
    assert scorecard["selected_case_id"] == d["design_assessment"]["matched_case_id"]
    assert scorecard["selected_rank"] == 1
    assert scorecard["metric_scores"]
    scorecard_metric_ids = {item["metric_id"] for item in scorecard["metric_scores"]}
    assert {"efl", "fov", "fnum"}.issubset(scorecard_metric_ids)
    assert scorecard["summary"]
    assert scorecard["next_action"]
    assert scorecard["rejected_alternatives"]
    designer = d["design_assessment"]["designer_readiness_rubric"]
    assert designer["status"] in {"draft_ready", "conditional", "blocked"}
    assert 0.0 <= designer["score"] <= 1.0
    assert designer["claim_boundary"]
    assert designer["next_improvement_action"]
    designer_dimension_ids = {item["dimension_id"] for item in designer["dimensions"]}
    assert {
        "brief_interpretation",
        "seed_evidence",
        "optical_fit",
        "optimization_evidence",
        "manufacturing_review",
        "handoff_completeness",
    }.issubset(designer_dimension_ids)
    assert d["design_assessment"]["manufacturability_review"]["status"] in {
        "pass",
        "warning",
        "blocked",
    }
    assert d["design_assessment"]["manufacturability_review"]["checks"]
    sensitivity = d["design_assessment"]["manufacturing_sensitivity_audit"]
    assert sensitivity["status"] in {"clear", "watch", "risk", "blocked"}
    assert sensitivity["factors"]
    assert sensitivity["safe_next_action"]
    assert any("not a Monte-Carlo" in item for item in sensitivity["limitations"])
    clearance = d["design_assessment"]["manufacturing_clearance_checklist"]
    assert clearance["status"] in {
        "clear",
        "production_evidence_required",
        "blocked",
    }
    assert clearance["summary"]
    assert clearance["review_blocking_count"] == sum(
        1 for item in clearance["items"] if item["blocks_review"]
    )
    assert clearance["production_blocking_count"] == sum(
        1 for item in clearance["items"] if item["blocks_production_claims"]
    )
    assert clearance["external_dependency_count"] == sum(
        1 for item in clearance["items"] if item["status"] == "external_evidence_required"
    )
    assert clearance["next_clearance_action"]
    assert clearance["forbidden_claims"]
    if sensitivity["status"] == "clear":
        assert clearance["status"] == "clear"
        assert clearance["items"] == []
    else:
        assert clearance["items"]
        first_clearance_item = clearance["items"][0]
        assert first_clearance_item["source_factor_id"]
        assert first_clearance_item["owner_role"]
        assert first_clearance_item["clearance_objective"]
        assert first_clearance_item["required_evidence"]
        assert first_clearance_item["validation_steps"]
        assert first_clearance_item["acceptance_criteria"]
        assert first_clearance_item["current_evidence"]
    closeout = d["design_assessment"]["evidence_closeout_plan"]
    assert closeout["status"] in {
        "clear",
        "production_evidence_required",
        "blocked",
    }
    assert closeout["items"]
    assert closeout["safe_next_action"]
    assert any("production readiness" in item for item in closeout["forbidden_claims"])
    handoff = d["design_assessment"]["design_handoff_packet"]
    assert handoff["status"] in {"ready_for_review", "conditional", "blocked"}
    assert handoff["candidate_id"]
    assert handoff["prescription_source"]
    assert handoff["payload_policy"]
    assert {
        "effective_focal_length",
        "f_number",
        "field_of_view",
        "image_height",
        "element_count",
        "total_track",
        "mtf_field_evidence",
    }.issubset({metric["metric_id"] for metric in handoff["headline_metrics"]})
    assert handoff["review_focus"]
    assert any("production readiness" in item for item in handoff["forbidden_claims"])
    assert handoff["next_decision"]
    ledger = d["design_assessment"]["design_constraint_ledger"]
    assert ledger["status"] in {"ready_for_review", "needs_review", "blocked"}
    assert ledger["constraints"]
    assert ledger["variables"]
    assert ledger["next_action"]
    assert "first_order_lock" in {item["variable_id"] for item in ledger["variables"]}
    assert any("silently mutate" in item for item in ledger["forbidden_actions"])
    manifest = d["design_assessment"]["design_traceability_manifest"]
    assert manifest["status"] == handoff["status"]
    assert manifest["source_case_id"] == d["design_assessment"]["matched_case_id"]
    assert manifest["source_zmx"].lower().endswith(".zmx")
    assert manifest["source_zmx_path"].endswith(manifest["source_zmx"])
    assert manifest["generated_case_path"].endswith(f"{manifest['source_case_id']}.json")
    assert manifest["delivered_candidate_id"] == handoff["candidate_id"]
    assert manifest["surface_count"] == len(d["surfaces"])
    assert manifest["material_count"] == len(d["metadata"]["materials"])
    assert {"surface_table", "mtf_chart", "pdf_report"}.issubset(set(manifest["report_sections"]))
    assert any("evaluate_design_agent.py" in item for item in manifest["replay_commands"])
    assert any(
        "do not edit selected seed payload in-place" in item
        for item in manifest["forbidden_mutations"]
    )
    draft_acceptance = d["design_assessment"]["draft_acceptance_gate"]
    assert draft_acceptance["status"] in {
        "ready_for_review",
        "conditional",
        "blocked",
    }
    assert draft_acceptance["checks"]
    assert {
        "requirement_coverage",
        "optimizer_verification",
        "task_run_evidence",
    }.issubset({check["check_id"] for check in draft_acceptance["checks"]})
    if draft_acceptance["status"] != "ready_for_review":
        assert draft_acceptance["upgrade_actions"]
        assert draft_acceptance["upgrade_actions"][0]["acceptance_criteria"]
        assert d["design_assessment"]["acceptance_improvement_tasks"]
        assert d["design_assessment"]["acceptance_improvement_tasks"][0]["exit_criteria"]
    assert len(d["design_assessment"]["next_steps"]) >= 3
    assert d["design_assessment"]["readiness"]["level"] in {"green", "yellow", "red"}
    assert d["design_assessment"]["risk_register"]
    assert len(d["design_assessment"]["optimization_plan"]) >= 3
    assert d["design_assessment"]["optimization_attempt"]["status"] in {
        "proposal",
        "diagnostic_only",
        "not_attempted",
    }
    attempt = d["design_assessment"]["optimization_attempt"]
    assert attempt["variable_candidates"]
    assert any(
        candidate["variable"] == "radius" and candidate["status"] == "eligible"
        for candidate in attempt["variable_candidates"]
    )
    assert attempt["candidate_trials"]
    if attempt["status"] == "proposal":
        assert attempt["verification"]["status"] in {"passed", "warning"}
        assert attempt["verification"]["ray_trace_ok"] is True
        assert attempt["before_metrics"]["effective_focal_length_mm"] is not None
        assert attempt["after_metrics"]["mtf_max_field_frac"] is not None
        assert attempt["after_metrics"]["mtf_50lpmm_min"] is not None
        assert attempt["after_metrics"]["mtf_100lpmm_min"] is not None
        assert attempt["after_metrics"]["mtf_150lpmm_min"] is not None
        assert attempt["after_metrics"]["mtf_multiband_min_score"] is not None
        assert attempt["after_metrics"]["mtf_field_weighted_score"] is not None
    candidate_ids = {
        candidate["candidate_id"] for candidate in d["design_assessment"]["draft_candidates"]
    }
    assert "seed-baseline" in candidate_ids
    assert d["design_assessment"]["recommended_candidate_id"] in candidate_ids
    if attempt["status"] == "proposal":
        change_set = d["design_assessment"]["prescription_change_set"]
        if d["design_assessment"]["recommended_candidate_id"] == "optimizer-proposal":
            assert change_set["source_candidate_id"] == "optimizer-proposal"
            assert change_set["verification_checklist"]
        else:
            assert change_set is None
            optimizer_candidate = next(
                candidate
                for candidate in d["design_assessment"]["draft_candidates"]
                if candidate["candidate_id"] == "optimizer-proposal"
            )
            assert optimizer_candidate["status"] == "warning"
    merit_probe = d["design_assessment"]["merit_optimization_probe"]
    assert merit_probe["status"] in {"proposal", "warning", "diagnostic_only", "not_attempted"}
    if attempt["status"] == "proposal" and attempt["verification"]["status"] == "passed":
        assert merit_probe["before_metrics"] is not None
        assert merit_probe["variable_candidates"]
        assert any(
            candidate["variable"] in {"radius", "thickness"} and candidate["status"] == "eligible"
            for candidate in merit_probe["variable_candidates"]
        )
        assert merit_probe["candidate_trials"]
        assert any(
            trial["promotion_score"] is not None for trial in merit_probe["candidate_trials"]
        )
        assert any(
            trial["image_quality_floor_gap_closure"] is not None
            for trial in merit_probe["candidate_trials"]
        )
    task_queue = d["design_assessment"]["optimization_task_queue"]
    task_ids = {task["task_id"] for task in task_queue}
    assert len(task_queue) >= 3
    assert d["design_assessment"]["recommended_candidate_id"] in {
        task["candidate_id"] for task in task_queue
    }
    assert all(dep in task_ids for task in task_queue for dep in task["depends_on"])
    task_runs = d["design_assessment"]["optimization_task_runs"]
    assert task_runs
    first_ready = next(task for task in task_queue if task["status"] == "ready")
    assert task_runs[0]["task_id"] == first_ready["task_id"]
    assert task_runs[0]["status"] in {"passed", "warning", "diagnostic"}
    assert task_runs[0]["next_action"]
    assert task_runs[0]["evidence"]
    assert all(run["task_id"] in task_ids for run in task_runs)
    assert all(unlocked in task_ids for run in task_runs for unlocked in run["unlocked_tasks"])
    if task_runs[0]["status"] == "passed":
        assert len(task_runs) >= 2
        assert task_runs[1]["task_id"] in task_runs[0]["unlocked_tasks"]
        if task_runs[1]["status"] == "passed":
            assert len(task_runs) >= 3
            assert task_runs[2]["task_id"] in task_runs[1]["unlocked_tasks"]
    # real surfaces carry finite radii (sentinel 1e9 for planes, never inf/null)
    assert all(isinstance(s["radius_mm"], int | float) for s in d["surfaces"])


def test_match_endpoint_seed_only_env_returns_lightweight_mtf_assessment(monkeypatch):
    monkeypatch.setenv("LUMIRA_MATCH_MODE", "seed_only")
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 2.8,
            "f_number": 2.4,
            "field_of_view_deg": 78.0,
            "image_height_mm": 2.3,
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["metadata"]["source_zmx"].lower().endswith(".zmx")
    assert d["metadata"]["scenario"] == "smartphone-wide"
    assessment = d["design_assessment"]
    assert assessment is not None
    assert assessment["seed_selection_scorecard"]["metric_scores"]
    assert any(
        metric["metric_id"] == "quality"
        and metric["target"] == "0-250 lp/mm MTF/RMS floor gap 0.0; prefer 1.0-field evidence"
        and "min250" in metric["actual"]
        for metric in assessment["seed_selection_scorecard"]["metric_scores"]
    )
    assert assessment["candidate_comparison"]
    assert assessment["manufacturability_review"] is not None
    assert assessment["optimization_attempt"] is None
    assert any("analysis_depth='full'" in step for step in assessment["next_steps"])
    assert d["mtf"]["freq_lp_per_mm"]


def test_match_endpoint_explicit_seed_only_returns_real_case_without_assessment(monkeypatch):
    monkeypatch.setenv("LUMIRA_MATCH_MODE", "seed_only")
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 2.8,
            "f_number": 2.4,
            "field_of_view_deg": 78.0,
            "image_height_mm": 2.3,
            "analysis_depth": "seed_only",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["metadata"]["source_zmx"].lower().endswith(".zmx")
    assert d["metadata"]["scenario"] == "smartphone-wide"
    assert d["design_assessment"] is None
    assert d["mtf"]["freq_lp_per_mm"]


def test_match_endpoint_accepts_90deg_wide_family_bound():
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 2.8,
            "f_number": 1.9,
            "field_of_view_deg": 90.0,
            "image_height_mm": 2.9,
            "n_elements": 5,
            "priority": "performance",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["metadata"]["scenario"] == "smartphone-ultrawide"
    assert d["metadata"]["fov_deg"] == 89.5


def test_match_endpoint_404_for_telephoto():
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-telephoto",
            "focal_length_mm": 7.0,
            "f_number": 2.4,
            "field_of_view_deg": 30.0,
            "image_height_mm": 3.7,
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_real_case_for_scenario"


def test_match_endpoint_400_out_of_bounds():
    # EFL 50mm is way outside the calibrated wide bounds → parameter guard 400
    r = client.post(
        "/api/optical/match",
        json={
            "scenario": "smartphone-wide",
            "focal_length_mm": 50.0,
            "f_number": 2.4,
            "field_of_view_deg": 78.0,
            "image_height_mm": 2.3,
        },
    )
    assert r.status_code == 400
