from __future__ import annotations

import hashlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.core.batch_run_lock import BatchRunnerLockHeldError, batch_runner_lock
from app.core.engines.stagec_attested import StageCAttestedEvidence, StageCAttestedField
from scripts import p16_stagec_real_matrix as matrix


def test_matrix_cli_holds_cross_worktree_window_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    window = tmp_path / "p18-global-window"

    def fake_execute(**_kwargs: object) -> dict[str, object]:
        nonlocal calls
        with pytest.raises(BatchRunnerLockHeldError), batch_runner_lock(window):
            raise AssertionError("matrix execution escaped the P18 global window")
        calls += 1
        return {}

    monkeypatch.setattr(matrix, "P18_GLOBAL_WINDOW_ROOT", window)
    monkeypatch.setattr(matrix, "build_plan", lambda **_kwargs: {"matrix_id": "fixture"})
    monkeypatch.setattr(matrix, "execute_plan", fake_execute)
    monkeypatch.setattr(
        matrix,
        "aggregate",
        lambda **_kwargs: {
            "run_count": 0,
            "delivered_run_count": 0,
            "blocked_run_count": 0,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "p16_stagec_real_matrix.py",
            "--stageb-manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(tmp_path / "matrix"),
        ],
    )
    with batch_runner_lock(window), pytest.raises(BatchRunnerLockHeldError):
        matrix.main()
    assert calls == 0
    assert matrix.main() == 0
    assert calls == 1
    with batch_runner_lock(window):
        pass


def _cache_hash(case_id: str) -> str:
    return hashlib.sha256(f"cache:{case_id}".encode()).hexdigest()


def _cache_state(cell: dict[str, object]) -> dict[str, object]:
    return {
        "stageb_cache_scope": cell["cache_scope"],
        "stageb_pre_run_bound": cell["pre_run_bound"],
        "stageb_cache_record_sha256": cell["cache_record_sha256"],
    }


def _field(index: int, fraction: float) -> StageCAttestedField:
    return StageCAttestedField(
        field_index=index,
        sample_id=f"field-{index:04d}",
        normalized_fraction=fraction,
        definition_x_ri_mm=0.0,
        definition_y_ri_mm=2.9 * fraction,
        rsi_actual_x_mm=0.0,
        rsi_actual_y_mm=2.9 * fraction,
        rsi_direction_l=0.0,
        rsi_direction_m=0.0,
        rsi_direction_n=1.0,
        rayrsi_return_code=0,
        rer=0,
        bls=0,
        spotdata_return_code=0,
        rms_spot_diameter_um=10.0 + index,
        rmswe_return_value=1.0,
        rms_wfe_waves=0.2 + index / 100,
        vuy=0.0,
        vly=0.0,
        vux=0.0,
        vlx=0.0,
        ray_classification="valid",
    )


def _evidence(
    *,
    matrix_id: str,
    plan_sha: str,
    case_id: str,
    arm: str,
    repeat: int,
    cache_scope: str = "pre-run-bound",
) -> StageCAttestedEvidence:
    run_id = f"run-{case_id}-{arm}-{repeat}"
    return StageCAttestedEvidence.model_construct(
        schema_id="atelier-stagec-attested-evidence-v3",
        evidence_kind="attested-machine",
        run_id=run_id,
        matrix_id=matrix_id,
        cell_id=f"{case_id}--{arm}",
        seed_id=case_id,
        arm=arm,
        repeat_index=repeat,
        receipt_sha256=hashlib.sha256(run_id.encode()).hexdigest(),
        execution_plan_sha256=plan_sha,
        stageb_cache_scope=cache_scope,
        stageb_pre_run_bound=cache_scope == "pre-run-bound",
        stageb_cache_record_sha256=_cache_hash(case_id),
        package_path=f"D:/runs/{run_id}",
        source_zmx_sha256="a" * 64,
        reconstructed_zmx_sha256=f"{int(case_id[-1]):064x}",
        target_efl_mm=3.6,
        target_image_height_mm=2.9,
        normalized_fractions=(0.0, 1.0),
        expected_vignetting_profile=((0.0, 0.0, 0.0, 0.0),) * 2,
        measured_efl_mm=3.6,
        fields=(_field(1, 0.0), _field(2, 1.0)),
        process_returncode_observed=0,
        process_duration_seconds=float(repeat),
        artifact_bindings_valid=True,
        receipt_attested=True,
        field_type="RIH",
        expert_verdict=None,
    )


