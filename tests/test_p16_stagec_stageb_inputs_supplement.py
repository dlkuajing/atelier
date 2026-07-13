from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from scripts import p16_stagec_stageb_inputs as base
from scripts import p16_stagec_stageb_inputs_supplement as supplement


def _authority_kwargs() -> dict[str, object]:
    return {
        "recovery_p18_root": Path("p18-global"),
        "lock_authority": {"mode": "pre-run-held"},
        "lock_owner_ids": {
            "output": "a" * 32,
            "p18_global": "b" * 32,
            "p18_archive": "c" * 32,
            "codev": None,
        },
        "p18_terminal_authority": {"batch_id": "night-20260711"},
    }


def _run_kwargs(tmp_path: Path, job: base.InputJob) -> dict[str, object]:
    return {
        "job": job,
        "meta": {"case_id": job.case_id},
        "output_dir": tmp_path / "stageb-inputs",
        "executable": tmp_path / "codev.exe",
        **_authority_kwargs(),
    }


def _accepted_result(*, accepted_path: Path, efl: float, fnum: float) -> dict[str, object]:
    accepted = {
        "rung_index": 3,
        "status": "measured",
        "measured_fnum": fnum,
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
        "quality_note": "offline wrapper integration fixture",
        "optimized_zmx_path": str(accepted_path),
    }
    return {
        "schema": "atelier-p15-fno-ladder-v1",
        "target_achieved": True,
        "accepted_final": accepted,
        "target_efl_mm": efl,
        "fnum_target": fnum,
        "stage": "B",
        "rung_count": 3,
        "fnum_tolerance_pct": 8.0,
        "vig_ladder": [0.0, 0.2],
        "ray_retry_vig_ladder": [0.2, 0.3],
        "num_fields": 3,
        "extra_dof": "both",
    }


def test_reviewed_supplement_is_appended_in_exact_unique_order_with_honest_rationale() -> None:
    expected = (
        ("US10330891B2", 2.4),
        ("US20180143405A1", 2.4),
        ("US20140111876A1", 2.4),
        ("US-11906710-B2-e6", 2.35),
        ("US-10101561-B2-e3", 2.2),
        ("US-11668898-B2-e6", 2.4),
        ("US-10921568-B2-e9", 2.2),
        ("US-12174456-B2-e5", 2.4),
    )

    assert supplement.JOBS[: len(supplement._ORIGINAL_JOBS)] == supplement._ORIGINAL_JOBS
    assert tuple((job.case_id, job.fnum_target) for job in supplement.SUPPLEMENTAL_JOBS) == expected
    assert len({job.case_id for job in supplement.JOBS}) == len(supplement.JOBS)
    assert all(
        "evidence-ranked supplemental exploration" in job.rationale
        and "no Stage B acceptance is presumed" in job.rationale
        for job in supplement.SUPPLEMENTAL_JOBS
    )


def test_reviewed_supplement_cases_resolve_to_existing_index_sources() -> None:
    supplement._validate_reviewed_plan()
    rows = base._index()

    assert all(
        (base.ZMX_DIR / str(rows[job.case_id]["source_zmx"])).is_file()
        for job in supplement.SUPPLEMENTAL_JOBS
    )


def test_original_identity_remains_byte_for_byte_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_identity = {
        "runner_sources": {
            "files": {"scripts/p16_stagec_stageb_inputs.py": {"sha256": "a", "size": 1}},
            "aggregate_sha256": "base-aggregate",
        },
        "sentinel": ["unchanged"],
    }
    monkeypatch.setattr(
        supplement,
        "_ORIGINAL_CURRENT_IDENTITY",
        lambda **_kwargs: original_identity,
    )

    actual = supplement._current_identity(job=supplement._ORIGINAL_JOBS[0])

    assert actual is original_identity
    assert base._canonical_bytes(actual) == base._canonical_bytes(original_identity)


