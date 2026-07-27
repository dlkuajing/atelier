"""Process-isolated patent embodiment conversion with append-only evidence.

Optiland tracing runs only in the worker process.  The parent enforces a hard
wall-clock timeout, terminates the complete worker process tree, retains raw
logs, and publishes a ZMX only after validating the worker response and loading
the candidate again in the parent process.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.zmx_ingest import load_normalized_zmx

SCHEMA_VERSION = 1
DEFAULT_CONVERSION_TIMEOUT_SECONDS = 120.0
DEFAULT_PATENT_REFERENCE_WAVELENGTH_UM = 0.5876
PROCESS_TREE_KILL_TIMEOUT_SECONDS = 5.0
PROCESS_REAP_TIMEOUT_SECONDS = 2.0
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PatentConversionEvidenceError(RuntimeError):
    """Raised when an attempt cannot be represented without losing evidence."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourceDocumentEvidence(StrictModel):
    source_bucket: str = Field(min_length=1)
    retained_path: str = Field(min_length=1)
    sha256: str

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class PatentSurfaceInput(StrictModel):
    index: int = Field(ge=0)
    label: str
    radius_mm: float | None
    thickness_mm: float | None
    material: str | None
    nd: float | None
    vd: float | None
    surface_type: str | None
    asphere_coefficients: dict[str, float]


class PatentPrescriptionInput(StrictModel):
    patent_id: str = Field(min_length=1)
    embodiment: str = Field(min_length=1)
    focal_length_mm: float
    f_number: float
    hfov_deg: float
    surfaces: tuple[PatentSurfaceInput, ...] = Field(min_length=1)
    reference_wavelength_um: float = Field(
        default=DEFAULT_PATENT_REFERENCE_WAVELENGTH_UM,
        gt=0.0,
        exclude_if=lambda value: value == DEFAULT_PATENT_REFERENCE_WAVELENGTH_UM,
    )
    unsupported_asphere_terms: tuple[str, ...] = ()


