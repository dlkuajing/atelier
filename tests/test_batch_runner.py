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
from app.core.batch_run_lock import BatchRunnerLockHeldError, batch_runner_lock
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


@pytest.fixture(autouse=True)
def _isolated_p18_global_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.core.batch_runner as batch_runner_module

    monkeypatch.setattr(
        batch_runner_module,
        "P18_GLOBAL_WINDOW_ROOT",
        tmp_path / "p18-global-window",
    )


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
        captured.update(
            n=n,
            repeat_runs=repeat_runs,
            artifact_dir=artifact_dir,
            stagec_machine_evidence=kwargs.get("stagec_machine_evidence"),
        )
        return batch_runner_module.CandidateSet(
            target=target,
            candidates=[],
            summary=CandidateSetSummary(
                candidate_count=0,
                mode_counts={},
                ranked_count=0,
                withheld_count=0,
                ri_missing_count=0,
                notes=[],
            ),
        )

    monkeypatch.setattr(batch_runner_module, "orchestrate", _stub_orchestrate)

    engine = RealEngine(n=2, repeat_runs=2)
    target = target_spec_from_entry(_valid_entry(0))
    result = engine.run(target, artifact_dir=tmp_path / "art")

    assert captured["n"] == 2
    assert captured["repeat_runs"] == 2
    assert captured["stagec_machine_evidence"] is False
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
# BLOCKER-1: mode accounting + degraded status (P18 对抗审)
# ---------------------------------------------------------------------------


class _DegradedStubEngine:
    """Test-only engine simulating a real batch whose Mode3/CODE V leg
    silently fell away: it *requests* both modes but delegates to Mode1-only
    orchestration — exactly what `RealEngine` produces on a machine where
    `DEFAULT_CODEV_EXECUTABLE` is missing (TargetConvergedGenerator returns
    `[]` with only a log line, no summary note)."""

    modes_requested = (GenerationMode.RETRIEVED, GenerationMode.TARGET_CONVERGED)
    engine_kind = "real"
    requires_codev_window = True

    def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
        return FakeEngine(n=2).run(target, artifact_dir=artifact_dir)


def test_real_engine_requests_all_registered_modes():
    from app.core.orchestration.orchestrator import _REGISTRY

    assert RealEngine.modes_requested == tuple(_REGISTRY.keys())
    assert GenerationMode.TARGET_CONVERGED in RealEngine.modes_requested


def test_real_engine_cannot_be_relabelled_fake_before_any_ledger_write(
    tmp_path: Path,
) -> None:
    archive = BatchArchive(root=tmp_path / "archive")
    with pytest.raises(ValueError, match="engine mismatch"):
        run_batch(
            engine=RealEngine(n=1),
            archive=archive,
            targets=[_valid_entry(0)],
            engine_name="fake",
        )
    assert archive.list_batches() == []


def test_codev_window_engine_timeout_is_rejected_by_public_api_before_engine_or_ledger(
    tmp_path: Path,
) -> None:
    calls = 0

    class NeverRunRealEngine:
        modes_requested = (GenerationMode.RETRIEVED,)
        engine_kind = "real"
        requires_codev_window = True

        def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
            nonlocal calls
            calls += 1
            raise AssertionError("real timeout preflight must reject before engine startup")

    archive = BatchArchive(root=tmp_path / "archive")
    artifacts = tmp_path / "artifacts"
    with pytest.raises(ValueError, match="job_timeout_sec is forbidden"):
        run_batch(
            engine=NeverRunRealEngine(),
            archive=archive,
            targets=[_valid_entry(0)],
            target_source="direct-api-timeout-refusal",
            job_timeout_sec=0.01,
            artifacts_root=artifacts,
        )

    assert calls == 0
    assert archive.list_batches() == []
    assert not artifacts.exists()


def test_run_batch_exposes_no_global_window_override(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="global_window_root"):
        run_batch(
            engine=FakeEngine(n=1),
            archive=BatchArchive(root=tmp_path / "archive"),
            targets=[_valid_entry(0)],
            global_window_root=tmp_path / "bypass",  # type: ignore[call-arg]
        )