def _run_row(evidence: StageCAttestedEvidence, receipt: str) -> dict[str, object]:
    return {
        "cell_id": evidence.cell_id,
        "case_id": evidence.seed_id,
        "arm": evidence.arm,
        "repeat_index": evidence.repeat_index,
        "run_id": evidence.run_id,
        "receipt": receipt,
        "receipt_sha256": evidence.receipt_sha256,
        "stageb_cache_scope": evidence.stageb_cache_scope,
        "stageb_pre_run_bound": evidence.stageb_pre_run_bound,
        "stageb_cache_record_sha256": evidence.stageb_cache_record_sha256,
        "attested_duration_seconds": evidence.process_duration_seconds,
    }


def _plan(
    tmp_path: Path, *, retrospective_seed_ids: set[str] | None = None
) -> tuple[dict[str, object], str]:
    retrospective_seed_ids = retrospective_seed_ids or set()
    stageb_manifest = tmp_path / "stageb-manifest.json"
    if not stageb_manifest.exists():
        stageb_manifest.write_text("{}", encoding="utf-8")
    cells = []
    for seed_index in range(1, 9):
        case_id = f"seed-{seed_index}"
        cache_scope = (
            "retrospective-current-state-adoption"
            if case_id in retrospective_seed_ids
            else "pre-run-bound"
        )
        for arm in matrix.ARMS:
            cells.append(
                {
                    "cell_id": f"{case_id}--{arm}",
                    "case_id": case_id,
                    "arm": arm,
                    "target_efl_mm": 3.6,
                    "target_image_height_mm": 2.9,
                    "accepted_zmx_sha256": "a" * 64,
                    "source_zmx_sha256": "b" * 64,
                    "cache_scope": cache_scope,
                    "pre_run_bound": cache_scope == "pre-run-bound",
                    "cache_record_path": str(
                        (tmp_path / "cache-records" / f"{case_id}.json").resolve()
                    ),
                    "cache_record_sha256": _cache_hash(case_id),
                    "reconstruction": {"output_sha256": f"{seed_index:064x}"},
                }
            )
    plan = {
        "schema_id": matrix.PLAN_SCHEMA,
        "matrix_id": "matrix-test",
        "stageb_manifest": str(stageb_manifest.resolve()),
        "stageb_manifest_sha256": hashlib.sha256(stageb_manifest.read_bytes()).hexdigest(),
        "stageb_cache_scope_counts": {
            scope: sum(
                (case_id in retrospective_seed_ids)
                == (scope == "retrospective-current-state-adoption")
                for case_id in {f"seed-{index}" for index in range(1, 9)}
            )
            for scope in (
                ["pre-run-bound", "retrospective-current-state-adoption"]
                if retrospective_seed_ids
                else ["pre-run-bound"]
            )
        },
        "all_inputs_pre_run_bound": not retrospective_seed_ids,
        "retrospective_seed_ids": sorted(retrospective_seed_ids),
        "cells": cells,
    }
    plan_path = tmp_path / "matrix-plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan, hashlib.sha256(plan_path.read_bytes()).hexdigest()


