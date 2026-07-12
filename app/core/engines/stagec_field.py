"""Phase 16 Stage C field-target resolution and offline ZMX reconstruction.

This module deliberately stops at the last operation proven without CODE V:
rewrite a temporary Zemax field table from angular (FTYP 0) to image-height
(FTYP 3).  Real chief-ray/RSI verification and CODE V syntax are separate,
pending machine evidence.  A constructed field is therefore never evidence of
an optimized or measured target by itself.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import math
import os
import re
import uuid
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    computed_field,
    model_validator,
)


class FieldTargetStatus(StrEnum):
    RESOLVED = "resolved"
    CONFLICT = "conflict"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


class ResolvedFieldTarget(BaseModel):
    """First-order IMH/FOV relationship with no invented tolerance."""

    model_config = ConfigDict(extra="forbid")

    status: FieldTargetStatus
    efl_mm: float | None
    image_height_mm: float | None
    full_fov_deg: float | None
    image_height_source: Literal["provided", "derived", "unavailable"]
    fov_source: Literal["provided", "derived", "unavailable"]
    consistency: Literal["exact", "conflict", "not-applicable"]
    image_height_delta_mm: float | None = None
    fov_delta_deg: float | None = None
    reason: str

    @model_validator(mode="after")
    def _closed_shape(self) -> ResolvedFieldTarget:
        if self.efl_mm is not None and (not math.isfinite(self.efl_mm) or self.efl_mm <= 0):
            raise ValueError("EFL must be positive and finite when present")
        if self.image_height_mm is not None and (
            not math.isfinite(self.image_height_mm) or self.image_height_mm <= 0
        ):
            raise ValueError("IMH must be positive and finite when present")
        if self.full_fov_deg is not None and (
            not math.isfinite(self.full_fov_deg) or not 0 < self.full_fov_deg < 180
        ):
            raise ValueError("FOV must be finite and inside (0, 180) when present")
        if self.status is FieldTargetStatus.RESOLVED and (
            self.efl_mm is None or self.image_height_mm is None or self.full_fov_deg is None
        ):
            raise ValueError("resolved field target requires EFL, IMH and FOV")
        if self.status is FieldTargetStatus.CONFLICT and (
            self.image_height_delta_mm is None or self.fov_delta_deg is None
        ):
            raise ValueError("conflict requires both raw deltas")
        if self.status is FieldTargetStatus.UNAVAILABLE and any(
            value is not None
            for value in (self.image_height_mm, self.full_fov_deg)
        ):
            raise ValueError("unavailable target cannot carry resolved IMH/FOV")
        if self.status is FieldTargetStatus.RESOLVED and (
            not math.isfinite(self.efl_mm) or self.efl_mm <= 0
            or not math.isfinite(self.image_height_mm) or self.image_height_mm <= 0
            or not math.isfinite(self.full_fov_deg) or not 0 < self.full_fov_deg < 180
        ):
            raise ValueError("resolved EFL/IMH/FOV must be finite and physically positive")
        if self.status in {FieldTargetStatus.INVALID, FieldTargetStatus.UNAVAILABLE} and any(
            value is not None for value in (self.image_height_delta_mm, self.fov_delta_deg)
        ):
            raise ValueError("invalid/unavailable target cannot carry consistency deltas")
        if self.status is FieldTargetStatus.INVALID and any(
            value is not None for value in (self.image_height_mm, self.full_fov_deg)
        ):
            raise ValueError("invalid target cannot carry resolved IMH/FOV")
        if self.status is FieldTargetStatus.CONFLICT and (
            self.consistency != "conflict"
            or self.image_height_source != "unavailable"
            or self.fov_source != "unavailable"
            or not math.isfinite(self.image_height_delta_mm)
            or not math.isfinite(self.fov_delta_deg)
        ):
            raise ValueError("conflict target must carry finite deltas and unavailable sources")
        return self


def resolve_field_target(
    *, efl_mm: float | None, image_height_mm: float | None, full_fov_deg: float | None
) -> ResolvedFieldTarget:
    """Resolve ``IMH = EFL * tan(FOV/2)`` using strict mathematical equality.

    When both IMH and FOV are supplied they are constraints, not alternatives.
    Floating-point roundoff is handled by ``math.isclose`` at machine-scale;
    no optical or product tolerance is invented here.  A mismatch returns its
    two raw signed deltas so policy can be chosen outside this module.
    """

    if efl_mm is None:
        return ResolvedFieldTarget(
            status=FieldTargetStatus.UNAVAILABLE,
            efl_mm=None,
            image_height_mm=None,
            full_fov_deg=None,
            image_height_source="unavailable",
            fov_source="unavailable",
            consistency="not-applicable",
            reason="positive finite EFL is required",
        )
    if not math.isfinite(efl_mm) or efl_mm <= 0:
        return ResolvedFieldTarget(
            status=FieldTargetStatus.INVALID, efl_mm=None, image_height_mm=None,
            full_fov_deg=None, image_height_source="unavailable", fov_source="unavailable",
            consistency="not-applicable", reason="explicit EFL is not positive and finite",
        )
    if image_height_mm is not None and (
        not math.isfinite(image_height_mm) or image_height_mm <= 0
    ):
        return ResolvedFieldTarget(
            status=FieldTargetStatus.INVALID, efl_mm=efl_mm, image_height_mm=None,
            full_fov_deg=None, image_height_source="unavailable", fov_source="unavailable",
            consistency="not-applicable", reason="explicit IMH is not positive and finite",
        )
    if full_fov_deg is not None and (
        not math.isfinite(full_fov_deg) or not 0 < full_fov_deg < 180
    ):
        return ResolvedFieldTarget(
            status=FieldTargetStatus.INVALID, efl_mm=efl_mm, image_height_mm=None,
            full_fov_deg=None, image_height_source="unavailable", fov_source="unavailable",
            consistency="not-applicable", reason="explicit FOV is outside (0, 180) or non-finite",
        )
    imh_ok = image_height_mm is not None
    fov_ok = full_fov_deg is not None
    if not imh_ok and not fov_ok:
        return ResolvedFieldTarget(
            status=FieldTargetStatus.UNAVAILABLE,
            efl_mm=efl_mm,
            image_height_mm=None,
            full_fov_deg=None,
            image_height_source="unavailable",
            fov_source="unavailable",
            consistency="not-applicable",
            reason="at least one positive finite IMH or FOV target is required",
        )
    if imh_ok and not fov_ok:
        assert image_height_mm is not None
        derived_fov = 2 * math.degrees(math.atan(image_height_mm / efl_mm))
        return ResolvedFieldTarget(
            status=FieldTargetStatus.RESOLVED,
            efl_mm=efl_mm,
            image_height_mm=image_height_mm,
            full_fov_deg=derived_fov,
            image_height_source="provided",
            fov_source="derived",
            consistency="not-applicable",
            reason="FOV derived from provided IMH and EFL",
        )
    if fov_ok and not imh_ok:
        assert full_fov_deg is not None
        derived_imh = efl_mm * math.tan(math.radians(full_fov_deg / 2))
        return ResolvedFieldTarget(
            status=FieldTargetStatus.RESOLVED,
            efl_mm=efl_mm,
            image_height_mm=derived_imh,
            full_fov_deg=full_fov_deg,
            image_height_source="derived",
            fov_source="provided",
            consistency="not-applicable",
            reason="IMH derived from provided FOV and EFL",
        )
    assert image_height_mm is not None and full_fov_deg is not None
    implied_imh = efl_mm * math.tan(math.radians(full_fov_deg / 2))
    implied_fov = 2 * math.degrees(math.atan(image_height_mm / efl_mm))
    imh_delta = image_height_mm - implied_imh
    fov_delta = full_fov_deg - implied_fov
    exact = math.isclose(image_height_mm, implied_imh, rel_tol=1e-12, abs_tol=1e-12)
    return ResolvedFieldTarget(
        status=FieldTargetStatus.RESOLVED if exact else FieldTargetStatus.CONFLICT,
        efl_mm=efl_mm,
        image_height_mm=image_height_mm if exact else None,
        full_fov_deg=full_fov_deg if exact else None,
        image_height_source="provided" if exact else "unavailable",
        fov_source="provided" if exact else "unavailable",
        consistency="exact" if exact else "conflict",
        image_height_delta_mm=None if exact else imh_delta,
        fov_delta_deg=None if exact else fov_delta,
        reason=(
            "provided IMH and FOV are mathematically consistent"
            if exact
            else "provided IMH and FOV conflict; no product tolerance is defined"
        ),
    )


class FieldReconstructionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["constructed", "unverified", "rejected"]
    source_path: str
    output_path: str | None
    source_sha256_before: str
    source_sha256_after: str
    output_sha256: str | None = None
    num_fields: int | None
    normalized_fractions: tuple[float, ...]
    target_efl_mm: float
    target_image_height_mm: float
    field_type_before: int | None
    field_type_after: Literal[3] | None
    line_endings: Literal["LF"] | None
    vignetting_status: Literal["zero", "nonzero-unverified", "unavailable"]
    reason: str

    @model_validator(mode="after")
    def _source_unchanged(self) -> FieldReconstructionResult:
        for label, digest in (
            ("source_sha256_before", self.source_sha256_before),
            ("source_sha256_after", self.source_sha256_after),
            ("output_sha256", self.output_sha256),
        ):
            if digest is not None and (
                len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError(f"{label} must be a lowercase SHA-256 hex digest")
        if self.source_sha256_before != self.source_sha256_after:
            raise ValueError("source ZMX changed during temporary reconstruction")
        if self.status == "constructed" and (
            self.output_path is None
            or self.field_type_after != 3
            or self.line_endings != "LF"
            or self.vignetting_status != "zero"
            or self.output_sha256 is None
        ):
            raise ValueError("constructed result requires a complete zero-vignetting FTYP3 artifact")
        if self.normalized_fractions and self.num_fields is not None and (
            len(self.normalized_fractions) != self.num_fields
        ):
            raise ValueError("normalized field profile length must equal num_fields")
        if self.status == "constructed" and (
            not self.normalized_fractions
            or not math.isclose(
                max(abs(value) for value in self.normalized_fractions), 1.0,
                rel_tol=0.0, abs_tol=1e-15,
            )
        ):
            raise ValueError("constructed field profile must contain a signed unit edge")
        if not math.isfinite(self.target_efl_mm) or self.target_efl_mm <= 0:
            raise ValueError("target_efl_mm must be positive and finite")
        return self


_FIELD_LINE = re.compile(r"^(?P<key>FTYP|XFLN|YFLN|VDXN|VDYN|VCXN|VCYN)\s+(?P<body>.*)$")


def _floats(body: str) -> tuple[float, ...]:
    return tuple(float(token) for token in body.split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ParsedStageCArtifact(BaseModel):
    """Facts parsed from artifact bytes; never accepts producer declarations as facts."""

    model_config = ConfigDict(extra="forbid")
    sha256: str
    num_fields: int = Field(ge=2)
    normalized_fractions: tuple[float, ...]
    target_image_height_mm: float = Field(gt=0)


def validate_reconstructed_field_artifact(
    artifact_path: str | Path,
    *,
    expected_num_fields: int,
    expected_fractions: tuple[float, ...],
    target_image_height_mm: float,
) -> ParsedStageCArtifact:
    """Parse and validate the complete offline Stage C artifact from actual bytes."""

    path = Path(artifact_path)
    payload = path.read_bytes()
    if b"\r" in payload or not payload.endswith(b"\n"):
        raise ValueError("Stage C artifact must use LF-only line endings")
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("Stage C artifact must be ASCII") from exc
    lines = text.splitlines()

    def unique_row(key: str) -> tuple[float, ...]:
        matches = [line for line in lines if line.startswith(f"{key} ")]
        if len(matches) != 1:
            raise ValueError(f"Stage C artifact requires exactly one {key} row")
        return _floats(matches[0].removeprefix(f"{key} "))

    ftyp = unique_row("FTYP")
    if len(ftyp) != 8 or not math.isfinite(ftyp[0]) or ftyp[0] != 3.0:
        raise ValueError("Stage C artifact must contain one complete 8-slot FTYP3 row")
    if any(not value.is_integer() for value in (ftyp[2], ftyp[7])) or (
        int(ftyp[2]) != expected_num_fields or int(ftyp[7]) != expected_num_fields
    ):
        raise ValueError("Stage C artifact FTYP field-count slots differ from num_fields")
    xfln = unique_row("XFLN")
    yfln = unique_row("YFLN")
    if len(yfln) != expected_num_fields or len(xfln) != expected_num_fields:
        raise ValueError("Stage C artifact XFLN/YFLN count differs from declared num_fields")
    if any(value != 0.0 for value in xfln):
        raise ValueError("Stage C artifact supports XFLN=0 only")
    if len(expected_fractions) != expected_num_fields:
        raise ValueError("declared field fraction count differs from num_fields")
    edge = max(abs(value) for value in yfln)
    if not math.isclose(edge, target_image_height_mm, rel_tol=1e-15, abs_tol=1e-15):
        raise ValueError("Stage C artifact edge does not equal target IMH")
    actual_fractions = tuple(value / edge for value in yfln)
    if any(
        not math.isclose(actual, expected, rel_tol=1e-15, abs_tol=1e-15)
        for actual, expected in zip(actual_fractions, expected_fractions, strict=True)
    ):
        raise ValueError("Stage C artifact signed field fractions differ from declaration")
    for key in ("VDXN", "VDYN", "VCXN", "VCYN"):
        values = unique_row(key)
        if len(values) != expected_num_fields or any(value != 0.0 for value in values):
            raise ValueError(f"Stage C artifact {key} must be complete and all-zero")
    return ParsedStageCArtifact(
        sha256=hashlib.sha256(payload).hexdigest(),
        num_fields=expected_num_fields,
        normalized_fractions=actual_fractions,
        target_image_height_mm=edge,
    )


def reconstruct_image_fields(
    *, source_zmx: str | Path, output_zmx: str | Path,
    resolved_target: ResolvedFieldTarget,
) -> FieldReconstructionResult:
    """Create a LF-only temporary FTYP3 ZMX, or fail closed before writing."""

    source = Path(source_zmx)
    output = Path(output_zmx)
    source_resolved = source.resolve(strict=True)
    output_resolved = output.resolve(strict=False)
    if source_resolved == output_resolved:
        raise ValueError("source_zmx and output_zmx must resolve to different paths")
    if resolved_target.status is not FieldTargetStatus.RESOLVED or (
        resolved_target.efl_mm is None or resolved_target.image_height_mm is None
    ):
        raise ValueError("reconstruction requires a resolved canonical field target")
    target_efl_mm = resolved_target.efl_mm
    target_image_height_mm = resolved_target.image_height_mm
    before = _sha256(source)
    source_bytes = source.read_bytes()
    encoding = "utf-16" if source_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    text = source_bytes.decode(encoding)
    rows: dict[str, tuple[float, ...]] = {}
    lines = text.splitlines()
    for line in lines:
        match = _FIELD_LINE.match(line.strip())
        if match:
            rows[match.group("key")] = _floats(match.group("body"))
    ftyp = rows.get("FTYP")
    xfln = rows.get("XFLN")
    yfln = rows.get("YFLN")
    num_fields = len(yfln) if yfln else None
    fractions: tuple[float, ...] = ()
    base = {
        "source_path": str(source),
        "output_path": None,
        "source_sha256_before": before,
        "source_sha256_after": _sha256(source),
        "output_sha256": None,
        "num_fields": num_fields,
        "normalized_fractions": fractions,
        "target_efl_mm": target_efl_mm,
        "target_image_height_mm": target_image_height_mm,
        "field_type_before": int(ftyp[0]) if ftyp else None,
        "field_type_after": None,
        "line_endings": None,
    }
    if not ftyp or not yfln or not xfln or len(xfln) != len(yfln) or len(yfln) < 2:
        return FieldReconstructionResult(
            status="rejected", vignetting_status="unavailable",
            reason="FTYP/XFLN/YFLN field profile is missing or inconsistent", **base
        )
    if int(ftyp[0]) != 0:
        return FieldReconstructionResult(
            status="rejected", vignetting_status="unavailable",
            reason="only angular FTYP0 input is supported by the offline reconstruction", **base
        )
    if any(value != 0.0 for value in xfln):
        return FieldReconstructionResult(
            status="rejected", vignetting_status="unavailable",
            reason="initial Stage C supports XFLN=0 only", **base
        )
    edge = max(abs(value) for value in yfln)
    if edge <= 0:
        return FieldReconstructionResult(
            status="rejected", vignetting_status="unavailable",
            reason="angular YFLN profile has no positive edge", **base
        )
    fractions = tuple(value / edge for value in yfln)
    base["normalized_fractions"] = fractions
    vig_keys = ("VDXN", "VDYN", "VCXN", "VCYN")
    if any(key not in rows or len(rows[key]) != len(yfln) for key in vig_keys):
        return FieldReconstructionResult(
            status="unverified", vignetting_status="unavailable",
            reason="complete vignetting profile is unavailable; no artifact emitted", **base
        )
    if any(value != 0.0 for key in vig_keys for value in rows[key]):
        return FieldReconstructionResult(
            status="unverified", vignetting_status="nonzero-unverified",
            reason="nonzero vignetting remap is not machine-verified; no artifact emitted", **base
        )
    rebuilt: list[str] = []
    y_values = " ".join(format(frac * target_image_height_mm, ".17g") for frac in fractions)
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("FTYP "):
            tokens = stripped.split()
            tokens[1] = "3"
            line = " ".join(tokens)
        elif stripped.startswith("YFLN "):
            line = f"YFLN {y_values}"
        rebuilt.append(line)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    try:
        payload = ("\n".join(rebuilt) + "\n").encode("utf-8")
        temp.write_bytes(payload)
        parsed = validate_reconstructed_field_artifact(
            temp,
            expected_num_fields=num_fields,
            expected_fractions=fractions,
            target_image_height_mm=target_image_height_mm,
        )
        after = _sha256(source)
        if after != before:
            raise ValueError("source ZMX changed before atomic output publication")
        result = FieldReconstructionResult(
            status="constructed", output_path=str(output), source_sha256_after=after,
            output_sha256=parsed.sha256, field_type_after=3, line_endings="LF",
            vignetting_status="zero",
            reason="temporary FTYP3/YFLN artifact constructed; real chief-ray verification pending",
            **{key: value for key, value in base.items() if key not in {
                "output_path", "source_sha256_after", "output_sha256", "field_type_after", "line_endings"
            }},
        )
        os.replace(temp, output)
        return result
    except Exception:
        temp.unlink(missing_ok=True)
        raise


class StageCFieldEvidence(BaseModel):
    """Offline-only evidence. It cannot express any achieved machine condition."""

    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["atelier-p16-stagec-field-v1"] = "atelier-p16-stagec-field-v1"
    evidence_kind: Literal["offline"] = "offline"
    machine_execution_status: Literal["blocked"] = "blocked"
    machine_execution_reason: str = Field(
        default="real chief-ray/RSI machine verification has not run", min_length=1
    )
    reconstruction_status: Literal["not-applied", "constructed"]
    imh_source: Literal["constructed", "unavailable"]
    fov_source: Literal["derived", "unavailable"]
    efl_constraint_status: Literal["unverified"] = "unverified"
    ray_metrics_status: Literal["pending"] = "pending"
    real_chief_ray_status: Literal["pending"] = "pending"
    rsi_status: Literal["pending"] = "pending"
    target_image_height_mm: float | None
    target_efl_mm: float | None
    nominal_image_height_mm: float | None
    derived_full_fov_deg: float | None
    measured_full_fov_deg: float | None
    reconstruction_applied: StrictBool
    imh_field_valid: Literal[False] = False
    efl_constraint_held: Literal[False] = False
    ray_metrics_valid: Literal[False] = False
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def _derive_and_close(self) -> StageCFieldEvidence:
        expected = (self.reconstruction_status != "not-applied", False, False, False)
        actual = (
            self.reconstruction_applied,
            self.imh_field_valid,
            self.efl_constraint_held,
            self.ray_metrics_valid,
        )
        if actual != expected:
            raise ValueError(f"Stage C four-condition flags disagree with typed evidence: {actual=}, {expected=}")
        if self.reconstruction_status == "constructed":
            if (
                self.imh_source != "constructed"
                or self.fov_source != "derived"
                or self.target_image_height_mm is None
                or self.target_efl_mm is None
                or self.nominal_image_height_mm != self.target_image_height_mm
                or not math.isfinite(self.target_image_height_mm)
                or self.target_image_height_mm <= 0
                or not math.isfinite(self.target_efl_mm)
                or self.target_efl_mm <= 0
                or self.derived_full_fov_deg is None
                or not math.isfinite(self.derived_full_fov_deg)
                or not 0 < self.derived_full_fov_deg < 180
                or not math.isclose(
                    self.derived_full_fov_deg,
                    2
                    * math.degrees(
                        math.atan(self.target_image_height_mm / self.target_efl_mm)
                    ),
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
                or self.measured_full_fov_deg is not None
            ):
                raise ValueError("constructed offline evidence requires same-source IMH and derived FOV")
        elif (
            self.imh_source != "unavailable"
            or self.fov_source != "unavailable"
            or any(
                value is not None
                for value in (
                    self.target_image_height_mm,
                    self.target_efl_mm,
                    self.nominal_image_height_mm,
                    self.derived_full_fov_deg,
                    self.measured_full_fov_deg,
                )
            )
        ):
            raise ValueError("not-applied offline evidence cannot carry field values")
        return self

    @property
    def image_height_achieved(self) -> bool:
        return False

    @property
    def fov_attainment_label(self) -> Literal["derived", "unavailable"]:
        return self.fov_source


class MachineRayClassification(StrEnum):
    """Fail-closed classification derived from raw CODE V ray outcomes."""

    VALID = "valid"
    RAY_TRACE_FAILURE = "ray-trace-failure"
    OBSCURATION = "obscuration"
    CLEAR_APERTURE_BLOCK = "clear-aperture-block"
    UNKNOWN = "unknown"


class MachineListingFailure(StrEnum):
    """Deterministic failure class for a rejected Stage C listing segment."""

    SEGMENT_CARDINALITY = "segment-cardinality"
    STALE_OR_FOREIGN_RUN = "stale-or-foreign-run"
    MALFORMED_SEGMENT = "malformed-segment"
    DUPLICATE_METADATA = "duplicate-metadata"
    METADATA_MISMATCH = "metadata-mismatch"
    ERROR_BEARING_RECORD = "error-bearing-record"
    FIELD_SEGMENT_MISMATCH = "field-segment-mismatch"


class MachineListingParseError(ValueError):
    """Listing rejection carrying a stable machine-readable category."""

    def __init__(self, category: MachineListingFailure, message: str) -> None:
        super().__init__(message)
        self.category = category


class MachineMetricCount(BaseModel):
    """Raw valid/attempted sample counts retained for one metric at one field."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    valid: int = Field(ge=0)
    attempted: int = Field(ge=0)


