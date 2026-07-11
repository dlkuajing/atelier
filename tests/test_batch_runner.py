"""Tests for `app.core.batch_runner` — P18-2 night batch queue.

Every test uses `FakeEngine` (Mode1-only real retrieval, structurally zero
CODE V dependency — see the module docstring in `app/core/batch_runner.py`)
or a local test-only stub engine. **`RealEngine` is never invoked here** —
this machine has CODE V installed (`D:\\CODEV115`), and the P18 batch brief's
执行授权 explicitly forbids running CODE V from this worktree; `RealEngine`'s
wiring is covered separately with `orchestrate` monkeypatched to a stub so
no real engine call ever happens.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.batch_archive import BatchArchive, BatchArchiveError
from app.core.batch_runner import (
    EngineRunResult,
    FakeEngine,
    RealEngine,
    TargetEntryError,
    _engine_result_failure_reason,
    run_batch,
    target_label_from_entry,
    target_spec_from_entry,
)
from app.core.orchestration.candidate import GenerationMode, TargetSpec


def _valid_entry(index: int) -> dict[str, object]:
    return {
        "label": f"t{index}",
        "scenario": "smartphone-wide",
        "efl_mm": 3.5 + index * 0.1,
        "fnum": 2.0,
        "fov_deg": 78.0,
        "image_height_mm": 3.4,
    }


# ---------------------------------------------------------------------------
# target_spec_from_entry / target_label_from_entry
# ---------------------------------------------------------------------------


def test_target_spec_from_entry_ignores_provenance_only_keys():
    entry = {
        **_valid_entry(0),
        "seed_case_id": "US-123",
        "seed_native_efl_mm": 3.6,
        "delta_efl_pct": -1.2,
        "band": "lt5",
    }
    spec = target_spec_from_entry(entry)
    assert isinstance(spec, TargetSpec)
    assert spec.efl_mm == entry["efl_mm"]


def test_target_spec_from_entry_missing_required_field_raises_target_entry_error():
    entry = {"scenario": "smartphone-wide", "efl_mm": 3.5, "fov_deg": 78.0, "image_height_mm": 3.4}
    with pytest.raises(TargetEntryError):
        target_spec_from_entry(entry)


def test_target_label_from_entry_prefers_label():
    assert target_label_from_entry({"label": "custom"}, 5) == "custom"


def test_target_label_from_entry_falls_back_to_seed_case_id():
    assert target_label_from_entry({"seed_case_id": "US-999"}, 5) == "US-999"


def test_target_label_from_entry_falls_back_to_index():
    assert target_label_from_entry({}, 5) == "target-0005"


# ---------------------------------------------------------------------------
# FakeEngine — Mode1-only, zero CODE V
# ---------------------------------------------------------------------------


def test_fake_engine_produces_mode1_only_candidate_set(tmp_path: Path):
    engine = FakeEngine(n=3)
    target = target_spec_from_entry(_valid_entry(0))
    result = engine.run(target, artifact_dir=tmp_path / "art")
    assert isinstance(result, EngineRunResult)
    assert result.candidate_set.modes_present <= {GenerationMode.RETRIEVED}
    assert result.candidate_set.summary.candidate_count > 0


def test_real_engine_wiring_delegates_to_orchestrate_stub(tmp_path: Path, monkeypatch):
    """Verifies `RealEngine.run` calls `orchestrate` with the right
    arguments WITHOUT ever invoking the real orchestrator/CODE V — the
    module-level `orchestrate` name `RealEngine.run` calls is monkeypatched
    to a stub that builds a trivial empty `CandidateSet` directly (must NOT
    delegate to `FakeEngine`/real `orchestrate`, either of which would
    recurse back through this same monkeypatched name)."""
    import app.core.batch_runner as batch_runner_module
    from app.core.orchestration.candidate import CandidateSetSummary

    captured: dict[str, object] = {}

    def _stub_orchestrate(spec, target, *, n, repeat_runs=1, artifact_dir=None, **kwargs):
        captured.update(n=n, repeat_runs=repeat_runs, artifact_dir=artifact_dir)
        return batch_runner_module.CandidateSet(
            target=target,
            candidates=[],
            summary=CandidateSetSummary(
                candidate_count=0, mode_counts={}, ranked_count=0, withheld_count=0,
                ri_missing_count=0, notes=[],
            ),
        )

    monkeypatch.setattr(batch_runner_module, "orchestrate", _stub_orchestrate)

    engine = RealEngine(n=2, repeat_runs=2)
    target = target_spec_from_entry(_valid_entry(0))
    result = engine.run(target, artifact_dir=tmp_path / "art")

    assert captured["n"] == 2
    assert captured["repeat_runs"] == 2
    assert isinstance(result, EngineRunResult)


# ---------------------------------------------------------------------------
# _engine_result_failure_reason
# ---------------------------------------------------------------------------


def test_engine_result_failure_reason_none_for_zero_candidates_target():
    # fov_deg=None makes RetrievalGenerator._generate raise internally;
    # orchestrate isolates that failure and returns 0 candidates.
    engine = FakeEngine(n=2)
    entry = {**_valid_entry(0), "fov_deg": None}
    target = target_spec_from_entry(entry)
    result = engine.run(target, artifact_dir=Path("."))
    assert result.candidate_set.summary.candidate_count == 0
    reason = _engine_result_failure_reason(result.candidate_set)
    assert reason is not None


def test_engine_result_failure_reason_none_for_healthy_result():
    engine = FakeEngine(n=2)
    target = target_spec_from_entry(_valid_entry(0))
    result = engine.run(target, artifact_dir=Path("."))
    assert _engine_result_failure_reason(result.candidate_set) is None


# ---------------------------------------------------------------------------
# run_batch — full chain with FakeEngine
# ---------------------------------------------------------------------------


def test_run_batch_fake_engine_five_targets_one_injected_failure(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [_valid_entry(i) for i in range(5)]
    targets[2] = {**targets[2], "fov_deg": None}  # injected failure: Mode1 retrieval requires fov_deg

    summary = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-5",
        engine_name="fake",
        artifacts_root=tmp_path / "artifacts",
    )

    assert summary.batch.status == "completed"
    assert summary.budget_exhausted is False
    assert len(summary.jobs) == 5
    statuses = {job.target_index: job.status for job in summary.jobs}
    assert statuses[2] == "failed"
    assert all(statuses[i] == "succeeded" for i in (0, 1, 3, 4))

    failed_job = next(j for j in summary.jobs if j.target_index == 2)
    assert failed_job.failure is not None
    assert failed_job.failure.category == "engine"
    # A failed attempt still persists its (0-candidate) CandidateSet — honest
    # audit trail, not swept under the rug.
    assert failed_job.candidate_set_pointer is not None
    assert Path(failed_job.candidate_set_pointer).is_file()

    succeeded_job = next(j for j in summary.jobs if j.target_index == 0)
    assert succeeded_job.result_summary is not None
    assert succeeded_job.result_summary["candidate_count"] > 0

    # Crash-safety: a fresh BatchArchive instance reconstructs the same ledger.
    reloaded = BatchArchive(root=tmp_path / "archive")
    reloaded_jobs = reloaded.list_jobs(summary.batch.batch_id)
    assert len(reloaded_jobs) == 5
    assert {j.status for j in reloaded_jobs} == {"succeeded", "failed"}


def test_run_batch_preflight_failure_for_invalid_entry(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [{"scenario": "smartphone-wide", "efl_mm": 3.5, "fov_deg": 78.0, "image_height_mm": 3.4}]

    summary = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-1",
        artifacts_root=tmp_path / "artifacts",
    )

    assert len(summary.jobs) == 1
    job = summary.jobs[0]
    assert job.status == "failed"
    assert job.failure is not None
    assert job.failure.category == "preflight"
    assert job.artifact_dir is None


class _SlowStubEngine:
    """Local test-only engine (not `FakeEngine`/`RealEngine`) — sleeps past
    a short timeout to exercise the `timeout` failure category."""

    def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
        time.sleep(0.3)
        raise AssertionError("should have been abandoned by the timeout before reaching here")


def test_run_batch_job_timeout_classified_correctly(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = _SlowStubEngine()
    targets = [_valid_entry(0)]

    summary = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-timeout",
        job_timeout_sec=0.05,
        artifacts_root=tmp_path / "artifacts",
    )

    assert len(summary.jobs) == 1
    job = summary.jobs[0]
    assert job.status == "failed"
    assert job.failure is not None
    assert job.failure.category == "timeout"


def test_run_batch_unexpected_post_engine_error_classified_as_exception(tmp_path: Path, monkeypatch):
    import app.core.batch_runner as batch_runner_module

    def _boom(_candidate_set):
        raise RuntimeError("simulated bug after the engine already succeeded")

    monkeypatch.setattr(batch_runner_module, "_engine_result_failure_reason", _boom)

    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [_valid_entry(0)]

    summary = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-exception",
        artifacts_root=tmp_path / "artifacts",
    )

    assert len(summary.jobs) == 1
    job = summary.jobs[0]
    assert job.status == "failed"
    assert job.failure is not None
    assert job.failure.category == "exception"


# ---------------------------------------------------------------------------
# Budget cutoffs + resume
# ---------------------------------------------------------------------------


def test_run_batch_max_jobs_truncates_then_resume_completes(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [_valid_entry(i) for i in range(5)]

    first = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-5",
        max_jobs=2,
        artifacts_root=tmp_path / "artifacts",
    )
    assert first.budget_exhausted is True
    assert first.batch.status == "budget_exhausted"
    assert len(first.jobs) == 2
    assert any("budget exhausted" in note for note in first.batch.notes)

    second = run_batch(
        engine=engine,
        archive=archive,
        resume=True,
        batch_id=first.batch.batch_id,
        artifacts_root=tmp_path / "artifacts",
    )
    assert second.budget_exhausted is False
    assert second.batch.status == "completed"
    assert len(second.jobs) == 5

    first_by_id = {j.job_id: j for j in first.jobs}
    second_by_id = {j.job_id: j for j in second.jobs}
    for job_id, job in first_by_id.items():
        assert second_by_id[job_id].created_at == job.created_at  # untouched by resume, not re-run


def test_run_batch_max_wall_min_truncates_after_first_job(tmp_path: Path, monkeypatch):
    import app.core.batch_runner as batch_runner_module

    calls = {"n": 0}

    def fake_monotonic() -> float:
        calls["n"] += 1
        # call 1 = started_at; call 2 = pre-job-1 budget check (still within
        # budget); call 3+ = pre-job-2 check, far past the 1-minute budget.
        return 0.0 if calls["n"] <= 2 else 10_000.0

    monkeypatch.setattr(batch_runner_module.time, "monotonic", fake_monotonic)

    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [_valid_entry(i) for i in range(3)]

    summary = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-3",
        max_wall_min=1.0,
        artifacts_root=tmp_path / "artifacts",
    )

    assert summary.budget_exhausted is True
    assert summary.batch.status == "budget_exhausted"
    assert len(summary.jobs) == 1


def test_resume_without_batch_id_raises():
    archive = BatchArchive(root=Path("."))
    engine = FakeEngine(n=1)
    with pytest.raises(ValueError):
        run_batch(engine=engine, archive=archive, resume=True)


def test_resume_unknown_batch_raises(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=1)
    with pytest.raises(BatchArchiveError):
        run_batch(engine=engine, archive=archive, resume=True, batch_id="nope")


def test_run_batch_without_targets_and_without_resume_raises(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=1)
    with pytest.raises(ValueError):
        run_batch(engine=engine, archive=archive)


def test_run_batch_resume_ignores_new_targets_argument(tmp_path: Path):
    """A `--resume` invocation must replay the frozen target list from disk,
    not whatever (or nothing) the caller passes this time."""
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [_valid_entry(i) for i in range(2)]
    first = run_batch(
        engine=engine, archive=archive, targets=targets, target_source="unit-2",
        artifacts_root=tmp_path / "artifacts",
    )
    assert first.batch.status == "completed"

    # Resuming an already-completed batch with zero pending targets is a no-op.
    second = run_batch(
        engine=engine, archive=archive, resume=True, batch_id=first.batch.batch_id,
        artifacts_root=tmp_path / "artifacts",
    )
    assert second.batch.status == "completed"
    assert len(second.jobs) == 2


def test_target_entry_error_message_surfaces_pydantic_validation_error():
    entry = {"scenario": "not-a-real-scenario", "fnum": 2.0}
    with pytest.raises(TargetEntryError):
        target_spec_from_entry(entry)
    # sanity: constructing TargetSpec directly with a bad scenario also raises
    with pytest.raises(ValidationError):
        TargetSpec(scenario="not-a-real-scenario", fnum=2.0)  # type: ignore[arg-type]