def test_aggregate_requires_exact_8_by_3_by_2_unique_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, plan_sha = _plan(tmp_path)
    evidence_by_receipt = {}
    rows = []
    for cell in plan["cells"]:
        for repeat in (1, 2):
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=cell["case_id"],
                arm=cell["arm"],
                repeat=repeat,
            )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    monkeypatch.setattr(
        matrix,
        "restore_stagec_attested_evidence",
        lambda path: evidence_by_receipt[str(path)],
    )

    report = matrix.aggregate(
        plan=plan,
        state={"runs": rows, "attempts": []},
        output_dir=tmp_path,
    )

    assert report["structural_complete"] is True
    assert report["run_count"] == 48
    assert report["delivered_run_count"] == 48
    assert report["expert_verdict"] is None
    assert len(report["cell_repeat_distributions"]) == 24
    assert report["arm_duration_costs"][0]["run_count"] == 16
    assert report["arm_duration_costs"][0]["total_attested_duration_seconds"] == 24.0
    assert report["cell_repeat_distributions"][0]["attested_duration_seconds_mean"] == 1.5


def test_aggregate_excludes_spot_and_wfe_sentinels_from_all_statistics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, plan_sha = _plan(tmp_path)
    evidence_by_receipt: dict[str, StageCAttestedEvidence] = {}
    rows: list[dict[str, object]] = []
    for cell in plan["cells"]:
        for repeat in (1, 2):
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=cell["case_id"],
                arm=cell["arm"],
                repeat=repeat,
            )
            if cell["case_id"] == "seed-1" and (
                cell["arm"] == "target-low" or (cell["arm"] == "target-high" and repeat == 1)
            ):
                evidence = evidence.model_copy(
                    update={
                        "fields": tuple(
                            field.model_copy(
                                update={
                                    "spotdata_return_code": -1,
                                    "rms_spot_diameter_um": -1000.0,
                                    "rmswe_return_value": -1.0,
                                    "rms_wfe_waves": -1.0,
                                }
                            )
                            for field in evidence.fields
                        )
                    }
                )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    monkeypatch.setattr(
        matrix,
        "restore_stagec_attested_evidence",
        lambda path: evidence_by_receipt[str(path)],
    )

    report = matrix.aggregate(
        plan=plan,
        state={"runs": rows, "attempts": []},
        output_dir=tmp_path,
    )

    low = next(
        item
        for item in report["cell_repeat_distributions"]
        if item["case_id"] == "seed-1" and item["arm"] == "target-low"
    )
    assert low["max_field_spot_diameter_um_samples"] == []
    assert low["max_field_spot_diameter_um_mean"] is None
    assert low["max_field_spot_diameter_um_spread"] is None
    assert low["max_field_spot_diameter_um_availability"] == "unavailable"
    assert low["max_field_rms_wfe_waves_samples"] == []
    assert low["max_field_rms_wfe_waves_mean"] is None
    assert low["max_field_rms_wfe_waves_spread"] is None
    assert low["max_field_rms_wfe_waves_availability"] == "unavailable"
    assert low["max_field_spot_diameter_um_mean_delta_vs_native"] is None
    assert low["max_field_spot_diameter_um_mean_pct_vs_native"] is None
    assert low["max_field_rms_wfe_waves_mean_delta_vs_native"] is None
    assert low["max_field_rms_wfe_waves_mean_pct_vs_native"] is None

    high = next(
        item
        for item in report["cell_repeat_distributions"]
        if item["case_id"] == "seed-1" and item["arm"] == "target-high"
    )
    assert high["max_field_spot_diameter_um_samples"] == [12.0]
    assert high["max_field_spot_diameter_um_mean"] == 12.0
    assert high["max_field_spot_diameter_um_spread"] is None
    assert high["max_field_spot_diameter_um_availability"] == "partial"
    assert high["max_field_spot_diameter_um_mean_delta_vs_native"] is None
    assert high["max_field_rms_wfe_waves_samples"] == [0.22]
    assert high["max_field_rms_wfe_waves_mean"] == 0.22
    assert high["max_field_rms_wfe_waves_spread"] is None
    assert high["max_field_rms_wfe_waves_availability"] == "partial"
    assert high["max_field_rms_wfe_waves_mean_pct_vs_native"] is None

    blocked_runs = [
        run
        for run in report["runs"]
        if run["case_id"] == "seed-1"
        and run["arm"] in {"target-low", "target-high"}
        and run["repeat_index"] == 1
    ]
    assert all(run["status"] == "blocked" for run in blocked_runs)
    assert all(run["spot_diameter_um"] is None for run in blocked_runs)
    assert all(run["rms_wfe_waves"] is None for run in blocked_runs)
    assert "-1000" not in json.dumps(report["cell_repeat_distributions"])