class BoundMachineArtifact(BaseModel):
    """Artifact bytes and their digest; the digest is never accepted unbound."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    content_base64: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _digest_matches_bytes(self) -> BoundMachineArtifact:
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("artifact content_base64 is invalid") from exc
        if not payload:
            raise ValueError("bound artifact cannot be empty")
        if hashlib.sha256(payload).hexdigest() != self.sha256:
            raise ValueError("artifact SHA-256 does not match bound bytes")
        return self

    @classmethod
    def from_bytes(cls, payload: bytes) -> BoundMachineArtifact:
        if not payload:
            raise ValueError("bound artifact cannot be empty")
        return cls(
            content_base64=base64.b64encode(payload).decode("ascii"),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    def binding_valid(self) -> bool:
        try:
            payload = base64.b64decode(self.content_base64, validate=True)
        except (binascii.Error, ValueError):
            return False
        return bool(payload) and hashlib.sha256(payload).hexdigest() == self.sha256


class StageCMachinePerFieldReadback(BaseModel):
    """RIH definition and RSI chief-ray facts kept as distinct raw columns."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    field_index: int = Field(ge=0)
    normalized_fraction: float
    field_type: Literal["RIH"] = "RIH"
    definition_x_ri_mm: float
    definition_y_ri_mm: float
    rsi_actual_x_mm: float
    rsi_actual_y_mm: float
    rsi_direction_l: float
    rsi_direction_m: float
    rsi_direction_n: float
    rayrsi_return_code: int
    ray_error_code: int
    blocked_surface: int
    rms_spot_radius_um: float
    rms_wfe_waves: float
    vuy: float
    vly: float
    vux: float
    vlx: float
    rsi_samples: MachineMetricCount
    chief_ray_samples: MachineMetricCount
    spot_samples: MachineMetricCount
    wfe_samples: MachineMetricCount

    @computed_field
    @property
    def ray_classification(self) -> MachineRayClassification:
        if self.rayrsi_return_code != 0 or self.ray_error_code != 0:
            return MachineRayClassification.RAY_TRACE_FAILURE
        if self.blocked_surface < 0:
            return MachineRayClassification.OBSCURATION
        if self.blocked_surface > 0:
            return MachineRayClassification.CLEAR_APERTURE_BLOCK
        return MachineRayClassification.VALID


