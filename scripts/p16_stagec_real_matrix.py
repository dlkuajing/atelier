"""Run and audit the Stage C 8-seed × 3-arm × 2-repeat real-machine matrix.

The command is resume-safe at the receipt level: a completed run is reused only
after the public v3 restore path revalidates its HMAC, Stage B authority bytes,
raw artifacts, canonical sequence, and matrix identity.  It never manufactures
an optical or ``[EXPERT]`` verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.batch_run_lock import (  # noqa: E402
    P18_GLOBAL_WINDOW_ROOT,
    batch_runner_lock,
)
from app.core.engines.stageb_authority import (  # noqa: E402
    STAGEB_MANIFEST_SCHEMA,
    no_pre_run_raw_bytes,
    validate_retained_stageb_authority,
)
from app.core.engines.stagec_attested import (  # noqa: E402
    StageCAttestedEvidence,
    _publish_stagec_inflight,
    restore_stagec_attested_evidence,
    run_stagec_attested,
    trusted_stagec_run_root,
)
from app.core.engines.stagec_field import (  # noqa: E402
    reconstruct_image_fields,
    resolve_field_target,
)
from app.core.lens_system import Scenario  # noqa: E402
from app.core.parameter_guards import SCENARIO_BOUNDS  # noqa: E402

PLAN_SCHEMA = "atelier-stagec-real-matrix-plan-v1"
STATE_SCHEMA = "atelier-stagec-real-matrix-state-v1"
REPORT_SCHEMA = "atelier-stagec-real-matrix-report-v1"
ARMS = ("native-imh-reconstructed-control", "target-low", "target-high")


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            move_file = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
            move_file.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
            move_file.restype = wintypes.BOOL
            if not move_file(str(temporary), str(path), 0x00000001 | 0x00000008):
                raise OSError(ctypes.get_last_error(), f"durable replace failed: {path}")
        else:
            os.replace(temporary, path)
            descriptor = os.open(path.parent.resolve(strict=True), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _matrix_id() -> str:
    return f"stagec-matrix-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_cells(
    *, stageb_manifest: Path, reconstruction_root: Path, published_root: Path
) -> list[dict[str, object]]:
    """Re-derive the closed 8x3 matrix from byte-bound Stage B inputs."""

    manifest = _json(stageb_manifest)
    entries = manifest.get("accepted")
    if (
        manifest.get("schema_id") != STAGEB_MANIFEST_SCHEMA
        or manifest.get("complete") is not True
        or manifest.get("accepted_count") != (len(entries) if isinstance(entries, list) else -1)
        or not isinstance(entries, list)
        or len(entries) != 8
    ):
        raise ValueError("Stage B manifest lacks eight accepted inputs")
    selected = entries[:8]
    case_ids = [entry.get("case_id") for entry in selected if isinstance(entry, dict)]
    if len(case_ids) != 8 or len(set(case_ids)) != 8:
        raise ValueError("Stage B matrix inputs are not eight unique case IDs")

    cells: list[dict[str, object]] = []
    for entry in selected:
        assert isinstance(entry, dict)
        case_id = str(entry["case_id"])
        accepted_path = Path(str(entry["accepted_zmx"])).resolve(strict=True)
        source_path = Path(str(entry["source_zmx"])).resolve(strict=True)
        ladder_path = Path(str(entry["ladder_result"])).resolve(strict=True)
        cache_record_path = Path(str(entry["cache_record_path"])).resolve(strict=True)
        raw_path_value = entry.get("raw_ladder_result_path")
        raw_ladder_raw = (
            no_pre_run_raw_bytes()
            if raw_path_value is None
            else Path(str(raw_path_value)).resolve(strict=True).read_bytes()
        )
        if _sha(accepted_path) != entry.get("accepted_zmx_sha256"):
            raise ValueError(f"{case_id} accepted Stage B ZMX bytes changed")
        if _sha(source_path) != entry.get("source_zmx_sha256"):
            raise ValueError(f"{case_id} original source ZMX bytes changed")
        cache_binding = validate_retained_stageb_authority(
            manifest_raw=stageb_manifest.read_bytes(),
            ladder_raw=ladder_path.read_bytes(),
            raw_ladder_raw=raw_ladder_raw,
            accepted_zmx_raw=accepted_path.read_bytes(),
            cache_record_raw=cache_record_path.read_bytes(),
            case_id=case_id,
            verify_external_paths=True,
        )
        scenario = Scenario(str(entry["scenario"]))
        bounds = SCENARIO_BOUNDS[scenario]
        efl = float(entry["target_efl_mm"])
        native = float(entry["native_image_height_mm"])
        lower = max(
            bounds.image_height_mm_min,
            efl * math.tan(math.radians(bounds.fov_deg_min / 2)),
        )
        upper = min(
            bounds.image_height_mm_max,
            efl * math.tan(math.radians(bounds.fov_deg_max / 2)),
        )
        if not lower < native < upper:
            raise ValueError(f"{case_id} native image height has no bidirectional in-bounds room")
        targets = {
            "native-imh-reconstructed-control": native,
            "target-low": (lower + native) / 2,
            "target-high": (native + upper) / 2,
        }
        for arm, target_imh in targets.items():
            cell_id = f"{case_id}--{arm}"
            work_path = reconstruction_root / "cells" / cell_id / "reconstructed.zmx"
            work_path.parent.mkdir(parents=True, exist_ok=False)
            resolved = resolve_field_target(
                efl_mm=efl, image_height_mm=target_imh, full_fov_deg=None
            )
            reconstruction = reconstruct_image_fields(
                source_zmx=accepted_path,
                output_zmx=work_path,
                resolved_target=resolved,
                allow_nonzero_vignetting_for_machine=True,
            )
            if reconstruction.status != "constructed":
                raise ValueError(f"{cell_id} reconstruction did not produce a machine input")
            reconstruction_payload = reconstruction.model_dump(mode="json")
            reconstruction_payload["output_path"] = str(
                (published_root / "cells" / cell_id / "reconstructed.zmx").resolve()
            )
            cells.append(
                {
                    "cell_id": cell_id,
                    "case_id": case_id,
                    "arm": arm,
                    "target_image_height_mm": target_imh,
                    "target_efl_mm": efl,
                    "accepted_zmx_sha256": entry["accepted_zmx_sha256"],
                    "source_zmx_sha256": entry["source_zmx_sha256"],
                    "cache_scope": cache_binding.scope,
                    "pre_run_bound": cache_binding.pre_run_bound,
                    "cache_record_path": cache_binding.record_path,
                    "cache_record_sha256": cache_binding.record_sha256,
                    "raw_ladder_result_path": cache_binding.raw_result_path,
                    "raw_ladder_result_sha256": cache_binding.raw_result_sha256,
                    "reconstruction": reconstruction_payload,
                }
            )
    return cells


def validate_or_rederive_plan(
    *, plan: dict[str, object], stageb_manifest: Path, output_dir: Path
) -> None:
    """Prove an existing plan still equals the current canonical derivation."""

    if (
        plan.get("schema_id") != PLAN_SCHEMA
        or plan.get("stageb_manifest") != str(stageb_manifest.resolve())
        or plan.get("stageb_manifest_sha256") != _sha(stageb_manifest)
        or plan.get("seed_count") != 8
        or plan.get("cell_count") != 24
        or plan.get("repeat_count") != 2
        or plan.get("expected_run_count") != 48
        or not isinstance(plan.get("matrix_id"), str)
    ):
        raise ValueError("existing matrix plan identity differs from canonical matrix")
    with tempfile.TemporaryDirectory(prefix="atelier-stagec-plan-validate-") as raw:
        canonical = _canonical_cells(
            stageb_manifest=stageb_manifest,
            reconstruction_root=Path(raw),
            published_root=output_dir,
        )
    if plan.get("cells") != canonical:
        raise ValueError("existing matrix plan cells differ from canonical Stage B derivation")
    seed_cells = {str(cell["case_id"]): cell for cell in canonical if isinstance(cell, dict)}
    expected_scope_counts = {
        scope: sum(cell["cache_scope"] == scope for cell in seed_cells.values())
        for scope in sorted({str(cell["cache_scope"]) for cell in seed_cells.values()})
    }
    expected_retrospective = sorted(
        case_id
        for case_id, cell in seed_cells.items()
        if cell["cache_scope"] == "retrospective-current-state-adoption"
    )
    if (
        plan.get("stageb_cache_scope_counts") != expected_scope_counts
        or plan.get("all_inputs_pre_run_bound")
        is not all(bool(cell["pre_run_bound"]) for cell in seed_cells.values())
        or plan.get("retrospective_seed_ids") != expected_retrospective
    ):
        raise ValueError("existing matrix plan cache summary differs from canonical seeds")


def build_plan(
    *, stageb_manifest: Path, output_dir: Path, seed_count: int = 8
) -> dict[str, object]:
    if seed_count != 8:
        raise ValueError("Stage C real matrix requires exactly eight unique seeds")
    plan_path = output_dir / "matrix-plan.json"
    if plan_path.is_file():
        plan = _json(plan_path)
        validate_or_rederive_plan(plan=plan, stageb_manifest=stageb_manifest, output_dir=output_dir)
        return plan

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        orphan = output_dir.with_name(
            f"{output_dir.name}.orphan-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid4().hex}"
        )
        os.replace(output_dir, orphan)
    temporary = output_dir.with_name(f"{output_dir.name}.building-{uuid4().hex}")
    temporary.mkdir(parents=False, exist_ok=False)
    matrix_id = _matrix_id()
    try:
        cells = _canonical_cells(
            stageb_manifest=stageb_manifest,
            reconstruction_root=temporary,
            published_root=output_dir,
        )
        seed_cells = {str(cell["case_id"]): cell for cell in cells if isinstance(cell, dict)}
        scope_counts = {
            scope: sum(cell["cache_scope"] == scope for cell in seed_cells.values())
            for scope in sorted({str(cell["cache_scope"]) for cell in seed_cells.values()})
        }
        plan = {
            "schema_id": PLAN_SCHEMA,
            "matrix_id": matrix_id,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "stageb_manifest": str(stageb_manifest.resolve()),
            "stageb_manifest_sha256": _sha(stageb_manifest),
            "seed_count": 8,
            "cell_count": 24,
            "repeat_count": 2,
            "expected_run_count": 48,
            "stageb_cache_scope_counts": scope_counts,
            "all_inputs_pre_run_bound": all(
                bool(cell["pre_run_bound"]) for cell in seed_cells.values()
            ),
            "retrospective_seed_ids": sorted(
                case_id
                for case_id, cell in seed_cells.items()
                if cell["cache_scope"] == "retrospective-current-state-adoption"
            ),
            "cells": cells,
            "expert_verdict": None,
        }
        _atomic_json(temporary / "matrix-plan.json", plan)
        validate_or_rederive_plan(plan=plan, stageb_manifest=stageb_manifest, output_dir=output_dir)
        os.replace(temporary, output_dir)
        return plan
    except Exception:
        # The building directory is retained as evidence of the failed construction.
        failed = temporary.with_name(f"{temporary.name}.failed")
        if temporary.exists():
            os.replace(temporary, failed)
        raise


def _load_state(output_dir: Path, matrix_id: str) -> dict[str, object]:
    path = output_dir / "matrix-state.json"
    if not path.is_file():
        return {
            "schema_id": STATE_SCHEMA,
            "matrix_id": matrix_id,
            "runs": [],
            "attempts": [],
        }
    state = _json(path)
    if state.get("schema_id") != STATE_SCHEMA or state.get("matrix_id") != matrix_id:
        raise ValueError("matrix state identity mismatch")
    if not isinstance(state.get("runs"), list):
        raise ValueError("matrix state runs must be a list")
    if not isinstance(state.get("attempts"), list):
        raise ValueError("matrix state attempts must be a list")
    return state


def _cell_map(plan: dict[str, object]) -> dict[tuple[str, int], dict[str, object]]:
    cells = plan.get("cells")
    if not isinstance(cells, list) or len(cells) != 24:
        raise ValueError("matrix plan must contain exactly 24 cells")
    result: dict[tuple[str, int], dict[str, object]] = {}
    for cell in cells:
        if (
            not isinstance(cell, dict)
            or cell.get("arm") not in ARMS
            or not isinstance(cell.get("cell_id"), str)
            or cell.get("cell_id") != f"{cell.get('case_id')}--{cell.get('arm')}"
            or not isinstance(cell.get("reconstruction"), dict)
            or cell.get("cache_scope")
            not in {"pre-run-bound", "retrospective-current-state-adoption"}
            or not isinstance(cell.get("pre_run_bound"), bool)
            or cell.get("pre_run_bound") is not (cell.get("cache_scope") == "pre-run-bound")
            or not isinstance(cell.get("cache_record_path"), str)
            or str(Path(str(cell.get("cache_record_path"))).resolve())
            != cell.get("cache_record_path")
            or not isinstance(cell.get("cache_record_sha256"), str)
            or len(str(cell.get("cache_record_sha256"))) != 64
            or any(
                character not in "0123456789abcdef"
                for character in str(cell.get("cache_record_sha256"))
            )
        ):
            raise ValueError("matrix plan contains malformed cell identity")
        for repeat in (1, 2):
            key = (str(cell["cell_id"]), repeat)
            if key in result:
                raise ValueError("matrix plan contains duplicate cell identity")
            result[key] = cell
    if len(result) != 48:
        raise ValueError("matrix plan does not define exactly 48 run identities")
    return result


def _validate_evidence_identity(
    evidence: StageCAttestedEvidence,
    *,
    cell: dict[str, object],
    repeat: int,
    matrix_id: str,
    plan_sha256: str,
    expected_run_id: str | None = None,
) -> None:
    reconstruction = cell.get("reconstruction")
    if not isinstance(reconstruction, dict):
        raise ValueError("matrix cell reconstruction is malformed")
    if (
        evidence.matrix_id != matrix_id
        or evidence.cell_id != cell["cell_id"]
        or evidence.seed_id != cell["case_id"]
        or evidence.arm != cell["arm"]
        or evidence.repeat_index != repeat
        or evidence.execution_plan_sha256 != plan_sha256
        or evidence.target_efl_mm != cell["target_efl_mm"]
        or evidence.target_image_height_mm != cell["target_image_height_mm"]
        or evidence.reconstructed_zmx_sha256 != reconstruction.get("output_sha256")
        or evidence.source_zmx_sha256 != cell.get("accepted_zmx_sha256")
        or evidence.stageb_cache_scope != cell.get("cache_scope")
        or evidence.stageb_pre_run_bound is not cell.get("pre_run_bound")
        or evidence.stageb_cache_record_sha256 != cell.get("cache_record_sha256")
        or (expected_run_id is not None and evidence.run_id != expected_run_id)
    ):
        raise ValueError("restored receipt differs from canonical matrix identity")


def _run_row(evidence: StageCAttestedEvidence, receipt: Path) -> dict[str, object]:
    return {
        "cell_id": evidence.cell_id,
        "case_id": evidence.seed_id,
        "arm": evidence.arm,
        "repeat_index": evidence.repeat_index,
        "run_id": evidence.run_id,
        "receipt": str(receipt),
        "receipt_sha256": evidence.receipt_sha256,
        "stageb_cache_scope": evidence.stageb_cache_scope,
        "stageb_pre_run_bound": evidence.stageb_pre_run_bound,
        "stageb_cache_record_sha256": evidence.stageb_cache_record_sha256,
        "attested_duration_seconds": evidence.process_duration_seconds,
    }


def _valid_spot_values(evidence: StageCAttestedEvidence) -> list[float] | None:
    values: list[float] = []
    for field in evidence.fields:
        value = field.rms_spot_diameter_um
        if field.spotdata_return_code != 0 or not math.isfinite(value) or value <= 0:
            return None
        values.append(value)
    return values or None


def _valid_wfe_values(evidence: StageCAttestedEvidence) -> list[float] | None:
    values: list[float] = []
    for field in evidence.fields:
        value = field.rms_wfe_waves
        if (
            not math.isfinite(field.rmswe_return_value)
            or field.rmswe_return_value <= 0
            or not math.isfinite(value)
            or value <= 0
        ):
            return None
        values.append(value)
    return values or None


def _metric_summary(
    repeats: list[StageCAttestedEvidence],
    *,
    values_for: Callable[[StageCAttestedEvidence], list[float] | None],
) -> dict[str, object]:
    valid_samples: list[float] = []
    valid_run_ids: list[str] = []
    unavailable_run_ids: list[str] = []
    for evidence in repeats:
        values = values_for(evidence)
        if values is None:
            unavailable_run_ids.append(evidence.run_id)
            continue
        valid_samples.append(max(values))
        valid_run_ids.append(evidence.run_id)
    valid_count = len(valid_samples)
    expected_count = len(repeats)
    availability = (
        "complete" if valid_count == expected_count else "partial" if valid_count else "unavailable"
    )
    return {
        "samples": valid_samples,
        "valid_run_ids": valid_run_ids,
        "unavailable_run_ids": unavailable_run_ids,
        "valid_receipt_count": valid_count,
        "availability": availability,
        "spread": max(valid_samples) - min(valid_samples) if valid_count >= 2 else None,
        "mean": sum(valid_samples) / valid_count if valid_count else None,
    }


def _validate_attempt_rows(
    attempts: object, *, identities: dict[tuple[str, int], dict[str, object]]
) -> list[dict[str, object]]:
    if not isinstance(attempts, list):
        raise ValueError("matrix state attempts must be a list")
    validated: list[dict[str, object]] = []
    run_ids: set[str] = set()
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("matrix state attempt is malformed")
        key = (attempt.get("cell_id"), attempt.get("repeat_index"))
        cell = identities.get(key)  # type: ignore[arg-type]
        run_id = attempt.get("run_id")
        duration = attempt.get("duration_seconds")
        if (
            cell is None
            or attempt.get("case_id") != cell.get("case_id")
            or attempt.get("arm") != cell.get("arm")
            or attempt.get("stageb_cache_scope") != cell.get("cache_scope")
            or attempt.get("stageb_pre_run_bound") is not cell.get("pre_run_bound")
            or attempt.get("stageb_cache_record_sha256") != cell.get("cache_record_sha256")
            or attempt.get("status") not in {"started", "failed", "incomplete", "attested"}
            or not isinstance(run_id, str)
            or run_id in run_ids
            or (
                duration is not None
                and (
                    not isinstance(duration, (int, float))
                    or isinstance(duration, bool)
                    or not math.isfinite(float(duration))
                    or float(duration) < 0
                )
            )
        ):
            raise ValueError("matrix state attempt identity or duration is malformed")
        run_ids.add(run_id)
        validated.append(attempt)
    return validated


def _recover_started_attempts(
    *, plan: dict[str, object], state: dict[str, object], output_dir: Path
) -> bool:
    """Reconcile interrupted durable packages before any cell can be retried."""

    matrix_id = str(plan["matrix_id"])
    plan_sha = _sha(output_dir / "matrix-plan.json")
    cell_map = _cell_map(plan)
    runs = state.get("runs")
    attempts = state.get("attempts")
    if not isinstance(runs, list):
        raise ValueError("matrix state rows are malformed")
    attempts = _validate_attempt_rows(attempts, identities=cell_map)
    changed = False
    recovery_blocked = False
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise ValueError("matrix state attempt is malformed")
        attempt_status = attempt.get("status")
        if attempt_status not in {"started", "failed", "incomplete"}:
            continue
        key = (attempt.get("cell_id"), attempt.get("repeat_index"))
        cell = cell_map.get(key)  # type: ignore[arg-type]
        run_id = attempt.get("run_id")
        if cell is None or not isinstance(run_id, str):
            raise ValueError("started attempt identity is outside the canonical plan")
        root = trusted_stagec_run_root()
        inflight = root / f"{run_id}.inflight"
        final = root / run_id
        final_receipt = final / "post-run-receipt.json"
        inflight_receipt = inflight / "post-run-receipt.json"
        quarantines = sorted(root.glob(f"{run_id}.quarantine-*"))
        package_paths = [
            str(path)
            for path in (
                inflight,
                final,
                *quarantines,
            )
            if path.exists()
        ]
        if attempt_status == "failed" and not package_paths:
            # A process failure that produced no durable package remains an explicit failed
            # attempt and may be retried.  Any surviving package must first be reconciled.
            continue
        if attempt_status == "incomplete" and not package_paths:
            recovery_blocked = True
            continue
        evidence: StageCAttestedEvidence | None = None
        recovered_receipt: Path | None = None
        recovery_error: dict[str, str] | None = None
        if quarantines or (inflight.exists() and final.exists()):
            recovery_error = {
                "type": "RecoveryPackageConflict",
                "message": (
                    "final/inflight/quarantine packages conflict for one run identity; "
                    "automatic publication and rerun are refused"
                ),
            }
        elif final.exists():
            if not final.is_dir() or not final_receipt.is_file():
                recovery_error = {
                    "type": "IncompleteFinalPackage",
                    "message": "final package lacks its receipt-last artifact; rerun is refused",
                }
            else:
                try:
                    evidence = restore_stagec_attested_evidence(final_receipt)
                    recovered_receipt = final_receipt
                except Exception as exc:
                    recovery_error = {
                        "type": "FinalPackageValidationError",
                        "message": f"{type(exc).__name__}: {exc}",
                    }
        elif inflight.exists():
            if not inflight.is_dir() or not inflight_receipt.is_file():
                recovery_error = {
                    "type": "InterruptedAttempt",
                    "message": (
                        "inflight package lacks its receipt-last artifact; automatic rerun is "
                        "refused"
                    ),
                }
            else:
                try:
                    recovered_receipt = _publish_stagec_inflight(
                        inflight=inflight,
                        final=final,
                    )
                    # The safe publisher validates both sides of the atomic rename.  Restore
                    # once more through the public boundary before matrix state trusts it.
                    evidence = restore_stagec_attested_evidence(recovered_receipt)
                except Exception as exc:
                    package_paths = [
                        str(path)
                        for path in (
                            inflight,
                            final,
                            *sorted(root.glob(f"{run_id}.quarantine-*")),
                        )
                        if path.exists()
                    ]
                    recovery_error = {
                        "type": "InflightPublicationError",
                        "message": f"{type(exc).__name__}: {exc}",
                    }
        else:
            recovery_error = {
                "type": "InterruptedAttempt",
                "message": "no durable Stage C package exists; automatic rerun is refused",
            }
        if evidence is not None and recovered_receipt is not None:
            try:
                _validate_evidence_identity(
                    evidence,
                    cell=cell,
                    repeat=int(attempt["repeat_index"]),
                    matrix_id=matrix_id,
                    plan_sha256=plan_sha,
                    expected_run_id=run_id,
                )
                matching = [
                    row
                    for row in runs
                    if isinstance(row, dict)
                    and (row.get("cell_id"), row.get("repeat_index")) == key
                ]
                if matching and (
                    len(matching) != 1 or matching[0].get("run_id") != evidence.run_id
                ):
                    raise ValueError("recovered receipt collides with matrix state run identity")
            except Exception as exc:
                evidence = None
                recovered_receipt = None
                package_paths = [
                    str(path)
                    for path in (
                        inflight,
                        final,
                        *sorted(root.glob(f"{run_id}.quarantine-*")),
                    )
                    if path.exists()
                ]
                recovery_error = {
                    "type": "RecoveredEvidenceIdentityError",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            else:
                if not matching:
                    runs.append(_run_row(evidence, recovered_receipt))
        if evidence is not None and recovered_receipt is not None:
            attempt.update(
                {
                    "status": "attested",
                    "ended_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "receipt": str(recovered_receipt),
                    "package_paths": [str(recovered_receipt.parent)],
                    "duration_seconds": evidence.process_duration_seconds,
                    "recovered_after_crash": True,
                    "error": None,
                }
            )
        else:
            assert recovery_error is not None
            attempt.update(
                {
                    "status": "incomplete",
                    "ended_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "receipt": None,
                    "package_paths": package_paths,
                    "duration_seconds": None,
                    "error": recovery_error,
                }
            )
            recovery_blocked = True
        changed = True
    if changed:
        _atomic_json(output_dir / "matrix-state.json", state)
    return recovery_blocked


def execute_plan(*, plan: dict[str, object], output_dir: Path) -> dict[str, object]:
    matrix_id = str(plan["matrix_id"])
    state = _load_state(output_dir, matrix_id)
    recovery_blocked = _recover_started_attempts(plan=plan, state=state, output_dir=output_dir)
    runs = state["runs"]
    attempts = state["attempts"]
    assert isinstance(runs, list)
    assert isinstance(attempts, list)
    if recovery_blocked or any(
        isinstance(attempt, dict) and attempt.get("status") in {"started", "incomplete"}
        for attempt in attempts
    ):
        raise RuntimeError(
            "matrix recovery found incomplete or conflicting durable evidence; "
            "automatic CODE V rerun is refused"
        )
    identities = _cell_map(plan)
    expected = [(cell, repeat) for (cell_id, repeat), cell in identities.items()]
    plan_sha = _sha(output_dir / "matrix-plan.json")
    seen_state_identities: set[tuple[object, object]] = set()
    for row in runs:
        if not isinstance(row, dict):
            raise ValueError("matrix state contains malformed run row")
        key = (row.get("cell_id"), row.get("repeat_index"))
        if key in seen_state_identities or key not in identities:
            raise ValueError("matrix state contains duplicate or unexpected run identity")
        seen_state_identities.add(key)
    for index, (cell, repeat) in enumerate(expected, start=1):
        identity = (cell["cell_id"], repeat)
        existing = [
            row
            for row in runs
            if isinstance(row, dict) and (row.get("cell_id"), row.get("repeat_index")) == identity
        ]
        if existing:
            if len(existing) != 1 or not isinstance(existing[0].get("receipt"), str):
                raise ValueError("matrix state contains duplicate or malformed run identity")
            evidence = restore_stagec_attested_evidence(Path(str(existing[0]["receipt"])))
            _validate_evidence_identity(
                evidence,
                cell=cell,
                repeat=repeat,
                matrix_id=matrix_id,
                plan_sha256=plan_sha,
            )
            if (
                existing[0].get("run_id") != evidence.run_id
                or existing[0].get("receipt_sha256") != evidence.receipt_sha256
                or existing[0].get("stageb_cache_scope") != evidence.stageb_cache_scope
                or existing[0].get("stageb_pre_run_bound") is not evidence.stageb_pre_run_bound
                or existing[0].get("stageb_cache_record_sha256")
                != evidence.stageb_cache_record_sha256
            ):
                raise ValueError("matrix state row differs from restored receipt")
            continue
        reconstruction = cell["reconstruction"]
        if not isinstance(reconstruction, dict):
            raise ValueError("matrix cell reconstruction is malformed")
        print(
            f"[stagec-matrix {index}/{len(expected)}] {cell['cell_id']} repeat={repeat}",
            flush=True,
        )
        run_id = f"stagec_{uuid4().hex}"
        started_monotonic = time.monotonic()
        attempt = {
            "attempt_id": uuid4().hex,
            "cell_id": cell["cell_id"],
            "case_id": cell["case_id"],
            "arm": cell["arm"],
            "repeat_index": repeat,
            "run_id": run_id,
            "stageb_cache_scope": cell["cache_scope"],
            "stageb_pre_run_bound": cell["pre_run_bound"],
            "stageb_cache_record_sha256": cell["cache_record_sha256"],
            "status": "started",
            "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "started_monotonic": started_monotonic,
            "duration_seconds": None,
            "receipt": None,
            "package_paths": [],
            "error": None,
        }
        attempts.append(attempt)
        _atomic_json(output_dir / "matrix-state.json", state)
        try:
            receipt = run_stagec_attested(
                stageb_manifest=Path(str(plan["stageb_manifest"])),
                execution_plan=output_dir / "matrix-plan.json",
                stageb_case_id=str(cell["case_id"]),
                matrix_id=matrix_id,
                arm=str(cell["arm"]),  # type: ignore[arg-type]
                repeat_index=repeat,
                target_image_height_mm=float(cell["target_image_height_mm"]),
                timeout_seconds=180.0,
                run_id=run_id,
            )
        except Exception as exc:
            root = trusted_stagec_run_root()
            package_paths = [
                str(path)
                for path in (
                    root / f"{run_id}.inflight",
                    root / run_id,
                    *sorted(root.glob(f"{run_id}.quarantine-*")),
                )
                if path.exists()
            ]
            attempt.update(
                {
                    "status": "failed",
                    "ended_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "duration_seconds": time.monotonic() - started_monotonic,
                    "package_paths": package_paths,
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            )
            _atomic_json(output_dir / "matrix-state.json", state)
            raise
        evidence = restore_stagec_attested_evidence(receipt)
        _validate_evidence_identity(
            evidence,
            cell=cell,
            repeat=repeat,
            matrix_id=matrix_id,
            plan_sha256=plan_sha,
            expected_run_id=run_id,
        )
        attempt.update(
            {
                "status": "attested",
                "ended_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "receipt": str(receipt),
                "package_paths": [str(receipt.parent)],
                "duration_seconds": time.monotonic() - started_monotonic,
            }
        )
        runs.append(_run_row(evidence, receipt))
        _atomic_json(output_dir / "matrix-state.json", state)
    return state


def aggregate(
    *, plan: dict[str, object], state: dict[str, object], output_dir: Path
) -> dict[str, object]:
    rows = state.get("runs")
    if not isinstance(rows, list):
        raise ValueError("matrix state is malformed")
    identities = _cell_map(plan)
    plan_sha = _sha(output_dir / "matrix-plan.json")
    evidence_rows: list[StageCAttestedEvidence] = []
    row_identities: set[tuple[object, object]] = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("receipt"), str):
            raise ValueError("matrix state contains malformed receipt row")
        key = (row.get("cell_id"), row.get("repeat_index"))
        if key in row_identities or key not in identities:
            raise ValueError("matrix state contains duplicate or unexpected run identity")
        evidence = restore_stagec_attested_evidence(Path(row["receipt"]))
        _validate_evidence_identity(
            evidence,
            cell=identities[key],
            repeat=int(row["repeat_index"]),
            matrix_id=str(plan["matrix_id"]),
            plan_sha256=plan_sha,
        )
        if (
            row.get("run_id") != evidence.run_id
            or row.get("receipt_sha256") != evidence.receipt_sha256
            or row.get("case_id") != evidence.seed_id
            or row.get("arm") != evidence.arm
            or row.get("stageb_cache_scope") != evidence.stageb_cache_scope
            or row.get("stageb_pre_run_bound") is not evidence.stageb_pre_run_bound
            or row.get("stageb_cache_record_sha256") != evidence.stageb_cache_record_sha256
        ):
            raise ValueError("matrix state row differs from restored receipt")
        row_identities.add(key)
        evidence_rows.append(evidence)
    expected_cells = {
        (str(cell["case_id"]), str(cell["arm"])) for cell in plan["cells"] if isinstance(cell, dict)
    }
    observed = {
        (evidence.seed_id, evidence.arm, evidence.repeat_index) for evidence in evidence_rows
    }
    expected = {(case_id, arm, repeat) for case_id, arm in expected_cells for repeat in (1, 2)}
    run_ids = {evidence.run_id for evidence in evidence_rows}
    receipt_hashes = {evidence.receipt_sha256 for evidence in evidence_rows}
    structural_complete = (
        len(expected_cells) == 24
        and len({case_id for case_id, _arm in expected_cells}) == 8
        and observed == expected
        and len(evidence_rows) == len(run_ids) == len(receipt_hashes) == 48
        and all(evidence.matrix_id == plan["matrix_id"] for evidence in evidence_rows)
        and all(evidence.execution_plan_sha256 == plan_sha for evidence in evidence_rows)
        and all(
            {arm for observed_case, arm in expected_cells if observed_case == case_id} == set(ARMS)
            for case_id in {case_id for case_id, _arm in expected_cells}
        )
    )
    if not structural_complete:
        raise ValueError("matrix aggregate does not prove 8 seeds × 3 arms × 2 unique repeats")
    seed_cache: dict[str, tuple[str, bool, str]] = {}
    for evidence in evidence_rows:
        binding = (
            evidence.stageb_cache_scope,
            evidence.stageb_pre_run_bound,
            evidence.stageb_cache_record_sha256,
        )
        if evidence.seed_id in seed_cache and seed_cache[evidence.seed_id] != binding:
            raise ValueError("matrix receipts contradict one seed's Stage B cache binding")
        seed_cache[evidence.seed_id] = binding
    scope_counts = {
        scope: sum(binding[0] == scope for binding in seed_cache.values())
        for scope in sorted({binding[0] for binding in seed_cache.values()})
    }
    retrospective_seed_ids = sorted(
        case_id
        for case_id, binding in seed_cache.items()
        if binding[0] == "retrospective-current-state-adoption"
    )
    all_pre_run_bound = all(binding[1] for binding in seed_cache.values())
    if (
        plan.get("stageb_cache_scope_counts") != scope_counts
        or plan.get("retrospective_seed_ids") != retrospective_seed_ids
        or plan.get("all_inputs_pre_run_bound") is not all_pre_run_bound
    ):
        raise ValueError("matrix receipt cache summary differs from the signed plan")
    runs = []
    for evidence in evidence_rows:
        spot_values = _valid_spot_values(evidence)
        wfe_values = _valid_wfe_values(evidence)
        runs.append(
            {
                "run_id": evidence.run_id,
                "case_id": evidence.seed_id,
                "cell_id": evidence.cell_id,
                "arm": evidence.arm,
                "repeat_index": evidence.repeat_index,
                "receipt_sha256": evidence.receipt_sha256,
                "stageb_cache_scope": evidence.stageb_cache_scope,
                "stageb_pre_run_bound": evidence.stageb_pre_run_bound,
                "stageb_cache_record_sha256": evidence.stageb_cache_record_sha256,
                "attested_duration_seconds": evidence.process_duration_seconds,
                "status": "delivered" if evidence.image_height_achieved else "blocked",
                "measured_efl_mm": evidence.measured_efl_mm,
                "target_image_height_mm": evidence.target_image_height_mm,
                "all_rays_valid": evidence.all_rays_valid,
                "all_metrics_valid": evidence.all_metrics_valid,
                "vignetting_profile_valid": evidence.vignetting_profile_valid,
                "spot_diameter_um": spot_values,
                "spot_metric_available": spot_values is not None,
                "rms_wfe_waves": wfe_values,
                "rms_wfe_metric_available": wfe_values is not None,
            }
        )
    delivered = sum(run["status"] == "delivered" for run in runs)
    attempts = _validate_attempt_rows(state.get("attempts"), identities=identities)
    failed_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict) and attempt.get("status") == "failed"
    ]
    incomplete_attempts = [
        attempt
        for attempt in attempts
        if isinstance(attempt, dict) and attempt.get("status") in {"started", "incomplete"}
    ]
    cell_distributions = []
    for case_id, arm in sorted(expected_cells):
        repeats = [
            evidence
            for evidence in evidence_rows
            if evidence.seed_id == case_id and evidence.arm == arm
        ]
        repeats.sort(key=lambda evidence: evidence.repeat_index)
        spot = _metric_summary(repeats, values_for=_valid_spot_values)
        wfe = _metric_summary(repeats, values_for=_valid_wfe_values)
        duration_samples = [item.process_duration_seconds for item in repeats]
        cell_distributions.append(
            {
                "case_id": case_id,
                "arm": arm,
                "run_ids": [item.run_id for item in repeats],
                "delivered_count": sum(item.image_height_achieved for item in repeats),
                "max_field_spot_diameter_um_samples": spot["samples"],
                "max_field_spot_diameter_um_valid_run_ids": spot["valid_run_ids"],
                "max_field_spot_diameter_um_unavailable_run_ids": spot["unavailable_run_ids"],
                "max_field_spot_diameter_um_valid_receipt_count": spot["valid_receipt_count"],
                "max_field_spot_diameter_um_availability": spot["availability"],
                "max_field_spot_diameter_um_spread": spot["spread"],
                "max_field_spot_diameter_um_mean": spot["mean"],
                "max_field_rms_wfe_waves_samples": wfe["samples"],
                "max_field_rms_wfe_waves_valid_run_ids": wfe["valid_run_ids"],
                "max_field_rms_wfe_waves_unavailable_run_ids": wfe["unavailable_run_ids"],
                "max_field_rms_wfe_waves_valid_receipt_count": wfe["valid_receipt_count"],
                "max_field_rms_wfe_waves_availability": wfe["availability"],
                "max_field_rms_wfe_waves_spread": wfe["spread"],
                "max_field_rms_wfe_waves_mean": wfe["mean"],
                "attested_duration_seconds_samples": duration_samples,
                "attested_duration_seconds_spread": max(duration_samples) - min(duration_samples),
                "attested_duration_seconds_mean": sum(duration_samples) / len(duration_samples),
            }
        )
    native_by_seed = {
        item["case_id"]: item
        for item in cell_distributions
        if item["arm"] == "native-imh-reconstructed-control"
    }
    for item in cell_distributions:
        native = native_by_seed[item["case_id"]]
        for metric in (
            "max_field_spot_diameter_um_mean",
            "max_field_rms_wfe_waves_mean",
            "attested_duration_seconds_mean",
        ):
            current_value = item[metric]
            baseline_value = native[metric]
            comparison_available = current_value is not None and baseline_value is not None
            if metric != "attested_duration_seconds_mean":
                prefix = metric.removesuffix("_mean")
                comparison_available = comparison_available and all(
                    candidate[f"{prefix}_availability"] == "complete"
                    for candidate in (item, native)
                )
            item[f"{metric}_comparison_available"] = comparison_available
            if not comparison_available:
                item[f"{metric}_delta_vs_native"] = None
                item[f"{metric}_pct_vs_native"] = None
                continue
            current = float(current_value)
            baseline = float(baseline_value)
            item[f"{metric}_delta_vs_native"] = current - baseline
            item[f"{metric}_pct_vs_native"] = (
                (current - baseline) / baseline * 100 if baseline != 0 else None
            )
    arm_duration_costs = []
    for arm in ARMS:
        samples = [
            evidence.process_duration_seconds for evidence in evidence_rows if evidence.arm == arm
        ]
        arm_duration_costs.append(
            {
                "arm": arm,
                "run_count": len(samples),
                "total_attested_duration_seconds": sum(samples),
                "mean_attested_duration_seconds": sum(samples) / len(samples),
            }
        )
    failed_or_incomplete = [*failed_attempts, *incomplete_attempts]
    known_failed_durations = [
        float(attempt["duration_seconds"])
        for attempt in failed_or_incomplete
        if isinstance(attempt.get("duration_seconds"), (int, float))
        and not isinstance(attempt.get("duration_seconds"), bool)
    ]
    report = {
        "schema_id": REPORT_SCHEMA,
        "matrix_id": plan["matrix_id"],
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "structural_complete": True,
        "seed_count": 8,
        "cell_count": 24,
        "repeat_count": 2,
        "run_count": 48,
        "stageb_cache_scope_counts": scope_counts,
        "retrospective_seed_ids": retrospective_seed_ids,
        "all_inputs_pre_run_bound": all_pre_run_bound,
        "delivered_run_count": delivered,
        "blocked_run_count": 48 - delivered,
        "failed_attempt_count": len(failed_attempts),
        "incomplete_attempt_count": len(incomplete_attempts),
        "failed_incomplete_known_duration_seconds": sum(known_failed_durations),
        "failed_incomplete_unknown_duration_count": len(failed_or_incomplete)
        - len(known_failed_durations),
        "attempts": attempts,
        "runs": runs,
        "cell_repeat_distributions": cell_distributions,
        "arm_duration_costs": arm_duration_costs,
        "metric_aggregation_policy": (
            "SPOTDATA and RMSWE means/spreads/comparisons use only receipts whose every field "
            "has a positive finite metric and a successful metric return; invalid/sentinel "
            "receipts are null/unavailable and partial repeats are never compared to native."
        ),
        "expert_verdict": None,
        "truth_notice": (
            "Machine-attested measurements and delivery gates only; no yield, qualification, "
            "production-usability, or [EXPERT] verdict is inferred."
        ),
    }
    _atomic_json(output_dir / "matrix-report.json", report)
    lines = [
        "# Stage C real-machine matrix",
        "",
        f"- matrix: `{report['matrix_id']}`",
        "- structural coverage: 8 seeds × 3 arms × 2 independent receipts = 48 runs",
        f"- final delivered/blocked: {delivered}/{48 - delivered}",
        f"- historical failed/incomplete attempts: {len(failed_attempts)}/{len(incomplete_attempts)}",
        f"- Stage B cache scopes (unique seeds): `{json.dumps(scope_counts, sort_keys=True)}`",
        f"- all Stage B inputs pre-run bound: `{str(all_pre_run_bound).lower()}`",
        f"- retrospective seed IDs: `{', '.join(retrospective_seed_ids) or 'none'}`",
        f"- known failed/incomplete duration cost: {sum(known_failed_durations):.6f}s "
        f"(unknown: {len(failed_or_incomplete) - len(known_failed_durations)})",
        "- SPOTDATA/RMSWE aggregates exclude invalid or sentinel receipts; unavailable values "
        "are null",
        "- [EXPERT]: blank",
        "",
        "Retrospective current-state adoption does not prove pre-run provenance; it only",
        "binds the reviewed bytes observed at adoption time.",
        "",
        "This is machine evidence, not a production-usability or yield verdict.",
    ]
    (output_dir / "matrix-report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stageb-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--recover-stale-matrix-lock", action="store_true")
    parser.add_argument("--recover-stale-window-lock", action="store_true")
    args = parser.parse_args()
    lock_root = args.output_dir.parent / f".{args.output_dir.name}.matrix-lock"
    with batch_runner_lock(
        lock_root,
        recover_stale=args.recover_stale_matrix_lock,
        details={"purpose": "stagec-real-matrix", "output_dir": str(args.output_dir.resolve())},
    ):
        plan = build_plan(stageb_manifest=args.stageb_manifest, output_dir=args.output_dir)
        if args.plan_only:
            print(args.output_dir / "matrix-plan.json")
            return 0
        with batch_runner_lock(
            P18_GLOBAL_WINDOW_ROOT,
            recover_stale=args.recover_stale_window_lock,
            details={
                "purpose": "stagec-real-matrix-p18-global-window",
                "output_dir": str(args.output_dir.resolve()),
            },
        ):
            state = execute_plan(plan=plan, output_dir=args.output_dir)
            report = aggregate(plan=plan, state=state, output_dir=args.output_dir)
    print(
        json.dumps(
            {key: report[key] for key in ("run_count", "delivered_run_count", "blocked_run_count")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
