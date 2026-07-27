"""Pre-run-bound Stage B authority lifecycle.

The external interface is deliberately small: open one authority session,
run closed requests through it, and validate retained authority bytes.  The
implementation hides lock ordering, durable intent publication, the official
CODE V ladder call, immutable raw/final artifacts, and the accepted-ZMX hash
DAG.  Legacy adoption remains an explicit caller concern; this module only
validates its retained representation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.metadata
import json
import math
import os
import re
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.core.batch_run_lock import P18_GLOBAL_WINDOW_ROOT, batch_runner_lock
from app.core.engines.codev import _read_windows_file_version
from app.core.engines.codev_optimize import (
    RAY_RETRY_VIG_LADDER,
    run_codev_target_fno_ladder,
)
from app.core.lens_system import Scenario

PRE_RUN_SCOPE = "pre-run-bound"
RETROSPECTIVE_SCOPE = "retrospective-current-state-adoption"
CACHE_INTENT_SCHEMA = "atelier-stagec-stageb-cache-intent-v1"
CACHE_ADOPTION_SCHEMA = "atelier-stagec-stageb-cache-adoption-v1"
NO_PRE_RUN_RAW_SCHEMA = "atelier-stagec-no-pre-run-raw-v1"
STAGEB_MANIFEST_SCHEMA = "atelier-stagec-stageb-input-manifest-v2"
OFFICIAL_MACRO = Path("D:/CODEV115/macro/zemaxos_to_cv.seq")
OFFICIAL_EXECUTABLE = Path("D:/CODEV115/codev.exe")
TRUSTED_CODEV_SHA256 = "05fd2b3c3588d839257cfe09f5585e69921195f6975bfe6793de2b05b4033aae"
TRUSTED_CODEV_SIZE_BYTES = 383848
TRUSTED_MACRO_SHA256 = "55cb7f9c8c40a58c8a059bdcc93dd84d54355f47676296b2e8f74fe9967f36ef"
TRUSTED_CODEV_FILE_VERSION = "11.5.27302.701"
CODEV_LOCK_ROOT = Path.home() / ".atelier" / "codev-execution-lock"
STAGEB_TRUTH_NOTICE = (
    "Retained Stage B machine facts only; cache scope is explicit; no yield, "
    "production usability, or [EXPERT] verdict is asserted."
)
LEGACY_STAGEB_TRUTH_NOTICE = (
    "Stage B machine gates and byte bindings only; no yield, production usability, "
    "or [EXPERT] verdict is asserted."
)
PRODUCTION_RUNNER_KIND = "production-generator"
BATCH_RUNNER_KIND = "stageb-input-batch"
VIG_LADDER = (0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
FNUM_TOLERANCE_PCT = 8.0
_SAFE_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_ATTEMPT_ID = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROOT = Path(__file__).resolve().parents[3]
_BASE_PARAMETER_KEYS = {
    "target_efl_mm",
    "fnum_target",
    "target_imh_mm",
    "stage",
    "rung_count",
    "fnum_tolerance_pct",
    "vig_ladder",
    "ray_retry_vig_ladder",
    "num_fields",
    "extra_dof",
    "glass_bounds_nd_vd",
    "emit_optimized_zmx",
    "timeout_seconds",
    "platform_name",
}
_PRODUCTION_PARAMETER_KEYS = {*_BASE_PARAMETER_KEYS, "work_dir"}
_COMMON_RUNNER_SOURCES = frozenset(
    {
        "app/core/batch_run_lock.py",
        "app/core/engines/codev.py",
        "app/core/engines/codev_batch.py",
        "app/core/engines/codev_optimize.py",
        "app/core/engines/stageb_authority.py",
        "pyproject.toml",
        "uv.lock",
    }
)
_REQUIRED_RUNNER_SOURCES = {
    PRODUCTION_RUNNER_KIND: _COMMON_RUNNER_SOURCES | {"app/core/orchestration/generators.py"},
    BATCH_RUNNER_KIND: _COMMON_RUNNER_SOURCES | {"scripts/p16_stagec_stageb_inputs.py"},
}
_SCENARIOS = frozenset(scenario.value for scenario in Scenario)
_MANIFEST_COMMON_KEYS = {
    "schema_id",
    "created_at",
    "required_count",
    "accepted_count",
    "complete",
    "accepted",
    "cache_scope_counts",
    "all_inputs_pre_run_bound",
    "expert_verdict",
    "truth_notice",
}
_MANIFEST_BATCH_KEYS = _MANIFEST_COMMON_KEYS | {"outcomes", "incomplete_attempts"}
_MANIFEST_ENTRY_KEYS = {
    "case_id",
    "scenario",
    "source_zmx",
    "source_zmx_sha256",
    "accepted_zmx",
    "accepted_zmx_sha256",
    "target_efl_mm",
    "native_image_height_mm",
    "fnum_target",
    "accepted_final",
    "ladder_result",
    "ladder_result_sha256",
    "raw_ladder_result_path",
    "raw_ladder_result_sha256",
    "cache_scope",
    "cache_record_path",
    "cache_record_sha256",
    "pre_run_bound",
}
_BATCH_OUTCOME_KEYS = {
    "case_id",
    "fnum_target",
    "accepted",
    "reason",
    "cache_scope",
    "cache_record_path",
    "cache_record_sha256",
    "pre_run_bound",
    "result_sha256",
}
_INCOMPLETE_ATTEMPT_KEYS = {
    "case_id",
    "attempt_id",
    "path",
    "classification",
    "recovery_receipt",
    "recovery_receipt_sha256",
}
_P18_REQUIRED_BATCH_ID = "night-20260711"
_P18_REQUIRED_TARGET_COUNT = 50
_LADDER_TOP_KEYS = {
    "schema",
    "source_zmx",
    "stage",
    "target_efl_mm",
    "fnum_target",
    "rung_count",
    "fnum_tolerance_pct",
    "vig_ladder",
    "ray_retry_vig_ladder",
    "num_fields",
    "extra_dof",
    "native_fnum_measured",
    "rungs",
    "last_measured_rung_index",
    "last_measured_rung",
    "target_achieved",
    "accepted_final",
    "blocked",
}
_RUNG_KEYS = {
    "rung_index",
    "target_fnum",
    "status",
    "measured_fnum",
    "fnum_target_deviation_pct",
    "fno_param_achieved",
    "ray_traceable",
    "ray_grid",
    "efl_target_deviation_pct",
    "post_aut.max_rms_spot_diameter_um",
    "post_aut.max_rms_wavefront_error_waves",
    "err_f_ratio",
    "aut_termination",
    "aut_converged",
    "autovig.edge_used",
    "autovig.converged",
    "effective_edge_used",
    "quality_note",
    "optimized_zmx_path",
    "ray_retry",
    "error",
}
_RAY_GRID_KEYS = {
    "category",
    "refl_count",
    "miss_count",
    "ray_aiming_warning",
    "aperture_conflict_matched",
    "excerpt",
    "note",
    "normal_completion",
    "abnormal_completion_matched",
}
_RAY_RETRY_KEYS = {
    "triggered",
    "accepted_edge",
    "attempts",
    "quality_note",
    "skip_reason",
}
_RAY_RETRY_ATTEMPT_KEYS = {"edge", "aut_converged", "ray_category", "error"}
_FORBIDDEN_CLAIM_KEYS = frozenset(
    {
        "expert",
        "expert_verdict",
        "yield",
        "yield_pct",
        "qualified",
        "qualification",
        "production_usable",
        "production_usability",
        "quality_verdict",
        "pass_fail",
    }
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _strict_json(raw: bytes, label: str) -> dict[str, object]:
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


def _reject_forbidden_claims(value: object, *, label: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).casefold() in _FORBIDDEN_CLAIM_KEYS:
                raise ValueError(f"forbidden verdict/yield claim in {label}: {key}")
            _reject_forbidden_claims(item, label=f"{label}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_claims(item, label=f"{label}[{index}]")
    elif isinstance(value, str) and re.search(
        r"(?i)(\[expert\]|\bverdict\b|\byield\b|\bqualified\b|"
        r"production[- ]usable|\bpass\b)",
        value,
    ):
        raise ValueError(f"forbidden verdict/yield text in {label}")


def _validate_ladder_shape(
    value: Mapping[str, object],
    *,
    label: str,
    allow_historical_accepted_path_rebound: bool = False,
) -> None:
    _reject_forbidden_claims(value, label=label)
    expected_top = set(_LADDER_TOP_KEYS)
    if "stagec_input_job" in value:
        expected_top.add("stagec_input_job")
    if "cache_provenance" in value:
        expected_top.add("cache_provenance")
    if set(value) != expected_top:
        raise ValueError(f"{label} differs from the closed ladder schema")
    rungs = value.get("rungs")
    if not isinstance(rungs, list) or not rungs:
        raise ValueError(f"{label} has no closed rung list")
    for index, rung in enumerate(rungs):
        if not isinstance(rung, dict) or set(rung) != _RUNG_KEYS:
            raise ValueError(f"{label}.rungs[{index}] differs from the closed schema")
    accepted = value.get("accepted_final")
    measured_rungs = [rung for rung in rungs if rung.get("status") == "measured"]
    expected_last = measured_rungs[-1] if measured_rungs else None
    if value.get("last_measured_rung") != expected_last or value.get(
        "last_measured_rung_index"
    ) != (expected_last.get("rung_index") if expected_last is not None else None):
        raise ValueError(f"{label} last measured rung is not re-derived from rungs")
    target_rungs = [rung for rung in rungs if rung.get("target_fnum") == value.get("fnum_target")]
    if value.get("target_achieved") is not (accepted is not None):
        raise ValueError(f"{label} target gate and accepted_final are contradictory")
    if accepted is not None:
        if len(target_rungs) != 1:
            raise ValueError(f"{label} requires one unique target F-number rung")
        if not isinstance(accepted, dict) or set(accepted) != _RUNG_KEYS:
            raise ValueError(f"{label}.accepted_final differs from the closed rung schema")
        if accepted != target_rungs[0]:
            normalized_accepted = dict(accepted)
            normalized_target = dict(target_rungs[0])
            normalized_accepted.pop("optimized_zmx_path", None)
            normalized_target.pop("optimized_zmx_path", None)
            if (
                not allow_historical_accepted_path_rebound
                or normalized_accepted != normalized_target
            ):
                raise ValueError(f"{label}.accepted_final is not the retained target rung")
        ray_grid = accepted.get("ray_grid")
        if not isinstance(ray_grid, dict) or set(ray_grid) != _RAY_GRID_KEYS:
            raise ValueError(f"{label}.accepted_final ray grid is not closed")
        ray_retry = accepted.get("ray_retry")
        if ray_retry is not None:
            if not isinstance(ray_retry, dict) or set(ray_retry) != _RAY_RETRY_KEYS:
                raise ValueError(f"{label}.accepted_final ray retry is not closed")
            attempts = ray_retry.get("attempts")
            if not isinstance(attempts, list) or any(
                not isinstance(item, dict) or set(item) != _RAY_RETRY_ATTEMPT_KEYS
                for item in attempts
            ):
                raise ValueError(f"{label}.accepted_final retry attempts are not closed")
    elif len(target_rungs) > 1:
        raise ValueError(f"{label} has duplicate unaccepted target F-number rungs")
    stagec_job = value.get("stagec_input_job")
    if stagec_job is not None and (
        not isinstance(stagec_job, dict) or set(stagec_job) != {"rationale", "duration_seconds"}
    ):
        raise ValueError(f"{label}.stagec_input_job differs from the closed schema")


def _rebind_accepted_path(value: dict[str, object], path: str) -> None:
    accepted = value.get("accepted_final")
    rungs = value.get("rungs")
    if not isinstance(accepted, dict) or not isinstance(rungs, list):
        raise ValueError("Stage B accepted ladder cannot be rebound")
    rung_index = accepted.get("rung_index")
    accepted["optimized_zmx_path"] = path
    matches = [
        rung for rung in rungs if isinstance(rung, dict) and rung.get("rung_index") == rung_index
    ]
    if len(matches) != 1:
        raise ValueError("Stage B accepted rung mirror is not unique")
    matches[0]["optimized_zmx_path"] = path
    last = value.get("last_measured_rung")
    if isinstance(last, dict) and last.get("rung_index") == rung_index:
        last["optimized_zmx_path"] = path


def _closed_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} differs from the closed schema")


def _canonical_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a canonical absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be a canonical absolute path")
    canonical = str(path.resolve(strict=False))
    if value != canonical:
        raise ValueError(f"{label} must be a canonical absolute path")
    return canonical


def _descriptor(path: Path, raw: bytes | None = None) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    payload = resolved.read_bytes() if raw is None else raw
    return {"path": str(resolved), "sha256": _sha(payload), "size": len(payload)}


def _validate_descriptor(
    value: object,
    label: str,
    *,
    expected_path: object | None = None,
    expected_raw: bytes | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a file descriptor")
    _closed_keys(value, {"path", "sha256", "size"}, label)
    path = _canonical_path(value.get("path"), f"{label}.path")
    digest = value.get("sha256")
    size = value.get("size")
    if (
        not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
    ):
        raise ValueError(f"{label} digest/size is malformed")
    if expected_path is not None and path != _canonical_path(
        expected_path, f"{label} expected path"
    ):
        raise ValueError(f"{label} path differs from retained authority")
    if expected_raw is not None and (digest != _sha(expected_raw) or size != len(expected_raw)):
        raise ValueError(f"{label} digest differs from retained bytes")
    return value


def no_pre_run_raw_bytes() -> bytes:
    """Return the signed sentinel used by retrospective packages."""

    return _canonical_bytes({"schema_id": NO_PRE_RUN_RAW_SCHEMA, "scope": RETROSPECTIVE_SCOPE})


def production_ladder_parameters(
    *, target_efl_mm: float, fnum_target: float, work_dir: Path
) -> dict[str, object]:
    """Return the exact effective parameters used by identity and the runner."""

    for value, label in ((target_efl_mm, "target EFL"), (fnum_target, "target F-number")):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not (float(value) > 0):
            raise ValueError(f"production Stage B {label} must be positive")
    return {
        "target_efl_mm": float(target_efl_mm),
        "fnum_target": float(fnum_target),
        "target_imh_mm": None,
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
        "work_dir": str(work_dir.resolve()),
    }


def _runner_sources() -> dict[str, object]:
    paths = sorted((_ROOT / "app" / "core").rglob("*.py"))
    paths.extend(path for path in (_ROOT / "pyproject.toml", _ROOT / "uv.lock") if path.is_file())
    files = {
        str(path.relative_to(_ROOT)).replace("\\", "/"): {
            "sha256": _sha(path.read_bytes()),
            "size": path.stat().st_size,
        }
        for path in paths
    }
    return {"files": files, "aggregate_sha256": _sha(_canonical_bytes(files))}


def _python_environment() -> dict[str, object]:
    distributions = sorted(
        f"{(dist.metadata.get('Name') or '').lower()}=={dist.version}"
        for dist in importlib.metadata.distributions()
    )
    payload = {
        "executable": _descriptor(Path(sys.executable)),
        "version": sys.version,
        "implementation": sys.implementation.name,
        "platform": {"os_name": os.name, "sys_platform": sys.platform},
        "installed_distributions": distributions,
    }
    return {**payload, "aggregate_sha256": _sha(_canonical_bytes(payload))}


def _identity(
    *,
    config: StageBAuthorityConfig,
    request: StageBAuthorityRequest,
    work_dir: Path,
    lock_authority: Mapping[str, object],
) -> dict[str, object]:
    parameters = production_ladder_parameters(
        target_efl_mm=request.target_efl_mm,
        fnum_target=request.fnum_target,
        work_dir=work_dir,
    )
    index_record = json.loads(_canonical_bytes(dict(request.index_record)))
    if not isinstance(index_record, dict):
        raise ValueError("Stage B index record must be a JSON object")
    job = {
        "case_id": request.case_id,
        "rationale": request.rationale,
        "index_record": index_record,
        "scenario": request.scenario,
        "native_image_height_mm": request.native_image_height_mm,
    }
    return {
        "runner_kind": PRODUCTION_RUNNER_KIND,
        "lock_authority": dict(lock_authority),
        "job": job,
        "job_sha256": _sha(_canonical_bytes(job)),
        "source": _descriptor(request.source_zmx),
        "codev": {**_descriptor(config.executable), "version": _codev_version(config)},
        "official_macro": _descriptor(config.official_macro),
        "runner_sources": _runner_sources(),
        "python_environment": _python_environment(),
        "parameters": parameters,
    }


def _codev_version(config: StageBAuthorityConfig) -> str:
    if config._codev_version_for_tests is not None:
        if not config._codev_version_for_tests:
            raise ValueError("test CODE V version override may not be empty")
        return config._codev_version_for_tests
    version = _read_windows_file_version(config.executable.resolve(strict=True))
    if not version:
        raise ValueError("official CODE V executable has no readable file version")
    return version


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path.resolve(strict=True), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_move(source: Path, destination: Path, *, replace: bool) -> None:
    if os.name != "nt":
        if replace:
            os.replace(source, destination)
        else:
            os.link(source, destination)
            os.unlink(source)
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


def _exclusive_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".exclusive-{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _durable_move(temporary, path, replace=False)
    finally:
        temporary.unlink(missing_ok=True)


def _exclusive_json(path: Path, payload: object) -> None:
    _exclusive_bytes(path, _canonical_bytes(payload))


@dataclass(frozen=True)
class StageBAuthorityConfig:
    """Filesystem and execution authority supplied when opening a session."""

    authority_root: Path
    output_lock_root: Path
    p18_lock_root: Path
    executable: Path
    official_macro: Path = OFFICIAL_MACRO
    _codev_version_for_tests: str | None = None
    recover_stale_output_lock: bool = False
    recover_stale_p18_lock: bool = False
    allow_existing_authority_root: bool = False


@dataclass(frozen=True)
class StageBAuthorityRequest:
    """One closed production Stage B request."""

    case_id: str
    rationale: str
    index_record: Mapping[str, object]
    source_zmx: Path
    accepted_output_path: Path
    scenario: str
    target_efl_mm: float
    fnum_target: float
    native_image_height_mm: float | None


@dataclass(frozen=True)
class StageBAuthorityOutcome:
    """Retained result of one session run; no quality verdict is implied."""

    status: Literal["accepted", "not-accepted"]
    case_id: str
    attempt_dir: Path
    intent_path: Path
    raw_result_path: Path
    final_result_path: Path | None
    manifest_path: Path | None
    terminal_path: Path | None
    accepted_zmx: Path | None
    result: dict[str, object]


@dataclass(frozen=True)
class StageBAuthorityBinding:
    scope: Literal["pre-run-bound", "retrospective-current-state-adoption"]
    pre_run_bound: bool
    record_path: str
    record_sha256: str
    raw_result_path: str | None
    raw_result_sha256: str | None
    entry: dict[str, object]


class StageBAuthoritySession:
    """Open authority session; :meth:`run` is the sole machine entrypoint."""

    def __init__(
        self,
        config: StageBAuthorityConfig,
        *,
        runner: Callable[..., dict[str, object]],
        lock_authority: Mapping[str, object],
        lock_owner_ids: Mapping[str, object],
    ) -> None:
        self.config = config
        self._runner = runner
        self._lock_authority = dict(lock_authority)
        self._lock_owner_ids = dict(lock_owner_ids)
        self._open = True

    def close(self) -> None:
        self._open = False

    def run(self, request: StageBAuthorityRequest) -> StageBAuthorityOutcome:
        if not self._open:
            raise RuntimeError("Stage B authority session is closed")
        if _SAFE_ID.fullmatch(request.case_id) is None:
            raise ValueError("unsafe Stage B authority case identity")
        if not request.rationale:
            raise ValueError("Stage B authority rationale is required")
        source = request.source_zmx.resolve(strict=True)
        accepted_output = request.accepted_output_path.resolve()
        if accepted_output.exists():
            raise FileExistsError(f"Stage B accepted artifact collision: {accepted_output}")
        attempts_root = self.config.authority_root / "attempts"
        attempts_root.mkdir(parents=True, exist_ok=True)
        incomplete = [
            path
            for path in attempts_root.iterdir()
            if path.is_dir()
            and not (path / "stageb-manifest.json").is_file()
            and not (path / "terminal.json").is_file()
        ]
        if incomplete:
            raise RuntimeError(
                "incomplete Stage B authority attempt requires explicit forensic recovery: "
                + ", ".join(str(path) for path in incomplete)
            )
        attempt_id = uuid4().hex
        attempt_dir = attempts_root / attempt_id
        attempt_dir.mkdir(exist_ok=False)
        intent_path = attempt_dir / "intent.json"
        raw_path = attempt_dir / "raw-ladder-result.json"
        final_path = attempt_dir / "stageb-ladder-result.json"
        manifest_path = attempt_dir / "stageb-manifest.json"
        terminal_path = attempt_dir / "terminal.json"
        work_dir = attempt_dir / "runner-work"
        work_dir.mkdir(exist_ok=False)
        identity = _identity(
            config=self.config,
            request=request,
            work_dir=work_dir,
            lock_authority=self._lock_authority,
        )
        intent = {
            "schema_id": CACHE_INTENT_SCHEMA,
            "scope": "pre-run-intent",
            "attempt_id": attempt_id,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "identity": identity,
            "lock_owner_ids": self._lock_owner_ids,
        }
        _exclusive_json(intent_path, intent)
        parameters = identity["parameters"]
        assert isinstance(parameters, dict)
        result = self._runner(
            source_zmx=source,
            work_dir=work_dir,
            target_efl_mm=parameters["target_efl_mm"],
            fnum_target=parameters["fnum_target"],
            target_imh_mm=parameters["target_imh_mm"],
            stage=parameters["stage"],
            rung_count=parameters["rung_count"],
            fnum_tolerance_pct=parameters["fnum_tolerance_pct"],
            vig_ladder=tuple(parameters["vig_ladder"]),
            ray_retry_vig_ladder=tuple(parameters["ray_retry_vig_ladder"]),
            num_fields=parameters["num_fields"],
            extra_dof=parameters["extra_dof"],
            glass_bounds_nd_vd=parameters["glass_bounds_nd_vd"],
            executable=self.config.executable.resolve(strict=True),
            timeout_seconds=parameters["timeout_seconds"],
            platform_name=parameters["platform_name"],
            emit_optimized_zmx=parameters["emit_optimized_zmx"],
        )
        normalized = _strict_json(_canonical_bytes(dict(result)), "Stage B raw result")
        _validate_ladder_shape(normalized, label="Stage B raw result")
        raw_bytes = _canonical_bytes(normalized)
        _exclusive_bytes(raw_path, raw_bytes)
        post_identity = _identity(
            config=self.config,
            request=request,
            work_dir=work_dir,
            lock_authority=self._lock_authority,
        )
        if post_identity != identity:
            raise RuntimeError("Stage B authority identity changed during the machine run")
        accepted_final = normalized.get("accepted_final")
        from app.core.orchestration.candidate import (
            fnum_ladder_evidence_from_result,
        )

        ladder_evidence = fnum_ladder_evidence_from_result(normalized)
        if not (
            normalized.get("schema") == "atelier-p15-fno-ladder-v1"
            and normalized.get("stage") == "B"
            and normalized.get("target_achieved") is True
            and isinstance(accepted_final, dict)
            and accepted_final.get("status") == "measured"
            and accepted_final.get("fno_param_achieved") is True
            and accepted_final.get("aut_converged") is True
            and accepted_final.get("ray_traceable") is True
            and ladder_evidence is not None
            and ladder_evidence.target_achieved is True
            and ladder_evidence.accepted_final is not None
        ):
            _exclusive_json(
                terminal_path,
                {
                    "schema_id": "atelier-stageb-authority-terminal-v1",
                    "status": "not-accepted",
                    "case_id": request.case_id,
                    "attempt_id": attempt_id,
                    "intent_sha256": _sha(intent_path.read_bytes()),
                    "raw_result_sha256": _sha(raw_bytes),
                    "post_run_identity_sha256": _sha(_canonical_bytes(post_identity)),
                    "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
                },
            )
            return StageBAuthorityOutcome(
                status="not-accepted",
                case_id=request.case_id,
                attempt_dir=attempt_dir,
                intent_path=intent_path,
                raw_result_path=raw_path,
                final_result_path=None,
                manifest_path=None,
                terminal_path=terminal_path,
                accepted_zmx=None,
                result=normalized,
            )
        emitted_raw = accepted_final.get("optimized_zmx_path")
        if not isinstance(emitted_raw, str) or not emitted_raw:
            raise ValueError("accepted Stage B result lacks emitted ZMX")
        emitted = Path(emitted_raw).resolve(strict=True)
        emitted_bytes = emitted.read_bytes()
        _exclusive_bytes(accepted_output, emitted_bytes)
        accepted_bytes = accepted_output.read_bytes()
        if accepted_bytes != emitted_bytes:
            raise RuntimeError("published Stage B accepted bytes differ from runner output")
        derived = _strict_json(raw_bytes, "Stage B derived source")
        _rebind_accepted_path(derived, str(accepted_output))
        provenance = {
            "scope": PRE_RUN_SCOPE,
            "pre_run_bound": True,
            "intent_sha256": _sha(intent_path.read_bytes()),
            "raw_result_sha256": _sha(raw_bytes),
            "post_run_identity_sha256": _sha(_canonical_bytes(post_identity)),
            "accepted_artifact": {
                "raw_emitted": _descriptor(emitted, emitted_bytes),
                "published": _descriptor(accepted_output, accepted_bytes),
            },
        }
        derived["cache_provenance"] = provenance
        final_bytes = _canonical_bytes(derived)
        _exclusive_bytes(final_path, final_bytes)
        source_bytes = source.read_bytes()
        entry = {
            "case_id": request.case_id,
            "scenario": request.scenario,
            "source_zmx": str(source),
            "source_zmx_sha256": _sha(source_bytes),
            "accepted_zmx": str(accepted_output),
            "accepted_zmx_sha256": _sha(accepted_bytes),
            "target_efl_mm": derived.get("target_efl_mm"),
            "native_image_height_mm": request.native_image_height_mm,
            "fnum_target": derived.get("fnum_target"),
            "accepted_final": derived["accepted_final"],
            "ladder_result": str(final_path),
            "ladder_result_sha256": _sha(final_bytes),
            "raw_ladder_result_path": str(raw_path),
            "raw_ladder_result_sha256": _sha(raw_bytes),
            "cache_scope": PRE_RUN_SCOPE,
            "cache_record_path": str(intent_path),
            "cache_record_sha256": _sha(intent_path.read_bytes()),
            "pre_run_bound": True,
        }
        manifest = {
            "schema_id": STAGEB_MANIFEST_SCHEMA,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "required_count": 1,
            "accepted_count": 1,
            "complete": True,
            "accepted": [entry],
            "cache_scope_counts": {PRE_RUN_SCOPE: 1},
            "all_inputs_pre_run_bound": True,
            "expert_verdict": None,
            "truth_notice": STAGEB_TRUTH_NOTICE,
        }
        manifest_bytes = _canonical_bytes(manifest)
        validate_retained_stageb_authority(
            manifest_raw=manifest_bytes,
            ladder_raw=final_bytes,
            raw_ladder_raw=raw_bytes,
            cache_record_raw=intent_path.read_bytes(),
            case_id=request.case_id,
            accepted_zmx_raw=accepted_bytes,
            verify_external_paths=True,
        )
        _exclusive_bytes(manifest_path, manifest_bytes)
        return StageBAuthorityOutcome(
            status="accepted",
            case_id=request.case_id,
            attempt_dir=attempt_dir,
            intent_path=intent_path,
            raw_result_path=raw_path,
            final_result_path=final_path,
            manifest_path=manifest_path,
            terminal_path=None,
            accepted_zmx=accepted_output,
            result=derived,
        )


def _normalized_lock_root(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


@contextmanager
def _open_stageb_authority(
    config: StageBAuthorityConfig,
    *,
    runner: Callable[..., dict[str, object]],
) -> Iterator[StageBAuthoritySession]:
    lock_roots = {
        _normalized_lock_root(config.output_lock_root),
        _normalized_lock_root(config.p18_lock_root),
        _normalized_lock_root(CODEV_LOCK_ROOT),
    }
    if len(lock_roots) != 3:
        raise ValueError("Stage B output, P18, and CODE V lock roots must be distinct")
    with ExitStack() as stack:
        output_owner = stack.enter_context(
            batch_runner_lock(
                config.output_lock_root,
                recover_stale=config.recover_stale_output_lock,
                details={"purpose": "stageb-authority-output"},
            )
        )
        p18_owner = stack.enter_context(
            batch_runner_lock(
                config.p18_lock_root,
                recover_stale=config.recover_stale_p18_lock,
                details={"purpose": "stageb-authority-p18-window"},
            )
        )
        root = config.authority_root.resolve()
        root.parent.mkdir(parents=True, exist_ok=True)
        if config.allow_existing_authority_root:
            root.mkdir(parents=True, exist_ok=True)
        else:
            root.mkdir(exist_ok=False)
        normalized = StageBAuthorityConfig(
            authority_root=root,
            output_lock_root=config.output_lock_root.resolve(),
            p18_lock_root=config.p18_lock_root.resolve(),
            executable=config.executable.resolve(strict=True),
            official_macro=config.official_macro.resolve(strict=True),
            _codev_version_for_tests=config._codev_version_for_tests,
            recover_stale_output_lock=config.recover_stale_output_lock,
            recover_stale_p18_lock=config.recover_stale_p18_lock,
            allow_existing_authority_root=True,
        )
        lock_authority = {
            "mode": "pre-run-held",
            "order": ["output", "p18-global", "codev-per-call"],
            "roots": {
                "output": str(config.output_lock_root.resolve()),
                "p18_global": str(config.p18_lock_root.resolve()),
                "p18_archive": None,
                "codev": str(CODEV_LOCK_ROOT.resolve()),
            },
        }
        lock_owner_ids = {
            "output": output_owner["lock_id"],
            "p18_global": p18_owner["lock_id"],
            "p18_archive": None,
            "codev": None,
        }
        session = StageBAuthoritySession(
            normalized,
            runner=runner,
            lock_authority=lock_authority,
            lock_owner_ids=lock_owner_ids,
        )
        try:
            yield session
        finally:
            session.close()


def open_stageb_authority(
    config: StageBAuthorityConfig,
) -> Iterator[StageBAuthoritySession]:
    """Open the official production authority session."""

    if config._codev_version_for_tests is not None:
        raise ValueError("production Stage B authority forbids test version overrides")
    if (
        config.executable.resolve(strict=True) != OFFICIAL_EXECUTABLE.resolve(strict=True)
        or config.official_macro.resolve(strict=True) != OFFICIAL_MACRO.resolve(strict=True)
        or config.p18_lock_root.resolve() != P18_GLOBAL_WINDOW_ROOT.resolve()
    ):
        raise ValueError(
            "production Stage B authority requires the official toolchain and global P18 window"
        )
    executable_raw = config.executable.read_bytes()
    macro_raw = config.official_macro.read_bytes()
    if (
        _sha(executable_raw) != TRUSTED_CODEV_SHA256
        or len(executable_raw) != TRUSTED_CODEV_SIZE_BYTES
        or _sha(macro_raw) != TRUSTED_MACRO_SHA256
        or _codev_version(config) != TRUSTED_CODEV_FILE_VERSION
    ):
        raise ValueError("production Stage B authority toolchain bytes/version are not trusted")
    return _open_stageb_authority(config, runner=run_codev_target_fno_ladder)


def _open_stageb_authority_for_tests(
    config: StageBAuthorityConfig,
    runner: Callable[..., dict[str, object]],
) -> Iterator[StageBAuthoritySession]:
    """Private adapter seam for offline tests; never used by production callers."""

    return _open_stageb_authority(config, runner=runner)


def _validate_lock_authority(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Stage B lock authority is missing")
    _closed_keys(
        value,
        {"mode", "order", "roots"},
        "Stage B lock authority",
    )
    roots = value.get("roots")
    if not isinstance(roots, dict):
        raise ValueError("Stage B lock roots are malformed")
    _closed_keys(
        roots,
        {"output", "p18_global", "p18_archive", "codev"},
        "Stage B lock roots",
    )
    canonical_roots = {
        name: _canonical_path(path, f"Stage B {name} lock root")
        for name, path in roots.items()
        if path is not None
    }
    archive_root = roots.get("p18_archive")
    mode = value.get("mode")
    if (
        value.get("order")
        != (
            ["output", "p18-global", "codev-per-call"]
            if archive_root is None
            else ["output", "p18-global", "p18-archive", "codev-per-call"]
        )
        or canonical_roots["p18_global"] != str(P18_GLOBAL_WINDOW_ROOT.resolve())
        or canonical_roots["codev"] != str(CODEV_LOCK_ROOT.resolve())
        or len({os.path.normcase(path) for path in canonical_roots.values()})
        != len(canonical_roots)
    ):
        raise ValueError("Stage B lock authority differs from the closed global window")
    if mode not in {"pre-run-held", "retrospective-observation"}:
        raise ValueError("Stage B lock authority mode is unsupported")
    return value


def _validate_lock_owner_ids(value: object, *, archive_required: bool) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Stage B pre-run lock owner observation is missing")
    _closed_keys(
        value,
        {"output", "p18_global", "p18_archive", "codev"},
        "Stage B pre-run lock owner observation",
    )
    for name in ("output", "p18_global"):
        owner_id = value.get(name)
        if not isinstance(owner_id, str) or _ATTEMPT_ID.fullmatch(owner_id) is None:
            raise ValueError("Stage B pre-run lock owner ID is malformed")
    archive_owner = value.get("p18_archive")
    if archive_required:
        if not isinstance(archive_owner, str) or _ATTEMPT_ID.fullmatch(archive_owner) is None:
            raise ValueError("Stage B archive lock owner ID is malformed")
    elif archive_owner is not None:
        raise ValueError("production Stage B may not claim an archive lock owner")
    if value.get("codev") is not None:
        raise ValueError("pre-run intent may not claim the inner per-call CODE V owner")
    return value


def _validate_p18_terminal_authority(
    value: object,
    *,
    verify_external_paths: bool,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("P18 terminal authority is missing")
    _closed_keys(
        value,
        {
            "archive_root",
            "lock_file",
            "terminal_batch",
            "batch_id",
            "status",
            "target_count",
        },
        "P18 terminal authority",
    )
    archive_root = _canonical_path(value.get("archive_root"), "P18 archive root")
    if (
        value.get("batch_id") != _P18_REQUIRED_BATCH_ID
        or value.get("status") != "completed"
        or value.get("target_count") != _P18_REQUIRED_TARGET_COUNT
    ):
        raise ValueError("P18 terminal authority differs from the required completed batch")
    lock_path = Path(archive_root) / ".p18-runner.lock"
    batch_path = Path(archive_root) / _P18_REQUIRED_BATCH_ID / "batch.json"
    lock_descriptor = value.get("lock_file")
    if (
        not isinstance(lock_descriptor, dict)
        or set(lock_descriptor) != {"path", "protocol", "content_observed"}
        or _canonical_path(lock_descriptor.get("path"), "P18 archive lock file")
        != str(lock_path.resolve(strict=False))
        or lock_descriptor.get("protocol") != "atelier-batch-runner-os-byte-range-v1"
        or lock_descriptor.get("content_observed") is not False
    ):
        raise ValueError("P18 archive lock authority is malformed")
    batch_descriptor = _validate_descriptor(
        value.get("terminal_batch"),
        "P18 terminal batch ledger",
        expected_path=str(batch_path.resolve(strict=False)),
    )
    if verify_external_paths:
        if not lock_path.resolve(strict=True).is_file():
            raise ValueError("P18 lock authority file disappeared")
        for descriptor, label in ((batch_descriptor, "P18 batch ledger"),):
            raw = Path(str(descriptor["path"])).resolve(strict=True).read_bytes()
            if descriptor.get("sha256") != _sha(raw) or descriptor.get("size") != len(raw):
                raise ValueError(f"{label} changed after adoption")
        batch = _strict_json(batch_path.read_bytes(), "P18 terminal batch ledger")
        if (
            set(batch)
            != {
                "batch_id",
                "created_at",
                "updated_at",
                "target_source",
                "target_count",
                "status",
                "engine",
                "notes",
            }
            or batch.get("batch_id") != _P18_REQUIRED_BATCH_ID
            or batch.get("status") != "completed"
            or batch.get("target_count") != _P18_REQUIRED_TARGET_COUNT
            or batch.get("engine") != "real"
        ):
            raise ValueError("P18 terminal batch ledger content is not the prerequisite")
    return value


def _validate_identity(
    identity: object,
    *,
    case_id: str,
    entry: Mapping[str, object],
    ladder: Mapping[str, object],
    expected_work_dir: Path | None,
) -> dict[str, object]:
    if not isinstance(identity, dict):
        raise ValueError("Stage B current identity must be an object")
    _closed_keys(
        identity,
        {
            "runner_kind",
            "lock_authority",
            "job",
            "job_sha256",
            "source",
            "codev",
            "official_macro",
            "runner_sources",
            "python_environment",
            "parameters",
        },
        "Stage B current identity",
    )
    job = identity.get("job")
    parameters = identity.get("parameters")
    runner_kind = identity.get("runner_kind")
    lock_authority = _validate_lock_authority(identity.get("lock_authority"))
    if lock_authority.get("mode") != (
        "pre-run-held" if expected_work_dir is not None else "retrospective-observation"
    ):
        raise ValueError("Stage B lock mode contradicts the cache scope")
    if not isinstance(job, dict) or not isinstance(parameters, dict):
        raise ValueError("Stage B job/parameters are missing")
    _closed_keys(
        job,
        {
            "case_id",
            "rationale",
            "index_record",
            "scenario",
            "native_image_height_mm",
        },
        "Stage B job",
    )
    if runner_kind not in _REQUIRED_RUNNER_SOURCES:
        raise ValueError("Stage B runner kind is unsupported")
    lock_roots = lock_authority.get("roots")
    assert isinstance(lock_roots, dict)
    if (runner_kind == PRODUCTION_RUNNER_KIND and lock_roots.get("p18_archive") is not None) or (
        runner_kind == BATCH_RUNNER_KIND and lock_roots.get("p18_archive") is None
    ):
        raise ValueError("Stage B runner kind contradicts its lock roots")
    expected_parameter_keys = (
        _PRODUCTION_PARAMETER_KEYS if expected_work_dir is not None else _BASE_PARAMETER_KEYS
    )
    if set(parameters) != expected_parameter_keys:
        raise ValueError("Stage B parameters differ from the closed schema")
    index_record = job.get("index_record")
    if not isinstance(index_record, dict):
        raise ValueError("Stage B index record is missing")
    target_efl = parameters.get("target_efl_mm")
    fnum_target = parameters.get("fnum_target")
    target_imh = parameters.get("target_imh_mm")
    if (
        not isinstance(target_efl, (int, float))
        or isinstance(target_efl, bool)
        or float(target_efl) <= 0
        or not isinstance(fnum_target, (int, float))
        or isinstance(fnum_target, bool)
        or float(fnum_target) <= 0
        or (
            target_imh is not None
            and (
                not isinstance(target_imh, (int, float))
                or isinstance(target_imh, bool)
                or float(target_imh) <= 0
            )
        )
        or parameters.get("stage") != "B"
        or parameters.get("rung_count") != 3
        or parameters.get("fnum_tolerance_pct") != FNUM_TOLERANCE_PCT
        or parameters.get("vig_ladder") != list(VIG_LADDER)
        or parameters.get("ray_retry_vig_ladder") != list(RAY_RETRY_VIG_LADDER)
        or parameters.get("num_fields") != 3
        or parameters.get("extra_dof") != "both"
        or parameters.get("glass_bounds_nd_vd") is not None
        or parameters.get("emit_optimized_zmx") is not True
        or parameters.get("timeout_seconds") != 180.0
        or parameters.get("platform_name") != os.name
        or (runner_kind == PRODUCTION_RUNNER_KIND and parameters.get("target_imh_mm") is not None)
        or (
            runner_kind == BATCH_RUNNER_KIND
            and parameters.get("target_imh_mm") != job.get("native_image_height_mm")
        )
    ):
        raise ValueError("Stage B effective parameters differ from the closed contract")
    if expected_work_dir is not None and _canonical_path(
        parameters.get("work_dir"), "Stage B runner work directory"
    ) != str(expected_work_dir.resolve()):
        raise ValueError("Stage B runner work directory differs from its attempt")
    scenario = job.get("scenario")
    native_image_height = job.get("native_image_height_mm")
    native_image_height_is_positive = (
        isinstance(native_image_height, (int, float))
        and not isinstance(native_image_height, bool)
        and math.isfinite(float(native_image_height))
        and float(native_image_height) > 0
    )
    native_image_height_is_valid = native_image_height_is_positive or (
        runner_kind == PRODUCTION_RUNNER_KIND and native_image_height is None
    )
    if (
        job.get("case_id") != case_id
        or not isinstance(job.get("rationale"), str)
        or not job.get("rationale")
        or scenario not in _SCENARIOS
        or not native_image_height_is_valid
        or identity.get("job_sha256") != _sha(_canonical_bytes(job))
        or index_record.get("case_id") != case_id
        or index_record.get("source_zmx") != ladder.get("source_zmx")
        or Path(str(entry.get("source_zmx"))).name != ladder.get("source_zmx")
        or index_record.get("scenario") != scenario
        or entry.get("scenario") != scenario
        or index_record.get("efl_mm") != parameters.get("target_efl_mm")
        or index_record.get("image_height_mm") != native_image_height
        or entry.get("native_image_height_mm") != native_image_height
        or parameters.get("target_efl_mm") != ladder.get("target_efl_mm")
        or parameters.get("target_efl_mm") != entry.get("target_efl_mm")
        or parameters.get("fnum_target") != ladder.get("fnum_target")
        or parameters.get("fnum_target") != entry.get("fnum_target")
        or parameters.get("stage") != ladder.get("stage")
        or parameters.get("rung_count") != ladder.get("rung_count")
        or parameters.get("fnum_tolerance_pct") != ladder.get("fnum_tolerance_pct")
        or parameters.get("vig_ladder") != ladder.get("vig_ladder")
        or parameters.get("ray_retry_vig_ladder") != ladder.get("ray_retry_vig_ladder")
        or parameters.get("num_fields") != ladder.get("num_fields")
        or parameters.get("extra_dof") != ladder.get("extra_dof")
    ):
        raise ValueError("Stage B identity claims differ from retained authority")
    source = _validate_descriptor(
        identity.get("source"), "Stage B source", expected_path=entry.get("source_zmx")
    )
    if source.get("sha256") != entry.get("source_zmx_sha256"):
        raise ValueError("Stage B source digest differs from retained manifest")
    codev = identity.get("codev")
    if not isinstance(codev, dict) or set(codev) != {"path", "sha256", "size", "version"}:
        raise ValueError("Stage B CODE V identity is malformed")
    codev_descriptor = _validate_descriptor(
        {key: codev[key] for key in ("path", "sha256", "size")}, "CODE V"
    )
    version = codev.get("version")
    if (
        codev_descriptor.get("path") != str(OFFICIAL_EXECUTABLE.resolve(strict=False))
        or codev_descriptor.get("sha256") != TRUSTED_CODEV_SHA256
        or codev_descriptor.get("size") != TRUSTED_CODEV_SIZE_BYTES
        or not isinstance(version, str)
        or version != TRUSTED_CODEV_FILE_VERSION
    ):
        raise ValueError("Stage B CODE V identity differs from the hard-pinned toolchain")
    macro_descriptor = _validate_descriptor(
        identity.get("official_macro"), "Stage B official macro"
    )
    if (
        macro_descriptor.get("path") != str(OFFICIAL_MACRO.resolve(strict=False))
        or macro_descriptor.get("sha256") != TRUSTED_MACRO_SHA256
    ):
        raise ValueError("Stage B official macro differs from the hard-pinned toolchain")
    sources = identity.get("runner_sources")
    if not isinstance(sources, dict) or set(sources) != {"files", "aggregate_sha256"}:
        raise ValueError("Stage B runner-source identity is malformed")
    files = sources.get("files")
    required_sources = _REQUIRED_RUNNER_SOURCES[str(runner_kind)]
    if not isinstance(files, dict) or not required_sources.issubset(files):
        raise ValueError("Stage B runner-source identity omits required semantics")
    for name, descriptor in files.items():
        if (
            not isinstance(name, str)
            or not name
            or "\\" in name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or not isinstance(descriptor, dict)
            or set(descriptor) != {"sha256", "size"}
            or _SHA256.fullmatch(str(descriptor.get("sha256"))) is None
            or not isinstance(descriptor.get("size"), int)
            or isinstance(descriptor.get("size"), bool)
            or int(descriptor["size"]) < 0
        ):
            raise ValueError("Stage B runner-source descriptor is malformed")
    if sources.get("aggregate_sha256") != _sha(_canonical_bytes(files)):
        raise ValueError("Stage B runner-source aggregate is invalid")
    python_environment = identity.get("python_environment")
    if not isinstance(python_environment, dict) or "aggregate_sha256" not in python_environment:
        raise ValueError("Stage B Python identity is missing")
    python_payload = {
        key: value for key, value in python_environment.items() if key != "aggregate_sha256"
    }
    if python_environment.get("aggregate_sha256") != _sha(_canonical_bytes(python_payload)):
        raise ValueError("Stage B Python identity aggregate is invalid")
    return identity


def validate_retained_stageb_authority(
    *,
    manifest_raw: bytes,
    ladder_raw: bytes,
    raw_ladder_raw: bytes | None,
    cache_record_raw: bytes,
    case_id: str,
    accepted_zmx_raw: bytes,
    verify_external_paths: bool,
) -> StageBAuthorityBinding:
    """Revalidate retained Stage B authority bytes without trusting claims."""

    manifest = _strict_json(manifest_raw, "Stage B manifest")
    ladder = _strict_json(ladder_raw, "Stage B final ladder")
    entries = manifest.get("accepted")
    if (
        set(manifest) not in (_MANIFEST_COMMON_KEYS, _MANIFEST_BATCH_KEYS)
        or manifest.get("schema_id") != STAGEB_MANIFEST_SCHEMA
        or manifest.get("complete") is not True
        or manifest.get("expert_verdict") is not None
        or not isinstance(manifest.get("created_at"), str)
        or not manifest.get("created_at")
        or manifest.get("truth_notice") != STAGEB_TRUTH_NOTICE
        or not isinstance(manifest.get("required_count"), int)
        or isinstance(manifest.get("required_count"), bool)
        or not isinstance(manifest.get("accepted_count"), int)
        or isinstance(manifest.get("accepted_count"), bool)
        or not isinstance(entries, list)
        or manifest.get("required_count") != len(entries)
        or manifest.get("accepted_count") != len(entries)
        or not entries
    ):
        raise ValueError("Stage B manifest has not closed its accepted gate")
    if any(not isinstance(item, dict) or set(item) != _MANIFEST_ENTRY_KEYS for item in entries):
        raise ValueError("Stage B manifest accepted entry differs from the closed schema")
    case_ids = [str(item.get("case_id")) for item in entries]
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Stage B manifest accepted case identities are not unique")
    if set(manifest) == _MANIFEST_BATCH_KEYS:
        outcomes = manifest.get("outcomes")
        incomplete_attempts = manifest.get("incomplete_attempts")
        if (
            len(entries) != 8
            or not isinstance(outcomes, list)
            or any(
                not isinstance(item, dict) or set(item) != _BATCH_OUTCOME_KEYS for item in outcomes
            )
            or not isinstance(incomplete_attempts, list)
            or any(
                not isinstance(item, dict) or set(item) != _INCOMPLETE_ATTEMPT_KEYS
                for item in incomplete_attempts
            )
        ):
            raise ValueError("Stage B batch manifest nested records are not closed")
        outcome_ids = [str(item.get("case_id")) for item in outcomes]
        if len(set(outcome_ids)) != len(outcome_ids):
            raise ValueError("Stage B batch outcome case identities are not unique")
        accepted_by_case = {str(item["case_id"]): item for item in entries}
        accepted_outcome_ids: set[str] = set()
        for item in outcomes:
            outcome_case = item.get("case_id")
            accepted_flag = item.get("accepted")
            reason = item.get("reason")
            outcome_fnum = item.get("fnum_target")
            if (
                not isinstance(outcome_case, str)
                or _SAFE_ID.fullmatch(outcome_case) is None
                or not isinstance(accepted_flag, bool)
                or not isinstance(outcome_fnum, (int, float))
                or isinstance(outcome_fnum, bool)
                or not math.isfinite(float(outcome_fnum))
                or float(outcome_fnum) <= 0
                or item.get("cache_scope") not in {PRE_RUN_SCOPE, RETROSPECTIVE_SCOPE}
                or item.get("pre_run_bound") is not (item.get("cache_scope") == PRE_RUN_SCOPE)
                or _SHA256.fullmatch(str(item.get("cache_record_sha256"))) is None
                or _SHA256.fullmatch(str(item.get("result_sha256"))) is None
            ):
                raise ValueError("Stage B batch outcome binding is malformed")
            _canonical_path(item.get("cache_record_path"), "Stage B outcome cache record")
            if accepted_flag:
                accepted_outcome_ids.add(outcome_case)
                entry_for_outcome = accepted_by_case.get(outcome_case)
                if (
                    reason is not None
                    or entry_for_outcome is None
                    or outcome_fnum != entry_for_outcome.get("fnum_target")
                    or item.get("cache_scope") != entry_for_outcome.get("cache_scope")
                    or item.get("cache_record_path") != entry_for_outcome.get("cache_record_path")
                    or item.get("cache_record_sha256")
                    != entry_for_outcome.get("cache_record_sha256")
                    or item.get("result_sha256") != entry_for_outcome.get("ladder_result_sha256")
                ):
                    raise ValueError("Stage B accepted outcome differs from its input binding")
            elif not isinstance(reason, str) or not reason:
                raise ValueError("Stage B rejected outcome requires an honest reason")
            if isinstance(reason, str) and re.search(
                r"(?i)(\[expert\]|\bverdict\b|\byield\b|\bqualified\b|"
                r"production[- ]usable|\bpass\b)",
                reason,
            ):
                raise ValueError("Stage B outcome reason contains a forbidden verdict claim")
        if accepted_outcome_ids != set(accepted_by_case):
            raise ValueError("Stage B outcomes differ from the accepted case set")
        for item in incomplete_attempts:
            receipt = item.get("recovery_receipt")
            receipt_sha = item.get("recovery_receipt_sha256")
            if (
                not isinstance(receipt, str)
                or not receipt
                or not isinstance(receipt_sha, str)
                or _SHA256.fullmatch(receipt_sha) is None
            ):
                raise ValueError(
                    "complete Stage B manifest contains an unrecovered incomplete attempt"
                )
            attempt_path = _canonical_path(item.get("path"), "Stage B incomplete attempt path")
            case_id_value = item.get("case_id")
            attempt_id_value = item.get("attempt_id")
            if (
                not isinstance(case_id_value, str)
                or _SAFE_ID.fullmatch(case_id_value) is None
                or not isinstance(attempt_id_value, str)
                or _ATTEMPT_ID.fullmatch(attempt_id_value) is None
                or Path(attempt_path).name != attempt_id_value
                or Path(attempt_path).parent.parent.name != case_id_value
                or item.get("classification")
                not in {"raw-without-final", "intent-only", "missing-intent"}
            ):
                raise ValueError("Stage B incomplete attempt identity is malformed")
            if verify_external_paths:
                receipt_raw = Path(receipt).resolve(strict=True).read_bytes()
                if _sha(receipt_raw) != receipt_sha:
                    raise ValueError("Stage B recovery receipt bytes changed")
                recovery = _strict_json(receipt_raw, "Stage B recovery receipt")
                recovery_snapshot = recovery.get("attempt_snapshot")
                if (
                    set(recovery)
                    != {
                        "schema_id",
                        "recovered_at",
                        "case_id",
                        "attempt_id",
                        "classification",
                        "attempt_snapshot",
                        "old_identity",
                        "current_identity",
                        "processes_zero",
                        "lock_roots",
                        "lock_ids",
                        "p18_terminal_authority",
                    }
                    or recovery.get("schema_id") != "atelier-stagec-stageb-attempt-recovery-v1"
                    or recovery.get("case_id") != case_id_value
                    or recovery.get("attempt_id") != attempt_id_value
                    or recovery.get("classification") != item.get("classification")
                    or recovery.get("processes_zero") is not True
                    or not isinstance(recovery_snapshot, dict)
                    or set(recovery_snapshot) != {"path", "files", "aggregate_sha256"}
                    or recovery_snapshot.get("path") != attempt_path
                ):
                    raise ValueError("Stage B recovery receipt semantics differ")
                recovery_files = recovery_snapshot.get("files")
                if not isinstance(recovery_files, dict) or recovery_snapshot.get(
                    "aggregate_sha256"
                ) != _sha(_canonical_bytes(recovery_files)):
                    raise ValueError("Stage B recovery snapshot aggregate is invalid")
                actual_files = {
                    str(path.relative_to(Path(attempt_path))).replace("\\", "/"): _descriptor(path)
                    for path in sorted(Path(attempt_path).rglob("*"))
                    if path.is_file()
                }
                if recovery_files != actual_files:
                    raise ValueError("Stage B recovery snapshot differs from attempt bytes")
                recovery_roots = recovery.get("lock_roots")
                recovery_ids = recovery.get("lock_ids")
                recovery_terminal = _validate_p18_terminal_authority(
                    recovery.get("p18_terminal_authority"),
                    verify_external_paths=True,
                )
                attempt_output = Path(attempt_path).parents[3]
                expected_output_lock = (
                    attempt_output.parent / f".{attempt_output.name}.stageb-input-lock"
                )
                if (
                    not isinstance(recovery_roots, dict)
                    or set(recovery_roots) != {"output", "p18", "p18_archive", "codev"}
                    or recovery_roots.get("p18")
                    != os.path.normcase(os.path.realpath(P18_GLOBAL_WINDOW_ROOT))
                    or recovery_roots.get("codev")
                    != os.path.normcase(os.path.realpath(CODEV_LOCK_ROOT))
                    or recovery_roots.get("p18_archive")
                    != os.path.normcase(
                        os.path.realpath(str(recovery_terminal.get("archive_root")))
                    )
                    or recovery_roots.get("output")
                    != os.path.normcase(os.path.realpath(expected_output_lock))
                    or len({os.path.normcase(str(path)) for path in recovery_roots.values()}) != 4
                    or not isinstance(recovery_ids, dict)
                    or set(recovery_ids) != {"output", "p18", "p18_archive", "codev"}
                    or any(
                        not isinstance(owner_id, str) or _ATTEMPT_ID.fullmatch(owner_id) is None
                        for owner_id in recovery_ids.values()
                    )
                ):
                    raise ValueError("Stage B recovery lock authority is malformed")
    elif len(entries) != 1:
        raise ValueError("production Stage B authority requires exactly one accepted input")
    expected_scope_counts = {
        scope: sum(entry.get("cache_scope") == scope for entry in entries)
        for scope in sorted({str(entry.get("cache_scope")) for entry in entries})
    }
    if manifest.get("cache_scope_counts") != expected_scope_counts or manifest.get(
        "all_inputs_pre_run_bound"
    ) is not all(entry.get("pre_run_bound") is True for entry in entries):
        raise ValueError("Stage B manifest cache summary differs from accepted inputs")
    matches = [
        entry for entry in entries if isinstance(entry, dict) and entry.get("case_id") == case_id
    ]
    if len(matches) != 1:
        raise ValueError("Stage B manifest requires one unique accepted case")
    entry = matches[0]
    accepted_path = _canonical_path(entry.get("accepted_zmx"), "accepted ZMX")
    ladder_path = _canonical_path(entry.get("ladder_result"), "ladder result")
    record_path = _canonical_path(entry.get("cache_record_path"), "cache record")
    if entry.get("accepted_zmx_sha256") != _sha(accepted_zmx_raw):
        raise ValueError("Stage B accepted digest differs from retained bytes")
    if entry.get("ladder_result_sha256") != _sha(ladder_raw):
        raise ValueError("Stage B final ladder digest differs from retained bytes")
    if entry.get("cache_record_sha256") != _sha(cache_record_raw):
        raise ValueError("Stage B cache record digest differs from retained bytes")
    record = _strict_json(cache_record_raw, "Stage B cache record")
    if cache_record_raw != _canonical_bytes(record):
        raise ValueError("Stage B cache record must use canonical JSON bytes")
    scope = entry.get("cache_scope")
    pre_run_bound = entry.get("pre_run_bound")
    if scope not in {PRE_RUN_SCOPE, RETROSPECTIVE_SCOPE} or pre_run_bound is not (
        scope == PRE_RUN_SCOPE
    ):
        raise ValueError("Stage B scope and pre-run flag are contradictory")
    _validate_ladder_shape(
        ladder,
        label="Stage B final ladder",
        allow_historical_accepted_path_rebound=scope == RETROSPECTIVE_SCOPE,
    )
    raw_path_value = entry.get("raw_ladder_result_path")
    raw_sha_value = entry.get("raw_ladder_result_sha256")
    if scope == PRE_RUN_SCOPE:
        if raw_ladder_raw is None:
            raise ValueError("fresh Stage B authority lacks retained raw ladder bytes")
        raw_path = _canonical_path(raw_path_value, "raw ladder result")
        if raw_sha_value != _sha(raw_ladder_raw):
            raise ValueError("fresh Stage B raw ladder digest differs from retained bytes")
        raw_ladder = _strict_json(raw_ladder_raw, "Stage B raw ladder")
        _validate_ladder_shape(raw_ladder, label="Stage B raw ladder")
        _closed_keys(
            record,
            {
                "schema_id",
                "scope",
                "attempt_id",
                "created_at",
                "identity",
                "lock_owner_ids",
            },
            "Stage B pre-run intent",
        )
        attempt_id = record.get("attempt_id")
        if (
            record.get("schema_id") != CACHE_INTENT_SCHEMA
            or record.get("scope") != "pre-run-intent"
            or not isinstance(attempt_id, str)
            or _ATTEMPT_ID.fullmatch(attempt_id) is None
            or Path(record_path).name != "intent.json"
            or Path(record_path).parent.name != attempt_id
        ):
            raise ValueError("Stage B pre-run intent is malformed")
        identity = _validate_identity(
            record.get("identity"),
            case_id=case_id,
            entry=entry,
            ladder=ladder,
            expected_work_dir=(
                Path(record_path).parent
                / (
                    "runner-work"
                    if isinstance(record.get("identity"), dict)
                    and record["identity"].get("runner_kind") == PRODUCTION_RUNNER_KIND
                    else "work"
                )
            ),
        )
        lock_authority = identity["lock_authority"]
        assert isinstance(lock_authority, dict)
        roots = lock_authority.get("roots")
        assert isinstance(roots, dict)
        _validate_lock_owner_ids(
            record.get("lock_owner_ids"),
            archive_required=roots.get("p18_archive") is not None,
        )
        provenance = ladder.get("cache_provenance")
        if not isinstance(provenance, dict):
            raise ValueError("fresh Stage B final ladder lacks provenance")
        _closed_keys(
            provenance,
            {
                "scope",
                "pre_run_bound",
                "intent_sha256",
                "raw_result_sha256",
                "post_run_identity_sha256",
                "accepted_artifact",
            },
            "Stage B cache provenance",
        )
        artifacts = provenance.get("accepted_artifact")
        if not isinstance(artifacts, dict):
            raise ValueError("fresh Stage B accepted provenance is missing")
        _closed_keys(artifacts, {"raw_emitted", "published"}, "accepted provenance")
        raw_final = raw_ladder.get("accepted_final")
        if not isinstance(raw_final, dict):
            raise ValueError("fresh raw ladder lacks accepted_final")
        raw_emitted = _validate_descriptor(
            artifacts.get("raw_emitted"),
            "raw emitted accepted ZMX",
            expected_path=raw_final.get("optimized_zmx_path"),
            expected_raw=accepted_zmx_raw,
        )
        published = _validate_descriptor(
            artifacts.get("published"),
            "published accepted ZMX",
            expected_path=accepted_path,
            expected_raw=accepted_zmx_raw,
        )
        expected_provenance = {
            "scope": PRE_RUN_SCOPE,
            "pre_run_bound": True,
            "intent_sha256": _sha(cache_record_raw),
            "raw_result_sha256": _sha(raw_ladder_raw),
            "post_run_identity_sha256": _sha(_canonical_bytes(identity)),
            "accepted_artifact": {"raw_emitted": raw_emitted, "published": published},
        }
        expected_final = _strict_json(raw_ladder_raw, "expected final source")
        _rebind_accepted_path(expected_final, accepted_path)
        expected_final["cache_provenance"] = expected_provenance
        if ladder != expected_final or provenance != expected_provenance:
            raise ValueError("Stage B final ladder is not the unique raw-derived result")
        raw_result_path: str | None = raw_path
        raw_result_sha: str | None = _sha(raw_ladder_raw)
    else:
        if raw_path_value is not None or raw_sha_value is not None:
            raise ValueError("retrospective Stage B authority may not claim raw ladder bytes")
        if raw_ladder_raw != no_pre_run_raw_bytes():
            raise ValueError("retrospective Stage B package lacks the canonical no-raw sentinel")
        _closed_keys(
            record,
            {
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
            },
            "Stage B retrospective adoption",
        )
        encoded = record.get("legacy_manifest_base64")
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Stage B adoption lacks embedded legacy manifest")
        try:
            embedded = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Stage B adoption manifest is not strict base64") from exc
        if base64.b64encode(embedded).decode("ascii") != encoded:
            raise ValueError("Stage B adoption manifest base64 is non-canonical")
        embedded_manifest = _strict_json(embedded, "embedded legacy Stage B manifest")
        embedded_accepted = embedded_manifest.get("accepted")
        embedded_outcomes = embedded_manifest.get("outcomes")
        if (
            set(embedded_manifest)
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
            or embedded_manifest.get("schema_id") != "atelier-stagec-stageb-input-manifest-v1"
            or embedded_manifest.get("required_count") != 8
            or not isinstance(embedded_accepted, list)
            or embedded_manifest.get("accepted_count") != len(embedded_accepted)
            or embedded_manifest.get("complete") is not (len(embedded_accepted) >= 8)
            or not isinstance(embedded_outcomes, list)
            or embedded_manifest.get("expert_verdict") is not None
            or embedded_manifest.get("truth_notice") != LEGACY_STAGEB_TRUTH_NOTICE
        ):
            raise ValueError("embedded legacy Stage B manifest claims are not closed")
        _validate_descriptor(
            record.get("legacy_manifest"), "legacy manifest", expected_raw=embedded
        )
        _validate_descriptor(
            record.get("legacy_result"),
            "legacy result",
            expected_path=ladder_path,
            expected_raw=ladder_raw,
        )
        referenced = record.get("referenced_artifacts")
        if not isinstance(referenced, list) or len(referenced) != 1:
            raise ValueError("Stage B adoption must reference exactly one accepted artifact")
        _validate_descriptor(
            referenced[0],
            "legacy accepted artifact",
            expected_path=accepted_path,
            expected_raw=accepted_zmx_raw,
        )
        terminal_authority = _validate_p18_terminal_authority(
            record.get("p18_terminal_authority"),
            verify_external_paths=verify_external_paths,
        )
        retrospective_identity = _validate_identity(
            record.get("current_identity"),
            case_id=case_id,
            entry=entry,
            ladder=ladder,
            expected_work_dir=None,
        )
        if retrospective_identity.get("runner_kind") != BATCH_RUNNER_KIND:
            raise ValueError("retrospective Stage B adoption requires the batch runner")
        retrospective_locks = retrospective_identity.get("lock_authority")
        assert isinstance(retrospective_locks, dict)
        retrospective_roots = retrospective_locks.get("roots")
        assert isinstance(retrospective_roots, dict)
        if retrospective_roots.get("p18_archive") != terminal_authority.get("archive_root"):
            raise ValueError("P18 terminal ledger differs from the retained archive lock")
        if (
            record.get("schema_id") != CACHE_ADOPTION_SCHEMA
            or record.get("scope") != RETROSPECTIVE_SCOPE
            or record.get("pre_run_bound") is not False
            or record.get("run_time_identity_verified") is not False
            or record.get("claims_match_current") is not True
            or record.get("case_id") != case_id
        ):
            raise ValueError("Stage B retrospective adoption claims are invalid")
        raw_result_path = None
        raw_result_sha = None
    accepted_final = ladder.get("accepted_final")
    from app.core.orchestration.candidate import fnum_ladder_evidence_from_result

    ladder_evidence = fnum_ladder_evidence_from_result(ladder)
    if (
        ladder.get("schema") != "atelier-p15-fno-ladder-v1"
        or ladder.get("stage") != "B"
        or ladder.get("target_achieved") is not True
        or not isinstance(accepted_final, dict)
        or accepted_final.get("status") != "measured"
        or accepted_final.get("fno_param_achieved") is not True
        or accepted_final.get("aut_converged") is not True
        or accepted_final.get("ray_traceable") is not True
        or accepted_final.get("optimized_zmx_path") != accepted_path
        or entry.get("accepted_final") != accepted_final
        or ladder_evidence is None
        or ladder_evidence.target_achieved is not True
        or ladder_evidence.accepted_final is None
    ):
        raise ValueError("Stage B authority does not close the four-condition accepted gate")
    if verify_external_paths:
        if (
            Path(accepted_path).resolve(strict=True).read_bytes() != accepted_zmx_raw
            or Path(ladder_path).resolve(strict=True).read_bytes() != ladder_raw
            or Path(record_path).resolve(strict=True).read_bytes() != cache_record_raw
        ):
            raise ValueError("Stage B external authority changed during packaging")
        if (
            scope == PRE_RUN_SCOPE
            and Path(str(raw_result_path)).resolve(strict=True).read_bytes() != raw_ladder_raw
        ):
            raise ValueError("Stage B external raw ladder changed during packaging")
    return StageBAuthorityBinding(
        scope=scope,  # type: ignore[arg-type]
        pre_run_bound=bool(pre_run_bound),
        record_path=record_path,
        record_sha256=_sha(cache_record_raw),
        raw_result_path=raw_result_path,
        raw_result_sha256=raw_result_sha,
        entry=dict(entry),
    )