class StageCVignettingReadback(BaseModel):
    """Vignetting provenance without interpreting or generating CODE V syntax."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    classification: Literal["zero-verified", "nonzero-verified", "unknown"]
    provenance: Literal["machine-readback", "artifact", "unknown"]
    profile: tuple[float, ...] | None
    artifact_sha256: str | None = Field(None, pattern=r"^[0-9a-f]{64}$")


class StageCMachineReadback(BaseModel):
    """Complete structured input to the controlled machine-evidence factory.

    This is deliberately a readback container, not evidence: it contains no
    ``achieved`` or gate booleans for a caller to assert.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: Literal["atelier-stagec-machine-readback-v2"] = (
        "atelier-stagec-machine-readback-v2"
    )
    run_id: str = Field(min_length=1)
    field_type: Literal["RIH"] = "RIH"
    measured_efl_mm: float
    expected_samples_per_metric: int = Field(ge=2)
    fields: tuple[StageCMachinePerFieldReadback, ...]
    vignetting: StageCVignettingReadback
    listing_artifact: BoundMachineArtifact
    metrics_artifact: BoundMachineArtifact
    source_zmx_artifact: BoundMachineArtifact
    reconstructed_zmx_artifact: BoundMachineArtifact
    sequence_artifact: BoundMachineArtifact
    manifest_artifact: BoundMachineArtifact
    config_snapshot: dict[str, str | int | float | bool | None]
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    readback_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconstructed_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @computed_field
    @property
    def listing_sha256(self) -> str:
        return self.listing_artifact.sha256

    @computed_field
    @property
    def metrics_artifact_sha256(self) -> str:
        return self.metrics_artifact.sha256

    @model_validator(mode="after")
    def _bindings_are_canonical(self) -> StageCMachineReadback:
        artifacts = (
            self.listing_artifact,
            self.metrics_artifact,
            self.source_zmx_artifact,
            self.reconstructed_zmx_artifact,
            self.sequence_artifact,
            self.manifest_artifact,
        )
        if not all(artifact.binding_valid() for artifact in artifacts):
            raise ValueError("machine artifact byte binding is invalid")
        if self.source_zmx_sha256 != self.source_zmx_artifact.sha256:
            raise ValueError("source ZMX SHA-256 does not match bound bytes")
        if self.reconstructed_zmx_sha256 != self.reconstructed_zmx_artifact.sha256:
            raise ValueError("reconstructed ZMX SHA-256 does not match bound bytes")
        if _config_fingerprint(self.config_snapshot) != self.config_fingerprint:
            raise ValueError("config fingerprint does not match canonical snapshot")
        if _readback_fingerprint(self) != self.readback_fingerprint:
            raise ValueError("readback fingerprint does not match structured facts")
        return self


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _config_fingerprint(
    snapshot: Mapping[str, str | int | float | bool | None],
) -> str:
    try:
        payload = _canonical_json_bytes(dict(snapshot))
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(payload).hexdigest()


