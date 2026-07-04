from __future__ import annotations

import pytest

from app.core.engines import SleepEngine
from app.core.job_store import JobNotFoundError, JobStatus, JobStore


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
