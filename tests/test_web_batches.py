"""P18-3 web contract tests — `/batches` list, `/batches/{batch_id}` detail,
[EXPERT] verdict POST, xlsx export.

Uses `FakeEngine` (Mode1-only, zero CODE V dependency — see
`app/core/batch_runner.py`) via `run_batch` to produce a real, small batch
in an isolated tmp archive, then monkeypatches `app.main.batch_archive_store`
to point at it (same pattern as `test_web_job_progress.py`'s
`monkeypatch.setattr(optical, "job_store", store)`).
"""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.core.batch_archive import BatchArchive
from app.core.batch_runner import FakeEngine, run_batch
from app.main import app

_TARGETS = [
    {"label": "t0", "scenario": "smartphone-wide", "efl_mm": 3.8, "fnum": 2.0, "fov_deg": 80.0, "image_height_mm": 3.6},
    {"label": "t1", "scenario": "smartphone-wide", "efl_mm": 4.8, "fnum": 1.8, "fov_deg": 79.0, "image_height_mm": 4.4},
]


@pytest.fixture
def batch_setup(tmp_path: Path, monkeypatch):
    archive = BatchArchive(root=tmp_path / "archive")
    monkeypatch.setattr(main_module, "batch_archive_store", archive)

    summary = run_batch(
        engine=FakeEngine(n=2),
        archive=archive,
        targets=_TARGETS,
        target_source="unit-test",
        artifacts_root=tmp_path / "artifacts",
    )
    return archive, summary.batch


def test_batches_list_empty_state(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "batch_archive_store", BatchArchive(root=tmp_path / "empty"))
    with TestClient(app) as client:
        response = client.get("/batches")
    assert response.status_code == 200
    assert "data-empty-batch-list" in response.text


def test_batches_list_shows_batch_row(batch_setup):
    _, batch = batch_setup
    with TestClient(app) as client:
        response = client.get("/batches")
    assert response.status_code == 200
    assert batch.batch_id in response.text
    assert f'data-batch-id="{batch.batch_id}"' in response.text
    assert "2 / 2" in response.text  # attempted / total


def test_batch_detail_unknown_batch_404(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "batch_archive_store", BatchArchive(root=tmp_path / "empty"))
    with TestClient(app) as client:
        response = client.get("/batches/nope")
    assert response.status_code == 404
    assert "data-error-page" in response.text


def test_batch_detail_renders_jobs_and_verdict_forms(batch_setup):
    _, batch = batch_setup
    with TestClient(app) as client:
        response = client.get(f"/batches/{batch.batch_id}")
    assert response.status_code == 200
    html = response.text
    assert f'data-batch-id="{batch.batch_id}"' in html
    assert "job-0000" in html
    assert "job-0001" in html
    assert "data-verdict-form" in html  # at least one candidate has an open verdict entry form
    assert "[EXPERT]" in html


def test_batch_detail_never_shows_machine_pass_fail_wording(batch_setup):
    _, batch = batch_setup
    with TestClient(app) as client:
        response = client.get(f"/batches/{batch.batch_id}")
    html = response.text
    for forbidden in ("合格", "良品", "pass</", ">fail<"):
        assert forbidden not in html