def _readback_fingerprint(readback: StageCMachineReadback) -> str:
    try:
        payload = readback.model_dump(
            mode="json",
            exclude={"readback_fingerprint"},
            exclude_computed_fields=True,
        )
        return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    except (TypeError, ValueError):
        return ""


class _StageCMachineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    field_type: Literal["RIH"]
    field_count: int = Field(ge=2)
    expected_samples_per_metric: int = Field(ge=2)
    vignetting_mode: Literal["zero-only"]


class _StageCMachineManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: Literal["atelier-stagec-machine-manifest-v1"]
    run_id: str = Field(min_length=1)
    source_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconstructed_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sequence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config: _StageCMachineConfig
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _config_is_bound(self) -> _StageCMachineManifest:
        if _config_fingerprint(self.config.model_dump()) != self.config_fingerprint:
            raise ValueError("manifest config fingerprint mismatch")
        return self


_METRICS_COLUMNS = (
    "record",
    "field_index",
    "normalized_fraction",
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
    "rms_spot_radius_um",
    "rms_wfe_waves",
    "rsi_valid",
    "rsi_attempted",
    "chief_valid",
    "chief_attempted",
    "spot_valid",
    "spot_attempted",
    "wfe_valid",
    "wfe_attempted",
    "vuy",
    "vly",
    "vux",
    "vlx",
)
_METRICS_META_KEYS = frozenset(
    {
        "schema_id",
        "run_id",
        "source_zmx_sha256",
        "reconstructed_zmx_sha256",
        "config_fingerprint",
        "field_type",
        "field_count",
        "expected_samples_per_metric",
        "measured_efl_mm",
    }
)


