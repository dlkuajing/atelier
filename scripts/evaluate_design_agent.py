"""Fixed regression set for the Lumira Atelier phone-camera design agent.

This is intentionally small and deterministic. It does not prove optical design
quality by itself; it guards the first behavior shift we need for v2-05:
requests with different design intent should select and explain different real
seeds instead of collapsing to a 3-number nearest neighbor.

Run:
    cd lumira-backend
    uv run python scripts/evaluate_design_agent.py --fail-on-regression
    uv run python scripts/evaluate_design_agent.py --case low_cost_accepts_three_piece_seed --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.case_library import match_case  # noqa: E402
from app.core.image_quality_floor import image_quality_floor_gap_score  # noqa: E402
from app.core.lens_system import Scenario  # noqa: E402
from app.core.optical_sample import OpticalSampleData  # noqa: E402

Check = Callable[[OpticalSampleData], tuple[bool, str]]


@dataclass(frozen=True)
class EvalCase:
    name: str
    request: dict
    checks: tuple[Check, ...]


def _score_at_least(value: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        score = sample.design_assessment.score if sample.design_assessment else 0.0
        return score >= value, f"score {score:.3f} >= {value:.2f}"

    return check


def _case_contains(fragment: str) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        case_id = sample.metadata.case_id if sample.metadata else ""
        return fragment in case_id, f"case contains {fragment}"

    return check


def _scenario_is(scenario: Scenario) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        got = sample.metadata.scenario if sample.metadata else None
        return got == scenario, f"scenario {got} == {scenario}"

    return check


def _fov_at_least(value: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        fov = sample.metadata.fov_deg if sample.metadata else 0.0
        return fov >= value, f"case FOV {fov:.1f} >= {value:.1f}"

    return check


def _ttl_at_most(value: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        ttl = sample.paraxial.total_track_mm
        return ttl <= value, f"TTL {ttl:.2f} <= {value:.2f}"

    return check


def _n_pieces_at_most(value: int) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        n = sample.metadata.n_pieces if sample.metadata else 99
        return n <= value, f"pieces {n} <= {value}"

    return check


def _assessment_has_rationale(fragment: str) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        rationale = sample.design_assessment.rationale if sample.design_assessment else []
        ok = any(fragment in item for item in rationale)
        return ok, f"rationale mentions {fragment}"

    return check


def _candidate_count_at_least(value: int) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        candidates = (
            sample.design_assessment.candidate_comparison if sample.design_assessment else []
        )
        return len(candidates) >= value, f"candidate comparison count {len(candidates)} >= {value}"

    return check


def _candidate_role_present(role: str) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        candidates = (
            sample.design_assessment.candidate_comparison if sample.design_assessment else []
        )
        roles = {candidate.role for candidate in candidates}
        return role in roles, f"candidate role {role} present"

    return check


def _candidate_review_proxy_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        candidates = (
            sample.design_assessment.candidate_comparison if sample.design_assessment else []
        )
        ok = bool(candidates) and all(
            candidate.tolerance_risk_score is not None
            and candidate.tolerance_risk_level in {"low", "medium", "high"}
            and candidate.process_yield_score is not None
            and candidate.process_yield_level in {"low", "medium", "high"}
            and candidate.mass_proxy_g is not None
            and bool(candidate.review_proxy_notes)
            for candidate in candidates
        )
        return ok, f"candidate review proxies present for {len(candidates)} candidates"

    return check


def _candidate_roles_unique() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        candidates = (
            sample.design_assessment.candidate_comparison if sample.design_assessment else []
        )
        roles = [candidate.role for candidate in candidates]
        ok = len(roles) == len(set(roles))
        return ok, f"candidate roles unique: {roles}"

    return check


def _next_steps_at_least(value: int) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        steps = sample.design_assessment.next_steps if sample.design_assessment else []
        return len(steps) >= value, f"next step count {len(steps)} >= {value}"

    return check


def _next_step_mentions(fragment: str) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        steps = sample.design_assessment.next_steps if sample.design_assessment else []
        ok = any(fragment in item for item in steps)
        return ok, f"next steps mention {fragment}"

    return check


def _has_requirement_coverage() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.requirement_coverage_summary is None:
            return False, "requirement coverage missing"
        coverage = assessment.requirement_coverage
        ids = {item.requirement_id for item in coverage}
        required_ids = {
            "effective_focal_length",
            "f_number",
            "field_of_view",
            "mtf_field_evidence",
            "tolerance_risk",
            "process_yield_risk",
        }
        statuses = {item.status for item in coverage}
        counts_match = (
            assessment.requirement_coverage_summary.met_count
            + assessment.requirement_coverage_summary.tradeoff_count
            + assessment.requirement_coverage_summary.miss_count
            + assessment.requirement_coverage_summary.unscored_count
            == len(coverage)
        )
        ok = (
            required_ids.issubset(ids)
            and statuses.issubset({"met", "tradeoff", "miss", "unscored"})
            and counts_match
        )
        return ok, f"requirement coverage {assessment.requirement_coverage_summary.status}"

    return check


def _has_seed_selection_scorecard() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.seed_selection_scorecard is None:
            return False, "seed selection scorecard missing"
        scorecard = assessment.seed_selection_scorecard
        metric_ids = {item.metric_id for item in scorecard.metric_scores}
        active_weights = sum(item.weight for item in scorecard.metric_scores)
        contribution_sum = sum(item.contribution for item in scorecard.metric_scores)
        ok = (
            scorecard.selected_case_id == assessment.matched_case_id
            and scorecard.selected_rank == 1
            and abs(scorecard.selected_score - assessment.score) < 1e-9
            and abs(scorecard.normalized_distance - assessment.normalized_distance) < 1e-9
            and {"efl", "fov", "fnum"}.issubset(metric_ids)
            and 0.99 <= active_weights <= 1.01
            and contribution_sum >= 0.0
            and all(
                item.status in {"dominant", "tradeoff", "aligned"}
                for item in scorecard.metric_scores
            )
            and bool(scorecard.summary)
            and bool(scorecard.next_action)
            and bool(scorecard.rejected_alternatives)
        )
        return (
            ok,
            f"selection scorecard {scorecard.selected_case_id}: "
            f"metrics={len(scorecard.metric_scores)}, top={scorecard.top_penalty_metric_id}",
        )

    return check


def _floor_aware_performance_seed_selected() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.seed_selection_scorecard is None:
            return False, "floor-aware seed routing missing scorecard"
        scorecard = assessment.seed_selection_scorecard
        metrics = {item.metric_id: item for item in scorecard.metric_scores}
        quality = metrics.get("quality")
        comparison = {item.role: item for item in assessment.candidate_comparison}
        ok = (
            sample.metadata.case_id == "4P_F2.2_FOV74.7_EFL2.9_IMH2.2_TTL3.90"
            and assessment.recommended_candidate_id == "seed-baseline"
            and scorecard.top_penalty_metric_id == "fnum"
            and quality is not None
            and quality.label == "MTF/RMS floor evidence"
            and "floor gap 0.000" in quality.actual
            and "0.9 field" in quality.actual
            and any("Element count: 4P vs 5P" in item for item in scorecard.accepted_tradeoffs)
            and any(
                "MTF field evidence: 0.9 field" in item for item in scorecard.accepted_tradeoffs
            )
            and comparison.get("performance_variant") is not None
            and comparison["performance_variant"].case_id == "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56"
            and comparison.get("nearby_alternative_1") is not None
            and comparison["nearby_alternative_1"].case_id.startswith("5P_F2.0")
        )
        return (
            ok,
            f"floor-aware seed {sample.metadata.case_id}, top={scorecard.top_penalty_metric_id}",
        )

    return check


def _balanced_floor_aware_seed_selected() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.seed_selection_scorecard is None:
            return False, "balanced floor-aware seed routing missing scorecard"
        scorecard = assessment.seed_selection_scorecard
        metrics = {item.metric_id: item for item in scorecard.metric_scores}
        quality = metrics.get("quality")
        gate = assessment.draft_acceptance_gate
        gate_checks = {item.check_id: item for item in gate.checks} if gate else {}
        ok = (
            sample.metadata.case_id == "4P_F2.2_FOV74.7_EFL2.9_IMH2.2_TTL3.90"
            and assessment.recommended_candidate_id == "seed-baseline"
            and quality is not None
            and quality.label == "MTF/RMS floor evidence"
            and "floor gap 0.000" in quality.actual
            and "0.9 field" in quality.actual
            and any("F-number: 2.19 vs 2.00" in item for item in scorecard.accepted_tradeoffs)
            and any("Element count: 4P vs 5P" in item for item in scorecard.accepted_tradeoffs)
            and any(
                "MTF field evidence: 0.9 field" in item for item in scorecard.accepted_tradeoffs
            )
            and gate is not None
            and gate.status == "conditional"
            and gate_checks.get("image_quality_floor") is not None
            and gate_checks["image_quality_floor"].status == "pass"
        )
        return (
            ok,
            f"balanced floor-aware seed {sample.metadata.case_id}, "
            f"quality={quality.actual if quality else 'missing'}",
        )

    return check


def _full_field_recovery_replay_passes() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "full-field recovery task missing assessment"
        recover_task = next(
            (
                task
                for task in assessment.optimization_task_queue
                if task.task_id == "recover-full-field"
            ),
            None,
        )
        protected_task = next(
            (
                task
                for task in assessment.optimization_task_queue
                if task.task_id == "apply-protected-change-set"
            ),
            None,
        )
        recover_run = next(
            (
                run
                for run in assessment.optimization_task_runs
                if run.task_id == "recover-full-field"
            ),
            None,
        )
        diagnostic = assessment.full_field_recovery_diagnostic
        best_trial = diagnostic.best_recovery_trial if diagnostic is not None else None
        recovery_candidate = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "full-field-floor-clean-recovery-candidate"
            ),
            None,
        )
        change_set = assessment.prescription_change_set
        ok = (
            recover_task is not None
            and recover_task.status == "ready"
            and recover_task.candidate_id == "full-field-floor-clean-recovery-candidate"
            and any("field gap=" in item for item in recover_task.evidence)
            and protected_task is not None
            and protected_task.status == "queued"
            and protected_task.candidate_id == "full-field-floor-clean-recovery-candidate"
            and protected_task.depends_on == ["record-spec-repair-target"]
            and recover_run is not None
            and recover_run.status == "passed"
            and recover_run.candidate_id == "full-field-floor-clean-recovery-candidate"
            and recover_run.replay_gate is not None
            and recover_run.replay_gate.gate_id == "full-field-recovery-replay"
            and recover_run.replay_gate.status == "pass"
            and recover_run.replay_gate.promotion_allowed is True
            and recover_run.unlocked_tasks == ["record-spec-repair-target"]
            and any("best recovery field=" in item for item in recover_run.evidence)
            and any("best recovery floor gap=" in item for item in recover_run.evidence)
            and any("best recovery MTF/RMS=" in item for item in recover_run.evidence)
            and any("protected changes=" in item for item in recover_run.evidence)
            and any("promotion allowed=True" in item for item in recover_run.evidence)
            and best_trial is not None
            and best_trial.variable_family == "compound_field_extension"
            and best_trial.status == "recovered"
            and best_trial.mtf_max_field_frac == 1.0
            and len(best_trial.variable_changes) == 3
            and best_trial.image_quality_floor_gap_score is not None
            and best_trial.image_quality_floor_gap_score == 0.0
            and best_trial.metrics is not None
            and best_trial.metrics.mtf_multiband_min_score is not None
            and best_trial.metrics.mtf_multiband_min_score >= 0.08
            and best_trial.metrics.mtf_field_weighted_score is not None
            and best_trial.metrics.mtf_field_weighted_score >= 0.15
            and best_trial.metrics.max_rms_spot_radius_um is not None
            and best_trial.metrics.max_rms_spot_radius_um <= 100.0
            and recovery_candidate is not None
            and recovery_candidate.status == "proposed"
            and recovery_candidate.recommendation == "continue"
            and recovery_candidate.metrics is not None
            and image_quality_floor_gap_score(recovery_candidate.metrics) == 0.0
            and change_set is not None
            and change_set.source_candidate_id == "full-field-floor-clean-recovery-candidate"
            and len(change_set.changes) == 3
            and "full-field MTF evidence" in change_set.expected_effect
        )
        status = recover_run.status if recover_run is not None else "missing"
        return ok, f"recover-full-field task/run status={status}"

    return check


def _performance_recovery_branch_policy_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "performance recovery branch policy missing assessment"
        policy = assessment.branch_selection_policy
        gate = assessment.draft_acceptance_gate
        rows_by_id = {row.candidate_id: row for row in assessment.strategy_tradeoff_matrix}
        recovery_row = rows_by_id.get("full-field-floor-clean-recovery-candidate")
        seed_row = rows_by_id.get("seed-baseline")
        branch_check = (
            next(
                (check for check in gate.checks if check.check_id == "branch_selection"),
                None,
            )
            if gate is not None
            else None
        )
        ok = (
            policy is not None
            and policy.status == "strategy_resolution_required"
            and policy.primary_candidate_id == "full-field-floor-clean-recovery-candidate"
            and policy.active_candidate_id == "seed-baseline"
            and policy.current_deliverable_candidate_id == "seed-baseline"
            and policy.candidate_priority_order[:2]
            == ["full-field-floor-clean-recovery-candidate", "seed-baseline"]
            and any(
                "F-number / element-count waiver" in item or "slower-aperture tradeoff" in item
                for item in policy.promotion_requirements
            )
            and any(
                "floor-clean 5P/F1.8-ish visible-light seed" in item or "4P-vs-requested-5P" in item
                for item in policy.promotion_requirements
            )
            and any("delivered payload" in item for item in policy.forbidden_claims)
            and recovery_row is not None
            and recovery_row.priority_rank == 1
            and "primary" in recovery_row.role_tags
            and recovery_row.claim_status == "full_field_evidence_available"
            and seed_row is not None
            and {"active_payload", "current_deliverable", "recommended_payload"}.issubset(
                set(seed_row.role_tags)
            )
            and branch_check is not None
            and branch_check.status == "warning"
            and branch_check.required_action is not None
            and (
                "F-number / element-count waiver" in branch_check.required_action
                or "slower-aperture tradeoff" in branch_check.required_action
            )
            and gate is not None
            and gate.status == "conditional"
            and gate.candidate_id == "seed-baseline"
        )
        primary = policy.primary_candidate_id if policy is not None else "missing"
        active = policy.active_candidate_id if policy is not None else "missing"
        return ok, f"recovery policy primary={primary}, active={active}"

    return check


def _performance_tradeoff_policy_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "performance tradeoff policy missing assessment"
        policy = assessment.branch_selection_policy
        coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
        f_number = coverage.get("f_number")
        readiness = assessment.designer_readiness_rubric
        gate = assessment.draft_acceptance_gate
        ok = (
            policy is not None
            and policy.status == "strategy_resolution_required"
            and policy.primary_candidate_id == "full-field-floor-clean-recovery-candidate"
            and gate.status == "conditional"
            and gate.required_next_actions
            and "F-number / element-count waiver" in gate.required_next_actions[0]
            and any("claiming F/1.80 compliance" in item for item in gate.forbidden_claims)
            and f_number is not None
            and f_number.status == "tradeoff"
            and any(
                "rejected exact-aperture seed=5P_F1.8_FOV74.1" in item for item in f_number.evidence
            )
            and readiness is not None
            and readiness.status == "conditional"
            and not readiness.blockers
        )
        return (
            ok,
            (
                "performance tradeoff policy "
                f"{policy.status if policy else 'missing'}; gate={gate.status}"
            ),
        )

    return check


def _has_designer_readiness_rubric() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.designer_readiness_rubric is None:
            return False, "designer readiness rubric missing"
        rubric = assessment.designer_readiness_rubric
        dimension_ids = {dimension.dimension_id for dimension in rubric.dimensions}
        required_ids = {
            "brief_interpretation",
            "seed_evidence",
            "optical_fit",
            "optimization_evidence",
            "manufacturing_review",
            "handoff_completeness",
        }
        statuses = {dimension.status for dimension in rubric.dimensions}
        blockers_match = bool(rubric.blockers) == any(
            dimension.status == "blocker" for dimension in rubric.dimensions
        )
        ok = (
            rubric.status in {"draft_ready", "conditional", "blocked"}
            and 0.0 <= rubric.score <= 1.0
            and required_ids.issubset(dimension_ids)
            and statuses.issubset({"pass", "warning", "blocker"})
            and blockers_match
            and bool(rubric.claim_boundary)
            and bool(rubric.forbidden_claims)
            and bool(rubric.next_improvement_action)
            and bool(rubric.summary)
        )
        return (
            ok,
            f"designer readiness {rubric.status}: score={rubric.score:.3f}, "
            f"weakest={rubric.weakest_dimension_id}",
        )

    return check


def _designer_readiness_target(status: str, min_score: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.designer_readiness_rubric is None:
            return False, "designer readiness target missing"
        rubric = assessment.designer_readiness_rubric
        status_ok = rubric.status == status
        score_ok = rubric.score >= min_score
        if status == "blocked":
            boundary_ok = "not replacement-ready" in rubric.claim_boundary
            blocker_ok = bool(rubric.blockers)
        elif status == "draft_ready":
            boundary_ok = "junior first-pass draft" in rubric.claim_boundary
            blocker_ok = not rubric.blockers
        else:
            boundary_ok = "conditional draft" in rubric.claim_boundary
            blocker_ok = not rubric.blockers
        ok = status_ok and score_ok and boundary_ok and blocker_ok
        return (
            ok,
            (
                "designer readiness target "
                f"status={rubric.status}/{status}, "
                f"score={rubric.score:.3f}>={min_score:.2f}, "
                f"blockers={len(rubric.blockers)}"
            ),
        )

    return check


def _faster_aperture_counts_as_met() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        item = next(
            (
                coverage
                for coverage in assessment.requirement_coverage
                if coverage.requirement_id == "f_number"
            ),
            None,
        )
        ok = (
            item is not None
            and item.status == "met"
            and item.delta is not None
            and item.delta < 0
            and item.next_action is None
            and any("faster than or equal to target" in evidence for evidence in item.evidence)
        )
        return ok, "faster aperture is treated as met"

    return check


def _has_fov_spec_consistency_diagnostic() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        item = next(
            (
                coverage
                for coverage in assessment.requirement_coverage
                if coverage.requirement_id == "fov_spec_consistency"
            ),
            None,
        )
        has_risk = any(
            risk.risk == "request-geometry inconsistency" for risk in assessment.risk_register
        )
        has_next_step = any("EFL/image-height/FOV triad" in step for step in assessment.next_steps)
        ok = (
            item is not None
            and item.status == "tradeoff"
            and item.delta is not None
            and item.delta > 2.0
            and any("first-order FOV" in evidence for evidence in item.evidence)
            and item.next_action is not None
            and "lower EFL" in item.next_action
            and has_risk
            and has_next_step
        )
        return ok, "FOV spec consistency diagnostic"

    return check


def _has_fov_spec_reconciliation_branch() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "fov-spec-reconciliation"
            ),
            None,
        )
        ok = (
            branch is not None
            and branch.source == "requirement_branch"
            and branch.status == "proposed"
            and branch.recommendation == "continue"
            and branch.metrics is not None
            and any("default repair recommendation" in evidence for evidence in branch.evidence)
            and any("repair target EFL" in evidence for evidence in branch.evidence)
            and any("repaired-target replay uses EFL" in evidence for evidence in branch.evidence)
            and any("replay same seed" in evidence for evidence in branch.evidence)
            and any("replay coverage preview" in evidence for evidence in branch.evidence)
            and any("remaining after repaired target" in evidence for evidence in branch.evidence)
            and any("first-order FOV" in evidence for evidence in branch.evidence)
            and any("-> EFL" in evidence for evidence in branch.evidence)
            and any("-> image height" in evidence for evidence in branch.evidence)
            and any("sensor image height is the harder" in risk for risk in branch.risks)
            and any("delivered prescription is unchanged" in risk for risk in branch.risks)
            and any("original target triad" in risk for risk in branch.risks)
        )
        return ok, "FOV spec reconciliation branch"

    return check


def _mtf_first_recovery_precedes_spec_reconciliation() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.branch_selection_policy is None:
            return False, "spec reconciliation branch policy missing"
        policy = assessment.branch_selection_policy
        preview = assessment.spec_repair_preview
        decision = assessment.spec_repair_decision
        auto_closure = assessment.spec_repair_auto_closure
        rerun_contract = decision.rerun_contract if decision is not None else None
        tasks = assessment.optimization_task_queue
        runs = assessment.optimization_task_runs
        first_task = tasks[0] if tasks else None
        first_run = runs[0] if runs else None
        spec_task = next(
            (task for task in tasks if task.task_id == "record-spec-repair-target"),
            None,
        )
        ok = (
            policy.status == "strategy_resolution_required"
            and policy.active_candidate_id == assessment.recommended_candidate_id
            and policy.primary_candidate_id == "full-field-floor-clean-recovery-candidate"
            and policy.current_deliverable_candidate_id == assessment.recommended_candidate_id
            and policy.candidate_priority_order[:2]
            == ["full-field-floor-clean-recovery-candidate", "fov-spec-reconciliation"]
            and "fov-target-seed-needed" in policy.blocked_candidate_ids
            and "fov-waiver-review" in policy.fallback_candidate_ids
            and bool(policy.promotion_requirements)
            and any(
                "full-field recovery replay gate" in item for item in policy.promotion_requirements
            )
            and any("target-spec" in item for item in policy.promotion_requirements)
            and any("MTF/RMS first" in item for item in policy.rationale)
            and any("requested EFL/image-height/FOV triad" in item for item in policy.rationale)
            and any("protected recovery changes" in item for item in policy.forbidden_claims)
            and preview is not None
            and preview.source_candidate_id == "fov-spec-reconciliation"
            and preview.status == "tradeoff_after_repair"
            and preview.selected_case_id == assessment.matched_case_id
            and abs(preview.repaired_target_focal_length_mm - 2.84) < 0.02
            and preview.coverage_summary.met_count == 2
            and preview.coverage_summary.tradeoff_count == 4
            and preview.coverage_summary.miss_count == 0
            and any("Field of view=tradeoff" in item for item in preview.remaining_tradeoffs)
            and any("F-number=tradeoff" in item for item in preview.remaining_tradeoffs)
            and any("Element count=tradeoff" in item for item in preview.remaining_tradeoffs)
            and any("MTF field evidence=tradeoff" in item for item in preview.remaining_tradeoffs)
            and any(
                item.requirement_id == "effective_focal_length" and item.status == "met"
                for item in preview.coverage
            )
            and "preview_only" in preview.payload_policy
            and decision is not None
            and decision.source_candidate_id == "fov-spec-reconciliation"
            and decision.status == "recommended_with_tradeoffs"
            and decision.recommended_decision == "accept_repaired_efl_target"
            and decision.locked_constraint == "sensor_image_height_and_target_fov"
            and abs(decision.original_focal_length_mm - 3.0) < 0.01
            and decision.repaired_focal_length_mm is not None
            and abs(decision.repaired_focal_length_mm - 2.84) < 0.02
            and decision.implied_image_height_mm is not None
            and abs(decision.implied_image_height_mm - 2.43) < 0.02
            and decision.preview_coverage_summary is not None
            and decision.preview_coverage_summary.tradeoff_count == 4
            and "repaired target EFL" in decision.required_record
            and "unblocks branch-selection review" in decision.acceptance_effect
            and any("image height" in item for item in decision.alternatives)
            and any("waive FOV" in item for item in decision.alternatives)
            and any("first-order FOV" in item for item in decision.evidence)
            and any("target spec" in item for item in decision.risks)
            and auto_closure is None
            and rerun_contract is not None
            and rerun_contract.source_decision == "accept_repaired_efl_target"
            and rerun_contract.status == "ready"
            and rerun_contract.target_scenario == Scenario.SMARTPHONE_WIDE
            and abs(rerun_contract.target_focal_length_mm - 2.84) < 0.02
            and abs(rerun_contract.target_f_number - 2.0) < 0.01
            and abs(rerun_contract.target_fov_deg - 78.0) < 0.01
            and rerun_contract.expected_case_id == assessment.matched_case_id
            and rerun_contract.expected_coverage_summary is not None
            and rerun_contract.expected_coverage_summary.tradeoff_count == 4
            and "rerun match request with EFL" in rerun_contract.query_summary
            and "scenario smartphone-wide" in rerun_contract.query_summary
            and any(
                "target_scenario=smartphone-wide" in item
                for item in rerun_contract.validation_checks
            )
            and any(
                "target_focal_length_mm=2.84" in item for item in rerun_contract.validation_checks
            )
            and first_task is not None
            and first_task.task_id == "recover-full-field"
            and first_task.candidate_id == "full-field-floor-clean-recovery-candidate"
            and first_task.stage == "full_field_recovery"
            and spec_task is not None
            and spec_task.status == "queued"
            and spec_task.candidate_id == "fov-spec-reconciliation"
            and spec_task.depends_on == ["recover-full-field"]
            and any(
                "preview coverage=2 met / 4 tradeoff / 0 miss" in item
                for item in spec_task.evidence
            )
            and any(task.task_id == "recover-full-field" for task in tasks)
            and first_run is not None
            and first_run.task_id == "recover-full-field"
            and first_run.status == "passed"
            and first_run.unlocked_tasks == ["record-spec-repair-target"]
        )
        return ok, f"MTF-first policy {policy.primary_candidate_id}"

    return check


def _spec_repair_rerun_contract_is_idempotent() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.spec_repair_decision is None:
            return False, "spec repair decision missing"
        contract = assessment.spec_repair_decision.rerun_contract
        if contract is None:
            return False, "spec repair rerun contract missing"

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
        if rerun is None or rerun.design_assessment is None or rerun.metadata is None:
            return False, "rerun contract produced no assessment"

        rerun_assessment = rerun.design_assessment
        branch_policy = rerun_assessment.branch_selection_policy
        coverage_ids = {item.requirement_id for item in rerun_assessment.requirement_coverage}
        candidate_ids = {candidate.candidate_id for candidate in rerun_assessment.draft_candidates}
        first_task = (
            rerun_assessment.optimization_task_queue[0]
            if rerun_assessment.optimization_task_queue
            else None
        )
        first_run = (
            rerun_assessment.optimization_task_runs[0]
            if rerun_assessment.optimization_task_runs
            else None
        )
        rerun_gate = rerun_assessment.draft_acceptance_gate
        rerun_checks = (
            {item.check_id: item for item in rerun_gate.checks} if rerun_gate is not None else {}
        )
        ok = (
            rerun.metadata.case_id == contract.expected_case_id
            and rerun_assessment.spec_repair_preview is None
            and rerun_assessment.spec_repair_decision is None
            and "fov_spec_consistency" not in coverage_ids
            and "fov-spec-reconciliation" not in candidate_ids
            and (
                branch_policy is None
                or branch_policy.primary_candidate_id != "fov-spec-reconciliation"
            )
            and first_task is not None
            and first_task.task_id == "recover-full-field"
            and first_task.candidate_id == "full-field-floor-clean-recovery-candidate"
            and first_run is not None
            and first_run.task_id == "recover-full-field"
            and first_run.status == "passed"
            and rerun_gate is not None
            and rerun_gate.status == "conditional"
            and rerun_gate.score >= 0.70
            and rerun_checks.get("image_quality_floor") is not None
            and rerun_checks["image_quality_floor"].status == "pass"
            and any(
                task.stage == "requirement_resolution"
                for task in rerun_assessment.acceptance_improvement_tasks
            )
        )
        return ok, "rerun contract is idempotent"

    return check


def _has_fov_alternative_resolution() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "assessment or acceptance gate missing"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "fov-alternative-review"
            ),
            None,
        )
        fov_item = next(
            (
                item
                for item in assessment.requirement_coverage
                if item.requirement_id == "field_of_view"
            ),
            None,
        )
        brief = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "fov-target-seed-needed"
            ),
            None,
        )
        waiver = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "fov-waiver-review"
            ),
            None,
        )
        gate_check = next(
            (
                item
                for item in assessment.draft_acceptance_gate.checks
                if item.check_id == "fov_alternative_review"
            ),
            None,
        )
        ok = (
            branch is not None
            and branch.source == "requirement_branch"
            and branch.status == "blocked"
            and branch.recommendation == "reject"
            and any("alternative FOV delta" in evidence for evidence in branch.evidence)
            and any("F-number" in risk for risk in branch.risks)
            and fov_item is not None
            and fov_item.next_action is not None
            and "FOV alternative" in fov_item.next_action
            and "rejected" in fov_item.next_action
            and "fov-target-seed-needed" in fov_item.next_action
            and "fov-waiver-review" in fov_item.next_action
            and brief is not None
            and brief.source == "requirement_gap"
            and brief.status == "blocked"
            and any("EFL window" in evidence for evidence in brief.evidence)
            and any("F/# window" in evidence for evidence in brief.evidence)
            and any("required MTF field" in evidence for evidence in brief.evidence)
            and waiver is not None
            and waiver.source == "requirement_gap"
            and waiver.status == "conditional"
            and waiver.recommendation == "hold"
            and any("selected actual FOV" in evidence for evidence in waiver.evidence)
            and any("cannot claim" in risk for risk in waiver.risks)
            and gate_check is not None
            and gate_check.status == "pass"
            and "cannot replace" in gate_check.evidence
        )
        return ok, "FOV alternative branch is resolved and rejected when it breaks target fit"

    return check


def _has_design_intent_contract() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_intent_contract is None:
            return False, "design intent contract missing"
        contract = assessment.design_intent_contract
        hard_ids = {item.requirement_id for item in contract.hard_constraints}
        required_hard = {
            "effective_focal_length",
            "f_number",
            "field_of_view",
            "mtf_field_evidence",
        }
        hard_statuses = {item.status for item in contract.hard_constraints}
        negotiability_values = {item.negotiability for item in contract.hard_constraints}
        ok = (
            contract.status in {"ready", "review_required", "blocked"}
            and required_hard.issubset(hard_ids)
            and "scenario=" in contract.normalized_query
            and "phone main/wide" in contract.scenario_family
            and hard_statuses.issubset({"met", "tradeoff", "miss", "unscored"})
            and negotiability_values.issubset(
                {"locked", "explicit_review_required", "reviewable", "context"}
            )
            and bool(contract.inferred_assumptions)
            and bool(contract.safe_interpretation)
            and bool(contract.next_action)
        )
        return (
            ok,
            f"intent contract {contract.status}: hard={len(contract.hard_constraints)}, "
            f"soft={len(contract.soft_preferences)}",
        )

    return check


def _has_manufacturability_review() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.manufacturability_review is None:
            return False, "manufacturability review missing"
        review = assessment.manufacturability_review
        check_ids = {item.check_id for item in review.checks}
        required = {
            "element_count_complexity",
            "minimum_axial_spacing",
            "minimum_curvature_radius",
            "material_diversity",
            "tolerance_risk_proxy",
            "process_yield_proxy",
        }
        ok = (
            review.status in {"pass", "warning", "blocked"}
            and 0.0 <= review.score <= 1.0
            and required.issubset(check_ids)
            and bool(review.limitations)
        )
        return ok, f"manufacturability review {review.status}"

    return check


def _has_draft_acceptance_gate() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "draft acceptance gate missing"
        gate = assessment.draft_acceptance_gate
        check_ids = {item.check_id for item in gate.checks}
        check_statuses = {item.status for item in gate.checks}
        required_ids = {
            "requirement_coverage",
            "manufacturability",
            "delivery_gate",
            "optimizer_verification",
            "task_run_evidence",
        }
        ok = (
            gate.status in {"ready_for_review", "conditional", "blocked"}
            and 0.0 <= gate.score <= 1.0
            and required_ids.issubset(check_ids)
            and check_statuses.issubset({"pass", "warning", "blocker"})
            and all(item.label and item.evidence for item in gate.checks)
            and (
                gate.status != "ready_for_review"
                or all(item.status == "pass" for item in gate.checks)
                or bool(gate.review_notes)
            )
            and (
                gate.status == "ready_for_review"
                or (
                    bool(gate.upgrade_actions)
                    and all(
                        action.priority >= 1
                        and action.source_check_id in check_ids
                        and action.action
                        and action.acceptance_criteria
                        and action.expected_effect
                        for action in gate.upgrade_actions
                    )
                )
            )
            and bool(gate.allowed_claims)
            and bool(gate.forbidden_claims)
        )
        return ok, f"draft acceptance {gate.status}"

    return check


def _has_candidate_proxy_acceptance_evidence() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "candidate proxy acceptance evidence missing"
        proxy_check = next(
            (
                item
                for item in assessment.draft_acceptance_gate.checks
                if item.check_id == "candidate_proxy_review"
            ),
            None,
        )
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "low-risk-candidate-review"
            ),
            None,
        )
        if proxy_check is None:
            return False, "candidate proxy acceptance check missing"
        if proxy_check.status == "warning":
            ok = (
                branch is not None
                and branch.source == "candidate_proxy"
                and branch.status == "fallback"
                and bool(branch.evidence)
                and any("review risk" in item for item in branch.evidence)
            )
            return ok, "candidate proxy review branch present"
        return proxy_check.status == "pass", f"candidate proxy check {proxy_check.status}"

    return check


def _manufacturing_tier_is_scored() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "missing assessment"
        item = next(
            (
                coverage
                for coverage in assessment.requirement_coverage
                if coverage.requirement_id == "manufacturing_tier"
            ),
            None,
        )
        ok = item is not None and item.status in {"met", "tradeoff", "miss"}
        return ok, f"manufacturing tier coverage {item.status if item else 'missing'}"

    return check


def _has_readiness() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        readiness = sample.design_assessment.readiness if sample.design_assessment else None
        ok = readiness is not None and readiness.level in {"green", "yellow", "red"}
        label = f"readiness present ({readiness.level if readiness else 'missing'})"
        return ok, label

    return check


def _risk_count_at_least(value: int) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        risks = sample.design_assessment.risk_register if sample.design_assessment else []
        return len(risks) >= value, f"risk count {len(risks)} >= {value}"

    return check


def _optimization_plan_at_least(value: int) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        plan = sample.design_assessment.optimization_plan if sample.design_assessment else []
        return len(plan) >= value, f"optimization action count {len(plan)} >= {value}"

    return check


def _risk_mentions(fragment: str) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        risks = sample.design_assessment.risk_register if sample.design_assessment else []
        ok = any(fragment in risk.risk or fragment in risk.evidence for risk in risks)
        return ok, f"risk register mentions {fragment}"

    return check


def _has_optimizer_attempt() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        attempt = (
            sample.design_assessment.optimization_attempt if sample.design_assessment else None
        )
        ok = attempt is not None and attempt.status in {
            "proposal",
            "diagnostic_only",
            "not_attempted",
        }
        label = f"optimizer attempt present ({attempt.status if attempt else 'missing'})"
        return ok, label

    return check


def _optimizer_gate_is_honest() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        attempt = (
            sample.design_assessment.optimization_attempt if sample.design_assessment else None
        )
        if attempt is None:
            return False, "optimizer gate missing because attempt is missing"
        if attempt.status == "proposal":
            gate = attempt.verification
            ok = gate is not None and gate.status in {"passed", "warning"} and gate.ray_trace_ok
            label = f"proposal verification gate {gate.status if gate else 'missing'}"
            return ok, label
        has_diagnostics = bool(attempt.diagnostics or attempt.failures)
        return has_diagnostics, "diagnostic attempt carries diagnostics/failures"

    return check


def _optimizer_metrics_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        attempt = (
            sample.design_assessment.optimization_attempt if sample.design_assessment else None
        )
        if attempt is None:
            return False, "optimizer metrics missing because attempt is missing"
        if attempt.status == "proposal":
            ok = attempt.before_metrics is not None and attempt.after_metrics is not None
            if not ok:
                return False, "proposal has before/after metric snapshots"
            has_mtf_band = (
                attempt.before_metrics.mtf_50lpmm_min is not None
                and attempt.before_metrics.mtf_100lpmm_min is not None
                and attempt.before_metrics.mtf_150lpmm_min is not None
                and attempt.before_metrics.mtf_multiband_min_score is not None
                and attempt.before_metrics.mtf_field_weighted_score is not None
                and attempt.after_metrics.mtf_50lpmm_min is not None
                and attempt.after_metrics.mtf_100lpmm_min is not None
                and attempt.after_metrics.mtf_150lpmm_min is not None
                and attempt.after_metrics.mtf_multiband_min_score is not None
                and attempt.after_metrics.mtf_field_weighted_score is not None
            )
            return has_mtf_band, "proposal has multiband MTF metric snapshots"
        ok = attempt.before_metrics is not None or attempt.status == "not_attempted"
        return ok, "diagnostic attempt has before metrics or was not attempted"

    return check


def _optimizer_metrics_consistent() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        attempt = (
            sample.design_assessment.optimization_attempt if sample.design_assessment else None
        )
        if attempt is None or attempt.status != "proposal":
            return True, "optimizer metrics consistency skipped for non-proposal"
        metrics = attempt.after_metrics
        if metrics is None:
            return False, "proposal after_metrics missing"
        if (
            attempt.after_efl_mm is not None
            and metrics.effective_focal_length_mm is not None
            and abs(attempt.after_efl_mm - metrics.effective_focal_length_mm) > 1e-6
        ):
            return False, "after EFL scalar and after_metrics disagree"
        if (
            attempt.after_total_track_mm is not None
            and metrics.total_track_mm is not None
            and abs(attempt.after_total_track_mm - metrics.total_track_mm) > 1e-6
        ):
            return False, "after TTL scalar and after_metrics disagree"
        return True, "optimizer after metrics align with scalar fields"

    return check


def _has_merit_probe() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "merit probe missing because assessment is missing"
        probe = assessment.merit_optimization_probe
        if probe is None:
            return False, "merit probe missing"
        status_ok = probe.status in {
            "proposal",
            "warning",
            "diagnostic_only",
            "not_attempted",
        }
        if not status_ok:
            return False, f"unexpected merit probe status {probe.status}"
        attempt = assessment.optimization_attempt
        if (
            attempt is not None
            and attempt.status == "proposal"
            and attempt.verification is not None
            and attempt.verification.status == "passed"
        ):
            ok = probe.status in {"proposal", "warning", "diagnostic_only"} and probe.before_metrics
            if ok and probe.status in {"proposal", "warning"}:
                ok = probe.after_metrics is not None and (
                    probe.after_metrics.mtf_50lpmm_min is not None
                    and probe.after_metrics.mtf_100lpmm_min is not None
                    and probe.after_metrics.mtf_150lpmm_min is not None
                    and probe.after_metrics.mtf_multiband_min_score is not None
                    and probe.after_metrics.mtf_field_weighted_score is not None
                )
            return bool(ok), f"merit probe present for passed proposal ({probe.status})"
        return True, f"merit probe present ({probe.status})"

    return check


def _partial_field_merit_probe_has_trials() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.merit_optimization_probe is None:
            return False, "partial-field merit probe missing"
        probe = assessment.merit_optimization_probe
        has_warning_trials = any(
            trial.verification_status == "warning" and trial.status == "rejected"
            for trial in probe.candidate_trials
        )
        ok = probe.status == "warning" and has_warning_trials
        return ok, f"partial-field merit probe has rejected warning trials ({probe.status})"

    return check


def _full_field_recovery_diagnostic_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.full_field_recovery_diagnostic is None:
            return False, "full-field recovery diagnostic missing"
        diagnostic = assessment.full_field_recovery_diagnostic
        has_field_gap = (
            diagnostic.current_field_frac is not None
            and diagnostic.current_field_frac < 1.0
            and diagnostic.field_gap is not None
            and diagnostic.field_gap > 0
        )
        has_variable_evidence = diagnostic.rejected_trial_count > 0 and bool(
            diagnostic.local_variable_families_tested
        )
        has_next_family = (
            "chief-ray" in diagnostic.recommended_variable_family
            or "stop-position" in diagnostic.recommended_variable_family
            or "stop position" in diagnostic.recommended_variable_family
        )
        has_recovery_probe = (
            bool(diagnostic.recovery_trials)
            and diagnostic.best_recovery_trial is not None
            and diagnostic.best_recovery_trial.status == "improved"
            and diagnostic.best_recovery_trial.mtf_max_field_frac == diagnostic.current_field_frac
            and diagnostic.best_recovery_trial.rms_delta_um is not None
            and diagnostic.best_recovery_trial.rms_delta_um > 0.0
        )
        has_edge_scan = (
            bool(diagnostic.edge_field_scan)
            and diagnostic.highest_scanned_stable_field_frac is not None
            and diagnostic.edge_field_cliff_frac is not None
            and diagnostic.highest_scanned_stable_field_frac >= diagnostic.current_field_frac
            and diagnostic.edge_field_cliff_frac > diagnostic.highest_scanned_stable_field_frac
            and any(point.status == "pass" for point in diagnostic.edge_field_scan)
            and any(point.status in {"unstable", "failed"} for point in diagnostic.edge_field_scan)
        )
        ok = (
            diagnostic.status == "warning"
            and diagnostic.failure_mode == "partial_field_stability_gap"
            and has_field_gap
            and has_variable_evidence
            and has_next_family
            and has_recovery_probe
            and has_edge_scan
        )
        return (
            ok,
            f"full-field diagnostic {diagnostic.failure_mode} at {diagnostic.current_field_frac}",
        )

    return check


def _library_coverage_gap_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.library_coverage_diagnostic is None:
            return False, "library coverage diagnostic missing"
        diagnostic = assessment.library_coverage_diagnostic
        has_gap = (
            diagnostic.status == "gap"
            and not diagnostic.high_fov_full_field_available
            and diagnostic.full_field_fov_gap_deg is not None
            and diagnostic.full_field_fov_gap_deg > 5.0
        )
        has_strategy = "full-field high-FOV seed" in diagnostic.recommended_strategy
        ok = has_gap and has_strategy
        return (
            ok,
            "library coverage "
            f"{diagnostic.status}, full-field gap={diagnostic.full_field_fov_gap_deg}",
        )

    return check


def _has_reference_influence_audit() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.reference_influence_audit is None:
            return False, "reference influence audit missing"
        audit = assessment.reference_influence_audit
        ok = (
            audit.status in {"supported", "constrained", "conflicted"}
            and bool(audit.selected_reference_id)
            and bool(audit.supporting_reference_ids)
            and bool(audit.safe_next_action)
            and bool(audit.forbidden_claims)
        )
        return ok, f"reference audit {audit.status}: {audit.summary}"

    return check


def _has_manufacturing_sensitivity_audit() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.manufacturing_sensitivity_audit is None:
            return False, "manufacturing sensitivity audit missing"
        audit = assessment.manufacturing_sensitivity_audit
        factor_ids = {factor.factor_id for factor in audit.factors}
        required = {"minimum_axial_spacing", "tolerance_risk_proxy", "process_yield_proxy"}
        ok = (
            audit.status in {"clear", "watch", "risk", "blocked"}
            and 0.0 <= audit.confidence <= 1.0
            and required.issubset(factor_ids)
            and bool(audit.safe_next_action)
            and bool(audit.limitations)
            and any("not a Monte-Carlo" in item for item in audit.limitations)
        )
        return ok, f"manufacturing sensitivity {audit.status}: {audit.summary}"

    return check


def _has_tolerance_sensitivity_audit() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.tolerance_sensitivity_audit is None:
            return False, "tolerance sensitivity audit missing"
        audit = assessment.tolerance_sensitivity_audit
        item_ids = {item.item_id for item in audit.items}
        statuses = {item.status for item in audit.items}
        dominant = next(
            (item for item in audit.items if item.item_id == audit.dominant_item_id),
            None,
        )
        ok = (
            audit.status in {"clear", "watch", "risk", "blocked"}
            and 0.0 <= audit.confidence <= 1.0
            and {"minimum-air-gap", "field-coverage-sensitivity"}.issubset(item_ids)
            and statuses.issubset({"pass", "watch", "risk", "blocked"})
            and dominant is not None
            and dominant.sensitivity_score >= audit.items[-1].sensitivity_score
            and bool(audit.pass_criteria)
            and bool(audit.safe_next_action)
            and any("not a Monte-Carlo" in item for item in audit.limitations)
        )
        return ok, f"tolerance sensitivity {audit.status}: {audit.summary}"

    return check


def _tolerance_sensitivity_status(
    expected_status: str | set[str],
    *,
    dominant_item_id: str | None = None,
    min_items: int = 3,
) -> Check:
    expected = {expected_status} if isinstance(expected_status, str) else expected_status

    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.tolerance_sensitivity_audit is None:
            return False, "tolerance sensitivity audit missing"
        audit = assessment.tolerance_sensitivity_audit
        dominant_ok = dominant_item_id is None or audit.dominant_item_id == dominant_item_id
        return (
            audit.status in expected and dominant_ok and len(audit.items) >= min_items,
            (
                f"tolerance sensitivity {audit.status}; "
                f"dominant={audit.dominant_item_id}; items={len(audit.items)}"
            ),
        )

    return check


def _has_manufacturing_clearance_checklist() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.manufacturing_clearance_checklist is None:
            return False, "manufacturing clearance checklist missing"
        checklist = assessment.manufacturing_clearance_checklist
        items = checklist.items
        item_ids = {item.item_id for item in items}
        allowed_item_statuses = {
            "clear",
            "ready",
            "external_evidence_required",
            "blocked",
        }
        status_ok = checklist.status in {
            "clear",
            "production_evidence_required",
            "blocked",
        }
        counts_ok = (
            checklist.review_blocking_count == sum(1 for item in items if item.blocks_review)
            and checklist.production_blocking_count
            == sum(1 for item in items if item.blocks_production_claims)
            and checklist.external_dependency_count
            == sum(1 for item in items if item.status == "external_evidence_required")
        )
        dominant_ok = (not items and checklist.dominant_item_id is None) or (
            checklist.dominant_item_id in item_ids
        )
        items_ok = all(
            item.status in allowed_item_statuses
            and bool(item.owner_role)
            and bool(item.clearance_objective)
            and bool(item.required_evidence)
            and bool(item.validation_steps)
            and bool(item.acceptance_criteria)
            and bool(item.current_evidence)
            and bool(item.next_action)
            for item in items
        )
        sensitivity_status = (
            assessment.manufacturing_sensitivity_audit.status
            if assessment.manufacturing_sensitivity_audit is not None
            else None
        )
        if sensitivity_status == "clear":
            sensitivity_alignment = (
                checklist.status == "clear"
                and not items
                and checklist.review_blocking_count == 0
                and checklist.production_blocking_count == 0
            )
        else:
            sensitivity_alignment = (
                bool(items)
                and bool(checklist.next_clearance_action)
                and bool(checklist.forbidden_claims)
            )
        status_consistent = (
            (checklist.review_blocking_count > 0 and checklist.status == "blocked")
            or (
                checklist.review_blocking_count == 0
                and checklist.production_blocking_count > 0
                and checklist.status == "production_evidence_required"
            )
            or (
                checklist.review_blocking_count == 0
                and checklist.production_blocking_count == 0
                and checklist.status == "clear"
            )
        )
        ok = (
            status_ok
            and counts_ok
            and dominant_ok
            and items_ok
            and sensitivity_alignment
            and status_consistent
        )
        return (
            ok,
            (
                "manufacturing clearance "
                f"{checklist.status}: items={len(items)}, "
                f"review_blockers={checklist.review_blocking_count}, "
                f"production_blockers={checklist.production_blocking_count}"
            ),
        )

    return check


def _manufacturing_sensitivity_status(
    expected_status: str | set[str],
    *,
    required_factor_id: str | None = None,
    evidence_fragment: str | None = None,
) -> Check:
    expected = {expected_status} if isinstance(expected_status, str) else expected_status

    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.manufacturing_sensitivity_audit is None:
            return False, "manufacturing sensitivity audit missing"
        audit = assessment.manufacturing_sensitivity_audit
        factor_ids = {factor.factor_id for factor in audit.factors}
        status_ok = audit.status in expected
        factor_ok = required_factor_id is None or required_factor_id in factor_ids
        joined_required = " ".join(audit.required_evidence)
        evidence_ok = evidence_fragment is None or evidence_fragment in joined_required
        return (
            status_ok and factor_ok and evidence_ok,
            f"manufacturing sensitivity {audit.status}; factors={len(audit.factors)}",
        )

    return check


def _has_evidence_closeout_plan() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.evidence_closeout_plan is None:
            return False, "evidence closeout plan missing"
        plan = assessment.evidence_closeout_plan
        ok = (
            plan.status in {"clear", "production_evidence_required", "blocked"}
            and bool(plan.items)
            and bool(plan.safe_next_action)
            and plan.production_blocking_count >= 0
            and plan.review_blocking_count >= 0
            and any(item.acceptance_criteria for item in plan.items)
            and any(item.claim_unblocked for item in plan.items)
            and any(
                "production readiness" in item or "production-ready" in item
                for item in plan.forbidden_claims
            )
        )
        return ok, f"evidence closeout {plan.status}: {plan.summary}"

    return check


def _evidence_closeout_status(
    expected_status: str | set[str],
    *,
    source_fragment: str | None = None,
    evidence_fragment: str | None = None,
    blocks_review: bool | None = None,
) -> Check:
    expected = {expected_status} if isinstance(expected_status, str) else expected_status

    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.evidence_closeout_plan is None:
            return False, "evidence closeout plan missing"
        plan = assessment.evidence_closeout_plan
        status_ok = plan.status in expected
        source_ok = (
            True
            if source_fragment is None
            else any(source_fragment in item.source for item in plan.items)
        )
        evidence_ok = (
            True
            if evidence_fragment is None
            else any(evidence_fragment in item.required_evidence for item in plan.items)
        )
        review_ok = (
            True
            if blocks_review is None
            else any(item.blocks_review is blocks_review for item in plan.items)
        )
        return (
            status_ok and source_ok and evidence_ok and review_ok,
            f"evidence closeout {plan.status}; items={len(plan.items)}",
        )

    return check


def _has_design_handoff_packet() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_handoff_packet is None:
            return False, "design handoff packet missing"
        handoff = assessment.design_handoff_packet
        metric_ids = {metric.metric_id for metric in handoff.headline_metrics}
        required_metrics = {
            "effective_focal_length",
            "f_number",
            "field_of_view",
            "image_height",
            "element_count",
            "total_track",
            "mtf_field_evidence",
        }
        ok = (
            handoff.status in {"ready_for_review", "conditional", "blocked"}
            and bool(handoff.candidate_id)
            and bool(handoff.prescription_source)
            and bool(handoff.payload_policy)
            and required_metrics.issubset(metric_ids)
            and bool(handoff.review_focus)
            and bool(handoff.forbidden_claims)
            and "production readiness" in " ".join(handoff.forbidden_claims)
        )
        return ok, f"design handoff {handoff.status}: {handoff.summary}"

    return check


def _design_handoff_status(
    expected_status: str,
    *,
    candidate_id: str | None = None,
    payload_fragment: str | None = None,
) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_handoff_packet is None:
            return False, "design handoff packet missing"
        handoff = assessment.design_handoff_packet
        status_ok = handoff.status == expected_status
        candidate_ok = candidate_id is None or handoff.candidate_id == candidate_id
        payload_ok = payload_fragment is None or payload_fragment in handoff.payload_policy
        return (
            status_ok and candidate_ok and payload_ok,
            f"design handoff {handoff.status}/{handoff.candidate_id}",
        )

    return check


def _has_design_traceability_manifest() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_traceability_manifest is None:
            return False, "design traceability manifest missing"
        manifest = assessment.design_traceability_manifest
        report_sections = set(manifest.report_sections)
        validation_blob = " ".join(manifest.validation_evidence)
        replay_blob = " ".join(manifest.replay_commands)
        mutation_blob = " ".join(manifest.forbidden_mutations)
        required_sections = {"surface_table", "mtf_chart", "pdf_report"}
        ok = (
            manifest.status in {"ready_for_review", "conditional", "blocked"}
            and manifest.source_case_id == assessment.matched_case_id
            and manifest.source_zmx.lower().endswith(".zmx")
            and manifest.source_zmx_path.endswith(manifest.source_zmx)
            and "app/data/optical_cases" in manifest.generated_case_path
            and manifest.source_case_id in manifest.generated_case_path
            and bool(manifest.delivered_candidate_id)
            and bool(manifest.delivered_payload)
            and bool(manifest.payload_policy)
            and manifest.surface_count > 0
            and manifest.material_count >= 0
            and required_sections.issubset(report_sections)
            and "MTF evidence reaches" in validation_blob
            and "evaluate_design_agent.py" in replay_blob
            and "do not edit selected seed payload in-place" in mutation_blob
            and bool(manifest.next_replay_action)
        )
        return (
            ok,
            f"traceability {manifest.status}: {manifest.source_case_id} -> "
            f"{manifest.delivered_candidate_id}",
        )

    return check


def _has_design_constraint_ledger() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_constraint_ledger is None:
            return False, "design constraint ledger missing"
        ledger = assessment.design_constraint_ledger
        constraint_ids = {item.requirement_id for item in ledger.constraints}
        variable_ids = {item.variable_id for item in ledger.variables}
        required_constraints = {
            "effective_focal_length",
            "f_number",
            "field_of_view",
            "mtf_field_evidence",
        }
        ok = (
            ledger.status in {"ready_for_review", "needs_review", "blocked"}
            and required_constraints.issubset(constraint_ids)
            and ledger.locked_count >= 0
            and ledger.accepted_tradeoff_count >= 0
            and ledger.unresolved_count >= 0
            and "first_order_lock" in variable_ids
            and bool(ledger.variable_policy_summary)
            and bool(ledger.next_action)
            and any("silently mutate" in item for item in ledger.forbidden_actions)
        )
        return ok, f"constraint ledger {ledger.status}: {ledger.summary}"

    return check


def _constraint_ledger_status(
    expected_status: str,
    *,
    variable_id: str | None = None,
    variable_status: str | None = None,
    min_accepted_tradeoffs: int | None = None,
) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_constraint_ledger is None:
            return False, "design constraint ledger missing"
        ledger = assessment.design_constraint_ledger
        variable_ok = True
        if variable_id is not None:
            variable = next(
                (item for item in ledger.variables if item.variable_id == variable_id),
                None,
            )
            variable_ok = variable is not None and (
                variable_status is None or variable.status == variable_status
            )
        tradeoff_ok = (
            True
            if min_accepted_tradeoffs is None
            else ledger.accepted_tradeoff_count >= min_accepted_tradeoffs
        )
        return (
            ledger.status == expected_status and variable_ok and tradeoff_ok,
            f"constraint ledger {ledger.status}, variables={len(ledger.variables)}",
        )

    return check


def _reference_influence_status(
    expected_status: str,
    *,
    data_gap_fragment: str | None = None,
) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.reference_influence_audit is None:
            return False, "reference influence audit missing"
        audit = assessment.reference_influence_audit
        status_ok = audit.status == expected_status
        gap_ok = (
            True
            if data_gap_fragment is None
            else any(data_gap_fragment in gap for gap in audit.data_gaps)
        )
        return (
            status_ok and gap_ok,
            f"reference audit {audit.status}; gaps={len(audit.data_gaps)}",
        )

    return check


def _design_strategy_decision_selects_seed_acquisition() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.design_strategy_decision is None:
            return False, "design strategy decision missing"
        decision = assessment.design_strategy_decision
        has_primary_strategy = decision.selected_strategy == "add_full_field_high_fov_seed"
        has_fallbacks = {
            "relax_fov_to_full_field_seed",
            "partial_field_high_fov_draft",
        }.issubset(set(decision.fallback_strategies))
        no_stale_sibling = "stable_partial_field_sibling_seed" not in decision.fallback_strategies
        has_evidence_contract = any(
            ">=85 deg" in item and "1.0 field" in item for item in decision.required_evidence
        )
        options = {option.option_id: option for option in decision.options}
        has_options = {
            "add_full_field_high_fov_seed",
            "relax_fov_to_full_field_seed",
            "partial_field_high_fov_draft",
        }.issubset(options)
        relaxed = options.get("relax_fov_to_full_field_seed")
        partial = options.get("partial_field_high_fov_draft")
        relaxed_full_field = (
            relaxed is not None
            and relaxed.candidate_id is not None
            and relaxed.mtf_max_field_frac == 1.0
        )
        partial_field = (
            partial is not None
            and partial.candidate_id == "5P_F1.9_FOV89.5_EFL2.8_IMH2.9_TTL4.33"
            and partial.evidence_status == "partial_field_only"
            and partial.mtf_max_field_frac == 0.85
        )
        brief = decision.seed_acquisition_brief
        brief_ok = (
            brief is not None
            and brief.priority == "required_for_full_field_claim"
            and brief.minimum_fov_deg >= 85.0
            and brief.required_mtf_field_frac == 1.0
            and len(brief.efl_window_mm) == 2
            and brief.efl_window_mm[0] < brief.target_efl_mm < brief.efl_window_mm[1]
            and len(brief.f_number_window) == 2
            and brief.f_number_window[0] < brief.target_f_number < brief.f_number_window[1]
            and any("visible-light" in item for item in brief.validation_requirements)
            and any("MTF max stable field below 1.0" in item for item in brief.rejection_filters)
        )
        gate = assessment.delivery_gate
        gate_ok = (
            gate is not None
            and gate.status == "conditional_partial_field"
            and "partial-field" in gate.deliverable_type
            and any("full-field edge-performance" in item for item in gate.forbidden_claims)
            and any("MTF evidence" in item for item in gate.allowed_claims)
            and any("1.0 field" in item for item in gate.promotion_requirements)
        )
        ok = (
            has_primary_strategy
            and has_fallbacks
            and no_stale_sibling
            and has_evidence_contract
            and has_options
            and relaxed_full_field
            and partial_field
            and brief_ok
            and gate_ok
        )
        return ok, f"design strategy decision {decision.selected_strategy}"

    return check


def _has_high_fov_seed_acquisition_branch() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "seed-acquisition branch missing because assessment is missing"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "high-fov-full-field-seed-needed"
            ),
            None,
        )
        if branch is None:
            return False, "high-FOV full-field seed acquisition branch present"
        evidence_ok = (
            any("add_full_field_high_fov_seed" in item for item in branch.evidence)
            and any("required FOV >= 85.0" in item for item in branch.evidence)
            and any("required MTF field 1.0" in item for item in branch.evidence)
        )
        risk_ok = any("no current visible-light" in item for item in branch.risks)
        ok = (
            branch.source == "strategy_option"
            and branch.strategy_option_id == "add_full_field_high_fov_seed"
            and branch.status == "blocked"
            and branch.recommendation == "hold"
            and branch.metrics is None
            and evidence_ok
            and risk_ok
        )
        return ok, f"high-FOV seed acquisition branch {branch.status}"

    return check


def _has_relaxed_fov_full_field_branch() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "relaxed-FOV branch missing because assessment is missing"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "relaxed-fov-full-field"
            ),
            None,
        )
        if branch is None:
            return False, "relaxed-FOV full-field draft branch present"
        metrics = branch.metrics
        has_full_field_metrics = (
            metrics is not None
            and metrics.mtf_max_field_frac == 1.0
            and metrics.effective_focal_length_mm is not None
            and metrics.mtf_50lpmm_min is not None
            and metrics.mtf_field_weighted_score is not None
        )
        evidence_ok = any("full-field real case" in item for item in branch.evidence)
        risk_ok = any("FOV" in item and "reduced" in item for item in branch.risks)
        ok = (
            branch.source == "strategy_option"
            and branch.strategy_option_id == "relax_fov_to_full_field_seed"
            and branch.status == "fallback"
            and branch.recommendation == "continue"
            and has_full_field_metrics
            and evidence_ok
            and risk_ok
        )
        return ok, f"relaxed-FOV full-field branch {branch.status}"

    return check


def _has_near_threshold_partial_field_branch() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "near-threshold branch missing because assessment is missing"
        option = next(
            (
                item
                for item in (
                    assessment.design_strategy_decision.options
                    if assessment.design_strategy_decision
                    else []
                )
                if item.option_id == "near_threshold_partial_field_seed"
            ),
            None,
        )
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "near-threshold-partial-field"
            ),
            None,
        )
        if option is None or branch is None:
            return False, "near-threshold partial-field strategy option and branch present"
        metrics = branch.metrics
        has_metrics = (
            metrics is not None
            and metrics.mtf_max_field_frac is not None
            and 0.8 < metrics.mtf_max_field_frac < 1.0
            and metrics.effective_focal_length_mm is not None
            and metrics.mtf_50lpmm_min is not None
        )
        evidence_ok = (
            any("near-threshold real case" in item for item in branch.evidence)
            and any("0.9 field" in item for item in branch.evidence)
            and any("0.8" in item and "0.9" in item for item in branch.evidence)
        )
        risk_ok = any("requested FOV is reduced" in item for item in branch.risks) and any(
            "full-field edge-performance" in item for item in branch.risks
        )
        ok = (
            option.candidate_id == "4P_F2.0_FOV84.1_EFL2.5_IMH2.3_TTL3.34"
            and option.evidence_status == "partial_field_only"
            and option.mtf_max_field_frac == 0.9
            and branch.source == "strategy_option"
            and branch.strategy_option_id == "near_threshold_partial_field_seed"
            and branch.status == "fallback"
            and branch.recommendation == "hold"
            and has_metrics
            and evidence_ok
            and risk_ok
        )
        return ok, f"near-threshold partial branch {branch.status}"

    return check


def _selected_partial_branch_uses_085_seed() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "partial-field branch missing because assessment is missing"
        option = next(
            (
                item
                for item in (
                    assessment.design_strategy_decision.options
                    if assessment.design_strategy_decision
                    else []
                )
                if item.option_id == "stable_partial_field_sibling_seed"
            ),
            None,
        )
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "partial-field-high-fov-draft"
            ),
            None,
        )
        if option is not None or branch is None:
            return False, "0.85 partial-field seed is the selected draft branch"
        metrics = branch.metrics
        has_metrics = (
            metrics is not None
            and metrics.mtf_max_field_frac == 0.85
            and metrics.effective_focal_length_mm is not None
            and metrics.mtf_50lpmm_min is not None
        )
        evidence_ok = any("partial-field real case" in item for item in branch.evidence) and any(
            "0.85 field" in item for item in branch.evidence
        )
        risk_ok = any("full-field edge-performance" in item for item in branch.risks) and any(
            "unproven" in item for item in branch.risks
        )
        ok = (
            branch.source == "strategy_option"
            and branch.strategy_option_id == "partial_field_high_fov_draft"
            and branch.status == "conditional"
            and branch.recommendation == "hold"
            and has_metrics
            and evidence_ok
            and risk_ok
        )
        return ok, f"selected partial branch {branch.status}"

    return check


def _stable_sibling_review_is_not_queued() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "stable sibling queue audit missing because assessment is missing"
        task = next(
            (
                item
                for item in assessment.optimization_task_queue
                if item.task_id == "review-stable-sibling-branch"
            ),
            None,
        )
        run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "review-stable-sibling-branch"
            ),
            None,
        )
        resolve_run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "resolve-design-strategy"
            ),
            None,
        )
        if resolve_run is None:
            return False, "strategy resolution run present"
        ok = (
            task is None
            and run is None
            and "review-stable-sibling-branch" not in resolve_run.unlocked_tasks
        )
        return ok, "stable sibling review omitted after 0.85 seed becomes baseline"

    return check


def _has_partial_field_high_fov_branch() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "partial-field high-FOV branch missing because assessment is missing"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "partial-field-high-fov-draft"
            ),
            None,
        )
        if branch is None:
            return False, "partial-field high-FOV draft branch present"
        metrics = branch.metrics
        has_partial_field_metrics = (
            metrics is not None
            and metrics.mtf_max_field_frac is not None
            and metrics.mtf_max_field_frac < 1.0
            and metrics.effective_focal_length_mm is not None
            and metrics.mtf_50lpmm_min is not None
        )
        evidence_ok = any("partial-field real case" in item for item in branch.evidence)
        risk_ok = any("full-field edge-performance" in item for item in branch.risks)
        ok = (
            branch.source == "strategy_option"
            and branch.strategy_option_id == "partial_field_high_fov_draft"
            and branch.status == "conditional"
            and branch.recommendation == "hold"
            and has_partial_field_metrics
            and evidence_ok
            and risk_ok
        )
        return ok, f"partial-field high-FOV branch {branch.status}"

    return check


def _high_fov_seed_baseline_maps_partial_strategy() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "seed baseline strategy mapping missing because assessment is missing"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "seed-baseline"
            ),
            None,
        )
        if branch is None:
            return False, "seed baseline branch present"
        ok = branch.strategy_option_id == "partial_field_high_fov_draft"
        return ok, f"seed baseline strategy {branch.strategy_option_id}"

    return check


def _has_branch_selection_policy() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.branch_selection_policy is None:
            return False, "branch selection policy missing"
        policy = assessment.branch_selection_policy
        has_order = policy.candidate_priority_order[:4] == [
            "high-fov-full-field-seed-needed",
            "near-threshold-partial-field",
            "relaxed-fov-full-field",
            "partial-field-high-fov-draft",
        ]
        has_requirements = any("1.0 field" in item for item in policy.promotion_requirements)
        has_forbidden = any(
            "full-field edge-performance" in item for item in policy.forbidden_claims
        )
        ok = (
            policy.status == "strategy_resolution_required"
            and policy.active_candidate_id == "seed-baseline"
            and policy.primary_candidate_id == "high-fov-full-field-seed-needed"
            and policy.current_deliverable_candidate_id == "partial-field-high-fov-draft"
            and "high-fov-full-field-seed-needed" in policy.blocked_candidate_ids
            and "stable-partial-field-sibling" not in policy.fallback_candidate_ids
            and "near-threshold-partial-field" in policy.fallback_candidate_ids
            and "relaxed-fov-full-field" in policy.fallback_candidate_ids
            and "partial-field-high-fov-draft" in policy.fallback_candidate_ids
            and has_order
            and has_requirements
            and has_forbidden
        )
        return ok, f"branch selection policy {policy.status}"

    return check


def _has_strategy_tradeoff_matrix() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "strategy tradeoff matrix missing because assessment is missing"
        rows = {row.candidate_id: row for row in assessment.strategy_tradeoff_matrix}
        required_ids = [
            "high-fov-full-field-seed-needed",
            "near-threshold-partial-field",
            "relaxed-fov-full-field",
            "partial-field-high-fov-draft",
        ]
        if not set(required_ids).issubset(rows):
            return False, "strategy tradeoff matrix contains high-FOV decision rows"
        primary = rows["high-fov-full-field-seed-needed"]
        near = rows["near-threshold-partial-field"]
        relaxed = rows["relaxed-fov-full-field"]
        partial = rows["partial-field-high-fov-draft"]
        order_ok = [rows[item].priority_rank for item in required_ids] == [
            1,
            2,
            3,
            4,
        ] and "stable-partial-field-sibling" not in rows
        primary_ok = (
            primary.evidence_level == "missing_seed"
            and primary.claim_status == "blocked_until_reference_seed"
            and "primary" in primary.role_tags
            and "blocked" in primary.role_tags
            and ">=85 deg" in primary.next_action
        )
        near_ok = (
            near.evidence_level == "partial_field"
            and near.claim_status == "partial_field_only_no_edge_claim"
            and near.mtf_max_field_frac == 0.9
            and near.delta_fov_deg is not None
            and near.delta_fov_deg < 0
            and "near-threshold" in near.next_action
        )
        relaxed_ok = (
            relaxed.evidence_level == "full_field"
            and relaxed.claim_status == "full_field_available_if_fov_relaxed"
            and relaxed.mtf_max_field_frac == 1.0
            and relaxed.delta_fov_deg is not None
            and relaxed.delta_fov_deg < -5.0
            and "relax target FOV" in relaxed.next_action
        )
        partial_ok = (
            partial.evidence_level == "partial_field"
            and partial.claim_status == "partial_field_only_no_edge_claim"
            and "current_deliverable" in partial.role_tags
            and partial.mtf_max_field_frac is not None
            and partial.mtf_max_field_frac < 1.0
            and "partial-field" in partial.tradeoff_summary
            and "field only" in partial.tradeoff_summary
        )
        ok = order_ok and primary_ok and near_ok and relaxed_ok and partial_ok
        return ok, f"strategy tradeoff rows {len(assessment.strategy_tradeoff_matrix)}"

    return check


def _cost_priority_resolves_low_risk_candidate_branch() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.branch_selection_policy is None:
            return False, "cost/yield branch selection policy missing"
        policy = assessment.branch_selection_policy
        tasks = assessment.optimization_task_queue
        runs = assessment.optimization_task_runs
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "low-risk-candidate-review"
            ),
            None,
        )
        ok = (
            branch is not None
            and branch.source == "candidate_proxy"
            and policy.status == "resolved"
            and policy.primary_candidate_id == assessment.recommended_candidate_id
            and "low-risk-candidate-review" in policy.blocked_candidate_ids
            and any("FOV miss" in item for item in policy.rationale)
            and bool(tasks)
            and tasks[0].task_id == "package-optimizer-proposal-review"
            and tasks[0].candidate_id == assessment.recommended_candidate_id
            and bool(runs)
            and runs[0].task_id == "package-optimizer-proposal-review"
            and runs[0].status == "passed"
        )
        return ok, f"cost/yield branch policy {policy.status}/{policy.primary_candidate_id}"

    return check


def _big_sensor_rejects_low_risk_target_miss() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "big-sensor proxy rejection missing assessment"
        branch = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == "low-risk-candidate-review"
            ),
            None,
        )
        proxy_check = next(
            (
                item
                for item in assessment.draft_acceptance_gate.checks
                if item.check_id == "candidate_proxy_review"
            ),
            None,
        )
        gap = image_quality_floor_gap_score(branch.metrics) if branch and branch.metrics else None
        ok = (
            branch is not None
            and branch.source == "candidate_proxy"
            and branch.status == "blocked"
            and branch.recommendation == "reject"
            and gap == 0.0
            and any("EFL miss" in item for item in branch.risks)
            and any("image-height miss" in item for item in branch.risks)
            and proxy_check is not None
            and proxy_check.status == "pass"
            and "rejected" in proxy_check.evidence
            and assessment.recommended_candidate_id == "optimizer-proposal"
        )
        status = branch.status if branch is not None else "missing"
        return ok, f"big-sensor low-risk proxy branch {status}, gap={gap}"

    return check


def _mass_budget_is_scored() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.manufacturability_review is None:
            return False, "mass budget missing because assessment is missing"
        coverage = {item.requirement_id: item for item in assessment.requirement_coverage}
        item = coverage.get("mass_budget")
        mass_check = next(
            (
                check
                for check in assessment.manufacturability_review.checks
                if check.check_id == "mass_proxy_budget"
            ),
            None,
        )
        ok = (
            item is not None
            and item.status in {"met", "tradeoff", "miss"}
            and item.status != "unscored"
            and item.delta is not None
            and "optical-stack proxy" in item.actual
            and mass_check is not None
            and mass_check.status in {"pass", "warning", "blocker"}
            and "proxy" in mass_check.actual
        )
        return ok, f"mass budget {item.status if item else 'missing'}"

    return check


def _high_fov_mtf_coverage_is_tradeoff() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "missing assessment"
        by_id = {item.requirement_id: item for item in assessment.requirement_coverage}
        mtf_item = by_id.get("mtf_field_evidence")
        priority_item = by_id.get("design_priority")
        ok = (
            mtf_item is not None
            and mtf_item.status == "tradeoff"
            and mtf_item.actual.startswith("0.8")
            and priority_item is not None
            and priority_item.status == "tradeoff"
        )
        return ok, "high-FOV MTF and priority coverage remain tradeoffs"

    return check


def _high_fov_acceptance_is_conditional() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "high-FOV draft acceptance gate missing"
        gate = assessment.draft_acceptance_gate
        check_ids = {item.check_id for item in gate.checks}
        has_required_checks = {
            "requirement_coverage",
            "delivery_gate",
            "branch_selection",
            "optimizer_verification",
            "image_quality_floor",
            "task_run_evidence",
        }.issubset(check_ids)
        has_promotion_action = any(
            "1.0 field" in item or "full-field" in item for item in gate.required_next_actions
        )
        has_forbidden_claim = any(
            "full-field edge-performance" in item for item in gate.forbidden_claims
        )
        has_upgrade_action = any(
            action.source_check_id in {"delivery_gate", "branch_selection", "requirement_coverage"}
            and ("1.0 field" in action.action or "full-field" in action.action)
            and any("1.0 field" in item for item in action.acceptance_criteria)
            and any("full-field edge-performance" in item for item in action.unblocks_claims)
            for action in gate.upgrade_actions
        )
        ok = (
            gate.status in {"blocked", "conditional"}
            and gate.deliverable_type == "partial-field concept only"
            and gate.candidate_id == "seed-baseline"
            and has_required_checks
            and has_promotion_action
            and has_forbidden_claim
            and has_upgrade_action
        )
        return ok, f"high-FOV acceptance {gate.status}"

    return check


def _high_fov_has_seed_ingestion_task() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "missing assessment"
        task = next(
            (
                item
                for item in assessment.acceptance_improvement_tasks
                if item.task_id == "ingest-high-fov-full-field-seed"
            ),
            None,
        )
        if task is None:
            return False, "high-FOV seed-ingestion acceptance task missing"
        text = " ".join(
            [
                task.objective,
                *task.required_inputs,
                *task.validation_steps,
                *task.exit_criteria,
                *task.blocks_claims,
                *(task.evidence_probe.known_evidence if task.evidence_probe else []),
                *(task.evidence_probe.missing_evidence if task.evidence_probe else []),
                task.evidence_probe.summary if task.evidence_probe else "",
                (task.evidence_probe.next_probe_command or "") if task.evidence_probe else "",
            ]
        )
        ok = (
            task.status == "external_evidence_required"
            and task.stage == "seed_ingestion"
            and task.owner == "case_library"
            and task.evidence_probe is not None
            and task.evidence_probe.status == "gap"
            and ">= 85.0 deg" in text
            and "1.0 field" in text
            and "full-field edge-performance" in text
            and "audit_seed_intake.py" in text
        )
        probe_status = task.evidence_probe.status if task.evidence_probe else "missing"
        return ok, f"high-FOV acceptance task {task.status}/{task.stage}/{probe_status}"

    return check


def _high_fov_has_seed_intake_audit() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.seed_intake_audit is None:
            return False, "seed intake audit missing"
        audit = assessment.seed_intake_audit
        nearest_roles = {item.role for item in audit.nearest_candidates}
        text = " ".join(
            [
                audit.summary,
                *audit.known_evidence,
                *audit.missing_evidence,
                audit.next_probe_command,
                audit.candidate_preflight_command,
                *[
                    " ".join([candidate.case_id, *candidate.miss_reasons])
                    for candidate in audit.nearest_candidates
                ],
            ]
        )
        ok = (
            audit.status == "gap"
            and audit.minimum_fov_deg >= 85.0
            and audit.required_mtf_field_frac >= 1.0
            and audit.total_seed_count >= audit.high_fov_seed_count
            and audit.full_field_seed_count > 0
            and audit.high_fov_seed_count > 0
            and audit.accepted_seed_count == 0
            and audit.accepted_seed_candidates == []
            and {"nearest_high_fov", "nearest_full_field"}.issubset(nearest_roles)
            and "accepted high-FOV full-field seeds=0" in text
            and "MTF evaluates at 1.0 field without fallback" in text
            and "audit_seed_intake.py" in text
            and "--candidate-zmx /path/to/candidate.zmx" in text
        )
        return (
            ok,
            f"seed intake audit {audit.status}, accepted={audit.accepted_seed_count}",
        )

    return check


def _high_fov_has_seed_acquisition_contract() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.seed_acquisition_contract is None:
            return False, "seed acquisition contract missing"
        contract = assessment.seed_acquisition_contract
        text = " ".join(
            [
                contract.summary,
                contract.acceptance_target,
                *(contract.required_candidate_properties),
                *(contract.pass_criteria),
                *(contract.rejection_filters),
                *(contract.current_gap_evidence),
                *(contract.fallback_paths),
                *(contract.blocked_claims),
                contract.preflight_command or "",
                contract.next_action,
            ]
        )
        ok = (
            contract.status == "external_evidence_required"
            and contract.source_task_id == "ingest-high-fov-full-field-seed"
            and "FOV >= 85.0 deg" in text
            and "1.0 field" in text
            and "accepted high-FOV full-field seeds=0" in text
            and "near miss nearest_high_fov" in text
            and "near miss best_stable_high_fov" in text
            and "MTF field" in text
            and "near miss nearest_full_field" in text
            and len(contract.current_gap_evidence) >= 2
            and contract.current_gap_evidence[0].startswith("near miss nearest_high_fov")
            and any(
                item.startswith("near miss nearest_full_field")
                for item in contract.current_gap_evidence[:3]
            )
            and "audit_seed_intake.py" in text
            and "--candidate-zmx /path/to/candidate.zmx" in text
            and "full-field edge-performance claim" in text
            and any("partial_field" in item for item in contract.fallback_paths)
            and any("full_field_available" in item for item in contract.fallback_paths)
        )
        return ok, f"seed acquisition contract {contract.status}: {contract.acceptance_target}"

    return check


def _seed_baseline_hold_ready_for_review() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "seed-baseline readiness missing because assessment is missing"
        gate = assessment.draft_acceptance_gate
        checks = {item.check_id: item for item in gate.checks}
        required_check_ids = {
            "requirement_coverage",
            "manufacturability",
            "optimizer_verification",
            "image_quality_probe",
            "image_quality_floor",
            "task_run_evidence",
        }
        check_statuses_pass = all(
            checks.get(check_id) is not None and checks[check_id].status == "pass"
            for check_id in required_check_ids
        )
        evidence_text = " ".join(item.evidence for item in checks.values())
        ok = (
            assessment.recommended_candidate_id == "seed-baseline"
            and gate.status == "ready_for_review"
            and gate.score == 1.0
            and not gate.upgrade_actions
            and not assessment.acceptance_improvement_tasks
            and check_statuses_pass
            and "unchanged seed-baseline hold accepted" in evidence_text
            and "no protected optimizer change is required" in evidence_text
        )
        return ok, f"seed-baseline acceptance {gate.status}"

    return check


def _seed_baseline_hold_blocked_on_quality_floor_with_review_notes() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "seed-baseline readiness missing because assessment is missing"
        gate = assessment.draft_acceptance_gate
        checks = {item.check_id: item for item in gate.checks}
        optimizer_checks_pass = all(
            checks.get(check_id) is not None and checks[check_id].status == "pass"
            for check_id in {
                "optimizer_verification",
                "image_quality_probe",
                "task_run_evidence",
            }
        )
        recovery_run = next(
            (
                run
                for run in assessment.optimization_task_runs
                if run.task_id == "recover-image-quality-floor"
            ),
            None,
        )
        replay_run = next(
            (
                run
                for run in assessment.optimization_task_runs
                if run.task_id == "replay-floor-gap-recovery-candidate"
            ),
            None,
        )
        recovery_metric = next(
            (
                metric
                for metric in (recovery_run.metric_updates if recovery_run is not None else [])
                if metric.metric == "recovery_probe_floor_gap_score"
            ),
            None,
        )
        recovery_evidence_ready = (
            recovery_run is not None
            and recovery_run.status in {"warning", "passed", "diagnostic"}
            and recovery_metric is not None
            and recovery_metric.before is not None
            and recovery_metric.after is not None
            and recovery_metric.after < recovery_metric.before
            and any("best floor-gap trial=" in item for item in recovery_run.evidence)
            and replay_run is not None
            and replay_run.replay_gate is not None
            and replay_run.replay_gate.promotion_allowed is False
            and any(
                check.check_id == "payload_frozen" and check.status == "pass"
                for check in replay_run.replay_gate.checks
            )
        )
        optimizer_checks_ready = optimizer_checks_pass or (
            recovery_evidence_ready
            and checks.get("optimizer_verification") is not None
            and checks["optimizer_verification"].status == "warning"
            and checks.get("image_quality_probe") is not None
            and checks["image_quality_probe"].status == "warning"
            and checks.get("task_run_evidence") is not None
            and checks["task_run_evidence"].status == "pass"
        )
        review_note_text = " ".join(gate.review_notes)
        evidence_text = " ".join(item.evidence for item in checks.values())
        floor_task = next(
            (
                task
                for task in assessment.acceptance_improvement_tasks
                if task.source_action_id.startswith("image_quality_floor")
            ),
            None,
        )
        ok = (
            assessment.recommended_candidate_id == "seed-baseline"
            and gate.status == "blocked"
            and gate.score >= 0.50
            and bool(gate.review_notes)
            and any(
                action.source_check_id == "image_quality_floor" for action in gate.upgrade_actions
            )
            and floor_task is not None
            and floor_task.stage == "image_quality_recovery"
            and optimizer_checks_ready
            and checks.get("image_quality_floor") is not None
            and checks["image_quality_floor"].status == "blocker"
            and "tolerance" in review_note_text
            and "manufacturability" in review_note_text.lower()
            and (
                (
                    "unchanged seed-baseline hold accepted" in evidence_text
                    and "no protected optimizer change is required" in evidence_text
                )
                or recovery_evidence_ready
            )
            and any("production-ready" in claim for claim in gate.forbidden_claims)
        )
        return (
            ok,
            f"seed-baseline floor-gated hold {gate.status}, notes={len(gate.review_notes)}",
        )

    return check


def _seed_baseline_queue_starts_with_review_package() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "seed-baseline queue missing because assessment is missing"
        tasks = assessment.optimization_task_queue
        runs = assessment.optimization_task_runs
        if not tasks or not runs:
            return False, "seed-baseline queue/run missing"
        first_task = tasks[0]
        first_run = runs[0]
        evidence_text = " ".join(first_run.evidence)
        review_package_ok = (
            first_task.task_id == "package-seed-baseline-review"
            and first_task.status == "ready"
            and first_task.stage == "review_package"
            and first_run.task_id == first_task.task_id
            and first_run.status == "passed"
            and "no optimizer proposal is required" in evidence_text
            and all(task.task_id != "stabilize-optimizer" for task in tasks[:2])
        )
        recovery_task = next(
            (task for task in tasks if task.task_id == "recover-image-quality-floor"),
            None,
        )
        recovery_run = next(
            (run for run in runs if run.task_id == "recover-image-quality-floor"),
            None,
        )
        recovery_metric = next(
            (
                metric
                for metric in (recovery_run.metric_updates if recovery_run is not None else [])
                if metric.metric == "recovery_probe_floor_gap_score"
            ),
            None,
        )
        floor_recovery_ok = (
            first_task.task_id == "lock-first-order"
            and first_task.status == "ready"
            and first_run.task_id == "lock-first-order"
            and first_run.status == "passed"
            and recovery_task is not None
            and recovery_task.status == "queued"
            and recovery_task.depends_on == ["lock-first-order"]
            and recovery_run is not None
            and recovery_run.status in {"warning", "passed", "diagnostic"}
            and recovery_metric is not None
            and recovery_metric.before is not None
            and recovery_metric.after is not None
            and recovery_metric.after < recovery_metric.before
            and any("best floor-gap trial=" in item for item in recovery_run.evidence)
            and all(task.task_id != "stabilize-optimizer" for task in tasks[:2])
        )
        ok = review_package_ok or floor_recovery_ok
        path = "floor-recovery" if floor_recovery_ok else "review-package"
        return ok, f"seed-baseline first task {first_task.task_id}/{first_run.status} via {path}"

    return check


def _proposal_ready_with_review_notes() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "proposal readiness missing because assessment is missing"
        gate = assessment.draft_acceptance_gate
        checks = {item.check_id: item for item in gate.checks}
        ok = (
            assessment.recommended_candidate_id == "optimizer-proposal"
            and gate.status == "ready_for_review"
            and bool(gate.review_notes)
            and not gate.upgrade_actions
            and not assessment.acceptance_improvement_tasks
            and bool(assessment.optimization_task_queue)
            and assessment.optimization_task_queue[0].task_id == "package-optimizer-proposal-review"
            and bool(assessment.optimization_task_runs)
            and assessment.optimization_task_runs[0].task_id == "package-optimizer-proposal-review"
            and assessment.optimization_task_runs[0].status == "passed"
            and checks.get("optimizer_verification") is not None
            and checks["optimizer_verification"].status == "pass"
            and checks.get("delivery_gate") is not None
            and checks["delivery_gate"].status == "pass"
        )
        return ok, f"proposal acceptance {gate.status}, notes={len(gate.review_notes)}"

    return check


def _proposal_conditional_with_review_notes() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "proposal readiness missing because assessment is missing"
        gate = assessment.draft_acceptance_gate
        checks = {item.check_id: item for item in gate.checks}
        ok = (
            assessment.recommended_candidate_id == "optimizer-proposal"
            and gate.status in {"blocked", "conditional", "ready_for_review"}
            and gate.score >= 0.40
            and bool(gate.review_notes)
            and bool(assessment.optimization_task_queue)
            and assessment.optimization_task_queue[0].task_id == "package-optimizer-proposal-review"
            and bool(assessment.optimization_task_runs)
            and assessment.optimization_task_runs[0].task_id == "package-optimizer-proposal-review"
            and assessment.optimization_task_runs[0].status == "passed"
            and checks.get("optimizer_verification") is not None
            and checks["optimizer_verification"].status == "pass"
            and checks.get("delivery_gate") is not None
            and checks["delivery_gate"].status == "pass"
            and checks.get("image_quality_floor") is not None
            and checks["image_quality_floor"].status in {"blocker", "pass"}
        )
        return ok, f"proposal acceptance {gate.status}, notes={len(gate.review_notes)}"

    return check


def _has_structured_variable_candidates() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.optimization_attempt is None:
            return False, "variable candidates missing because optimizer attempt is missing"
        attempt = assessment.optimization_attempt
        attempt_ok = any(
            candidate.variable == "radius" and candidate.status == "eligible"
            for candidate in attempt.variable_candidates
        )
        if not attempt_ok:
            return False, "optimizer attempt has no eligible radius candidate"
        if not attempt.candidate_trials:
            return False, "optimizer attempt has no variable trial replay"

        probe = assessment.merit_optimization_probe
        if probe is None or probe.status == "not_attempted":
            return True, "attempt variable candidates present; merit probe not attempted"
        probe_ok = any(
            candidate.variable in {"radius", "thickness"} and candidate.status == "eligible"
            for candidate in probe.variable_candidates
        )
        if not probe_ok:
            return False, "merit probe has no eligible structured variable candidate"
        asphere_candidates = [
            candidate
            for candidate in probe.variable_candidates
            if candidate.variable == "asphere_coefficient" and candidate.status == "audited_only"
        ]
        if asphere_candidates and not all(
            candidate.min_value is not None
            and candidate.max_value is not None
            and candidate.asphere_power is not None
            and candidate.audit_aperture_mm is not None
            and candidate.edge_sag_delta_um is not None
            and candidate.edge_slope_delta_mrad is not None
            and candidate.manufacturability_status == "guarded"
            for candidate in asphere_candidates
        ):
            return False, "asphere audited candidates are missing manufacturability guard evidence"
        trial_ok = bool(probe.candidate_trials)
        if not trial_ok:
            return False, "merit probe has no variable trial replay"
        score_ok = any(trial.promotion_score is not None for trial in probe.candidate_trials)
        guarded_aspheres = [
            candidate
            for candidate in asphere_candidates
            if candidate.manufacturability_status == "guarded"
        ]
        if probe.status == "warning" and guarded_aspheres:
            has_asphere_audit_trial = any(
                trial.variable == "asphere_coefficient"
                and trial.status in {"improved", "rejected", "failed"}
                and trial.coefficient_index is not None
                and trial.prescreen_rank is not None
                and trial.step_fraction is not None
                and trial.merit_before is not None
                and trial.merit_after is not None
                for trial in probe.candidate_trials
            )
            if not has_asphere_audit_trial:
                return False, "warning merit probe has no asphere audit replay trial"
            merit_change_variable = (
                probe.variable_changes[0].variable if probe.variable_changes else None
            )
            if merit_change_variable in {"radius", "thickness"}:
                has_joint_audit_trial = any(
                    trial.variable == "joint_asphere_merit"
                    and trial.status in {"improved", "rejected", "failed"}
                    and trial.coefficient_index is not None
                    and trial.coupled_variable in {"radius", "thickness"}
                    and trial.coupled_surface_index is not None
                    and trial.coupled_before is not None
                    and trial.coupled_after is not None
                    for trial in probe.candidate_trials
                )
                if not has_joint_audit_trial:
                    return False, "warning merit probe has no joint asphere/merit audit trial"
        return (
            score_ok,
            "structured variable candidates and promotion-scored trial replay are present",
        )

    return check


def _merit_probe_selection_prefers_accepted_trial() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        probe = assessment.merit_optimization_probe if assessment else None
        if probe is None or probe.status == "not_attempted":
            return True, "merit probe selection skipped"
        has_accepted_trial = any(trial.status == "accepted" for trial in probe.candidate_trials)
        if not has_accepted_trial:
            has_nonnegative_warning = any(
                trial.rms_improvement_um is not None and trial.rms_improvement_um >= 0
                for trial in probe.candidate_trials
            )
            if has_nonnegative_warning and probe.rms_improvement_um is not None:
                return probe.rms_improvement_um >= 0, "warning merit trial keeps RMS non-worse"
            return True, "merit probe has no accepted or non-negative trial to prefer"
        return probe.status == "proposal", "accepted merit trial is selected as proposal"

    return check


def _merit_probe_proposal_has_quality_gate() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        probe = assessment.merit_optimization_probe if assessment else None
        if probe is None or probe.status != "proposal":
            return True, "merit quality gate skipped for non-proposal"
        if probe.before_metrics is None or probe.after_metrics is None:
            return False, "proposal merit probe missing before/after metrics"
        if (
            probe.before_metrics.max_rms_spot_radius_um is None
            or probe.after_metrics.max_rms_spot_radius_um is None
        ):
            return False, "proposal merit probe missing RMS metric snapshots"
        accepted_trials = [trial for trial in probe.candidate_trials if trial.status == "accepted"]
        gate_clean_trial = any(
            trial.rms_improvement_um is not None
            and probe.rms_improvement_um is not None
            and trial.rms_improvement_um >= probe.rms_improvement_um - 1e-6
            and trial.rms_improvement_um > 0.0
            and trial.mtf_band_non_regressed is True
            and trial.mtf_field_weighted_non_regressed is True
            and trial.efl_locked is True
            and trial.image_quality_floor_gap_before is not None
            and trial.image_quality_floor_gap_after is not None
            and trial.image_quality_floor_gap_closure is not None
            and trial.image_quality_floor_gap_closure >= 0.0
            for trial in accepted_trials
        )
        rms_snapshot_improved = (
            probe.after_metrics.max_rms_spot_radius_um < probe.before_metrics.max_rms_spot_radius_um
        )
        ok = (
            probe.rms_improvement_um is not None
            and probe.rms_improvement_um > 0.0
            and rms_snapshot_improved
            and probe.verification is not None
            and probe.verification.status == "passed"
            and gate_clean_trial
        )
        return ok, f"merit proposal quality gate rms={probe.rms_improvement_um}"

    return check


def _compound_merit_branch_is_guarded(min_rms_um: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        probe = assessment.merit_optimization_probe if assessment else None
        if probe is None:
            return False, "merit probe missing"
        compound_trials = [
            trial for trial in probe.candidate_trials if trial.variable == "compound_merit"
        ]
        has_promoted_compound = (
            probe.status == "proposal"
            and len(probe.variable_changes) >= 2
            and any(
                trial.status == "accepted"
                and trial.rms_improvement_um is not None
                and probe.rms_improvement_um is not None
                and trial.rms_improvement_um >= probe.rms_improvement_um - 1e-6
                and trial.image_quality_floor_gap_before is not None
                and trial.image_quality_floor_gap_after is not None
                and trial.image_quality_floor_gap_closure is not None
                for trial in compound_trials
            )
        )
        change_set = assessment.prescription_change_set if assessment else None
        promoted_to_change_set = change_set is not None and len(change_set.changes) >= len(
            probe.variable_changes
        ) + (
            len(assessment.optimization_attempt.variable_changes)
            if assessment and assessment.optimization_attempt
            else 0
        )
        if has_promoted_compound:
            ok = (
                probe.rms_improvement_um is not None
                and probe.rms_improvement_um >= min_rms_um
                and promoted_to_change_set
            )
            return ok, f"compound merit branch promoted with RMS >= {min_rms_um:.1f} um"
        if compound_trials:
            return True, "compound merit trials stayed gated without promotion"
        return True, "compound merit replay not available on this runner"

    return check


def _floor_gap_recovery_closure_at_least(min_closure: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        probe = assessment.merit_optimization_probe if assessment else None
        if probe is None:
            return False, "merit probe missing"
        closures = [
            trial.image_quality_floor_gap_closure
            for trial in probe.candidate_trials
            if trial.status == "accepted"
            if trial.image_quality_floor_gap_closure is not None
        ]
        best = max(closures, default=None)
        ok = best is not None and best >= min_closure
        return ok, f"best accepted floor-gap closure {best} >= {min_closure:.3f}"

    return check


def _stop_position_recovery_closure_at_least(min_closure: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        probe = assessment.merit_optimization_probe if assessment else None
        if probe is None:
            return False, "merit probe missing"
        closures = [
            trial.image_quality_floor_gap_closure
            for trial in probe.candidate_trials
            if trial.variable == "stop_position"
            and trial.status == "accepted"
            and trial.image_quality_floor_gap_closure is not None
        ]
        best = max(closures, default=None)
        ok = best is not None and best >= min_closure
        return ok, f"best accepted stop-position closure {best} >= {min_closure:.3f}"

    return check


def _focus_position_recovery_closure_at_least(min_closure: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        probe = assessment.merit_optimization_probe if assessment else None
        if probe is None:
            return False, "merit probe missing"
        closures = [
            trial.image_quality_floor_gap_closure
            for trial in probe.candidate_trials
            if trial.variable == "focus_position"
            and trial.status == "accepted"
            and trial.image_quality_floor_gap_closure is not None
        ]
        best = max(closures, default=None)
        ok = best is not None and best >= min_closure
        return ok, f"best accepted focus-position closure {best} >= {min_closure:.3f}"

    return check


def _second_pass_compound_continuation_gap_at_most(max_gap: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        local_run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "local-merit-tuning"
            ),
            None,
        )
        if local_run is None:
            return False, "local-merit-tuning run missing"
        replay_run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "replay-second-pass-recovery-candidate"
            ),
            None,
        )
        floor_metric = next(
            (
                metric
                for metric in (
                    replay_run.metric_updates
                    if replay_run is not None
                    else local_run.metric_updates
                )
                if metric.metric
                in {
                    "second_pass_replay_floor_gap_score",
                    "local_merit_floor_gap_score",
                }
            ),
            None,
        )
        after_gap = floor_metric.after if floor_metric else None
        before_gap = floor_metric.before if floor_metric else None
        has_compound_continuation = any(
            "variable=compound" in item
            and "S14 focus_position 0.1540->0.0540" in item
            and "S4 radius 4.9395->4.9889" in item
            for item in [
                *local_run.evidence,
                *(replay_run.evidence if replay_run is not None else []),
            ]
        )
        status_ok = (
            replay_run.status in {"passed", "warning"}
            if replay_run is not None
            else local_run.status == "passed"
        )
        ok = (
            status_ok
            and before_gap is not None
            and after_gap is not None
            and after_gap < before_gap
            and after_gap <= max_gap
            and has_compound_continuation
        )
        source = "replay verdict" if replay_run is not None else "local merit"
        return ok, (f"second-pass compound continuation {source} gap {after_gap} <= {max_gap:.3f}")

    return check


def _local_merit_floor_gap_evidence_uses_accepted_trial() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "local-merit-tuning"
            ),
            None,
        )
        if run is None:
            return False, "local-merit-tuning run missing"
        accepted_evidence = any(
            item.startswith("best accepted image-quality floor gap closure=+")
            and "trial=compound_continuation S14" in item
            and "status=accepted" in item
            for item in run.evidence
        )
        raw_max_evidence = any(
            item.startswith("best image-quality floor gap closure=") for item in run.evidence
        )
        ok = accepted_evidence and not raw_max_evidence
        return ok, "local-merit floor-gap evidence uses accepted trial, not raw max"

    return check


def _second_pass_recovery_candidate_gap_at_most(max_gap: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        candidate = next(
            (
                item
                for item in assessment.draft_candidates
                if item.candidate_id == "second-pass-recovery-candidate"
            ),
            None,
        )
        if candidate is None or candidate.metrics is None:
            return False, "second-pass recovery candidate missing"
        gap = image_quality_floor_gap_score(candidate.metrics)
        has_compound_evidence = any(
            "S14 focus_position 0.1540->0.0540" in item and "S4 radius 4.9395->4.9889" in item
            for item in candidate.evidence
        )
        ok = (
            candidate.recommendation == "hold"
            and gap is not None
            and gap <= max_gap
            and has_compound_evidence
        )
        return ok, f"second-pass recovery candidate gap {gap} <= {max_gap:.3f}"

    return check


def _second_pass_replay_task_is_queued() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        task = next(
            (
                item
                for item in assessment.optimization_task_queue
                if item.task_id == "replay-second-pass-recovery-candidate"
            ),
            None,
        )
        ok = (
            task is not None
            and task.candidate_id == "second-pass-recovery-candidate"
            and task.status == "queued"
            and task.depends_on == ["local-merit-tuning"]
            and any("second-pass floor gap=" in item for item in task.evidence)
        )
        return ok, "second-pass recovery candidate replay task is queued"

    return check


def _second_pass_asphere_audit_present() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "local-merit-tuning"
            ),
            None,
        )
        if run is None:
            return False, "local-merit-tuning run missing"
        has_second_pass_source = any(
            "merit probe source=second-pass-continuation-probe" in item for item in run.evidence
        )
        has_audit_trials = any(
            "asphere audit trials=" in item and "asphere audit trials=0" not in item
            for item in run.evidence
        )
        has_prescreen = any(
            item.startswith("asphere prescreen trials=") and item != "asphere prescreen trials=0"
            for item in run.evidence
        )
        ok = has_second_pass_source and has_audit_trials and has_prescreen
        return ok, "second-pass remediation runs guarded asphere audit"

    return check


def _second_pass_replay_run_has_verdict(max_gap: float) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        run = next(
            (
                item
                for item in assessment.optimization_task_runs
                if item.task_id == "replay-second-pass-recovery-candidate"
            ),
            None,
        )
        if run is None:
            return False, "second-pass replay run missing"
        metric = next(
            (
                item
                for item in run.metric_updates
                if item.metric == "second_pass_replay_floor_gap_score"
            ),
            None,
        )
        gate = run.replay_gate
        after_gap = metric.after if metric is not None else None
        before_gap = metric.before if metric is not None else None
        ok = (
            run.status == "warning"
            and gate is not None
            and gate.gate_id == "second-pass-recovery-replay"
            and gate.promotion_allowed is False
            and "floor_gap_cleared" in gate.failed_check_ids
            and before_gap is not None
            and after_gap is not None
            and after_gap < before_gap
            and after_gap <= max_gap
            and any("promotion allowed=False" in item for item in run.evidence)
        )
        return ok, f"second-pass replay verdict gap {after_gap} <= {max_gap:.3f}"

    return check


def _image_quality_floor_gates_low_mtf() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "assessment missing"
        recommended = next(
            (
                candidate
                for candidate in assessment.draft_candidates
                if candidate.candidate_id == assessment.recommended_candidate_id
            ),
            None,
        )
        if recommended is None or recommended.metrics is None:
            return False, "recommended candidate metrics missing"
        metrics = recommended.metrics
        low_quality_floor = (
            metrics.mtf_multiband_min_score is None
            or metrics.mtf_multiband_min_score < 0.08
            or metrics.mtf_field_weighted_score is None
            or metrics.mtf_field_weighted_score < 0.15
            or metrics.max_rms_spot_radius_um is None
            or metrics.max_rms_spot_radius_um > 100.0
        )
        quality = assessment.draft_quality_rubric
        readiness = assessment.designer_readiness_rubric
        if quality is None or readiness is None:
            return False, "quality/readiness rubric missing"
        optical_dimension = next(
            (
                dimension
                for dimension in quality.dimensions
                if dimension.dimension_id == "optical_evidence"
            ),
            None,
        )
        if optical_dimension is None:
            return False, "optical evidence dimension missing"
        has_floor_evidence = any(
            "image quality floor" in item for item in optical_dimension.evidence
        )
        recovery_task = next(
            (
                task
                for task in assessment.optimization_task_queue
                if task.task_id == "recover-image-quality-floor"
            ),
            None,
        )
        if low_quality_floor:
            task_ready = (
                recovery_task is not None
                and recovery_task.stage == "image_quality_recovery"
                and recovery_task.status == "queued"
                and "lock-first-order" in recovery_task.depends_on
                and any("image quality floor" in item for item in recovery_task.evidence)
                and any("dominant floor gap=" in item for item in recovery_task.evidence)
                and any("targeted recovery variables=" in item for item in recovery_task.evidence)
            )
            lock_passed = any(
                run.task_id == "lock-first-order" and run.status == "passed"
                for run in assessment.optimization_task_runs
            )
            recovery_run = next(
                (
                    run
                    for run in assessment.optimization_task_runs
                    if run.task_id == "recover-image-quality-floor"
                ),
                None,
            )
            recovery_branch = next(
                (
                    candidate
                    for candidate in assessment.draft_candidates
                    if candidate.candidate_id == "floor-gap-recovery-candidate"
                ),
                None,
            )
            replay_task = next(
                (
                    task
                    for task in assessment.optimization_task_queue
                    if task.task_id == "replay-floor-gap-recovery-candidate"
                ),
                None,
            )
            remediation_task = next(
                (
                    task
                    for task in assessment.optimization_task_queue
                    if task.task_id == "remediate-recovery-replay-gate"
                ),
                None,
            )
            local_merit_task = next(
                (
                    task
                    for task in assessment.optimization_task_queue
                    if task.task_id == "local-merit-tuning"
                ),
                None,
            )
            followup_task = next(
                (
                    task
                    for task in assessment.optimization_task_queue
                    if task.task_id == "resolve-remediation-policy-block"
                ),
                None,
            )
            replay_run = next(
                (
                    run
                    for run in assessment.optimization_task_runs
                    if run.task_id == "replay-floor-gap-recovery-candidate"
                ),
                None,
            )
            remediation_run = next(
                (
                    run
                    for run in assessment.optimization_task_runs
                    if run.task_id == "remediate-recovery-replay-gate"
                ),
                None,
            )
            local_merit_run = next(
                (
                    run
                    for run in assessment.optimization_task_runs
                    if run.task_id == "local-merit-tuning"
                ),
                None,
            )
            followup_run = next(
                (
                    run
                    for run in assessment.optimization_task_runs
                    if run.task_id == "resolve-remediation-policy-block"
                ),
                None,
            )
            resolution_acceptance_task = next(
                (
                    task
                    for task in assessment.acceptance_improvement_tasks
                    if task.task_id.startswith("resolve-task_run_evidence")
                ),
                None,
            )
            task_run_evidence_passed = assessment.draft_acceptance_gate is not None and any(
                check.check_id == "task_run_evidence" and check.status == "pass"
                for check in assessment.draft_acceptance_gate.checks
            )
            remediation_policy = (
                next(
                    (
                        item.removeprefix("remediation policy=")
                        for item in remediation_run.evidence
                        if item.startswith("remediation policy=")
                    ),
                    "",
                )
                if remediation_run is not None
                else ""
            )
            policy_action = (
                next(
                    (
                        item.removeprefix("policy action=")
                        for item in remediation_run.evidence
                        if item.startswith("policy action=")
                    ),
                    "",
                )
                if remediation_run is not None
                else ""
            )
            probe = assessment.merit_optimization_probe
            accepted_floor_gap_trial_available = probe is not None and any(
                trial.status == "accepted" and trial.image_quality_floor_gap_closure is not None
                for trial in probe.candidate_trials
            )
            accepted_floor_gap_replay_selected = (
                not accepted_floor_gap_trial_available
                or replay_run is None
                or any("trial status=accepted" in item for item in replay_run.evidence)
            )
            policy_downstream_ready = False
            remediation_probe_evidence_ready = False
            typed_resolution_packet_ready = False
            if followup_task is not None and followup_task.resolution_packet is not None:
                packet = followup_task.resolution_packet
                path_ids = {path.path_id for path in packet.paths}
                run_packet = followup_run.resolution_packet if followup_run is not None else None
                typed_resolution_packet_ready = (
                    packet.packet_id == "remediation-policy-block"
                    and packet.policy
                    and packet.policy_action
                    and {"stronger-seed", "alternate-variable-family", "replay-evidence"}
                    <= path_ids
                    and bool(packet.resume_criteria)
                    and run_packet is not None
                    and run_packet.packet_id == packet.packet_id
                )
            resolution_packet_ready = (
                followup_task is not None
                and all(
                    any(marker in item for item in followup_task.evidence)
                    for marker in [
                        "resolution packet=remediation-policy-block",
                        "resolution path=stronger-seed",
                        "resolution path=alternate-variable-family",
                        "resolution path=replay-evidence",
                        "resume criterion=policy changes",
                    ]
                )
                and followup_run is not None
                and any(
                    "resolution packet=remediation-policy-block" in item
                    for item in followup_run.evidence
                )
                and typed_resolution_packet_ready
            )
            resolution_acceptance_ready = (
                resolution_acceptance_task is not None
                and resolution_acceptance_task.stage == "remediation_resolution"
                and any(
                    "resolution packet policy=" in item
                    for item in resolution_acceptance_task.required_inputs
                )
                and any(
                    "policy changes to" in item for item in resolution_acceptance_task.exit_criteria
                )
                and resolution_acceptance_task.evidence_probe is not None
                and resolution_acceptance_task.evidence_probe.probe_id
                == "remediation-resolution-packet"
                and bool(resolution_acceptance_task.evidence_probe.missing_evidence)
            )
            if (
                remediation_task is not None
                and remediation_run is not None
                and local_merit_task is not None
            ):
                remediation_probe_evidence_ready = (
                    any(
                        metric.metric == "remediation_probe_floor_gap_score"
                        for metric in remediation_run.metric_updates
                    )
                    and any(
                        "probe purpose=replay_gate_remediation" in item
                        for item in remediation_run.evidence
                    )
                ) or (
                    remediation_policy == "probe_not_attempted"
                    and any(
                        "remediation probe=not_attempted" in item
                        for item in remediation_run.evidence
                    )
                )
                if remediation_policy == "switch_variable_family":
                    policy_downstream_ready = (
                        local_merit_task.status == "queued"
                        and local_merit_task.variables != remediation_task.variables
                        and "local-merit-tuning" in remediation_run.unlocked_tasks
                        and local_merit_run is not None
                        and any(
                            "merit probe source=policy-switched-remediation-probe" in item
                            for item in local_merit_run.evidence
                        )
                    )
                elif remediation_policy == "continue_second_pass_branch":
                    policy_downstream_ready = (
                        local_merit_task.status == "queued"
                        and local_merit_task.variables == remediation_task.variables
                        and "local-merit-tuning" in remediation_run.unlocked_tasks
                        and local_merit_run is not None
                        and any(
                            "merit probe source=second-pass-continuation-probe" in item
                            for item in local_merit_run.evidence
                        )
                    )
                elif remediation_policy in {
                    "hold_no_second_pass_gain",
                    "hold_no_alternative_variable_family",
                    "probe_inconclusive",
                    "probe_not_attempted",
                    "candidate_ready_for_replay_gate",
                }:
                    policy_downstream_ready = (
                        local_merit_task.status == "blocked"
                        and "local-merit-tuning" not in remediation_run.unlocked_tasks
                        and followup_task is not None
                        and followup_task.status == "queued"
                        and followup_task.depends_on == ["remediate-recovery-replay-gate"]
                        and "resolve-remediation-policy-block" in remediation_run.unlocked_tasks
                        and followup_run is not None
                        and followup_run.status == "diagnostic"
                        and any(
                            "do not resume local merit" in item for item in followup_task.evidence
                        )
                        and resolution_packet_ready
                        and (resolution_acceptance_ready or task_run_evidence_passed)
                    )
            recovery_trial_branch_ready = (
                recovery_run is None
                or not any("best floor-gap trial=" in item for item in recovery_run.evidence)
                or (
                    recovery_branch is not None
                    and recovery_branch.source == "recovery_probe"
                    and recovery_branch.recommendation == "hold"
                    and any(
                        "selected by floor-gap-first recovery probe" in item
                        for item in recovery_branch.evidence
                    )
                    and replay_task is not None
                    and replay_task.candidate_id == "floor-gap-recovery-candidate"
                    and "recover-image-quality-floor" in replay_task.depends_on
                    and remediation_task is not None
                    and remediation_task.candidate_id == "floor-gap-recovery-candidate"
                    and "replay-floor-gap-recovery-candidate" in remediation_task.depends_on
                    and bool(remediation_task.variables)
                    and local_merit_task is not None
                    and local_merit_task.depends_on == ["remediate-recovery-replay-gate"]
                    and replay_run is not None
                    and replay_run.status == "diagnostic"
                    and accepted_floor_gap_replay_selected
                    and replay_run.replay_gate is not None
                    and replay_run.replay_gate.gate_id == "floor-gap-recovery-replay"
                    and replay_run.replay_gate.promotion_allowed is False
                    and bool(replay_run.replay_gate.failed_check_ids)
                    and bool(replay_run.replay_gate.recommended_variables)
                    and bool(replay_run.replay_gate.remediation_actions)
                    and replay_run.next_action.startswith(
                        replay_run.replay_gate.remediation_actions[0]
                    )
                    and "remediate-recovery-replay-gate" in replay_run.unlocked_tasks
                    and remediation_run is not None
                    and remediation_run.status == "diagnostic"
                    and policy_downstream_ready
                    and any(
                        metric.metric == "failed_replay_gate_checks"
                        for metric in remediation_run.metric_updates
                    )
                    and remediation_probe_evidence_ready
                    and any(
                        "bounded search variable priority=" in item
                        for item in remediation_run.evidence
                    )
                    and any("remediation policy=" in item for item in remediation_run.evidence)
                    and bool(policy_action)
                    and remediation_run.next_action.startswith(policy_action)
                    and any(
                        "policy-selected downstream variables=" in item
                        for item in remediation_run.evidence
                    )
                    and any(
                        check.check_id == "floor_gap_cleared" and check.required_for_promotion
                        for check in replay_run.replay_gate.checks
                    )
                    and any(
                        check.check_id == "payload_frozen" and check.status == "pass"
                        for check in replay_run.replay_gate.checks
                    )
                    and any(
                        metric.metric == "recovery_candidate_floor_gap_score"
                        for metric in replay_run.metric_updates
                    )
                )
            )
            run_ready = not lock_passed or (
                recovery_run is not None
                and recovery_run.status in {"warning", "passed", "diagnostic"}
                and any(
                    metric.metric == "image_quality_floor_gap_score"
                    for metric in recovery_run.metric_updates
                )
                and any(
                    metric.metric == "recovery_probe_floor_gap_score"
                    for metric in recovery_run.metric_updates
                )
                and any(
                    metric.metric == "mtf_multiband_floor_gap"
                    for metric in recovery_run.metric_updates
                )
                and any(
                    metric.metric == "max_rms_floor_gap" for metric in recovery_run.metric_updates
                )
                and any("dominant floor gap=" in item for item in recovery_run.evidence)
                and any("targeted recovery variables=" in item for item in recovery_run.evidence)
                and any("floor recovery probe=" in item for item in recovery_run.evidence)
                and any("probe ranking policy=" in item for item in recovery_run.evidence)
                and recovery_trial_branch_ready
            )
            ok = (
                optical_dimension.status == "blocker"
                and readiness.status != "draft_ready"
                and has_floor_evidence
                and task_ready
                and run_ready
            )
            return ok, "low image-quality floor queues/runs recovery after first-order lock"
        ok = optical_dimension.status != "blocker" and has_floor_evidence and recovery_task is None
        return ok, "image-quality floor clears blocker threshold"

    return check


def _has_draft_candidates() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "draft candidates missing because assessment is missing"
        ids = {candidate.candidate_id for candidate in assessment.draft_candidates}
        ok = bool(assessment.draft_candidates) and assessment.recommended_candidate_id in ids
        return ok, f"draft candidates present ({assessment.recommended_candidate_id})"

    return check


def _change_set_matches_optimizer_status() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        attempt = assessment.optimization_attempt if assessment else None
        change_set = assessment.prescription_change_set if assessment else None
        if attempt is None:
            return False, "change set missing because optimizer attempt is missing"
        if attempt.status == "proposal" and attempt.variable_changes:
            ok = change_set is not None and bool(change_set.verification_checklist)
            return ok, "proposal has prescription change set"
        return change_set is None, "non-proposal has no application change set"

    return check


def _has_optimization_task_queue() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "optimization task queue missing because assessment is missing"
        tasks = assessment.optimization_task_queue
        ids = {task.task_id for task in tasks}
        deps_known = all(dep in ids for task in tasks for dep in task.depends_on)
        has_stop_conditions = all(task.stop_condition and task.verification for task in tasks)
        ok = len(tasks) >= 3 and deps_known and has_stop_conditions
        return ok, f"task queue count {len(tasks)} >= 3 with valid dependencies"

    return check


def _has_acceptance_improvement_tasks() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_acceptance_gate is None:
            return False, "acceptance improvement tasks missing because assessment is missing"
        gate = assessment.draft_acceptance_gate
        tasks = assessment.acceptance_improvement_tasks
        if gate.status == "ready_for_review":
            return True, "ready gate does not require acceptance improvement tasks"
        action_ids = {action.action_id for action in gate.upgrade_actions}
        ok = (
            bool(tasks)
            and all(task.source_action_id in action_ids for task in tasks)
            and all(task.priority >= 1 for task in tasks)
            and all(task.objective and task.exit_criteria for task in tasks)
            and all(task.required_inputs and task.validation_steps for task in tasks)
            and all(
                task.status in {"ready", "queued", "blocked", "external_evidence_required"}
                for task in tasks
            )
        )
        return ok, f"acceptance improvement task count {len(tasks)}"

    return check


def _image_quality_floor_task_has_evidence_probe() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "image-quality floor task probe missing assessment"
        tasks = [
            task
            for task in assessment.acceptance_improvement_tasks
            if task.source_action_id.startswith("image_quality_floor")
        ]
        if not tasks:
            return True, "no image-quality floor acceptance task required"
        probes = [task.evidence_probe for task in tasks]
        ok = all(
            probe is not None
            and probe.probe_id == "image-quality-floor-gap"
            and probe.status in {"gap", "satisfied"}
            and any("normalized floor gap=" in item for item in probe.known_evidence)
            and any("review floor" in item for item in probe.known_evidence)
            and any("dominant floor gap=" in item for item in probe.known_evidence)
            and any("multiband min MTF" in item for item in probe.missing_evidence)
            and any("field-weighted MTF" in item for item in probe.missing_evidence)
            and any("max RMS spot radius" in item for item in probe.missing_evidence)
            and probe.next_probe_command is not None
            and "evaluate_design_agent.py --fail-on-regression --json" in probe.next_probe_command
            for probe in probes
        )
        statuses = [probe.status if probe is not None else "missing" for probe in probes]
        return ok, f"image-quality floor probes {statuses}"

    return check


def _has_optimization_task_runs() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None:
            return False, "optimization task runs missing because assessment is missing"
        tasks = assessment.optimization_task_queue
        runs = assessment.optimization_task_runs
        task_ids = {task.task_id for task in tasks}
        ready_task = next((task for task in tasks if task.status == "ready"), None)
        ids_known = all(run.task_id in task_ids for run in runs)
        unlocked_known = all(
            unlocked in task_ids for run in runs for unlocked in run.unlocked_tasks
        )
        statuses_known = all(run.status in {"passed", "warning", "diagnostic"} for run in runs)
        has_contract = all(run.summary and run.next_action and run.evidence for run in runs)
        first_run_matches_ready = bool(
            ready_task is None or (runs and runs[0].task_id == ready_task.task_id)
        )
        sequential_runs = all(
            runs[index].task_id in runs[index - 1].unlocked_tasks for index in range(1, len(runs))
        )
        passed_apply_reaches_merit = True
        if runs and runs[0].task_id == "apply-protected-change-set" and runs[0].status == "passed":
            passed_apply_reaches_merit = any(run.task_id == "local-merit-tuning" for run in runs)
        ok = (
            bool(runs)
            and ids_known
            and unlocked_known
            and statuses_known
            and has_contract
            and first_run_matches_ready
            and sequential_runs
            and passed_apply_reaches_merit
        )
        return ok, f"task run count {len(runs)} with valid task linkage"

    return check


def _has_draft_quality_rubric() -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_quality_rubric is None:
            return False, "draft quality rubric missing"
        rubric = assessment.draft_quality_rubric
        dimension_ids = {dimension.dimension_id for dimension in rubric.dimensions}
        required_ids = {
            "requirement_fit",
            "optical_evidence",
            "manufacturability",
            "workflow_closure",
            "claim_safety",
        }
        scores_valid = 0.0 <= rubric.score <= 1.0 and all(
            0.0 <= dimension.score <= 1.0 for dimension in rubric.dimensions
        )
        statuses_valid = all(
            dimension.status in {"pass", "warning", "blocker"} and dimension.evidence
            for dimension in rubric.dimensions
        )
        gate = assessment.draft_acceptance_gate
        level_matches_gate = (
            gate is None
            or (gate.status == "ready_for_review" and rubric.level in {"reviewable", "blocked"})
            or (gate.status == "conditional" and rubric.level in {"conditional", "blocked"})
            or (gate.status == "blocked" and rubric.level == "blocked")
        )
        closeout_valid = bool(rubric.promotion_target) and (
            rubric.level == "reviewable"
            or (
                rubric.weakest_dimension_id in dimension_ids
                and bool(rubric.minimum_next_action)
                and bool(rubric.promotion_actions)
            )
        )
        ok = (
            rubric.level in {"reviewable", "conditional", "blocked"}
            and required_ids.issubset(dimension_ids)
            and scores_valid
            and statuses_valid
            and bool(rubric.summary)
            and level_matches_gate
            and closeout_valid
        )
        return ok, f"draft quality {rubric.level} score={rubric.score:.3f}"

    return check


def _draft_quality_target(
    *,
    level: str,
    min_score: float,
    acceptance_status: str,
    closeout_fragment: str | None = None,
) -> Check:
    def check(sample: OpticalSampleData) -> tuple[bool, str]:
        assessment = sample.design_assessment
        if assessment is None or assessment.draft_quality_rubric is None:
            return False, "draft quality target missing assessment or rubric"
        if assessment.draft_acceptance_gate is None:
            return False, "draft quality target missing acceptance gate"
        rubric = assessment.draft_quality_rubric
        gate = assessment.draft_acceptance_gate
        level_ok = rubric.level == level
        score_ok = rubric.score >= min_score
        acceptance_ok = gate.status == acceptance_status
        if level == "reviewable":
            closeout_ok = rubric.minimum_next_action is None and not rubric.promotion_actions
        else:
            closeout_ok = bool(rubric.minimum_next_action) and bool(rubric.promotion_actions)
        if closeout_fragment is not None:
            closeout_ok = closeout_ok and closeout_fragment in (rubric.minimum_next_action or "")
        ok = level_ok and score_ok and acceptance_ok and closeout_ok
        return (
            ok,
            (
                "quality target "
                f"level={rubric.level}/{level}, "
                f"score={rubric.score:.3f}>={min_score:.2f}, "
                f"acceptance={gate.status}/{acceptance_status}, "
                f"closeout={rubric.minimum_next_action or 'none'}"
            ),
        )

    return check


_DESIGNER_PACKET_CHECKS: tuple[Check, ...] = (
    _candidate_count_at_least(3),
    _candidate_review_proxy_present(),
    _candidate_roles_unique(),
    _next_steps_at_least(3),
    _next_step_mentions("Candidate proxy check"),
    _has_requirement_coverage(),
    _has_seed_selection_scorecard(),
    _has_designer_readiness_rubric(),
    _has_manufacturability_review(),
    _has_draft_acceptance_gate(),
    _has_candidate_proxy_acceptance_evidence(),
    _has_design_intent_contract(),
    _has_readiness(),
    _risk_count_at_least(1),
    _optimization_plan_at_least(3),
    _has_optimizer_attempt(),
    _optimizer_gate_is_honest(),
    _optimizer_metrics_present(),
    _optimizer_metrics_consistent(),
    _has_merit_probe(),
    _has_structured_variable_candidates(),
    _merit_probe_selection_prefers_accepted_trial(),
    _merit_probe_proposal_has_quality_gate(),
    _image_quality_floor_gates_low_mtf(),
    _has_draft_candidates(),
    _change_set_matches_optimizer_status(),
    _has_acceptance_improvement_tasks(),
    _image_quality_floor_task_has_evidence_probe(),
    _has_optimization_task_queue(),
    _has_optimization_task_runs(),
    _has_draft_quality_rubric(),
    _has_reference_influence_audit(),
    _has_manufacturing_sensitivity_audit(),
    _has_tolerance_sensitivity_audit(),
    _has_manufacturing_clearance_checklist(),
    _has_evidence_closeout_plan(),
    _has_design_handoff_packet(),
    _has_design_traceability_manifest(),
    _has_design_constraint_ledger(),
)


EVAL_CASES: tuple[EvalCase, ...] = (
    EvalCase(
        name="balanced_main_default",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 3.0,
            "fnum": 2.0,
            "fov_deg": 78.0,
            "image_height_mm": 2.3,
            "n_elements": 5,
            "priority": "balanced",
        },
        checks=(
            _score_at_least(0.80),
            _assessment_has_rationale("image height"),
            _candidate_role_present("cost_variant"),
            _balanced_floor_aware_seed_selected(),
            _has_fov_spec_consistency_diagnostic(),
            _has_fov_spec_reconciliation_branch(),
            _mtf_first_recovery_precedes_spec_reconciliation(),
            _spec_repair_rerun_contract_is_idempotent(),
            _has_fov_alternative_resolution(),
            _reference_influence_status("constrained"),
            _manufacturing_sensitivity_status(
                {"watch", "risk"},
                required_factor_id="tolerance_risk_proxy",
                evidence_fragment="tolerance",
            ),
            _evidence_closeout_status(
                "production_evidence_required",
                source_fragment="draft_quality_rubric",
                evidence_fragment="full-field recovery replay gate",
                blocks_review=False,
            ),
            _design_handoff_status(
                "conditional",
                candidate_id="seed-baseline",
                payload_fragment="unchanged selected real seed",
            ),
            _constraint_ledger_status(
                "needs_review",
                variable_id="protected_change_set",
                variable_status="guarded",
            ),
            _draft_quality_target(
                level="conditional",
                min_score=0.70,
                acceptance_status="conditional",
                closeout_fragment="full-field recovery replay gate",
            ),
            _designer_readiness_target("conditional", 0.60),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="high_fov_main_uses_89deg_seed",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 2.8,
            "fnum": 1.9,
            "fov_deg": 88.0,
            "image_height_mm": 2.9,
            "n_elements": 5,
            "priority": "performance",
        },
        checks=(
            _score_at_least(0.80),
            _scenario_is(Scenario.SMARTPHONE_ULTRAWIDE),
            _fov_at_least(89.0),
            _next_step_mentions("full-field"),
            _risk_mentions("MTF"),
            _partial_field_merit_probe_has_trials(),
            _full_field_recovery_diagnostic_present(),
            _library_coverage_gap_present(),
            _reference_influence_status(
                "constrained",
                data_gap_fragment="no high-FOV visible-light seed",
            ),
            _manufacturing_sensitivity_status(
                {"watch", "risk"},
                required_factor_id="guarded_asphere_coefficients",
                evidence_fragment="asphere",
            ),
            _tolerance_sensitivity_status(
                "risk",
                dominant_item_id="field-coverage-sensitivity",
            ),
            _evidence_closeout_status(
                "blocked",
                source_fragment="delivery_gate",
                evidence_fragment="1.0 field",
                blocks_review=True,
            ),
            _design_handoff_status(
                "blocked",
                candidate_id="seed-baseline",
                payload_fragment="unchanged selected real seed",
            ),
            _constraint_ledger_status(
                "blocked",
                variable_id="full_field_recovery",
                variable_status="blocked",
            ),
            _design_strategy_decision_selects_seed_acquisition(),
            _has_high_fov_seed_acquisition_branch(),
            _selected_partial_branch_uses_085_seed(),
            _stable_sibling_review_is_not_queued(),
            _has_near_threshold_partial_field_branch(),
            _has_partial_field_high_fov_branch(),
            _has_relaxed_fov_full_field_branch(),
            _high_fov_seed_baseline_maps_partial_strategy(),
            _has_branch_selection_policy(),
            _has_strategy_tradeoff_matrix(),
            _high_fov_mtf_coverage_is_tradeoff(),
            _high_fov_acceptance_is_conditional(),
            _high_fov_has_seed_intake_audit(),
            _high_fov_has_seed_acquisition_contract(),
            _high_fov_has_seed_ingestion_task(),
            _draft_quality_target(
                level="blocked",
                min_score=0.60,
                acceptance_status="blocked",
                closeout_fragment="1.0 field",
            ),
            _designer_readiness_target("blocked", 0.45),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="ui_high_fov_default_request_stays_blocked",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 3.0,
            "fnum": 2.0,
            "fov_deg": 88.0,
            "image_height_mm": 2.3,
            "n_elements": 5,
            "priority": "balanced",
        },
        checks=(
            _score_at_least(0.78),
            _scenario_is(Scenario.SMARTPHONE_ULTRAWIDE),
            _case_contains("TTL4.33"),
            _fov_at_least(89.0),
            _next_step_mentions("full-field"),
            _risk_mentions("MTF"),
            _partial_field_merit_probe_has_trials(),
            _library_coverage_gap_present(),
            _design_handoff_status("blocked", candidate_id="seed-baseline"),
            _constraint_ledger_status(
                "blocked",
                variable_id="full_field_recovery",
                variable_status="blocked",
            ),
            _has_high_fov_seed_acquisition_branch(),
            _has_near_threshold_partial_field_branch(),
            _has_relaxed_fov_full_field_branch(),
            _high_fov_seed_baseline_maps_partial_strategy(),
            _high_fov_has_seed_intake_audit(),
            _high_fov_has_seed_acquisition_contract(),
            _high_fov_has_seed_ingestion_task(),
            _draft_quality_target(
                level="blocked",
                min_score=0.50,
                acceptance_status="blocked",
                closeout_fragment="1.0 field",
            ),
            _designer_readiness_target("blocked", 0.40),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="relaxed_full_field_fallback_blocks_low_mtf",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 3.8059,
            "fnum": 2.05,
            "fov_deg": 78.8,
            "image_height_mm": 3.2,
            "n_elements": 5,
        },
        checks=(
            _score_at_least(0.70),
            _scenario_is(Scenario.SMARTPHONE_WIDE),
            _case_contains("FOV78.8_EFL3.8_IMH3.2"),
            _seed_baseline_hold_blocked_on_quality_floor_with_review_notes(),
            _seed_baseline_queue_starts_with_review_package(),
            _manufacturing_sensitivity_status(
                {"watch", "risk"},
                required_factor_id="tolerance_risk_proxy",
                evidence_fragment="tolerance",
            ),
            _tolerance_sensitivity_status(
                "risk",
                dominant_item_id="minimum-air-gap",
            ),
            _evidence_closeout_status(
                "blocked",
                source_fragment="draft_quality_rubric",
                evidence_fragment="MTF/RMS",
                blocks_review=True,
            ),
            _design_handoff_status(
                "blocked",
                candidate_id="seed-baseline",
                payload_fragment="unchanged selected real seed",
            ),
            _constraint_ledger_status(
                "blocked",
                variable_id="seed_payload",
                variable_status="frozen",
            ),
            _draft_quality_target(
                level="blocked",
                min_score=0.70,
                acceptance_status="blocked",
                closeout_fragment="MTF/RMS",
            ),
            _designer_readiness_target("blocked", 0.40),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="thin_module_respects_ttl",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 2.6,
            "fnum": 2.2,
            "fov_deg": 67.8,
            "image_height_mm": 1.8,
            "n_elements": 4,
            "max_total_track_mm": 3.4,
            "priority": "cost",
            "manufacturing_tier": "consumer",
        },
        checks=(
            _score_at_least(0.90),
            _ttl_at_most(3.4),
            _case_contains("TTL3.30"),
            _next_step_mentions("TTL"),
            _manufacturing_tier_is_scored(),
            _cost_priority_resolves_low_risk_candidate_branch(),
            _draft_quality_target(
                level="reviewable",
                min_score=0.80,
                acceptance_status="ready_for_review",
            ),
            _designer_readiness_target("draft_ready", 0.78),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="big_sensor_prefers_large_image_height_seed",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 3.8,
            "fnum": 2.0,
            "fov_deg": 78.8,
            "image_height_mm": 3.3,
            "n_elements": 5,
            "priority": "balanced",
        },
        checks=(
            _score_at_least(0.70),
            _case_contains("IMH3.3"),
            _proposal_conditional_with_review_notes(),
            _big_sensor_rejects_low_risk_target_miss(),
            _draft_quality_target(
                level="blocked",
                min_score=0.70,
                acceptance_status="blocked",
                closeout_fragment="MTF/RMS",
            ),
            _designer_readiness_target("blocked", 0.50),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="low_cost_accepts_three_piece_seed",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 2.75,
            "fnum": 2.45,
            "fov_deg": 78.0,
            "image_height_mm": 2.3,
            "n_elements": 3,
            "max_weight_g": 0.05,
            "priority": "cost",
            "manufacturing_tier": "consumer",
        },
        checks=(
            _score_at_least(0.90),
            _n_pieces_at_most(3),
            _next_step_mentions("cost-control"),
            _manufacturing_tier_is_scored(),
            _mass_budget_is_scored(),
            _seed_baseline_hold_ready_for_review(),
            _seed_baseline_queue_starts_with_review_package(),
            _manufacturing_sensitivity_status(
                "clear",
                required_factor_id="tolerance_risk_proxy",
            ),
            _evidence_closeout_status(
                "production_evidence_required",
                source_fragment="production_claim_safety",
                evidence_fragment="production claims",
                blocks_review=False,
            ),
            _design_handoff_status(
                "ready_for_review",
                candidate_id="seed-baseline",
                payload_fragment="unchanged selected real seed",
            ),
            _constraint_ledger_status(
                "ready_for_review",
                variable_id="seed_payload",
                variable_status="frozen",
            ),
            _draft_quality_target(
                level="reviewable",
                min_score=0.95,
                acceptance_status="ready_for_review",
            ),
            _designer_readiness_target("draft_ready", 0.84),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
    EvalCase(
        name="performance_full_field_seed_blocks_low_mtf",
        request={
            "scenario": Scenario.SMARTPHONE_WIDE,
            "efl_mm": 2.9,
            "fnum": 1.8,
            "fov_deg": 74.1,
            "image_height_mm": 2.3,
            "n_elements": 5,
            "priority": "performance",
            "manufacturing_tier": "premium",
        },
        checks=(
            _score_at_least(0.75),
            _case_contains("4P_F2.2_FOV74.7"),
            _next_step_mentions("Benchmark"),
            _floor_aware_performance_seed_selected(),
            _full_field_recovery_replay_passes(),
            _performance_recovery_branch_policy_present(),
            _performance_tradeoff_policy_present(),
            _manufacturing_tier_is_scored(),
            _draft_quality_target(
                level="conditional",
                min_score=0.76,
                acceptance_status="conditional",
                closeout_fragment="F-number / element-count waiver",
            ),
            _designer_readiness_target("conditional", 0.62),
            *_DESIGNER_PACKET_CHECKS,
        ),
    ),
)


EvalRow = tuple[EvalCase, OpticalSampleData | None, list[str]]


def evaluate(case_names: set[str] | None = None) -> list[EvalRow]:
    rows: list[tuple[EvalCase, OpticalSampleData | None, list[str]]] = []
    for item in EVAL_CASES:
        if case_names is not None and item.name not in case_names:
            continue
        sample = match_case(**item.request)
        failures: list[str] = []
        if sample is None:
            rows.append((item, None, ["no case returned"]))
            continue
        if sample.design_assessment is None:
            failures.append("missing design_assessment")
        for check in item.checks:
            ok, label = check(sample)
            if not ok:
                failures.append(label)
        rows.append((item, sample, failures))
    return rows


def _task_packet(task: Any) -> dict[str, Any]:
    probe = task.evidence_probe
    return {
        "task_id": task.task_id,
        "source_action_id": task.source_action_id,
        "priority": task.priority,
        "status": task.status,
        "stage": task.stage,
        "owner": task.owner,
        "objective": task.objective,
        "evidence_probe": probe.model_dump(mode="json") if probe is not None else None,
    }


def _row_packet(
    item: EvalCase, sample: OpticalSampleData | None, failures: list[str]
) -> dict[str, Any]:
    if sample is None:
        return {
            "eval_case": item.name,
            "passed": False,
            "failures": failures,
            "matched_case_id": None,
        }

    assessment = sample.design_assessment
    readiness = assessment.designer_readiness_rubric if assessment else None
    acceptance = assessment.draft_acceptance_gate if assessment else None
    return {
        "eval_case": item.name,
        "passed": not failures,
        "failures": failures,
        "matched_case_id": sample.metadata.case_id if sample.metadata else None,
        "score": assessment.score if assessment else None,
        "recommended_candidate_id": (assessment.recommended_candidate_id if assessment else None),
        "designer_readiness": (
            {
                "status": readiness.status,
                "score": readiness.score,
                "weakest_dimension_id": readiness.weakest_dimension_id,
                "blocker_count": len(readiness.blockers),
            }
            if readiness is not None
            else None
        ),
        "acceptance": (
            {
                "status": acceptance.status,
                "score": acceptance.score,
                "candidate_id": acceptance.candidate_id,
                "upgrade_count": len(acceptance.upgrade_actions),
                "review_note_count": len(acceptance.review_notes),
            }
            if acceptance is not None
            else None
        ),
        "acceptance_improvement_tasks": [
            _task_packet(task)
            for task in (assessment.acceptance_improvement_tasks if assessment else [])
        ],
        "warnings": assessment.warnings if assessment else [],
    }


def build_json_report(rows: list[EvalRow]) -> dict[str, Any]:
    failed = sum(1 for _, _, failures in rows if failures)
    return {
        "summary": {
            "case_count": len(rows),
            "passed_count": len(rows) - failed,
            "failed_count": failed,
            "all_passed": failed == 0,
        },
        "cases": [_row_packet(item, sample, failures) for item, sample, failures in rows],
    }


def _validate_case_names(case_names: set[str] | None) -> list[str]:
    if case_names is None:
        return []
    known = {item.name for item in EVAL_CASES}
    return sorted(case_names - known)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Only evaluate one named fixed eval case; may be passed more than once",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args(argv)

    case_names = set(args.cases) if args.cases else None
    unknown_cases = _validate_case_names(case_names)
    if unknown_cases:
        print(f"unknown eval case(s): {', '.join(unknown_cases)}", file=sys.stderr)
        return 2

    rows = evaluate(case_names=case_names)
    if args.json:
        print(json.dumps(build_json_report(rows), ensure_ascii=False, indent=2))
        failed = sum(1 for _, _, failures in rows if failures)
        return 1 if failed and args.fail_on_regression else 0

    print("Lumira Atelier design-agent regression set")
    print("=" * 72)
    for item, sample, failures in rows:
        if sample is None:
            print(f"FAIL {item.name:42} no case")
            continue
        meta = sample.metadata
        assessment = sample.design_assessment
        status = "FAIL" if failures else "PASS"
        print(
            f"{status} {item.name:42} -> {meta.case_id:42} "
            f"score={assessment.score:.3f} "
            f"dEFL={assessment.delta_efl_mm:+.2f} "
            f"dF#={assessment.delta_f_number:+.2f} "
            f"dFOV={assessment.delta_fov_deg:+.1f}"
        )
        roles = ", ".join(c.role for c in assessment.candidate_comparison)
        print(f"     candidates: {roles}")
        if assessment.requirement_coverage_summary is not None:
            coverage = assessment.requirement_coverage_summary
            print(
                "     requirements: "
                f"{coverage.status}, met={coverage.met_count}, "
                f"tradeoff={coverage.tradeoff_count}, miss={coverage.miss_count}, "
                f"unscored={coverage.unscored_count}"
            )
        if assessment.seed_selection_scorecard is not None:
            scorecard = assessment.seed_selection_scorecard
            print(
                "     selection: "
                f"score={scorecard.selected_score:.3f}, "
                f"distance={scorecard.normalized_distance:.3f}, "
                f"top={scorecard.top_penalty_metric_id or 'none'}"
            )
        if assessment.manufacturability_review is not None:
            review = assessment.manufacturability_review
            print(
                "     manufacturability: "
                f"{review.status}, tier={review.tier}, score={review.score:.2f}"
            )
        if assessment.design_intent_contract is not None:
            contract = assessment.design_intent_contract
            print(
                "     intent: "
                f"{contract.status}, hard={len(contract.hard_constraints)}, "
                f"soft={len(contract.soft_preferences)}, "
                f"conflicts={len(contract.conflict_flags)}"
            )
        if assessment.designer_readiness_rubric is not None:
            rubric = assessment.designer_readiness_rubric
            print(
                "     designer readiness: "
                f"{rubric.status}, score={rubric.score:.2f}, "
                f"weakest={rubric.weakest_dimension_id}, "
                f"blockers={len(rubric.blockers)}"
            )
        if assessment.optimization_attempt is not None:
            gate = assessment.optimization_attempt.verification
            gate_label = f", gate={gate.status}" if gate is not None else ""
            print(f"     optimizer: {assessment.optimization_attempt.status}{gate_label}")
        if assessment.recommended_candidate_id:
            print(f"     recommended: {assessment.recommended_candidate_id}")
        if assessment.merit_optimization_probe is not None:
            probe = assessment.merit_optimization_probe
            improvement = (
                f", rms_improvement={probe.rms_improvement_um:.2f}um"
                if probe.rms_improvement_um is not None
                else ""
            )
            print(f"     merit probe: {probe.status}{improvement}")
        if assessment.full_field_recovery_diagnostic is not None:
            diagnostic = assessment.full_field_recovery_diagnostic
            best_trial = diagnostic.best_recovery_trial
            best_trial_label = (
                f", best={best_trial.variable_family}/S{best_trial.surface_index}"
                f"/{best_trial.status}"
                if best_trial is not None
                else ""
            )
            edge_cliff_label = (
                f", edge_cliff={diagnostic.edge_field_cliff_frac}"
                if diagnostic.edge_field_cliff_frac is not None
                else ""
            )
            print(
                "     full-field diagnostic: "
                f"{diagnostic.failure_mode}, "
                f"field={diagnostic.current_field_frac}, "
                f"next={diagnostic.recommended_variable_family}"
                f"{best_trial_label}"
                f"{edge_cliff_label}"
            )
        if assessment.library_coverage_diagnostic is not None:
            diagnostic = assessment.library_coverage_diagnostic
            print(
                "     library coverage: "
                f"{diagnostic.status}, "
                f"nearest_full={diagnostic.nearest_full_field_fov_deg}, "
                f"gap={diagnostic.full_field_fov_gap_deg}"
            )
        if assessment.reference_influence_audit is not None:
            audit = assessment.reference_influence_audit
            print(
                "     reference influence: "
                f"{audit.status}, confidence={audit.confidence:.2f}, "
                f"gaps={len(audit.data_gaps)}, rejected={len(audit.rejected_reference_ids)}"
            )
        if assessment.manufacturing_sensitivity_audit is not None:
            audit = assessment.manufacturing_sensitivity_audit
            print(
                "     manufacturing sensitivity: "
                f"{audit.status}, confidence={audit.confidence:.2f}, "
                f"dominant={audit.dominant_factor_id or 'none'}"
            )
        if assessment.tolerance_sensitivity_audit is not None:
            audit = assessment.tolerance_sensitivity_audit
            print(
                "     first-order tolerance: "
                f"{audit.status}, confidence={audit.confidence:.2f}, "
                f"dominant={audit.dominant_item_id or 'none'}"
            )
        if assessment.manufacturing_clearance_checklist is not None:
            checklist = assessment.manufacturing_clearance_checklist
            print(
                "     manufacturing clearance: "
                f"{checklist.status}, items={len(checklist.items)}, "
                f"production_blockers={checklist.production_blocking_count}, "
                f"dominant={checklist.dominant_item_id or 'none'}"
            )
        if assessment.evidence_closeout_plan is not None:
            plan = assessment.evidence_closeout_plan
            print(
                "     evidence closeout: "
                f"{plan.status}, items={len(plan.items)}, "
                f"review_blockers={plan.review_blocking_count}, "
                f"production_blockers={plan.production_blocking_count}"
            )
        if assessment.design_handoff_packet is not None:
            handoff = assessment.design_handoff_packet
            print(
                "     handoff: "
                f"{handoff.status}, candidate={handoff.candidate_id}, "
                f"metrics={len(handoff.headline_metrics)}"
            )
        if assessment.design_traceability_manifest is not None:
            manifest = assessment.design_traceability_manifest
            print(
                "     traceability: "
                f"{manifest.status}, source={manifest.source_case_id}, "
                f"candidate={manifest.delivered_candidate_id}, "
                f"replay={len(manifest.replay_commands)}"
            )
        if assessment.design_constraint_ledger is not None:
            ledger = assessment.design_constraint_ledger
            print(
                "     constraints: "
                f"{ledger.status}, locked={ledger.locked_count}, "
                f"tradeoffs={ledger.accepted_tradeoff_count}, "
                f"unresolved={ledger.unresolved_count}, "
                f"variables={len(ledger.variables)}"
            )
        if assessment.seed_intake_audit is not None:
            audit = assessment.seed_intake_audit
            print(
                "     seed intake: "
                f"{audit.status}, accepted={audit.accepted_seed_count}, "
                f"high_fov={audit.high_fov_seed_count}, "
                f"full_field={audit.full_field_seed_count}"
            )
        if assessment.seed_acquisition_contract is not None:
            contract = assessment.seed_acquisition_contract
            print(
                "     seed acquisition: "
                f"{contract.status}, target={contract.acceptance_target}, "
                f"fallbacks={len(contract.fallback_paths)}"
            )
        if assessment.design_strategy_decision is not None:
            decision = assessment.design_strategy_decision
            print(
                "     strategy decision: "
                f"{decision.selected_strategy}, "
                f"fallbacks={','.join(decision.fallback_strategies)}"
            )
            for option in decision.options[:3]:
                print(
                    "       option: "
                    f"{option.option_id}, "
                    f"candidate={option.candidate_id or 'new-seed'}, "
                    f"fov={option.fov_deg}, "
                    f"field={option.mtf_max_field_frac}"
                )
            if decision.seed_acquisition_brief is not None:
                brief = decision.seed_acquisition_brief
                print(
                    "       seed brief: "
                    f"FOV>={brief.minimum_fov_deg}, "
                    f"EFL={brief.efl_window_mm}, "
                    f"F#={brief.f_number_window}, "
                    f"field={brief.required_mtf_field_frac}"
                )
        if assessment.delivery_gate is not None:
            gate = assessment.delivery_gate
            print(f"     delivery gate: {gate.status}, {gate.deliverable_type}")
        if assessment.draft_quality_rubric is not None:
            rubric = assessment.draft_quality_rubric
            closeout = (
                f", weakest={rubric.weakest_dimension_id}, next={rubric.minimum_next_action}"
                if rubric.minimum_next_action
                else ""
            )
            print(f"     quality: {rubric.level}, score={rubric.score:.2f}{closeout}")
        if assessment.draft_acceptance_gate is not None:
            gate = assessment.draft_acceptance_gate
            print(
                "     acceptance: "
                f"{gate.status}, candidate={gate.candidate_id}, score={gate.score:.2f}"
            )
            if gate.upgrade_actions:
                action = gate.upgrade_actions[0]
                print(
                    f"       upgrade: P{action.priority} {action.source_check_id}: {action.action}"
                )
            if gate.review_notes:
                print(f"       review note: {gate.review_notes[0]}")
        if assessment.acceptance_improvement_tasks:
            task = assessment.acceptance_improvement_tasks[0]
            probe = f"/{task.evidence_probe.status}" if task.evidence_probe is not None else ""
            print(
                "       acceptance task: "
                f"P{task.priority} {task.task_id}/{task.status}/{task.stage}{probe}"
            )
        if assessment.optimization_task_queue:
            first_task = assessment.optimization_task_queue[0]
            print(f"     first task: {first_task.task_id}/{first_task.status}")
        if assessment.optimization_task_runs:
            first_run = assessment.optimization_task_runs[0]
            metric_labels = ", ".join(
                f"{metric.metric}={metric.direction}" for metric in first_run.metric_updates[:2]
            )
            suffix = f" ({metric_labels})" if metric_labels else ""
            print(f"     first run: {first_run.task_id}/{first_run.status}{suffix}")
            if len(assessment.optimization_task_runs) > 1:
                latest_run = assessment.optimization_task_runs[-1]
                print(f"     latest run: {latest_run.task_id}/{latest_run.status}")
        for warning in assessment.warnings:
            print(f"     warning: {warning}")
        for failure in failures:
            print(f"     unmet: {failure}")

    failed = sum(1 for _, _, failures in rows if failures)
    print("=" * 72)
    print(f"{len(rows) - failed}/{len(rows)} eval cases passing")
    return 1 if failed and args.fail_on_regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
