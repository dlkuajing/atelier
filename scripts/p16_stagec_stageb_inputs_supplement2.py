"""Continue Stage B with a second reviewed supplemental job set.

The 21 base jobs and the first eight supplemental jobs are immutable cache
authority.  This wrapper validates exactly one existing cache result for each
of those 29 jobs and never delegates them to a runner.  Only the eight jobs
declared here may reach the original production ``_run_job`` implementation.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import p16_stagec_stageb_inputs as base  # noqa: E402
from scripts import p16_stagec_stageb_inputs_supplement as first  # noqa: E402

_TRUSTED_BASE_SHA256 = "4f94a0cbc01405a7b3025f6c2ebadf9403282d83d566fe46bad0390b2f79d080"
_TRUSTED_BASE_SIZE = 73242
_TRUSTED_FIRST_SHA256 = "9ffcbd381ccb62d8caefd01bd28e3dc7fed57a856d3b8c7a26d92cb7d40cae30"
_TRUSTED_FIRST_SIZE = 9864

_BASE_JOBS = tuple(first._ORIGINAL_JOBS)
_FIRST_JOBS = tuple(first.SUPPLEMENTAL_JOBS)
_BASE_CURRENT_IDENTITY = first._ORIGINAL_CURRENT_IDENTITY
_FIRST_CURRENT_IDENTITY = first._current_identity
_ORIGINAL_RUN_JOB = first._ORIGINAL_RUN_JOB

_RATIONALE = "evidence-ranked second supplemental exploration; no Stage B acceptance is presumed"
SUPPLEMENTAL_JOBS = (
    base.InputJob("US-11906710-B2-e5", 2.28, _RATIONALE),
    base.InputJob("US-11906710-B2-e8", 2.22, _RATIONALE),
    base.InputJob("US-11906710-B2-e1", 2.20, _RATIONALE),
    base.InputJob("US-11906710-B2-e4", 2.15, _RATIONALE),
    base.InputJob("US-10921568-B2-e7", 2.30, _RATIONALE),
    base.InputJob("US-12523849-B2-e5", 2.47, _RATIONALE),
    base.InputJob("US-12523849-B2-e4", 2.47, _RATIONALE),
    base.InputJob("US-11906710-B2-e2", 2.00, _RATIONALE),
)
HISTORICAL_JOBS = (*_BASE_JOBS, *_FIRST_JOBS)
JOBS = (*HISTORICAL_JOBS, *SUPPLEMENTAL_JOBS)

_BASE_BY_CASE = {job.case_id: job for job in _BASE_JOBS}
_FIRST_BY_CASE = {job.case_id: job for job in _FIRST_JOBS}
_SECOND_BY_CASE = {job.case_id: job for job in SUPPLEMENTAL_JOBS}
_SECOND_RELATIVE_PATH = "scripts/p16_stagec_stageb_inputs_supplement2.py"


def _source_descriptor(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    raw = resolved.read_bytes()
    without_crlf = raw.replace(b"\r\n", b"")
    if b"\r" in without_crlf:
        raise RuntimeError("reviewed source contains a bare CR line ending")
    line_feed_count = raw.count(b"\n")
    crlf_count = raw.count(b"\r\n")
    if crlf_count not in (0, line_feed_count):
        raise RuntimeError("reviewed source contains mixed LF and CRLF line endings")
    canonical = raw.replace(b"\r\n", b"\n") if crlf_count else raw
    return {"sha256": hashlib.sha256(canonical).hexdigest(), "size": len(canonical)}


def _assert_trusted_predecessors() -> None:
    base_descriptor = _source_descriptor(Path(base.__file__))
    first_descriptor = _source_descriptor(Path(first.__file__))
    if base_descriptor != {
        "sha256": _TRUSTED_BASE_SHA256,
        "size": _TRUSTED_BASE_SIZE,
    }:
        raise RuntimeError("base Stage B wrapper source differs from the reviewed hard pin")
    if first_descriptor != {
        "sha256": _TRUSTED_FIRST_SHA256,
        "size": _TRUSTED_FIRST_SIZE,
    }:
        raise RuntimeError("first Stage B supplement source differs from the reviewed hard pin")


def _job_family(job: base.InputJob) -> str:
    expected = _BASE_BY_CASE.get(job.case_id)
    if expected is not None:
        if job != expected:
            raise ValueError(f"base Stage B job descriptor drifted: {job.case_id}")
        return "base-cache-only"
    expected = _FIRST_BY_CASE.get(job.case_id)
    if expected is not None:
        if job != expected:
            raise ValueError(f"first supplemental Stage B job descriptor drifted: {job.case_id}")
        return "first-cache-only"
    expected = _SECOND_BY_CASE.get(job.case_id)
    if expected is not None:
        if job != expected:
            raise ValueError(f"second supplemental Stage B job descriptor drifted: {job.case_id}")
        return "second-runnable"
    raise ValueError(f"Stage B job is outside the reviewed second supplement: {job.case_id}")


def _validate_reviewed_plan() -> None:
    _assert_trusted_predecessors()
    case_ids = [job.case_id for job in JOBS]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("all Stage B base and supplemental jobs must be unique")
    records = base._index()
    zmx_root = base.ZMX_DIR.resolve(strict=True)
    for job in SUPPLEMENTAL_JOBS:
        row = records.get(job.case_id)
        if not isinstance(row, dict) or row.get("case_id") != job.case_id:
            raise ValueError(f"second supplemental case is absent from the index: {job.case_id}")
        source_name = row.get("source_zmx")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError(f"second supplemental source is missing: {job.case_id}")
        source = (zmx_root / source_name).resolve(strict=True)
        if not source.is_file() or source.parent != zmx_root:
            raise ValueError(
                f"second supplemental source must be a direct ZMX_DIR file: {job.case_id}"
            )


def _add_runner_source(
    runner_sources: object, *, relative_path: str, path: Path
) -> dict[str, object]:
    if not isinstance(runner_sources, dict) or set(runner_sources) != {
        "files",
        "aggregate_sha256",
    }:
        raise ValueError("predecessor Stage B runner_sources has an unexpected schema")
    original_files = runner_sources.get("files")
    if not isinstance(original_files, dict):
        raise ValueError("predecessor Stage B runner_sources files are malformed")
    files = dict(original_files)
    if relative_path in files:
        raise ValueError(f"runner source unexpectedly collides: {relative_path}")
    files[relative_path] = _source_descriptor(path)
    return {
        "files": files,
        "aggregate_sha256": hashlib.sha256(base._canonical_bytes(files)).hexdigest(),
    }


def _current_identity(**kwargs: Any) -> dict[str, object]:
    _assert_trusted_predecessors()
    job = kwargs.get("job")
    if not isinstance(job, base.InputJob):
        raise TypeError("Stage B identity requires InputJob")
    family = _job_family(job)
    if family in {"base-cache-only", "first-cache-only"}:
        return _FIRST_CURRENT_IDENTITY(**kwargs)

    identity = _BASE_CURRENT_IDENTITY(**kwargs)
    first_bound = dict(identity)
    first_bound["runner_sources"] = first._wrapper_runner_sources(identity.get("runner_sources"))
    second_bound = dict(first_bound)
    second_bound["runner_sources"] = _add_runner_source(
        first_bound.get("runner_sources"),
        relative_path=_SECOND_RELATIVE_PATH,
        path=Path(__file__),
    )
    return second_bound


def _historical_cache_only(
    *,
    job: base.InputJob,
    meta: dict[str, object],
    output_dir: Path,
    executable: Path,
    recovery_p18_root: Path | None = None,
    lock_authority: Mapping[str, object] | None = None,
    lock_owner_ids: Mapping[str, object] | None = None,
    p18_terminal_authority: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return exactly one historical authority without creating filesystem state."""

    del recovery_p18_root
    if _job_family(job) not in {"base-cache-only", "first-cache-only"}:
        raise ValueError("historical cache lookup is restricted to the first 29 Stage B jobs")
    if lock_authority is None or lock_owner_ids is None or p18_terminal_authority is None:
        raise ValueError("Stage B cache lookup requires retained lock authority/owners")

    candidates: list[dict[str, object]] = []
    attempts_root = output_dir / "ladders" / job.case_id / "attempts"
    if attempts_root.exists() and not attempts_root.is_dir():
        raise RuntimeError(f"historical Stage B attempts root is damaged: {attempts_root}")
    if attempts_root.is_dir():
        entries = list(attempts_root.iterdir())
        unexpected = [path for path in entries if not path.is_dir()]
        if unexpected:
            raise RuntimeError(
                "historical Stage B attempts contain damaged entries: "
                + ", ".join(str(path) for path in sorted(unexpected))
            )
        incomplete = [path for path in entries if not (path / "ladder-result.json").is_file()]
        if incomplete:
            raise RuntimeError(
                "historical Stage B attempt is incomplete; refusing all writes/runs: "
                + ", ".join(str(path) for path in sorted(incomplete))
            )
        for path in entries:
            expected_identity = _current_identity(
                job=job,
                meta=meta,
                executable=executable,
                work_dir=path / "work",
                lock_authority=lock_authority,
            )
            try:
                intent = base._strict_json(path / "intent.json")
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"historical Stage B intent is damaged: {path}") from exc
            if intent.get("identity") != expected_identity:
                raise RuntimeError(f"historical Stage B identity drift: {path}")
            try:
                candidates.append(
                    base._validate_bound_attempt(
                        attempt_dir=path,
                        expected_identity=expected_identity,
                    )
                )
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"historical Stage B attempt is damaged: {path}") from exc

    retrospective_authority = dict(lock_authority)
    retrospective_authority["mode"] = "retrospective-observation"
    adoption_identity = _current_identity(
        job=job,
        meta=meta,
        executable=executable,
        work_dir=None,
        lock_authority=retrospective_authority,
    )
    adoption_path = output_dir / "adoptions-v1" / f"{job.case_id}.json"
    if adoption_path.exists() and not adoption_path.is_file():
        raise RuntimeError(f"historical Stage B adoption is damaged: {adoption_path}")
    try:
        adopted = base._validate_adoption(
            output_dir=output_dir,
            job=job,
            expected_identity=adoption_identity,
            expected_p18_terminal_authority=p18_terminal_authority,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(
            f"historical Stage B adoption is missing, drifted, or damaged: {job.case_id}"
        ) from exc
    if adopted is not None:
        candidates.append(adopted)

    if len(candidates) != 1:
        reason = "missing" if not candidates else "duplicate"
        raise RuntimeError(
            f"historical Stage B authority must have exactly one hit ({reason}): {job.case_id}"
        )
    return candidates[0]


def _run_job(**kwargs: Any) -> dict[str, object]:
    job = kwargs.get("job")
    if not isinstance(job, base.InputJob):
        raise TypeError("Stage B dispatch requires InputJob")
    if _job_family(job) in {"base-cache-only", "first-cache-only"}:
        return _historical_cache_only(**kwargs)
    return _ORIGINAL_RUN_JOB(**kwargs)


def _install_wrapper() -> None:
    _assert_trusted_predecessors()
    base.JOBS = JOBS
    base._current_identity = _current_identity
    base._run_job = _run_job


def main() -> int:
    forbidden = {
        "--adopt-legacy-cache",
        "--recover-incomplete-attempts",
        "--recover-stale-output-lock",
        "--recover-stale-p18-lock",
        "--recover-stale-codev-lock",
    }
    requested = sorted(forbidden.intersection(sys.argv[1:]))
    if requested:
        raise SystemExit(
            "second supplemental Stage B wrapper refuses adoption/recovery mode: "
            + ", ".join(requested)
        )
    _validate_reviewed_plan()
    _install_wrapper()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
