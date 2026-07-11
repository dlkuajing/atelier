"""P18-2: night batch queue — target list -> per-job orchestration -> the
P18-1 archive ledger, with honest failure classification, budget cutoffs,
and crash-safe resume. See `scripts/p18_night_batch.py` for the CLI.

**Engine injection (batch brief 交付2 "禁跑 CODE V")**: two `BatchEngine`
implementations.

- `FakeEngine` runs `orchestrate(..., modes=[GenerationMode.RETRIEVED])`
  (Mode1 only) — genuine case-library retrieval + Optiland scoring, not
  fabricated data, but structurally zero CODE V dependency
  (`RetrievalGenerator` never imports `codev_batch`/`codev_optimize`, see
  its docstring in `app/core/orchestration/generators.py`). Safe to run on
  any machine regardless of what's installed, fast, and exercises the real
  orchestrate -> scorecard -> archive pipeline end to end. This is what the
  full-chain tests in `tests/test_batch_runner.py` use — they never touch a
  real CODE V process.
- `RealEngine` runs `orchestrate()`'s default modes (Mode1 + Mode3). Mode3
  invokes real CODE V when `DEFAULT_CODEV_EXECUTABLE` is present. This is
  what the loop orchestrator runs during a scheduled CODE V window
  (`--engine real`) — this module's own test suite never invokes it.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from app.core.batch_archive import (
    BatchArchive,
    BatchJobFailure,
    BatchJobRecord,
    BatchRecord,
)
from app.core.config import settings
from app.core.orchestration.candidate import CandidateSet, GenerationMode, TargetSpec
from app.core.orchestration.orchestrator import DEFAULT_N, orchestrate

_TARGET_SPEC_FIELDS = frozenset(TargetSpec.model_fields.keys())
_TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed"})


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Target-entry parsing (shared by both engines and every CLI target source)
# ---------------------------------------------------------------------------


class TargetEntryError(ValueError):
    """Raised when a raw target-list entry fails to become a valid
    `TargetSpec` — the batch runner's preflight failure category."""


def target_spec_from_entry(entry: Mapping[str, object]) -> TargetSpec:
    """Pick the `TargetSpec` fields out of a raw entry, ignoring extra
    provenance keys (`sweet-zone-topic-set.json` carries `seed_case_id` /
    `seed_native_efl_mm` / `delta_efl_pct` / `band` alongside the target
    fields — none of those are `TargetSpec` fields, all safely dropped
    here). Raises `TargetEntryError` (not a bare `ValidationError`) so
    callers have one exception type to catch for the preflight failure
    category."""
    fields = {k: v for k, v in entry.items() if k in _TARGET_SPEC_FIELDS}
    try:
        return TargetSpec(**fields)
    except ValidationError as exc:
        raise TargetEntryError(str(exc)) from exc