def test_supplement_identity_binds_wrapper_descriptor_and_recomputes_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {"scripts/p16_stagec_stageb_inputs.py": {"sha256": "a", "size": 1}}
    monkeypatch.setattr(
        supplement,
        "_ORIGINAL_CURRENT_IDENTITY",
        lambda **_kwargs: {
            "runner_sources": {
                "files": files,
                "aggregate_sha256": hashlib.sha256(base._canonical_bytes(files)).hexdigest(),
            }
        },
    )

    actual = supplement._current_identity(job=supplement.SUPPLEMENTAL_JOBS[0])
    sources = actual["runner_sources"]
    assert isinstance(sources, dict)
    actual_files = sources["files"]
    assert isinstance(actual_files, dict)
    wrapper = Path(supplement.__file__).resolve()
    assert actual_files[supplement._WRAPPER_RELATIVE_PATH] == {
        "sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
        "size": wrapper.stat().st_size,
    }
    assert (
        sources["aggregate_sha256"]
        == hashlib.sha256(base._canonical_bytes(actual_files)).hexdigest()
    )
    assert files == {"scripts/p16_stagec_stageb_inputs.py": {"sha256": "a", "size": 1}}


def test_original_cache_only_miss_is_zero_write_and_never_delegates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "stageb-inputs"
    delegated = False

    def forbidden_delegate(**_kwargs: object) -> dict[str, object]:
        nonlocal delegated
        delegated = True
        raise AssertionError("true-machine delegation must not run")

    monkeypatch.setattr(supplement, "_ORIGINAL_RUN_JOB", forbidden_delegate)
    monkeypatch.setattr(supplement, "_current_identity", lambda **_kwargs: {"identity": "old"})
    monkeypatch.setattr(base, "_validate_adoption", lambda **_kwargs: None)

    with pytest.raises(RuntimeError, match=r"exactly one hit \(missing\)"):
        supplement._run_job(**_run_kwargs(tmp_path, supplement._ORIGINAL_JOBS[0]))

    assert delegated is False
    assert not output_dir.exists()
    assert list(tmp_path.rglob("*")) == []


def test_original_cache_only_returns_one_exact_attempt_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = supplement._ORIGINAL_JOBS[0]
    attempt = tmp_path / "stageb-inputs" / "ladders" / job.case_id / "attempts" / "one"
    attempt.mkdir(parents=True)
    (attempt / "intent.json").write_text("{}", encoding="utf-8")
    (attempt / "ladder-result.json").write_text("{}", encoding="utf-8")
    expected_identity = {"identity": "old"}
    expected_cache = {"result": {}, "path": attempt / "ladder-result.json"}
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(supplement, "_current_identity", lambda **_kwargs: expected_identity)
    monkeypatch.setattr(base, "_strict_json", lambda _path: {"identity": expected_identity})
    monkeypatch.setattr(
        base,
        "_validate_bound_attempt",
        lambda **_kwargs: expected_cache,
    )
    monkeypatch.setattr(base, "_validate_adoption", lambda **_kwargs: None)

    actual = supplement._run_job(**_run_kwargs(tmp_path, job))
    repeated = supplement._run_job(**_run_kwargs(tmp_path, job))

    assert actual is expected_cache
    assert repeated is expected_cache
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_original_cache_only_returns_one_exact_adoption_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = supplement._ORIGINAL_JOBS[0]
    legacy_result = tmp_path / "stageb-inputs" / "ladders" / job.case_id / "ladder-result.json"
    adoption = tmp_path / "stageb-inputs" / "adoptions-v1" / f"{job.case_id}.json"
    legacy_result.parent.mkdir(parents=True)
    adoption.parent.mkdir(parents=True)
    legacy_result.write_text("{}", encoding="utf-8")
    adoption.write_text("{}", encoding="utf-8")
    expected_cache = {"result": {}, "path": legacy_result, "record": adoption}
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(supplement, "_current_identity", lambda **_kwargs: {"identity": "old"})
    monkeypatch.setattr(base, "_validate_adoption", lambda **_kwargs: expected_cache)

    actual = supplement._run_job(**_run_kwargs(tmp_path, job))

    assert actual is expected_cache
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize("failure", ["incomplete", "drift", "damaged", "duplicate"])
def test_original_cache_only_fails_closed_for_unsafe_cache_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    job = supplement._ORIGINAL_JOBS[0]
    attempt = tmp_path / "stageb-inputs" / "ladders" / job.case_id / "attempts" / "one"
    attempt.mkdir(parents=True)
    (attempt / "intent.json").write_text("{}", encoding="utf-8")
    if failure != "incomplete":
        (attempt / "ladder-result.json").write_text("{}", encoding="utf-8")
    expected_identity = {"identity": "old"}
    monkeypatch.setattr(supplement, "_current_identity", lambda **_kwargs: expected_identity)

    def strict_json(_path: Path) -> dict[str, object]:
        if failure == "damaged":
            raise ValueError("damaged fixture")
        return {"identity": {"identity": "drift"} if failure == "drift" else expected_identity}

    monkeypatch.setattr(base, "_strict_json", strict_json)
    monkeypatch.setattr(
        base,
        "_validate_bound_attempt",
        lambda **_kwargs: {"result": {}, "path": attempt / "ladder-result.json"},
    )
    monkeypatch.setattr(
        base,
        "_validate_adoption",
        lambda **_kwargs: (
            {"result": {}, "path": tmp_path / "adoption.json"} if failure == "duplicate" else None
        ),
    )

    with pytest.raises(RuntimeError, match=failure):
        supplement._run_job(**_run_kwargs(tmp_path, job))