def test_custom_engine_without_closed_execution_contract_fails_before_lock(
    tmp_path: Path,
) -> None:
    class UnclassifiedEngine:
        modes_requested: tuple[GenerationMode, ...] = ()

        def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
            raise AssertionError("unclassified engine must never start")

    archive = BatchArchive(root=tmp_path / "archive")
    with pytest.raises(ValueError, match="closed engine_kind"):
        run_batch(
            engine=UnclassifiedEngine(),  # type: ignore[arg-type]
            archive=archive,
            targets=[_valid_entry(0)],
        )
    assert archive.list_batches() == []


def test_real_batches_with_distinct_archives_share_one_global_window(
    tmp_path: Path,
) -> None:
    calls = 0

    class NeverRunEngine:
        modes_requested = (GenerationMode.RETRIEVED,)
        engine_kind = "real"
        requires_codev_window = True

        def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
            nonlocal calls
            calls += 1
            raise AssertionError("global window contention must fail before engine startup")

    import app.core.batch_runner as batch_runner_module

    window = batch_runner_module.P18_GLOBAL_WINDOW_ROOT
    archive = BatchArchive(root=tmp_path / "other-worktree" / "archive")
    with batch_runner_lock(window), pytest.raises(BatchRunnerLockHeldError):
        run_batch(
            engine=NeverRunEngine(),
            archive=archive,
            targets=[_valid_entry(0)],
            target_source="cross-worktree-window",
            engine_name="real",
        )
    assert calls == 0
    assert archive.list_batches() == []


def test_real_batch_holds_global_window_for_entire_engine_call(tmp_path: Path) -> None:
    import app.core.batch_runner as batch_runner_module

    window = batch_runner_module.P18_GLOBAL_WINDOW_ROOT

    class WindowProbeEngine:
        modes_requested = (GenerationMode.RETRIEVED,)
        engine_kind = "real"
        requires_codev_window = True

        def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
            with pytest.raises(BatchRunnerLockHeldError), batch_runner_lock(window):
                raise AssertionError("real engine ran outside the global window")
            return FakeEngine(n=1).run(target, artifact_dir=artifact_dir)

    summary = run_batch(
        engine=WindowProbeEngine(),
        archive=BatchArchive(root=tmp_path / "archive"),
        targets=[_valid_entry(0)],
        target_source="global-window-lifetime",
        engine_name="real",
        artifacts_root=tmp_path / "artifacts",
    )
    assert len(summary.jobs) == 1
    with batch_runner_lock(window):
        pass


