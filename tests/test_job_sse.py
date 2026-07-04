from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping

import pytest
from fastapi.testclient import TestClient

from app.api import optical
from app.core.engines import SleepEngine
from app.core.job_store import JobStatus, JobStore
from app.main import app


class GateEngine:
    name = "gate"

    def __init__(self) -> None:
        self.started: list[str] = []
        self.first_started = threading.Event()
        self.second_started = threading.Event()
        self.release_first = threading.Event()
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return True

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "available": True}

    def submit(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        job_name = str(payload["job"])
        with self._lock:
            self.started.append(job_name)
        if job_name == "first":
            self.first_started.set()
            if not self.release_first.wait(timeout=1.0):
                raise RuntimeError("first job was not released")
        else:
            self.second_started.set()
        return {"job": job_name}


@pytest.mark.asyncio
async def test_job_store_keeps_second_job_queued_until_single_seat_is_free():
    store = JobStore()
    engine = GateEngine()

    first_id = store.submit(engine, {"job": "first"})
    second_id = store.submit(engine, {"job": "second"})

    assert await asyncio.to_thread(engine.first_started.wait, 1.0)
    await asyncio.sleep(0.02)

    assert store.status(first_id) is JobStatus.RUNNING
    assert store.status(second_id) is JobStatus.QUEUED
    assert engine.started == ["first"]
    assert not engine.second_started.is_set()

    engine.release_first.set()
    first = await store.wait(first_id, timeout=1.0)
    second = await store.wait(second_id, timeout=1.0)

    assert first.status is JobStatus.SUCCEEDED
    assert second.status is JobStatus.SUCCEEDED
    assert engine.started == ["first", "second"]


def test_job_events_endpoint_streams_sse_until_terminal_status(monkeypatch):
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)
    monkeypatch.setattr(optical, "get_deep_engine", lambda: SleepEngine(delay_seconds=0.001))

    with TestClient(app) as client:
        submitted = client.post("/api/optical/jobs", json={"payload": {"case_id": "demo"}})
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            assert streamed.status_code == 200
            assert streamed.headers["content-type"].startswith("text/event-stream")
            body = "".join(streamed.iter_text())

    assert f'"job_id":"{job_id}"' in body
    assert "event: succeeded" in body
    assert '"status":"succeeded"' in body