def test_supplemental_job_alone_delegates_to_original_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {"result": {"target_achieved": False}}
    observed: dict[str, object] = {}

    def delegate(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return expected

    monkeypatch.setattr(supplement, "_ORIGINAL_RUN_JOB", delegate)
    kwargs = _run_kwargs(tmp_path, supplement.SUPPLEMENTAL_JOBS[0])

    actual = supplement._run_job(**kwargs)

    assert actual is expected
    assert observed == kwargs


def test_six_old_plus_two_supplemental_results_publish_exact_eight_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zmx_root = tmp_path / "zmx"
    zmx_root.mkdir()
    # Keep the manifest snapshot path below legacy Windows MAX_PATH.
    output_dir = tmp_path.parents[1] / "supplement-exact8"
    records: dict[str, dict[str, object]] = {}
    accepted_ids = {
        *(job.case_id for job in supplement._ORIGINAL_JOBS[:6]),
        *(job.case_id for job in supplement.SUPPLEMENTAL_JOBS[:2]),
    }
    caches: dict[str, dict[str, object]] = {}
    for job in supplement.JOBS:
        source = zmx_root / f"{job.case_id}.zmx"
        source.write_bytes(f"source:{job.case_id}".encode())
        records[job.case_id] = {
            "case_id": job.case_id,
            "scenario": "smartphone-wide",
            "source_zmx": source.name,
            "efl_mm": 4.0,
            "image_height_mm": 3.0,
        }
        accepted_path = tmp_path / "emitted" / f"{job.case_id}.zmx"
        accepted_path.parent.mkdir(exist_ok=True)
        accepted_path.write_bytes(f"accepted:{job.case_id}".encode())
        result = (
            _accepted_result(accepted_path=accepted_path, efl=4.0, fnum=job.fnum_target)
            if job.case_id in accepted_ids
            else {"target_achieved": False, "accepted_final": None}
        )
        cache_root = tmp_path / "cache" / job.case_id
        cache_root.mkdir(parents=True)
        result_path = cache_root / "ladder-result.json"
        raw_path = cache_root / "raw-ladder-result.json"
        record_path = cache_root / "intent.json"
        base._atomic_json(result_path, result)
        base._atomic_json(raw_path, result)
        base._atomic_json(record_path, {"case_id": job.case_id})
        caches[job.case_id] = {
            "result": result,
            "path": result_path,
            "raw": raw_path,
            "scope": "pre-run-bound",
            "record": record_path,
        }

    observed_old: list[str] = []
    observed_supplemental: list[str] = []

    def old_cache(*, job: base.InputJob, **_kwargs: object) -> dict[str, object]:
        observed_old.append(job.case_id)
        return caches[job.case_id]

    def supplemental_run(*, job: base.InputJob, **_kwargs: object) -> dict[str, object]:
        observed_supplemental.append(job.case_id)
        return caches[job.case_id]

    terminal = {
        "archive_root": str(tmp_path / "p18-archive"),
        "batch_id": base.P18_REQUIRED_BATCH_ID,
        "target_count": 50,
    }
    validator_calls: list[dict[str, object]] = []
    monkeypatch.setattr(base, "JOBS", base.JOBS)
    monkeypatch.setattr(base, "_run_job", base._run_job)
    monkeypatch.setattr(base, "_current_identity", base._current_identity)
    monkeypatch.setattr(base, "ZMX_DIR", zmx_root)
    monkeypatch.setattr(base, "_index", lambda: records)
    monkeypatch.setattr(base, "_require_official_toolchain", lambda executable: executable)
    monkeypatch.setattr(base, "_p18_terminal_authority", lambda **_kwargs: terminal)
    monkeypatch.setattr(
        base,
        "validate_retained_stageb_authority",
        lambda **kwargs: validator_calls.append(kwargs),
    )
    monkeypatch.setattr(supplement, "_original_cache_only", old_cache)
    monkeypatch.setattr(supplement, "_ORIGINAL_RUN_JOB", supplemental_run)
    supplement._install_wrapper()

    manifest = base.build_inputs(
        output_dir=output_dir,
        required_count=8,
        executable=tmp_path / "unused-codev.exe",
        recovery_p18_root=tmp_path / "p18-global",
        p18_terminal_authority=terminal,
        lock_authority={"mode": "pre-run-held"},
        lock_owner_ids=_authority_kwargs()["lock_owner_ids"],
    )

    assert manifest["complete"] is True
    assert manifest["accepted_count"] == 8
    assert [row["case_id"] for row in manifest["accepted"]] == [
        *(job.case_id for job in supplement._ORIGINAL_JOBS[:6]),
        *(job.case_id for job in supplement.SUPPLEMENTAL_JOBS[:2]),
    ]
    assert observed_old == [job.case_id for job in supplement._ORIGINAL_JOBS]
    assert observed_supplemental == [job.case_id for job in supplement.SUPPLEMENTAL_JOBS[:2]]
    assert len(validator_calls) == 16
    assert manifest["expert_verdict"] is None


def test_cli_rejects_adoption_before_plan_validation_or_base_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [str(Path(supplement.__file__)), "--adopt-legacy-cache"],
    )
    monkeypatch.setattr(
        supplement,
        "_validate_reviewed_plan",
        lambda: (_ for _ in ()).throw(AssertionError("plan validation must not run")),
    )
    monkeypatch.setattr(
        base,
        "main",
        lambda: (_ for _ in ()).throw(AssertionError("base main must not run")),
    )

    with pytest.raises(SystemExit, match="refuses --adopt-legacy-cache"):
        supplement.main()