def test_mixed_cache_scopes_survive_all_48_receipts_and_report_by_unique_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    retrospective = {"seed-2", "seed-7"}
    plan, plan_sha = _plan(tmp_path, retrospective_seed_ids=retrospective)
    evidence_by_receipt: dict[str, StageCAttestedEvidence] = {}
    rows: list[dict[str, object]] = []
    for cell in plan["cells"]:
        assert isinstance(cell, dict)
        for repeat in (1, 2):
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=str(cell["case_id"]),
                arm=str(cell["arm"]),
                repeat=repeat,
                cache_scope=str(cell["cache_scope"]),
            )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    monkeypatch.setattr(
        matrix,
        "restore_stagec_attested_evidence",
        lambda path: evidence_by_receipt[str(path)],
    )

    report = matrix.aggregate(
        plan=plan,
        state={"runs": rows, "attempts": []},
        output_dir=tmp_path,
    )

    assert report["stageb_cache_scope_counts"] == {
        "pre-run-bound": 6,
        "retrospective-current-state-adoption": 2,
    }
    assert report["retrospective_seed_ids"] == ["seed-2", "seed-7"]
    assert report["all_inputs_pre_run_bound"] is False
    assert (
        sum(
            run["stageb_cache_scope"] == "retrospective-current-state-adoption"
            for run in report["runs"]
        )
        == 12
    )
    markdown = (tmp_path / "matrix-report.md").read_text(encoding="utf-8")
    assert "does not prove pre-run provenance" in markdown


def test_aggregate_rejects_receipt_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, plan_sha = _plan(tmp_path)
    evidence_by_receipt = {}
    rows = []
    for cell in plan["cells"]:
        for repeat in (1, 2):
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=cell["case_id"],
                arm=cell["arm"],
                repeat=repeat,
            )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    rows[-1] = rows[0]
    monkeypatch.setattr(
        matrix,
        "restore_stagec_attested_evidence",
        lambda path: evidence_by_receipt[str(path)],
    )

    with pytest.raises(ValueError, match="duplicate"):
        matrix.aggregate(
            plan=plan,
            state={"runs": rows, "attempts": []},
            output_dir=tmp_path,
        )


