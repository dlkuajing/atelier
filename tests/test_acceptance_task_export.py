from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import scripts.export_acceptance_tasks as acceptance_export
from scripts.export_acceptance_tasks import (
    build_report,
    build_runner_summary,
    write_artifacts,
)

_REPORT_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


def _report(**kwargs: Any) -> dict[str, Any]:
    """``build_report`` memoized across tests in this module.

    ``build_report`` forks ``uv run python scripts/evaluate_design_agent.py``
    once per case, and every fork re-imports the whole Optiland/scipy/numpy
    stack before running a full optical evaluation. Two tests here call it with
    *identical* arguments -- ``test_acceptance_export_writes_runner_summary_artifact``
    and ``test_acceptance_export_executes_case_verification_probe``, both
    ``case_names={"high_fov_main_uses_89deg_seed"}`` plus
    ``execute_case_verification=True`` -- so the second one recomputed a report
    the first had already produced.

    Measured on identical serial CI baselines (2026-07-27): those two ran at
    117.67s and 116.52s without the cache (main run 30254095332) and dropped
    off the slowest-25 table entirely (<2s) with it (run 30256323174) --
    about 232s of CPU that was pure duplication.

    Two honest caveats, so nobody over-credits this:

    * ``test_seed_ingestion_export_empty_after_evidence_layer_cleared`` looks
      like a third duplicate but is NOT one: it also passes
      ``stage="seed_ingestion"`` and ``execute_local_probes=True``, so it keys
      differently and still pays full price.
    * End-to-end wall clock did not measurably improve (1782s -> 1842s across
      those two runs). Runner variance dominates: the single slowest test moved
      593s -> 711s (+20%) between the same two runs. The duplication removed
      here is real, but it is smaller than the noise floor.

    Caching is observationally equivalent: ``build_report`` writes no files
    (that is ``write_artifacts``' job) and its result depends only on these
    arguments. Callers get a deep copy, so a test mutating its report cannot
    leak into another.
    """

    case_names = kwargs.get("case_names")
    key = (
        frozenset(case_names) if case_names is not None else None,
        kwargs.get("stage"),
        kwargs.get("execute_local_probes", False),
        kwargs.get("execute_case_verification", False),
        kwargs.get("probe_timeout_s"),
    )
    if key not in _REPORT_CACHE:
        _REPORT_CACHE[key] = build_report(**kwargs)
    return copy.deepcopy(_REPORT_CACHE[key])


def test_acceptance_export_has_no_stale_remediation_resolution_packets():
    report = _report(
        stage="remediation_resolution",
        case_names={"big_sensor_prefers_large_image_height_seed"},
        execute_local_probes=True,
    )

    assert report["summary"]["task_count"] == 0
    assert report["summary"]["executed_probe_count"] == 0
    assert report["summary"]["failed_probe_count"] == 0
    assert report["tasks"] == []


def test_seed_ingestion_export_empty_after_evidence_layer_cleared():
    # E2-01 batch 1: the library now carries real >=85deg full-field(1.0) evidence
    # (US20170003482A1 / US8908290B1), so no eval case emits a seed-ingestion
    # acceptance task -- the external-seed acquisition export is legitimately empty
    # (blocker resolved at the evidence layer, not hidden). Regression guard that
    # the machinery stays dissolved; the seed-task packet/runner logic remains
    # covered by the inline-data tests below.
    report = _report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_local_probes=True,
        execute_case_verification=True,
    )
    assert report["summary"]["task_count"] == 0
    assert report["tasks"] == []
    assert report["summary"]["executed_probe_count"] == 0
    assert report["summary"]["executed_verification_count"] == 0


