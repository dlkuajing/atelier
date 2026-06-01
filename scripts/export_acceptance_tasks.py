"""Export design-agent acceptance tasks as machine-readable work packets.

Run:
    cd lumira-backend
    uv run python scripts/export_acceptance_tasks.py --json
    uv run python scripts/export_acceptance_tasks.py --stage remediation_resolution --json
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.case_library import match_case  # noqa: E402
from app.core.optical_sample import AcceptanceImprovementTask, OpticalSampleData  # noqa: E402
from scripts.evaluate_design_agent import EVAL_CASES, EvalCase  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "lumira-backend"
LOCAL_PROBE_PREFIX = "cd lumira-backend && uv run python "
LOCAL_PROBE_SCRIPT_ROOT = BACKEND_ROOT / "scripts"
_SLUG_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _command_mode(command: str | None) -> str:
    if not command:
        return "manual"
    if "/path/to/" in command:
        return "template"
    if command.startswith(f"{LOCAL_PROBE_PREFIX}scripts/"):
        return "local_probe"
    return "manual"


def _execution_state(task: AcceptanceImprovementTask) -> str:
    if task.status == "external_evidence_required":
        return "waiting_for_external_evidence"
    if task.evidence_probe is not None and task.evidence_probe.status == "gap":
        return "waiting_for_probe_evidence"
    if task.status in {"ready", "queued"}:
        return "ready_for_agent_or_designer"
    return task.status


def _case_verification_command(case: EvalCase) -> str:
    return (
        "cd lumira-backend && uv run python scripts/evaluate_design_agent.py "
        f"--case {case.name} --json --fail-on-regression"
    )


def _task_packet(
    case: EvalCase,
    sample: OpticalSampleData,
    task: AcceptanceImprovementTask,
) -> dict[str, Any]:
    assessment = sample.design_assessment
    probe = task.evidence_probe
    next_command = probe.next_probe_command if probe is not None else None
    verification_command = _case_verification_command(case)
    return {
        "eval_case": case.name,
        "matched_case_id": sample.metadata.case_id,
        "recommended_candidate_id": (
            assessment.recommended_candidate_id if assessment is not None else None
        ),
        "acceptance_status": (
            assessment.draft_acceptance_gate.status
            if assessment is not None and assessment.draft_acceptance_gate is not None
            else None
        ),
        "designer_readiness": (
            assessment.designer_readiness_rubric.status
            if assessment is not None
            and assessment.designer_readiness_rubric is not None
            else None
        ),
        "task_id": task.task_id,
        "source_action_id": task.source_action_id,
        "priority": task.priority,
        "status": task.status,
        "stage": task.stage,
        "owner": task.owner,
        "objective": task.objective,
        "required_inputs": task.required_inputs,
        "validation_steps": task.validation_steps,
        "exit_criteria": task.exit_criteria,
        "depends_on": task.depends_on,
        "blocks_claims": task.blocks_claims,
        "execution_state": _execution_state(task),
        "command_mode": _command_mode(next_command),
        "next_probe_command": next_command,
        "case_verification_command": verification_command,
        "case_verification_command_mode": _command_mode(verification_command),
        "evidence_probe": probe.model_dump(mode="json") if probe is not None else None,
    }


def _tail_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value.strip()[-2000:]


def _local_probe_argv(command: str) -> list[str] | None:
    if not command.startswith(LOCAL_PROBE_PREFIX):
        return None

    args = shlex.split(command.removeprefix(LOCAL_PROBE_PREFIX))
    if not args:
        return None

    script = args[0]
    script_path = (BACKEND_ROOT / script).resolve()
    script_root = LOCAL_PROBE_SCRIPT_ROOT.resolve()
    try:
        script_path.relative_to(script_root)
    except ValueError:
        return None
    if script_path.suffix != ".py" or not script_path.exists():
        return None

    return ["uv", "run", "python", *args]


def _local_probe_execution(command: str, *, timeout_s: int) -> dict[str, Any]:
    argv = _local_probe_argv(command)
    if argv is None:
        return {
            "executed": False,
            "reason": "untrusted_local_probe_command",
        }

    try:
        result = subprocess.run(
            argv,
            cwd=BACKEND_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "executed": True,
            "timed_out": True,
            "exit_code": None,
            "stdout_json": None,
            "json_parse_error": None,
            "stdout_tail": _tail_text(exc.stdout),
            "stderr_tail": _tail_text(exc.stderr),
        }

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    stdout_json = None
    parse_error = None
    if stdout:
        try:
            stdout_json = json.loads(stdout)
        except json.JSONDecodeError as exc:
            parse_error = str(exc)
    return {
        "executed": True,
        "timed_out": False,
        "exit_code": result.returncode,
        "stdout_json": stdout_json,
        "json_parse_error": parse_error,
        "stdout_tail": stdout[-2000:] if stdout_json is None else "",
        "stderr_tail": stderr[-2000:],
    }


def _attach_probe_execution(
    tasks: list[dict[str, Any]],
    *,
    execute_local_probes: bool,
    probe_timeout_s: int,
) -> None:
    for task in tasks:
        command = task.get("next_probe_command")
        if not execute_local_probes:
            task["probe_execution"] = {"executed": False, "reason": "not_requested"}
            continue
        if task.get("command_mode") != "local_probe" or not command:
            task["probe_execution"] = {
                "executed": False,
                "reason": f"command_mode={task.get('command_mode')}",
            }
            continue
        task["probe_execution"] = _local_probe_execution(
            command,
            timeout_s=probe_timeout_s,
        )


def _attach_case_verification_execution(
    tasks: list[dict[str, Any]],
    *,
    execute_case_verification: bool,
    probe_timeout_s: int,
) -> None:
    verification_by_command: dict[str, dict[str, Any]] = {}
    for task in tasks:
        command = task.get("case_verification_command")
        if not execute_case_verification:
            task["case_verification_execution"] = {
                "executed": False,
                "reason": "not_requested",
            }
            continue
        if task.get("case_verification_command_mode") != "local_probe" or not command:
            task["case_verification_execution"] = {
                "executed": False,
                "reason": f"command_mode={task.get('case_verification_command_mode')}",
            }
            continue
        if command not in verification_by_command:
            verification_by_command[command] = _local_probe_execution(
                command,
                timeout_s=probe_timeout_s,
            )
        task["case_verification_execution"] = dict(verification_by_command[command])


def collect_acceptance_tasks(
    *,
    stage: str | None = None,
    case_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for case in EVAL_CASES:
        if case_names is not None and case.name not in case_names:
            continue
        sample = match_case(**case.request)
        if sample is None or sample.design_assessment is None:
            continue
        for task in sample.design_assessment.acceptance_improvement_tasks:
            if stage is not None and task.stage != stage:
                continue
            packets.append(_task_packet(case, sample, task))
    return packets


def build_report(
    *,
    stage: str | None = None,
    case_names: set[str] | None = None,
    execute_local_probes: bool = False,
    execute_case_verification: bool = False,
    probe_timeout_s: int = 120,
) -> dict[str, Any]:
    tasks = collect_acceptance_tasks(stage=stage, case_names=case_names)
    _attach_probe_execution(
        tasks,
        execute_local_probes=execute_local_probes,
        probe_timeout_s=probe_timeout_s,
    )
    _attach_case_verification_execution(
        tasks,
        execute_case_verification=execute_case_verification,
        probe_timeout_s=probe_timeout_s,
    )
    stages = Counter(task["stage"] for task in tasks)
    statuses = Counter(task["status"] for task in tasks)
    command_modes = Counter(task["command_mode"] for task in tasks)
    executed_probe_count = sum(
        1 for task in tasks if task.get("probe_execution", {}).get("executed")
    )
    failed_probe_count = sum(
        1
        for task in tasks
        if task.get("probe_execution", {}).get("executed")
        and (
            task.get("probe_execution", {}).get("exit_code") != 0
            or task.get("probe_execution", {}).get("timed_out")
        )
    )
    executed_verification_count = sum(
        1
        for task in tasks
        if task.get("case_verification_execution", {}).get("executed")
    )
    failed_verification_count = sum(
        1
        for task in tasks
        if task.get("case_verification_execution", {}).get("executed")
        and (
            task.get("case_verification_execution", {}).get("exit_code") != 0
            or task.get("case_verification_execution", {}).get("timed_out")
        )
    )
    return {
        "summary": {
            "task_count": len(tasks),
            "stage_filter": stage,
            "case_filter": sorted(case_names) if case_names else [],
            "stages": dict(sorted(stages.items())),
            "statuses": dict(sorted(statuses.items())),
            "command_modes": dict(sorted(command_modes.items())),
            "execute_local_probes": execute_local_probes,
            "execute_case_verification": execute_case_verification,
            "executed_probe_count": executed_probe_count,
            "failed_probe_count": failed_probe_count,
            "executed_verification_count": executed_verification_count,
            "failed_verification_count": failed_verification_count,
        },
        "tasks": tasks,
    }


def _artifact_slug(value: str) -> str:
    slug = _SLUG_RE.sub("-", value).strip("-._")
    return slug or "task"


def _execution_failed(execution: dict[str, Any] | None) -> bool:
    if not execution or not execution.get("executed"):
        return False
    return (
        execution.get("exit_code") != 0
        or bool(execution.get("timed_out"))
        or bool(execution.get("json_parse_error"))
    )


def _probe_result_status(task: dict[str, Any]) -> str | None:
    execution = task.get("probe_execution", {})
    stdout_json = execution.get("stdout_json")
    if isinstance(stdout_json, dict) and isinstance(stdout_json.get("status"), str):
        return stdout_json["status"]
    evidence_probe = task.get("evidence_probe")
    if isinstance(evidence_probe, dict) and isinstance(evidence_probe.get("status"), str):
        return evidence_probe["status"]
    return None


def _case_verification_passed(task: dict[str, Any]) -> bool | None:
    execution = task.get("case_verification_execution", {})
    if not execution.get("executed"):
        return None
    if _execution_failed(execution):
        return False
    stdout_json = execution.get("stdout_json")
    if not isinstance(stdout_json, dict):
        return False
    summary = stdout_json.get("summary")
    if not isinstance(summary, dict):
        return False
    return bool(summary.get("all_passed"))


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _list_value(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _evidence_request_packet(task: dict[str, Any]) -> dict[str, Any] | None:
    if task["status"] != "external_evidence_required" and _probe_result_status(task) != "gap":
        return None

    probe_execution = task.get("probe_execution", {})
    probe_stdout = probe_execution.get("stdout_json")
    evidence_probe = task.get("evidence_probe")
    evidence_payload = _first_dict(probe_stdout, evidence_probe)
    if not evidence_payload:
        return {
            "required_inputs": task["required_inputs"],
            "known_evidence": [],
            "missing_evidence": [],
            "blocked_claims": task["blocks_claims"],
            "candidate_preflight_command": None,
            "nearest_candidates": [],
        }

    return {
        "required_inputs": task["required_inputs"],
        "known_evidence": _list_value(evidence_payload, "known_evidence"),
        "missing_evidence": _list_value(evidence_payload, "missing_evidence"),
        "blocked_claims": task["blocks_claims"],
        "candidate_preflight_command": evidence_payload.get(
            "candidate_preflight_command"
        ),
        "next_probe_command": evidence_payload.get("next_probe_command"),
        "nearest_candidates": _list_value(evidence_payload, "nearest_candidates"),
        "accepted_seed_count": evidence_payload.get("accepted_seed_count"),
        "required_mtf_field_frac": evidence_payload.get("required_mtf_field_frac"),
    }


def _runner_action_kind(task: dict[str, Any]) -> str:
    probe_execution = task.get("probe_execution", {})
    verification_execution = task.get("case_verification_execution", {})
    probe_status = _probe_result_status(task)
    if _execution_failed(probe_execution):
        return "local_probe_failed"
    if task["status"] == "external_evidence_required":
        if probe_status == "gap":
            return "external_evidence_gap"
        return "external_evidence_required"
    if _execution_failed(verification_execution):
        return "case_verification_failed"
    if _case_verification_passed(task) is False:
        return "case_verification_failed"
    if task["command_mode"] == "local_probe":
        if probe_status == "satisfied":
            return "local_probe_satisfied"
        if probe_status == "gap":
            return "local_probe_gap"
        return "local_probe_available"
    if task["command_mode"] == "manual":
        return "manual_followup"
    return "ready_followup"


def _attach_upstream_blockers(actions: list[dict[str, Any]]) -> None:
    upstream_by_case: dict[str, dict[str, Any]] = {}
    for action in sorted(
        actions,
        key=lambda item: (
            item["priority"],
            item["eval_case"],
            item["stage"],
            item["task_id"],
        ),
    ):
        if action["action_kind"] in {
            "external_evidence_gap",
            "external_evidence_required",
        }:
            upstream_by_case.setdefault(action["eval_case"], action)

    for action in actions:
        upstream = upstream_by_case.get(action["eval_case"])
        if upstream is None or upstream["task_id"] == action["task_id"]:
            continue
        if action["priority"] <= upstream["priority"]:
            continue
        if action["action_kind"] in {
            "external_evidence_gap",
            "external_evidence_required",
            "local_probe_failed",
        }:
            continue
        action["original_action_kind"] = action["action_kind"]
        action["action_kind"] = "blocked_by_upstream_evidence"
        action["blocked_by"] = {
            "eval_case": upstream["eval_case"],
            "task_id": upstream["task_id"],
            "priority": upstream["priority"],
            "stage": upstream["stage"],
            "action_kind": upstream["action_kind"],
            "objective": upstream["objective"],
            "evidence_request": upstream.get("evidence_request"),
        }


def build_runner_summary(report: dict[str, Any]) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for task in report["tasks"]:
        action_kind = _runner_action_kind(task)
        actions.append(
            {
                "action_kind": action_kind,
                "eval_case": task["eval_case"],
                "task_id": task["task_id"],
                "priority": task["priority"],
                "stage": task["stage"],
                "owner": task["owner"],
                "status": task["status"],
                "execution_state": task["execution_state"],
                "objective": task["objective"],
                "probe_result_status": _probe_result_status(task),
                "case_verification_passed": _case_verification_passed(task),
                "next_probe_command": task["next_probe_command"],
                "case_verification_command": task["case_verification_command"],
                "evidence_request": _evidence_request_packet(task),
            }
        )

    _attach_upstream_blockers(actions)
    actions.sort(
        key=lambda item: (
            item["priority"],
            item["eval_case"],
            item["stage"],
            item["task_id"],
        )
    )
    action_kinds = Counter(action["action_kind"] for action in actions)
    if action_kinds["local_probe_failed"]:
        runner_status = "local_probe_failed"
    elif action_kinds["external_evidence_gap"] or action_kinds[
        "external_evidence_required"
    ]:
        runner_status = "blocked_on_external_evidence"
    elif action_kinds["case_verification_failed"]:
        runner_status = "case_verification_failed"
    elif action_kinds["manual_followup"]:
        runner_status = "manual_followup_ready"
    elif actions:
        runner_status = "local_followup_ready"
    else:
        runner_status = "no_acceptance_tasks"

    return {
        "summary": {
            "runner_status": runner_status,
            "task_count": len(actions),
            "action_kinds": dict(sorted(action_kinds.items())),
            "external_blocker_count": action_kinds["external_evidence_gap"]
            + action_kinds["external_evidence_required"],
            "manual_followup_count": action_kinds["manual_followup"],
            "upstream_blocked_count": action_kinds["blocked_by_upstream_evidence"],
            "local_probe_failure_count": action_kinds["local_probe_failed"],
            "case_verification_failure_count": action_kinds[
                "case_verification_failed"
            ],
            "top_action_kind": actions[0]["action_kind"] if actions else None,
        },
        "next_actions": actions,
    }


def write_artifacts(
    report: dict[str, Any],
    output_dir: Path,
    *,
    split_tasks: bool = False,
    include_runner_summary: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths: dict[str, Any] = {
        "report": str(output_dir / "acceptance_tasks.json"),
        "tasks": [],
    }
    if include_runner_summary:
        artifact_paths["runner_summary"] = str(
            output_dir / "acceptance_runner_summary.json"
        )
        report["runner_summary"] = build_runner_summary(report)

    if split_tasks:
        tasks_dir = output_dir / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for index, task in enumerate(report["tasks"], start=1):
            filename = (
                f"{index:03d}-"
                f"{_artifact_slug(str(task['eval_case']))}-"
                f"{_artifact_slug(str(task['task_id']))}.json"
            )
            task_path = tasks_dir / filename
            artifact_paths["tasks"].append(str(task_path))
            task_path.write_text(
                json.dumps(task, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    report["summary"]["artifacts"] = artifact_paths
    if include_runner_summary:
        Path(artifact_paths["runner_summary"]).write_text(
            json.dumps(report["runner_summary"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    Path(artifact_paths["report"]).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact_paths


def _print_human(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print("Lumira Atelier acceptance task export")
    print("=" * 72)
    print(
        f"tasks={summary['task_count']} "
        f"stages={summary['stages']} "
        f"statuses={summary['statuses']} "
        f"commands={summary['command_modes']} "
        f"executed_probes={summary['executed_probe_count']} "
        f"failed_probes={summary['failed_probe_count']} "
        f"executed_verifications={summary['executed_verification_count']} "
        f"failed_verifications={summary['failed_verification_count']}"
    )
    if artifacts := summary.get("artifacts"):
        print(f"artifacts={artifacts}")
    for task in report["tasks"]:
        print(
            f"- {task['eval_case']}: P{task['priority']} {task['task_id']} "
            f"{task['status']}/{task['stage']} "
            f"mode={task['command_mode']} state={task['execution_state']}"
        )
        if task["next_probe_command"]:
            print(f"  command: {task['next_probe_command']}")
        execution = task.get("probe_execution", {})
        if execution.get("executed"):
            print(
                "  probe: "
                f"exit={execution.get('exit_code')} "
                f"timed_out={execution.get('timed_out')}"
            )
        verification = task.get("case_verification_execution", {})
        if verification.get("executed"):
            print(
                "  verification: "
                f"exit={verification.get('exit_code')} "
                f"timed_out={verification.get('timed_out')}"
            )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", help="Only export tasks with this stage")
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        help="Only export one eval case; may be passed more than once",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    parser.add_argument(
        "--fail-on-empty",
        action="store_true",
        help="Exit non-zero when no tasks match the filters",
    )
    parser.add_argument(
        "--execute-local-probes",
        action="store_true",
        help="Execute trusted local_probe commands and attach their results",
    )
    parser.add_argument(
        "--execute-case-verification",
        action="store_true",
        help="Execute each task's trusted single-case eval verification command",
    )
    parser.add_argument(
        "--probe-timeout",
        type=int,
        default=120,
        help="Timeout in seconds for each executed local probe",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write the full report JSON to this directory",
    )
    parser.add_argument(
        "--split-tasks",
        action="store_true",
        help="When --output-dir is set, also write one JSON file per task",
    )
    parser.add_argument(
        "--runner-summary",
        action="store_true",
        help="Build a compact runner triage summary from the exported task evidence",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_report(
        stage=args.stage,
        case_names=set(args.cases) if args.cases else None,
        execute_local_probes=args.execute_local_probes,
        execute_case_verification=args.execute_case_verification,
        probe_timeout_s=args.probe_timeout,
    )
    if args.runner_summary:
        report["runner_summary"] = build_runner_summary(report)
    if args.output_dir is not None:
        write_artifacts(
            report,
            args.output_dir,
            split_tasks=args.split_tasks,
            include_runner_summary=args.runner_summary,
        )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    if args.fail_on_empty and not report["tasks"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