@pytest.mark.parametrize(
    "tamper",
    (
        "target",
        "accepted-hash",
        "arm",
        "seed-count",
        "reconstruction-hash",
        "cache-scope",
        "cache-hash",
        "cache-summary",
    ),
)
def test_validate_existing_plan_rejects_canonical_semantic_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: str
) -> None:
    plan, _plan_sha = _plan(tmp_path)
    manifest = tmp_path / "stageb-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    plan.update(
        {
            "stageb_manifest": str(manifest.resolve()),
            "stageb_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "seed_count": 8,
            "cell_count": 24,
            "repeat_count": 2,
            "expected_run_count": 48,
        }
    )
    canonical = json.loads(json.dumps(plan["cells"]))
    monkeypatch.setattr(matrix, "_canonical_cells", lambda **_kwargs: canonical)
    if tamper == "target":
        plan["cells"][0]["target_image_height_mm"] = 3.1
    elif tamper == "accepted-hash":
        plan["cells"][0]["accepted_zmx_sha256"] = "f" * 64
    elif tamper == "arm":
        plan["cells"][0]["arm"] = "target-high"
    elif tamper == "seed-count":
        plan["seed_count"] = 9
    elif tamper == "cache-scope":
        plan["cells"][0]["cache_scope"] = "retrospective-current-state-adoption"
        plan["cells"][0]["pre_run_bound"] = False
    elif tamper == "cache-hash":
        plan["cells"][0]["cache_record_sha256"] = "f" * 64
    elif tamper == "cache-summary":
        plan["all_inputs_pre_run_bound"] = False
    else:
        plan["cells"][0]["reconstruction"]["output_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="canonical"):
        matrix.validate_or_rederive_plan(plan=plan, stageb_manifest=manifest, output_dir=tmp_path)


def test_main_holds_independent_matrix_lock_before_plan_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    held = False
    observed_root: Path | None = None

    @contextmanager
    def fake_lock(root: Path, **_kwargs: object):
        nonlocal held, observed_root
        observed_root = root
        held = True
        try:
            yield {"lock_id": "test"}
        finally:
            held = False

    def fake_build_plan(**_kwargs: object) -> dict[str, object]:
        assert held is True
        return {"matrix_id": "locked-plan"}

    output = tmp_path / "matrix"
    monkeypatch.setattr(matrix, "batch_runner_lock", fake_lock)
    monkeypatch.setattr(matrix, "build_plan", fake_build_plan)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "p16_stagec_real_matrix.py",
            "--stageb-manifest",
            str(tmp_path / "manifest.json"),
            "--output-dir",
            str(output),
            "--plan-only",
        ],
    )

    assert matrix.main() == 0
    assert held is False
    assert observed_root == tmp_path / ".matrix.matrix-lock"


def test_build_plan_preserves_planless_output_as_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "matrix"
    output.mkdir()
    (output / "interrupted-evidence.bin").write_bytes(b"preserve-me")
    manifest = tmp_path / "stageb-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    canonical_root = tmp_path / "canonical"
    canonical_root.mkdir()
    cells, _ = _plan(canonical_root)
    monkeypatch.setattr(
        matrix,
        "_canonical_cells",
        lambda **_kwargs: json.loads(json.dumps(cells["cells"])),
    )

    plan = matrix.build_plan(stageb_manifest=manifest, output_dir=output)

    assert plan["expected_run_count"] == 48
    orphans = list(tmp_path.glob("matrix.orphan-*"))
    assert len(orphans) == 1
    assert (orphans[0] / "interrupted-evidence.bin").read_bytes() == b"preserve-me"


def test_recover_started_final_receipt_without_duplicate_machine_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, plan_sha = _plan(tmp_path)
    cell = plan["cells"][0]
    evidence = _evidence(
        matrix_id="matrix-test",
        plan_sha=plan_sha,
        case_id=cell["case_id"],
        arm=cell["arm"],
        repeat=1,
    )
    run_root = tmp_path / "trusted-runs"
    receipt = run_root / evidence.run_id / "post-run-receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(matrix, "trusted_stagec_run_root", lambda: run_root)
    monkeypatch.setattr(matrix, "restore_stagec_attested_evidence", lambda _path: evidence)
    state = {
        "runs": [],
        "attempts": [
            {
                "status": "started",
                "cell_id": cell["cell_id"],
                "case_id": cell["case_id"],
                "arm": cell["arm"],
                **_cache_state(cell),
                "repeat_index": 1,
                "run_id": evidence.run_id,
            }
        ],
    }

    matrix._recover_started_attempts(plan=plan, state=state, output_dir=tmp_path)

    assert len(state["runs"]) == 1
    assert state["runs"][0]["run_id"] == evidence.run_id
    assert state["attempts"][0]["status"] == "attested"
    assert state["attempts"][0]["recovered_after_crash"] is True