def test_acceptance_export_writes_artifacts(tmp_path):
    # Covered world: the high-FOV case's follow-ups are internal manual tasks
    # (recover full-field, etc.), not a seed-acquisition probe. Artifact writing is
    # exercised against those real tasks.
    report = _report(
        case_names={"high_fov_main_uses_89deg_seed"},
    )

    artifacts = write_artifacts(report, tmp_path, split_tasks=True)

    report_path = tmp_path / "acceptance_tasks.json"
    assert artifacts["report"] == str(report_path)
    assert report_path.exists()
    saved_report = json.loads(report_path.read_text())
    assert saved_report["summary"]["artifacts"]["report"] == str(report_path)
    assert saved_report["summary"]["task_count"] == 4
    task_paths = saved_report["summary"]["artifacts"]["tasks"]
    assert len(task_paths) == 4
    saved_task = json.loads(Path(task_paths[0]).read_text())
    assert saved_task["task_id"].startswith("resolve-")
    assert (
        "evaluate_design_agent.py --case high_fov_main_uses_89deg_seed"
        in saved_task["case_verification_command"]
    )


def test_acceptance_export_writes_runner_summary_artifact(tmp_path):
    # Covered world: no external seed blocker, so the runner is manual-followup
    # ready rather than blocked on external evidence.
    report = _report(
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_case_verification=True,
    )

    artifacts = write_artifacts(
        report,
        tmp_path,
        split_tasks=True,
        include_runner_summary=True,
    )

    runner_path = tmp_path / "acceptance_runner_summary.json"
    assert artifacts["runner_summary"] == str(runner_path)
    saved_report = json.loads((tmp_path / "acceptance_tasks.json").read_text())
    saved_runner = json.loads(runner_path.read_text())
    assert saved_report["summary"]["artifacts"]["runner_summary"] == str(runner_path)
    assert saved_report["runner_summary"] == saved_runner
    assert saved_runner["summary"]["runner_status"] == "manual_followup_ready"
    assert saved_runner["summary"]["external_blocker_count"] == 0


def test_acceptance_export_executes_case_verification_probe():
    # Covered world: the high-FOV follow-ups are internal manual tasks; case
    # verification runs the eval for the case (which passes) per task.
    report = _report(
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_case_verification=True,
    )

    assert report["summary"]["task_count"] == 4
    assert report["summary"]["executed_verification_count"] == 4
    assert report["summary"]["failed_verification_count"] == 0
    task = report["tasks"][0]
    execution = task["case_verification_execution"]
    assert execution["executed"] is True
    assert execution["timed_out"] is False
    assert execution["exit_code"] == 0
    assert execution["json_parse_error"] is None
    assert execution["stdout_json"]["summary"] == {
        "case_count": 1,
        "passed_count": 1,
        "failed_count": 0,
        "all_passed": True,
    }
    case = execution["stdout_json"]["cases"][0]
    assert case["eval_case"] == "high_fov_main_uses_89deg_seed"
    assert case["acceptance"]["status"] == "blocked"
    assert case["acceptance_improvement_tasks"][0]["stage"] == "requirement_resolution"


def test_acceptance_export_scopes_balanced_followups_to_single_case():
    report = _report(case_names={"balanced_main_default"})

    assert report["tasks"]
    assert {item["eval_case"] for item in report["tasks"]} == {"balanced_main_default"}
    assert not any(
        item["source_action_id"].startswith("image_quality_probe")
        for item in report["tasks"]
    )
    # World-flip from the XASPHERE ingest fix: the balanced default is now blocked
    # on the high-frequency MTF floor, so its single follow-up is the
    # image_quality_floor recovery task (a scoped local replay) rather than a
    # task_run_evidence probe. The follow-up stays scoped to the single case.
    task = next(
        item
        for item in report["tasks"]
        if item["source_action_id"].startswith("image_quality_floor")
    )

    assert task["command_mode"] == "manual"
    assert "balanced_main_default" in task["next_probe_command"]
    assert task["case_verification_command"] == (
        "cd lumira-backend && uv run python "
        "scripts/evaluate_design_agent.py "
        "--case balanced_main_default --json --fail-on-regression"
    )