def _artifact_bytes(artifact: BoundMachineArtifact) -> bytes:
    return base64.b64decode(artifact.content_base64, validate=True)


def _strict_utf8(payload: bytes, label: str) -> str:
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be strict UTF-8") from exc
    if "\x00" in text:
        raise ValueError(f"{label} contains NUL")
    return text


def _parse_int(value: str, label: str) -> int:
    if not re.fullmatch(r"-?\d+", value):
        raise ValueError(f"{label} must be an integer")
    return int(value)


def _parse_float(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def _parse_metric_count(values: Mapping[str, str], prefix: str) -> MachineMetricCount:
    return MachineMetricCount(
        valid=_parse_int(values[f"{prefix}_valid"], f"{prefix}_valid"),
        attempted=_parse_int(values[f"{prefix}_attempted"], f"{prefix}_attempted"),
    )


def _parse_manifest(payload: bytes) -> _StageCMachineManifest:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("manifest contains duplicate JSON keys")
            result[key] = value
        return result

    try:
        raw = json.loads(
            _strict_utf8(payload, "manifest"), object_pairs_hook=reject_duplicate_keys
        )
    except json.JSONDecodeError as exc:
        raise ValueError("manifest must be strict JSON") from exc
    return _StageCMachineManifest.model_validate(raw)


def _parse_listing(
    payload: bytes,
    *,
    manifest: _StageCMachineManifest,
) -> None:
    lines = [line.rstrip("\r") for line in _strict_utf8(payload, "listing").splitlines()]
    begin = f"ATELIER_STAGEC_RUN_BEGIN\t{manifest.run_id}"
    end = f"ATELIER_STAGEC_RUN_END\t{manifest.run_id}"
    if lines.count(begin) != 1 or lines.count(end) != 1:
        raise MachineListingParseError(
            MachineListingFailure.SEGMENT_CARDINALITY,
            "listing requires one unique complete run segment",
        )
    stagec_markers = [line for line in lines if line.startswith("ATELIER_STAGEC_RUN_")]
    if stagec_markers != [begin, end]:
        raise MachineListingParseError(
            MachineListingFailure.STALE_OR_FOREIGN_RUN,
            "listing contains a stale, foreign, or partial Stage C run",
        )
    start, stop = lines.index(begin), lines.index(end)
    if stop <= start or any(line.startswith("ATELIER_STAGEC_RUN_") for line in lines[start + 1 : stop]):
        raise MachineListingParseError(
            MachineListingFailure.MALFORMED_SEGMENT,
            "listing run segment is nested, stale, or truncated",
        )
    segment = lines[start + 1 : stop]
    expected_meta = {
        "SCHEMA": "atelier-stagec-listing-v1",
        "SOURCE_ZMX_SHA256": manifest.source_zmx_sha256,
        "RECONSTRUCTED_ZMX_SHA256": manifest.reconstructed_zmx_sha256,
        "CONFIG_FINGERPRINT": manifest.config_fingerprint,
        "TYP_FLD": "RIH",
    }
    seen_meta: dict[str, str] = {}
    field_events: list[tuple[str, int]] = []
    for line in segment:
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] in expected_meta:
            if parts[0] in seen_meta:
                raise MachineListingParseError(
                    MachineListingFailure.DUPLICATE_METADATA,
                    "listing contains duplicate run metadata",
                )
            seen_meta[parts[0]] = parts[1]
        elif len(parts) == 2 and parts[0] in {"FIELD_BEGIN", "FIELD_OK", "FIELD_END"}:
            field_events.append((parts[0], _parse_int(parts[1], "listing field index")))
        else:
            raise MachineListingParseError(
                MachineListingFailure.ERROR_BEARING_RECORD,
                "listing contains unknown or error-bearing run record",
            )
    if seen_meta != expected_meta:
        raise MachineListingParseError(
            MachineListingFailure.METADATA_MISMATCH,
            "listing run metadata mismatch",
        )
    expected_events = [
        (event, index)
        for index in range(manifest.config.field_count)
        for event in ("FIELD_BEGIN", "FIELD_OK", "FIELD_END")
    ]
    if field_events != expected_events:
        raise MachineListingParseError(
            MachineListingFailure.FIELD_SEGMENT_MISMATCH,
            "listing field segments are incomplete, duplicated, or out of order",
        )


