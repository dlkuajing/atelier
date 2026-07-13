from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from app.core.batch_run_lock import (
    BatchRunnerLockHeldError,
)
from scripts import p16_stagec_stageb_inputs as inputs


@pytest.fixture(autouse=True)
def _offline_machine_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every unit test on fake, per-test lock/toolchain roots."""

    monkeypatch.setattr(
        inputs,
        "_require_official_toolchain",
        lambda executable: Path(executable).resolve(),
    )
    monkeypatch.setattr(inputs, "P18_GLOBAL_WINDOW_ROOT", tmp_path / "p18-global")
    monkeypatch.setattr(inputs, "CODEV_LOCK_ROOT", tmp_path / "codev-lock")


def _owner_ids() -> dict[str, str | None]:
    return {
        "output": "a" * 32,
        "p18_global": "b" * 32,
        "p18_archive": "c" * 32,
        "codev": None,
    }


def _p18_fixture(
    tmp_path: Path, *, archive_root: Path | None = None
) -> tuple[Path, dict[str, object]]:
    archive_root = tmp_path / "p18-archive" if archive_root is None else archive_root
    archive_root.mkdir(parents=True, exist_ok=True)
    (archive_root / ".p18-runner.lock").touch(exist_ok=True)
    batch_path = archive_root / inputs.P18_REQUIRED_BATCH_ID / "batch.json"
    if not batch_path.exists():
        inputs._atomic_json(
            batch_path,
            {
                "batch_id": inputs.P18_REQUIRED_BATCH_ID,
                "created_at": "2026-07-11T00:00:00+00:00",
                "updated_at": "2026-07-12T00:00:00+00:00",
                "target_source": "offline-test-fixture",
                "target_count": 50,
                "status": "completed",
                "engine": "real",
                "notes": [],
            },
        )
    return archive_root, inputs._p18_terminal_authority(
        archive_root=archive_root,
        batch_id=inputs.P18_REQUIRED_BATCH_ID,
    )


def _authority_kwargs(tmp_path: Path, output_dir: Path) -> dict[str, object]:
    archive_root, terminal = _p18_fixture(tmp_path)
    output_lock = output_dir.parent / f".{output_dir.name}.stageb-input-lock"
    return {
        "recovery_p18_root": inputs.P18_GLOBAL_WINDOW_ROOT,
        "p18_terminal_authority": terminal,
        "lock_authority": inputs._lock_authority(
            output_root=output_lock,
            p18_archive_root=archive_root,
            mode="pre-run-held",
        ),
        "lock_owner_ids": _owner_ids(),
    }


def _legacy_manifest(
    outcomes: list[dict[str, object]],
    *,
    accepted: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    retained = [] if accepted is None else accepted
    return {
        "schema_id": "atelier-stagec-stageb-input-manifest-v1",
        "created_at": "2026-07-12T00:00:00+00:00",
        "required_count": 8,
        "accepted_count": len(retained),
        "complete": len(retained) >= 8,
        "accepted": retained,
        "outcomes": outcomes,
        "expert_verdict": None,
        "truth_notice": inputs.LEGACY_STAGEB_TRUTH_NOTICE,
    }


def _cache(tmp_path: Path, case_id: str, result: dict[str, object], scope: str = "pre-run-bound"):
    root = tmp_path / "cache" / case_id
    root.mkdir(parents=True, exist_ok=True)
    result_path = root / "ladder-result.json"
    raw_path = root / "raw-ladder-result.json"
    record_path = root / "record.json"
    inputs._atomic_json(result_path, result)
    inputs._atomic_json(raw_path, result)
    inputs._atomic_json(record_path, {"case_id": case_id, "scope": scope})
    return {
        "result": result,
        "path": result_path,
        "raw": raw_path if scope == "pre-run-bound" else None,
        "scope": scope,
        "record": record_path,
    }


def _accepted_result(*, source_name: str, accepted_path: Path, efl: float, fnum: float):
    accepted = {
        "rung_index": 3,
        "target_fnum": fnum,
        "status": "measured",
        "measured_fnum": fnum,
        "fnum_target_deviation_pct": 0.0,
        "fno_param_achieved": True,
        "aut_converged": True,
        "ray_traceable": True,
        "effective_edge_used": 0.2,
        "ray_grid": {
            "category": "ok",
            "refl_count": 0,
            "miss_count": 0,
            "ray_aiming_warning": False,
            "aperture_conflict_matched": None,
            "excerpt": None,
            "note": "complete positive listing",
            "normal_completion": True,
            "abnormal_completion_matched": None,
        },
        "efl_target_deviation_pct": 0.0,
        "post_aut.max_rms_spot_diameter_um": 1.0,
        "post_aut.max_rms_wavefront_error_waves": 0.1,
        "err_f_ratio": 0.0,
        "aut_termination": "normal_completion",
        "autovig.edge_used": "0",
        "autovig.converged": "1",
        "quality_note": "accepted test rung",
        "optimized_zmx_path": str(accepted_path),
        "ray_retry": None,
        "error": None,
    }
    return {
        "schema": "atelier-p15-fno-ladder-v1",
        "source_zmx": source_name,
        "stage": "B",
        "target_efl_mm": efl,
        "fnum_target": fnum,
        "rung_count": 3,
        "fnum_tolerance_pct": 8.0,
        "vig_ladder": [0.0, 0.2],
        "ray_retry_vig_ladder": [0.2, 0.3],
        "num_fields": 3,
        "extra_dof": "both",
        "native_fnum_measured": fnum,
        "target_achieved": True,
        "accepted_final": accepted,
        "rungs": [dict(accepted)],
        "last_measured_rung_index": 3,
        "last_measured_rung": dict(accepted),
        "blocked": False,
    }


def test_build_inputs_requires_eight_unique_closed_stageb_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    jobs = tuple(inputs.InputJob(f"case-{index}", 2.4, "test") for index in range(1, 9))
    records = {}
    results = {}
    for index, job in enumerate(jobs, start=1):
        source_name = f"case-{index}.zmx"
        (zmx_dir / source_name).write_bytes(f"source-{index}".encode())
        emitted = tmp_path / f"emitted-{index}.zmx"
        emitted.write_bytes(f"accepted-{index}".encode())
        records[job.case_id] = {
            "case_id": job.case_id,
            "scenario": "smartphone-wide",
            "source_zmx": source_name,
            "efl_mm": 4.0,
            "image_height_mm": 3.0,
        }
        results[job.case_id] = _accepted_result(
            source_name=source_name,
            accepted_path=emitted,
            efl=4.0,
            fnum=2.4,
        )
    monkeypatch.setattr(inputs, "JOBS", jobs)
    monkeypatch.setattr(inputs, "ZMX_DIR", zmx_dir)
    monkeypatch.setattr(inputs, "_index", lambda: records)
    monkeypatch.setattr(
        inputs,
        "_run_job",
        lambda *, job, **_kwargs: _cache(tmp_path, job.case_id, results[job.case_id]),
    )
    monkeypatch.setattr(inputs, "validate_retained_stageb_authority", lambda **_kwargs: None)
    output = tmp_path / "out"

    manifest = inputs.build_inputs(
        output_dir=output,
        required_count=8,
        executable=tmp_path / "unused.exe",
        **_authority_kwargs(tmp_path, output),
    )

    assert manifest["complete"] is True
    assert manifest["accepted_count"] == 8
    assert len({entry["case_id"] for entry in manifest["accepted"]}) == 8
    for entry in manifest["accepted"]:
        assert len(entry["accepted_zmx_sha256"]) == 64
        assert len(entry["ladder_result_sha256"]) == 64
        assert Path(entry["accepted_final"]["optimized_zmx_path"]) == Path(entry["accepted_zmx"])
        assert Path(entry["cache_record_path"]).is_file()
        assert inputs._sha(Path(entry["cache_record_path"])) == entry["cache_record_sha256"]


def test_legacy_cache_without_adoption_is_rejected(tmp_path: Path, monkeypatch) -> None:
    job = inputs.InputJob("case-1", 2.4, "test")
    meta = {
        "source_zmx": "case-1.zmx",
        "efl_mm": 4.0,
        "image_height_mm": 3.0,
    }
    result_path = tmp_path / "ladders" / job.case_id / "ladder-result.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        json.dumps(
            {
                "schema": "atelier-p15-fno-ladder-v1",
                "source_zmx": "other-seed.zmx",
                "stage": "B",
                "target_efl_mm": 4.0,
                "fnum_target": 2.4,
                "rung_count": 3,
                "num_fields": 3,
                "extra_dof": "both",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: {"identity": 1})
    with pytest.raises(RuntimeError, match="explicit adoption"):
        inputs._run_job(
            job=job,
            meta=meta,
            output_dir=tmp_path,
            executable=tmp_path / "unused.exe",
            **_authority_kwargs(tmp_path, tmp_path),
        )
    assert "other-seed.zmx" in result_path.read_text(encoding="utf-8")


def test_fresh_attempt_writes_intent_before_runner_and_reverse_binds_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = inputs.InputJob("case-1", 2.4, "test")
    meta = {"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0}
    identity = {"identity": "stable"}
    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: identity)

    def runner(**kwargs: object):
        work = Path(kwargs["work_dir"])
        assert (work.parent / "intent.json").is_file()
        return {
            "schema": "atelier-p15-fno-ladder-v1",
            "source_zmx": "case.zmx",
            "stage": "B",
            "target_efl_mm": 4.0,
            "fnum_target": 2.4,
            "rung_count": 3,
            "fnum_tolerance_pct": 8.0,
            "vig_ladder": list(inputs.VIG_LADDER),
            "ray_retry_vig_ladder": list(inputs.RAY_RETRY_VIG_LADDER),
            "num_fields": 3,
            "extra_dof": "both",
            "target_achieved": False,
            "accepted_final": None,
            "rungs": [],
        }

    monkeypatch.setattr(inputs, "run_codev_target_fno_ladder", runner)
    output = tmp_path / "out"
    cache = inputs._run_job(
        job=job,
        meta=meta,
        output_dir=output,
        executable=tmp_path / "codev.exe",
        **_authority_kwargs(tmp_path, output),
    )

    provenance = cache["result"]["cache_provenance"]
    assert provenance["scope"] == "pre-run-bound"
    assert provenance["intent_sha256"] == inputs._sha(cache["record"])
    raw = cache["path"].parent / "raw-ladder-result.json"
    assert provenance["raw_result_sha256"] == inputs._sha(raw)


@pytest.mark.parametrize(
    "changed",
    (
        "source",
        "executable",
        "runner",
        "target_imh",
        "vig",
        "ray_retry",
        "timeout",
        "platform",
        "python",
        "codev_version",
    ),
)
def test_bound_cache_rejects_every_identity_dimension_drift(tmp_path: Path, changed: str) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    identity = {
        "source": "a",
        "executable": "a",
        "runner": "a",
        "target_imh": 3.0,
        "vig": [0.0],
        "ray_retry": [0.2],
        "timeout": 180.0,
        "platform": "nt",
        "python": "3.12",
        "codev_version": "11.5.27302.701",
    }
    intent = {
        "schema_id": inputs.INTENT_SCHEMA,
        "scope": "pre-run-intent",
        "attempt_id": "a",
        "created_at": "now",
        "identity": identity,
        "lock_owner_ids": _owner_ids(),
    }
    inputs._exclusive_json(attempt / "intent.json", intent)
    inputs._exclusive_json(attempt / "raw-ladder-result.json", {"raw": True})
    provenance = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": inputs._sha(attempt / "intent.json"),
        "raw_result_sha256": inputs._sha(attempt / "raw-ladder-result.json"),
        "post_run_identity_sha256": __import__("hashlib")
        .sha256(inputs._canonical_bytes(identity))
        .hexdigest(),
    }
    inputs._exclusive_json(attempt / "ladder-result.json", {"cache_provenance": provenance})
    drifted = json.loads(json.dumps(identity))
    drifted[changed] = "changed"
    with pytest.raises(ValueError, match="intent differs"):
        inputs._validate_bound_attempt(attempt_dir=attempt, expected_identity=drifted)


def test_post_run_identity_drift_preserves_intent_and_raw_without_final_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_identities = iter(({"source": "before"}, {"source": "after"}))

    def identity(**kwargs: object) -> dict[str, str]:
        if kwargs.get("work_dir") is None:
            return {"scope": "retrospective"}
        return next(run_identities)

    monkeypatch.setattr(inputs, "_current_identity", identity)
    monkeypatch.setattr(
        inputs,
        "run_codev_target_fno_ladder",
        lambda **_kwargs: {"target_achieved": False, "accepted_final": None},
    )
    with pytest.raises(RuntimeError, match="changed during run"):
        inputs._run_job(
            job=inputs.InputJob("case-1", 2.4, "test"),
            meta={"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0},
            output_dir=tmp_path,
            executable=tmp_path / "codev.exe",
            **_authority_kwargs(tmp_path, tmp_path),
        )
    attempt = next((tmp_path / "ladders" / "case-1" / "attempts").iterdir())
    assert (attempt / "intent.json").is_file()
    assert (attempt / "raw-ladder-result.json").is_file()
    assert not (attempt / "ladder-result.json").exists()


def test_adoption_refuses_current_nine_outcome_shape_with_missing_result_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = tuple(inputs.InputJob(f"case-{index}", 2.4, "test") for index in range(1, 10))
    monkeypatch.setattr(inputs, "JOBS", jobs)
    monkeypatch.setattr(
        inputs,
        "_index",
        lambda: {
            job.case_id: {"source_zmx": f"{job.case_id}.zmx", "efl_mm": 4.0, "image_height_mm": 3.0}
            for job in jobs
        },
    )
    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: {"current": True})
    monkeypatch.setattr(inputs, "_active_phase18_processes", lambda: [])
    manifest = _legacy_manifest(
        [{"case_id": job.case_id, "accepted": False, "reason": "terminal"} for job in jobs]
    )
    inputs._atomic_json(tmp_path / "manifest.json", manifest)
    for job in jobs[:8]:
        inputs._atomic_json(tmp_path / "ladders" / job.case_id / "ladder-result.json", {})
    p18, _terminal = _p18_fixture(tmp_path)

    with pytest.raises(ValueError, match="case set or count"):
        inputs.adopt_legacy_cache(
            output_dir=tmp_path,
            executable=tmp_path / "codev.exe",
            p18_archive_root=p18,
            p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
        )
    assert not (tmp_path / "adoptions-v1").exists()


def test_publish_accepted_is_content_addressed_idempotent_and_collision_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    emitted = tmp_path / "emitted.zmx"
    emitted.write_bytes(b"accepted")
    result = _accepted_result(source_name="case.zmx", accepted_path=emitted, efl=4.0, fnum=2.4)
    monkeypatch.setattr(
        inputs,
        "fnum_ladder_evidence_from_result",
        lambda _result: type("E", (), {"target_achieved": True})(),
    )
    inputs._publish_accepted(raw_result=result, output_dir=tmp_path / "out", case_id="case")
    canonical = Path(result["accepted_final"]["optimized_zmx_path"])
    before = canonical.stat().st_mtime_ns
    inputs._publish_accepted(raw_result=result, output_dir=tmp_path / "out", case_id="case")
    assert canonical.stat().st_mtime_ns == before
    result["accepted_final"]["optimized_zmx_path"] = str(emitted)
    canonical.write_bytes(b"collision")
    with pytest.raises(ValueError, match="collision"):
        inputs._publish_accepted(raw_result=result, output_dir=tmp_path / "out", case_id="case")


def test_strict_json_rejects_duplicate_keys_and_nan(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        inputs._strict_json(duplicate)
    nan = tmp_path / "nan.json"
    nan.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        inputs._strict_json(nan)


@pytest.mark.skipif(os.name != "nt", reason="MoveFileExW error propagation is Windows-only")
def test_windows_durable_move_reports_actual_last_error(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"source")
    destination.write_bytes(b"destination")
    with pytest.raises(OSError) as captured:
        inputs._durable_move(source, destination, replace=False)
    assert captured.value.errno not in (None, 0)
    assert source.read_bytes() == b"source"
    assert destination.read_bytes() == b"destination"


def test_adoption_is_idempotent_and_never_mutates_legacy_bytes_or_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = inputs.InputJob("case-1", 2.4, "test")
    monkeypatch.setattr(inputs, "JOBS", (job,))
    monkeypatch.setattr(
        inputs,
        "_index",
        lambda: {"case-1": {"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0}},
    )
    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: {"current": True})
    monkeypatch.setattr(inputs, "_active_phase18_processes", lambda: [])
    monkeypatch.setattr(inputs, "CODEV_LOCK_ROOT", tmp_path / "codev-lock")
    inputs._atomic_json(
        tmp_path / "manifest.json",
        _legacy_manifest([{"case_id": "case-1", "accepted": False, "reason": "terminal"}]),
    )
    result_path = tmp_path / "ladders" / "case-1" / "ladder-result.json"
    inputs._atomic_json(
        result_path, {"source_zmx": "case.zmx", "target_efl_mm": 4.0, "fnum_target": 2.4}
    )
    manifest_path = tmp_path / "manifest.json"
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (manifest_path, result_path)
    }
    p18, terminal = _p18_fixture(tmp_path)

    first = inputs.adopt_legacy_cache(
        output_dir=tmp_path,
        executable=tmp_path / "codev.exe",
        p18_archive_root=p18,
        p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
    )
    second = inputs.adopt_legacy_cache(
        output_dir=tmp_path,
        executable=tmp_path / "codev.exe",
        p18_archive_root=p18,
        p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
    )

    assert first == {"created": 1, "verified": 0}
    assert second == {"created": 0, "verified": 1}
    adoption = inputs._strict_json(tmp_path / "adoptions-v1" / "case-1.json")
    assert adoption["pre_run_bound"] is False
    assert adoption["run_time_identity_verified"] is False
    for path, snapshot in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == snapshot
    adoption_path = tmp_path / "adoptions-v1" / "case-1.json"
    tampered = inputs._strict_json(adoption_path)
    tampered["legacy_manifest_base64"] = "***not-base64***"
    inputs._atomic_json(adoption_path, tampered)
    with pytest.raises(ValueError, match="strict base64"):
        inputs._validate_adoption(
            output_dir=tmp_path,
            job=job,
            expected_identity={"current": True},
            expected_p18_terminal_authority=terminal,
        )


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("target_achieved", True),
        ("target_efl_mm", 9.0),
        ("fnum_target", 1.0),
        ("source_zmx", "tampered.zmx"),
    ),
)
def test_final_result_business_tamper_is_rejected_even_with_valid_provenance_hashes(
    tmp_path: Path, key: str, value: object
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    identity = {"stable": True}
    inputs._exclusive_json(
        attempt / "intent.json",
        {
            "schema_id": inputs.INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": "a",
            "created_at": "now",
            "identity": identity,
            "lock_owner_ids": _owner_ids(),
        },
    )
    raw = {
        "target_achieved": False,
        "target_efl_mm": 4.0,
        "fnum_target": 2.4,
        "source_zmx": "case.zmx",
        "accepted_final": None,
    }
    inputs._exclusive_json(attempt / "raw-ladder-result.json", raw)
    final = dict(raw)
    final[key] = value
    final["cache_provenance"] = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": inputs._sha(attempt / "intent.json"),
        "raw_result_sha256": inputs._sha(attempt / "raw-ladder-result.json"),
        "post_run_identity_sha256": __import__("hashlib")
        .sha256(inputs._canonical_bytes(identity))
        .hexdigest(),
    }
    inputs._exclusive_json(attempt / "ladder-result.json", final)

    with pytest.raises(ValueError, match="business facts"):
        inputs._validate_bound_attempt(attempt_dir=attempt, expected_identity=identity)


def test_adoption_claim_mismatch_is_preflight_zero_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = inputs.InputJob("case-1", 2.4, "test")
    monkeypatch.setattr(inputs, "JOBS", (job,))
    monkeypatch.setattr(
        inputs,
        "_index",
        lambda: {"case-1": {"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0}},
    )
    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: {"current": True})
    monkeypatch.setattr(inputs, "_active_phase18_processes", lambda: [])
    monkeypatch.setattr(inputs, "CODEV_LOCK_ROOT", tmp_path / "codev-lock")
    inputs._atomic_json(
        tmp_path / "manifest.json",
        _legacy_manifest([{"case_id": "case-1", "accepted": False, "reason": "terminal"}]),
    )
    inputs._atomic_json(
        tmp_path / "ladders" / "case-1" / "ladder-result.json",
        {"source_zmx": "wrong.zmx", "target_efl_mm": 4.0, "fnum_target": 2.4},
    )
    p18, _terminal = _p18_fixture(tmp_path)
    with pytest.raises(ValueError, match="claims differ"):
        inputs.adopt_legacy_cache(
            output_dir=tmp_path,
            executable=tmp_path / "codev.exe",
            p18_archive_root=p18,
            p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
        )
    assert not (tmp_path / "adoptions-v1").exists()


def test_raw_and_final_matching_wrong_target_still_rejected_against_intent(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    identity = {
        "job": {"index_record": {"source_zmx": "case.zmx"}},
        "parameters": {"target_efl_mm": 4.0, "fnum_target": 2.4},
    }
    inputs._exclusive_json(
        attempt / "intent.json",
        {
            "schema_id": inputs.INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": "a",
            "created_at": "now",
            "identity": identity,
            "lock_owner_ids": _owner_ids(),
        },
    )
    raw = {
        "schema": "atelier-p15-fno-ladder-v1",
        "source_zmx": "case.zmx",
        "target_efl_mm": 9.0,
        "fnum_target": 2.4,
        "accepted_final": None,
    }
    inputs._exclusive_json(attempt / "raw-ladder-result.json", raw)
    final = dict(raw)
    final["cache_provenance"] = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": inputs._sha(attempt / "intent.json"),
        "raw_result_sha256": inputs._sha(attempt / "raw-ladder-result.json"),
        "post_run_identity_sha256": __import__("hashlib")
        .sha256(inputs._canonical_bytes(identity))
        .hexdigest(),
    }
    inputs._exclusive_json(attempt / "ladder-result.json", final)
    with pytest.raises(ValueError, match="claims differ"):
        inputs._validate_bound_attempt(attempt_dir=attempt, expected_identity=identity)


def test_final_accepted_path_tamper_is_rejected_with_valid_provenance(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    identity = {"stable": True}
    inputs._exclusive_json(
        attempt / "intent.json",
        {
            "schema_id": inputs.INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": "a",
            "created_at": "now",
            "identity": identity,
            "lock_owner_ids": _owner_ids(),
        },
    )
    emitted = tmp_path / "ephemeral.zmx"
    emitted.write_bytes(b"forged")
    raw = {"accepted_final": {"optimized_zmx_path": str(emitted)}}
    inputs._exclusive_json(attempt / "raw-ladder-result.json", raw)
    forged = tmp_path / "forged.zmx"
    forged.write_bytes(b"forged")
    final = {"accepted_final": {"optimized_zmx_path": str(forged)}}
    final["cache_provenance"] = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": inputs._sha(attempt / "intent.json"),
        "raw_result_sha256": inputs._sha(attempt / "raw-ladder-result.json"),
        "post_run_identity_sha256": __import__("hashlib")
        .sha256(inputs._canonical_bytes(identity))
        .hexdigest(),
    }
    inputs._exclusive_json(attempt / "ladder-result.json", final)
    with pytest.raises(ValueError, match="exact canonical"):
        inputs._validate_bound_attempt(attempt_dir=attempt, expected_identity=identity)


def test_final_accepted_cross_case_self_consistent_path_is_rejected(tmp_path: Path) -> None:
    attempt = tmp_path / "out" / "ladders" / "case-1" / "attempts" / "a"
    attempt.mkdir(parents=True)
    identity = {"stable": True}
    inputs._exclusive_json(
        attempt / "intent.json",
        {
            "schema_id": inputs.INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": "a",
            "created_at": "now",
            "identity": identity,
            "lock_owner_ids": _owner_ids(),
        },
    )
    emitted = attempt / "work" / "emitted.zmx"
    emitted.parent.mkdir()
    emitted.write_bytes(b"same-bytes")
    digest = __import__("hashlib").sha256(b"same-bytes").hexdigest()
    wrong_case = tmp_path / "out" / "accepted" / "case-2" / f"{digest}.zmx"
    wrong_case.parent.mkdir(parents=True)
    wrong_case.write_bytes(b"same-bytes")
    raw = {"accepted_final": {"optimized_zmx_path": str(emitted)}}
    inputs._exclusive_json(attempt / "raw-ladder-result.json", raw)
    final = {"accepted_final": {"optimized_zmx_path": str(wrong_case)}}
    final["cache_provenance"] = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": inputs._sha(attempt / "intent.json"),
        "raw_result_sha256": inputs._sha(attempt / "raw-ladder-result.json"),
        "post_run_identity_sha256": __import__("hashlib")
        .sha256(inputs._canonical_bytes(identity))
        .hexdigest(),
        "accepted_artifact": {
            "raw_emitted": inputs._descriptor(emitted),
            "published": inputs._descriptor(wrong_case),
        },
    }
    inputs._exclusive_json(attempt / "ladder-result.json", final)
    with pytest.raises(ValueError, match="exact canonical"):
        inputs._validate_bound_attempt(attempt_dir=attempt, expected_identity=identity)


def test_required_count_other_than_exact_eight_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly eight"):
        inputs.build_inputs(
            output_dir=tmp_path,
            required_count=9,
            executable=tmp_path / "unused.exe",
            **_authority_kwargs(tmp_path, tmp_path),
        )


def test_same_identity_damaged_attempt_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = {"same": True}
    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: identity)
    attempt = tmp_path / "ladders" / "case-1" / "attempts" / "a"
    attempt.mkdir(parents=True)
    inputs._exclusive_json(
        attempt / "intent.json",
        {
            "schema_id": inputs.INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": "a",
            "created_at": "now",
            "identity": identity,
            "lock_owner_ids": _owner_ids(),
        },
    )
    inputs._exclusive_json(attempt / "raw-ladder-result.json", {})
    (attempt / "ladder-result.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(RuntimeError, match="damaged"):
        inputs._run_job(
            job=inputs.InputJob("case-1", 2.4, "test"),
            meta={"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0},
            output_dir=tmp_path,
            executable=tmp_path / "codev.exe",
            **_authority_kwargs(tmp_path, tmp_path),
        )


def test_adoption_refuses_competing_authoritative_p18_lock(tmp_path: Path) -> None:
    p18, _terminal = _p18_fixture(tmp_path)
    with (
        inputs.batch_runner_lock(p18, details={"test": "competitor"}),
        pytest.raises(BatchRunnerLockHeldError, match="lock is held"),
    ):
        inputs.adopt_legacy_cache(
            output_dir=tmp_path,
            executable=tmp_path / "codev.exe",
            p18_archive_root=p18,
            p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
        )


def test_p18_terminal_authority_remains_readable_while_lock_is_held(
    tmp_path: Path,
) -> None:
    p18, before = _p18_fixture(tmp_path)
    assert before["lock_file"] == {
        "path": str((p18 / ".p18-runner.lock").resolve()),
        "protocol": "atelier-batch-runner-os-byte-range-v1",
        "content_observed": False,
    }
    with inputs.batch_runner_lock(p18, details={"test": "terminal-observation"}):
        while_held = inputs._p18_terminal_authority(
            archive_root=p18,
            batch_id=inputs.P18_REQUIRED_BATCH_ID,
        )
    assert while_held == before


def test_adoption_wrong_archive_preflight_creates_no_lock_or_output(
    tmp_path: Path,
) -> None:
    output = tmp_path / "out"
    missing_archive = tmp_path / "missing-p18-archive"
    output_lock = output.parent / f".{output.name}.stageb-input-lock"
    with pytest.raises((FileNotFoundError, ValueError)):
        inputs.adopt_legacy_cache(
            output_dir=output,
            executable=tmp_path / "codev.exe",
            p18_archive_root=missing_archive,
            p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
        )
    assert not missing_archive.exists()
    assert not output_lock.exists()
    assert not inputs.P18_GLOBAL_WINDOW_ROOT.exists()
    assert not output.exists()


def test_authoritative_lock_is_cross_process_nonblocking(tmp_path: Path) -> None:
    root = tmp_path / "cross-process-lock"
    code = (
        "from pathlib import Path\n"
        "from app.core.batch_run_lock import batch_runner_lock, BatchRunnerLockHeldError\n"
        f"root=Path({str(root)!r})\n"
        "try:\n"
        "  with batch_runner_lock(root): pass\n"
        "except BatchRunnerLockHeldError:\n"
        "  print('HELD')\n"
    )
    with inputs.batch_runner_lock(root, details={"test": "parent-holder"}):
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=inputs.ROOT,
            env={**os.environ, "PYTHONUTF8": "1"},
            check=True,
            capture_output=True,
            text=True,
        )
    assert completed.stdout.strip() == "HELD"


def test_public_adoption_holds_all_four_authoritative_locks_against_subprocesses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out"
    p18, _terminal = _p18_fixture(tmp_path)
    roots = (
        output.parent / f".{output.name}.stageb-input-lock",
        inputs.P18_GLOBAL_WINDOW_ROOT,
        p18,
        inputs.CODEV_LOCK_ROOT,
    )

    def inside_critical_section(**_kwargs: object) -> dict[str, int]:
        for root in roots:
            code = (
                "from pathlib import Path\n"
                "from app.core.batch_run_lock import batch_runner_lock, BatchRunnerLockHeldError\n"
                f"root=Path({str(root)!r})\n"
                "try:\n"
                "  with batch_runner_lock(root): pass\n"
                "except BatchRunnerLockHeldError:\n"
                "  print('HELD')\n"
            )
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=inputs.ROOT,
                env={**os.environ, "PYTHONUTF8": "1"},
                check=True,
                capture_output=True,
                text=True,
            )
            assert completed.stdout.strip() == "HELD"
        return {"created": 0, "verified": 0}

    monkeypatch.setattr(inputs, "_adopt_legacy_cache_locked", inside_critical_section)
    assert inputs.adopt_legacy_cache(
        output_dir=output,
        executable=tmp_path / "codev.exe",
        p18_archive_root=p18,
        p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
    ) == {"created": 0, "verified": 0}
    for root in roots:
        assert not (root / ".p18-runner.owner.json").exists()


def test_partial_manifest_snapshot_resumes_to_exact_eight_without_overwriting_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = tuple(inputs.InputJob(f"case-{index}", 2.4, "test") for index in range(1, 9))
    records = {}
    results = {}
    zmx_dir = tmp_path / "resume-zmx"
    zmx_dir.mkdir()
    for index, job in enumerate(jobs, start=1):
        emitted = tmp_path / f"accepted-{index}.zmx"
        emitted.write_bytes(f"accepted-{index}".encode())
        (zmx_dir / f"case-{index}.zmx").write_bytes(f"source-{index}".encode())
        records[job.case_id] = {
            "source_zmx": f"case-{index}.zmx",
            "efl_mm": 4.0,
            "image_height_mm": 3.0,
            "scenario": "smartphone-wide",
        }
        results[job.case_id] = _accepted_result(
            source_name=f"case-{index}.zmx", accepted_path=emitted, efl=4.0, fnum=2.4
        )
    monkeypatch.setattr(inputs, "JOBS", jobs)
    monkeypatch.setattr(inputs, "ZMX_DIR", zmx_dir)
    monkeypatch.setattr(inputs, "_index", lambda: records)
    monkeypatch.setattr(
        inputs,
        "_run_job",
        lambda *, job, **_kwargs: _cache(tmp_path, job.case_id, results[job.case_id]),
    )
    monkeypatch.setattr(inputs, "validate_retained_stageb_authority", lambda **_kwargs: None)
    output = tmp_path / "out"
    authority_kwargs = _authority_kwargs(tmp_path, output)
    first = inputs.build_inputs(
        output_dir=output,
        required_count=8,
        executable=tmp_path / "unused",
        limit=4,
        **authority_kwargs,
    )
    first_snapshot = next((output / "manifest-v2-snapshots").iterdir())
    preserved = (first_snapshot.read_bytes(), first_snapshot.stat().st_mtime_ns)
    second = inputs.build_inputs(
        output_dir=output,
        required_count=8,
        executable=tmp_path / "unused",
        limit=8,
        **authority_kwargs,
    )
    assert first["complete"] is False
    assert second["complete"] is True
    assert second["accepted_count"] == 8
    assert (first_snapshot.read_bytes(), first_snapshot.stat().st_mtime_ns) == preserved
    assert len(list((output / "manifest-v2-snapshots").iterdir())) == 2
    current = output / "manifest-v2.json"
    complete_snapshot = (current.read_bytes(), current.stat().st_mtime_ns)
    snapshot_inventory = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (output / "manifest-v2-snapshots").iterdir()
    }
    with pytest.raises(ValueError, match="refusing to downgrade"):
        inputs.build_inputs(
            output_dir=output,
            required_count=8,
            executable=tmp_path / "unused",
            limit=4,
            **authority_kwargs,
        )
    assert (current.read_bytes(), current.stat().st_mtime_ns) == complete_snapshot
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (output / "manifest-v2-snapshots").iterdir()
    } == snapshot_inventory


@pytest.mark.parametrize("limit", (4, 8))
def test_manifest_noop_rerun_preserves_current_and_snapshot_bytes_and_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    jobs = tuple(inputs.InputJob(f"case-{index}", 2.4, "test") for index in range(1, 9))
    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    records = {}
    results = {}
    for index, job in enumerate(jobs, start=1):
        source = f"case-{index}.zmx"
        (zmx_dir / source).write_bytes(f"source-{index}".encode())
        emitted = tmp_path / f"accepted-{index}.zmx"
        emitted.write_bytes(f"accepted-{index}".encode())
        records[job.case_id] = {
            "source_zmx": source,
            "efl_mm": 4.0,
            "image_height_mm": 3.0,
            "scenario": "smartphone-wide",
        }
        results[job.case_id] = _accepted_result(
            source_name=source, accepted_path=emitted, efl=4.0, fnum=2.4
        )
    monkeypatch.setattr(inputs, "JOBS", jobs)
    monkeypatch.setattr(inputs, "ZMX_DIR", zmx_dir)
    monkeypatch.setattr(inputs, "_index", lambda: records)
    monkeypatch.setattr(
        inputs,
        "_run_job",
        lambda *, job, **_kwargs: _cache(tmp_path, job.case_id, results[job.case_id]),
    )
    monkeypatch.setattr(inputs, "validate_retained_stageb_authority", lambda **_kwargs: None)
    output = tmp_path / "out"
    authority_kwargs = _authority_kwargs(tmp_path, output)
    first = inputs.build_inputs(
        output_dir=output,
        required_count=8,
        executable=tmp_path / "unused",
        limit=limit,
        **authority_kwargs,
    )
    current = output / "manifest-v2.json"
    snapshots = list((output / "manifest-v2-snapshots").iterdir())
    before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in [current, *snapshots]}
    second = inputs.build_inputs(
        output_dir=output,
        required_count=8,
        executable=tmp_path / "unused",
        limit=limit,
        **authority_kwargs,
    )
    assert second == first
    assert list((output / "manifest-v2-snapshots").iterdir()) == snapshots
    for path, value in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == value


def test_explicit_incomplete_recovery_writes_external_receipt_and_preserves_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = inputs.InputJob("case-1", 2.4, "test")
    identity = {"same": True}
    monkeypatch.setattr(inputs, "JOBS", (job,))
    monkeypatch.setattr(
        inputs,
        "_index",
        lambda: {"case-1": {"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0}},
    )
    monkeypatch.setattr(inputs, "_current_identity", lambda **_kwargs: identity)
    monkeypatch.setattr(inputs, "_active_phase18_processes", lambda: [])
    monkeypatch.setattr(inputs, "CODEV_LOCK_ROOT", tmp_path / "codev-lock")
    attempt = tmp_path / "out" / "ladders" / "case-1" / "attempts" / "old"
    attempt.mkdir(parents=True)
    inputs._exclusive_json(
        attempt / "intent.json",
        {
            "schema_id": inputs.INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": "old",
            "created_at": "now",
            "identity": identity,
            "lock_owner_ids": _owner_ids(),
        },
    )
    before = inputs._attempt_snapshot(attempt)
    p18, terminal = _p18_fixture(tmp_path)
    summary = inputs.recover_incomplete_attempts(
        output_dir=tmp_path / "out",
        executable=tmp_path / "codev.exe",
        p18_archive_root=p18,
        p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
        recover_stale_p18_lock=False,
        recover_stale_codev_lock=False,
    )
    assert summary == {"created": 1, "verified": 0}
    assert inputs._attempt_snapshot(attempt) == before
    receipt = tmp_path / "out" / "attempt-recoveries" / "case-1" / "old.json"
    assert inputs._strict_json(receipt)["classification"] == "intent-only"
    monkeypatch.setattr(
        inputs,
        "run_codev_target_fno_ladder",
        lambda **_kwargs: {
            "schema": "atelier-stagec-stageb-input-error-v1",
            "case_id": "case-1",
            "target_achieved": False,
            "accepted_final": None,
        },
    )
    cache = inputs._run_job(
        job=job,
        meta={"source_zmx": "case.zmx", "efl_mm": 4.0, "image_height_mm": 3.0},
        output_dir=tmp_path / "out",
        executable=tmp_path / "codev.exe",
        recovery_p18_root=inputs.P18_GLOBAL_WINDOW_ROOT,
        p18_terminal_authority=terminal,
        lock_authority=inputs._lock_authority(
            output_root=tmp_path / ".out.stageb-input-lock",
            p18_archive_root=p18,
            mode="pre-run-held",
        ),
        lock_owner_ids=_owner_ids(),
    )
    assert cache["scope"] == "pre-run-bound"
    assert len(list((tmp_path / "out" / "ladders" / "case-1" / "attempts").iterdir())) == 2


@pytest.mark.parametrize("mode", ("normal", "adopt", "recover"))
def test_main_cli_uses_each_mode_lock_path_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    lock_calls = []
    mode_calls = []
    p18, _terminal = _p18_fixture(tmp_path)

    @contextmanager
    def fake_lock(root: Path, **_kwargs: object):
        lock_calls.append(root)
        yield {"lock_id": "test"}

    monkeypatch.setattr(inputs, "batch_runner_lock", fake_lock)
    monkeypatch.setattr(inputs, "_active_phase18_processes", lambda: [])
    monkeypatch.setattr(
        inputs,
        "build_inputs",
        lambda **_kwargs: {"accepted_count": 8, "complete": True},
    )
    monkeypatch.setattr(
        inputs,
        "adopt_legacy_cache",
        lambda **_kwargs: mode_calls.append("adopt") or {"created": 1, "verified": 0},
    )
    monkeypatch.setattr(
        inputs,
        "recover_incomplete_attempts",
        lambda **_kwargs: mode_calls.append("recover") or {"created": 1, "verified": 0},
    )
    argv = [
        "p16_stagec_stageb_inputs.py",
        "--output-dir",
        str(tmp_path / "out"),
        "--executable",
        str(tmp_path / "codev.exe"),
        "--p18-archive-root",
        str(p18),
        "--p18-batch-id",
        inputs.P18_REQUIRED_BATCH_ID,
    ]
    if mode != "normal":
        argv += [f"--{'adopt-legacy-cache' if mode == 'adopt' else 'recover-incomplete-attempts'}"]
    monkeypatch.setattr(sys, "argv", argv)
    assert inputs.main() == 0
    if mode == "normal":
        assert len(lock_calls) == 3
        assert mode_calls == []
    else:
        assert lock_calls == []
        assert mode_calls == [mode]


@pytest.mark.parametrize(
    "extra",
    (
        ("--recover-stale-codev-lock",),
        ("--adopt-legacy-cache", "--recover-incomplete-attempts"),
        ("--adopt-legacy-cache", "--limit", "9"),
        ("--recover-incomplete-attempts", "--required-count", "9"),
    ),
)
def test_main_cli_rejects_flags_irrelevant_to_selected_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, extra: tuple[str, ...]
) -> None:
    p18, _terminal = _p18_fixture(tmp_path)
    argv = [
        "p16_stagec_stageb_inputs.py",
        "--output-dir",
        str(tmp_path / "out"),
        "--executable",
        str(tmp_path / "codev.exe"),
        "--p18-archive-root",
        str(p18),
        "--p18-batch-id",
        inputs.P18_REQUIRED_BATCH_ID,
        *extra,
    ]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(
        inputs,
        "build_inputs",
        lambda **_kwargs: pytest.fail("invalid CLI flags must fail before build"),
    )
    monkeypatch.setattr(
        inputs,
        "adopt_legacy_cache",
        lambda **_kwargs: pytest.fail("invalid CLI flags must fail before adoption"),
    )
    monkeypatch.setattr(
        inputs,
        "recover_incomplete_attempts",
        lambda **_kwargs: pytest.fail("invalid CLI flags must fail before recovery"),
    )
    with pytest.raises(SystemExit) as captured:
        inputs.main()
    assert captured.value.code == 2


def test_adoption_rejects_lock_root_alias_before_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "out"
    alias = output.parent / f".{output.name}.stageb-input-lock"
    _p18_fixture(tmp_path, archive_root=alias)
    with pytest.raises(ValueError, match="pairwise distinct"):
        inputs.adopt_legacy_cache(
            output_dir=output,
            executable=tmp_path / "codev.exe",
            p18_archive_root=alias,
            p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
        )


def test_recovery_stale_flag_is_not_a_habitual_bypass(tmp_path: Path, monkeypatch) -> None:
    p18, _terminal = _p18_fixture(tmp_path)
    with pytest.raises(ValueError, match="neither global nor archive root was stale"):
        inputs.recover_incomplete_attempts(
            output_dir=tmp_path / "out",
            executable=tmp_path / "codev.exe",
            p18_archive_root=p18,
            p18_batch_id=inputs.P18_REQUIRED_BATCH_ID,
            recover_stale_p18_lock=True,
            recover_stale_codev_lock=False,
        )
    assert not (tmp_path / "out" / "attempt-recoveries").exists()