def test_acceptance_export_reuses_case_verification_per_case(monkeypatch):
    calls = []

    def fake_local_probe_execution(command, *, timeout_s):
        calls.append((command, timeout_s))
        return {
            "executed": True,
            "timed_out": False,
            "exit_code": 0,
            "stdout_json": {
                "summary": {
                    "case_count": 1,
                    "passed_count": 1,
                    "failed_count": 0,
                    "all_passed": True,
                }
            },
            "json_parse_error": None,
        }

    monkeypatch.setattr(
        acceptance_export,
        "_local_probe_execution",
        fake_local_probe_execution,
    )
    high_fov_command = (
        "cd lumira-backend && uv run python scripts/evaluate_design_agent.py "
        "--case high_fov_main_uses_89deg_seed --json --fail-on-regression"
    )
    balanced_command = (
        "cd lumira-backend && uv run python scripts/evaluate_design_agent.py "
        "--case balanced_main_default --json --fail-on-regression"
    )
    tasks = [
        {
            "case_verification_command": high_fov_command,
            "case_verification_command_mode": "local_probe",
        },
        {
            "case_verification_command": high_fov_command,
            "case_verification_command_mode": "local_probe",
        },
        {
            "case_verification_command": balanced_command,
            "case_verification_command_mode": "local_probe",
        },
    ]

    acceptance_export._attach_case_verification_execution(
        tasks,
        execute_case_verification=True,
        probe_timeout_s=7,
    )

    assert calls == [(high_fov_command, 7), (balanced_command, 7)]
    assert tasks[0]["case_verification_execution"] == tasks[1][
        "case_verification_execution"
    ]
    assert tasks[0]["case_verification_execution"] is not tasks[1][
        "case_verification_execution"
    ]


def test_acceptance_runner_keeps_external_blocker_over_same_case_timeout():
    external_task = {
        "eval_case": "high_fov_main_uses_89deg_seed",
        "task_id": "ingest-high-fov-full-field-seed",
        "priority": 1,
        "stage": "seed_ingestion",
        "owner": "case_library",
        "status": "external_evidence_required",
        "execution_state": "waiting_for_external_evidence",
        "objective": "ingest a full-field seed",
        "required_inputs": ["visible-light high-FOV full-field seed"],
        "blocks_claims": ["full-field edge-performance claim"],
        "command_mode": "local_probe",
        "next_probe_command": "cd lumira-backend && uv run python scripts/audit.py",
        "case_verification_command": "verify high-fov",
        "evidence_probe": {
            "status": "gap",
            "known_evidence": [],
            "missing_evidence": ["MTF evaluates at 1.0 field"],
        },
        "probe_execution": {
            "executed": True,
            "timed_out": False,
            "exit_code": 0,
            "stdout_json": {"status": "gap"},
            "json_parse_error": None,
        },
        "case_verification_execution": {
            "executed": True,
            "timed_out": True,
            "exit_code": None,
            "stdout_json": None,
            "json_parse_error": None,
        },
    }
    downstream_task = {
        "eval_case": "high_fov_main_uses_89deg_seed",
        "task_id": "resolve-image_quality_floor-5",
        "priority": 5,
        "stage": "image_quality_recovery",
        "owner": "optimizer",
        "status": "ready",
        "execution_state": "ready_for_agent_or_designer",
        "objective": "recover image quality floor",
        "required_inputs": [],
        "blocks_claims": ["production-ready optical prescription"],
        "command_mode": "manual",
        "next_probe_command": None,
        "case_verification_command": "verify high-fov",
        "evidence_probe": None,
        "probe_execution": {"executed": False, "reason": "not_requested"},
        "case_verification_execution": {
            "executed": True,
            "timed_out": True,
            "exit_code": None,
            "stdout_json": None,
            "json_parse_error": None,
        },
    }

    runner = build_runner_summary({"tasks": [downstream_task, external_task]})

    assert runner["summary"]["runner_status"] == "blocked_on_external_evidence"
    assert runner["summary"]["action_kinds"] == {
        "blocked_by_upstream_evidence": 1,
        "external_evidence_gap": 1,
    }
    blocked = runner["next_actions"][1]
    assert blocked["task_id"] == "resolve-image_quality_floor-5"
    assert blocked["original_action_kind"] == "case_verification_failed"
    assert blocked["blocked_by"]["task_id"] == "ingest-high-fov-full-field-seed"


