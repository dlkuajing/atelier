"""In-memory background job store for deep-engine tasks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import uuid4

from app.core.engines import DeepEngine


class JobStatus(StrEnum):
    """Lifecycle states for one in-memory background job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED})


class JobNotFoundError(KeyError):
    """Raised when a job id is not present in the in-memory store."""


#: Lane every engine runs on unless it declares a `seat_lane` attribute (or the
#: caller passes an explicit `lane` to `submit`). Preserves the pre-lane
#: behavior for every existing engine: same lane = one shared serialized seat.
DEFAULT_SEAT_LANE = "default"

#: Lane shared by everything that drives a real CODE V process. CODE V is a
#: single-instance tool on the demo machine (iron rule): a C1 orchestration
#: batch and a raw `/api/optical/jobs` deep job must serialize against each
#: other on this lane — while staying off the default lane so multi-minute
#: CODE V work never freezes the instant demo path (ResultSummaryEngine /
#: ExecutiveSummaryEngine jobs keep their own seat).
CODEV_SEAT_LANE = "codev"


@dataclass(frozen=True)
class JobRecord:
    """Serializable snapshot of one background job."""

    job_id: str
    engine: str
    status: JobStatus
    payload: dict[str, object]
    result: dict[str, object] | None = None
    error: str | None = None


class JobStore:
    """Run deep-engine submissions in asyncio background tasks and keep snapshots.

    Seats are per lane: jobs on the same lane run strictly serialized (one
    semaphore seat per lane — the CODE V single-instance iron rule lives on
    the `CODEV_SEAT_LANE`), while jobs on different lanes run concurrently, so
    a multi-minute CODE V batch cannot freeze the sub-second demo lane.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._seats: dict[str, asyncio.Semaphore] = {}
        self._subscribers: dict[str, set[asyncio.Queue[JobRecord]]] = {}

    def _seat(self, lane: str) -> asyncio.Semaphore:
        seat = self._seats.get(lane)
        if seat is None:
            seat = asyncio.Semaphore(1)
            self._seats[lane] = seat
        return seat

    def submit(
        self,
        engine: DeepEngine,
        payload: Mapping[str, object],
        *,
        lane: str | None = None,
        job_id: str | None = None,
    ) -> str:
        """Create a job and schedule the engine submission on the running event loop.

        The seat lane resolves in order: explicit `lane` argument (boundary
        code that resolves engines it does not own, e.g. the raw
        `/api/optical/jobs` path pinning probe-resolved CODE V engines to
        `CODEV_SEAT_LANE`) > the engine's own `seat_lane` attribute >
        `DEFAULT_SEAT_LANE`.
        """
        payload_copy = dict(payload)
        job_id = job_id or uuid4().hex
        if job_id in self._jobs:
            raise ValueError(f"job id already exists: {job_id}")
        resolved_lane = lane if lane is not None else getattr(engine, "seat_lane", DEFAULT_SEAT_LANE)
        self._jobs[job_id] = JobRecord(
            job_id=job_id,
            engine=engine.name,
            status=JobStatus.QUEUED,
            payload=payload_copy,
        )
        self._tasks[job_id] = asyncio.create_task(
            self._run(job_id, engine, payload_copy, resolved_lane)
        )
        self._publish(job_id)
        return job_id

    def get(self, job_id: str) -> JobRecord:
        """Return the latest snapshot for a job."""
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc

    def status(self, job_id: str) -> JobStatus:
        """Return a job's current status."""
        return self.get(job_id).status

    def result(self, job_id: str) -> dict[str, object] | None:
        """Return a succeeded job's result, if available."""
        result = self.get(job_id).result
        return dict(result) if result is not None else None

    def update_result(self, job_id: str, updates: Mapping[str, object]) -> JobRecord:
        """Merge fields into an existing result snapshot and publish the update."""
        record = self.get(job_id)
        if record.result is None:
            raise ValueError(f"job has no result to update: {job_id}")
        result = dict(record.result)
        result.update(dict(updates))
        self._replace(job_id, result=result)
        return self.get(job_id)

    def error(self, job_id: str) -> str | None:
        """Return a failed job's error string, if available."""
        return self.get(job_id).error

    async def wait(self, job_id: str, *, timeout: float | None = None) -> JobRecord:
        """Wait for one job's background task and return its final snapshot."""
        task = self._task(job_id)
        try:
            if timeout is None:
                await task
            else:
                await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError:
            raise TimeoutError(f"job did not finish within {timeout} seconds: {job_id}") from None
        return self.get(job_id)

    async def events(self, job_id: str) -> AsyncIterator[JobRecord]:
        """Yield the current snapshot and each later status change for one job."""
        self.get(job_id)
        queue: asyncio.Queue[JobRecord] = asyncio.Queue()
        self._subscribers.setdefault(job_id, set()).add(queue)
        try:
            record = self.get(job_id)
            yield record
            if record.status in TERMINAL_JOB_STATUSES:
                return

            while True:
                record = await queue.get()
                yield record
                if record.status in TERMINAL_JOB_STATUSES:
                    return
        finally:
            subscribers = self._subscribers.get(job_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(job_id, None)

    def _task(self, job_id: str) -> asyncio.Task[None]:
        try:
            return self._tasks[job_id]
        except KeyError as exc:
            raise JobNotFoundError(job_id) from exc

    async def _run(
        self,
        job_id: str,
        engine: DeepEngine,
        payload: Mapping[str, object],
        lane: str,
    ) -> None:
        async with self._seat(lane):
            self._replace(job_id, status=JobStatus.RUNNING)
            try:
                result = await asyncio.to_thread(engine.submit, payload)
            except Exception as exc:  # noqa: BLE001 - engines surface adapter/runtime failures.
                self._replace(
                    job_id,
                    status=JobStatus.FAILED,
                    result=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return
            self._replace(
                job_id,
                status=JobStatus.SUCCEEDED,
                result=dict(result),
                error=None,
            )

    def _replace(self, job_id: str, **changes: object) -> None:
        self._jobs[job_id] = replace(self.get(job_id), **changes)
        self._publish(job_id)

    def _publish(self, job_id: str) -> None:
        record = self.get(job_id)
        for queue in self._subscribers.get(job_id, ()):
            queue.put_nowait(record)