def target_label_from_entry(entry: Mapping[str, object], index: int) -> str:
    for key in ("label", "seed_case_id"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            return value
    return f"target-{index:04d}"


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EngineRunResult:
    candidate_set: CandidateSet


class BatchEngine(Protocol):
    def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult: ...


class FakeEngine:
    """Mode1-only real orchestration — see module docstring. `n` mirrors
    `orchestrate`'s own `n` (candidates per target)."""

    def __init__(self, *, n: int = DEFAULT_N) -> None:
        self.n = n

    def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        candidate_set = orchestrate(target, target, n=self.n, modes=[GenerationMode.RETRIEVED])
        return EngineRunResult(candidate_set=candidate_set)


class RealEngine:
    """Full orchestration (Mode1 + Mode3, `orchestrate`'s default modes) —
    see module docstring. Never invoked by this repo's own test suite."""

    def __init__(self, *, n: int = DEFAULT_N, repeat_runs: int = 1) -> None:
        self.n = n
        self.repeat_runs = repeat_runs

    def run(self, target: TargetSpec, *, artifact_dir: Path) -> EngineRunResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        candidate_set = orchestrate(
            target, target, n=self.n, repeat_runs=self.repeat_runs, artifact_dir=artifact_dir
        )
        return EngineRunResult(candidate_set=candidate_set)


# ---------------------------------------------------------------------------
# Honest per-job outcome classification
# ---------------------------------------------------------------------------


def _engine_result_failure_reason(candidate_set: CandidateSet) -> str | None:
    """Mirrors `scripts/c1_orchestrate.py::_requirement_failed`: a job
    counts as a failed attempt when its generator crashed (recorded in
    `summary.notes`) or it produced zero candidates outright — either way
    there is nothing (or nothing trustworthy) in the archive for this
    target. Returns the human reason, or `None` for a genuine (possibly
    withheld, possibly imperfect, but non-empty) result."""
    summary = candidate_set.summary
    if summary.candidate_count == 0:
        return "batch produced 0 candidates for this target"
    failing_notes = [n for n in summary.notes if "generator=" in n and "失败" in n]
    if failing_notes:
        return "; ".join(failing_notes)
    return None


def _result_summary(candidate_set: CandidateSet) -> dict[str, object]:
    s = candidate_set.summary
    return {
        "candidate_count": s.candidate_count,
        "ranked_count": s.ranked_count,
        "withheld_count": s.withheld_count,
        "ri_missing_count": s.ri_missing_count,
        "notes": list(s.notes),
    }


def _run_engine_with_timeout(
    engine: BatchEngine,
    target: TargetSpec,
    *,
    artifact_dir: Path,
    timeout_sec: float | None,
) -> EngineRunResult:
    """`timeout_sec=None` (the default) runs inline with no timeout guard.
    Otherwise runs the engine on a worker thread and raises
    `concurrent.futures.TimeoutError` if it doesn't finish in time — note
    Python cannot forcibly kill the worker thread, so a timed-out engine
    call keeps running in the background; this is a known limitation (see
    the batch brief's 夜批真跑风险清单), acceptable here because it only
    stops the *runner* from waiting, it never corrupts the ledger (the
    orphaned thread's eventual result, if any, is simply never persisted)."""
    if timeout_sec is None:
        return engine.run(target, artifact_dir=artifact_dir)
    # Deliberately not a `with ThreadPoolExecutor() as pool:` block: that
    # context manager's `__exit__` calls `shutdown(wait=True)`, which would
    # block until the (still-running, un-killable) worker thread finishes —
    # defeating the point of raising `TimeoutError` promptly. `wait=False`
    # lets this call return immediately; the orphaned thread finishes (or
    # not) on its own, its eventual result simply never observed/persisted.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(engine.run, target, artifact_dir=artifact_dir)
    try:
        return future.result(timeout=timeout_sec)
    finally:
        pool.shutdown(wait=False)


def _run_one_target(
    *,
    batch: BatchRecord,
    archive: BatchArchive,
    engine: BatchEngine,
    index: int,
    entry: Mapping[str, object],
    job_timeout_sec: float | None,
    artifacts_root: Path,
) -> BatchJobRecord:
    job_id = f"job-{index:04d}"
    label = target_label_from_entry(entry, index)
    common = {
        "job_id": job_id,
        "batch_id": batch.batch_id,
        "target_index": index,
        "target_label": label,
        "target_spec": dict(entry),
        "created_at": _utc_now_iso(),
    }

    # -- preflight --
    try:
        target = target_spec_from_entry(entry)
    except TargetEntryError as exc:
        record = BatchJobRecord(
            **common,
            status="failed",
            updated_at=_utc_now_iso(),
            failure=BatchJobFailure(category="preflight", message=str(exc)),
        )
        archive.put_job(record)
        return record

    artifact_dir = artifacts_root / batch.batch_id / job_id
    archive.put_job(
        BatchJobRecord(
            **common, status="running", updated_at=_utc_now_iso(), artifact_dir=str(artifact_dir)
        )
    )

    try:
        result = _run_engine_with_timeout(
            engine, target, artifact_dir=artifact_dir, timeout_sec=job_timeout_sec
        )
    except concurrent.futures.TimeoutError:
        record = BatchJobRecord(
            **common,
            status="failed",
            updated_at=_utc_now_iso(),
            artifact_dir=str(artifact_dir),
            failure=BatchJobFailure(category="timeout", message=f"exceeded {job_timeout_sec}s"),
        )
        archive.put_job(record)
        return record
    except Exception as exc:  # noqa: BLE001 - the engine itself failed; classify & record, never crash the batch loop
        record = BatchJobRecord(
            **common,
            status="failed",
            updated_at=_utc_now_iso(),
            artifact_dir=str(artifact_dir),
            failure=BatchJobFailure(category="engine", message=f"{type(exc).__name__}: {exc}"),
        )
        archive.put_job(record)
        return record

    artifact_dir.mkdir(parents=True, exist_ok=True)
    candidate_set_path = artifact_dir / "candidate_set.json"
    candidate_set_path.write_text(
        json.dumps(result.candidate_set.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failure_reason = _engine_result_failure_reason(result.candidate_set)
    record = BatchJobRecord(
        **common,
        status="failed" if failure_reason is not None else "succeeded",
        updated_at=_utc_now_iso(),
        result_summary=_result_summary(result.candidate_set),
        candidate_set_pointer=str(candidate_set_path),
        artifact_dir=str(artifact_dir),
        failure=BatchJobFailure(category="engine", message=failure_reason)
        if failure_reason is not None
        else None,
    )
    archive.put_job(record)
    return record


def _run_one_target_safe(
    *,
    batch: BatchRecord,
    archive: BatchArchive,
    engine: BatchEngine,
    index: int,
    entry: Mapping[str, object],
    job_timeout_sec: float | None,
    artifacts_root: Path,
) -> BatchJobRecord:
    """Last-resort safety net around `_run_one_target`: anything unexpected
    in the runner's *own* orchestration code (disk I/O, serialization —
    never the engine itself, which `_run_one_target` already classifies as
    `engine`) is caught here as `exception`, so one target's bug can never
    take down the whole night's batch."""
    try:
        return _run_one_target(
            batch=batch,
            archive=archive,
            engine=engine,
            index=index,
            entry=entry,
            job_timeout_sec=job_timeout_sec,
            artifacts_root=artifacts_root,
        )
    except Exception as exc:  # noqa: BLE001 - catch-all safety net, see docstring
        record = BatchJobRecord(
            job_id=f"job-{index:04d}",
            batch_id=batch.batch_id,
            target_index=index,
            target_label=target_label_from_entry(entry, index),
            target_spec=dict(entry),
            status="failed",
            created_at=_utc_now_iso(),
            updated_at=_utc_now_iso(),
            failure=BatchJobFailure(category="exception", message=f"{type(exc).__name__}: {exc}"),
        )
        with contextlib.suppress(Exception):  # archive itself is broken; nothing left to persist, still return honestly
            archive.put_job(record)
        return record


# ---------------------------------------------------------------------------
# run_batch — the whole loop
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchRunSummary:
    batch: BatchRecord
    jobs: list[BatchJobRecord]
    budget_exhausted: bool


def run_batch(
    *,
    engine: BatchEngine,
    archive: BatchArchive,
    targets: Sequence[Mapping[str, object]] | None = None,
    target_source: str = "",
    batch_id: str | None = None,
    resume: bool = False,
    max_jobs: int | None = None,
    max_wall_min: float | None = None,
    job_timeout_sec: float | None = None,
    engine_name: str = "fake",
    artifacts_root: Path | None = None,
) -> BatchRunSummary:
    """Run (or resume) one batch. Every target is attempted at most once per
    batch — a job's `target_index` and deterministic `job_id` (`job-NNNN`)
    are the resume key.

    Resume (`resume=True`) reloads the frozen target list from disk
    (`archive.get_targets`, written once at `create_batch` time) rather than
    trusting the caller's `targets`/`target_source` again — so a later
    `--resume` invocation always replays the exact same indexed set even if
    it's given different (or no) `--targets`/`--sample-n` flags. Only
    targets whose existing job record is *terminal* (`succeeded`/`failed`)
    are skipped; a job stuck at `running` (e.g. the process was killed
    mid-engine-call) is re-attempted — `put_job` overwrites are idempotent.

    `max_jobs` caps how many *new* jobs this single invocation starts;
    `max_wall_min` stops starting new jobs once that many minutes have
    elapsed since this call began (an in-flight job is never interrupted —
    the cutoff is checked only between jobs). Either limit leaves
    `batch.status="budget_exhausted"` rather than `"completed"`, with a note
    recording exactly how far the batch got, so a later `--resume` knows to
    continue.
    """
    if resume:
        if batch_id is None:
            raise ValueError("run_batch: resume=True 需要提供 batch_id")
        batch = archive.get_batch(batch_id)
        resolved_targets = archive.get_targets(batch_id)
    else:
        if targets is None:
            raise ValueError("run_batch: 非 resume 模式需要提供 targets")
        batch = archive.create_batch(
            target_source=target_source,
            targets=targets,
            engine=engine_name,
            batch_id=batch_id,
        )
        resolved_targets = list(targets)

    # `.resolve()` (not just the join) matters: `settings.job_artifacts_dir`
    # defaults to the *relative* `Path("var/job-artifacts")`, and the process
    # that later reads `job.artifact_dir`/`candidate_set_pointer` off disk
    # (the `/batches/{batch_id}` web page, in particular) is not guaranteed
    # to share this process's cwd. A relative path stored in the archive
    # would silently resolve to nothing (or the wrong directory) from a
    # different cwd — storing an absolute path makes every downstream reader
    # cwd-independent.
    resolved_artifacts_root = (
        artifacts_root if artifacts_root is not None else (settings.job_artifacts_dir / "batches")
    ).resolve()

    completed_indices = {
        job.target_index
        for job in archive.list_jobs(batch.batch_id)
        if job.status in _TERMINAL_JOB_STATUSES
    }
    pending_indices = [i for i in range(len(resolved_targets)) if i not in completed_indices]

    started_at = time.monotonic()
    budget_exhausted = False

    for attempt_count, index in enumerate(pending_indices, start=1):
        if max_jobs is not None and attempt_count > max_jobs:
            budget_exhausted = True
            break
        if max_wall_min is not None and (time.monotonic() - started_at) / 60.0 > max_wall_min:
            budget_exhausted = True
            break
        _run_one_target_safe(
            batch=batch,
            archive=archive,
            engine=engine,
            index=index,
            entry=resolved_targets[index],
            job_timeout_sec=job_timeout_sec,
            artifacts_root=resolved_artifacts_root,
        )

    all_jobs = archive.list_jobs(batch.batch_id)
    incomplete = len(all_jobs) < len(resolved_targets)
    notes = list(batch.notes)
    if budget_exhausted:
        notes.append(
            f"budget exhausted this run (max_jobs={max_jobs}, max_wall_min={max_wall_min}): "
            f"{len(all_jobs)}/{len(resolved_targets)} targets have a job record so far — "
            "resume with --resume to continue"
        )
    final_status = "budget_exhausted" if incomplete else "completed"
    updated_batch = archive.update_batch(batch.batch_id, status=final_status, notes=notes)

    return BatchRunSummary(batch=updated_batch, jobs=all_jobs, budget_exhausted=budget_exhausted)
