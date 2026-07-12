"""Read-only morning audit for a persisted Phase18 batch archive.

The exit code covers structural/provenance integrity only.  Optical metrics are
reported as observations and never converted into a pass/fail or [EXPERT]
verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.batch_archive import BatchJobRecord, BatchRecord  # noqa: E402
from app.core.orchestration import CandidateSet, TargetSpec  # noqa: E402

TERMINAL_JOB_STATUSES = {"succeeded", "degraded", "failed"}
_SURF_RE = re.compile(r"^\s*SURF\s+\d+\b", re.MULTILINE)
_WAVM_RE = re.compile(r"^\s*WAVM\s+\d+\b", re.MULTILINE)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _decode_zmx(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def inspect_zmx(path: Path) -> dict[str, Any]:
    """Return a cheap, non-optical structural check for a ZMX file."""

    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": None,
        "sha256": None,
        "surface_count": 0,
        "wavelength_count": 0,
        "valid": False,
        "reason": None,
    }
    if not path.is_file():
        result["reason"] = "missing"
        return result
    raw = path.read_bytes()
    result["size_bytes"] = len(raw)
    result["sha256"] = hashlib.sha256(raw).hexdigest()
    if not raw:
        result["reason"] = "empty"
        return result
    try:
        text = _decode_zmx(raw)
    except UnicodeError as exc:
        result["reason"] = f"decode-error: {exc}"
        return result
    result["surface_count"] = len(_SURF_RE.findall(text))
    result["wavelength_count"] = len(_WAVM_RE.findall(text))
    required = {
        "VERS": re.search(r"^\s*VERS\b", text, re.MULTILINE) is not None,
        "SURF 0": re.search(r"^\s*SURF\s+0\b", text, re.MULTILINE) is not None,
        ">=2 SURF": result["surface_count"] >= 2,
        ">=1 WAVM": result["wavelength_count"] >= 1,
    }
    missing = [name for name, present in required.items() if not present]
    if missing:
        result["reason"] = "missing token(s): " + ", ".join(missing)
        return result
    result["valid"] = True
    return result


def _normalize_aut(value: object) -> str:
    if value is True or value == "1" or value == "True":
        return "true"
    if value is False or value == "0" or value == "False":
        return "false"
    if value is None:
        return "missing"
    return f"other:{value}"


def finite_machine_number(value: object) -> tuple[float | None, str | None]:
    """Accept only finite JSON numbers; bool/string coercion would hide bad evidence."""

    if value is None:
        return None, "missing"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, f"malformed type={type(value).__name__} value={value!r}"
    number = float(value)
    if not math.isfinite(number):
        return None, f"malformed non-finite value={value!r}"
    return number, None


def accepted_final_path_issue(
    *, accepted_path: str, generated_path: str, artifact_dir: Path
) -> str | None:
    """Validate that accepted-final evidence binds to the delivered ZMX bytes."""

    accepted = Path(accepted_path).resolve()
    generated = Path(generated_path).resolve()
    if accepted != generated:
        return "accepted_final optimized_zmx_path differs from generated optimized_zmx_path"
    if not _is_within(accepted, artifact_dir):
        return "accepted_final optimized_zmx_path is outside current attempt"
    result = inspect_zmx(accepted)
    if not result["valid"]:
        return f"accepted_final optimized ZMX is invalid: {result['reason']}"
    return None


def _manifest_digest(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda item: item["relative_path"]):
        digest.update(
            f"{row['relative_path']}\0{row['size_bytes']}\0{row['sha256']}\n".encode()
        )
    return digest.hexdigest()


def audit_batch(
    *,
    archive_root: Path,
    artifact_root: Path,
    batch_id: str,
    expected_target_count: int,
    required_excluded_attempts: tuple[tuple[str, int], ...] = (),
    require_no_expert_verdicts: bool = False,
) -> dict[str, Any]:
    batch_dir = archive_root.resolve() / batch_id
    artifact_batch_dir = artifact_root.resolve() / batch_id
    errors: list[str] = []
    observations: list[str] = []
    source_hashes: dict[str, str] = {}
    manifest_rows: list[dict[str, Any]] = []

    def error(message: str) -> None:
        errors.append(message)

    batch_path = batch_dir / "batch.json"
    targets_path = batch_dir / "targets.json"
    try:
        batch = BatchRecord.model_validate(_read_json(batch_path))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"batch ledger is unreadable/invalid: {batch_path}: {exc}") from exc
    source_hashes["batch.json"] = _sha256(batch_path)
    try:
        targets_payload = _read_json(targets_path)
        targets = targets_payload["targets"]
        if not isinstance(targets, list):
            raise TypeError("targets must be a list")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"targets ledger is unreadable/invalid: {targets_path}: {exc}") from exc
    source_hashes["targets.json"] = _sha256(targets_path)

    if batch.batch_id != batch_id:
        error(f"batch_id mismatch: {batch.batch_id!r} != {batch_id!r}")
    if batch.status != "completed":
        error(f"batch status is {batch.status!r}, expected 'completed'")
    if batch.target_count != expected_target_count:
        error(
            f"batch target_count={batch.target_count}, externally expected "
            f"{expected_target_count}"
        )
    if batch.target_count != len(targets):
        error(f"target_count={batch.target_count}, targets.json has {len(targets)}")

    job_paths = sorted((batch_dir / "jobs").glob("*.json"))
    expected_ids = [f"job-{index:04d}" for index in range(batch.target_count)]
    actual_ids = [path.stem for path in job_paths]
    if actual_ids != expected_ids:
        error("job ledgers are not exactly continuous job-0000..job-{N-1}")

    job_statuses: Counter[str] = Counter()
    degraded_reasons: Counter[str] = Counter()
    candidate_modes: Counter[str] = Counter()
    aut_values: Counter[str] = Counter()
    terminations: Counter[str] = Counter()
    current_zmx_paths: set[Path] = set()
    referenced_zmx_paths: set[Path] = set()
    candidate_count = 0
    candidate_set_count = 0
    post_aut_count = 0
    fnum_ladder_count = 0
    fnum_target_achieved_count = 0
    fnum_accepted_final_count = 0
    quality_flags: list[dict[str, Any]] = []
    current_attempt_keys: set[tuple[str, int]] = set()

    for index, job_path in enumerate(job_paths):
        source_hashes[f"jobs/{job_path.name}"] = _sha256(job_path)
        try:
            job_raw = _read_json(job_path)
            job = BatchJobRecord.model_validate(job_raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            error(f"invalid job ledger {job_path.name}: {exc}")
            continue
        job_statuses[job.status] += 1
        if job.status not in TERMINAL_JOB_STATUSES:
            error(f"{job.job_id} is non-terminal: {job.status}")
        if job.status == "degraded":
            degraded_reasons[job.degradation or "<missing>"] += 1
        if job.batch_id != batch_id:
            error(f"{job.job_id} batch_id mismatch: {job.batch_id}")
        if job.engine != batch.engine:
            error(f"{job.job_id} engine={job.engine!r}, batch engine={batch.engine!r}")
        if job.job_id != job_path.stem or job.target_index != index:
            error(
                f"{job_path.name} identity/index mismatch: "
                f"job_id={job.job_id}, target_index={job.target_index}, expected={index}"
            )
        if index < len(targets) and job.target_spec != targets[index]:
            error(f"{job.job_id} target_spec differs from frozen targets.json")

        expected_artifact_dir = artifact_batch_dir / job.job_id / f"attempt-{job.attempt}"
        current_attempt_keys.add((job.job_id, job.attempt))
        if not job.artifact_dir:
            error(f"{job.job_id} has no artifact_dir")
            continue
        artifact_dir = Path(job.artifact_dir).resolve()
        if artifact_dir != expected_artifact_dir.resolve():
            error(
                f"{job.job_id} artifact_dir is not its current attempt directory: "
                f"{artifact_dir} != {expected_artifact_dir.resolve()}"
            )
        if not artifact_dir.is_dir() or not _is_within(artifact_dir, artifact_batch_dir):
            error(f"{job.job_id} artifact_dir missing or outside artifact root: {artifact_dir}")
            continue
        current_zmx_paths.update(path.resolve() for path in artifact_dir.rglob("*.zmx"))

        if not job.candidate_set_pointer:
            error(f"{job.job_id} has no candidate_set_pointer")
            continue
        candidate_path = Path(job.candidate_set_pointer).resolve()
        if candidate_path != (artifact_dir / "candidate_set.json").resolve():
            error(f"{job.job_id} candidate_set_pointer is not bound to current artifact_dir")
        if not candidate_path.is_file() or not _is_within(candidate_path, artifact_dir):
            error(f"{job.job_id} candidate_set missing or outside artifact_dir: {candidate_path}")
            continue
        try:
            candidate_raw = _read_json(candidate_path)
            candidate_set = CandidateSet.model_validate(candidate_raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            error(f"{job.job_id} CandidateSet invalid: {exc}")
            continue
        candidate_set_count += 1
        rel_candidate = candidate_path.relative_to(artifact_batch_dir).as_posix()
        candidate_sha = _sha256(candidate_path)
        manifest_rows.append(
            {
                "relative_path": rel_candidate,
                "size_bytes": candidate_path.stat().st_size,
                "sha256": candidate_sha,
            }
        )

        try:
            target = TargetSpec.model_validate(job.target_spec)
        except ValidationError as exc:
            error(f"{job.job_id} target_spec invalid: {exc}")
        else:
            if candidate_set.target != target:
                error(f"{job.job_id} CandidateSet target differs from job target")

        candidates = candidate_set.candidates
        candidate_count += len(candidates)
        raw_summary = candidate_raw.get("summary")
        ledger_summary = job.result_summary or {}
        if raw_summary != {
            key: ledger_summary.get(key)
            for key in (
                "candidate_count",
                "mode_counts",
                "ranked_count",
                "withheld_count",
                "ri_missing_count",
                "notes",
            )
        }:
            error(f"{job.job_id} CandidateSet summary differs from job result_summary")
        modes = Counter(candidate.generated.mode.value for candidate in candidates)
        candidate_modes.update(modes)
        if dict(modes) != ledger_summary.get("mode_counts"):
            error(f"{job.job_id} candidate modes differ from ledger mode_counts")
        if len(candidates) != ledger_summary.get("candidate_count"):
            error(f"{job.job_id} candidate_count differs from ledger")
        ranked_count = sum(candidate.scorecard.rank.status == "ranked" for candidate in candidates)
        withheld_count = len(candidates) - ranked_count
        ri_missing_count = sum(
            candidate.scorecard.image_quality.relative_illumination.status == "unavailable"
            for candidate in candidates
        )
        if candidate_set.summary.candidate_count != len(candidates):
            error(f"{job.job_id} CandidateSet summary candidate_count is not recomputed truth")
        if dict(candidate_set.summary.mode_counts) != dict(modes):
            error(f"{job.job_id} CandidateSet summary mode_counts is not recomputed truth")
        if candidate_set.summary.ranked_count != ranked_count:
            error(f"{job.job_id} CandidateSet summary ranked_count is not recomputed truth")
        if candidate_set.summary.withheld_count != withheld_count:
            error(f"{job.job_id} CandidateSet summary withheld_count is not recomputed truth")
        if candidate_set.summary.ri_missing_count != ri_missing_count:
            error(f"{job.job_id} CandidateSet summary ri_missing_count is not recomputed truth")
        requested_modes = ledger_summary.get("modes_requested")
        ledger_present = ledger_summary.get("modes_present")
        ledger_missing = ledger_summary.get("missing_modes")
        if not isinstance(requested_modes, list) or not all(
            isinstance(value, str) for value in requested_modes
        ):
            error(f"{job.job_id} modes_requested is missing or malformed")
        else:
            expected_present = sorted(modes)
            expected_missing = sorted(set(requested_modes) - set(modes))
            if sorted(ledger_present or []) != expected_present:
                error(f"{job.job_id} modes_present is not recomputed truth")
            if sorted(ledger_missing or []) != expected_missing:
                error(f"{job.job_id} missing_modes is not recomputed truth")
            if expected_missing and job.status not in {"degraded", "failed"}:
                error(f"{job.job_id} silently misses requested modes but status={job.status}")
            if not expected_missing and job.status == "degraded":
                error(f"{job.job_id} is degraded without a missing requested mode")
        ids = [candidate.generated.candidate_id for candidate in candidates]
        if len(ids) != len(set(ids)):
            error(f"{job.job_id} has duplicate candidate ids")

        for candidate in candidates:
            generated = candidate.generated
            scorecard = candidate.scorecard
            if generated.candidate_id != scorecard.candidate_id:
                error(f"{job.job_id} generated/scorecard candidate_id mismatch")
            if generated.mode != scorecard.mode:
                error(f"{job.job_id}/{generated.candidate_id} generated/scorecard mode mismatch")
            if generated.mode.value != "target-converged":
                continue
            optimized = Path(generated.optimized_zmx_path or "").resolve()
            repeats = [Path(path).resolve() for path in generated.repeat_run_artifact_paths]
            if not generated.optimized_zmx_path:
                error(f"{job.job_id}/{generated.candidate_id} lacks optimized_zmx_path")
            if not repeats:
                error(f"{job.job_id}/{generated.candidate_id} lacks repeat artifact path")
            if optimized not in repeats:
                error(f"{job.job_id}/{generated.candidate_id} optimized ZMX not in repeat paths")
            for zmx_path in {optimized, *repeats}:
                referenced_zmx_paths.add(zmx_path)
                if not _is_within(zmx_path, artifact_dir):
                    error(
                        f"{job.job_id}/{generated.candidate_id} references ZMX outside current attempt"
                    )

            extras_value = generated.optical_extras
            extras = (
                extras_value.model_dump(mode="json")
                if hasattr(extras_value, "model_dump")
                else (extras_value or {})
            )
            post_aut = extras.get("codev_post_aut")
            if not isinstance(post_aut, dict):
                error(f"{job.job_id}/{generated.candidate_id} lacks codev_post_aut snapshot")
                continue
            post_aut_count += 1
            aut = _normalize_aut(post_aut.get("aut_converged"))
            termination = post_aut.get("aut_termination") or "<missing>"
            rms_raw = post_aut.get("post_aut.max_rms_spot_diameter_um")
            efl_deviation_raw = post_aut.get("efl_target_deviation_pct")
            rms, rms_issue = finite_machine_number(rms_raw)
            efl_deviation, efl_issue = finite_machine_number(efl_deviation_raw)
            aut_values[aut] += 1
            terminations[str(termination)] += 1
            flags: list[str] = []
            if aut != "true":
                flags.append(f"aut_converged={aut}")
            if termination == "<missing>":
                flags.append("AUT termination missing")
            if rms_issue == "missing":
                flags.append("post-AUT RMS missing")
            elif rms_issue is not None:
                flags.append(f"post-AUT RMS {rms_issue}")
                error(
                    f"{job.job_id}/{generated.candidate_id} post-AUT RMS {rms_issue}"
                )
            elif rms is not None and rms < 0:
                flags.append(f"post-AUT RMS invalid-negative={rms} um")
                error(f"{job.job_id}/{generated.candidate_id} post-AUT RMS is negative")
            elif rms is not None and rms > 1e6:
                flags.append(f"post-AUT RMS extreme={rms} um")
            if efl_issue == "missing":
                flags.append("EFL deviation missing")
            elif efl_issue is not None:
                flags.append(f"EFL deviation {efl_issue}")
                error(
                    f"{job.job_id}/{generated.candidate_id} EFL deviation {efl_issue}"
                )
            elif efl_deviation is not None and abs(efl_deviation) > 10:
                flags.append(f"EFL deviation={efl_deviation}%")
            if flags:
                quality_flags.append(
                    {
                        "job_id": job.job_id,
                        "candidate_id": generated.candidate_id,
                        "flags": flags,
                    }
                )
            ladder = generated.fnum_ladder_evidence
            if ladder is not None:
                fnum_ladder_count += 1
                fnum_target_achieved_count += int(ladder.target_achieved)
                fnum_accepted_final_count += int(ladder.accepted_final is not None)
                if ladder.accepted_final is not None:
                    issue = accepted_final_path_issue(
                        accepted_path=ladder.accepted_final.optimized_zmx_path,
                        generated_path=generated.optimized_zmx_path or "",
                        artifact_dir=artifact_dir,
                    )
                    if issue:
                        error(f"{job.job_id}/{generated.candidate_id} {issue}")

    for path in sorted(current_zmx_paths | referenced_zmx_paths):
        result = inspect_zmx(path)
        if not result["valid"]:
            error(f"invalid referenced/current ZMX {path}: {result['reason']}")
            continue
        if _is_within(path, artifact_batch_dir):
            rel = path.relative_to(artifact_batch_dir).as_posix()
            manifest_rows.append(
                {
                    "relative_path": rel,
                    "size_bytes": result["size_bytes"],
                    "sha256": result["sha256"],
                }
            )

    incident_path = batch_dir / "resume-incident-20260712.json"
    receipt_path = batch_dir / "job-0020-retry-receipt-20260712.json"
    contaminated_path = batch_dir / "job-0020-attempt-1-contaminated-ledger.json"
    incident_checks: dict[str, Any] = {
        "resume_incident_present": incident_path.is_file(),
    }
    excluded_attempts: list[tuple[str, int]] = []
    if incident_path.is_file():
        source_hashes[incident_path.name] = _sha256(incident_path)
        incident = _read_json(incident_path)
        disposition_keys = sorted(incident.get("trust_disposition", {}).keys())
        incident_checks["trust_disposition_keys"] = disposition_keys
        for key in disposition_keys:
            match = re.fullmatch(r"(job-\d+)_attempt-(\d+)", key)
            if match is None:
                error(f"unparseable incident trust disposition key: {key}")
                continue
            excluded_attempts.append((match.group(1), int(match.group(2))))
        incident_checks["batch_id_matches"] = incident.get("batch_id") == batch_id
        if not incident_checks["batch_id_matches"]:
            error("resume incident batch_id does not match audited batch")
        if incident.get("incident") != "duplicate_resume_runner":
            error("resume incident type is not duplicate_resume_runner")

    required_excluded_set = set(required_excluded_attempts)
    if required_excluded_set:
        if not incident_path.is_file():
            error("required resume incident evidence is missing")
        if set(excluded_attempts) != required_excluded_set:
            error(
                "incident trust disposition does not exactly match required excluded attempts"
            )
        if incident_path.is_file():
            dispositions = incident.get("trust_disposition", {})
            for job_id, attempt in required_excluded_attempts:
                key = f"{job_id}_attempt-{attempt}"
                disposition = dispositions.get(key)
                if not isinstance(disposition, str) or "must not count" not in disposition:
                    error(f"{key} disposition does not explicitly say 'must not count'")
            incident_claims = {
                (
                    incident.get("retained_chain", {}).get("claimed_job"),
                    incident.get("retained_chain", {}).get("claimed_attempt"),
                ),
                (
                    incident.get("terminated_duplicate_chain", {}).get("claimed_job"),
                    incident.get("terminated_duplicate_chain", {}).get("claimed_attempt"),
                ),
            }
            if incident_claims != required_excluded_set:
                error("incident retained/terminated claimed attempts do not match exclusions")
            mitigation = incident.get("post_mitigation_observation", {})
            if mitigation.get("runner_chain_count") != 1 or mitigation.get(
                "codev_pair_count"
            ) != 1:
                error("incident post-mitigation observation is not single-runner/single-CODE-V")

    incident_checks["job0020_retry_receipt_present"] = receipt_path.is_file()
    incident_checks["job0020_contaminated_ledger_present"] = contaminated_path.is_file()
    if receipt_path.is_file() != contaminated_path.is_file():
        error("job-0020 retry receipt and contaminated ledger must be preserved together")
    if receipt_path.is_file() and contaminated_path.is_file():
        source_hashes[receipt_path.name] = _sha256(receipt_path)
        source_hashes[contaminated_path.name] = _sha256(contaminated_path)
        receipt = _read_json(receipt_path)
        preserved_hash = source_hashes[contaminated_path.name]
        incident_checks["job0020_preserved_hash_matches_receipt"] = (
            preserved_hash.lower()
            == str(receipt.get("preserved_ledger_sha256", "")).lower()
        )
        if not incident_checks["job0020_preserved_hash_matches_receipt"]:
            error("job-0020 contaminated ledger hash disagrees with retry receipt")
        receipt_expectations = {
            "batch_id": batch_id,
            "job_id": "job-0020",
            "preserved_ledger": contaminated_path.name,
            "attempt_1_artifacts_preserved": True,
            "original_job_ledger_removed_for_retry": True,
            "required_next_attempt": 2,
        }
        for key, expected in receipt_expectations.items():
            if receipt.get(key) != expected:
                error(f"job-0020 retry receipt {key}={receipt.get(key)!r}, expected {expected!r}")
        if "must never count" not in str(receipt.get("trust_rule", "")):
            error("job-0020 retry receipt trust_rule does not permanently exclude attempt-1")
        try:
            contaminated = BatchJobRecord.model_validate(_read_json(contaminated_path))
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            error(f"job-0020 contaminated ledger is invalid: {exc}")
        else:
            if contaminated.job_id != "job-0020" or contaminated.attempt != 1:
                error("job-0020 contaminated ledger identity/attempt mismatch")
    if ("job-0020", 1) in required_excluded_set and not (
        receipt_path.is_file() and contaminated_path.is_file()
    ):
        error("required job-0020 retry receipt/contaminated ledger evidence is missing")

    current_attempts: dict[str, int | None] = {}
    excluded_manifest_rows: list[dict[str, Any]] = []
    for job_id, excluded_attempt in excluded_attempts:
        path = batch_dir / "jobs" / f"{job_id}.json"
        attempt = _read_json(path).get("attempt") if path.is_file() else None
        current_attempts[job_id] = attempt
        expected_current_attempt = excluded_attempt + 1
        if attempt != expected_current_attempt:
            error(
                f"{job_id} current attempt is {attempt}, expected exact "
                f"attempt-{expected_current_attempt} after excluded attempt-{excluded_attempt}"
            )
        excluded_dir = artifact_batch_dir / job_id / f"attempt-{excluded_attempt}"
        key = f"{job_id}_attempt{excluded_attempt}_preserved"
        incident_checks[key] = excluded_dir.is_dir()
        if not excluded_dir.is_dir():
            error(f"{job_id} attempt-{excluded_attempt} evidence was not preserved")
            continue
        for artifact in sorted(path for path in excluded_dir.rglob("*") if path.is_file()):
            if artifact.suffix.lower() == ".zmx":
                zmx_result = inspect_zmx(artifact)
                if not zmx_result["valid"]:
                    error(f"excluded ZMX is corrupt: {artifact}: {zmx_result['reason']}")
            excluded_manifest_rows.append(
                {
                    "relative_path": artifact.relative_to(artifact_batch_dir).as_posix(),
                    "size_bytes": artifact.stat().st_size,
                    "sha256": _sha256(artifact),
                }
            )

    allowed_attempt_keys = current_attempt_keys | set(excluded_attempts)
    disk_attempt_keys: set[tuple[str, int]] = set()
    for job_dir in artifact_batch_dir.glob("job-*"):
        if not job_dir.is_dir():
            continue
        for attempt_dir in job_dir.glob("attempt-*"):
            if not attempt_dir.is_dir():
                continue
            match = re.fullmatch(r"attempt-(\d+)", attempt_dir.name)
            if match is None:
                error(f"unparseable artifact attempt directory: {attempt_dir}")
                continue
            disk_attempt_keys.add((job_dir.name, int(match.group(1))))
    unexpected_attempts = sorted(disk_attempt_keys - allowed_attempt_keys)
    if unexpected_attempts:
        error(f"unexpected/unclassified attempt directories: {unexpected_attempts}")

    verdict_dir = batch_dir / "verdicts"
    verdict_count = (
        len([path for path in verdict_dir.rglob("*") if path.is_file()])
        if verdict_dir.is_dir()
        else 0
    )
    if require_no_expert_verdicts and verdict_count:
        error(
            f"expected zero [EXPERT] verdict files for this acceptance audit, found {verdict_count}"
        )
    if verdict_count:
        observations.append(f"{verdict_count} [EXPERT] verdict file(s) recorded")
    else:
        observations.append("no [EXPERT] verdict files recorded; judgment remains blank")
    if current_zmx_paths - referenced_zmx_paths:
        observations.append(
            f"{len(current_zmx_paths - referenced_zmx_paths)} structurally valid current-attempt "
            "ZMX files are unpublished/unreferenced by the persisted CandidateSets"
        )
    observations.append(
        "terminal job status proves pipeline delivery only; it is not optical qualification"
    )

    report: dict[str, Any] = {
        "schema": "atelier-p18-morning-audit-v1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "batch_id": batch_id,
        "audit_scope": "structure-and-provenance-only",
        "acceptance_contract": {
            "expected_target_count": expected_target_count,
            "required_excluded_attempts": [
                f"{job_id}/attempt-{attempt}"
                for job_id, attempt in required_excluded_attempts
            ],
            "require_no_expert_verdicts": require_no_expert_verdicts,
        },
        "structural_status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "observations": observations,
        "source": {
            "archive_dir": str(batch_dir),
            "artifact_dir": str(artifact_batch_dir),
            "audit_script_sha256": _sha256(Path(__file__)),
            "sha256": source_hashes,
            "current_manifest_sha256": _manifest_digest(manifest_rows),
            "current_manifest_file_count": len(manifest_rows),
            "excluded_attempt_manifest_sha256": _manifest_digest(excluded_manifest_rows),
            "excluded_attempt_manifest_file_count": len(excluded_manifest_rows),
        },
        "counts": {
            "targets": len(targets),
            "jobs": len(job_paths),
            "candidate_sets_valid": candidate_set_count,
            "candidates": candidate_count,
            "job_statuses": dict(sorted(job_statuses.items())),
            "candidate_modes": dict(sorted(candidate_modes.items())),
            "degraded_reasons": dict(sorted(degraded_reasons.items())),
            "post_aut_snapshots": post_aut_count,
            "current_attempt_zmx": len(current_zmx_paths),
            "candidate_referenced_zmx": len(referenced_zmx_paths),
            "unpublished_current_attempt_zmx": len(
                current_zmx_paths - referenced_zmx_paths
            ),
            "expert_verdicts": verdict_count,
        },
        "incident_and_attempt_trust": {
            "current_attempts": current_attempts,
            **incident_checks,
            "permanently_excluded": [
                f"{job_id}/attempt-{attempt}" for job_id, attempt in excluded_attempts
            ],
        },
        "machine_quality_observations": {
            "aut_converged": dict(sorted(aut_values.items())),
            "aut_termination": dict(sorted(terminations.items())),
            "flagged_candidates": quality_flags,
            "fnum_ladder_candidates": fnum_ladder_count,
            "fnum_target_achieved": fnum_target_achieved_count,
            "fnum_accepted_final": fnum_accepted_final_count,
            "disclaimer": (
                "Machine measurements only. No pass/fail, yield, production-usability, "
                "or [EXPERT] verdict is inferred."
            ),
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    quality = report["machine_quality_observations"]
    trust = report["incident_and_attempt_trust"]
    lines = [
        "# Phase18 night-20260711 晨检",
        "",
        f"- 结构/溯源审计：**{report['structural_status']}**",
        f"- 生成时间（UTC）：`{report['generated_at']}`",
        "- 边界：本报告只证明流水线账本、指针、工件与机器数据的完整性；"
        "不判定光学合格、良品率、量产可用性，也不代填 `[EXPERT]`。",
        "",
        "## 账本与交付",
        "",
        "| 项目 | 结果 |",
        "|---|---:|",
        f"| targets（actual / expected） | {counts['targets']} / "
        f"{report['acceptance_contract']['expected_target_count']} |",
        f"| jobs / valid CandidateSets | {counts['jobs']} / "
        f"{counts['candidate_sets_valid']} |",
        f"| jobs succeeded / degraded / failed | "
        f"{counts['job_statuses'].get('succeeded', 0)} / "
        f"{counts['job_statuses'].get('degraded', 0)} / "
        f"{counts['job_statuses'].get('failed', 0)} |",
        f"| candidates retrieved / target-converged | "
        f"{counts['candidate_modes'].get('retrieved', 0)} / "
        f"{counts['candidate_modes'].get('target-converged', 0)} |",
        f"| current-attempt ZMX / CandidateSet 引用 / 未发布 | "
        f"{counts['current_attempt_zmx']} / {counts['candidate_referenced_zmx']} / "
        f"{counts['unpublished_current_attempt_zmx']} |",
        f"| post-AUT snapshots | {counts['post_aut_snapshots']} |",
        f"| `[EXPERT]` verdicts | {counts['expert_verdicts']}"
        f"{'（留白）' if counts['expert_verdicts'] == 0 else '（已有记录）'} |",
        "",
        f"全部 {counts['jobs']} 个 job id/index 连续、终态，job target 与冻结 targets 一致；"
        "current CandidateSet 均经当前 Pydantic 模型回读，summary/mode/count 自洽。"
        "全部 current-attempt 与引用 ZMX 通过非空、解码及 `VERS/WAVM/SURF` 结构检查。",
        "",
        "## 重跑事故信任边界",
        "",
    ]
    for excluded in trust["permanently_excluded"]:
        job_id = excluded.split("/", 1)[0]
        lines.append(
            f"- {excluded} 永久排除并保全；current=`attempt-"
            f"{trust['current_attempts'][job_id]}`。"
        )
    lines.extend(
        [
            "- `resume-incident-20260712.json` 的 trust disposition 为排除真值；"
            "job-0020 保全账本 SHA-256 与 retry receipt 一致。",
            "",
        "## 机器质量观察（非 verdict）",
        "",
        f"- AUT converged 分布：`{quality['aut_converged']}`。",
        f"- AUT termination 分布：`{quality['aut_termination']}`。",
        f"- F# ladder：{quality['fnum_ladder_candidates']} 个候选，"
        f"`target_achieved={quality['fnum_target_achieved']}`，"
        f"`accepted_final={quality['fnum_accepted_final']}`。",
        "- 下表只列缺测或显著异常机器数值；不把其余候选推断为合格。",
        "",
        "| job | candidate | observation |",
            "|---|---|---|",
        ]
    )
    for item in quality["flagged_candidates"]:
        lines.append(
            f"| {item['job_id']} | `{item['candidate_id']}` | "
            f"{'；'.join(item['flags'])} |"
        )
    if not quality["flagged_candidates"]:
        lines.append("| — | — | 无 |")
    lines.extend(
        [
            "",
            "## Degraded 分类",
            "",
            "| count | reason |",
            "|---:|---|",
        ]
    )
    for reason, count in counts["degraded_reasons"].items():
        lines.append(f"| {count} | {reason} |")
    lines.extend(
        [
            "",
            "## 证据绑定",
            "",
            f"- current manifest SHA-256：`{report['source']['current_manifest_sha256']}` "
            f"（{report['source']['current_manifest_file_count']} files）",
            f"- excluded-attempt manifest SHA-256："
            f"`{report['source']['excluded_attempt_manifest_sha256']}` "
            f"（{report['source']['excluded_attempt_manifest_file_count']} files）",
            f"- audit script SHA-256：`{report['source']['audit_script_sha256']}`",
        ]
    )
    for name, digest in report["source"]["sha256"].items():
        if name.startswith("jobs/"):
            continue
        lines.append(f"- `{name}`：`{digest}`")
    lines.append(
        f"- {counts['jobs']} 份 job ledger 的逐文件 SHA-256 收录于同名 JSON 报告"
        f"（expected={report['acceptance_contract']['expected_target_count']}）。"
    )
    if report["errors"]:
        lines.extend(["", "## 结构错误", ""])
        lines.extend(f"- {message}" for message in report["errors"])
    lines.extend(
        [
            "",
            "> `succeeded` 仅表示流水线交付；`degraded` 如实表示请求模式缺失。"
            "量产可用性与 `[EXPERT]` 背书仍由资深设计师决定。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--expected-target-count", type=int, required=True)
    parser.add_argument(
        "--required-excluded-attempt",
        action="append",
        default=[],
        metavar="JOB_ID:ATTEMPT",
    )
    parser.add_argument("--require-no-expert-verdicts", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    required_excluded_attempts: list[tuple[str, int]] = []
    for value in args.required_excluded_attempt:
        try:
            job_id, attempt_text = value.rsplit(":", 1)
            attempt = int(attempt_text)
        except (ValueError, TypeError) as exc:
            parser.error(f"invalid --required-excluded-attempt {value!r}: {exc}")
        if not re.fullmatch(r"job-\d+", job_id) or attempt < 1:
            parser.error(f"invalid --required-excluded-attempt {value!r}")
        required_excluded_attempts.append((job_id, attempt))
    report = audit_batch(
        archive_root=args.archive_root,
        artifact_root=args.artifact_root,
        batch_id=args.batch_id,
        expected_target_count=args.expected_target_count,
        required_excluded_attempts=tuple(required_excluded_attempts),
        require_no_expert_verdicts=args.require_no_expert_verdicts,
    )
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown_text = render_markdown(report)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json_text, encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown_text, encoding="utf-8")
    if not args.json_output and not args.markdown_output:
        print(json_text, end="")
    return 0 if report["structural_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
