from __future__ import annotations

import json

import scripts.export_acceptance_tasks as acceptance_export
from scripts.export_acceptance_tasks import (
    build_report,
    build_runner_summary,
    write_artifacts,
)


def test_acceptance_export_has_no_stale_remediation_resolution_packets():
    report = build_report(
        stage="remediation_resolution",
        case_names={"big_sensor_prefers_large_image_height_seed"},
        execute_local_probes=True,
    )

    assert report["summary"]["task_count"] == 0
    assert report["summary"]["executed_probe_count"] == 0
    assert report["summary"]["failed_probe_count"] == 0
    assert report["tasks"] == []


def test_acceptance_export_keeps_seed_intake_probe_runnable():
    report = build_report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
    )

    assert report["summary"]["task_count"] == 1
    task = report["tasks"][0]
    assert task["task_id"] == "ingest-high-fov-full-field-seed"
    assert task["status"] == "external_evidence_required"
    assert task["command_mode"] == "local_probe"
    assert "audit_seed_intake.py" in task["next_probe_command"]
    assert task["case_verification_command"] == (
        "cd lumira-backend && uv run python scripts/evaluate_design_agent.py "
        "--case high_fov_main_uses_89deg_seed --json --fail-on-regression"
    )
    assert task["case_verification_command_mode"] == "local_probe"
    assert task["case_verification_execution"] == {
        "executed": False,
        "reason": "not_requested",
    }
    assert task["evidence_probe"]["probe_id"] == "high-fov-full-field-seed-intake"
    assert task["probe_execution"] == {
        "executed": False,
        "reason": "not_requested",
    }


def test_acceptance_export_executes_seed_intake_local_probe():
    report = build_report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_local_probes=True,
    )

    assert report["summary"]["task_count"] == 1
    assert report["summary"]["executed_probe_count"] == 1
    assert report["summary"]["failed_probe_count"] == 0
    task = report["tasks"][0]
    execution = task["probe_execution"]
    assert execution["executed"] is True
    assert execution["timed_out"] is False
    assert execution["exit_code"] == 0
    assert execution["json_parse_error"] is None
    assert execution["stdout_json"]["status"] == "gap"
    assert execution["stdout_json"]["missing_evidence"]


def test_acceptance_export_writes_artifacts(tmp_path):
    report = build_report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_local_probes=True,
    )

    artifacts = write_artifacts(report, tmp_path, split_tasks=True)

    report_path = tmp_path / "acceptance_tasks.json"
    assert artifacts["report"] == str(report_path)
    assert report_path.exists()
    saved_report = json.loads(report_path.read_text())
    assert saved_report["summary"]["artifacts"]["report"] == str(report_path)
    assert len(saved_report["summary"]["artifacts"]["tasks"]) == 1
    task_path = tmp_path / "tasks" / (
        "001-high_fov_main_uses_89deg_seed-ingest-high-fov-full-field-seed.json"
    )
    assert saved_report["summary"]["artifacts"]["tasks"] == [str(task_path)]
    saved_task = json.loads(task_path.read_text())
    assert saved_task["task_id"] == "ingest-high-fov-full-field-seed"
    assert "evaluate_design_agent.py --case" in saved_task["case_verification_command"]
    assert saved_task["probe_execution"]["stdout_json"]["status"] == "gap"


def test_acceptance_export_writes_runner_summary_artifact(tmp_path):
    report = build_report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_local_probes=True,
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
    assert saved_runner["summary"]["runner_status"] == "blocked_on_external_evidence"
    assert saved_runner["summary"]["external_blocker_count"] == 1


def test_acceptance_export_executes_case_verification_probe():
    report = build_report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_case_verification=True,
    )

    assert report["summary"]["task_count"] == 1
    assert report["summary"]["executed_verification_count"] == 1
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
    assert case["acceptance_improvement_tasks"][0]["stage"] == "seed_ingestion"


