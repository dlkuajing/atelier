"""Runner-attested Stage C evidence package.

The v2 contract in :mod:`stagec_field` is deliberately synthetic.  This module
adds a separate v3 boundary whose authority is the receipt-last package emitted
by the process runner.  Persisted conclusions are never trusted: every restore
rehashes and reparses the retained raw bytes.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import math
import ntpath
import os
import posixpath
import re
import secrets
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.engines.codev import _read_windows_file_version
from app.core.engines.codev_batch import (
    run_codev_process_bytes,
)
from app.core.engines.stageb_authority import (
    CACHE_ADOPTION_SCHEMA,
    CACHE_INTENT_SCHEMA,
    OFFICIAL_EXECUTABLE,
    OFFICIAL_MACRO,
    STAGEB_MANIFEST_SCHEMA,
    TRUSTED_CODEV_FILE_VERSION,
    TRUSTED_CODEV_SHA256,
    TRUSTED_CODEV_SIZE_BYTES,
    TRUSTED_MACRO_SHA256,
    no_pre_run_raw_bytes,
    validate_retained_stageb_authority,
)
from app.core.engines.stagec_field import (
    FieldReconstructionResult,
    reconstruct_image_fields,
    resolve_field_target,
    validate_reconstructed_field_artifact,
)

SPEC_SCHEMA = "atelier-stagec-run-spec-v3"
LAUNCH_SCHEMA = "atelier-stagec-launch-manifest-v3"
METRICS_SCHEMA = "atelier-stagec-machine-metrics-v3"
RECEIPT_SCHEMA = "atelier-stagec-post-run-receipt-v3"
EVIDENCE_SCHEMA = "atelier-stagec-attested-evidence-v3"

_SAFE_ID = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TRUSTED_RUN_ROOT = Path.home() / ".atelier" / "stagec-runs"
_ATTESTATION_KEY_PATH = Path.home() / ".atelier" / "stagec-attestation.key"
_ATTESTATION_ALGORITHM = "hmac-sha256-local-runner-v1"
_ATTESTATION_SCOPE = (
    "trusted Atelier runner code under the current OS account/profile ACL; "
    "does not resist arbitrary code execution as the same user or a local administrator"
)
_OFFICIAL_ZEMAX_MACRO = OFFICIAL_MACRO
_TRUSTED_CODEV_EXECUTABLE = OFFICIAL_EXECUTABLE
_TRUSTED_CODEV_SHA256 = TRUSTED_CODEV_SHA256
_TRUSTED_CODEV_SIZE_BYTES = TRUSTED_CODEV_SIZE_BYTES
_TRUSTED_ZEMAX_MACRO_SHA256 = TRUSTED_MACRO_SHA256
_SUCCESSFUL_CODEV_RETURNCODES = frozenset({0, 1})
# CODE V stores field definitions in single precision: we write
# `YFLN 0 2.3143779176266652 ...` into the reconstructed ZMX, and `(YRI F^f Z1)`
# reads back `2.3143779000000e+00` -- roughly 8 significant digits.  Comparing that
# readout against a full-precision Python product therefore cannot succeed at the
# default rel_tol=1e-9 unless the target image height happens to be exactly
# representable, which is why only the control arm (whose target is the ZMX's own
# short literal, e.g. 2.91297) ever landed.  Measured relative error across the
# archived 2026-07-13 matrix peaks at 3.6e-8; float32 eps is 1.19e-7.  This bound
# tracks the instrument's actual precision -- it is not a relaxation of the gate.
_CODEV_FIELD_READOUT_REL_TOL = 2e-7
_REAL_MATRIX_PLAN_SCHEMA = "atelier-stagec-real-matrix-plan-v1"
_PRODUCTION_PLAN_SCHEMA = "atelier-stagec-production-execution-plan-v1"
_REAL_MATRIX_ARMS = frozenset({"native-imh-reconstructed-control", "target-low", "target-high"})
_PRODUCTION_ARM = "production-target"
_PRE_RUN_CACHE_SCOPE = "pre-run-bound"
_RETROSPECTIVE_CACHE_SCOPE = "retrospective-current-state-adoption"
_CACHE_SCOPES = frozenset({_PRE_RUN_CACHE_SCOPE, _RETROSPECTIVE_CACHE_SCOPE})
_CACHE_INTENT_SCHEMA = CACHE_INTENT_SCHEMA
_CACHE_ADOPTION_SCHEMA = CACHE_ADOPTION_SCHEMA
_ARTIFACT_NAMES = (
    "stageb-manifest.json",
    "stageb-ladder-result.json",
    "stageb-raw-ladder-result.json",
    "stageb-cache-record.json",
    "execution-plan.json",
    "official_zemaxos_to_cv.seq",
    "source.zmx",
    "reconstructed.zmx",
    "stagec.seq",
    "spec.json",
    "launch.json",
    "stdout.bin",
    "stderr.bin",
    "listing.lis",
    "metrics.tsv",
    "normalized-metrics.json",
)
_METRICS_HEADERS = (
    "record",
    "run_id",
    "field_index",
    "field_type",
    "definition_x_ri_mm",
    "definition_y_ri_mm",
    "rsi_actual_x_mm",
    "rsi_actual_y_mm",
    "rsi_direction_l",
    "rsi_direction_m",
    "rsi_direction_n",
    "rayrsi_return_code",
    "rer",
    "bls",
    "spotdata_return_code",
    "rms_spot_diameter_um",
    "rmswe_return_value",
    "rms_wfe_waves",
    "vuy",
    "vly",
    "vux",
    "vlx",
    "measured_efl_mm",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _no_pre_run_raw_bytes() -> bytes:
    return no_pre_run_raw_bytes()


def _attestation_key(*, create: bool) -> bytes:
    """Load the local runner trust anchor without ever logging its bytes.

    This protects the application boundary from caller-authored receipts.  It
    intentionally relies on the current OS account/profile ACL and does not
    claim resistance to a malicious local administrator.
    """

    path = _ATTESTATION_KEY_PATH.resolve()
    if not path.exists() and create:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = secrets.token_bytes(32)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
    try:
        key = path.read_bytes()
    except OSError as exc:
        raise ValueError("Stage C local attestation key is unavailable") from exc
    if len(key) != 32:
        raise ValueError("Stage C local attestation key has invalid length")
    return key


def _pinned_codev_file_version(executable: Path) -> str:
    version = _read_windows_file_version(executable)
    if version != TRUSTED_CODEV_FILE_VERSION:
        raise ValueError("Stage C CODE V file version differs from the verified probe pin")
    return version


@dataclass(frozen=True)
class _CodeVExecutableSnapshot:
    path: Path
    sha256: str
    size_bytes: int
    version: str


@dataclass
class _CodeVExecutableLease:
    pre: _CodeVExecutableSnapshot
    _handle: BinaryIO

    def post_snapshot(self) -> _CodeVExecutableSnapshot:
        return _snapshot_leased_codev(self.pre.path, self._handle)


def _open_windows_executable_read_lease(path: Path) -> BinaryIO:
    """Open ``path`` without sharing write/delete access until the file is closed."""

    import ctypes
    import msvcrt
    from ctypes import wintypes

    generic_read = 0x80000000
    file_share_read = 0x00000001
    open_existing = 3
    file_attribute_normal = 0x00000080
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    os_handle = create_file(
        str(path),
        generic_read,
        file_share_read,
        None,
        open_existing,
        file_attribute_normal,
        None,
    )
    if os_handle == wintypes.HANDLE(-1).value:
        error = ctypes.get_last_error()
        raise OSError(error, os.strerror(error), str(path))
    try:
        descriptor = msvcrt.open_osfhandle(os_handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        close_handle(os_handle)
        raise
    return os.fdopen(descriptor, "rb", closefd=True)


def _open_executable_read_lease(path: Path) -> BinaryIO:
    if os.name == "nt":
        return _open_windows_executable_read_lease(path)
    # CODE V production is Windows-only.  This fallback keeps mocked non-Windows
    # CI deterministic while still deriving every identity field from one fd.
    return path.open("rb")


def _leased_file_digest(handle: BinaryIO) -> tuple[str, int]:
    handle.seek(0)
    digest = hashlib.sha256()
    size_bytes = 0
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
        size_bytes += len(chunk)
    observed_size = os.fstat(handle.fileno()).st_size
    handle.seek(0)
    if size_bytes != observed_size:
        raise ValueError("Stage C CODE V executable changed while its identity was read")
    return digest.hexdigest(), size_bytes


def _snapshot_leased_codev(path: Path, handle: BinaryIO) -> _CodeVExecutableSnapshot:
    executable_sha256, executable_size_bytes = _leased_file_digest(handle)
    if executable_sha256 != _TRUSTED_CODEV_SHA256:
        raise ValueError("Stage C CODE V executable differs from the verified probe pin")
    if executable_size_bytes != _TRUSTED_CODEV_SIZE_BYTES:
        raise ValueError("Stage C CODE V executable size differs from the verified probe pin")
    return _CodeVExecutableSnapshot(
        path=path,
        sha256=executable_sha256,
        size_bytes=executable_size_bytes,
        version=_pinned_codev_file_version(path),
    )


@contextmanager
def _trusted_codev_executable_lease() -> Iterator[_CodeVExecutableLease]:
    executable = _TRUSTED_CODEV_EXECUTABLE.resolve(strict=True)
    with _open_executable_read_lease(executable) as handle:
        yield _CodeVExecutableLease(
            pre=_snapshot_leased_codev(executable, handle),
            _handle=handle,
        )


def _trusted_codev_identity() -> tuple[Path, str]:
    macro = _OFFICIAL_ZEMAX_MACRO.resolve(strict=True)
    if _sha(macro.read_bytes()) != _TRUSTED_ZEMAX_MACRO_SHA256:
        raise ValueError("Stage C official Zemax macro differs from the verified probe pin")
    with _trusted_codev_executable_lease() as lease:
        return lease.pre.path, lease.pre.version


def trusted_stagec_run_root() -> Path:
    """Return the fixed local attestation root without exposing signing material."""

    return _TRUSTED_RUN_ROOT.resolve()


def _attach_local_attestation(payload: dict[str, object]) -> dict[str, object]:
    if "attestation" in payload:
        raise ValueError("receipt payload may not pre-supply attestation")
    key = _attestation_key(create=True)
    signed = dict(payload)
    signed["attestation"] = {
        "algorithm": _ATTESTATION_ALGORITHM,
        "key_id": hashlib.sha256(key).hexdigest()[:16],
        "mac": hmac.new(key, _canonical_json(payload), hashlib.sha256).hexdigest(),
    }
    return signed


def _verify_local_attestation(receipt: dict[str, object]) -> None:
    attestation = receipt.get("attestation")
    if not isinstance(attestation, dict) or set(attestation) != {
        "algorithm",
        "key_id",
        "mac",
    }:
        raise ValueError("receipt lacks the closed local runner attestation")
    payload = {key: value for key, value in receipt.items() if key != "attestation"}
    key = _attestation_key(create=False)
    expected = {
        "algorithm": _ATTESTATION_ALGORITHM,
        "key_id": hashlib.sha256(key).hexdigest()[:16],
        "mac": hmac.new(key, _canonical_json(payload), hashlib.sha256).hexdigest(),
    }
    if not hmac.compare_digest(_canonical_json(attestation), _canonical_json(expected)):
        raise ValueError("receipt local runner attestation is invalid")


def _strict_json(raw: bytes, label: str) -> dict[str, object]:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=no_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"{label} contains non-standard numeric constant {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _finite(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _integer(value: str, label: str) -> int:
    if not re.fullmatch(r"-?\d+", value):
        raise ValueError(f"{label} must be an integer")
    return int(value)


class StageCAttestedField(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_index: int = Field(ge=1)
    sample_id: str = Field(pattern=r"^field-[0-9]{4}$")
    normalized_fraction: float
    definition_x_ri_mm: float
    definition_y_ri_mm: float
    rsi_actual_x_mm: float
    rsi_actual_y_mm: float
    rsi_direction_l: float
    rsi_direction_m: float
    rsi_direction_n: float
    rayrsi_return_code: int
    rer: int
    bls: int
    spotdata_return_code: int
    rms_spot_diameter_um: float
    rmswe_return_value: float
    rms_wfe_waves: float
    vuy: float
    vly: float
    vux: float
    vlx: float
    ray_classification: Literal[
        "valid", "ray-function-failure", "ray-error", "obscuration", "clear-aperture-block"
    ]


class StageCAttestedEvidence(BaseModel):
    """Evidence returned by receipt restore; this model factory is not a trust boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: Literal["atelier-stagec-attested-evidence-v3"] = EVIDENCE_SCHEMA
    evidence_kind: Literal["attested-machine"] = "attested-machine"
    run_id: str
    matrix_id: str
    cell_id: str
    seed_id: str
    arm: Literal[
        "native-imh-reconstructed-control", "target-low", "target-high", "production-target"
    ]
    repeat_index: int = Field(ge=1)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stageb_cache_scope: Literal["pre-run-bound", "retrospective-current-state-adoption"]
    stageb_pre_run_bound: bool
    stageb_cache_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stageb_raw_ladder_result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    package_path: str
    source_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconstructed_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_efl_mm: float = Field(gt=0)
    target_image_height_mm: float = Field(gt=0)
    normalized_fractions: tuple[float, ...] = Field(min_length=2)
    expected_vignetting_profile: tuple[tuple[float, float, float, float], ...] = Field(min_length=2)
    measured_efl_mm: float = Field(gt=0)
    fields: tuple[StageCAttestedField, ...] = Field(min_length=2)
    process_returncode_observed: Literal[0, 1]
    process_duration_seconds: float = Field(ge=0, allow_inf_nan=False)
    artifact_bindings_valid: Literal[True] = True
    receipt_attested: Literal[True] = True
    attestation_scope: Literal[
        "trusted Atelier runner code under the current OS account/profile ACL; does not resist "
        "arbitrary code execution as the same user or a local administrator"
    ] = _ATTESTATION_SCOPE
    field_type: Literal["RIH"] = "RIH"
    expert_verdict: None = None

    def __init__(self, **data: object) -> None:
        raise TypeError(
            "Stage C v3 public construction requires a restored runner post-run receipt"
        )

    @computed_field
    @property
    def attempted_sample_count(self) -> int:
        return len(self.fields)

    @computed_field
    @property
    def valid_ray_sample_count(self) -> int:
        return sum(field.ray_classification == "valid" for field in self.fields)

    @computed_field
    @property
    def valid_metric_sample_count(self) -> int:
        return sum(
            field.spotdata_return_code == 0
            and field.rmswe_return_value > 0
            and field.rms_spot_diameter_um > 0
            and field.rms_wfe_waves > 0
            for field in self.fields
        )

    @computed_field
    @property
    def all_rays_valid(self) -> bool:
        return all(
            field.ray_classification == "valid"
            and math.isclose(
                field.rsi_direction_l**2 + field.rsi_direction_m**2 + field.rsi_direction_n**2,
                1.0,
                abs_tol=2e-12,
            )
            for field in self.fields
        )

    @computed_field
    @property
    def all_metrics_valid(self) -> bool:
        return all(
            field.spotdata_return_code == 0
            and field.rmswe_return_value > 0
            and field.rms_spot_diameter_um > 0
            and field.rms_wfe_waves > 0
            for field in self.fields
        )

    @computed_field
    @property
    def zero_vignetting(self) -> bool:
        return all(
            value == 0
            for field in self.fields
            for value in (field.vuy, field.vly, field.vux, field.vlx)
        )

    @computed_field
    @property
    def vignetting_profile_valid(self) -> bool:
        return len(self.expected_vignetting_profile) == len(self.fields) and all(
            all(
                math.isclose(actual, expected, abs_tol=5e-12)
                for actual, expected in zip(
                    (field.vuy, field.vly, field.vux, field.vlx),
                    expected_profile,
                    strict=True,
                )
            )
            for field, expected_profile in zip(
                self.fields, self.expected_vignetting_profile, strict=True
            )
        )

    @computed_field
    @property
    def imh_field_valid(self) -> bool:
        profile_bound = (
            len(self.normalized_fractions) == len(self.fields)
            and tuple(field.normalized_fraction for field in self.fields)
            == self.normalized_fractions
        )
        # Only the Python-computed target crosses the precision boundary, so only it
        # gets the instrument-matched tolerance.  The other three comparisons stay
        # strict: they are CODE V readout against CODE V readout (same precision, and
        # empirically bit-identical) or against exact zero, where a relative tolerance
        # would be meaningless anyway.  abs_tol is retained for the on-axis field,
        # whose expected value is exactly 0 and thus outside rel_tol's reach.
        landing = all(
            math.isclose(field.definition_x_ri_mm, 0.0, abs_tol=5e-12)
            and math.isclose(
                field.definition_y_ri_mm,
                self.target_image_height_mm * field.normalized_fraction,
                rel_tol=_CODEV_FIELD_READOUT_REL_TOL,
                abs_tol=5e-12,
            )
            and math.isclose(field.definition_x_ri_mm, field.rsi_actual_x_mm, abs_tol=5e-12)
            and math.isclose(field.definition_y_ri_mm, field.rsi_actual_y_mm, abs_tol=5e-12)
            for field in self.fields
        )
        return profile_bound and self.all_rays_valid and landing

    @computed_field
    @property
    def efl_constraint_held(self) -> bool:
        return abs(self.measured_efl_mm - self.target_efl_mm) / self.target_efl_mm < 0.02

    @computed_field
    @property
    def image_height_achieved(self) -> bool:
        return (
            self.process_returncode_observed in _SUCCESSFUL_CODEV_RETURNCODES
            and math.isfinite(self.process_duration_seconds)
            and self.process_duration_seconds >= 0
            and self.reconstruction_applied
            and self.imh_field_valid
            and self.efl_constraint_held
            and self.all_metrics_valid
            and self.vignetting_profile_valid
        )

    @computed_field
    @property
    def reconstruction_applied(self) -> Literal[True]:
        return True

    @computed_field
    @property
    def nominal_image_height_mm(self) -> float:
        return self.target_image_height_mm

    @computed_field
    @property
    def derived_full_fov_deg(self) -> float:
        return 2 * math.degrees(math.atan(self.target_image_height_mm / self.target_efl_mm))

    @computed_field
    @property
    def measured_full_fov_deg(self) -> None:
        return None

    @computed_field
    @property
    def reconstruction_artifact_sha256(self) -> str:
        return self.reconstructed_zmx_sha256

    @computed_field
    @property
    def machine_execution_status(self) -> Literal["attested"]:
        return "attested"

    @computed_field
    @property
    def machine_execution_reason(self) -> str:
        return "local runner HMAC, receipt, raw artifacts, and Stage B authority bytes revalidated"

    @computed_field
    @property
    def reconstruction_status(self) -> Literal["constructed-verified"]:
        return "constructed-verified"

    @computed_field
    @property
    def imh_source(self) -> Literal["machine-attested"]:
        return "machine-attested"

    @computed_field
    @property
    def fov_source(self) -> Literal["derived"]:
        return "derived"

    @computed_field
    @property
    def efl_constraint_status(self) -> Literal["attested-held", "attested-violated"]:
        return "attested-held" if self.efl_constraint_held else "attested-violated"

    @computed_field
    @property
    def ray_metrics_status(self) -> Literal["attested-valid", "attested-invalid"]:
        return (
            "attested-valid"
            if self.all_rays_valid and self.all_metrics_valid and self.vignetting_profile_valid
            else "attested-invalid"
        )

    @computed_field
    @property
    def real_chief_ray_status(self) -> Literal["attested-valid", "attested-invalid"]:
        return "attested-valid" if self.all_rays_valid else "attested-invalid"

    @computed_field
    @property
    def rsi_status(self) -> Literal["attested-valid", "attested-invalid"]:
        return self.real_chief_ray_status

    @computed_field
    @property
    def note(self) -> str:
        return "runner-attested machine facts; FOV remains derived and [EXPERT] remains blank"

    @property
    def fov_attainment_label(self) -> Literal["derived"]:
        return "derived"