def test_crash_restore_preserves_retrospective_cache_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, plan_sha = _plan(tmp_path, retrospective_seed_ids={"seed-1"})
    cell = plan["cells"][0]
    assert isinstance(cell, dict)
    evidence = _evidence(
        matrix_id="matrix-test",
        plan_sha=plan_sha,
        case_id=str(cell["case_id"]),
        arm=str(cell["arm"]),
        repeat=1,
        cache_scope="retrospective-current-state-adoption",
    )
    run_root = tmp_path / "trusted-retro-runs"
    receipt = run_root / evidence.run_id / "post-run-receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(matrix, "trusted_stagec_run_root", lambda: run_root)
    monkeypatch.setattr(matrix, "restore_stagec_attested_evidence", lambda _path: evidence)
    state = {
        "runs": [],
        "attempts": [
            {
                "status": "started",
                "cell_id": cell["cell_id"],
                "case_id": cell["case_id"],
                "arm": cell["arm"],
                **_cache_state(cell),
                "repeat_index": 1,
                "run_id": evidence.run_id,
            }
        ],
    }

    matrix._recover_started_attempts(plan=plan, state=state, output_dir=tmp_path)

    assert state["runs"][0]["stageb_cache_scope"] == ("retrospective-current-state-adoption")
    assert state["runs"][0]["stageb_pre_run_bound"] is False
    assert state["runs"][0]["stageb_cache_record_sha256"] == _cache_hash("seed-1")


def test_recover_started_orphan_is_incomplete_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, _plan_sha = _plan(tmp_path)
    cell = plan["cells"][0]
    run_root = tmp_path / "trusted-runs"
    inflight = run_root / "orphan-run.inflight"
    inflight.mkdir(parents=True)
    monkeypatch.setattr(matrix, "trusted_stagec_run_root", lambda: run_root)
    state = {
        "runs": [],
        "attempts": [
            {
                "status": "started",
                "cell_id": cell["cell_id"],
                "case_id": cell["case_id"],
                "arm": cell["arm"],
                **_cache_state(cell),
                "repeat_index": 1,
                "run_id": "orphan-run",
            }
        ],
    }

    recovery_blocked = matrix._recover_started_attempts(plan=plan, state=state, output_dir=tmp_path)

    assert recovery_blocked is True
    assert state["runs"] == []
    assert state["attempts"][0]["status"] == "incomplete"
    assert state["attempts"][0]["duration_seconds"] is None
    assert str(inflight) in state["attempts"][0]["package_paths"]
    assert "rerun is refused" in state["attempts"][0]["error"]["message"]