def _parse_metrics(
    payload: bytes,
    *,
    manifest: _StageCMachineManifest,
) -> tuple[float, tuple[StageCMachinePerFieldReadback, ...], tuple[float, ...]]:
    rows = list(csv.reader(io.StringIO(_strict_utf8(payload, "metrics")), delimiter="\t"))
    meta: dict[str, str] = {}
    cursor = 0
    while cursor < len(rows) and rows[cursor] and rows[cursor][0] == "META":
        row = rows[cursor]
        if len(row) != 3 or row[1] in meta:
            raise ValueError("metrics META rows must be unique key/value triples")
        meta[row[1]] = row[2]
        cursor += 1
    if set(meta) != _METRICS_META_KEYS:
        raise ValueError("metrics metadata schema is incomplete or contains unknown keys")
    expected_meta = {
        "schema_id": "atelier-stagec-machine-metrics-v1",
        "run_id": manifest.run_id,
        "source_zmx_sha256": manifest.source_zmx_sha256,
        "reconstructed_zmx_sha256": manifest.reconstructed_zmx_sha256,
        "config_fingerprint": manifest.config_fingerprint,
        "field_type": "RIH",
        "field_count": str(manifest.config.field_count),
        "expected_samples_per_metric": str(manifest.config.expected_samples_per_metric),
    }
    for key, value in expected_meta.items():
        if meta[key] != value:
            raise ValueError(f"metrics {key} does not match bound run artifacts")
    if cursor >= len(rows) or tuple(rows[cursor]) != _METRICS_COLUMNS:
        raise ValueError("metrics field table header does not match closed schema")
    cursor += 1
    data_rows = rows[cursor:]
    if len(data_rows) != manifest.config.field_count:
        raise ValueError("metrics field row count mismatch")
    fields: list[StageCMachinePerFieldReadback] = []
    vignetting: list[float] = []
    for expected_index, row in enumerate(data_rows):
        if len(row) != len(_METRICS_COLUMNS) or row[0] != "FIELD":
            raise ValueError("metrics contains malformed or unknown data row")
        values = dict(zip(_METRICS_COLUMNS, row, strict=True))
        index = _parse_int(values["field_index"], "field_index")
        if index != expected_index:
            raise ValueError("metrics field indices must be unique and contiguous")
        if values["field_type"] != "RIH":
            raise ValueError("metrics field_type must be exact RIH")
        field = StageCMachinePerFieldReadback(
            field_index=index,
            normalized_fraction=_parse_float(values["normalized_fraction"], "fraction"),
            field_type="RIH",
            definition_x_ri_mm=_parse_float(values["definition_x_ri_mm"], "XRI"),
            definition_y_ri_mm=_parse_float(values["definition_y_ri_mm"], "YRI"),
            rsi_actual_x_mm=_parse_float(values["rsi_actual_x_mm"], "RSI actual X"),
            rsi_actual_y_mm=_parse_float(values["rsi_actual_y_mm"], "RSI actual Y"),
            rsi_direction_l=_parse_float(values["rsi_direction_l"], "RSI L"),
            rsi_direction_m=_parse_float(values["rsi_direction_m"], "RSI M"),
            rsi_direction_n=_parse_float(values["rsi_direction_n"], "RSI N"),
            rayrsi_return_code=_parse_int(values["rayrsi_return_code"], "RAYRSI return"),
            ray_error_code=_parse_int(values["rer"], "RER"),
            blocked_surface=_parse_int(values["bls"], "BLS"),
            rms_spot_radius_um=_parse_float(values["rms_spot_radius_um"], "spot"),
            rms_wfe_waves=_parse_float(values["rms_wfe_waves"], "WFE"),
            vuy=_parse_float(values["vuy"], "VUY"),
            vly=_parse_float(values["vly"], "VLY"),
            vux=_parse_float(values["vux"], "VUX"),
            vlx=_parse_float(values["vlx"], "VLX"),
            rsi_samples=_parse_metric_count(values, "rsi"),
            chief_ray_samples=_parse_metric_count(values, "chief"),
            spot_samples=_parse_metric_count(values, "spot"),
            wfe_samples=_parse_metric_count(values, "wfe"),
        )
        fields.append(field)
        vignetting.append(max(abs(field.vuy), abs(field.vly), abs(field.vux), abs(field.vlx)))
    measured_efl = _parse_float(meta["measured_efl_mm"], "measured EFL")
    return measured_efl, tuple(fields), tuple(vignetting)


def build_stagec_machine_readback(
    *,
    listing_bytes: bytes,
    metrics_bytes: bytes,
    source_zmx_bytes: bytes,
    reconstructed_zmx_bytes: bytes,
    sequence_bytes: bytes,
    manifest_bytes: bytes,
) -> StageCMachineReadback:
    """Parse a closed synthetic contract; callers cannot supply machine facts."""

    listing = BoundMachineArtifact.from_bytes(listing_bytes)
    metrics = BoundMachineArtifact.from_bytes(metrics_bytes)
    source = BoundMachineArtifact.from_bytes(source_zmx_bytes)
    reconstructed = BoundMachineArtifact.from_bytes(reconstructed_zmx_bytes)
    sequence = BoundMachineArtifact.from_bytes(sequence_bytes)
    manifest_artifact = BoundMachineArtifact.from_bytes(manifest_bytes)
    manifest = _parse_manifest(manifest_bytes)
    if manifest.source_zmx_sha256 != source.sha256:
        raise ValueError("manifest source ZMX SHA-256 mismatch")
    if manifest.reconstructed_zmx_sha256 != reconstructed.sha256:
        raise ValueError("manifest reconstructed ZMX SHA-256 mismatch")
    if manifest.sequence_sha256 != sequence.sha256:
        raise ValueError("manifest sequence SHA-256 mismatch")
    _parse_listing(
        listing_bytes,
        manifest=manifest,
    )
    measured_efl, fields, vignetting_profile = _parse_metrics(
        metrics_bytes,
        manifest=manifest,
    )
    config_snapshot = manifest.config.model_dump()
    provisional = StageCMachineReadback.model_construct(
        schema_id="atelier-stagec-machine-readback-v2",
        run_id=manifest.run_id,
        field_type="RIH",
        measured_efl_mm=measured_efl,
        expected_samples_per_metric=manifest.config.expected_samples_per_metric,
        fields=fields,
        vignetting=StageCVignettingReadback(
            classification=(
                "zero-verified"
                if all(value == 0 for value in vignetting_profile)
                else "nonzero-verified"
            ),
            provenance="machine-readback",
            profile=vignetting_profile,
            artifact_sha256=metrics.sha256,
        ),
        listing_artifact=listing,
        metrics_artifact=metrics,
        source_zmx_artifact=source,
        reconstructed_zmx_artifact=reconstructed,
        sequence_artifact=sequence,
        manifest_artifact=manifest_artifact,
        config_snapshot=config_snapshot,
        config_fingerprint=manifest.config_fingerprint,
        readback_fingerprint="0" * 64,
        source_zmx_sha256=source.sha256,
        reconstructed_zmx_sha256=reconstructed.sha256,
    )
    payload = provisional.model_dump(mode="python", exclude_computed_fields=True)
    payload["readback_fingerprint"] = _readback_fingerprint(provisional)
    return StageCMachineReadback.model_validate(payload)


