"""Produce byte-pinned Stage B accepted inputs for the Stage C real matrix.

This is a production-path prerequisite, not a quality verdict.  A seed enters
the output manifest only when the existing Stage B ladder returns both
``target_achieved`` and ``accepted_final`` and the emitted ZMX can be copied and
hashed.  Failed ladders remain on disk and are reported honestly.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.batch_run_lock import (  # noqa: E402
    P18_GLOBAL_WINDOW_ROOT,
    _active_phase18_processes,
    batch_runner_lock,
)
from app.core.engines.codev import (  # noqa: E402
    _read_windows_file_version,
    probe_code_v_installation,
)
from app.core.engines.codev_batch import (  # noqa: E402
    CodeVBatchError,
    resolve_default_codev_executable,
)
from app.core.engines.codev_optimize import (  # noqa: E402
    RAY_RETRY_VIG_LADDER,
    run_codev_target_fno_ladder,
)
from app.core.engines.stageb_authority import (  # noqa: E402
    BATCH_RUNNER_KIND,
    LEGACY_STAGEB_TRUTH_NOTICE,
    OFFICIAL_EXECUTABLE,
    OFFICIAL_MACRO,
    STAGEB_MANIFEST_SCHEMA,
    STAGEB_TRUTH_NOTICE,
    TRUSTED_CODEV_FILE_VERSION,
    TRUSTED_CODEV_SHA256,
    TRUSTED_CODEV_SIZE_BYTES,
    TRUSTED_MACRO_SHA256,
    no_pre_run_raw_bytes,
    validate_retained_stageb_authority,
)
from app.core.orchestration.candidate import fnum_ladder_evidence_from_result  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "app" / "data" / "optical_cases" / "index.json"
ZMX_DIR = ROOT / "data" / "zmx"
MANIFEST_SCHEMA = STAGEB_MANIFEST_SCHEMA
INTENT_SCHEMA = "atelier-stagec-stageb-cache-intent-v1"
ADOPTION_SCHEMA = "atelier-stagec-stageb-cache-adoption-v1"
VIG_LADDER = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
FNUM_TOLERANCE_PCT = 8.0
CODEV_LOCK_ROOT = Path.home() / ".atelier" / "codev-execution-lock"
P18_REQUIRED_BATCH_ID = "night-20260711"
_P18_BATCH_KEYS = {
    "batch_id",
    "created_at",
    "updated_at",
    "target_source",
    "target_count",
    "status",
    "engine",
    "notes",
}


@dataclass(frozen=True)
class InputJob:
    case_id: str
    fnum_target: float
    rationale: str


# First four repeat already closed accepted cells with ZMX emission enabled.
# The next two target prior clean measured rungs.  Remaining jobs are honest
# exploration of offline-matrix-eligible seeds and are never assumed accepted.
JOBS = (
    InputJob("US20170003482A1", 2.4, "repeat closed loosen accepted cell with ZMX emission"),
    InputJob("US20210165194A1", 2.4, "repeat closed loosen accepted cell with ZMX emission"),
    InputJob("US8908290B1", 2.4, "repeat closed loosen accepted cell with ZMX emission"),
    InputJob("US-20260160979-A1-e3", 2.68, "repeat closed pilot accepted cell with ZMX emission"),
    InputJob("US-11940597-B2-e6", 3.8511981398212924, "target prior clean measured rung"),
    InputJob("US10281683B2", 2.472770408229216, "target prior clean measured rung"),
    InputJob("US20170045714A1", 1.75, "offline-matrix-eligible native F-number exploration"),
    InputJob("US9239447B1", 2.2, "offline-matrix-eligible native F-number exploration"),
    InputJob("US10310222B2", 1.8, "offline-matrix-eligible native F-number exploration"),
    InputJob("US20150338607A1", 1.6, "additional production-path native F-number exploration"),
    InputJob("US9651759B2", 2.2, "additional production-path native F-number exploration"),
    InputJob("US9201216B2", 2.1, "additional production-path native F-number exploration"),
    InputJob("US20140118844A1", 2.4, "additional production-path native F-number exploration"),
    InputJob("US9304295B2", 2.5, "additional production-path native F-number exploration"),
    InputJob("US8310767B2", 2.9, "additional production-path native F-number exploration"),
    InputJob("US9810880B2", 2.25, "additional production-path native F-number exploration"),
    InputJob("US9557532B2", 2.3, "additional production-path native F-number exploration"),
    InputJob("US10031318B2", 2.05, "additional production-path native F-number exploration"),
    InputJob("US9063319B1", 2.25, "additional production-path native F-number exploration"),
    InputJob("US9316811B2", 2.2, "additional production-path native F-number exploration"),
    InputJob("US9195030B2", 2.24, "additional production-path native F-number exploration"),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    """Flush a POSIX directory; Windows publication uses write-through moves."""

    resolved = path.resolve(strict=True)
    if os.name != "nt":
        fd = os.open(resolved, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return
    # Windows directory handles do not support FlushFileBuffers. Every publish
    # below uses MoveFileExW(MOVEFILE_WRITE_THROUGH), the documented equivalent
    # that waits for metadata movement to reach disk.


def _durable_move(source: Path, destination: Path, *, replace: bool) -> None:
    if os.name != "nt":
        if replace:
            os.replace(source, destination)
        elif source.is_file():
            os.link(source, destination)
            os.unlink(source)
            if source.parent.resolve() != destination.parent.resolve():
                _fsync_directory(source.parent)
        else:
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            renameat2 = getattr(libc, "renameat2", None)
            if renameat2 is None:
                raise OSError("atomic no-replace directory publication requires renameat2")
            renameat2.argtypes = (
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            )
            renameat2.restype = ctypes.c_int
            if (
                renameat2(
                    -100,
                    os.fsencode(source),
                    -100,
                    os.fsencode(destination),
                    1,
                )
                != 0
            ):
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(destination))
        _fsync_directory(destination.parent)
        return
    import ctypes
    from ctypes import wintypes

    flags = 0x00000008 | (0x00000001 if replace else 0)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    move_file = kernel32.MoveFileExW
    move_file.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    move_file.restype = wintypes.BOOL
    if not move_file(str(source), str(destination), flags):
        raise OSError(ctypes.get_last_error(), f"durable move failed: {source} -> {destination}")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    with temporary.open("xb") as handle:
        handle.write(_canonical_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())
    _durable_move(temporary, path, replace=True)


def _exclusive_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.exclusive-{uuid4().hex}.tmp")
    with temporary.open("xb") as handle:
        handle.write(_canonical_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())
    _durable_move(temporary, path, replace=False)


def _strict_json(path: Path) -> dict[str, object]:
    return _strict_json_raw(path.read_bytes(), label=str(path))


def _strict_json_raw(raw: bytes, *, label: str) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}: {label}")
            result[key] = value
        return result

    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=pairs,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON token {token}: {label}")
        ),
    )
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {label}")
    return value


def _descriptor(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    raw = resolved.read_bytes()
    return {"path": str(resolved), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _p18_terminal_authority(
    *,
    archive_root: Path,
    batch_id: str,
    expected_target_count: int = 50,
) -> dict[str, object]:
    root = archive_root.resolve(strict=True)
    if not root.is_dir() or batch_id != P18_REQUIRED_BATCH_ID or Path(batch_id).name != batch_id:
        raise ValueError("canonical existing P18 archive root/batch id is required")
    lock_file = (root / ".p18-runner.lock").resolve(strict=True)
    batch_path = (root / batch_id / "batch.json").resolve(strict=True)
    if batch_path.parent.parent != root or not lock_file.is_file() or not batch_path.is_file():
        raise ValueError("P18 lock root and terminal batch ledger are not co-located")
    batch = _strict_json(batch_path)
    if (
        set(batch) != _P18_BATCH_KEYS
        or batch.get("batch_id") != batch_id
        or batch.get("status") != "completed"
        or batch.get("target_count") != expected_target_count
        or batch.get("engine") != "real"
    ):
        raise ValueError("P18 terminal batch ledger differs from the closed prerequisite")
    return {
        "archive_root": str(root),
        "lock_file": {
            "path": str(lock_file),
            "protocol": "atelier-batch-runner-os-byte-range-v1",
            "content_observed": False,
        },
        "terminal_batch": _descriptor(batch_path),
        "batch_id": batch_id,
        "status": "completed",
        "target_count": expected_target_count,
    }


def _require_official_toolchain(executable: Path) -> Path:
    resolved = executable.resolve(strict=True)
    executable_raw = resolved.read_bytes()
    macro_raw = OFFICIAL_MACRO.resolve(strict=True).read_bytes()
    if (
        resolved != OFFICIAL_EXECUTABLE.resolve(strict=True)
        or hashlib.sha256(executable_raw).hexdigest() != TRUSTED_CODEV_SHA256
        or len(executable_raw) != TRUSTED_CODEV_SIZE_BYTES
        or hashlib.sha256(macro_raw).hexdigest() != TRUSTED_MACRO_SHA256
        or _read_windows_file_version(resolved) != TRUSTED_CODEV_FILE_VERSION
    ):
        raise ValueError("Stage B requires the exact official CODE V toolchain")
    return resolved


def _lock_root_key(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


def _lock_authority(*, output_root: Path, p18_archive_root: Path, mode: str) -> dict[str, object]:
    if mode not in {"pre-run-held", "retrospective-observation"}:
        raise ValueError("unsupported Stage B lock authority mode")
    return {
        "mode": mode,
        "order": ["output", "p18-global", "p18-archive", "codev-per-call"],
        "roots": {
            "output": str(output_root.resolve()),
            "p18_global": str(P18_GLOBAL_WINDOW_ROOT.resolve()),
            "p18_archive": str(p18_archive_root.resolve(strict=True)),
            "codev": str(CODEV_LOCK_ROOT.resolve()),
        },
    }


def _runner_sources() -> dict[str, object]:
    paths = [Path(__file__).resolve(), *sorted((ROOT / "app" / "core").rglob("*.py"))]
    paths.extend(path for path in (ROOT / "pyproject.toml", ROOT / "uv.lock") if path.is_file())
    files = {
        str(path.relative_to(ROOT)).replace("\\", "/"): {
            "sha256": _sha(path),
            "size": path.stat().st_size,
        }
        for path in paths
    }
    return {
        "files": files,
        "aggregate_sha256": hashlib.sha256(_canonical_bytes(files)).hexdigest(),
    }


def _python_environment() -> dict[str, object]:
    distributions = sorted(
        (
            (dist.metadata.get("Name") or "").lower(),
            dist.version,
        )
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    )
    payload = {
        "executable": _descriptor(Path(sys.executable)),
        "version": sys.version,
        "implementation": {
            "name": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag,
            "version": list(sys.implementation.version),
        },
        "platform": {
            "os_name": os.name,
            "sys_platform": sys.platform,
            "machine": platform.machine(),
        },
        "distributions": [list(item) for item in distributions],
    }
    return {
        **payload,
        "aggregate_sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
    }


def _parameters(
    *, job: InputJob, meta: dict[str, object], work_dir: Path | None = None
) -> dict[str, object]:
    parameters: dict[str, object] = {
        "target_efl_mm": float(meta["efl_mm"]),
        "fnum_target": job.fnum_target,
        "target_imh_mm": float(meta["image_height_mm"]),
        "stage": "B",
        "rung_count": 3,
        "fnum_tolerance_pct": FNUM_TOLERANCE_PCT,
        "vig_ladder": list(VIG_LADDER),
        "ray_retry_vig_ladder": list(RAY_RETRY_VIG_LADDER),
        "num_fields": 3,
        "extra_dof": "both",
        "glass_bounds_nd_vd": None,
        "emit_optimized_zmx": True,
        "timeout_seconds": 180.0,
        "platform_name": os.name,
    }
    if work_dir is not None:
        parameters["work_dir"] = str(work_dir.resolve())
    return parameters


def _current_identity(
    *,
    job: InputJob,
    meta: dict[str, object],
    executable: Path,
    work_dir: Path | None = None,
    lock_authority: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if lock_authority is None:
        raise ValueError("Stage B current identity requires retained lock authority")
    source = ZMX_DIR / str(meta["source_zmx"])
    exe = executable.resolve(strict=True)
    version = _read_windows_file_version(exe)
    installation = probe_code_v_installation(env={}, scan_registry=False, common_roots=[exe.parent])
    discovered_version = installation.version if installation is not None else None
    if (
        version is not None
        and discovered_version is not None
        and not discovered_version.startswith(
            version.split(".", 2)[0] + "." + version.split(".", 2)[1]
        )
    ):
        raise ValueError("CODE V file/discovered versions disagree")
    version = version or discovered_version
    if not version:
        raise ValueError("CODE V executable has no readable file version")
    metadata = {
        "case_id": job.case_id,
        "rationale": job.rationale,
        "index_record": meta,
        "scenario": meta["scenario"],
        "native_image_height_mm": float(meta["image_height_mm"]),
    }
    return {
        "runner_kind": BATCH_RUNNER_KIND,
        "lock_authority": dict(lock_authority),
        "job": metadata,
        "job_sha256": hashlib.sha256(_canonical_bytes(metadata)).hexdigest(),
        "source": _descriptor(source),
        "codev": {**_descriptor(exe), "version": version},
        "official_macro": _descriptor(OFFICIAL_MACRO),
        "runner_sources": _runner_sources(),
        "python_environment": _python_environment(),
        "parameters": _parameters(job=job, meta=meta, work_dir=work_dir),
    }


def _index() -> dict[str, dict[str, object]]:
    rows = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {str(row["case_id"]): row for row in rows}


def _rebind_accepted_path(result: dict[str, object], path: str) -> None:
    accepted = result.get("accepted_final")
    rungs = result.get("rungs")
    if not isinstance(accepted, dict) or not isinstance(rungs, list):
        raise ValueError("accepted Stage B ladder mirrors are missing")
    rung_index = accepted.get("rung_index")
    accepted["optimized_zmx_path"] = path
    matches = [
        rung for rung in rungs if isinstance(rung, dict) and rung.get("rung_index") == rung_index
    ]
    if len(matches) != 1:
        raise ValueError("accepted Stage B target rung mirror is not unique")
    matches[0]["optimized_zmx_path"] = path
    last = result.get("last_measured_rung")
    if isinstance(last, dict) and last.get("rung_index") == rung_index:
        last["optimized_zmx_path"] = path


def _publish_accepted(*, raw_result: dict[str, object], output_dir: Path, case_id: str) -> None:
    evidence = fnum_ladder_evidence_from_result(raw_result)
    accepted = raw_result.get("accepted_final")
    if not (
        raw_result.get("target_achieved") is True
        and evidence is not None
        and evidence.target_achieved
        and isinstance(accepted, dict)
    ):
        return
    emitted_raw = accepted.get("optimized_zmx_path")
    emitted = Path(str(emitted_raw)).resolve(strict=True) if emitted_raw else None
    if emitted is None or not emitted.is_file():
        raise ValueError("accepted_final emitted ZMX is missing")
    raw = emitted.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    canonical = output_dir / "accepted" / case_id / f"{digest}.zmx"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    if canonical.exists():
        if canonical.read_bytes() != raw:
            raise ValueError(f"content-addressed accepted collision: {canonical}")
    else:
        temporary = canonical.with_name(f".{canonical.name}.{uuid4().hex}.tmp")
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _durable_move(temporary, canonical, replace=False)
    _rebind_accepted_path(raw_result, str(canonical.resolve()))


def _business_transform_matches(*, raw: dict[str, object], final: dict[str, object]) -> bool:
    expected = copy.deepcopy(raw)
    actual = copy.deepcopy(final)
    actual.pop("cache_provenance", None)
    raw_accepted = expected.get("accepted_final")
    final_accepted = actual.get("accepted_final")
    if isinstance(raw_accepted, dict) and isinstance(final_accepted, dict):
        final_path = final_accepted.get("optimized_zmx_path")
        if not isinstance(final_path, str):
            return False
        _rebind_accepted_path(expected, final_path)
    return actual == expected


def _ladder_claims_match_identity(result: dict[str, object], identity: dict[str, object]) -> bool:
    if result.get("schema") == "atelier-stagec-stageb-input-error-v1":
        job = identity.get("job")
        return (
            set(result)
            == {
                "schema",
                "case_id",
                "target_achieved",
                "accepted_final",
                "error",
                "stagec_input_job",
            }
            and isinstance(job, dict)
            and result.get("case_id") == job.get("case_id")
            and result.get("target_achieved") is False
            and result.get("accepted_final") is None
            and isinstance(result.get("error"), dict)
            and bool(result["error"])
        )
    parameters = identity.get("parameters")
    job = identity.get("job")
    index_record = job.get("index_record") if isinstance(job, dict) else None
    return (
        result.get("schema") == "atelier-p15-fno-ladder-v1"
        and isinstance(parameters, dict)
        and isinstance(index_record, dict)
        and result.get("source_zmx") == index_record.get("source_zmx")
        and result.get("target_efl_mm") == parameters.get("target_efl_mm")
        and result.get("fnum_target") == parameters.get("fnum_target")
        and result.get("stage") == parameters.get("stage")
        and result.get("rung_count") == parameters.get("rung_count")
        and result.get("fnum_tolerance_pct") == parameters.get("fnum_tolerance_pct")
        and result.get("vig_ladder") == parameters.get("vig_ladder")
        and result.get("ray_retry_vig_ladder") == parameters.get("ray_retry_vig_ladder")
        and result.get("num_fields") == parameters.get("num_fields")
        and result.get("extra_dof") == parameters.get("extra_dof")
    )


def _accepted_artifact_binding(
    *, raw: dict[str, object], final: dict[str, object], output_dir: Path, case_id: str
) -> dict[str, object] | None:
    raw_accepted = raw.get("accepted_final")
    final_accepted = final.get("accepted_final")
    if raw_accepted is None and final_accepted is None:
        return None
    if not isinstance(raw_accepted, dict) or not isinstance(final_accepted, dict):
        raise ValueError("accepted_final shape changed during cache derivation")
    raw_path_value = raw_accepted.get("optimized_zmx_path")
    final_path_value = final_accepted.get("optimized_zmx_path")
    if not isinstance(raw_path_value, str) or not isinstance(final_path_value, str):
        raise ValueError("accepted_final paths are missing")
    raw_descriptor = _descriptor(Path(raw_path_value))
    final_descriptor = _descriptor(Path(final_path_value))
    expected_path = (
        output_dir / "accepted" / case_id / f"{raw_descriptor['sha256']}.zmx"
    ).resolve()
    if (
        Path(final_path_value).resolve(strict=True) != expected_path
        or final_descriptor["sha256"] != raw_descriptor["sha256"]
        or final_descriptor["size"] != raw_descriptor["size"]
    ):
        raise ValueError("accepted bytes/path are not the exact canonical raw emission")
    return {"raw_emitted": raw_descriptor, "published": final_descriptor}


def _validate_bound_attempt(
    *, attempt_dir: Path, expected_identity: dict[str, object]
) -> dict[str, object]:
    intent_path = attempt_dir / "intent.json"
    raw_path = attempt_dir / "raw-ladder-result.json"
    result_path = attempt_dir / "ladder-result.json"
    intent = _strict_json(intent_path)
    lock_owner_ids = intent.get("lock_owner_ids")
    if (
        set(intent)
        != {
            "schema_id",
            "scope",
            "attempt_id",
            "created_at",
            "identity",
            "lock_owner_ids",
        }
        or intent.get("schema_id") != INTENT_SCHEMA
        or intent.get("scope") != "pre-run-intent"
        or intent.get("identity") != expected_identity
        or not isinstance(lock_owner_ids, dict)
        or set(lock_owner_ids) != {"output", "p18_global", "p18_archive", "codev"}
        or any(
            not isinstance(lock_owner_ids.get(name), str) or len(str(lock_owner_ids[name])) != 32
            for name in ("output", "p18_global", "p18_archive")
        )
        or lock_owner_ids.get("codev") is not None
    ):
        raise ValueError("cached pre-run intent differs from current identity")
    intent_sha = _sha(intent_path)
    result = _strict_json(result_path)
    raw = _strict_json(raw_path)
    provenance = result.get("cache_provenance")
    expected_provenance = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": intent_sha,
        "raw_result_sha256": _sha(raw_path),
        "post_run_identity_sha256": hashlib.sha256(_canonical_bytes(expected_identity)).hexdigest(),
    }
    binding = _accepted_artifact_binding(
        raw=raw,
        final=result,
        output_dir=attempt_dir.parents[3],
        case_id=attempt_dir.parent.parent.name,
    )
    if binding is not None:
        expected_provenance["accepted_artifact"] = binding
    if not isinstance(provenance, dict) or provenance != expected_provenance:
        raise ValueError("cached result does not reverse-bind its intent/raw/post-run identity")
    if not _business_transform_matches(raw=raw, final=result):
        raise ValueError("cached final result changes business facts beyond accepted path rebound")
    if not _ladder_claims_match_identity(raw, expected_identity):
        raise ValueError("cached raw ladder claims differ from pre-run intent")
    return {
        "result": result,
        "path": result_path,
        "raw": raw_path,
        "scope": "pre-run-bound",
        "record": intent_path,
    }


def _validate_adoption(
    *,
    output_dir: Path,
    job: InputJob,
    expected_identity: dict[str, object],
    expected_p18_terminal_authority: Mapping[str, object],
) -> dict[str, object] | None:
    legacy_result = output_dir / "ladders" / job.case_id / "ladder-result.json"
    adoption_path = output_dir / "adoptions-v1" / f"{job.case_id}.json"
    if not adoption_path.is_file():
        if legacy_result.is_file():
            raise RuntimeError("legacy cache lacks pre-run intent; explicit adoption required")
        return None
    adoption = _strict_json(adoption_path)
    embedded_raw_value = adoption.get("legacy_manifest_base64")
    if not isinstance(embedded_raw_value, str):
        raise ValueError("retrospective adoption lacks embedded legacy manifest")
    try:
        embedded_raw = base64.b64decode(embedded_raw_value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("embedded legacy manifest is not strict base64") from exc
    _strict_json_raw(embedded_raw, label="embedded legacy manifest")
    embedded_descriptor = adoption.get("legacy_manifest")
    if not isinstance(embedded_descriptor, dict) or (
        embedded_descriptor.get("sha256") != hashlib.sha256(embedded_raw).hexdigest()
        or embedded_descriptor.get("size") != len(embedded_raw)
    ):
        raise ValueError("embedded legacy manifest differs from its descriptor")
    result = _strict_json(legacy_result)
    artifacts = []
    accepted = result.get("accepted_final")
    if isinstance(accepted, dict) and isinstance(accepted.get("optimized_zmx_path"), str):
        artifacts.append(_descriptor(Path(accepted["optimized_zmx_path"])))
    if (
        set(adoption)
        != {
            "schema_id",
            "scope",
            "pre_run_bound",
            "run_time_identity_verified",
            "adopted_at",
            "case_id",
            "legacy_result",
            "legacy_manifest",
            "legacy_manifest_base64",
            "current_identity",
            "referenced_artifacts",
            "p18_terminal_authority",
            "claims_match_current",
        }
        or adoption.get("schema_id") != ADOPTION_SCHEMA
        or adoption.get("scope") != "retrospective-current-state-adoption"
        or adoption.get("pre_run_bound") is not False
        or adoption.get("run_time_identity_verified") is not False
        or adoption.get("case_id") != job.case_id
        or adoption.get("current_identity") != expected_identity
        or adoption.get("legacy_result") != _descriptor(legacy_result)
        or adoption.get("legacy_manifest") != _descriptor(output_dir / "manifest.json")
        or adoption.get("referenced_artifacts") != artifacts
        or adoption.get("p18_terminal_authority") != dict(expected_p18_terminal_authority)
        or adoption.get("claims_match_current") is not True
    ):
        raise ValueError("retrospective adoption binding changed")
    if not _ladder_claims_match_identity(result, expected_identity):
        raise ValueError("adopted legacy result claims differ from current identity")
    return {
        "result": result,
        "path": legacy_result,
        "raw": None,
        "scope": "retrospective-current-state-adoption",
        "record": adoption_path,
    }


def _attempt_snapshot(attempt_dir: Path) -> dict[str, object]:
    files = {
        str(path.relative_to(attempt_dir)).replace("\\", "/"): _descriptor(path)
        for path in sorted(attempt_dir.rglob("*"))
        if path.is_file()
    }
    return {
        "path": str(attempt_dir.resolve()),
        "files": files,
        "aggregate_sha256": hashlib.sha256(_canonical_bytes(files)).hexdigest(),
    }


def _validated_recovery_receipt(
    *,
    output_dir: Path,
    attempt_dir: Path,
    expected_identity: dict[str, object],
    expected_p18_root: Path | None,
    expected_p18_terminal_authority: Mapping[str, object],
) -> bool:
    receipt = (
        output_dir
        / "attempt-recoveries"
        / attempt_dir.parent.parent.name
        / f"{attempt_dir.name}.json"
    )
    if not receipt.is_file():
        return False
    payload = _strict_json(receipt)
    intent = (
        _strict_json(attempt_dir / "intent.json")
        if (attempt_dir / "intent.json").is_file()
        else None
    )
    classification = (
        "raw-without-final"
        if (attempt_dir / "raw-ladder-result.json").is_file()
        else "intent-only"
        if intent is not None
        else "missing-intent"
    )
    roots = payload.get("lock_roots")
    lock_ids = payload.get("lock_ids")
    return (
        payload.get("schema_id") == "atelier-stagec-stageb-attempt-recovery-v1"
        and payload.get("case_id") == attempt_dir.parent.parent.name
        and payload.get("attempt_id") == attempt_dir.name
        and payload.get("classification") == classification
        and payload.get("attempt_snapshot") == _attempt_snapshot(attempt_dir)
        and payload.get("old_identity")
        == (intent.get("identity") if isinstance(intent, dict) else None)
        and payload.get("current_identity") == expected_identity
        and payload.get("processes_zero") is True
        and isinstance(roots, dict)
        and roots.get("output")
        == _lock_root_key(output_dir.parent / f".{output_dir.name}.stageb-input-lock")
        and roots.get("codev") == _lock_root_key(CODEV_LOCK_ROOT)
        and expected_p18_root is not None
        and roots.get("p18") == _lock_root_key(expected_p18_root)
        and roots.get("p18_archive")
        == _lock_root_key(Path(str(expected_p18_terminal_authority["archive_root"])))
        and len(set(roots.values())) == 4
        and isinstance(lock_ids, dict)
        and set(lock_ids) == {"output", "p18", "p18_archive", "codev"}
        and payload.get("p18_terminal_authority") == dict(expected_p18_terminal_authority)
        and all(
            isinstance(value, str)
            and len(value) == 32
            and all(char in "0123456789abcdef" for char in value)
            for value in lock_ids.values()
        )
    )


def _run_job(
    *,
    job: InputJob,
    meta: dict[str, object],
    output_dir: Path,
    executable: Path,
    recovery_p18_root: Path | None = None,
    lock_authority: Mapping[str, object] | None = None,
    lock_owner_ids: Mapping[str, object] | None = None,
    p18_terminal_authority: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if lock_authority is None or lock_owner_ids is None or p18_terminal_authority is None:
        raise ValueError("Stage B run requires retained lock authority/owners")
    attempts_root = output_dir / "ladders" / job.case_id / "attempts"
    if attempts_root.is_dir():
        attempt_dirs = [path for path in attempts_root.iterdir() if path.is_dir()]
        attempt_identities = {
            path: _current_identity(
                job=job,
                meta=meta,
                executable=executable,
                work_dir=path / "work",
                lock_authority=lock_authority,
            )
            for path in attempt_dirs
        }
        incomplete = [path for path in attempt_dirs if not (path / "ladder-result.json").is_file()]
        unrecovered = [
            path
            for path in incomplete
            if not _validated_recovery_receipt(
                output_dir=output_dir,
                attempt_dir=path,
                expected_identity=attempt_identities[path],
                expected_p18_root=recovery_p18_root,
                expected_p18_terminal_authority=p18_terminal_authority,
            )
        ]
        if unrecovered:
            raise RuntimeError(
                "incomplete Stage B attempt requires explicit crash recovery; refusing a new run: "
                + ", ".join(str(path) for path in unrecovered)
            )
        completed = [path for path in attempt_dirs if (path / "ladder-result.json").is_file()]
        matches = []
        for path in completed:
            try:
                historical_intent = _strict_json(path / "intent.json")
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"cached Stage B attempt intent is damaged: {path}") from exc
            if historical_intent.get("identity") != attempt_identities[path]:
                continue
            try:
                matches.append(
                    _validate_bound_attempt(
                        attempt_dir=path,
                        expected_identity=attempt_identities[path],
                    )
                )
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"cached Stage B attempt is damaged: {path}") from exc
        if len(matches) > 1:
            raise ValueError("duplicate current-identity Stage B cache attempts")
        if matches:
            return matches[0]  # type: ignore[return-value]
    retrospective_lock_authority = dict(lock_authority)
    retrospective_lock_authority["mode"] = "retrospective-observation"
    adoption_identity = _current_identity(
        job=job,
        meta=meta,
        executable=executable,
        work_dir=None,
        lock_authority=retrospective_lock_authority,
    )
    adopted = _validate_adoption(
        output_dir=output_dir,
        job=job,
        expected_identity=adoption_identity,
        expected_p18_terminal_authority=p18_terminal_authority,
    )
    if adopted is not None:
        return adopted  # type: ignore[return-value]

    attempt_id = uuid4().hex
    attempt_dir = attempts_root / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    work_dir = attempt_dir / "work"
    identity = _current_identity(
        job=job,
        meta=meta,
        executable=executable,
        work_dir=work_dir,
        lock_authority=lock_authority,
    )
    intent = {
        "schema_id": INTENT_SCHEMA,
        "scope": "pre-run-intent",
        "attempt_id": attempt_id,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "identity": identity,
        "lock_owner_ids": dict(lock_owner_ids),
    }
    intent_path = attempt_dir / "intent.json"
    _exclusive_json(intent_path, intent)
    started = time.monotonic()
    try:
        result = run_codev_target_fno_ladder(
            source_zmx=ZMX_DIR / str(meta["source_zmx"]),
            work_dir=work_dir,
            target_efl_mm=float(meta["efl_mm"]),
            fnum_target=job.fnum_target,
            target_imh_mm=float(meta["image_height_mm"]),
            stage="B",
            rung_count=3,
            fnum_tolerance_pct=FNUM_TOLERANCE_PCT,
            vig_ladder=VIG_LADDER,
            ray_retry_vig_ladder=RAY_RETRY_VIG_LADDER,
            num_fields=3,
            extra_dof="both",
            glass_bounds_nd_vd=None,
            emit_optimized_zmx=True,
            executable=executable,
            timeout_seconds=180.0,
            platform_name=os.name,
        )
    except CodeVBatchError as exc:
        result = {
            "schema": "atelier-stagec-stageb-input-error-v1",
            "case_id": job.case_id,
            "target_achieved": False,
            "accepted_final": None,
            "error": exc.describe(),
        }
    result["stagec_input_job"] = {
        "rationale": job.rationale,
        "duration_seconds": time.monotonic() - started,
    }
    raw_path = attempt_dir / "raw-ladder-result.json"
    _exclusive_json(raw_path, result)
    post_identity = _current_identity(
        job=job,
        meta=meta,
        executable=executable,
        work_dir=work_dir,
        lock_authority=lock_authority,
    )
    if post_identity != identity:
        raise RuntimeError("Stage B source/CODE V/runner identity changed during run")
    derived = json.loads(json.dumps(result, allow_nan=False))
    _publish_accepted(raw_result=derived, output_dir=output_dir, case_id=job.case_id)
    provenance = {
        "scope": "pre-run-bound",
        "pre_run_bound": True,
        "intent_sha256": _sha(intent_path),
        "raw_result_sha256": _sha(raw_path),
        "post_run_identity_sha256": hashlib.sha256(_canonical_bytes(post_identity)).hexdigest(),
    }
    accepted_binding = _accepted_artifact_binding(
        raw=result, final=derived, output_dir=output_dir, case_id=job.case_id
    )
    if accepted_binding is not None:
        provenance["accepted_artifact"] = accepted_binding
    derived["cache_provenance"] = provenance
    result_path = attempt_dir / "ladder-result.json"
    _exclusive_json(result_path, derived)
    return {
        "result": derived,
        "path": result_path,
        "raw": raw_path,
        "scope": "pre-run-bound",
        "record": intent_path,
    }


def _adopt_legacy_cache_locked(
    *,
    output_dir: Path,
    executable: Path,
    p18_terminal_authority: dict[str, object],
    lock_authority: Mapping[str, object],
) -> dict[str, int]:
    """Create retrospective records only; never mutate or run legacy artifacts."""

    manifest_path = output_dir / "manifest.json"
    manifest_raw = manifest_path.resolve(strict=True).read_bytes()
    manifest = _strict_json_raw(manifest_raw, label=str(manifest_path))
    manifest_descriptor = {
        "path": str(manifest_path.resolve()),
        "sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "size": len(manifest_raw),
    }
    outcomes = manifest.get("outcomes")
    legacy_accepted = manifest.get("accepted")
    if (
        not isinstance(outcomes, list)
        or not outcomes
        or any(
            not isinstance(row, dict)
            or not isinstance(row.get("case_id"), str)
            or not isinstance(row.get("accepted"), bool)
            or (row.get("accepted") is False and not isinstance(row.get("reason"), str))
            for row in outcomes
        )
    ):
        raise ValueError("legacy manifest outcomes are not all terminal")
    if (
        set(manifest)
        != {
            "schema_id",
            "created_at",
            "required_count",
            "accepted_count",
            "complete",
            "accepted",
            "outcomes",
            "expert_verdict",
            "truth_notice",
        }
        or manifest.get("schema_id") != "atelier-stagec-stageb-input-manifest-v1"
        or manifest.get("required_count") != 8
        or not isinstance(legacy_accepted, list)
        or manifest.get("accepted_count") != len(legacy_accepted)
        or manifest.get("complete") is not (len(legacy_accepted) >= 8)
        or manifest.get("expert_verdict") is not None
        or manifest.get("truth_notice") != LEGACY_STAGEB_TRUTH_NOTICE
    ):
        raise ValueError("legacy manifest top-level claims are inconsistent")
    legacy_accepted_by_case = {
        str(entry.get("case_id")): entry for entry in legacy_accepted if isinstance(entry, dict)
    }
    outcome_accepted_ids = {
        str(row["case_id"])
        for row in outcomes
        if isinstance(row, dict) and row.get("accepted") is True
    }
    if (
        len(legacy_accepted_by_case) != len(legacy_accepted)
        or set(legacy_accepted_by_case) != outcome_accepted_ids
    ):
        raise ValueError("legacy accepted case set differs from terminal outcomes")
    active = _active_phase18_processes()
    if active:
        raise RuntimeError(f"active Phase18/CODE V processes remain: {active}")
    records = _index()
    jobs = {job.case_id: job for job in JOBS}
    outcome_ids = [str(row["case_id"]) for row in outcomes if isinstance(row, dict)]
    expected_ids = [job.case_id for job in JOBS[: len(outcome_ids)]]
    result_ids = sorted(
        path.parent.name for path in (output_dir / "ladders").glob("*/ladder-result.json")
    )
    if (
        len(set(outcome_ids)) != len(outcome_ids)
        or outcome_ids != expected_ids
        or sorted(outcome_ids) != result_ids
    ):
        raise ValueError("legacy manifest/result case set or count differs from reviewed jobs")
    adoption_root = output_dir / "adoptions-v1"
    stale_staging = list(output_dir.glob(".adoptions-v1.building-*"))
    if stale_staging:
        raise RuntimeError("incomplete adoption staging requires explicit forensic recovery")
    pending: list[tuple[Path, dict[str, object]]] = []
    created = 0
    verified = 0
    for outcome in outcomes:
        assert isinstance(outcome, dict)
        case_id = str(outcome["case_id"])
        job = jobs.get(case_id)
        if job is None or case_id not in records:
            raise ValueError(f"legacy outcome is outside reviewed jobs: {case_id}")
        legacy_result = output_dir / "ladders" / case_id / "ladder-result.json"
        result = _strict_json(legacy_result)
        evidence = fnum_ladder_evidence_from_result(result)
        result_accepted = (
            result.get("target_achieved") is True
            and evidence is not None
            and evidence.target_achieved is True
            and evidence.accepted_final is not None
        )
        if result_accepted is not (outcome.get("accepted") is True):
            raise ValueError(f"legacy outcome/result accepted gate differs: {case_id}")
        identity = _current_identity(
            job=job,
            meta=records[case_id],
            executable=executable,
            lock_authority=lock_authority,
        )
        artifacts = []
        accepted = result.get("accepted_final")
        legacy_entry = legacy_accepted_by_case.get(case_id)
        if result_accepted:
            if (
                not isinstance(legacy_entry, dict)
                or legacy_entry.get("accepted_final") != accepted
                or legacy_entry.get("ladder_result") != str(legacy_result.resolve())
                or legacy_entry.get("ladder_result_sha256") != _sha(legacy_result)
            ):
                raise ValueError(f"legacy accepted manifest binding differs: {case_id}")
        elif legacy_entry is not None:
            raise ValueError(f"legacy rejected result appears accepted: {case_id}")
        if isinstance(accepted, dict) and isinstance(accepted.get("optimized_zmx_path"), str):
            artifacts.append(_descriptor(Path(accepted["optimized_zmx_path"])))
        payload = {
            "schema_id": ADOPTION_SCHEMA,
            "scope": "retrospective-current-state-adoption",
            "pre_run_bound": False,
            "run_time_identity_verified": False,
            "adopted_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "case_id": case_id,
            "legacy_result": _descriptor(legacy_result),
            "legacy_manifest": manifest_descriptor,
            "legacy_manifest_base64": base64.b64encode(manifest_raw).decode("ascii"),
            "current_identity": identity,
            "referenced_artifacts": artifacts,
            "p18_terminal_authority": p18_terminal_authority,
            "claims_match_current": (
                result.get("source_zmx") == records[case_id].get("source_zmx")
                and result.get("target_efl_mm") == records[case_id].get("efl_mm")
                and result.get("fnum_target") == job.fnum_target
            ),
        }
        if payload["claims_match_current"] is not True:
            raise ValueError(f"legacy result claims differ from current identity: {case_id}")
        path = adoption_root / f"{case_id}.json"
        if isinstance(accepted, dict) and isinstance(accepted.get("optimized_zmx_path"), str):
            accepted_path = Path(str(accepted["optimized_zmx_path"])).resolve(strict=True)
            adoption_raw = _canonical_bytes(payload)
            entry = {
                "case_id": case_id,
                "scenario": records[case_id]["scenario"],
                "source_zmx": str(
                    (ZMX_DIR / str(records[case_id]["source_zmx"])).resolve(strict=True)
                ),
                "source_zmx_sha256": _sha(ZMX_DIR / str(records[case_id]["source_zmx"])),
                "accepted_zmx": str(accepted_path),
                "accepted_zmx_sha256": _sha(accepted_path),
                "target_efl_mm": float(records[case_id]["efl_mm"]),
                "native_image_height_mm": float(records[case_id]["image_height_mm"]),
                "fnum_target": job.fnum_target,
                "accepted_final": accepted,
                "ladder_result": str(legacy_result.resolve()),
                "ladder_result_sha256": _sha(legacy_result),
                "raw_ladder_result_path": None,
                "raw_ladder_result_sha256": None,
                "cache_scope": "retrospective-current-state-adoption",
                "cache_record_path": str(path.resolve()),
                "cache_record_sha256": hashlib.sha256(adoption_raw).hexdigest(),
                "pre_run_bound": False,
            }
            authority_manifest = {
                "schema_id": MANIFEST_SCHEMA,
                "created_at": datetime.now(UTC).isoformat(timespec="microseconds"),
                "required_count": 1,
                "accepted_count": 1,
                "complete": True,
                "accepted": [entry],
                "cache_scope_counts": {"retrospective-current-state-adoption": 1},
                "all_inputs_pre_run_bound": False,
                "expert_verdict": None,
                "truth_notice": STAGEB_TRUTH_NOTICE,
            }
            validate_retained_stageb_authority(
                manifest_raw=_canonical_bytes(authority_manifest),
                ladder_raw=legacy_result.read_bytes(),
                raw_ladder_raw=no_pre_run_raw_bytes(),
                cache_record_raw=adoption_raw,
                case_id=case_id,
                accepted_zmx_raw=accepted_path.read_bytes(),
                verify_external_paths=False,
            )
        if path.exists():
            existing = _strict_json(path)
            comparable_existing = {
                key: value for key, value in existing.items() if key != "adopted_at"
            }
            comparable_new = {key: value for key, value in payload.items() if key != "adopted_at"}
            if comparable_existing != comparable_new:
                raise ValueError(f"existing adoption differs from current evidence: {case_id}")
            pending.append((path, existing))
        else:
            pending.append((path, payload))
    if adoption_root.exists():
        if sorted(path.name for path, _payload in pending) != sorted(
            path.name for path in adoption_root.iterdir() if path.is_file()
        ):
            raise ValueError("published adoption directory has missing or extra records")
        verified = len(pending)
    else:
        staging = output_dir / f".adoptions-v1.building-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        _fsync_directory(output_dir)
        for path, payload in pending:
            _exclusive_json(staging / path.name, payload)
        _fsync_directory(staging)
        _durable_move(staging, adoption_root, replace=False)
        created = len(pending)
    return {"created": created, "verified": verified}


def adopt_legacy_cache(
    *,
    output_dir: Path,
    executable: Path,
    p18_archive_root: Path,
    p18_batch_id: str,
) -> dict[str, int]:
    executable = _require_official_toolchain(executable)
    p18_terminal_before_lock = _p18_terminal_authority(
        archive_root=p18_archive_root,
        batch_id=p18_batch_id,
    )
    output_lock_root = output_dir.parent / f".{output_dir.name}.stageb-input-lock"
    roots = {
        _lock_root_key(path)
        for path in (
            output_lock_root,
            P18_GLOBAL_WINDOW_ROOT,
            p18_archive_root,
            CODEV_LOCK_ROOT,
        )
    }
    if len(roots) != 4:
        raise ValueError("Stage B authority lock roots must be pairwise distinct")
    with (
        batch_runner_lock(
            output_lock_root,
            details={"purpose": "stageb-cache-adoption-output-authority"},
        ),
        batch_runner_lock(
            P18_GLOBAL_WINDOW_ROOT,
            details={"purpose": "stageb-cache-adoption-p18-authority"},
        ),
        batch_runner_lock(
            p18_archive_root,
            details={"purpose": "stageb-cache-adoption-p18-archive-authority"},
        ),
        batch_runner_lock(
            CODEV_LOCK_ROOT,
            details={"purpose": "stageb-cache-adoption-codev-authority"},
        ),
    ):
        p18_terminal_authority = _p18_terminal_authority(
            archive_root=p18_archive_root,
            batch_id=p18_batch_id,
        )
        if p18_terminal_authority != p18_terminal_before_lock:
            raise ValueError("P18 terminal authority changed while acquiring adoption locks")
        return _adopt_legacy_cache_locked(
            output_dir=output_dir,
            executable=executable,
            p18_terminal_authority=p18_terminal_authority,
            lock_authority=_lock_authority(
                output_root=output_lock_root,
                p18_archive_root=p18_archive_root,
                mode="retrospective-observation",
            ),
        )


def recover_incomplete_attempts(
    *,
    output_dir: Path,
    executable: Path,
    p18_archive_root: Path,
    p18_batch_id: str,
    recover_stale_p18_lock: bool,
    recover_stale_codev_lock: bool,
    recover_stale_output_lock: bool = False,
) -> dict[str, int]:
    executable = _require_official_toolchain(executable)
    p18_terminal_before_lock = _p18_terminal_authority(
        archive_root=p18_archive_root,
        batch_id=p18_batch_id,
    )
    output_lock_root = output_dir.parent / f".{output_dir.name}.stageb-input-lock"
    if (
        len(
            {
                _lock_root_key(path)
                for path in (
                    output_lock_root,
                    P18_GLOBAL_WINDOW_ROOT,
                    p18_archive_root,
                    CODEV_LOCK_ROOT,
                )
            }
        )
        != 4
    ):
        raise ValueError("Stage B authority lock roots must be pairwise distinct")
    with (
        batch_runner_lock(
            output_lock_root,
            recover_stale=recover_stale_output_lock,
            details={"purpose": "stageb-attempt-recovery-output-authority"},
        ) as output_owner,
        batch_runner_lock(
            P18_GLOBAL_WINDOW_ROOT,
            recover_stale_if_present=recover_stale_p18_lock,
            details={"purpose": "stageb-attempt-recovery-p18-authority"},
        ) as p18_owner,
        batch_runner_lock(
            p18_archive_root,
            recover_stale_if_present=recover_stale_p18_lock,
            details={"purpose": "stageb-attempt-recovery-p18-archive-authority"},
        ) as archive_owner,
        batch_runner_lock(
            CODEV_LOCK_ROOT,
            recover_stale=recover_stale_codev_lock,
            details={"purpose": "stageb-attempt-recovery-codev-authority"},
        ) as codev_owner,
    ):
        if recover_stale_p18_lock and not (
            p18_owner.get("recovered_stale") is True or archive_owner.get("recovered_stale") is True
        ):
            raise ValueError("P18 recovery requested but neither global nor archive root was stale")
        p18_terminal_authority = _p18_terminal_authority(
            archive_root=p18_archive_root,
            batch_id=p18_batch_id,
        )
        if p18_terminal_authority != p18_terminal_before_lock:
            raise ValueError("P18 terminal authority changed while acquiring recovery locks")
        active = _active_phase18_processes()
        if active:
            raise RuntimeError(f"active Phase18/CODE V processes remain: {active}")
        records = _index()
        jobs = {job.case_id: job for job in JOBS}
        created = 0
        verified = 0
        for attempt in sorted((output_dir / "ladders").glob("*/attempts/*")):
            if not attempt.is_dir() or (attempt / "ladder-result.json").is_file():
                continue
            case_id = attempt.parent.parent.name
            job = jobs.get(case_id)
            if job is None or case_id not in records:
                raise ValueError(f"incomplete attempt is outside reviewed jobs: {attempt}")
            intent = (
                _strict_json(attempt / "intent.json")
                if (attempt / "intent.json").is_file()
                else None
            )
            current_identity = _current_identity(
                job=job,
                meta=records[case_id],
                executable=executable,
                work_dir=attempt / "work",
                lock_authority=_lock_authority(
                    output_root=output_lock_root,
                    p18_archive_root=p18_archive_root,
                    mode="pre-run-held",
                ),
            )
            stage = (
                "raw-without-final"
                if (attempt / "raw-ladder-result.json").is_file()
                else "intent-only"
                if intent is not None
                else "missing-intent"
            )
            payload = {
                "schema_id": "atelier-stagec-stageb-attempt-recovery-v1",
                "recovered_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "case_id": case_id,
                "attempt_id": attempt.name,
                "classification": stage,
                "attempt_snapshot": _attempt_snapshot(attempt),
                "old_identity": intent.get("identity") if isinstance(intent, dict) else None,
                "current_identity": current_identity,
                "processes_zero": True,
                "lock_roots": {
                    "output": _lock_root_key(output_lock_root),
                    "p18": _lock_root_key(P18_GLOBAL_WINDOW_ROOT),
                    "p18_archive": _lock_root_key(p18_archive_root),
                    "codev": _lock_root_key(CODEV_LOCK_ROOT),
                },
                "lock_ids": {
                    "output": output_owner["lock_id"],
                    "p18": p18_owner["lock_id"],
                    "p18_archive": archive_owner["lock_id"],
                    "codev": codev_owner["lock_id"],
                },
                "p18_terminal_authority": p18_terminal_authority,
            }
            receipt = output_dir / "attempt-recoveries" / case_id / f"{attempt.name}.json"
            if receipt.exists():
                existing = _strict_json(receipt)
                comparable_existing = {
                    k: v for k, v in existing.items() if k not in {"recovered_at", "lock_ids"}
                }
                comparable_new = {
                    k: v for k, v in payload.items() if k not in {"recovered_at", "lock_ids"}
                }
                if comparable_existing != comparable_new:
                    raise ValueError(f"attempt recovery receipt changed: {receipt}")
                verified += 1
            else:
                _exclusive_json(receipt, payload)
                created += 1
        return {"created": created, "verified": verified}


def _retained_incomplete_attempts(output_dir: Path) -> list[dict[str, object]]:
    retained: list[dict[str, object]] = []
    for attempt in sorted((output_dir / "ladders").glob("*/attempts/*")):
        if not attempt.is_dir() or (attempt / "ladder-result.json").is_file():
            continue
        case_id = attempt.parent.parent.name
        receipt = output_dir / "attempt-recoveries" / case_id / f"{attempt.name}.json"
        retained.append(
            {
                "case_id": case_id,
                "attempt_id": attempt.name,
                "path": str(attempt.resolve()),
                "classification": (
                    "raw-without-final"
                    if (attempt / "raw-ladder-result.json").is_file()
                    else "intent-only"
                    if (attempt / "intent.json").is_file()
                    else "missing-intent"
                ),
                "recovery_receipt": str(receipt.resolve()) if receipt.is_file() else None,
                "recovery_receipt_sha256": _sha(receipt) if receipt.is_file() else None,
            }
        )
    return retained


def build_inputs(
    *,
    output_dir: Path,
    required_count: int,
    executable: Path,
    limit: int | None = None,
    recovery_p18_root: Path | None = None,
    p18_terminal_authority: Mapping[str, object] | None = None,
    lock_authority: Mapping[str, object] | None = None,
    lock_owner_ids: Mapping[str, object] | None = None,
) -> dict[str, object]:
    executable = _require_official_toolchain(executable)
    if p18_terminal_authority is None or lock_authority is None or lock_owner_ids is None:
        raise ValueError("Stage B build requires P18 terminal and lock authority")
    expected_p18 = _p18_terminal_authority(
        archive_root=Path(str(p18_terminal_authority["archive_root"])),
        batch_id=str(p18_terminal_authority["batch_id"]),
        expected_target_count=int(p18_terminal_authority["target_count"]),
    )
    if expected_p18 != dict(p18_terminal_authority):
        raise ValueError("P18 terminal authority changed before Stage B build")
    if required_count != 8:
        raise ValueError("Stage C production manifest requires exactly eight accepted seeds")
    records = _index()
    accepted: list[dict[str, object]] = []
    outcomes: list[dict[str, object]] = []
    jobs = JOBS if limit is None else JOBS[:limit]
    if len({job.case_id for job in jobs}) != len(jobs):
        raise ValueError("Stage B input jobs must have unique case IDs")
    for index, job in enumerate(jobs, start=1):
        print(
            f"[stagec-input {index}/{len(jobs)}] {job.case_id} -> F/{job.fnum_target}",
            flush=True,
        )
        meta = records[job.case_id]
        cache = _run_job(
            job=job,
            meta=meta,
            output_dir=output_dir,
            executable=executable,
            recovery_p18_root=recovery_p18_root,
            lock_authority=lock_authority,
            lock_owner_ids=lock_owner_ids,
            p18_terminal_authority=p18_terminal_authority,
        )
        result = cache["result"]
        if not isinstance(result, dict):
            raise ValueError("Stage B cache result is malformed")
        result_path = Path(str(cache["path"])).resolve(strict=True)
        scope = str(cache["scope"])
        record_path = Path(str(cache["record"])).resolve(strict=True)
        raw_value = cache.get("raw")
        if scope == "pre-run-bound":
            raw_result_path = Path(str(raw_value)).resolve(strict=True)
            raw_result_path_value: str | None = str(raw_result_path)
            raw_result_sha_value: str | None = _sha(raw_result_path)
        elif scope == "retrospective-current-state-adoption" and raw_value is None:
            raw_result_path_value = None
            raw_result_sha_value = None
        else:
            raise ValueError("Stage B cache raw-result scope binding is malformed")
        evidence = fnum_ladder_evidence_from_result(result)
        accepted_raw = result.get("accepted_final")
        accepted_ok = (
            result.get("target_achieved") is True
            and evidence is not None
            and evidence.target_achieved is True
            and isinstance(accepted_raw, dict)
        )
        reason = None
        if accepted_ok:
            emitted_raw = accepted_raw.get("optimized_zmx_path")
            emitted = Path(str(emitted_raw)) if emitted_raw else None
            if emitted is None or not emitted.is_file():
                accepted_ok = False
                reason = "accepted_final emitted ZMX is missing"
            else:
                rebound = fnum_ladder_evidence_from_result(result)
                if rebound is None or rebound.accepted_final is None:
                    raise RuntimeError("persisted accepted_final failed Stage B revalidation")
                entry = {
                    "case_id": job.case_id,
                    "scenario": meta["scenario"],
                    "source_zmx": str((ZMX_DIR / str(meta["source_zmx"])).resolve()),
                    "source_zmx_sha256": _sha(ZMX_DIR / str(meta["source_zmx"])),
                    "accepted_zmx": str(emitted.resolve()),
                    "accepted_zmx_sha256": _sha(emitted),
                    "target_efl_mm": float(meta["efl_mm"]),
                    "native_image_height_mm": float(meta["image_height_mm"]),
                    "fnum_target": job.fnum_target,
                    "accepted_final": accepted_raw,
                    "ladder_result": str(result_path),
                    "ladder_result_sha256": _sha(result_path),
                    "raw_ladder_result_path": raw_result_path_value,
                    "raw_ladder_result_sha256": raw_result_sha_value,
                    "cache_scope": scope,
                    "cache_record_path": str(record_path),
                    "cache_record_sha256": _sha(record_path),
                    "pre_run_bound": scope == "pre-run-bound",
                }
                authority_manifest = {
                    "schema_id": MANIFEST_SCHEMA,
                    "created_at": datetime.now(UTC).isoformat(timespec="microseconds"),
                    "required_count": 1,
                    "accepted_count": 1,
                    "complete": True,
                    "accepted": [entry],
                    "cache_scope_counts": {scope: 1},
                    "all_inputs_pre_run_bound": scope == "pre-run-bound",
                    "expert_verdict": None,
                    "truth_notice": STAGEB_TRUTH_NOTICE,
                }
                validate_retained_stageb_authority(
                    manifest_raw=_canonical_bytes(authority_manifest),
                    ladder_raw=result_path.read_bytes(),
                    raw_ladder_raw=(
                        Path(str(raw_result_path_value)).read_bytes()
                        if raw_result_path_value is not None
                        else no_pre_run_raw_bytes()
                    ),
                    cache_record_raw=record_path.read_bytes(),
                    case_id=job.case_id,
                    accepted_zmx_raw=emitted.read_bytes(),
                    verify_external_paths=True,
                )
                accepted.append(entry)
        if not accepted_ok and reason is None:
            reason = "Stage B four-condition target_achieved/accepted_final gate did not close"
        outcomes.append(
            {
                "case_id": job.case_id,
                "fnum_target": job.fnum_target,
                "accepted": accepted_ok,
                "reason": reason,
                "cache_scope": scope,
                "cache_record_path": str(record_path),
                "cache_record_sha256": _sha(record_path),
                "pre_run_bound": scope == "pre-run-bound",
                "result_sha256": _sha(result_path),
            }
        )
        print(
            f"[stagec-input {index}/{len(jobs)}] accepted={accepted_ok} "
            f"accepted_count={len(accepted)} reason={reason or '-'}",
            flush=True,
        )
        if len(accepted) >= required_count:
            break
    scope_counts = {
        scope: sum(row["cache_scope"] == scope for row in accepted)
        for scope in sorted({str(row["cache_scope"]) for row in accepted})
    }
    manifest = {
        "schema_id": MANIFEST_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(timespec="microseconds"),
        "required_count": required_count,
        "accepted_count": len(accepted),
        "complete": len(accepted) == 8,
        "accepted": accepted,
        "outcomes": outcomes,
        "cache_scope_counts": scope_counts,
        "all_inputs_pre_run_bound": bool(accepted)
        and all(row["pre_run_bound"] for row in accepted),
        "incomplete_attempts": _retained_incomplete_attempts(output_dir),
        "expert_verdict": None,
        "truth_notice": STAGEB_TRUTH_NOTICE,
    }
    if manifest["complete"] is True:
        manifest_raw_for_validation = _canonical_bytes(manifest)
        for entry in accepted:
            ladder_path = Path(str(entry["ladder_result"]))
            record_path = Path(str(entry["cache_record_path"]))
            accepted_path = Path(str(entry["accepted_zmx"]))
            raw_path = entry["raw_ladder_result_path"]
            validate_retained_stageb_authority(
                manifest_raw=manifest_raw_for_validation,
                ladder_raw=ladder_path.read_bytes(),
                raw_ladder_raw=(
                    Path(str(raw_path)).read_bytes()
                    if raw_path is not None
                    else no_pre_run_raw_bytes()
                ),
                cache_record_raw=record_path.read_bytes(),
                case_id=str(entry["case_id"]),
                accepted_zmx_raw=accepted_path.read_bytes(),
                verify_external_paths=True,
            )
    if _p18_terminal_authority(
        archive_root=Path(str(p18_terminal_authority["archive_root"])),
        batch_id=str(p18_terminal_authority["batch_id"]),
        expected_target_count=int(p18_terminal_authority["target_count"]),
    ) != dict(p18_terminal_authority):
        raise ValueError("P18 terminal authority changed during Stage B build")
    current_path = output_dir / "manifest-v2.json"
    if current_path.is_file():
        current = _strict_json(current_path)
        current_truth = {key: value for key, value in current.items() if key != "created_at"}
        new_truth = {key: value for key, value in manifest.items() if key != "created_at"}
        if current_truth == new_truth:
            return current
        if current.get("complete") is True and manifest.get("complete") is not True:
            raise ValueError(
                "refusing to downgrade a complete manifest-v2 with a smaller/incomplete limit"
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_raw = _canonical_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    snapshot_path = output_dir / "manifest-v2-snapshots" / f"{manifest_sha}.json"
    if snapshot_path.exists():
        if snapshot_path.read_bytes() != manifest_raw:
            raise ValueError("manifest-v2 snapshot hash collision")
    else:
        _exclusive_json(snapshot_path, manifest)
    _atomic_json(current_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--required-count", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--executable", type=Path, default=resolve_default_codev_executable())
    parser.add_argument("--adopt-legacy-cache", action="store_true")
    parser.add_argument("--recover-incomplete-attempts", action="store_true")
    parser.add_argument("--p18-archive-root", type=Path)
    parser.add_argument(
        "--p18-batch-id",
        choices=(P18_REQUIRED_BATCH_ID,),
        required=True,
    )
    parser.add_argument("--recover-stale-output-lock", action="store_true")
    parser.add_argument("--recover-stale-p18-lock", action="store_true")
    parser.add_argument("--recover-stale-codev-lock", action="store_true")
    args = parser.parse_args()
    lock_root = args.output_dir.parent / f".{args.output_dir.name}.stageb-input-lock"
    if args.adopt_legacy_cache and args.recover_incomplete_attempts:
        parser.error("adoption and incomplete-attempt recovery are mutually exclusive modes")
    if args.adopt_legacy_cache or args.recover_incomplete_attempts:
        if args.p18_archive_root is None:
            parser.error("adoption/recovery requires --p18-archive-root")
        if args.limit is not None or args.required_count != 8:
            parser.error("adoption/recovery modes do not accept build limit/count options")
        if args.adopt_legacy_cache:
            if any(
                (
                    args.recover_stale_output_lock,
                    args.recover_stale_p18_lock,
                    args.recover_stale_codev_lock,
                )
            ):
                parser.error("adoption-only cannot recover stale locks")
            summary = adopt_legacy_cache(
                output_dir=args.output_dir,
                executable=args.executable,
                p18_archive_root=args.p18_archive_root,
                p18_batch_id=args.p18_batch_id,
            )
        else:
            summary = recover_incomplete_attempts(
                output_dir=args.output_dir,
                executable=args.executable,
                p18_archive_root=args.p18_archive_root,
                p18_batch_id=args.p18_batch_id,
                recover_stale_p18_lock=args.recover_stale_p18_lock,
                recover_stale_codev_lock=args.recover_stale_codev_lock,
                recover_stale_output_lock=args.recover_stale_output_lock,
            )
        print(json.dumps(summary, indent=2))
        return 0
    if args.recover_stale_codev_lock:
        parser.error(
            "normal build cannot recover the inner CODE V lock; run the explicit "
            "--recover-incomplete-attempts recovery mode first"
        )
    if args.p18_archive_root is None:
        parser.error("normal Stage B build requires canonical --p18-archive-root")
    executable = _require_official_toolchain(args.executable)
    p18_terminal_before_lock = _p18_terminal_authority(
        archive_root=args.p18_archive_root,
        batch_id=args.p18_batch_id,
    )
    if (
        len(
            {
                _lock_root_key(lock_root),
                _lock_root_key(P18_GLOBAL_WINDOW_ROOT),
                _lock_root_key(args.p18_archive_root),
                _lock_root_key(CODEV_LOCK_ROOT),
            }
        )
        != 4
    ):
        parser.error("Stage B authority lock roots must be pairwise distinct")
    with (
        batch_runner_lock(
            lock_root,
            recover_stale=args.recover_stale_output_lock,
            details={
                "purpose": "stagec-stageb-inputs",
                "output_dir": str(args.output_dir.resolve()),
            },
        ) as output_owner,
        batch_runner_lock(
            P18_GLOBAL_WINDOW_ROOT,
            recover_stale_if_present=args.recover_stale_p18_lock,
            details={"purpose": "stagec-stageb-inputs-p18-global-authority"},
        ) as p18_global_owner,
        batch_runner_lock(
            args.p18_archive_root,
            recover_stale_if_present=args.recover_stale_p18_lock,
            details={"purpose": "stagec-stageb-inputs-p18-archive-authority"},
        ) as p18_archive_owner,
    ):
        if args.recover_stale_p18_lock and not (
            p18_global_owner.get("recovered_stale") is True
            or p18_archive_owner.get("recovered_stale") is True
        ):
            parser.error("--recover-stale-p18-lock requested but neither P18 root was stale")
        active = _active_phase18_processes()
        if active:
            raise RuntimeError(f"active Phase18/CODE V processes remain: {active}")
        p18_terminal_authority = _p18_terminal_authority(
            archive_root=args.p18_archive_root,
            batch_id=args.p18_batch_id,
        )
        if p18_terminal_authority != p18_terminal_before_lock:
            raise ValueError("P18 terminal authority changed while acquiring build locks")
        manifest = build_inputs(
            output_dir=args.output_dir,
            required_count=args.required_count,
            executable=executable,
            limit=args.limit,
            recovery_p18_root=P18_GLOBAL_WINDOW_ROOT,
            p18_terminal_authority=p18_terminal_authority,
            lock_authority=_lock_authority(
                output_root=lock_root,
                p18_archive_root=args.p18_archive_root,
                mode="pre-run-held",
            ),
            lock_owner_ids={
                "output": output_owner["lock_id"],
                "p18_global": p18_global_owner["lock_id"],
                "p18_archive": p18_archive_owner["lock_id"],
                "codev": None,
            },
        )
    print(json.dumps({key: manifest[key] for key in ("accepted_count", "complete")}, indent=2))
    return 0 if manifest["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