@pytest.mark.parametrize("attempt_status", ("started", "failed"))
def test_execute_publishes_receipt_last_inflight_without_duplicate_machine_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attempt_status: str
) -> None:
    plan, plan_sha = _plan(tmp_path)
    target_cell = plan["cells"][0]
    target_repeat = 1
    target_evidence = _evidence(
        matrix_id="matrix-test",
        plan_sha=plan_sha,
        case_id=target_cell["case_id"],
        arm=target_cell["arm"],
        repeat=target_repeat,
    )
    evidence_by_receipt: dict[str, StageCAttestedEvidence] = {}
    rows: list[dict[str, object]] = []
    for cell in plan["cells"]:
        for repeat in (1, 2):
            if (cell["cell_id"], repeat) == (target_cell["cell_id"], target_repeat):
                continue
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=cell["case_id"],
                arm=cell["arm"],
                repeat=repeat,
            )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    state = {
        "schema_id": matrix.STATE_SCHEMA,
        "matrix_id": "matrix-test",
        "runs": rows,
        "attempts": [
            {
                "status": attempt_status,
                "cell_id": target_cell["cell_id"],
                "case_id": target_cell["case_id"],
                "arm": target_cell["arm"],
                **_cache_state(target_cell),
                "repeat_index": target_repeat,
                "run_id": target_evidence.run_id,
            }
        ],
    }
    (tmp_path / "matrix-state.json").write_text(json.dumps(state), encoding="utf-8")
    run_root = tmp_path / "trusted-runs"
    inflight = run_root / f"{target_evidence.run_id}.inflight"
    inflight.mkdir(parents=True)
    (inflight / "post-run-receipt.json").write_text("{}", encoding="utf-8")
    final = run_root / target_evidence.run_id
    final_receipt = final / "post-run-receipt.json"
    publish_calls: list[tuple[Path, Path]] = []
    restore_calls: list[Path] = []
    runner_calls: list[dict[str, object]] = []

    def fake_publish(*, inflight: Path, final: Path) -> Path:
        publish_calls.append((inflight, final))
        inflight.rename(final)
        return final / "post-run-receipt.json"

    def fake_restore(path: Path) -> StageCAttestedEvidence:
        restore_calls.append(path)
        if path == final_receipt:
            return target_evidence
        return evidence_by_receipt[str(path)]

    def forbidden_runner(**kwargs: object) -> Path:
        runner_calls.append(kwargs)
        raise AssertionError("complete inflight recovery must not invoke CODE V")

    monkeypatch.setattr(matrix, "trusted_stagec_run_root", lambda: run_root)
    monkeypatch.setattr(matrix, "_publish_stagec_inflight", fake_publish)
    monkeypatch.setattr(matrix, "restore_stagec_attested_evidence", fake_restore)
    monkeypatch.setattr(matrix, "run_stagec_attested", forbidden_runner)

    result = matrix.execute_plan(plan=plan, output_dir=tmp_path)

    assert publish_calls == [(inflight, final)]
    assert final_receipt in restore_calls
    assert runner_calls == []
    assert len(result["runs"]) == 48
    assert result["attempts"][0]["status"] == "attested"
    assert result["attempts"][0]["recovered_after_crash"] is True
    assert not inflight.exists()
    assert final_receipt.is_file()


def test_execute_refuses_final_inflight_quarantine_conflict_without_machine_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, _plan_sha = _plan(tmp_path)
    cell = plan["cells"][0]
    run_id = "conflicted-run"
    run_root = tmp_path / "trusted-runs"
    for package in (
        run_root / run_id,
        run_root / f"{run_id}.inflight",
        run_root / f"{run_id}.quarantine-preserved",
    ):
        package.mkdir(parents=True)
    state = {
        "schema_id": matrix.STATE_SCHEMA,
        "matrix_id": "matrix-test",
        "runs": [],
        "attempts": [
            {
                "status": "started",
                "cell_id": cell["cell_id"],
                "case_id": cell["case_id"],
                "arm": cell["arm"],
                **_cache_state(cell),
                "repeat_index": 1,
                "run_id": run_id,
            }
        ],
    }
    (tmp_path / "matrix-state.json").write_text(json.dumps(state), encoding="utf-8")
    runner_calls: list[dict[str, object]] = []

    def forbidden_runner(**kwargs: object) -> Path:
        runner_calls.append(kwargs)
        raise AssertionError("conflicting packages must fail closed before CODE V")

    monkeypatch.setattr(matrix, "trusted_stagec_run_root", lambda: run_root)
    monkeypatch.setattr(matrix, "run_stagec_attested", forbidden_runner)

    with pytest.raises(RuntimeError, match="automatic CODE V rerun is refused"):
        matrix.execute_plan(plan=plan, output_dir=tmp_path)

    persisted = json.loads((tmp_path / "matrix-state.json").read_text(encoding="utf-8"))
    assert runner_calls == []
    assert persisted["attempts"][0]["status"] == "incomplete"
    assert persisted["attempts"][0]["error"]["type"] == "RecoveryPackageConflict"
    assert len(persisted["attempts"][0]["package_paths"]) == 3