def test_submit_verdict_success_persists_and_redirects(batch_setup):
    archive, batch = batch_setup
    jobs = archive.list_jobs(batch.batch_id)
    job = next(j for j in jobs if j.status == "succeeded")
    candidates = archive.get_batch(batch.batch_id)  # sanity: batch still resolvable
    assert candidates is not None

    # Pull a real candidate_id off the job's persisted CandidateSet.
    import json

    payload = json.loads(Path(job.candidate_set_pointer).read_text(encoding="utf-8"))
    candidate_id = payload["candidates"][0]["scorecard"]["candidate_id"]

    with TestClient(app) as client:
        response = client.post(
            f"/batches/{batch.batch_id}/jobs/{job.job_id}/verdicts",
            data={
                "candidate_key": candidate_id,
                "verdict_text": "几何合理，值得细看",
                "reviewer": "张三",
                "note": "备注",
            },
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"] == f"/batches/{batch.batch_id}"

    verdict = archive.get_verdict(batch.batch_id, job.job_id, candidate_id)
    assert verdict is not None
    assert verdict.verdict_text == "几何合理，值得细看"
    assert verdict.reviewer == "张三"

    # Detail page now shows the recorded verdict instead of a blank form for
    # this candidate.
    with TestClient(app) as client:
        detail = client.get(f"/batches/{batch.batch_id}")
    assert "data-verdict-recorded" in detail.text
    assert "张三" in detail.text


def test_submit_verdict_blank_text_rejected_400(batch_setup):
    archive, batch = batch_setup
    job = next(j for j in archive.list_jobs(batch.batch_id) if j.status == "succeeded")
    import json

    payload = json.loads(Path(job.candidate_set_pointer).read_text(encoding="utf-8"))
    candidate_id = payload["candidates"][0]["scorecard"]["candidate_id"]

    with TestClient(app) as client:
        response = client.post(
            f"/batches/{batch.batch_id}/jobs/{job.job_id}/verdicts",
            data={"candidate_key": candidate_id, "verdict_text": "   ", "reviewer": "张三"},
        )
    assert response.status_code == 400
    assert archive.get_verdict(batch.batch_id, job.job_id, candidate_id) is None


def test_submit_verdict_missing_required_fields_422(batch_setup):
    _, batch = batch_setup
    job_id = "job-0000"
    with TestClient(app) as client:
        response = client.post(
            f"/batches/{batch.batch_id}/jobs/{job_id}/verdicts",
            data={"candidate_key": "cand-a"},  # missing verdict_text/reviewer
        )
    assert response.status_code == 422


def test_submit_verdict_unknown_job_404(batch_setup):
    _, batch = batch_setup
    with TestClient(app) as client:
        response = client.post(
            f"/batches/{batch.batch_id}/jobs/job-nope/verdicts",
            data={"candidate_key": "cand-a", "verdict_text": "x", "reviewer": "y"},
        )
    assert response.status_code == 404


def test_submit_verdict_unknown_batch_404(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "batch_archive_store", BatchArchive(root=tmp_path / "empty"))
    with TestClient(app) as client:
        response = client.post(
            "/batches/nope/jobs/job-0000/verdicts",
            data={"candidate_key": "cand-a", "verdict_text": "x", "reviewer": "y"},
        )
    assert response.status_code == 404


def test_batch_detail_shows_degraded_job_visibly(tmp_path: Path, monkeypatch):
    """BLOCKER-1 web visibility: a degraded job renders its own status badge
    and the degradation reason — it never reads as a clean success row."""
    from app.core.batch_archive import BatchJobRecord

    archive = BatchArchive(root=tmp_path / "archive")
    monkeypatch.setattr(main_module, "batch_archive_store", archive)
    batch = archive.create_batch(target_source="unit", targets=_TARGETS[:1], engine="real")
    archive.put_job(
        BatchJobRecord(
            job_id="job-0000",
            batch_id=batch.batch_id,
            target_index=0,
            target_label="t0",
            target_spec=_TARGETS[0],
            status="degraded",
            created_at="x",
            updated_at="x",
            result_summary={
                "candidate_count": 2,
                "ranked_count": 2,
                "modes_requested": ["retrieved", "target-converged"],
                "modes_present": ["retrieved"],
                "missing_modes": ["target-converged"],
                "mode_counts": {"retrieved": 2},
            },
            degradation="requested generation mode(s) produced no candidates: target-converged",
        )
    )

    with TestClient(app) as client:
        detail = client.get(f"/batches/{batch.batch_id}")
        listing = client.get("/batches")

    assert detail.status_code == 200
    assert 'data-job-status="degraded"' in detail.text
    assert "data-job-degradation" in detail.text
    assert "target-converged" in detail.text
    # List page: degraded count appears in the success-rate column.
    assert "(1 degraded)" in listing.text


def test_batch_export_xlsx_downloads_workbook_with_three_sheets(batch_setup):
    _, batch = batch_setup
    with TestClient(app) as client:
        response = client.get(f"/batches/{batch.batch_id}/export.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    assert wb.sheetnames == ["Summary", "Jobs", "Expert verdicts"]


def test_batch_export_xlsx_unknown_batch_404(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main_module, "batch_archive_store", BatchArchive(root=tmp_path / "empty"))
    with TestClient(app) as client:
        response = client.get("/batches/nope/export.xlsx")
    assert response.status_code == 404