@dataclass(frozen=True)
class _ParsedMetrics:
    measured_efl_mm: float
    fields: tuple[StageCAttestedField, ...]


def _stageb_binding(
    *,
    manifest_raw: bytes,
    ladder_raw: bytes,
    raw_ladder_raw: bytes,
    cache_record_raw: bytes,
    case_id: str,
    accepted_zmx_raw: bytes,
    verify_external_paths: bool,
) -> dict[str, object]:
    """Validate the exact Stage B accepted-final bytes consumed by Stage C."""

    manifest = _strict_json(manifest_raw, "Stage B input manifest")
    ladder = _strict_json(ladder_raw, "Stage B ladder result")
    accepted_entries = manifest.get("accepted")
    if (
        manifest.get("schema_id") != STAGEB_MANIFEST_SCHEMA
        or manifest.get("complete") is not True
        or not isinstance(manifest.get("required_count"), int)
        or manifest["required_count"] < 1
        or not isinstance(accepted_entries, list)
        or manifest.get("accepted_count") != len(accepted_entries)
        or len(accepted_entries) < manifest["required_count"]
    ):
        raise ValueError("Stage B input manifest has not closed its accepted-seed gate")
    matches = [
        entry
        for entry in accepted_entries
        if isinstance(entry, dict) and entry.get("case_id") == case_id
    ]
    if len(matches) != 1:
        raise ValueError("Stage B input manifest requires one unique accepted case binding")
    entry = matches[0]
    accepted_path_raw = entry.get("accepted_zmx")
    ladder_path_raw = entry.get("ladder_result")
    cache_record_path_raw = entry.get("cache_record_path")
    if (
        not isinstance(accepted_path_raw, str)
        or not isinstance(ladder_path_raw, str)
        or not isinstance(cache_record_path_raw, str)
    ):
        raise ValueError("Stage B accepted paths are missing")
    if entry.get("accepted_zmx_sha256") != _sha(accepted_zmx_raw):
        raise ValueError("Stage B accepted ZMX hash differs from consumed bytes")
    if entry.get("ladder_result_sha256") != _sha(ladder_raw):
        raise ValueError("Stage B ladder-result hash differs from retained bytes")
    binding = validate_retained_stageb_authority(
        manifest_raw=manifest_raw,
        ladder_raw=ladder_raw,
        raw_ladder_raw=raw_ladder_raw,
        cache_record_raw=cache_record_raw,
        case_id=case_id,
        accepted_zmx_raw=accepted_zmx_raw,
        verify_external_paths=verify_external_paths,
    )
    if verify_external_paths:
        accepted_path = Path(accepted_path_raw).resolve(strict=True)
        ladder_path = Path(ladder_path_raw).resolve(strict=True)
        cache_record_path = Path(cache_record_path_raw).resolve(strict=True)
        if (
            accepted_path.read_bytes() != accepted_zmx_raw
            or ladder_path.read_bytes() != ladder_raw
            or cache_record_path.read_bytes() != cache_record_raw
        ):
            raise ValueError("Stage B external binding changed during Stage C preparation")
    accepted_final = ladder.get("accepted_final")
    # Function-local import avoids the candidate -> stagec_attested import
    # cycle while still reusing the production closed-schema validator.
    from app.core.orchestration.candidate import fnum_ladder_evidence_from_result

    ladder_evidence = fnum_ladder_evidence_from_result(ladder)
    if (
        ladder.get("schema") != "atelier-p15-fno-ladder-v1"
        or ladder.get("stage") != "B"
        or ladder.get("target_achieved") is not True
        or not isinstance(accepted_final, dict)
        or accepted_final != entry.get("accepted_final")
        or accepted_final.get("status") != "measured"
        or accepted_final.get("fno_param_achieved") is not True
        or accepted_final.get("aut_converged") is not True
        or accepted_final.get("ray_traceable") is not True
        or accepted_final.get("optimized_zmx_path") != accepted_path_raw
        or ladder.get("source_zmx") != Path(str(entry.get("source_zmx"))).name
        or ladder.get("fnum_target") != entry.get("fnum_target")
        or ladder.get("target_efl_mm") != entry.get("target_efl_mm")
        or ladder_evidence is None
        or ladder_evidence.target_achieved is not True
        or ladder_evidence.accepted_final is None
    ):
        raise ValueError("Stage B ladder does not reproduce the accepted-final four-condition gate")
    if (
        binding.scope != entry.get("cache_scope")
        or binding.pre_run_bound is not entry.get("pre_run_bound")
        or binding.record_sha256 != entry.get("cache_record_sha256")
    ):
        raise ValueError("Stage B authority validator returned a contradictory binding")
    return entry


