from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping

import pytest

from app.core.engines import SleepEngine
from app.core.job_store import CODEV_SEAT_LANE, JobNotFoundError, JobStatus, JobStore


@pytest.mark.asyncio
async def test_job_store_runs_sleep_engine_successfully():
    store = JobStore()
    engine = SleepEngine(delay_seconds=0.001)

    job_id = store.submit(engine, {"case_id": "demo"})

    assert store.status(job_id) in {JobStatus.QUEUED, JobStatus.RUNNING}

    final = await store.wait(job_id, timeout=1.0)

    assert final.status is JobStatus.SUCCEEDED
    assert store.status(job_id) is JobStatus.SUCCEEDED
    assert store.error(job_id) is None
    assert store.result(job_id) == {
        "engine": "sleep",
        "status": "completed",
        "slept_seconds": 0.001,
        "payload": {"case_id": "demo"},
    }


@pytest.mark.asyncio
async def test_job_store_captures_engine_errors():
    store = JobStore()

    job_id = store.submit(
        SleepEngine(delay_seconds=0.001),
        {"fail": True, "message": "boom"},
    )
    final = await store.wait(job_id, timeout=1.0)

    assert final.status is JobStatus.FAILED
    assert store.result(job_id) is None
    assert store.error(job_id) == "RuntimeError: boom"


def test_job_store_unknown_job_queries_raise():
    store = JobStore()

    with pytest.raises(JobNotFoundError):
        store.status("missing")

    with pytest.raises(JobNotFoundError):
        store.result("missing")

    with pytest.raises(JobNotFoundError):
        store.error("missing")


# ---------------------------------------------------------------------------
# Per-lane seats: same lane serializes (CODE V single-instance iron rule),
# different lanes run concurrently (a multi-minute CODE V batch must not
# freeze the instant demo lane).
# ---------------------------------------------------------------------------


class _GatedEngine:
    """Fake slow engine whose `submit` blocks until explicitly released.

    Events are `threading.Event` (not `asyncio.Event`) because `JobStore._run`
    executes `engine.submit` in a worker thread via `asyncio.to_thread` —
    `asyncio.Event` is not thread-safe to set/wait across that boundary. The
    async tests bridge back with `asyncio.to_thread(event.wait, ...)`; the
    timeouts are failure bounds, not pacing sleeps.
    """

    def __init__(self, name: str, *, seat_lane: str | None = None) -> None:
        self.name = name
        if seat_lane is not None:
            self.seat_lane = seat_lane
        self.started = threading.Event()
        self.release = threading.Event()

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "engine": "_GatedEngine", "available": True}

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        self.started.set()
        if not self.release.wait(timeout=5.0):
            raise TimeoutError("gated engine was never released")
        return {"engine": self.name, "status": "completed"}


async def _assert_never_starts_while_seat_held(engine: _GatedEngine, store: JobStore, job_id: str):
    """Yield the event loop repeatedly; while another job holds the lane's
    seat, this job must stay QUEUED and its engine must never start (RUNNING
    is only set after the seat is acquired). `asyncio.sleep(0)` is a pure
    scheduler yield, not a timed sleep."""
    for _ in range(20):
        await asyncio.sleep(0)
    assert not engine.started.is_set()
    assert store.status(job_id) is JobStatus.QUEUED


@pytest.mark.asyncio
async def test_job_store_different_lanes_run_concurrently():
    store = JobStore()
    slow_codev = _GatedEngine("codev-batch", seat_lane=CODEV_SEAT_LANE)
    demo = _GatedEngine("demo-summary")  # no seat_lane -> default lane

    codev_job = store.submit(slow_codev, {"kind": "c1-batch"})
    assert await asyncio.to_thread(slow_codev.started.wait, 2.0)

    demo_job = store.submit(demo, {"kind": "instant-demo"})
    # The demo-lane job starts while the codev-lane job is still mid-flight
    # (its release event has not been set) — the demo path is not frozen.
    assert await asyncio.to_thread(demo.started.wait, 2.0)
    assert not slow_codev.release.is_set()
    assert store.status(codev_job) is JobStatus.RUNNING

    demo.release.set()
    slow_codev.release.set()
    assert (await store.wait(demo_job, timeout=5.0)).status is JobStatus.SUCCEEDED
    assert (await store.wait(codev_job, timeout=5.0)).status is JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_job_store_codev_lane_jobs_serialize():
    store = JobStore()
    first = _GatedEngine("codev-batch-1", seat_lane=CODEV_SEAT_LANE)
    # Second engine declares no seat_lane; it lands on the codev lane through
    # submit()'s explicit `lane=` override — the mechanism the raw
    # /api/optical/jobs path uses for probe-resolved engines it does not own.
    second = _GatedEngine("codev-batch-2")

    first_job = store.submit(first, {"seq": 1})
    assert await asyncio.to_thread(first.started.wait, 2.0)

    second_job = store.submit(second, {"seq": 2}, lane=CODEV_SEAT_LANE)
    await _assert_never_starts_while_seat_held(second, store, second_job)

    first.release.set()
    assert (await store.wait(first_job, timeout=5.0)).status is JobStatus.SUCCEEDED

    assert await asyncio.to_thread(second.started.wait, 2.0)
    second.release.set()
    assert (await store.wait(second_job, timeout=5.0)).status is JobStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_job_store_default_lane_behavior_unchanged():
    """Engines that declare no seat_lane keep the pre-lane behavior: strict
    serialization on the single default seat."""
    store = JobStore()
    first = _GatedEngine("legacy-engine-1")
    second = _GatedEngine("legacy-engine-2")

    first_job = store.submit(first, {"seq": 1})
    assert await asyncio.to_thread(first.started.wait, 2.0)

    second_job = store.submit(second, {"seq": 2})
    await _assert_never_starts_while_seat_held(second, store, second_job)

    first.release.set()
    assert (await store.wait(first_job, timeout=5.0)).status is JobStatus.SUCCEEDED

    assert await asyncio.to_thread(second.started.wait, 2.0)
    second.release.set()
    assert (await store.wait(second_job, timeout=5.0)).status is JobStatus.SUCCEEDED