def test_run_batch_books_degraded_when_requested_mode_produces_nothing(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    summary = run_batch(
        engine=_DegradedStubEngine(),
        archive=archive,
        targets=[_valid_entry(0)],
        target_source="unit-degraded",
        engine_name="real",
        artifacts_root=tmp_path / "artifacts",
    )

    job = summary.jobs[0]
    assert job.status == "degraded"  # never a silent succeeded
    assert job.failure is None
    assert job.degradation is not None
    assert "target-converged" in job.degradation
    assert job.result_summary is not None
    assert job.result_summary["modes_requested"] == ["retrieved", "target-converged"]
    assert job.result_summary["modes_present"] == ["retrieved"]
    assert job.result_summary["missing_modes"] == ["target-converged"]
    assert job.result_summary["mode_counts"] == {"retrieved": 2}

    # Crash-safe: reloaded ledger carries the same degradation record.
    reloaded = BatchArchive(root=tmp_path / "archive").get_job(summary.batch.batch_id, job.job_id)
    assert reloaded.status == "degraded"
    assert reloaded.degradation == job.degradation


def test_run_batch_fake_engine_records_full_mode_accounting_no_degradation(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    summary = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        targets=[_valid_entry(0)],
        target_source="unit-modes",
        artifacts_root=tmp_path / "artifacts",
    )

    job = summary.jobs[0]
    assert job.status == "succeeded"
    assert job.degradation is None
    assert job.result_summary is not None
    assert job.result_summary["modes_requested"] == ["retrieved"]
    assert job.result_summary["modes_present"] == ["retrieved"]
    assert job.result_summary["missing_modes"] == []


def test_degraded_is_terminal_for_resume(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    first = run_batch(
        engine=_DegradedStubEngine(),
        archive=archive,
        targets=[_valid_entry(0)],
        target_source="unit-degraded-resume",
        engine_name="real",
        artifacts_root=tmp_path / "artifacts",
    )
    assert first.jobs[0].status == "degraded"

    second = run_batch(
        engine=_DegradedStubEngine(),
        archive=archive,
        resume=True,
        batch_id=first.batch.batch_id,
        engine_name="real",
        artifacts_root=tmp_path / "artifacts",
    )
    # Not silently re-run: same record, untouched created_at.
    assert second.jobs[0].created_at == first.jobs[0].created_at
    assert second.batch.status == "completed"


def test_degraded_zero_candidates_still_books_as_engine_failure(tmp_path: Path):
    """0 candidates outranks degradation: an empty result is a failed job
    (engine category), not a degraded one."""

    class _EmptyStubEngine:
        modes_requested = (GenerationMode.RETRIEVED, GenerationMode.TARGET_CONVERGED)
        engine_kind = "fake"
        requires_codev_window = False

        def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
            entry = {**_valid_entry(0), "fov_deg": None}  # forces 0 retrieval candidates
            return FakeEngine(n=2).run(target_spec_from_entry(entry), artifact_dir=artifact_dir)

    archive = BatchArchive(root=tmp_path / "archive")
    summary = run_batch(
        engine=_EmptyStubEngine(),
        archive=archive,
        targets=[_valid_entry(0)],
        target_source="unit-empty",
        artifacts_root=tmp_path / "artifacts",
    )
    job = summary.jobs[0]
    assert job.status == "failed"
    assert job.failure is not None
    assert job.failure.category == "engine"
    assert job.degradation is None


# ---------------------------------------------------------------------------
# run_batch — full chain with FakeEngine
# ---------------------------------------------------------------------------


def test_run_batch_fake_engine_five_targets_one_injected_failure(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    engine = FakeEngine(n=2)
    targets = [_valid_entry(i) for i in range(5)]
    targets[2] = {
        **targets[2],
        "fov_deg": None,
    }  # injected failure: Mode1 retrieval requires fov_deg

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

    # Artifact paths must be absolute — a reader process (e.g. the
    # /batches/{batch_id} web page) is not guaranteed to share this
    # process's cwd, and a relative path would silently fail to resolve.
    succeeded_job = next(j for j in summary.jobs if j.target_index == 0)
    assert succeeded_job.artifact_dir is not None
    assert Path(succeeded_job.artifact_dir).is_absolute()
    assert succeeded_job.candidate_set_pointer is not None
    assert Path(succeeded_job.candidate_set_pointer).is_absolute()
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
    targets = [
        {"scenario": "smartphone-wide", "efl_mm": 3.5, "fov_deg": 78.0, "image_height_mm": 3.4}
    ]

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

    modes_requested: tuple[GenerationMode, ...] = ()
    engine_kind = "fake"
    requires_codev_window = False

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


def test_run_batch_unexpected_post_engine_error_classified_as_exception(
    tmp_path: Path, monkeypatch
):
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
# MAJOR-3: attempt isolation + stale-running refusal (P18 对抗审)
# ---------------------------------------------------------------------------


def test_jobs_run_in_attempt_subdirectories_with_provenance(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
    summary = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        targets=[_valid_entry(0)],
        target_source="unit-attempt",
        artifacts_root=tmp_path / "artifacts",
    )
    job = summary.jobs[0]
    assert job.attempt == 1
    assert job.artifact_dir is not None
    assert Path(job.artifact_dir).name == "attempt-1"
    assert Path(job.artifact_dir).is_dir()


def test_retry_after_operator_clears_ledger_uses_fresh_attempt_dir(tmp_path: Path):
    """MAJOR-3: after a timeout, the condemned attempt dir is never reused —
    an operator-cleared retry lands in attempt-2 while attempt-1 (where a
    possibly-still-alive orphan thread would write) stays untouched."""
    archive = BatchArchive(root=tmp_path / "archive")
    targets = [_valid_entry(0)]

    first = run_batch(
        engine=_SlowStubEngine(),
        archive=archive,
        targets=targets,
        target_source="unit-retry",
        job_timeout_sec=0.05,
        artifacts_root=tmp_path / "artifacts",
    )
    timed_out = first.jobs[0]
    assert timed_out.status == "failed"
    assert timed_out.failure is not None and timed_out.failure.category == "timeout"
    assert timed_out.attempt == 1
    attempt1_dir = Path(timed_out.artifact_dir)
    assert attempt1_dir.name == "attempt-1"
    marker = attempt1_dir / "orphan-was-here.txt"
    marker.write_text("simulates the un-killable timed-out worker still writing", encoding="utf-8")

    # Operator action: confirm nothing is running, clear the ledger file.
    job_file = tmp_path / "archive" / first.batch.batch_id / "jobs" / "job-0000.json"
    assert job_file.is_file()
    job_file.unlink()

    second = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        resume=True,
        batch_id=first.batch.batch_id,
        artifacts_root=tmp_path / "artifacts",
    )
    retried = second.jobs[0]
    assert retried.status == "succeeded"
    assert retried.attempt == 2
    assert Path(retried.artifact_dir).name == "attempt-2"
    assert Path(retried.artifact_dir) != attempt1_dir
    # The condemned dir (and whatever the orphan wrote into it) is untouched.
    assert marker.is_file()


def test_resume_refuses_stale_running_job(tmp_path: Path):
    """MAJOR-3 fail-closed: a job still marked running is never silently
    retried — resume skips it, records the refusal, and leaves the batch
    resumable instead of claiming completion."""
    from app.core.batch_archive import BatchJobRecord

    archive = BatchArchive(root=tmp_path / "archive")
    targets = [_valid_entry(0), _valid_entry(1)]
    batch = archive.create_batch(target_source="unit-stale", targets=targets, engine="fake")
    stale = BatchJobRecord(
        job_id="job-0000",
        batch_id=batch.batch_id,
        target_index=0,
        target_label="t0",
        target_spec=targets[0],
        status="running",
        created_at="2026-07-11T00:00:00+00:00",
        updated_at="2026-07-11T00:00:00+00:00",
    )
    archive.put_job(stale)

    summary = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        resume=True,
        batch_id=batch.batch_id,
        artifacts_root=tmp_path / "artifacts",
    )

    by_id = {j.job_id: j for j in summary.jobs}
    assert by_id["job-0000"].status == "running"  # untouched, not retried
    assert by_id["job-0000"].updated_at == stale.updated_at
    assert by_id["job-0001"].status == "succeeded"  # the other target still ran
    assert summary.batch.status == "budget_exhausted"  # not "completed" with a stuck job
    assert any("running/queued" in note and "job-0000" in note for note in summary.batch.notes)


def test_cli_rejects_job_timeout_with_real_engine(tmp_path: Path):
    """MAJOR-3 fail-closed: --job-timeout-sec + --engine real is a false
    safety valve (this layer cannot kill a CODE V call) — refused outright,
    nothing runs, nothing is archived."""
    import importlib.util

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "p18_night_batch.py"
    spec = importlib.util.spec_from_file_location("p18_night_batch_cli_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    exit_code = module.main(
        [
            "--engine",
            "real",
            "--job-timeout-sec",
            "5",
            "--archive-dir",
            str(tmp_path / "archive"),
        ]
    )
    assert exit_code == 2
    assert not (tmp_path / "archive").exists()  # nothing was created


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


def test_resume_engine_mismatch_refused(tmp_path: Path):
    """MAJOR-4 (P18 对抗审): resuming a batch with a different engine than
    the one recorded at creation is refused — the ledger must never claim
    engine=X while jobs actually ran on engine=Y."""
    archive = BatchArchive(root=tmp_path / "archive")
    first = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        targets=[_valid_entry(0), _valid_entry(1)],
        target_source="unit-engine",
        engine_name="fake",
        max_jobs=1,
        artifacts_root=tmp_path / "artifacts",
    )
    assert first.batch.status == "budget_exhausted"

    with pytest.raises(ValueError, match="engine mismatch"):
        run_batch(
            engine=FakeEngine(n=2),
            archive=archive,
            resume=True,
            batch_id=first.batch.batch_id,
            engine_name="real",
            artifacts_root=tmp_path / "artifacts",
        )
    # Nothing was run/written by the refused resume.
    assert len(archive.list_jobs(first.batch.batch_id)) == 1


