"""Continue Stage B with a reviewed, evidence-ranked supplemental job set.

The original 21 jobs are immutable cache authority: this wrapper can only
read and validate an exact existing attempt or retrospective adoption for
them.  Only the eight explicitly reviewed supplemental jobs may delegate to
the production runner in :mod:`scripts.p16_stagec_stageb_inputs`.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import p16_stagec_stageb_inputs as base  # noqa: E402

_ORIGINAL_JOBS = tuple(base.JOBS)
_ORIGINAL_RUN_JOB = base._run_job
_ORIGINAL_CURRENT_IDENTITY = base._current_identity

_RATIONALE = "evidence-ranked supplemental exploration; no Stage B acceptance is presumed"
SUPPLEMENTAL_JOBS = (
    base.InputJob("US10330891B2", 2.4, _RATIONALE),
    base.InputJob("US20180143405A1", 2.4, _RATIONALE),
    base.InputJob("US20140111876A1", 2.4, _RATIONALE),
    base.InputJob("US-11906710-B2-e6", 2.35, _RATIONALE),
    base.InputJob("US-10101561-B2-e3", 2.2, _RATIONALE),
    base.InputJob("US-11668898-B2-e6", 2.4, _RATIONALE),
    base.InputJob("US-10921568-B2-e9", 2.2, _RATIONALE),
    base.InputJob("US-12174456-B2-e5", 2.4, _RATIONALE),
)
JOBS = (*_ORIGINAL_JOBS, *SUPPLEMENTAL_JOBS)

_ORIGINAL_BY_CASE = {job.case_id: job for job in _ORIGINAL_JOBS}
_SUPPLEMENTAL_BY_CASE = {job.case_id: job for job in SUPPLEMENTAL_JOBS}
_WRAPPER_RELATIVE_PATH = "scripts/p16_stagec_stageb_inputs_supplement.py"


def _require_exact_reviewed_job(job: base.InputJob) -> str:
    expected = _ORIGINAL_BY_CASE.get(job.case_id)
    if expected is not None:
        if job != expected:
            raise ValueError(f"original Stage B job descriptor drifted: {job.case_id}")
        return "original-cache-only"
    expected = _SUPPLEMENTAL_BY_CASE.get(job.case_id)
    if expected is not None:
        if job != expected:
            raise ValueError(f"supplemental Stage B job descriptor drifted: {job.case_id}")
        return "supplemental"
    raise ValueError(f"Stage B job is outside the reviewed wrapper plan: {job.case_id}")


def _validate_reviewed_plan() -> None:
    case_ids = [job.case_id for job in JOBS]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("original and supplemental Stage B jobs must be unique")
    records = base._index()
    zmx_root = base.ZMX_DIR.resolve(strict=True)
    for job in SUPPLEMENTAL_JOBS:
        row = records.get(job.case_id)
        if not isinstance(row, dict) or row.get("case_id") != job.case_id:
            raise ValueError(f"supplemental Stage B case is absent from the index: {job.case_id}")
        source_name = row.get("source_zmx")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError(f"supplemental Stage B source is missing: {job.case_id}")
        source = (zmx_root / source_name).resolve(strict=True)
        if not source.is_file() or source.parent != zmx_root:
            raise ValueError(
                f"supplemental Stage B source must be a direct ZMX_DIR file: {job.case_id}"
            )


def _wrapper_runner_sources(runner_sources: object) -> dict[str, object]:
    if not isinstance(runner_sources, dict) or set(runner_sources) != {
        "files",
        "aggregate_sha256",
    }:
        raise ValueError("base Stage B runner_sources has an unexpected schema")
    original_files = runner_sources.get("files")
    if not isinstance(original_files, dict):
        raise ValueError("base Stage B runner_sources files are malformed")
    files = dict(original_files)
    if _WRAPPER_RELATIVE_PATH in files:
        raise ValueError("supplement wrapper source unexpectedly collides with base identity")
    wrapper = Path(__file__).resolve(strict=True)
    raw = wrapper.read_bytes()
    files[_WRAPPER_RELATIVE_PATH] = {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": len(raw),
    }
    return {
        "files": files,
        "aggregate_sha256": hashlib.sha256(base._canonical_bytes(files)).hexdigest(),
    }


def _current_identity(**kwargs: Any) -> dict[str, object]:
    job = kwargs.get("job")
    if not isinstance(job, base.InputJob):
        raise TypeError("Stage B identity requires InputJob")
    kind = _require_exact_reviewed_job(job)
    identity = _ORIGINAL_CURRENT_IDENTITY(**kwargs)
    if kind == "original-cache-only":
        return identity
    enriched = dict(identity)
    enriched["runner_sources"] = _wrapper_runner_sources(identity.get("runner_sources"))
    return enriched


def _original_cache_only(
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
    """Return one exact old cache authority without creating any filesystem state."""

    if _require_exact_reviewed_job(job) != "original-cache-only":
        raise ValueError("cache-only lookup is restricted to the original Stage B jobs")
    if lock_authority is None or lock_owner_ids is None or p18_terminal_authority is None:
        raise ValueError("Stage B cache lookup requires retained lock authority/owners")

    candidates: list[dict[str, object]] = []
    attempts_root = output_dir / "ladders" / job.case_id / "attempts"
    if attempts_root.exists() and not attempts_root.is_dir():
        raise RuntimeError(f"original cache-only Stage B attempts root is damaged: {attempts_root}")
    if attempts_root.is_dir():
        entries = list(attempts_root.iterdir())
        unexpected = [path for path in entries if not path.is_dir()]
        if unexpected:
            raise RuntimeError(
                "original cache-only Stage B attempts contain damaged entries: "
                + ", ".join(str(path) for path in sorted(unexpected))
            )
        attempt_dirs = entries
        incomplete = [path for path in attempt_dirs if not (path / "ladder-result.json").is_file()]
        if incomplete:
            raise RuntimeError(
                "original cache-only Stage B attempt is incomplete; refusing all writes/runs: "
                + ", ".join(str(path) for path in sorted(incomplete))
            )
        for path in attempt_dirs:
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
                raise RuntimeError(
                    f"original cache-only Stage B intent is damaged: {path}"
                ) from exc
            if intent.get("identity") != expected_identity:
                raise RuntimeError(f"original cache-only Stage B identity drift: {path}")
            try:
                candidates.append(
                    base._validate_bound_attempt(
                        attempt_dir=path,
                        expected_identity=expected_identity,
                    )
                )
            except (OSError, ValueError) as exc:
                raise RuntimeError(
                    f"original cache-only Stage B attempt is damaged: {path}"
                ) from exc

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
        raise RuntimeError(
            f"original cache-only Stage B adoption record is damaged: {adoption_path}"
        )
    try:
        adopted = base._validate_adoption(
            output_dir=output_dir,
            job=job,
            expected_identity=adoption_identity,
            expected_p18_terminal_authority=p18_terminal_authority,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        raise RuntimeError(
            f"original cache-only Stage B adoption is missing, drifted, or damaged: {job.case_id}"
        ) from exc
    if adopted is not None:
        candidates.append(adopted)

    if len(candidates) != 1:
        reason = "missing" if not candidates else "duplicate"
        raise RuntimeError(
            f"original cache-only Stage B authority must have exactly one hit ({reason}): "
            f"{job.case_id}"
        )
    return candidates[0]


def _run_job(**kwargs: Any) -> dict[str, object]:
    job = kwargs.get("job")
    if not isinstance(job, base.InputJob):
        raise TypeError("Stage B run dispatch requires InputJob")
    kind = _require_exact_reviewed_job(job)
    if kind == "original-cache-only":
        return _original_cache_only(**kwargs)
    return _ORIGINAL_RUN_JOB(**kwargs)


def _install_wrapper() -> None:
    base.JOBS = JOBS
    base._current_identity = _current_identity
    base._run_job = _run_job


def main() -> int:
    for forbidden_mode in ("--adopt-legacy-cache", "--recover-incomplete-attempts"):
        if forbidden_mode in sys.argv[1:]:
            raise SystemExit(
                f"supplemental Stage B wrapper refuses {forbidden_mode}; "
                "the original 21 jobs are cache-only"
            )
    _validate_reviewed_plan()
    _install_wrapper()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
