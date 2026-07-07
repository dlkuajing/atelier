"""Web job progress page contract tests."""

from fastapi.testclient import TestClient

from app.api import optical
from app.core.engines import SleepEngine
from app.core.job_store import JobStore
from app.main import app


def test_job_progress_page_subscribes_to_sse_until_sleep_engine_succeeds(monkeypatch):
    store = JobStore()
    monkeypatch.setattr(optical, "job_store", store)
    monkeypatch.setattr(optical, "get_deep_engine", lambda: SleepEngine(delay_seconds=0.001))

    with TestClient(app) as client:
        submitted = client.post("/api/optical/jobs", json={"payload": {"case_id": "demo"}})
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]

        page = client.get(f"/jobs/{job_id}")
        assert page.status_code == 200
        html = page.text
        assert "Task progress" in html
        assert f'data-job-id="{job_id}"' in html
        assert f'data-events-url="/api/optical/jobs/{job_id}/events"' in html
        assert "new EventSource" in html
        assert "job-progress-bar" in html

        with client.stream("GET", f"/api/optical/jobs/{job_id}/events") as streamed:
            assert streamed.status_code == 200
            assert streamed.headers["content-type"].startswith("text/event-stream")
            body = "".join(streamed.iter_text())

    assert "event: succeeded" in body
    assert '"status":"succeeded"' in body
    assert '"engine":"sleep"' in body


def test_unknown_job_progress_page_returns_404():
    with TestClient(app) as client:
        response = client.get("/jobs/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert 'data-error-page' in response.text
    assert 'data-status-code="404"' in response.text
    assert "missing" in response.text
    assert "Return home" in response.text