def test_job_records_carry_actual_engine_name(tmp_path: Path):
    """MAJOR-4: every job snapshot records which engine actually ran it."""
    archive = BatchArchive(root=tmp_path / "archive")
    targets = [_valid_entry(0)]
    targets[0] = {**targets[0]}
    summary = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        targets=targets,
        target_source="unit-engine-stamp",
        engine_name="fake",
        artifacts_root=tmp_path / "artifacts",
    )
    assert summary.jobs[0].engine == "fake"

    # Preflight-failed jobs are stamped too.
    archive2 = BatchArchive(root=tmp_path / "archive2")
    bad = run_batch(
        engine=FakeEngine(n=2),
        archive=archive2,
        targets=[{"scenario": "smartphone-wide"}],  # missing fnum -> preflight
        target_source="unit-engine-stamp-preflight",
        engine_name="fake",
        artifacts_root=tmp_path / "artifacts2",
    )
    assert bad.jobs[0].status == "failed"
    assert bad.jobs[0].engine == "fake"


def test_cli_resume_engine_mismatch_exits_2(tmp_path: Path):
    import importlib.util

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "p18_night_batch.py"
    spec = importlib.util.spec_from_file_location("p18_night_batch_cli_test_m4", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    archive = BatchArchive(root=tmp_path / "archive")
    first = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        targets=[_valid_entry(0)],
        target_source="unit-cli-m4",
        engine_name="fake",
        artifacts_root=tmp_path / "artifacts",
    )

    exit_code = module.main(
        [
            "--engine",
            "real",
            "--resume",
            "--batch-id",
            first.batch.batch_id,
            "--archive-dir",
            str(tmp_path / "archive"),
        ]
    )
    assert exit_code == 2


