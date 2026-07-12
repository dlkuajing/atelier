import json
from pathlib import Path

from scripts.audit_p18_archive import (
    _normalize_aut,
    accepted_final_path_issue,
    audit_batch,
    finite_machine_number,
    inspect_zmx,
    render_markdown,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _minimal_archive(tmp_path: Path) -> tuple[Path, Path]:
    archive_root = tmp_path / "archive"
    artifact_root = tmp_path / "artifacts"
    batch_dir = archive_root / "batch-1"
    artifact_dir = artifact_root / "batch-1" / "job-0000" / "attempt-1"
    candidate_path = artifact_dir / "candidate_set.json"
    target = {
        "scenario": "smartphone-wide",
        "efl_mm": 5.0,
        "fov_deg": 60.0,
        "fnum": 2.0,
        "image_height_mm": 3.0,
    }
    summary = {
        "candidate_count": 0,
        "mode_counts": {},
        "ranked_count": 0,
        "withheld_count": 0,
        "ri_missing_count": 0,
        "notes": [],
    }
    _write_json(
        batch_dir / "batch.json",
        {
            "batch_id": "batch-1",
            "created_at": "2026-07-12T00:00:00+00:00",
            "updated_at": "2026-07-12T00:01:00+00:00",
            "target_source": "test",
            "target_count": 1,
            "status": "completed",
            "engine": "fake",
            "notes": [],
        },
    )
    _write_json(batch_dir / "targets.json", {"targets": [target]})
    _write_json(
        batch_dir / "jobs" / "job-0000.json",
        {
            "job_id": "job-0000",
            "batch_id": "batch-1",
            "target_index": 0,
            "target_label": "test",
            "target_spec": target,
            "status": "failed",
            "created_at": "2026-07-12T00:00:00+00:00",
            "updated_at": "2026-07-12T00:01:00+00:00",
            "result_summary": {
                **summary,
                "modes_requested": ["retrieved", "target-converged"],
                "modes_present": [],
                "missing_modes": ["retrieved", "target-converged"],
            },
            "candidate_set_pointer": str(candidate_path),
            "artifact_dir": str(artifact_dir),
            "engine": "fake",
            "attempt": 1,
            "failure": {"category": "engine", "message": "test failure"},
            "degradation": None,
        },
    )
    _write_json(
        candidate_path,
        {"target": target, "candidates": [], "summary": summary},
    )
    return archive_root, artifact_root


def test_inspect_zmx_accepts_minimal_structural_file(tmp_path: Path) -> None:
    path = tmp_path / "candidate.zmx"
    path.write_text(
        "VERS 191028\nWAVM 1 0.5876 1\nSURF 0\nSURF 1\n",
        encoding="utf-8",
    )

    result = inspect_zmx(path)

    assert result["valid"] is True
    assert result["surface_count"] == 2
    assert result["wavelength_count"] == 1
    assert result["sha256"]


def test_inspect_zmx_rejects_truncated_file(tmp_path: Path) -> None:
    path = tmp_path / "candidate.zmx"
    path.write_text("VERS 191028\nSURF 0\n", encoding="utf-8")

    result = inspect_zmx(path)

    assert result["valid"] is False
    assert result["reason"] == "missing token(s): >=2 SURF, >=1 WAVM"


def test_inspect_zmx_decodes_utf16_bom(tmp_path: Path) -> None:
    path = tmp_path / "candidate.zmx"
    path.write_text(
        "VERS 191028\nWAVM 1 0.5876 1\nSURF 0\nSURF 1\n",
        encoding="utf-16",
    )

    assert inspect_zmx(path)["valid"] is True


def test_normalize_aut_accepts_real_archive_spellings() -> None:
    assert _normalize_aut("1") == "true"
    assert _normalize_aut("True") == "true"
    assert _normalize_aut(True) == "true"
    assert _normalize_aut("0") == "false"
    assert _normalize_aut(None) == "missing"


def test_audit_batch_accepts_complete_structurally_valid_archive(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
    )

    assert report["structural_status"] == "PASS"
    assert report["errors"] == []
    assert report["counts"]["candidate_sets_valid"] == 1
    assert report["counts"]["job_statuses"] == {"failed": 1}


def test_audit_batch_fails_closed_on_pointer_attempt_mismatch(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)
    job_path = archive_root / "batch-1" / "jobs" / "job-0000.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["artifact_dir"] = str(artifact_root / "batch-1" / "job-0000" / "attempt-2")
    _write_json(job_path, job)

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
    )

    assert report["structural_status"] == "FAIL"
    assert any("current attempt directory" in message for message in report["errors"])