def _classify(rc: int, rer: int, bls: int) -> str:
    if rc != 0:
        return "ray-function-failure"
    if rer != 0:
        return "ray-error"
    if bls < 0:
        return "obscuration"
    if bls > 0:
        return "clear-aperture-block"
    return "valid"


def _parse_metrics(
    raw: bytes,
    *,
    run_id: str,
    field_count: int,
    normalized_fractions: tuple[float, ...],
) -> _ParsedMetrics:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("metrics must be strict UTF-8") from exc
    if "\x00" in text:
        raise ValueError("metrics contain NUL")
    rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    if not rows or tuple(rows[0]) != _METRICS_HEADERS:
        raise ValueError("metrics header differs from closed v3 schema")
    if len(rows) != field_count + 1:
        raise ValueError("metrics must contain exactly one row per expected field")
    fields: list[StageCAttestedField] = []
    measured_values: list[float] = []
    for expected_index, row in enumerate(rows[1:], start=1):
        if len(row) != len(_METRICS_HEADERS):
            raise ValueError("metrics contain malformed or extra columns")
        values = dict(zip(_METRICS_HEADERS, row, strict=True))
        if values["record"] != "FIELD" or values["run_id"] != run_id:
            raise ValueError("metrics contain stale or foreign row identity")
        index = _integer(values["field_index"], "field_index")
        if index != expected_index:
            raise ValueError("metrics field indices must be unique contiguous 1..N")
        if values["field_type"] != "RIH":
            raise ValueError("attested Stage C metrics require exact RIH")
        rc = _integer(values["rayrsi_return_code"], "rayrsi_return_code")
        rer = _integer(values["rer"], "rer")
        bls = _integer(values["bls"], "bls")
        spot_rc = _integer(values["spotdata_return_code"], "spotdata_return_code")
        wfe_return = _finite(values["rmswe_return_value"], "rmswe_return_value")
        measured_values.append(_finite(values["measured_efl_mm"], "measured_efl_mm"))
        payload = {
            key: _finite(values[key], key)
            for key in (
                "definition_x_ri_mm",
                "definition_y_ri_mm",
                "rsi_actual_x_mm",
                "rsi_actual_y_mm",
                "rsi_direction_l",
                "rsi_direction_m",
                "rsi_direction_n",
                "rms_spot_diameter_um",
                "rms_wfe_waves",
                "vuy",
                "vly",
                "vux",
                "vlx",
            )
        }
        fields.append(
            StageCAttestedField(
                field_index=index,
                sample_id=f"field-{index:04d}",
                normalized_fraction=normalized_fractions[index - 1],
                rayrsi_return_code=rc,
                rer=rer,
                bls=bls,
                spotdata_return_code=spot_rc,
                rmswe_return_value=wfe_return,
                ray_classification=_classify(rc, rer, bls),
                **payload,
            )
        )
    if not measured_values or any(value != measured_values[0] for value in measured_values[1:]):
        raise ValueError("measured EFL must be present and identical on every field row")
    return _ParsedMetrics(measured_values[0], tuple(fields))


def _validate_listing(raw: bytes, *, run_id: str, spec_sha256: str) -> None:
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("listing must be strict UTF-8") from exc
    begin = f"STAGEC_ATTESTED_BEGIN {run_id} {spec_sha256}"
    end = f"STAGEC_ATTESTED_END {run_id} {spec_sha256}"
    if text.count(begin) != 1 or text.count(end) != 1 or text.index(end) <= text.index(begin):
        raise ValueError("listing lacks one unique complete attested run segment")
    for marker in ("COMPILATION ERRORS", "Sequence aborted"):
        if marker in text:
            raise ValueError(f"listing contains fatal marker {marker}")


def _artifact_digest(raw: bytes) -> dict[str, object]:
    return {"size_bytes": len(raw), "sha256": _sha(raw)}


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker()) if callable(checker) else False


def _validate_exact_package_entries(run_dir: Path) -> None:
    """Reject every directory entry outside the closed regular-file package."""

    expected = {*_ARTIFACT_NAMES, "post-run-receipt.json"}
    entries = list(run_dir.iterdir())
    if len(entries) != len(expected) or {entry.name for entry in entries} != expected:
        raise ValueError("Stage C package contains missing, extra, or non-canonical entries")
    for entry in entries:
        if entry.is_symlink() or _is_junction(entry):
            raise ValueError(f"Stage C package entry is a link or junction: {entry.name}")
        try:
            mode = os.lstat(entry).st_mode
        except OSError as exc:
            raise ValueError(f"Stage C package entry cannot be inspected: {entry.name}") from exc
        if not stat.S_ISREG(mode):
            raise ValueError(f"Stage C package entry is not a regular file: {entry.name}")


def _closed_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} keys differ from the closed schema")