def test_cli_rejects_recovery_before_plan_validation_or_base_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [str(Path(supplement.__file__)), "--recover-incomplete-attempts"],
    )
    monkeypatch.setattr(
        supplement,
        "_validate_reviewed_plan",
        lambda: (_ for _ in ()).throw(AssertionError("plan validation must not run")),
    )
    monkeypatch.setattr(
        base,
        "main",
        lambda: (_ for _ in ()).throw(AssertionError("base main must not run")),
    )

    with pytest.raises(SystemExit, match="refuses --recover-incomplete-attempts"):
        supplement.main()


def test_install_reuses_base_main_and_patches_identity_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_jobs = base.JOBS
    original_run_job = base._run_job
    original_identity = base._current_identity
    monkeypatch.setattr(base, "JOBS", original_jobs)
    monkeypatch.setattr(base, "_run_job", original_run_job)
    monkeypatch.setattr(base, "_current_identity", original_identity)

    supplement._install_wrapper()

    assert base.JOBS == supplement.JOBS
    assert base._run_job is supplement._run_job
    assert base._current_identity is supplement._current_identity


def test_main_delegates_to_base_locking_and_active_process_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_jobs = base.JOBS
    original_run_job = base._run_job
    original_identity = base._current_identity
    monkeypatch.setattr(base, "JOBS", original_jobs)
    monkeypatch.setattr(base, "_run_job", original_run_job)
    monkeypatch.setattr(base, "_current_identity", original_identity)
    monkeypatch.setattr(supplement, "_validate_reviewed_plan", lambda: None)
    monkeypatch.setattr(base, "main", lambda: 17)
    monkeypatch.setattr(sys, "argv", [str(Path(supplement.__file__))])

    assert supplement.main() == 17
    assert base.JOBS == supplement.JOBS
    assert base._run_job is supplement._run_job
    assert base._current_identity is supplement._current_identity