def test_audit_batch_rejects_silent_missing_mode_success(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)
    job_path = archive_root / "batch-1" / "jobs" / "job-0000.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["status"] = "succeeded"
    job["failure"] = None
    _write_json(job_path, job)

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
    )

    assert report["structural_status"] == "FAIL"
    assert any("silently misses requested modes" in message for message in report["errors"])


def test_audit_batch_recomputes_candidate_summary(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)
    candidate_path = (
        artifact_root / "batch-1" / "job-0000" / "attempt-1" / "candidate_set.json"
    )
    candidate_set = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate_set["summary"]["candidate_count"] = 1
    _write_json(candidate_path, candidate_set)
    job_path = archive_root / "batch-1" / "jobs" / "job-0000.json"
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["result_summary"]["candidate_count"] = 1
    _write_json(job_path, job)

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
    )

    assert report["structural_status"] == "FAIL"
    assert any("recomputed truth" in message for message in report["errors"])


def test_audit_batch_requires_external_target_count_anchor(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=50,
    )

    assert report["structural_status"] == "FAIL"
    assert any("externally expected 50" in message for message in report["errors"])


def test_audit_batch_requires_declared_incident_exclusions(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
        required_excluded_attempts=(("job-0000", 1),),
    )

    assert report["structural_status"] == "FAIL"
    assert "required resume incident evidence is missing" in report["errors"]


def test_audit_batch_requires_blank_expert_verdict_set(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)
    _write_json(
        archive_root / "batch-1" / "verdicts" / "unexpected.json",
        {"unexpected": "expert authority must not be inferred"},
    )

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
        require_no_expert_verdicts=True,
    )

    assert report["structural_status"] == "FAIL"
    assert any("expected zero [EXPERT]" in message for message in report["errors"])


def test_audit_batch_rejects_nested_non_json_verdict_artifact(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)
    verdict_path = archive_root / "batch-1" / "verdicts" / "nested" / "note.txt"
    verdict_path.parent.mkdir(parents=True)
    verdict_path.write_text("not a valid expert verdict", encoding="utf-8")

    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
        require_no_expert_verdicts=True,
    )

    assert report["structural_status"] == "FAIL"
    assert report["counts"]["expert_verdicts"] == 1


def test_render_markdown_uses_actual_and_expected_job_count(tmp_path: Path) -> None:
    archive_root, artifact_root = _minimal_archive(tmp_path)
    report = audit_batch(
        archive_root=archive_root,
        artifact_root=artifact_root,
        batch_id="batch-1",
        expected_target_count=1,
    )

    markdown = render_markdown(report)

    assert "1 份 job ledger" in markdown
    assert "expected=1" in markdown
    assert "50 份 job ledger" not in markdown


def test_accepted_final_path_must_equal_delivered_zmx(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "attempt-1"
    accepted = artifact_dir / "accepted.zmx"
    generated = artifact_dir / "generated.zmx"
    for path in (accepted, generated):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "VERS 191028\nWAVM 1 0.5876 1\nSURF 0\nSURF 1\n",
            encoding="utf-8",
        )

    issue = accepted_final_path_issue(
        accepted_path=str(accepted),
        generated_path=str(generated),
        artifact_dir=artifact_dir,
    )

    assert issue == (
        "accepted_final optimized_zmx_path differs from generated optimized_zmx_path"
    )


def test_finite_machine_number_rejects_type_drift_and_nonfinite() -> None:
    assert finite_machine_number(36.0802) == (36.0802, None)
    assert finite_machine_number(None) == (None, "missing")
    for value in ("36.0802", True, float("nan"), float("inf")):
        number, issue = finite_machine_number(value)
        assert number is None
        assert issue is not None and issue.startswith("malformed")