class StageCMachineFieldEvidence(BaseModel):
    """Factory-only machine evidence with gates derived from raw readback.

    Direct construction and generic ``model_validate`` are intentionally
    rejected. Persisted records must be re-established by feeding their raw
    readback through :func:`build_stagec_machine_evidence`, so serialized gate
    booleans can never become an authority source.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: Literal["atelier-stagec-machine-evidence-v2"] = (
        "atelier-stagec-machine-evidence-v2"
    )
    evidence_kind: Literal["machine"] = "machine"
    reconstruction: FieldReconstructionResult
    readback: StageCMachineReadback

    def __init__(self, **data: object) -> None:
        raise TypeError("Stage C machine evidence must be built by build_stagec_machine_evidence")

    @computed_field
    @property
    def target_image_height_mm(self) -> float:
        return self.reconstruction.target_image_height_mm

    @computed_field
    @property
    def target_efl_mm(self) -> float:
        return self.reconstruction.target_efl_mm

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
        return self.reconstruction.output_sha256 or self.readback.reconstructed_zmx_sha256

    @computed_field
    @property
    def reconstruction_applied(self) -> bool:
        return _machine_gate_state(self.reconstruction, self.readback)[0]

    @computed_field
    @property
    def imh_field_valid(self) -> bool:
        return _machine_gate_state(self.reconstruction, self.readback)[1]

    @computed_field
    @property
    def efl_constraint_held(self) -> bool:
        return _machine_gate_state(self.reconstruction, self.readback)[2]

    @computed_field
    @property
    def ray_metrics_valid(self) -> bool:
        return _machine_gate_state(self.reconstruction, self.readback)[3]

    @computed_field
    @property
    def machine_execution_status(self) -> Literal["verified", "invalid"]:
        return "verified" if self.image_height_achieved else "invalid"

    @computed_field
    @property
    def machine_execution_reason(self) -> str:
        if self.image_height_achieved:
            return "complete structured machine readback passed all four derived gates"
        return "structured machine readback failed one or more derived gates"

    @computed_field
    @property
    def reconstruction_status(self) -> Literal["constructed-verified", "invalid"]:
        return "constructed-verified" if self.reconstruction_applied else "invalid"

    @computed_field
    @property
    def imh_source(self) -> Literal[
        "constructed-machine-verified", "constructed-unverified"
    ]:
        return "constructed-machine-verified" if self.imh_field_valid else "constructed-unverified"

    @computed_field
    @property
    def fov_source(self) -> Literal["derived"]:
        return "derived"

    @computed_field
    @property
    def efl_constraint_status(self) -> Literal["held", "failed"]:
        return "held" if self.efl_constraint_held else "failed"

    @computed_field
    @property
    def ray_metrics_status(self) -> Literal["verified", "invalid"]:
        return "verified" if self.ray_metrics_valid else "invalid"

    @computed_field
    @property
    def real_chief_ray_status(self) -> Literal["verified", "invalid"]:
        return "verified" if _machine_gate_state(self.reconstruction, self.readback)[4] else "invalid"

    @computed_field
    @property
    def rsi_status(self) -> Literal["verified", "invalid"]:
        return self.real_chief_ray_status

    @computed_field
    @property
    def image_height_achieved(self) -> bool:
        return (
            self.reconstruction_applied
            and self.imh_field_valid
            and self.efl_constraint_held
            and self.ray_metrics_valid
        )

    @computed_field
    @property
    def note(self) -> str:
        if self.image_height_achieved:
            return "all four machine gates derived true; quantitative evidence only, [EXPERT] remains blank"
        return "one or more machine gates derived false; fail closed, [EXPERT] remains blank"

    @property
    def fov_attainment_label(self) -> Literal["derived"]:
        return "derived"


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def _full_count(count: MachineMetricCount, expected: int) -> bool:
    return expected >= 2 and count.attempted == expected and count.valid == expected


def _profile_matches(
    fields: tuple[StageCMachinePerFieldReadback, ...],
    expected: tuple[float, ...],
) -> bool:
    if len(fields) != len(expected):
        return False
    for index, (field, fraction) in enumerate(zip(fields, expected, strict=True)):
        if field.field_index != index or not _finite(field.normalized_fraction):
            return False
        assert field.normalized_fraction is not None
        if not math.isclose(field.normalized_fraction, fraction, rel_tol=1e-12, abs_tol=1e-12):
            return False
    return True


def _field_values_valid(
    fields: tuple[StageCMachinePerFieldReadback, ...],
    *,
    fractions: tuple[float, ...],
    target_image_height_mm: float,
    expected_samples_per_metric: int,
) -> tuple[bool, bool, bool]:
    """Return ``(imh, chief/rsi, ray metrics)`` from raw per-field facts."""

    imh_valid = True
    chief_rsi_valid = True
    ray_metrics_valid = True
    for field, fraction in zip(fields, fractions, strict=True):
        expected = fraction * target_image_height_mm
        if field.field_type != "RIH":
            imh_valid = False
        values = (
            field.definition_x_ri_mm,
            field.definition_y_ri_mm,
            field.rsi_actual_x_mm,
            field.rsi_actual_y_mm,
            field.rsi_direction_l,
            field.rsi_direction_m,
            field.rsi_direction_n,
        )
        if any(not _finite(value) for value in values):
            imh_valid = False
            chief_rsi_valid = False
        else:
            if field.definition_x_ri_mm != 0 or field.rsi_actual_x_mm != 0:
                imh_valid = False
                chief_rsi_valid = False
            if not math.isclose(
                field.definition_y_ri_mm, expected, rel_tol=1e-12, abs_tol=1e-12
            ):
                imh_valid = False
            if not math.isclose(field.rsi_actual_y_mm, expected, rel_tol=1e-12, abs_tol=1e-12):
                chief_rsi_valid = False
            direction_norm = math.sqrt(
                field.rsi_direction_l**2
                + field.rsi_direction_m**2
                + field.rsi_direction_n**2
            )
            if not math.isclose(direction_norm, 1.0, rel_tol=1e-9, abs_tol=1e-9):
                chief_rsi_valid = False
            if fraction != 0 and (
                field.definition_y_ri_mm == 0 or field.rsi_actual_y_mm == 0
            ):
                imh_valid = False
                chief_rsi_valid = False
        if not (
            _full_count(field.rsi_samples, expected_samples_per_metric)
            and _full_count(field.chief_ray_samples, expected_samples_per_metric)
        ):
            chief_rsi_valid = False
        if (
            field.ray_classification is not MachineRayClassification.VALID
            or not _finite(field.rms_spot_radius_um)
            or not _finite(field.rms_wfe_waves)
            or field.rms_spot_radius_um <= 0
            or field.rms_wfe_waves <= 0
            or not _full_count(field.spot_samples, expected_samples_per_metric)
            or not _full_count(field.wfe_samples, expected_samples_per_metric)
        ):
            ray_metrics_valid = False
    return imh_valid, chief_rsi_valid, ray_metrics_valid


def _readback_semantics_valid(readback: StageCMachineReadback) -> bool:
    """Reparse retained bytes so copied/rehydrated structured facts have no authority."""

    try:
        reparsed = build_stagec_machine_readback(
            listing_bytes=_artifact_bytes(readback.listing_artifact),
            metrics_bytes=_artifact_bytes(readback.metrics_artifact),
            source_zmx_bytes=_artifact_bytes(readback.source_zmx_artifact),
            reconstructed_zmx_bytes=_artifact_bytes(readback.reconstructed_zmx_artifact),
            sequence_bytes=_artifact_bytes(readback.sequence_artifact),
            manifest_bytes=_artifact_bytes(readback.manifest_artifact),
        )
    except (ValueError, binascii.Error):
        return False
    return reparsed == readback


def _machine_gate_state(
    reconstruction: FieldReconstructionResult,
    readback: StageCMachineReadback,
) -> tuple[bool, bool, bool, bool, bool]:
    """Derive four gates plus the shared chief-ray/RSI validity sub-gate."""

    artifact_ok = False
    if (
        reconstruction.status == "constructed"
        and reconstruction.output_path is not None
        and reconstruction.output_sha256 is not None
        and reconstruction.num_fields is not None
        and readback.reconstructed_zmx_sha256 == reconstruction.output_sha256
    ):
        try:
            parsed = validate_reconstructed_field_artifact(
                reconstruction.output_path,
                expected_num_fields=reconstruction.num_fields,
                expected_fractions=reconstruction.normalized_fractions,
                target_image_height_mm=reconstruction.target_image_height_mm,
            )
            artifact_ok = parsed.sha256 == reconstruction.output_sha256
        except (OSError, ValueError):
            artifact_ok = False

    profile_ok = _profile_matches(readback.fields, reconstruction.normalized_fractions)
    imh_values_ok = chief_rsi_ok = metrics_ok = False
    if profile_ok:
        imh_values_ok, chief_rsi_ok, metrics_ok = _field_values_valid(
            readback.fields,
            fractions=reconstruction.normalized_fractions,
            target_image_height_mm=reconstruction.target_image_height_mm,
            expected_samples_per_metric=readback.expected_samples_per_metric,
        )
    artifact_bindings_ok = (
        _readback_semantics_valid(readback)
        and readback.field_type == "RIH"
        and readback.listing_artifact.binding_valid()
        and readback.metrics_artifact.binding_valid()
        and _config_fingerprint(readback.config_snapshot) == readback.config_fingerprint
        and _readback_fingerprint(readback) == readback.readback_fingerprint
        and readback.config_snapshot.get("expected_samples_per_metric")
        == readback.expected_samples_per_metric
        and readback.config_snapshot.get("field_count") == len(readback.fields)
        and readback.config_snapshot.get("field_type") == "RIH"
        and readback.source_zmx_sha256 == reconstruction.source_sha256_before
    )
    vignetting_profile = readback.vignetting.profile
    provenance_sha_ok = False
    if readback.vignetting.provenance == "machine-readback":
        provenance_sha_ok = (
            readback.vignetting.artifact_sha256 == readback.metrics_artifact.sha256
        )
    vignetting_ok = (
        artifact_ok
        and artifact_bindings_ok
        and provenance_sha_ok
        and readback.vignetting.classification == "zero-verified"
        and vignetting_profile is not None
        and len(vignetting_profile) == len(reconstruction.normalized_fractions)
        and all(math.isfinite(value) for value in vignetting_profile)
        and readback.vignetting.artifact_sha256 is not None
        and all(
            math.isfinite(value) and value == 0
            for field in readback.fields
            for value in (field.vuy, field.vly, field.vux, field.vlx)
        )
    )
    if vignetting_ok:
        assert vignetting_profile is not None
        vignetting_ok = all(value == 0 for value in vignetting_profile)
    imh_field_valid = (
        artifact_ok
        and artifact_bindings_ok
        and readback.field_type == "RIH"
        and profile_ok
        and imh_values_ok
        and chief_rsi_ok
    )
    measured_efl = readback.measured_efl_mm
    efl_constraint_held = False
    if _finite(measured_efl) and measured_efl > 0 and artifact_bindings_ok:
        try:
            relative_error = abs(
                Decimal(str(measured_efl)) - Decimal(str(reconstruction.target_efl_mm))
            ) / Decimal(str(reconstruction.target_efl_mm))
            efl_constraint_held = relative_error < Decimal("0.02")
        except (InvalidOperation, ZeroDivisionError):
            efl_constraint_held = False
    ray_metrics_valid = (
        artifact_bindings_ok
        and profile_ok
        and chief_rsi_ok
        and metrics_ok
        and vignetting_ok
    )
    return (
        artifact_ok,
        imh_field_valid,
        efl_constraint_held,
        ray_metrics_valid,
        chief_rsi_ok and artifact_bindings_ok,
    )


def build_stagec_machine_evidence(
    *,
    reconstruction: FieldReconstructionResult,
    readback: StageCMachineReadback,
) -> StageCMachineFieldEvidence:
    """Derive the four-condition Stage C gate from complete structured facts.

    This function is pure/offline. It does not run, attach to, or parse CODE V;
    the machine-side reader is a separate, still-unimplemented boundary.
    """

    return StageCMachineFieldEvidence.model_construct(
        schema_id="atelier-stagec-machine-evidence-v2",
        evidence_kind="machine",
        reconstruction=reconstruction,
        readback=readback,
    )


def restore_stagec_machine_evidence(
    payload: Mapping[str, object],
) -> StageCMachineFieldEvidence:
    """Rebuild persisted machine evidence from raw facts, ignoring claimed gates.

    Canonical serialization includes computed fields for audit readability. On
    restore none of those conclusions is trusted: only ``reconstruction`` and
    ``readback`` are parsed, then the controlled factory derives every gate.
    """

    reconstruction = FieldReconstructionResult.model_validate(payload.get("reconstruction"))
    raw_readback = payload.get("readback")
    if not isinstance(raw_readback, Mapping):
        raise ValueError("persisted machine evidence requires structured readback")
    artifacts: dict[str, bytes] = {}
    for name in (
        "listing_artifact",
        "metrics_artifact",
        "source_zmx_artifact",
        "reconstructed_zmx_artifact",
        "sequence_artifact",
        "manifest_artifact",
    ):
        artifact_payload = raw_readback.get(name)
        artifact = BoundMachineArtifact.model_validate(artifact_payload)
        artifacts[name] = _artifact_bytes(artifact)
    readback = build_stagec_machine_readback(
        listing_bytes=artifacts["listing_artifact"],
        metrics_bytes=artifacts["metrics_artifact"],
        source_zmx_bytes=artifacts["source_zmx_artifact"],
        reconstructed_zmx_bytes=artifacts["reconstructed_zmx_artifact"],
        sequence_bytes=artifacts["sequence_artifact"],
        manifest_bytes=artifacts["manifest_artifact"],
    )
    return build_stagec_machine_evidence(reconstruction=reconstruction, readback=readback)


# Compatibility name for code that only needs the raw machine readback shape.
StageCMachineFieldResult = StageCMachineReadback
