"""Phase 16 Stage C field-target resolution and offline ZMX reconstruction.

This module deliberately stops at the last operation proven without CODE V:
rewrite a temporary Zemax field table from angular (FTYP 0) to image-height
(FTYP 3).  Real chief-ray/RSI verification and CODE V syntax are separate,
pending machine evidence.  A constructed field is therefore never evidence of
an optimized or measured target by itself.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import uuid
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, computed_field, model_validator


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
    """Classification emitted by a machine-side reader, never inferred here."""

    VALID = "valid"
    VIGNETTED = "vignetted"
    MISSED = "missed"
    UNKNOWN = "unknown"


class MachineMetricCount(BaseModel):
    """Raw valid/attempted sample counts retained for one metric at one field."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    valid: int = Field(ge=0)
    attempted: int = Field(ge=0)


class StageCMachinePerFieldReadback(BaseModel):
    """Structured facts for one field. Zero/None remain visible sentinel facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    field_index: int = Field(ge=0)
    normalized_fraction: float | None
    field_readback_mm: float | None
    rsi_image_height_mm: float | None
    chief_ray_image_height_mm: float | None
    rms_spot_radius_um: float | None
    rms_wfe_waves: float | None
    rsi_samples: MachineMetricCount
    chief_ray_samples: MachineMetricCount
    spot_samples: MachineMetricCount
    wfe_samples: MachineMetricCount
    ray_classification: MachineRayClassification


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
    schema_id: Literal["atelier-stagec-machine-readback-v1"] = (
        "atelier-stagec-machine-readback-v1"
    )
    field_coordinate_classification: Literal["image-height", "angle", "unknown"]
    measured_efl_mm: float | None
    fields: tuple[StageCMachinePerFieldReadback, ...]
    vignetting: StageCVignettingReadback
    listing_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reconstructed_zmx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metrics_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class StageCMachineFieldEvidence(BaseModel):
    """Factory-only machine evidence with gates derived from raw readback.

    Direct construction and generic ``model_validate`` are intentionally
    rejected. Persisted records must be re-established by feeding their raw
    readback through :func:`build_stagec_machine_evidence`, so serialized gate
    booleans can never become an authority source.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_id: Literal["atelier-stagec-machine-evidence-v1"] = (
        "atelier-stagec-machine-evidence-v1"
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


def _full_count(count: MachineMetricCount) -> bool:
    return count.attempted > 0 and count.valid == count.attempted


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
) -> tuple[bool, bool, bool]:
    """Return ``(imh, chief/rsi, ray metrics)`` from raw per-field facts."""

    imh_valid = True
    chief_rsi_valid = True
    ray_metrics_valid = True
    for field, fraction in zip(fields, fractions, strict=True):
        expected = fraction * target_image_height_mm
        values = (
            field.field_readback_mm,
            field.rsi_image_height_mm,
            field.chief_ray_image_height_mm,
        )
        if any(not _finite(value) for value in values):
            imh_valid = False
            chief_rsi_valid = False
        else:
            assert all(value is not None for value in values)
            if not math.isclose(field.field_readback_mm, expected, rel_tol=1e-12, abs_tol=1e-12):
                imh_valid = False
            if not math.isclose(field.rsi_image_height_mm, expected, rel_tol=1e-12, abs_tol=1e-12):
                chief_rsi_valid = False
            if not math.isclose(
                field.chief_ray_image_height_mm, expected, rel_tol=1e-12, abs_tol=1e-12
            ):
                chief_rsi_valid = False
            # A zero at the axial field is physical; at a non-zero field it is
            # an unresolved/sentinel readback and fails closed.
            if fraction != 0 and any(value == 0 for value in values):
                imh_valid = False
                chief_rsi_valid = False
        if not (_full_count(field.rsi_samples) and _full_count(field.chief_ray_samples)):
            chief_rsi_valid = False
        if (
            field.ray_classification is not MachineRayClassification.VALID
            or not _finite(field.rms_spot_radius_um)
            or not _finite(field.rms_wfe_waves)
            or field.rms_spot_radius_um <= 0
            or field.rms_wfe_waves <= 0
            or not _full_count(field.spot_samples)
            or not _full_count(field.wfe_samples)
        ):
            ray_metrics_valid = False
    return imh_valid, chief_rsi_valid, ray_metrics_valid


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
        )
    vignetting_profile = readback.vignetting.profile
    vignetting_ok = (
        readback.vignetting.classification != "unknown"
        and readback.vignetting.provenance != "unknown"
        and vignetting_profile is not None
        and len(vignetting_profile) == len(reconstruction.normalized_fractions)
        and all(math.isfinite(value) for value in vignetting_profile)
        and readback.vignetting.artifact_sha256 is not None
    )
    if vignetting_ok:
        assert vignetting_profile is not None
        if readback.vignetting.classification == "zero-verified":
            vignetting_ok = all(value == 0 for value in vignetting_profile)
        elif readback.vignetting.classification == "nonzero-verified":
            vignetting_ok = any(value != 0 for value in vignetting_profile)
    imh_field_valid = (
        artifact_ok
        and readback.field_coordinate_classification == "image-height"
        and profile_ok
        and imh_values_ok
        and chief_rsi_ok
    )
    measured_efl = readback.measured_efl_mm
    efl_constraint_held = (
        _finite(measured_efl)
        and measured_efl > 0
        and abs(measured_efl - reconstruction.target_efl_mm)
        / reconstruction.target_efl_mm
        < 0.02
    )
    ray_metrics_valid = profile_ok and chief_rsi_ok and metrics_ok and vignetting_ok
    return artifact_ok, imh_field_valid, efl_constraint_held, ray_metrics_valid, chief_rsi_ok


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
        schema_id="atelier-stagec-machine-evidence-v1",
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
    readback = StageCMachineReadback.model_validate(payload.get("readback"))
    return build_stagec_machine_evidence(reconstruction=reconstruction, readback=readback)


# Compatibility name for code that only needs the raw machine readback shape.
StageCMachineFieldResult = StageCMachineReadback