def test_execute_retries_failed_identity_and_fills_only_missing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, plan_sha = _plan(tmp_path)
    evidence_by_receipt: dict[str, StageCAttestedEvidence] = {}
    rows = []
    missing_cell = plan["cells"][-1]
    missing_identity = (missing_cell["cell_id"], 2)
    for cell in plan["cells"]:
        for repeat in (1, 2):
            if (cell["cell_id"], repeat) == missing_identity:
                continue
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=cell["case_id"],
                arm=cell["arm"],
                repeat=repeat,
            )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    state = {
        "schema_id": matrix.STATE_SCHEMA,
        "matrix_id": "matrix-test",
        "runs": rows,
        "attempts": [
            {
                "status": "failed",
                "cell_id": missing_cell["cell_id"],
                "case_id": missing_cell["case_id"],
                "arm": missing_cell["arm"],
                **_cache_state(missing_cell),
                "repeat_index": 2,
                "run_id": "prior-failed-run",
                "duration_seconds": 3.0,
            }
        ],
    }
    (tmp_path / "matrix-state.json").write_text(json.dumps(state), encoding="utf-8")
    calls = []

    def fake_runner(**kwargs: object) -> Path:
        calls.append(kwargs)
        base = _evidence(
            matrix_id="matrix-test",
            plan_sha=plan_sha,
            case_id=missing_cell["case_id"],
            arm=missing_cell["arm"],
            repeat=2,
        )
        run_id = str(kwargs["run_id"])
        evidence = base.model_copy(
            update={
                "run_id": run_id,
                "receipt_sha256": hashlib.sha256(run_id.encode()).hexdigest(),
            }
        )
        receipt = tmp_path / "new-receipt" / "post-run-receipt.json"
        receipt.parent.mkdir(exist_ok=True)
        receipt.write_text("{}", encoding="utf-8")
        evidence_by_receipt[str(receipt)] = evidence
        return receipt

    monkeypatch.setattr(matrix, "run_stagec_attested", fake_runner)
    monkeypatch.setattr(
        matrix, "restore_stagec_attested_evidence", lambda path: evidence_by_receipt[str(path)]
    )

    result = matrix.execute_plan(plan=plan, output_dir=tmp_path)

    assert len(calls) == 1
    assert len(result["runs"]) == 48
    assert result["attempts"][0]["status"] == "failed"
    assert result["attempts"][1]["status"] == "attested"


def test_aggregate_reports_failed_and_incomplete_duration_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, plan_sha = _plan(tmp_path)
    evidence_by_receipt: dict[str, StageCAttestedEvidence] = {}
    rows = []
    for cell in plan["cells"]:
        for repeat in (1, 2):
            evidence = _evidence(
                matrix_id="matrix-test",
                plan_sha=plan_sha,
                case_id=cell["case_id"],
                arm=cell["arm"],
                repeat=repeat,
            )
            receipt = str(Path(f"D:/receipts/{evidence.run_id}.json"))
            evidence_by_receipt[receipt] = evidence
            rows.append(_run_row(evidence, receipt))
    monkeypatch.setattr(
        matrix, "restore_stagec_attested_evidence", lambda path: evidence_by_receipt[str(path)]
    )
    first_cell = plan["cells"][0]
    attempts = [
        {
            "status": "failed",
            "cell_id": first_cell["cell_id"],
            "case_id": first_cell["case_id"],
            "arm": first_cell["arm"],
            **_cache_state(first_cell),
            "repeat_index": 1,
            "run_id": "failed-cost-run",
            "duration_seconds": 4.25,
        },
        {
            "status": "incomplete",
            "cell_id": first_cell["cell_id"],
            "case_id": first_cell["case_id"],
            "arm": first_cell["arm"],
            **_cache_state(first_cell),
            "repeat_index": 1,
            "run_id": "incomplete-cost-run",
            "duration_seconds": None,
        },
    ]

    report = matrix.aggregate(
        plan=plan, state={"runs": rows, "attempts": attempts}, output_dir=tmp_path
    )

    assert report["failed_attempt_count"] == 1
    assert report["incomplete_attempt_count"] == 1
    assert report["failed_incomplete_known_duration_seconds"] == 4.25
    assert report["failed_incomplete_unknown_duration_count"] == 1
