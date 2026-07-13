from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from scripts import p16_stagec_stageb_inputs as base
from scripts import p16_stagec_stageb_inputs_supplement as first
from scripts import p16_stagec_stageb_inputs_supplement2 as second


def _authority_kwargs() -> dict[str, object]:
    return {
        "recovery_p18_root": Path("unused-p18-global"),
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


def test_second_supplement_has_exact_reviewed_order_targets_and_honest_rationale() -> None:
    expected = (
        ("US-11906710-B2-e5", 2.28),
        ("US-11906710-B2-e8", 2.22),
        ("US-11906710-B2-e1", 2.20),
        ("US-11906710-B2-e4", 2.15),
        ("US-10921568-B2-e7", 2.30),
        ("US-12523849-B2-e5", 2.47),
        ("US-12523849-B2-e4", 2.47),
        ("US-11906710-B2-e2", 2.00),
    )

    assert (*second._BASE_JOBS, *second._FIRST_JOBS) == second.HISTORICAL_JOBS
    assert (*second.HISTORICAL_JOBS, *second.SUPPLEMENTAL_JOBS) == second.JOBS
    assert tuple((job.case_id, job.fnum_target) for job in second.SUPPLEMENTAL_JOBS) == expected
    assert len({job.case_id for job in second.JOBS}) == len(second.JOBS) == 37
    assert all(
        "evidence-ranked second supplemental exploration" in job.rationale
        and "no Stage B acceptance is presumed" in job.rationale
        for job in second.SUPPLEMENTAL_JOBS
    )


def test_second_supplement_cases_resolve_to_existing_index_sources() -> None:
    second._validate_reviewed_plan()
    records = base._index()

    assert all(
        (base.ZMX_DIR / str(records[job.case_id]["source_zmx"])).is_file()
        for job in second.SUPPLEMENTAL_JOBS
    )


def test_base_and_first_wrapper_hard_pins_match_reviewed_bytes() -> None:
    assert second._source_descriptor(Path(base.__file__)) == {
        "sha256": second._TRUSTED_BASE_SHA256,
        "size": second._TRUSTED_BASE_SIZE,
    }
    assert second._source_descriptor(Path(first.__file__)) == {
        "sha256": second._TRUSTED_FIRST_SHA256,
        "size": second._TRUSTED_FIRST_SIZE,
    }
    second._assert_trusted_predecessors()


@pytest.mark.parametrize("pin", ["_TRUSTED_BASE_SHA256", "_TRUSTED_FIRST_SHA256"])
def test_predecessor_pin_drift_blocks_install_before_dispatch_mutation(
    monkeypatch: pytest.MonkeyPatch, pin: str
) -> None:
    base_jobs_before = base.JOBS
    base_run_before = base._run_job
    base_identity_before = base._current_identity
    monkeypatch.setattr(second, pin, "0" * 64)

    with pytest.raises(RuntimeError, match="differs from the reviewed hard pin"):
        second._install_wrapper()

    assert base.JOBS is base_jobs_before
    assert base._run_job is base_run_before
    assert base._current_identity is base_identity_before


def test_three_identity_families_bind_only_their_executed_wrappers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_files = {"scripts/p16_stagec_stageb_inputs.py": {"sha256": "base", "size": 1}}
    base_identity = {
        "runner_sources": {
            "files": base_files,
            "aggregate_sha256": hashlib.sha256(base._canonical_bytes(base_files)).hexdigest(),
        },
        "sentinel": "base",
    }
    monkeypatch.setattr(second, "_assert_trusted_predecessors", lambda: None)
    monkeypatch.setattr(second, "_BASE_CURRENT_IDENTITY", lambda **_kwargs: base_identity)
    monkeypatch.setattr(first, "_ORIGINAL_CURRENT_IDENTITY", lambda **_kwargs: base_identity)

    base_actual = second._current_identity(job=second._BASE_JOBS[0])
    first_actual = second._current_identity(job=second._FIRST_JOBS[0])
    second_actual = second._current_identity(job=second.SUPPLEMENTAL_JOBS[0])

    assert base_actual is base_identity
    base_sources = base_actual["runner_sources"]
    first_sources = first_actual["runner_sources"]
    second_sources = second_actual["runner_sources"]
    assert isinstance(base_sources, dict)
    assert isinstance(first_sources, dict)
    assert isinstance(second_sources, dict)
    assert first._WRAPPER_RELATIVE_PATH not in base_sources["files"]
    assert second._SECOND_RELATIVE_PATH not in base_sources["files"]
    assert first._WRAPPER_RELATIVE_PATH in first_sources["files"]
    assert second._SECOND_RELATIVE_PATH not in first_sources["files"]
    assert first._WRAPPER_RELATIVE_PATH in second_sources["files"]
    assert second._SECOND_RELATIVE_PATH in second_sources["files"]
    assert (
        first_sources["aggregate_sha256"]
        == hashlib.sha256(base._canonical_bytes(first_sources["files"])).hexdigest()
    )
    assert (
        second_sources["aggregate_sha256"]
        == hashlib.sha256(base._canonical_bytes(second_sources["files"])).hexdigest()
    )


@pytest.mark.parametrize("job", [second._BASE_JOBS[0], second._FIRST_JOBS[0]])
def test_historical_cache_miss_is_zero_write_and_never_delegates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    job: base.InputJob,
) -> None:
    delegated = False

    def forbidden_delegate(**_kwargs: object) -> dict[str, object]:
        nonlocal delegated
        delegated = True
        raise AssertionError("historical job must never reach the true-machine runner")

    monkeypatch.setattr(second, "_ORIGINAL_RUN_JOB", forbidden_delegate)
    monkeypatch.setattr(second, "_current_identity", lambda **_kwargs: {"identity": "old"})
    monkeypatch.setattr(base, "_validate_adoption", lambda **_kwargs: None)

    with pytest.raises(RuntimeError, match=r"exactly one hit \(missing\)"):
        second._run_job(**_run_kwargs(tmp_path, job))

    assert delegated is False
    assert list(tmp_path.rglob("*")) == []