def _positive_finite(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{label} must be positive and finite")
    return float(value)


def _strict_int(value: object, label: str, *, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _is_exact_int(value: object, expected: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == expected


def _digest_value(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _canonical_absolute_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a canonical absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise ValueError(f"{label} must be a canonical absolute path")
    try:
        canonical = str(path.resolve(strict=False))
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label} must be a canonical absolute path") from exc
    if value != canonical:
        raise ValueError(f"{label} must be a canonical absolute path")
    return canonical


def _absolute_path_syntax_key(value: object, label: str) -> tuple[str, str]:
    """Normalize an absolute path without consulting the live filesystem.

    Retained Windows receipts must remain restorable from non-Windows CI, so a
    platform-native :class:`Path` cannot be used for this comparison.  Windows
    paths compare case-insensitively; POSIX fixture paths remain case-sensitive.
    Dot segments and duplicate/trailing separators are rejected instead of
    silently normalized.
    """

    if not isinstance(value, str) or not value or "\0" in value:
        raise ValueError(f"{label} must be a canonical absolute path")
    windows_value = value.replace("/", "\\")
    windows_drive, _ = ntpath.splitdrive(windows_value)
    if windows_drive and ntpath.isabs(windows_value):
        normalized = ntpath.normpath(windows_value)
        if normalized != windows_value:
            raise ValueError(f"{label} must be a canonical absolute path")
        return "windows", normalized.casefold()
    if posixpath.isabs(value):
        normalized = posixpath.normpath(value)
        if normalized != value:
            raise ValueError(f"{label} must be a canonical absolute path")
        return "posix", normalized
    raise ValueError(f"{label} must be a canonical absolute path")


def _stageb_manifest_bindings(
    manifest: dict[str, object], *, expected_count: int
) -> dict[str, tuple[str, str, str, str, bool, str, str | None, str | None]]:
    entries = manifest.get("accepted")
    if (
        manifest.get("complete") is not True
        or not _is_exact_int(manifest.get("required_count"), expected_count)
        or not _is_exact_int(manifest.get("accepted_count"), expected_count)
        or not isinstance(entries, list)
        or len(entries) != expected_count
    ):
        raise ValueError(
            f"retained Stage B manifest must contain exactly {expected_count} accepted entries"
        )
    bindings: dict[str, tuple[str, str, str, str, bool, str, str | None, str | None]] = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"retained Stage B manifest entry {index} must be an object")
        case_id = entry.get("case_id")
        if not isinstance(case_id, str) or _SAFE_ID.fullmatch(case_id) is None:
            raise ValueError(f"retained Stage B manifest entry {index} has an invalid case")
        accepted_sha = _digest_value(
            entry.get("accepted_zmx_sha256"),
            f"retained Stage B manifest entry {index}.accepted_zmx_sha256",
        )
        source_sha = _digest_value(
            entry.get("source_zmx_sha256"),
            f"retained Stage B manifest entry {index}.source_zmx_sha256",
        )
        cache_scope = entry.get("cache_scope")
        pre_run_bound = entry.get("pre_run_bound")
        cache_record_sha = _digest_value(
            entry.get("cache_record_sha256"),
            f"retained Stage B manifest entry {index}.cache_record_sha256",
        )
        cache_record_path = _canonical_absolute_path(
            entry.get("cache_record_path"),
            f"retained Stage B manifest entry {index}.cache_record_path",
        )
        raw_sha_value = entry.get("raw_ladder_result_sha256")
        raw_path_value = entry.get("raw_ladder_result_path")
        if (
            cache_scope not in _CACHE_SCOPES
            or not isinstance(pre_run_bound, bool)
            or pre_run_bound is not (cache_scope == _PRE_RUN_CACHE_SCOPE)
        ):
            raise ValueError(
                f"retained Stage B manifest entry {index} cache scope is contradictory"
            )
        if cache_scope == _PRE_RUN_CACHE_SCOPE:
            raw_sha = _digest_value(
                raw_sha_value,
                f"retained Stage B manifest entry {index}.raw_ladder_result_sha256",
            )
            raw_path = _canonical_absolute_path(
                raw_path_value,
                f"retained Stage B manifest entry {index}.raw_ladder_result_path",
            )
        elif raw_sha_value is None and raw_path_value is None:
            raw_sha = None
            raw_path = None
        else:
            raise ValueError(
                f"retained Stage B manifest entry {index} retrospective raw binding is invalid"
            )
        if case_id in bindings:
            raise ValueError("retained Stage B manifest case identities must be unique")
        bindings[case_id] = (
            accepted_sha,
            source_sha,
            str(cache_scope),
            cache_record_sha,
            pre_run_bound,
            cache_record_path,
            raw_sha,
            raw_path,
        )
    return bindings


def _reconstruction_semantics(result: FieldReconstructionResult) -> dict[str, object]:
    """Return every reconstruction fact except machine-specific path locations."""

    return result.model_dump(
        mode="python",
        exclude={"source_path", "output_path"},
    )


def _validate_plan_cell(
    cell: object, *, label: str, require_stageb_hashes: bool
) -> dict[str, object]:
    if not isinstance(cell, dict):
        raise ValueError(f"{label} must be an object")
    expected_keys = {
        "cell_id",
        "case_id",
        "arm",
        "target_efl_mm",
        "target_image_height_mm",
        "reconstruction",
        "cache_scope",
        "pre_run_bound",
        "cache_record_path",
        "cache_record_sha256",
        "raw_ladder_result_path",
        "raw_ladder_result_sha256",
    }
    if require_stageb_hashes:
        expected_keys.update({"accepted_zmx_sha256", "source_zmx_sha256"})
    _closed_keys(
        cell,
        expected_keys,
        label,
    )
    case_id = cell.get("case_id")
    arm = cell.get("arm")
    cell_id = cell.get("cell_id")
    if (
        not isinstance(case_id, str)
        or _SAFE_ID.fullmatch(case_id) is None
        or not isinstance(arm, str)
        or arm not in {*_REAL_MATRIX_ARMS, _PRODUCTION_ARM}
        or not isinstance(cell_id, str)
        or cell_id != f"{case_id}--{arm}"
        or _SAFE_ID.fullmatch(cell_id) is None
    ):
        raise ValueError(f"{label} identity is invalid")
    _positive_finite(cell.get("target_efl_mm"), f"{label}.target_efl_mm")
    _positive_finite(cell.get("target_image_height_mm"), f"{label}.target_image_height_mm")
    cache_scope = cell.get("cache_scope")
    pre_run_bound = cell.get("pre_run_bound")
    if (
        cache_scope not in _CACHE_SCOPES
        or not isinstance(pre_run_bound, bool)
        or pre_run_bound is not (cache_scope == _PRE_RUN_CACHE_SCOPE)
    ):
        raise ValueError(f"{label} cache scope is contradictory")
    _canonical_absolute_path(cell.get("cache_record_path"), f"{label}.cache_record_path")
    _digest_value(cell.get("cache_record_sha256"), f"{label}.cache_record_sha256")
    raw_path = cell.get("raw_ladder_result_path")
    raw_sha = cell.get("raw_ladder_result_sha256")
    if cache_scope == _PRE_RUN_CACHE_SCOPE:
        _canonical_absolute_path(raw_path, f"{label}.raw_ladder_result_path")
        _digest_value(raw_sha, f"{label}.raw_ladder_result_sha256")
    elif raw_path is not None or raw_sha is not None:
        raise ValueError(f"{label} retrospective raw binding is invalid")
    if require_stageb_hashes:
        _digest_value(cell.get("accepted_zmx_sha256"), f"{label}.accepted_zmx_sha256")
        _digest_value(cell.get("source_zmx_sha256"), f"{label}.source_zmx_sha256")
    reconstruction = cell.get("reconstruction")
    if not isinstance(reconstruction, dict):
        raise ValueError(f"{label}.reconstruction must be an object")
    _digest_value(reconstruction.get("output_sha256"), f"{label}.reconstruction.output_sha256")
    try:
        parsed_reconstruction = FieldReconstructionResult.model_validate(reconstruction)
    except ValueError as exc:
        raise ValueError(f"{label}.reconstruction differs from the closed schema") from exc
    if (
        parsed_reconstruction.status != "constructed"
        or parsed_reconstruction.target_efl_mm != float(cell["target_efl_mm"])
        or parsed_reconstruction.target_image_height_mm != float(cell["target_image_height_mm"])
        or (
            require_stageb_hashes
            and parsed_reconstruction.source_sha256_before != cell.get("accepted_zmx_sha256")
        )
    ):
        raise ValueError(f"{label}.reconstruction is not same-source with its cell")
    return cell


def _validate_execution_plan(
    payload: dict[str, object],
    *,
    stageb_manifest: dict[str, object],
    stageb_manifest_path: str,
    stageb_manifest_sha256: str,
    matrix_id: str,
    case_id: str,
    cell_id: str,
    arm: str,
    repeat_index: int,
    target_efl_mm: float,
    target_image_height_mm: float,
    reconstructed_zmx_sha256: str,
    retained_stageb_source_sha256: str,
    fresh_reconstruction: FieldReconstructionResult,
) -> dict[str, object]:
    """Validate either the exact 8x3 matrix plan or one production cell plan."""

    canonical_stageb_manifest_path = _canonical_absolute_path(
        stageb_manifest_path, "actual Stage B manifest path"
    )
    schema = payload.get("schema_id")
    if schema == _REAL_MATRIX_PLAN_SCHEMA:
        _closed_keys(
            payload,
            {
                "schema_id",
                "matrix_id",
                "created_at",
                "stageb_manifest",
                "stageb_manifest_sha256",
                "seed_count",
                "cell_count",
                "repeat_count",
                "expected_run_count",
                "stageb_cache_scope_counts",
                "all_inputs_pre_run_bound",
                "retrospective_seed_ids",
                "cells",
                "expert_verdict",
            },
            "real matrix execution plan",
        )
        if (
            not _is_exact_int(payload.get("seed_count"), 8)
            or not _is_exact_int(payload.get("cell_count"), 24)
            or not _is_exact_int(payload.get("repeat_count"), 2)
            or not _is_exact_int(payload.get("expected_run_count"), 48)
            or not isinstance(repeat_index, int)
            or isinstance(repeat_index, bool)
            or repeat_index not in {1, 2}
            or not isinstance(payload.get("created_at"), str)
            or not payload.get("created_at")
            or not isinstance(payload.get("stageb_manifest"), str)
            or not payload.get("stageb_manifest")
            or payload.get("expert_verdict") is not None
        ):
            raise ValueError("real matrix execution plan counts/metadata are invalid")
        allowed_arms = _REAL_MATRIX_ARMS
    elif schema == _PRODUCTION_PLAN_SCHEMA:
        _closed_keys(
            payload,
            {
                "schema_id",
                "matrix_id",
                "stageb_manifest",
                "stageb_manifest_sha256",
                "seed_count",
                "cell_count",
                "repeat_count",
                "expected_run_count",
                "stageb_cache_scope_counts",
                "all_inputs_pre_run_bound",
                "retrospective_seed_ids",
                "cells",
                "expert_verdict",
            },
            "production execution plan",
        )
        if (
            not _is_exact_int(payload.get("seed_count"), 1)
            or not _is_exact_int(payload.get("cell_count"), 1)
            or not _is_exact_int(payload.get("repeat_count"), 1)
            or not _is_exact_int(payload.get("expected_run_count"), 1)
            or not isinstance(payload.get("stageb_manifest"), str)
            or not payload.get("stageb_manifest")
            or payload.get("expert_verdict") is not None
        ):
            raise ValueError("production execution plan counts/metadata are invalid")
        _strict_int(repeat_index, "production repeat_index", minimum=1)
        allowed_arms = frozenset({_PRODUCTION_ARM})
    else:
        raise ValueError("unsupported Stage C execution-plan schema")

    plan_matrix_id = payload.get("matrix_id")
    if (
        not isinstance(plan_matrix_id, str)
        or _SAFE_ID.fullmatch(plan_matrix_id) is None
        or plan_matrix_id != matrix_id
        or payload.get("stageb_manifest") != canonical_stageb_manifest_path
        or payload.get("stageb_manifest_sha256") != stageb_manifest_sha256
    ):
        raise ValueError("execution-plan matrix or Stage B manifest binding is invalid")
    cells = payload.get("cells")
    if not isinstance(cells, list):
        raise ValueError("execution-plan cells must be a list")
    if schema == _REAL_MATRIX_PLAN_SCHEMA and len(cells) != 24:
        raise ValueError("real matrix execution plan requires exactly 24 cells")
    if schema == _PRODUCTION_PLAN_SCHEMA and len(cells) != 1:
        raise ValueError("production execution plan requires exactly one cell")

    validated = [
        _validate_plan_cell(
            cell,
            label=f"execution-plan cell {index}",
            require_stageb_hashes=schema == _REAL_MATRIX_PLAN_SCHEMA,
        )
        for index, cell in enumerate(cells, start=1)
    ]
    cell_ids = [str(cell["cell_id"]) for cell in validated]
    if len(set(cell_ids)) != len(cell_ids):
        raise ValueError("execution-plan cell identities must be unique")
    if any(cell["arm"] not in allowed_arms for cell in validated):
        raise ValueError("execution-plan contains an arm outside its schema")
    if schema == _REAL_MATRIX_PLAN_SCHEMA:
        by_seed: dict[str, set[str]] = {}
        for cell in validated:
            by_seed.setdefault(str(cell["case_id"]), set()).add(str(cell["arm"]))
        if len(by_seed) != 8 or any(arms != _REAL_MATRIX_ARMS for arms in by_seed.values()):
            raise ValueError("real matrix plan requires exactly three arms for each of eight seeds")

    matches = [cell for cell in validated if cell["cell_id"] == cell_id]
    if len(matches) != 1:
        raise ValueError("execution plan requires one unique matching cell")
    cell = matches[0]
    reconstruction = cell["reconstruction"]
    assert isinstance(reconstruction, dict)
    parsed_reconstruction = FieldReconstructionResult.model_validate(reconstruction)
    if (
        cell.get("case_id") != case_id
        or cell.get("arm") != arm
        or float(cell["target_efl_mm"]) != target_efl_mm
        or float(cell["target_image_height_mm"]) != target_image_height_mm
        or reconstruction.get("output_sha256") != reconstructed_zmx_sha256
    ):
        raise ValueError("signed spec differs from retained execution-plan cell")
    if (
        schema == _REAL_MATRIX_PLAN_SCHEMA
        and cell.get("accepted_zmx_sha256") != retained_stageb_source_sha256
    ):
        raise ValueError(
            "real matrix cell accepted hash differs from retained Stage B source bytes"
        )
    if parsed_reconstruction.source_sha256_before != retained_stageb_source_sha256:
        raise ValueError("plan reconstruction differs from retained Stage B source bytes")
    if _reconstruction_semantics(parsed_reconstruction) != _reconstruction_semantics(
        fresh_reconstruction
    ):
        raise ValueError("plan reconstruction differs from fresh runner reconstruction semantics")
    expected_manifest_count = 8 if schema == _REAL_MATRIX_PLAN_SCHEMA else 1
    manifest_bindings = _stageb_manifest_bindings(
        stageb_manifest, expected_count=expected_manifest_count
    )
    expected_scope_counts = {
        scope: sum(binding[2] == scope for binding in manifest_bindings.values())
        for scope in sorted({binding[2] for binding in manifest_bindings.values()})
    }
    expected_retrospective = sorted(
        case
        for case, binding in manifest_bindings.items()
        if binding[2] == _RETROSPECTIVE_CACHE_SCOPE
    )
    if (
        payload.get("stageb_cache_scope_counts") != expected_scope_counts
        or payload.get("all_inputs_pre_run_bound")
        is not all(binding[4] for binding in manifest_bindings.values())
        or payload.get("retrospective_seed_ids") != expected_retrospective
    ):
        raise ValueError("execution plan cache-scope summary differs from Stage B manifest")
    if schema == _REAL_MATRIX_PLAN_SCHEMA:
        if set(by_seed) != set(manifest_bindings):
            raise ValueError("real matrix seed identities differ from retained Stage B manifest")
        for plan_cell in validated:
            manifest_hashes = manifest_bindings[str(plan_cell["case_id"])]
            if (
                plan_cell.get("accepted_zmx_sha256") != manifest_hashes[0]
                or plan_cell.get("source_zmx_sha256") != manifest_hashes[1]
                or plan_cell.get("cache_scope") != manifest_hashes[2]
                or plan_cell.get("cache_record_sha256") != manifest_hashes[3]
                or plan_cell.get("pre_run_bound") is not manifest_hashes[4]
                or plan_cell.get("cache_record_path") != manifest_hashes[5]
                or plan_cell.get("raw_ladder_result_sha256") != manifest_hashes[6]
                or plan_cell.get("raw_ladder_result_path") != manifest_hashes[7]
            ):
                raise ValueError("real matrix cell hashes do not match retained Stage B manifest")
    elif case_id not in manifest_bindings:
        raise ValueError("production cell is absent from retained Stage B manifest")
    else:
        production_binding = manifest_bindings[case_id]
        if (
            cell.get("cache_scope") != production_binding[2]
            or cell.get("cache_record_sha256") != production_binding[3]
            or cell.get("pre_run_bound") is not production_binding[4]
            or cell.get("cache_record_path") != production_binding[5]
            or cell.get("raw_ladder_result_sha256") != production_binding[6]
            or cell.get("raw_ladder_result_path") != production_binding[7]
        ):
            raise ValueError("production cell cache binding differs from Stage B manifest")
    return cell


def restore_stagec_attested_evidence(receipt_path: Path | str) -> StageCAttestedEvidence:
    """Rehash and reparse a final receipt package; never trust serialized gates."""

    return _restore_stagec_attested_evidence(receipt_path, allow_inflight=False)


def _restore_stagec_attested_evidence(
    receipt_path: Path | str, *, allow_inflight: bool
) -> StageCAttestedEvidence:
    """Shared validator; inflight access is private to pre-publish runner validation."""

    supplied_receipt = Path(receipt_path)
    supplied_run_dir = supplied_receipt.parent
    if (
        supplied_receipt.name != "post-run-receipt.json"
        or supplied_receipt.is_symlink()
        or _is_junction(supplied_receipt)
        or supplied_run_dir.is_symlink()
        or _is_junction(supplied_run_dir)
    ):
        raise ValueError("v3 evidence requires a canonical regular post-run-receipt.json")
    receipt_path = supplied_receipt.resolve()
    if receipt_path.name != "post-run-receipt.json" or not receipt_path.is_file():
        raise ValueError("v3 evidence requires final post-run-receipt.json")
    run_dir = receipt_path.parent
    trusted_root = _TRUSTED_RUN_ROOT.resolve()
    if run_dir.parent != trusted_root:
        raise ValueError("v3 evidence package is outside the trusted Stage C run root")
    is_inflight = run_dir.name.endswith(".inflight")
    if is_inflight and not allow_inflight:
        raise ValueError("inflight Stage C package can never be attested")
    if allow_inflight and not is_inflight:
        raise ValueError("pre-publish validation requires the canonical inflight package")
    receipt_raw = receipt_path.read_bytes()
    receipt = _strict_json(receipt_raw, "receipt")
    if receipt_raw != _canonical_json(receipt):
        raise ValueError("receipt must use exact canonical JSON bytes")
    _verify_local_attestation(receipt)
    if receipt.get("schema_id") != RECEIPT_SCHEMA:
        raise ValueError("unexpected Stage C receipt schema")
    _closed_keys(
        receipt,
        {
            "schema_id",
            "run_id",
            "created_at",
            "process",
            "artifacts",
            "stageb_cache",
            "truth_notice",
            "attestation_scope",
            "attestation",
        },
        "Stage C receipt",
    )
    if receipt.get("attestation_scope") != _ATTESTATION_SCOPE:
        raise ValueError("receipt attestation scope is missing or overstated")
    run_id = receipt.get("run_id")
    expected_dir_name = f"{run_id}.inflight" if allow_inflight else run_id
    if (
        not isinstance(run_id, str)
        or _SAFE_ID.fullmatch(run_id) is None
        or run_dir.name != expected_dir_name
    ):
        raise ValueError("receipt run identity does not match canonical directory")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, dict) or tuple(sorted(artifacts)) != tuple(
        sorted(_ARTIFACT_NAMES)
    ):
        raise ValueError("receipt artifact set differs from closed v3 package")
    _validate_exact_package_entries(run_dir)
    retained: dict[str, bytes] = {}
    for name in _ARTIFACT_NAMES:
        if Path(name).name != name:
            raise ValueError("receipt artifact path is not canonical")
        descriptor = artifacts.get(name)
        if not isinstance(descriptor, dict):
            raise ValueError("receipt artifact descriptor is malformed")
        artifact_path = run_dir / name
        if artifact_path.is_symlink() or artifact_path.resolve().parent != run_dir:
            raise ValueError(f"receipt artifact path escapes trusted package: {name}")
        raw = artifact_path.read_bytes()
        if descriptor != _artifact_digest(raw):
            raise ValueError(f"receipt digest mismatch for {name}")
        retained[name] = raw
    spec = _strict_json(retained["spec.json"], "spec")
    launch = _strict_json(retained["launch.json"], "launch")
    if spec.get("schema_id") != SPEC_SCHEMA or spec.get("run_id") != run_id:
        raise ValueError("spec identity/schema mismatch")
    if launch.get("schema_id") != LAUNCH_SCHEMA or launch.get("run_id") != run_id:
        raise ValueError("launch identity/schema mismatch")
    spec_sha = _sha(retained["spec.json"])
    if launch.get("spec_sha256") != spec_sha or launch.get("sequence_sha256") != _sha(
        retained["stagec.seq"]
    ):
        raise ValueError("launch hash DAG is broken")
    source_sha = _sha(retained["source.zmx"])
    reconstructed_sha = _sha(retained["reconstructed.zmx"])
    if (
        spec.get("source_zmx_sha256") != source_sha
        or spec.get("reconstructed_zmx_sha256") != reconstructed_sha
    ):
        raise ValueError("spec ZMX byte binding mismatch")
    execution_plan_sha = _sha(retained["execution-plan.json"])
    if spec.get("execution_plan_sha256") != execution_plan_sha:
        raise ValueError("spec execution-plan binding mismatch")
    execution_plan_payload = _strict_json(retained["execution-plan.json"], "execution plan")
    retained_stageb_manifest = _strict_json(
        retained["stageb-manifest.json"], "retained Stage B manifest"
    )
    stageb_manifest_path = _canonical_absolute_path(
        spec.get("stageb_manifest_path"), "spec.stageb_manifest_path"
    )
    case_id = spec.get("stageb_case_id")
    if not isinstance(case_id, str) or _SAFE_ID.fullmatch(case_id) is None:
        raise ValueError("spec Stage B case identity is invalid")
    stageb_entry = _stageb_binding(
        manifest_raw=retained["stageb-manifest.json"],
        ladder_raw=retained["stageb-ladder-result.json"],
        raw_ladder_raw=retained["stageb-raw-ladder-result.json"],
        cache_record_raw=retained["stageb-cache-record.json"],
        case_id=case_id,
        accepted_zmx_raw=retained["source.zmx"],
        verify_external_paths=False,
    )
    stageb_cache = {
        "scope": stageb_entry.get("cache_scope"),
        "pre_run_bound": stageb_entry.get("pre_run_bound"),
        "record_sha256": stageb_entry.get("cache_record_sha256"),
        "raw_result_sha256": stageb_entry.get("raw_ladder_result_sha256"),
    }
    if (
        spec.get("stageb_manifest_sha256") != _sha(retained["stageb-manifest.json"])
        or spec.get("stageb_ladder_result_sha256") != _sha(retained["stageb-ladder-result.json"])
        or spec.get("stageb_cache_record_sha256") != _sha(retained["stageb-cache-record.json"])
        or spec.get("stageb_raw_ladder_result_sha256")
        != stageb_entry.get("raw_ladder_result_sha256")
        or spec.get("stageb_cache_scope") != stageb_cache["scope"]
        or spec.get("stageb_pre_run_bound") is not stageb_cache["pre_run_bound"]
        or receipt.get("stageb_cache") != stageb_cache
        or spec.get("target_efl_mm") != stageb_entry.get("target_efl_mm")
    ):
        raise ValueError("spec does not bind the retained Stage B authority bytes")
    field_count = spec.get("field_count")
    if not isinstance(field_count, int) or isinstance(field_count, bool) or field_count < 2:
        raise ValueError("spec field_count is invalid")
    fractions = spec.get("normalized_fractions")
    if (
        not isinstance(fractions, list)
        or len(fractions) != field_count
        or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            for value in fractions
        )
    ):
        raise ValueError("spec normalized field fractions are invalid")
    canonical_sequence = build_attested_sequence(
        reconstructed_zmx=Path("reconstructed.zmx"),
        metrics_path=Path("metrics.tsv"),
        run_id=run_id,
        spec_sha256=spec_sha,
    ).encode("ascii")
    if retained["stagec.seq"] != canonical_sequence:
        raise ValueError("retained sequence differs from canonical reviewed v3 generator")
    if spec.get("official_zemax_macro_sha256") != _sha(retained["official_zemaxos_to_cv.seq"]):
        raise ValueError("spec official Zemax macro binding mismatch")
    _validate_listing(retained["listing.lis"], run_id=run_id, spec_sha256=spec_sha)
    normalized_fraction_tuple = tuple(float(value) for value in fractions)
    parsed = _parse_metrics(
        retained["metrics.tsv"],
        run_id=run_id,
        field_count=field_count,
        normalized_fractions=normalized_fraction_tuple,
    )
    normalized = _strict_json(retained["normalized-metrics.json"], "normalized metrics")
    expected_normalized = {
        "schema_id": METRICS_SCHEMA,
        "run_id": run_id,
        "measured_efl_mm": parsed.measured_efl_mm,
        "fields": [field.model_dump(mode="json") for field in parsed.fields],
    }
    if normalized != expected_normalized:
        raise ValueError("normalized sidecar differs from raw metrics derivation")
    process = receipt.get("process")
    process_duration = process.get("duration_seconds") if isinstance(process, dict) else None
    if (
        not isinstance(process, dict)
        or not isinstance(process.get("returncode"), int)
        or isinstance(process.get("returncode"), bool)
        or process.get("returncode") not in _SUCCESSFUL_CODEV_RETURNCODES
        or not isinstance(process_duration, (int, float))
        or isinstance(process_duration, bool)
        or not math.isfinite(float(process_duration))
        or float(process_duration) < 0
    ):
        raise ValueError("receipt requires a successful finite CODE V process observation")
    owner = process.get("lock_owner")
    owner_details = owner.get("details") if isinstance(owner, dict) else None
    command = launch.get("command")
    if (
        not isinstance(command, list)
        or len(command) != 3
        or command[1:] != ["/B", "stagec.seq"]
        or not all(isinstance(value, str) for value in command)
        or not isinstance(owner, dict)
        or owner.get("schema_version") != 1
        or not isinstance(owner.get("lock_id"), str)
        or re.fullmatch(r"[0-9a-f]{32}", owner["lock_id"]) is None
        or not isinstance(owner_details, dict)
        or owner_details.get("purpose") != "codev-process"
        or owner_details.get("command") != command
        or launch.get("codev_executable_sha256") != _TRUSTED_CODEV_SHA256
        or process.get("executable_post_sha256") != _TRUSTED_CODEV_SHA256
        or not isinstance(launch.get("codev_executable_size_bytes"), int)
        or isinstance(launch.get("codev_executable_size_bytes"), bool)
        or launch.get("codev_executable_size_bytes") != _TRUSTED_CODEV_SIZE_BYTES
        or launch.get("official_zemax_macro_sha256") != _TRUSTED_ZEMAX_MACRO_SHA256
        or process.get("official_zemax_macro_post_sha256") != _TRUSTED_ZEMAX_MACRO_SHA256
        or _sha(retained["official_zemaxos_to_cv.seq"]) != _TRUSTED_ZEMAX_MACRO_SHA256
        or launch.get("codev_version") != TRUSTED_CODEV_FILE_VERSION
        or process.get("codev_version") != TRUSTED_CODEV_FILE_VERSION
    ):
        raise ValueError("receipt does not bind the shared CODE V lock launch")
    try:
        command_executable_key = _absolute_path_syntax_key(
            command[0], "retained CODE V launch executable"
        )
        trusted_executable_key = _absolute_path_syntax_key(
            str(_TRUSTED_CODEV_EXECUTABLE), "trusted CODE V executable"
        )
    except ValueError as exc:
        raise ValueError("receipt does not bind the shared CODE V lock launch") from exc
    if command_executable_key != trusted_executable_key:
        raise ValueError("receipt does not bind the shared CODE V lock launch")
    owner_work_dir = owner_details.get("work_dir")
    if not isinstance(owner_work_dir, str):
        raise ValueError("receipt lock work directory is missing")
    expected_inflight = run_dir.with_name(f"{run_id}.inflight")
    try:
        owner_work_dir_key = _absolute_path_syntax_key(
            owner_work_dir, "retained CODE V lock work directory"
        )
        expected_inflight_key = _absolute_path_syntax_key(
            str(expected_inflight), "canonical inflight package"
        )
    except ValueError as exc:
        raise ValueError(
            "receipt lock work directory is not the canonical inflight package"
        ) from exc
    if owner_work_dir_key != expected_inflight_key:
        raise ValueError("receipt lock work directory is not the canonical inflight package")
    target_efl = spec.get("target_efl_mm")
    target_imh = spec.get("target_image_height_mm")
    if (
        not isinstance(target_efl, (int, float))
        or isinstance(target_efl, bool)
        or not math.isfinite(float(target_efl))
        or float(target_efl) <= 0
    ):
        raise ValueError("spec target EFL is invalid")
    if (
        not isinstance(target_imh, (int, float))
        or isinstance(target_imh, bool)
        or not math.isfinite(float(target_imh))
        or float(target_imh) <= 0
        or not math.isfinite(parsed.measured_efl_mm)
        or parsed.measured_efl_mm <= 0
    ):
        raise ValueError("spec target image height is invalid")
    matrix_id = spec.get("matrix_id")
    cell_id = spec.get("cell_id")
    arm = spec.get("arm")
    repeat_index = spec.get("repeat_index")
    expected_cell = f"{case_id}--{arm}"
    if (
        not isinstance(matrix_id, str)
        or _SAFE_ID.fullmatch(matrix_id) is None
        or not isinstance(cell_id, str)
        or _SAFE_ID.fullmatch(cell_id) is None
        or cell_id != expected_cell
        or arm
        not in {
            "native-imh-reconstructed-control",
            "target-low",
            "target-high",
            "production-target",
        }
        or not isinstance(repeat_index, int)
        or isinstance(repeat_index, bool)
        or repeat_index < 1
    ):
        raise ValueError("spec matrix/cell/arm/repeat identity is invalid")
    parsed_artifact = validate_reconstructed_field_artifact(
        run_dir / "reconstructed.zmx",
        expected_num_fields=field_count,
        expected_fractions=tuple(float(value) for value in fractions),
        target_image_height_mm=float(target_imh),
        vignetting_mode="finite-nonzoom",
    )
    if parsed_artifact.sha256 != reconstructed_sha:
        raise ValueError("reconstructed Stage C artifact semantic binding failed")
    if spec.get("reconstruction_recipe") != "ftyp3-rih-nonzoom-vig-retained-v1":
        raise ValueError("unknown Stage C reconstruction recipe")
    with tempfile.TemporaryDirectory(prefix="atelier-stagec-replay-") as replay_dir_raw:
        replay_dir = Path(replay_dir_raw)
        replay_source = replay_dir / "source.zmx"
        replay_output = replay_dir / "reconstructed.zmx"
        replay_source.write_bytes(retained["source.zmx"])
        replay_target = resolve_field_target(
            efl_mm=float(target_efl),
            image_height_mm=float(target_imh),
            full_fov_deg=None,
        )
        replay_result = reconstruct_image_fields(
            source_zmx=replay_source,
            output_zmx=replay_output,
            resolved_target=replay_target,
            allow_nonzero_vignetting_for_machine=True,
        )
        if (
            replay_result.status != "constructed"
            or replay_output.read_bytes() != retained["reconstructed.zmx"]
        ):
            raise ValueError("retained reconstruction is not the deterministic Stage B transform")
    _validate_execution_plan(
        execution_plan_payload,
        stageb_manifest=retained_stageb_manifest,
        stageb_manifest_path=stageb_manifest_path,
        stageb_manifest_sha256=_sha(retained["stageb-manifest.json"]),
        matrix_id=matrix_id,
        case_id=case_id,
        cell_id=cell_id,
        arm=arm,
        repeat_index=repeat_index,
        target_efl_mm=float(target_efl),
        target_image_height_mm=float(target_imh),
        reconstructed_zmx_sha256=reconstructed_sha,
        retained_stageb_source_sha256=source_sha,
        fresh_reconstruction=replay_result,
    )
    raw_expected_vignetting = spec.get("expected_vignetting_profile")
    if not isinstance(raw_expected_vignetting, list) or len(raw_expected_vignetting) != field_count:
        raise ValueError("spec expected vignetting profile is missing")
    try:
        expected_vignetting = tuple(
            tuple(float(value) for value in profile) for profile in raw_expected_vignetting
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("spec expected vignetting profile is malformed") from exc
    if any(
        len(profile) != 4 or any(not math.isfinite(value) for value in profile)
        for profile in expected_vignetting
    ):
        raise ValueError("spec expected vignetting profile must be finite four-V rows")
    artifact_expected = tuple(
        (vuy, vly, vux, vlx)
        for vuy, vly, vux, vlx in zip(
            parsed_artifact.vuy,
            parsed_artifact.vly,
            parsed_artifact.vux,
            parsed_artifact.vlx,
            strict=True,
        )
    )
    if expected_vignetting != artifact_expected:
        raise ValueError("spec vignetting profile differs from reconstructed ZMX bytes")
    return StageCAttestedEvidence.model_construct(
        run_id=run_id,
        matrix_id=matrix_id,
        cell_id=cell_id,
        seed_id=case_id,
        arm=arm,
        repeat_index=repeat_index,
        receipt_sha256=_sha(receipt_raw),
        execution_plan_sha256=execution_plan_sha,
        stageb_cache_scope=stageb_entry["cache_scope"],
        stageb_pre_run_bound=stageb_entry["pre_run_bound"],
        stageb_cache_record_sha256=stageb_entry["cache_record_sha256"],
        stageb_raw_ladder_result_sha256=stageb_entry.get("raw_ladder_result_sha256"),
        package_path=str(run_dir),
        source_zmx_sha256=source_sha,
        reconstructed_zmx_sha256=reconstructed_sha,
        target_efl_mm=float(target_efl),
        target_image_height_mm=float(target_imh),
        normalized_fractions=normalized_fraction_tuple,
        expected_vignetting_profile=expected_vignetting,
        measured_efl_mm=parsed.measured_efl_mm,
        fields=parsed.fields,
        process_returncode_observed=process["returncode"],
        process_duration_seconds=float(process_duration),
        attestation_scope=_ATTESTATION_SCOPE,
    )


def _fsync_package(directory: Path) -> None:
    """Flush every package file before same-volume atomic publication."""

    for path in directory.iterdir():
        if not path.is_file():
            continue
        with path.open("r+b") as handle:
            handle.flush()
            os.fsync(handle.fileno())
    if os.name == "nt":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _publish_stagec_inflight(*, inflight: Path, final: Path) -> Path:
    """Validate and atomically publish one complete receipt-last inflight package."""

    if inflight.parent != _TRUSTED_RUN_ROOT.resolve() or final.parent != inflight.parent:
        raise ValueError("Stage C publication requires the trusted local run root")
    if inflight.name != f"{final.name}.inflight":
        raise ValueError("Stage C inflight/final run identity mismatch")
    receipt_name = "post-run-receipt.json"
    receipt_inflight = inflight / receipt_name
    if not receipt_inflight.is_file():
        raise ValueError("Stage C inflight package lacks its receipt-last artifact")
    _fsync_package(inflight)
    _restore_stagec_attested_evidence(receipt_inflight, allow_inflight=True)
    if final.exists():
        raise ValueError("final Stage C run directory already exists")
    os.replace(inflight, final)
    receipt_path = final / receipt_name
    try:
        restore_stagec_attested_evidence(receipt_path)
    except Exception:
        quarantine = final.parent / f"{final.name}.quarantine-{uuid4().hex}"
        os.replace(final, quarantine)
        raise
    return receipt_path


def _quote(path: Path) -> str:
    value = str(path)
    if any(character in value for character in ('"', "\r", "\n")):
        raise ValueError("unsafe CODE V path")
    return f'"{value}"'


def _field_row() -> str:
    values = (
        '"FIELD"',
        "^run_id",
        "^f",
        "^field_type",
        "^definition_x",
        "^definition_y",
        "^actual_x",
        "^actual_y",
        "^actual_l",
        "^actual_m",
        "^actual_n",
        "^rc",
        "^rer",
        "^bls",
        "^spot_err",
        "^spot(1)*1000",
        "^wfe_ok",
        "^rwe(1,^f)",
        "^vuy",
        "^vly",
        "^vux",
        "^vlx",
        "^efy",
    )
    return f"  BUF PUT B1 I^row J1..23 {' '.join(values)}"


def build_attested_sequence(
    *, reconstructed_zmx: Path, metrics_path: Path, run_id: str, spec_sha256: str
) -> str:
    """Build the verified RIH sequence; conclusions remain parser-derived."""

    if _SAFE_ID.fullmatch(run_id) is None or _SHA256.fullmatch(spec_sha256) is None:
        raise ValueError("unsafe Stage C run identity")
    header = " ".join(f'"{value}"' for value in _METRICS_HEADERS)
    return "\n".join(
        [
            "! Generated by app.core.engines.stagec_attested.",
            f"! SPEC_SHA256 {spec_sha256}",
            "LCL NUM ^input(4) ^spot(10) ^rwe(10,26)",
            "LCL STR ^converter",
            "OUT NO",
            '^converter == "official_zemaxos_to_cv.seq"',
            f"IN ^converter {_quote(reconstructed_zmx)}",
            "^field_type == (TYP FLD)",
            "^numfld == (NUM F)",
            "^refw == (REF)",
            "^image == (FOC Z1)",
            "^efy == ABSF((EFY))",
            f'^run_id == "{run_id}"',
            "^input(1) == 0",
            "^input(2) == 0",
            "^input(3) == 0",
            "^input(4) == 0",
            "^wfe_ok == RMSWE(1,0,60,^rwe,'NOM')",
            "^row == 1",
            f"BUF PUT B1 I^row J1..23 {header}",
            "^row == ^row+1",
            "OUT YES",
            f'WRI Q"STAGEC_ATTESTED_BEGIN {run_id} {spec_sha256}"',
            "OUT NO",
            "FOR ^f 1 ^numfld",
            "  ^definition_x == (XRI F^f Z1)",
            "  ^definition_y == (YRI F^f Z1)",
            "  ^vuy == (VUY F^f Z1)",
            "  ^vly == (VLY F^f Z1)",
            "  ^vux == (VUX F^f Z1)",
            "  ^vlx == (VLX F^f Z1)",
            "  ^rer == 0",
            "  ^bls == 0",
            "  ^actual_x == -9.9E99",
            "  ^actual_y == -9.9E99",
            "  ^actual_l == -9.9E99",
            "  ^actual_m == -9.9E99",
            "  ^actual_n == -9.9E99",
            "  ^rc == RAYRSI(1,^refw,^f,0,^input)",
            "  IF ^rc = 0",
            "    ^rer == (RER)",
            "    IF ^rer = 0",
            "      ^bls == (BLS)",
            "      ^actual_x == (X S^image)",
            "      ^actual_y == (Y S^image)",
            "      ^actual_l == (L S^image)",
            "      ^actual_m == (M S^image)",
            "      ^actual_n == (N S^image)",
            "    END IF",
            "  END IF",
            "  ^spot_err == SPOTDATA(1,^f,1,0.01,'CEN',0,0,^spot)",
            _field_row(),
            "  BUF FMT B1 I^row J3 'd'",
            "  BUF FMT B1 I^row J5..11 '5e.17e'",
            "  BUF FMT B1 I^row J12..15 'd'",
            "  BUF FMT B1 I^row J16..23 '5e.17e'",
            "  ^row == ^row+1",
            "END FOR",
            f"BUF EXP B1 {_quote(metrics_path)}",
            "BUF DEL B1",
            "OUT YES",
            f'WRI Q"STAGEC_ATTESTED_END {run_id} {spec_sha256}"',
            "EXI YES",
            "",
        ]
    )


def run_stagec_attested(
    *,
    stageb_manifest: Path,
    execution_plan: Path,
    stageb_case_id: str,
    matrix_id: str,
    arm: Literal[
        "native-imh-reconstructed-control", "target-low", "target-high", "production-target"
    ],
    repeat_index: int,
    run_root: Path | None = None,
    target_image_height_mm: float,
    timeout_seconds: float = 180.0,
    run_id: str | None = None,
) -> Path:
    """Run one isolated package and atomically publish it only after validation."""

    run_id = run_id or (f"stagec_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:10]}")
    if _SAFE_ID.fullmatch(run_id) is None:
        raise ValueError("unsafe Stage C run_id")
    cell_id = f"{stageb_case_id}--{arm}"
    if (
        _SAFE_ID.fullmatch(stageb_case_id) is None
        or _SAFE_ID.fullmatch(matrix_id) is None
        or _SAFE_ID.fullmatch(cell_id) is None
        or not isinstance(repeat_index, int)
        or isinstance(repeat_index, bool)
        or repeat_index < 1
    ):
        raise ValueError("unsafe Stage C matrix/cell/repeat identity")
    root = (run_root or _TRUSTED_RUN_ROOT).resolve()
    if root != _TRUSTED_RUN_ROOT.resolve():
        raise ValueError("attested Stage C runs require the trusted local run root")
    root.mkdir(parents=True, exist_ok=True)
    inflight = root / f"{run_id}.inflight"
    final = root / run_id
    if final.exists():
        raise ValueError("final Stage C run directory already exists")
    inflight.mkdir(exist_ok=False)
    resolved_stageb_manifest = stageb_manifest.resolve(strict=True)
    stageb_manifest_path = str(resolved_stageb_manifest)
    manifest_raw = resolved_stageb_manifest.read_bytes()
    manifest = _strict_json(manifest_raw, "Stage B input manifest")
    entries = manifest.get("accepted")
    matches = (
        [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("case_id") == stageb_case_id
        ]
        if isinstance(entries, list)
        else []
    )
    if len(matches) != 1:
        raise ValueError("Stage B case is not uniquely accepted in the input manifest")
    external_accepted = Path(str(matches[0].get("accepted_zmx"))).resolve(strict=True)
    external_ladder = Path(str(matches[0].get("ladder_result"))).resolve(strict=True)
    external_raw_value = matches[0].get("raw_ladder_result_path")
    external_cache_record = Path(str(matches[0].get("cache_record_path"))).resolve(strict=True)
    accepted_raw = external_accepted.read_bytes()
    ladder_raw = external_ladder.read_bytes()
    if external_raw_value is None:
        raw_ladder_raw = _no_pre_run_raw_bytes()
    else:
        external_raw = Path(str(external_raw_value)).resolve(strict=True)
        raw_ladder_raw = external_raw.read_bytes()
    cache_record_raw = external_cache_record.read_bytes()
    stageb_entry = _stageb_binding(
        manifest_raw=manifest_raw,
        ladder_raw=ladder_raw,
        raw_ladder_raw=raw_ladder_raw,
        cache_record_raw=cache_record_raw,
        case_id=stageb_case_id,
        accepted_zmx_raw=accepted_raw,
        verify_external_paths=True,
    )
    (inflight / "stageb-manifest.json").write_bytes(manifest_raw)
    (inflight / "stageb-ladder-result.json").write_bytes(ladder_raw)
    (inflight / "stageb-raw-ladder-result.json").write_bytes(raw_ladder_raw)
    (inflight / "stageb-cache-record.json").write_bytes(cache_record_raw)
    execution_plan_raw = execution_plan.resolve(strict=True).read_bytes()
    execution_plan_payload = _strict_json(execution_plan_raw, "Stage C execution plan")
    (inflight / "execution-plan.json").write_bytes(execution_plan_raw)
    (inflight / "source.zmx").write_bytes(accepted_raw)
    official_macro_raw = _OFFICIAL_ZEMAX_MACRO.resolve(strict=True).read_bytes()
    if _sha(official_macro_raw) != _TRUSTED_ZEMAX_MACRO_SHA256:
        raise ValueError("Stage C official Zemax macro differs from the verified probe pin")
    (inflight / "official_zemaxos_to_cv.seq").write_bytes(official_macro_raw)
    resolved_target = resolve_field_target(
        efl_mm=float(stageb_entry["target_efl_mm"]),
        image_height_mm=target_image_height_mm,
        full_fov_deg=None,
    )
    reconstruction = reconstruct_image_fields(
        source_zmx=inflight / "source.zmx",
        output_zmx=inflight / "reconstructed.zmx",
        resolved_target=resolved_target,
        allow_nonzero_vignetting_for_machine=True,
    )
    if reconstruction.status != "constructed" or reconstruction.num_fields is None:
        raise ValueError("trusted runner could not deterministically reconstruct Stage C input")
    _validate_execution_plan(
        execution_plan_payload,
        stageb_manifest=manifest,
        stageb_manifest_path=stageb_manifest_path,
        stageb_manifest_sha256=_sha(manifest_raw),
        matrix_id=matrix_id,
        case_id=stageb_case_id,
        cell_id=cell_id,
        arm=arm,
        repeat_index=repeat_index,
        target_efl_mm=float(stageb_entry["target_efl_mm"]),
        target_image_height_mm=float(target_image_height_mm),
        reconstructed_zmx_sha256=_sha((inflight / "reconstructed.zmx").read_bytes()),
        retained_stageb_source_sha256=_sha(accepted_raw),
        fresh_reconstruction=reconstruction,
    )
    field_count = reconstruction.num_fields
    normalized_fractions = reconstruction.normalized_fractions
    parsed_reconstruction = validate_reconstructed_field_artifact(
        inflight / "reconstructed.zmx",
        expected_num_fields=field_count,
        expected_fractions=normalized_fractions,
        target_image_height_mm=target_image_height_mm,
        vignetting_mode="finite-nonzoom",
    )
    expected_vignetting = [
        [vuy, vly, vux, vlx]
        for vuy, vly, vux, vlx in zip(
            parsed_reconstruction.vuy,
            parsed_reconstruction.vly,
            parsed_reconstruction.vux,
            parsed_reconstruction.vlx,
            strict=True,
        )
    ]
    spec = {
        "schema_id": SPEC_SCHEMA,
        "run_id": run_id,
        "field_type": "RIH",
        "field_count": field_count,
        "normalized_fractions": list(normalized_fractions),
        "expected_vignetting_profile": expected_vignetting,
        "reconstruction_recipe": "ftyp3-rih-nonzoom-vig-retained-v1",
        "target_efl_mm": stageb_entry["target_efl_mm"],
        "target_image_height_mm": target_image_height_mm,
        "stageb_case_id": stageb_case_id,
        "matrix_id": matrix_id,
        "cell_id": cell_id,
        "arm": arm,
        "repeat_index": repeat_index,
        "stageb_manifest_path": stageb_manifest_path,
        "stageb_manifest_sha256": _sha(manifest_raw),
        "stageb_ladder_result_sha256": _sha(ladder_raw),
        "stageb_cache_scope": stageb_entry["cache_scope"],
        "stageb_pre_run_bound": stageb_entry["pre_run_bound"],
        "stageb_cache_record_sha256": _sha(cache_record_raw),
        "stageb_raw_ladder_result_sha256": stageb_entry.get("raw_ladder_result_sha256"),
        "execution_plan_sha256": _sha(execution_plan_raw),
        "official_zemax_macro_sha256": _sha(official_macro_raw),
        "source_zmx_sha256": _sha((inflight / "source.zmx").read_bytes()),
        "reconstructed_zmx_sha256": _sha((inflight / "reconstructed.zmx").read_bytes()),
    }
    spec_raw = _canonical_json(spec)
    (inflight / "spec.json").write_bytes(spec_raw)
    sequence_raw = build_attested_sequence(
        reconstructed_zmx=Path("reconstructed.zmx"),
        metrics_path=Path("metrics.tsv"),
        run_id=run_id,
        spec_sha256=_sha(spec_raw),
    ).encode("ascii")
    (inflight / "stagec.seq").write_bytes(sequence_raw)
    # Acquire the executable identity immediately before launch and retain the
    # same read-only OS lease across the global lock, Popen, and process exit.
    with _trusted_codev_executable_lease() as executable_lease:
        executable_pre = executable_lease.pre
        launch = {
            "schema_id": LAUNCH_SCHEMA,
            "run_id": run_id,
            "spec_sha256": _sha(spec_raw),
            "sequence_sha256": _sha(sequence_raw),
            "codev_executable_sha256": executable_pre.sha256,
            "codev_executable_size_bytes": executable_pre.size_bytes,
            "codev_version": executable_pre.version,
            "official_zemax_macro_sha256": _sha(official_macro_raw),
            "command": [str(executable_pre.path), "/B", "stagec.seq"],
        }
        (inflight / "launch.json").write_bytes(_canonical_json(launch))
        capture = run_codev_process_bytes(
            launch["command"],
            work_dir=inflight,
            timeout_seconds=timeout_seconds,
        )
        (inflight / "stdout.bin").write_bytes(capture.stdout_bytes)
        (inflight / "stderr.bin").write_bytes(capture.stderr_bytes)
        executable_post = executable_lease.post_snapshot()
        official_macro_post_sha = _sha(_OFFICIAL_ZEMAX_MACRO.resolve(strict=True).read_bytes())
        if (
            executable_post.path != executable_pre.path
            or executable_post.sha256 != executable_pre.sha256
            or executable_post.size_bytes != executable_pre.size_bytes
            or executable_post.version != executable_pre.version
            or executable_post.sha256 != _TRUSTED_CODEV_SHA256
            or executable_post.size_bytes != _TRUSTED_CODEV_SIZE_BYTES
            or executable_post.version != TRUSTED_CODEV_FILE_VERSION
            or official_macro_post_sha != launch["official_zemax_macro_sha256"]
            or official_macro_post_sha != _TRUSTED_ZEMAX_MACRO_SHA256
        ):
            raise ValueError(
                "CODE V executable, file version, or official import macro changed during run"
            )
    executable_post_sha = executable_post.sha256
    codev_version_post = executable_post.version
    listings = sorted(inflight.glob("*.lis"))
    if len(listings) != 1 or not (inflight / "metrics.tsv").is_file():
        raise ValueError("CODE V run did not produce unique listing and metrics")
    listings[0].replace(inflight / "listing.lis")
    parsed = _parse_metrics(
        (inflight / "metrics.tsv").read_bytes(),
        run_id=run_id,
        field_count=field_count,
        normalized_fractions=normalized_fractions,
    )
    _validate_listing(
        (inflight / "listing.lis").read_bytes(),
        run_id=run_id,
        spec_sha256=_sha(spec_raw),
    )
    normalized = {
        "schema_id": METRICS_SCHEMA,
        "run_id": run_id,
        "measured_efl_mm": parsed.measured_efl_mm,
        "fields": [field.model_dump(mode="json") for field in parsed.fields],
    }
    (inflight / "normalized-metrics.json").write_bytes(_canonical_json(normalized))
    artifacts = {name: _artifact_digest((inflight / name).read_bytes()) for name in _ARTIFACT_NAMES}
    receipt = _attach_local_attestation(
        {
            "schema_id": RECEIPT_SCHEMA,
            "run_id": run_id,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "process": {
                "returncode": capture.process.returncode,
                "duration_seconds": capture.duration_seconds,
                "lock_owner": capture.lock_owner,
                "executable_post_sha256": executable_post_sha,
                "official_zemax_macro_post_sha256": official_macro_post_sha,
                "codev_version": codev_version_post,
            },
            "artifacts": artifacts,
            "stageb_cache": {
                "scope": stageb_entry["cache_scope"],
                "pre_run_bound": stageb_entry["pre_run_bound"],
                "record_sha256": _sha(cache_record_raw),
                "raw_result_sha256": stageb_entry.get("raw_ladder_result_sha256"),
            },
            "truth_notice": (
                "Runner-attested machine facts only; no production usability, yield, "
                "or [EXPERT] verdict is asserted."
            ),
            "attestation_scope": _ATTESTATION_SCOPE,
        }
    )
    (inflight / "post-run-receipt.json").write_bytes(_canonical_json(receipt))
    return _publish_stagec_inflight(inflight=inflight, final=final)
