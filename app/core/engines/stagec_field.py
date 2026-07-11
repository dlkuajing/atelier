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
import re
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class FieldTargetStatus(StrEnum):
    RESOLVED = "resolved"
    CONFLICT = "conflict"
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

    if efl_mm is None or not math.isfinite(efl_mm) or efl_mm <= 0:
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
    imh_ok = image_height_mm is not None and math.isfinite(image_height_mm) and image_height_mm > 0
    fov_ok = full_fov_deg is not None and math.isfinite(full_fov_deg) and 0 < full_fov_deg < 180
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
    num_fields: int | None
    normalized_fractions: tuple[float, ...]
    target_image_height_mm: float
    field_type_before: int | None
    field_type_after: Literal[3] | None
    line_endings: Literal["LF"] | None
    vignetting_status: Literal["zero", "nonzero-unverified", "unavailable"]
    reason: str

    @model_validator(mode="after")
    def _source_unchanged(self) -> FieldReconstructionResult:
        if self.source_sha256_before != self.source_sha256_after:
            raise ValueError("source ZMX changed during temporary reconstruction")
        if self.status == "constructed" and (
            self.output_path is None
            or self.field_type_after != 3
            or self.line_endings != "LF"
            or self.vignetting_status != "zero"
        ):
            raise ValueError("constructed result requires a complete zero-vignetting FTYP3 artifact")
        return self


_FIELD_LINE = re.compile(r"^(?P<key>FTYP|XFLN|YFLN|VDXN|VDYN|VCXN|VCYN)\s+(?P<body>.*)$")


def _floats(body: str) -> tuple[float, ...]:
    return tuple(float(token) for token in body.split())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reconstruct_image_fields(
    *, source_zmx: str | Path, output_zmx: str | Path, target_image_height_mm: float
) -> FieldReconstructionResult:
    """Create a LF-only temporary FTYP3 ZMX, or fail closed before writing."""

    source = Path(source_zmx)
    output = Path(output_zmx)
    if not math.isfinite(target_image_height_mm) or target_image_height_mm <= 0:
        raise ValueError("target_image_height_mm must be positive and finite")
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
        "num_fields": num_fields,
        "normalized_fractions": fractions,
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
    fractions = tuple(abs(value) / edge for value in yfln)
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
    output.write_bytes(("\n".join(rebuilt) + "\n").encode("utf-8"))
    return FieldReconstructionResult(
        status="constructed", output_path=str(output), source_sha256_after=_sha256(source),
        field_type_after=3, line_endings="LF", vignetting_status="zero",
        reason="temporary FTYP3/YFLN artifact constructed; real chief-ray verification pending",
        **{key: value for key, value in base.items() if key not in {"output_path", "source_sha256_after", "field_type_after", "line_endings"}},
    )


class StageCFieldEvidence(BaseModel):
    """Closed Stage C evidence; four booleans cannot be supplied independently."""

    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["atelier-p16-stagec-field-v1"] = "atelier-p16-stagec-field-v1"
    reconstruction_status: Literal["not-applied", "constructed", "constructed-verified"]
    imh_source: Literal["constructed", "unavailable"]
    fov_source: Literal["derived", "measured", "unavailable"]
    efl_constraint_status: Literal["held", "failed", "unverified"]
    ray_metrics_status: Literal["valid", "invalid", "pending"]
    real_chief_ray_status: Literal["verified", "pending", "failed"]
    rsi_status: Literal["verified", "pending", "failed"]
    target_image_height_mm: float | None
    nominal_image_height_mm: float | None
    derived_full_fov_deg: float | None
    measured_full_fov_deg: float | None
    reconstruction_applied: StrictBool
    imh_field_valid: StrictBool
    efl_constraint_held: StrictBool
    ray_metrics_valid: StrictBool
    note: str = Field(min_length=1)

    @model_validator(mode="after")
    def _derive_and_close(self) -> StageCFieldEvidence:
        expected = (
            self.reconstruction_status != "not-applied",
            self.reconstruction_status == "constructed-verified"
            and self.imh_source == "constructed"
            and self.real_chief_ray_status == "verified"
            and self.rsi_status == "verified",
            self.efl_constraint_status == "held",
            self.ray_metrics_status == "valid",
        )
        actual = (
            self.reconstruction_applied,
            self.imh_field_valid,
            self.efl_constraint_held,
            self.ray_metrics_valid,
        )
        if actual != expected:
            raise ValueError(f"Stage C four-condition flags disagree with typed evidence: {actual=}, {expected=}")
        if all(actual) and (
            self.real_chief_ray_status != "verified" or self.rsi_status != "verified"
        ):
            raise ValueError("Stage C cannot close before real chief-ray and RSI verification")
        return self

    @property
    def image_height_achieved(self) -> bool:
        return all(
            (self.reconstruction_applied, self.imh_field_valid, self.efl_constraint_held, self.ray_metrics_valid)
        )

    @property
    def fov_attainment_label(self) -> Literal["derived", "measured", "unavailable"]:
        return self.fov_source