class PatentConversionRequest(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    prescription: PatentPrescriptionInput
    source_document: SourceDocumentEvidence


class TraceAuditResult(StrictModel):
    semi_diameters_mm: dict[int, float]
    real_image_height_mm: float
    sanity_image_height_mm: float
    measured_surfaces: tuple[int, ...]
    interpolated_surfaces: tuple[int, ...]
    finite_final_rays: int = Field(ge=0)
    total_rays: int = Field(ge=0)


class PatentWorkerResponse(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    request_sha256: str
    status: Literal["success", "quality_rejected", "trace_failed"]
    reason_code: str
    detail: str = ""
    efl_mm: float | None = None
    trace_audit: TraceAuditResult | None = None

    @field_validator("request_sha256")
    @classmethod
    def validate_request_sha256(cls, value: str) -> str:
        if SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("request_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def validate_status_payload(self) -> PatentWorkerResponse:
        if not self.reason_code.startswith(f"{self.status}."):
            raise ValueError("reason_code must be namespaced by status")
        if self.status == "success":
            if self.efl_mm is None or self.trace_audit is None:
                raise ValueError("successful response requires EFL and trace audit")
        elif self.efl_mm is not None or self.trace_audit is not None:
            raise ValueError("failed response cannot carry success measurements")
        return self


class PatentConversionReceipt(StrictModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    attempt_id: str
    retry_number: int = Field(ge=1)
    request_sha256: str
    request_file_sha256: str
    status: Literal["success", "quality_rejected", "trace_failed", "trace_timeout"]
    reason_code: str
    detail: str = ""
    timeout_seconds: float = Field(gt=0)
    elapsed_seconds: float = Field(ge=0)
    returncode: int | None
    request_path: str
    receipt_path: str
    response_path: str | None
    stdout_path: str
    stdout_sha256: str
    stderr_path: str
    stderr_sha256: str
    candidate_zmx_path: str | None = None
    candidate_zmx_sha256: str | None = None
    published_zmx_path: str | None = None
    published_zmx_sha256: str | None = None
    process_kill: dict[str, Any] | None = None
    process_reap: dict[str, Any] | None = None
    worker_response: PatentWorkerResponse | None = None

    @field_validator(
        "request_sha256",
        "request_file_sha256",
        "stdout_sha256",
        "stderr_sha256",
        "candidate_zmx_sha256",
        "published_zmx_sha256",
    )
    @classmethod
    def validate_optional_sha256(cls, value: str | None) -> str | None:
        if value is not None and SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value

    @model_validator(mode="after")
    def validate_status_namespace(self) -> PatentConversionReceipt:
        if not self.reason_code.startswith(f"{self.status}."):
            raise ValueError("reason_code must be namespaced by status")
        if self.status == "success" and (
            self.worker_response is None or self.published_zmx_sha256 is None
        ):
            raise ValueError("successful receipt requires response and published ZMX")
        if self.worker_response is not None and self.worker_response.status != self.status:
            raise ValueError("receipt status must match worker response status")
        if self.status != "success" and self.published_zmx_sha256 is not None:
            raise ValueError("failed receipt cannot carry a published ZMX")
        return self


@dataclass(frozen=True)
class ProcessExecution:
    timed_out: bool
    returncode: int | None
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    process_kill: dict[str, Any] | None = None
    process_reap: dict[str, Any] | None = None


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def conversion_request_sha256(request: PatentConversionRequest) -> str:
    """Hash only conversion inputs, excluding the machine-local retained path."""

    payload = request.model_dump(mode="json")
    payload["source_document"].pop("retained_path")
    return sha256_bytes(canonical_json_bytes(payload))


def load_conversion_request(path: Path) -> PatentConversionRequest:
    return PatentConversionRequest.model_validate_json(path.read_bytes())


def set_patent_validation_wavelength(optic: Any, wavelength_um: float) -> None:
    """Set the source-published primary wavelength for deterministic validation."""

    if not math.isfinite(wavelength_um) or wavelength_um <= 0.0:
        raise ValueError("patent reference wavelength must be finite and positive")
    optic.wavelengths.wavelengths.clear()
    optic.wavelengths.add(wavelength_um, is_primary=True)


def run_process_with_hard_timeout(
    command: list[str],
    *,
    work_dir: Path,
    timeout_seconds: float,
    env: dict[str, str] | None = None,
    platform_name: str | None = None,
) -> ProcessExecution:
    """Run a child with binary pipes and forcibly terminate its process tree."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    platform_name = platform_name or os.name
    popen_kwargs: dict[str, Any] = {
        "cwd": str(work_dir),
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if platform_name == "nt":
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    started = time.monotonic()
    process = subprocess.Popen(command, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ProcessExecution(
            timed_out=False,
            returncode=process.returncode,
            stdout=_coerce_bytes(stdout),
            stderr=_coerce_bytes(stderr),
            elapsed_seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        partial_stdout = _coerce_bytes(exc.stdout)
        partial_stderr = _coerce_bytes(exc.stderr)

    kill_details = _kill_process_tree(process, platform_name=platform_name)
    reap_details, reaped_stdout, reaped_stderr = _reap_process_after_kill(process)
    return ProcessExecution(
        timed_out=True,
        returncode=process.returncode,
        stdout=_prefer_complete_output(reaped_stdout, partial_stdout),
        stderr=_prefer_complete_output(reaped_stderr, partial_stderr),
        elapsed_seconds=time.monotonic() - started,
        process_kill=kill_details,
        process_reap=reap_details,
    )


def run_patent_conversion_attempt(
    request: PatentConversionRequest,
    *,
    published_zmx_path: Path,
    attempts_root: Path,
    repo_root: Path,
    timeout_seconds: float = DEFAULT_CONVERSION_TIMEOUT_SECONDS,
) -> PatentConversionReceipt:
    """Run one append-only embodiment attempt and conditionally publish its ZMX."""

    request_bytes = canonical_json_bytes(request)
    request_sha256 = conversion_request_sha256(request)
    request_key = _request_key(request, request_sha256)
    attempt_dir, retry_number = _allocate_attempt_dir(attempts_root / request_key)
    attempt_id = f"{request_key}:attempt-{retry_number:04d}"
    request_path = attempt_dir / "request.json"
    response_path = attempt_dir / "response.json"
    stdout_path = attempt_dir / "stdout.log"
    stderr_path = attempt_dir / "stderr.log"
    candidate_path = attempt_dir / "candidate.zmx"
    receipt_path = attempt_dir / "receipt.json"
    _atomic_write(request_path, request_bytes)

    command = [
        sys.executable,
        "-m",
        "scripts.patent_conversion_worker",
        "--request",
        str(request_path),
        "--response",
        str(response_path),
        "--output",
        str(candidate_path),
    ]
    worker_env = os.environ.copy()
    worker_env["PYTHONUTF8"] = "1"
    execution = run_process_with_hard_timeout(
        command,
        work_dir=repo_root,
        timeout_seconds=timeout_seconds,
        env=worker_env,
    )
    _atomic_write(stdout_path, execution.stdout)
    _atomic_write(stderr_path, execution.stderr)

    common = {
        "attempt_id": attempt_id,
        "retry_number": retry_number,
        "request_sha256": request_sha256,
        "request_file_sha256": sha256_bytes(request_bytes),
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": execution.elapsed_seconds,
        "returncode": execution.returncode,
        "request_path": _path_text(request_path),
        "receipt_path": _path_text(receipt_path),
        "response_path": _path_text(response_path) if response_path.is_file() else None,
        "stdout_path": _path_text(stdout_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_path": _path_text(stderr_path),
        "stderr_sha256": sha256_file(stderr_path),
        "process_kill": execution.process_kill,
        "process_reap": execution.process_reap,
    }
    if execution.timed_out:
        receipt = PatentConversionReceipt(
            **common,
            status="trace_timeout",
            reason_code="trace_timeout.worker_hard_timeout",
            detail=f"worker exceeded {timeout_seconds:g} seconds",
        )
        _atomic_write(receipt_path, canonical_json_bytes(receipt))
        return receipt

    if execution.returncode != 0:
        receipt = PatentConversionReceipt(
            **common,
            status="trace_failed",
            reason_code="trace_failed.worker_process_failed",
            detail=_diagnostic_detail(execution),
        )
        _atomic_write(receipt_path, canonical_json_bytes(receipt))
        return receipt

    publish_temp = published_zmx_path.with_name(f".{published_zmx_path.name}.publish-tmp")
    try:
        response = PatentWorkerResponse.model_validate_json(response_path.read_bytes())
        if response.request_sha256 != request_sha256:
            raise ValueError("worker response request hash mismatch")
    except (OSError, ValueError) as exc:
        receipt = PatentConversionReceipt(
            **common,
            status="trace_failed",
            reason_code="trace_failed.worker_response_invalid",
            detail=f"{type(exc).__name__}: {exc}",
        )
        _atomic_write(receipt_path, canonical_json_bytes(receipt))
        return receipt

    common["worker_response"] = response
    if response.status != "success":
        receipt = PatentConversionReceipt(
            **common,
            status=response.status,
            reason_code=response.reason_code,
            detail=response.detail,
        )
        _atomic_write(receipt_path, canonical_json_bytes(receipt))
        return receipt

    try:
        if not candidate_path.is_file():
            raise FileNotFoundError("worker reported success without candidate ZMX")
        optic = load_normalized_zmx(candidate_path)
        set_patent_validation_wavelength(
            optic,
            request.prescription.reference_wavelength_um,
        )
        parent_efl = float(optic.paraxial.f2())
        if not math.isfinite(parent_efl):
            raise ValueError("parent validation produced non-finite EFL")
        if response.efl_mm is None or not math.isclose(
            parent_efl,
            response.efl_mm,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise ValueError("parent/worker EFL mismatch")
        published_zmx_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate_path, publish_temp)
        publish_temp.replace(published_zmx_path)
    except Exception as exc:  # noqa: BLE001 - validation must fail closed with evidence.
        with contextlib.suppress(FileNotFoundError):
            publish_temp.unlink()
        receipt = PatentConversionReceipt(
            **common,
            status="trace_failed",
            reason_code="trace_failed.parent_validation_failed",
            detail=f"{type(exc).__name__}: {exc}",
            candidate_zmx_path=_path_text(candidate_path) if candidate_path.is_file() else None,
            candidate_zmx_sha256=sha256_file(candidate_path) if candidate_path.is_file() else None,
        )
        _atomic_write(receipt_path, canonical_json_bytes(receipt))
        return receipt

    receipt = PatentConversionReceipt(
        **common,
        status="success",
        reason_code=response.reason_code,
        detail=response.detail,
        candidate_zmx_path=_path_text(candidate_path),
        candidate_zmx_sha256=sha256_file(candidate_path),
        published_zmx_path=_path_text(published_zmx_path),
        published_zmx_sha256=sha256_file(published_zmx_path),
    )
    _atomic_write(receipt_path, canonical_json_bytes(receipt))
    return receipt


def _request_key(request: PatentConversionRequest, request_sha256: str) -> str:
    prescription = request.prescription
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", prescription.patent_id).strip("-")
    embodiment = re.sub(r"[^A-Za-z0-9_.-]+", "-", prescription.embodiment).strip("-")
    return f"{stem or 'patent'}-{embodiment or 'embodiment'}-{request_sha256[:16]}"


def _allocate_attempt_dir(request_dir: Path) -> tuple[Path, int]:
    request_dir.mkdir(parents=True, exist_ok=True)
    for retry_number in range(1, 1_000_000):
        path = request_dir / f"attempt-{retry_number:04d}"
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return path, retry_number
    raise PatentConversionEvidenceError(f"attempt sequence exhausted: {request_dir}")


def _kill_process_tree(process: subprocess.Popen[bytes], *, platform_name: str) -> dict[str, Any]:
    if platform_name == "nt":
        try:
            completed = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=PROCESS_TREE_KILL_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001 - cleanup evidence must survive failures.
            return {
                "method": "taskkill",
                "pid": process.pid,
                "error": f"{type(exc).__name__}: {exc}",
                "fallback": _kill_single_process(process),
            }
        details: dict[str, Any] = {
            "method": "taskkill",
            "pid": process.pid,
            "returncode": completed.returncode,
            "stdout_tail": _tail(_coerce_bytes(completed.stdout)),
            "stderr_tail": _tail(_coerce_bytes(completed.stderr)),
        }
        if completed.returncode != 0:
            details["fallback"] = _kill_single_process(process)
        return details

    try:
        os.killpg(process.pid, signal.SIGKILL)
        return {"method": "killpg", "pid": process.pid}
    except Exception as exc:  # noqa: BLE001 - use direct-kill fallback and retain why.
        return {
            "method": "killpg",
            "pid": process.pid,
            "error": f"{type(exc).__name__}: {exc}",
            "fallback": _kill_single_process(process),
        }


def _kill_single_process(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    try:
        process.kill()
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup evidence.
        return {"method": "kill", "pid": process.pid, "error": f"{type(exc).__name__}: {exc}"}
    return {"method": "kill", "pid": process.pid}


def _reap_process_after_kill(
    process: subprocess.Popen[bytes],
) -> tuple[dict[str, Any], bytes, bytes]:
    try:
        stdout, stderr = process.communicate(timeout=PROCESS_REAP_TIMEOUT_SECONDS)
        return (
            {
                "method": "communicate",
                "pid": process.pid,
                "returncode": process.returncode,
                "reaped": process.returncode is not None,
            },
            _coerce_bytes(stdout),
            _coerce_bytes(stderr),
        )
    except subprocess.TimeoutExpired as exc:
        details: dict[str, Any] = {
            "method": "communicate",
            "pid": process.pid,
            "timeout_seconds": PROCESS_REAP_TIMEOUT_SECONDS,
            "reaped": False,
        }
        stdout = _coerce_bytes(exc.stdout)
        stderr = _coerce_bytes(exc.stderr)
    except Exception as exc:  # noqa: BLE001 - cleanup diagnostics must not mask timeout.
        details = {
            "method": "communicate",
            "pid": process.pid,
            "error": f"{type(exc).__name__}: {exc}",
            "reaped": False,
        }
        stdout = b""
        stderr = b""

    try:
        details["wait_returncode"] = process.wait(timeout=PROCESS_REAP_TIMEOUT_SECONDS)
        details["reaped"] = True
    except Exception as exc:  # noqa: BLE001 - retain bounded reap failure.
        details["wait_error"] = f"{type(exc).__name__}: {exc}"
    return details, stdout, stderr


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_bytes(content)
    temp.replace(path)


def _diagnostic_detail(execution: ProcessExecution) -> str:
    stderr = _tail(execution.stderr)
    stdout = _tail(execution.stdout)
    return f"returncode={execution.returncode}; stderr={stderr!r}; stdout={stdout!r}"


def _tail(value: bytes, limit: int = 4000) -> str:
    return value[-limit:].decode("utf-8", errors="replace")


def _coerce_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8", errors="replace")


def _prefer_complete_output(complete: bytes, partial: bytes) -> bytes:
    return complete if len(complete) >= len(partial) else partial


def _path_text(path: Path) -> str:
    return path.resolve().as_posix()