def test_acceptance_runner_status_prefers_external_blocker_over_verification_noise():
    external_task = {
        "eval_case": "high_fov_main_uses_89deg_seed",
        "task_id": "ingest-high-fov-full-field-seed",
        "priority": 1,
        "stage": "seed_ingestion",
        "owner": "case_library",
        "status": "external_evidence_required",
        "execution_state": "waiting_for_external_evidence",
        "objective": "ingest a full-field seed",
        "required_inputs": [],
        "blocks_claims": [],
        "command_mode": "local_probe",
        "next_probe_command": "seed probe",
        "case_verification_command": "verify high-fov",
        "evidence_probe": {"status": "gap"},
        "probe_execution": {
            "executed": True,
            "timed_out": False,
            "exit_code": 0,
            "stdout_json": {"status": "gap"},
            "json_parse_error": None,
        },
        "case_verification_execution": {"executed": False, "reason": "not_requested"},
    }
    unrelated_failure = {
        "eval_case": "balanced_main_default",
        "task_id": "resolve-image_quality_floor-1",
        "priority": 5,
        "stage": "image_quality_recovery",
        "owner": "optimizer",
        "status": "ready",
        "execution_state": "ready_for_agent_or_designer",
        "objective": "recover image quality floor",
        "required_inputs": [],
        "blocks_claims": [],
        "command_mode": "manual",
        "next_probe_command": None,
        "case_verification_command": "verify balanced",
        "evidence_probe": None,
        "probe_execution": {"executed": False, "reason": "not_requested"},
        "case_verification_execution": {
            "executed": True,
            "timed_out": True,
            "exit_code": None,
            "stdout_json": None,
            "json_parse_error": None,
        },
    }

    runner = build_runner_summary({"tasks": [unrelated_failure, external_task]})

    assert runner["summary"]["runner_status"] == "blocked_on_external_evidence"
    assert runner["summary"]["case_verification_failure_count"] == 1
    assert runner["summary"]["external_blocker_count"] == 1


def test_acceptance_runner_summary_has_no_external_seed_gap_after_evidence_cleared():
    # E2-01 batch 1: the seed-acquisition blocker is resolved at the evidence
    # layer, so the high-FOV case's runner is manual-followup ready -- there is no
    # external-evidence gap to prioritize. The runner's external-gap and
    # upstream-blocking logic stays covered by the inline-data tests below.
    report = _report(
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_case_verification=True,
    )

    runner = build_runner_summary(report)

    assert runner["summary"]["runner_status"] == "manual_followup_ready"
    assert runner["summary"]["external_blocker_count"] == 0
    assert runner["summary"]["upstream_blocked_count"] == 0
    assert runner["summary"]["action_kinds"] == {"manual_followup": 4}
    assert runner["summary"]["top_action_kind"] == "manual_followup"
    assert all(
        action["action_kind"] == "manual_followup" for action in runner["next_actions"]
    )


def test_acceptance_runner_has_no_upstream_seed_blocking_after_evidence_cleared():
    # E2-01 batch 1: with the seed-acquisition blocker resolved at the evidence
    # layer, no external-evidence task exists, so no case's downstream tasks are
    # blocked on an upstream seed gap. The runner's external-gap / upstream-
    # blocking logic stays covered by the inline-data tests above.
    report = _report(
        case_names={
            "high_fov_main_uses_89deg_seed",
            "ui_high_fov_default_request_stays_blocked",
            "balanced_main_default",
            "performance_full_field_seed_blocks_low_mtf",
        },
        execute_case_verification=True,
    )

    runner = build_runner_summary(report)

    assert runner["summary"]["external_blocker_count"] == 0
    assert runner["summary"]["upstream_blocked_count"] == 0
    assert runner["summary"]["task_count"] > 0
    assert not any(
        action["action_kind"] == "blocked_by_upstream_evidence"
        for action in runner["next_actions"]
    )
    assert all(action.get("blocked_by") is None for action in runner["next_actions"])