def test_historical_exact_attempt_reuses_twice_without_byte_or_mtime_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = second._FIRST_JOBS[0]
    attempt = tmp_path / "stageb-inputs" / "ladders" / job.case_id / "attempts" / "one"
    attempt.mkdir(parents=True)
    (attempt / "intent.json").write_text("{}", encoding="utf-8")
    (attempt / "ladder-result.json").write_text("{}", encoding="utf-8")
    identity = {"identity": "first-wrapper-bound"}
    cache = {"result": {}, "path": attempt / "ladder-result.json"}
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(second, "_current_identity", lambda **_kwargs: identity)
    monkeypatch.setattr(base, "_strict_json", lambda _path: {"identity": identity})
    monkeypatch.setattr(base, "_validate_bound_attempt", lambda **_kwargs: cache)
    monkeypatch.setattr(base, "_validate_adoption", lambda **_kwargs: None)

    assert second._run_job(**_run_kwargs(tmp_path, job)) is cache
    assert second._run_job(**_run_kwargs(tmp_path, job)) is cache
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_historical_exact_adoption_reuses_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = second._BASE_JOBS[0]
    result = tmp_path / "stageb-inputs" / "ladders" / job.case_id / "ladder-result.json"
    adoption = tmp_path / "stageb-inputs" / "adoptions-v1" / f"{job.case_id}.json"
    result.parent.mkdir(parents=True)
    adoption.parent.mkdir(parents=True)
    result.write_text("{}", encoding="utf-8")
    adoption.write_text("{}", encoding="utf-8")
    cache = {"result": {}, "path": result, "record": adoption}
    before = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(second, "_current_identity", lambda **_kwargs: {"identity": "base"})
    monkeypatch.setattr(base, "_validate_adoption", lambda **_kwargs: cache)

    assert second._run_job(**_run_kwargs(tmp_path, job)) is cache
    assert {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


@pytest.mark.parametrize("failure", ["incomplete", "drift", "damaged", "duplicate"])
def test_historical_unsafe_cache_states_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    job = second._FIRST_JOBS[0]
    attempt = tmp_path / "stageb-inputs" / "ladders" / job.case_id / "attempts" / "one"
    attempt.mkdir(parents=True)
    (attempt / "intent.json").write_text("{}", encoding="utf-8")
    if failure != "incomplete":
        (attempt / "ladder-result.json").write_text("{}", encoding="utf-8")
    identity = {"identity": "first"}
    monkeypatch.setattr(second, "_current_identity", lambda **_kwargs: identity)

    def strict_json(_path: Path) -> dict[str, object]:
        if failure == "damaged":
            raise ValueError("damaged fixture")
        return {"identity": {"identity": "drift"} if failure == "drift" else identity}

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
        second._run_job(**_run_kwargs(tmp_path, job))


def test_only_second_supplement_delegates_to_original_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = {"result": {"target_achieved": False}}
    observed: dict[str, object] = {}

    def delegate(**kwargs: object) -> dict[str, object]:
        observed.update(kwargs)
        return expected

    monkeypatch.setattr(second, "_ORIGINAL_RUN_JOB", delegate)
    kwargs = _run_kwargs(tmp_path, second.SUPPLEMENTAL_JOBS[0])

    assert second._run_job(**kwargs) is expected
    assert observed == kwargs


@pytest.mark.parametrize(
    "forbidden",
    [
        "--adopt-legacy-cache",
        "--recover-incomplete-attempts",
        "--recover-stale-output-lock",
        "--recover-stale-p18-lock",
        "--recover-stale-codev-lock",
    ],
)
def test_cli_rejects_every_adoption_or_recovery_mode_before_base_main(
    monkeypatch: pytest.MonkeyPatch, forbidden: str
) -> None:
    monkeypatch.setattr(sys, "argv", [str(Path(second.__file__)), forbidden])
    monkeypatch.setattr(
        second,
        "_validate_reviewed_plan",
        lambda: (_ for _ in ()).throw(AssertionError("plan validation must not run")),
    )
    monkeypatch.setattr(
        base,
        "main",
        lambda: (_ for _ in ()).throw(AssertionError("base main must not run")),
    )

    with pytest.raises(SystemExit, match="refuses adoption/recovery mode"):
        second.main()


def test_main_installs_second_dispatch_then_reuses_base_lock_and_active_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_jobs_before = base.JOBS
    base_run_before = base._run_job
    base_identity_before = base._current_identity
    monkeypatch.setattr(base, "JOBS", base_jobs_before)
    monkeypatch.setattr(base, "_run_job", base_run_before)
    monkeypatch.setattr(base, "_current_identity", base_identity_before)
    monkeypatch.setattr(second, "_validate_reviewed_plan", lambda: None)
    monkeypatch.setattr(second, "_assert_trusted_predecessors", lambda: None)
    monkeypatch.setattr(base, "main", lambda: 23)
    monkeypatch.setattr(sys, "argv", [str(Path(second.__file__))])

    assert second.main() == 23
    assert base.JOBS == second.JOBS
    assert base._run_job is second._run_job
    assert base._current_identity is second._current_identity


def test_job_descriptor_drift_is_rejected_for_each_identity_family() -> None:
    for job in (second._BASE_JOBS[0], second._FIRST_JOBS[0], second.SUPPLEMENTAL_JOBS[0]):
        drifted = base.InputJob(job.case_id, job.fnum_target + 0.1, job.rationale)
        with pytest.raises(ValueError, match="descriptor drifted"):
            second._job_family(drifted)