def test_resume_without_batch_id_raises(tmp_path: Path):
    archive = BatchArchive(root=tmp_path / "archive")
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
        engine=engine,
        archive=archive,
        targets=targets,
        target_source="unit-2",
        artifacts_root=tmp_path / "artifacts",
    )
    assert first.batch.status == "completed"

    # Resuming an already-completed batch with zero pending targets is a no-op.
    second = run_batch(
        engine=engine,
        archive=archive,
        resume=True,
        batch_id=first.batch.batch_id,
        artifacts_root=tmp_path / "artifacts",
    )
    assert second.batch.status == "completed"
    assert len(second.jobs) == 2


# ---------------------------------------------------------------------------
# MINOR-5: CLI numeric-argument guards (P18 对抗审)
# ---------------------------------------------------------------------------


def _load_cli_module():
    import importlib.util

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "p18_night_batch.py"
    spec = importlib.util.spec_from_file_location("p18_night_batch_cli_test_m5", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "argv",
    [
        ["--engine", "fake", "--sample-n", "0"],
        ["--engine", "fake", "--sample-n", "-3"],
        ["--engine", "fake", "--max-jobs", "0"],
        ["--engine", "fake", "--max-wall-min", "0"],
        ["--engine", "fake", "--max-wall-min", "-1.5"],
        ["--engine", "fake", "--max-wall-min", "inf"],
        ["--engine", "fake", "--job-timeout-sec", "0"],
        ["--engine", "fake", "--job-timeout-sec", "nan"],
        ["--engine", "fake", "--n", "0"],
        ["--engine", "fake", "--repeat-runs", "0"],
        ["--engine", "fake", "--repeat-runs", "4"],
    ],
)
def test_cli_rejects_non_positive_numeric_args(argv: list[str], tmp_path: Path):
    module = _load_cli_module()
    with pytest.raises(SystemExit) as exc_info:
        module.main([*argv, "--archive-dir", str(tmp_path / "archive")])
    assert exc_info.value.code == 2  # argparse usage error
    assert not (tmp_path / "archive").exists()  # nothing ran, nothing written


def test_target_entry_error_message_surfaces_pydantic_validation_error():
    entry = {"scenario": "not-a-real-scenario", "fnum": 2.0}
    with pytest.raises(TargetEntryError):
        target_spec_from_entry(entry)
    # sanity: constructing TargetSpec directly with a bad scenario also raises
    with pytest.raises(ValidationError):
        TargetSpec(scenario="not-a-real-scenario", fnum=2.0)  # type: ignore[arg-type]