def test_acceptance_export_scopes_image_quality_probe_to_single_case():
    report = build_report(case_names={"balanced_main_default"})

    task = next(
        item
        for item in report["tasks"]
        if item["source_action_id"].startswith("image_quality_floor")
    )

    assert task["next_probe_command"] == (
        "single-case replay: cd lumira-backend && uv run python "
        "scripts/evaluate_design_agent.py "
        "--case balanced_main_default --json --fail-on-regression"
    )
    assert task["command_mode"] == "manual"
    assert task["evidence_probe"]["next_probe_command"] == (
        "cd lumira-backend && uv run python "
        "scripts/evaluate_design_agent.py --fail-on-regression --json"
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


def test_acceptance_runner_summary_prioritizes_external_seed_gap():
    report = build_report(
        stage="seed_ingestion",
        case_names={"high_fov_main_uses_89deg_seed"},
        execute_local_probes=True,
        execute_case_verification=True,
    )

    runner = build_runner_summary(report)

    assert runner["summary"]["runner_status"] == "blocked_on_external_evidence"
    assert runner["summary"]["action_kinds"] == {"external_evidence_gap": 1}
    assert runner["summary"]["top_action_kind"] == "external_evidence_gap"
    action = runner["next_actions"][0]
    assert action["eval_case"] == "high_fov_main_uses_89deg_seed"
    assert action["task_id"] == "ingest-high-fov-full-field-seed"
    assert action["probe_result_status"] == "gap"
    assert action["case_verification_passed"] is True
    assert "audit_seed_intake.py" in action["next_probe_command"]
    request = action["evidence_request"]
    assert request["accepted_seed_count"] == 0
    assert request["required_mtf_field_frac"] == 1.0
    assert any("FOV >= 85.0" in item for item in request["required_inputs"])
    assert any("MTF evaluates at 1.0 field" in item for item in request["missing_evidence"])
    assert any("nearest high-FOV seed" in item for item in request["known_evidence"])
    assert request["blocked_claims"] == [
        "full-field edge-performance claim",
        "production-ready optical prescription",
        "full replacement of optical designer review for this high-FOV case",
    ]
    assert "candidate.zmx" in request["candidate_preflight_command"]
    assert request["nearest_candidates"][0]["role"] == "nearest_high_fov"


def test_acceptance_runner_summary_blocks_downstream_same_case_tasks():
    report = build_report(
        case_names={
            "high_fov_main_uses_89deg_seed",
            "ui_high_fov_default_request_stays_blocked",
            "balanced_main_default",
            "performance_full_field_seed_blocks_low_mtf",
        },
        execute_local_probes=True,
        execute_case_verification=True,
    )

    runner = build_runner_summary(report)

    assert runner["summary"]["runner_status"] == "blocked_on_external_evidence"
    assert runner["summary"]["action_kinds"]["blocked_by_upstream_evidence"] == 8
    assert runner["summary"]["external_blocker_count"] >= 2
    assert (
        runner["summary"]["manual_followup_count"]
        + runner["summary"]["case_verification_failure_count"]
        >= 2
    )
    assert runner["summary"]["action_kinds"].get("local_probe_gap", 0) == 0
    assert runner["summary"]["upstream_blocked_count"] == 8
    assert (
        runner["summary"]["external_blocker_count"]
        + runner["summary"]["manual_followup_count"]
        + runner["summary"]["upstream_blocked_count"]
        + runner["summary"]["case_verification_failure_count"]
        == runner["summary"]["task_count"]
    )
    blocked = [
        action
        for action in runner["next_actions"]
        if action["action_kind"] == "blocked_by_upstream_evidence"
    ]
    assert {item["eval_case"] for item in blocked} == {
        "high_fov_main_uses_89deg_seed",
        "ui_high_fov_default_request_stays_blocked",
    }
    assert {item["original_action_kind"] for item in blocked} <= {
        "manual_followup",
        "case_verification_failed",
    }
    assert all(
        item["blocked_by"]["task_id"] == "ingest-high-fov-full-field-seed"
        for item in blocked
    )
    assert all(
        item["blocked_by"]["evidence_request"]["accepted_seed_count"] == 0
        for item in blocked
    )
