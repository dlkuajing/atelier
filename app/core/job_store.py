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
    """Run deep-engine submissions in asyncio background tasks and keep snapshots."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._single_seat = asyncio.Semaphore(1)
        self._subscribers: dict[str, set[asyncio.Queue[JobRecord]]] = {}

    def submit(self, engine: DeepEngine, payload: Mapping[str, object]) -> str:
        """Create a job and schedule the engine submission on the running event loop."""
        payload_copy = dict(payload)
        job_id = uuid4().hex
        self._jobs[job_id] = JobRecord(
            job_id=job_id,
            engine=engine.name,
            status=JobStatus.QUEUED,
            payload=payload_copy,
        )
        self._tasks[job_id] = asyncio.create_task(self._run(job_id, engine, payload_copy))
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
    ) -> None:
        async with self._single_seat:
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
