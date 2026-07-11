"""Offline-safe glass snap planning, macro building, and verification models.

The functions in this module never execute CODE V.  Macro grammar newly used by
the builder is intentionally labelled pending licensed-runtime verification.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.core.engines.codev_batch import ensure_codev_safe_input_path
from app.core.engines.codev_readout import CodeVReadout
from app.core.engines.glass_snap import CatalogEntry, SnapResult, snap_glass

UNVALIDATED_DEFAULT_SNAP_TOLERANCE = 0.01
UNVALIDATED_DEFAULT_SHORT_AUT_MAX_CYCLES = 5
UNVALIDATED_DEFAULT_SHORT_AUT_MIN_CYCLES = 1
_AIR_NAMES = {"", "AIR", "NONE", "NULL"}


@dataclass(frozen=True)
class MaterialIntervalClaim:
    """One assertion about the medium between two adjacent sequential surfaces."""

    start_surface: int
    end_surface: int
    thickness_mm: float | None
    glass_name: str | None
    nd: float | None
    vd: float | None
    surface_type: str | None = None


@dataclass(frozen=True)
class MaterialRegionIdentity:
    region_id: str
    start_surface: int
    end_surface: int
    thickness_mm: float
    source_glass_name: str
    nd: float
    vd: float
    cemented_before: bool
    cemented_after: bool


@dataclass(frozen=True)
class IdentityBuildResult:
    regions: tuple[MaterialRegionIdentity, ...]
    withheld_reasons: tuple[str, ...]

    @property
    def writable(self) -> bool:
        return bool(self.regions) and not self.withheld_reasons


def material_claims_from_readout(readout: CodeVReadout) -> tuple[MaterialIntervalClaim, ...]:
    """Translate CODE V's surface-medium convention into adjacent intervals."""

    if readout.num_zooms != 1:
        return ()
    return tuple(
        MaterialIntervalClaim(
            start_surface=s.index,
            end_surface=s.index + 1,
            thickness_mm=s.thickness_mm,
            glass_name=s.glass,
            nd=s.nd,
            vd=s.vd,
            surface_type=s.surface_type,
        )
        for s in readout.surfaces
        if _is_glass(s.glass, s.nd)
    )


def build_material_region_identities(
    claims: tuple[MaterialIntervalClaim, ...], *, num_zooms: int = 1
) -> IdentityBuildResult:
    """Build unique material intervals; ambiguity is a pre-write hard gate."""

    reasons: list[str] = []
    if num_zooms != 1:
        reasons.append("zoom identity is not uniquely supported")
    grouped: dict[tuple[int, int], list[MaterialIntervalClaim]] = {}
    for claim in claims:
        grouped.setdefault((claim.start_surface, claim.end_surface), []).append(claim)
    valid: list[MaterialIntervalClaim] = []
    for key, group in sorted(grouped.items()):
        if key[1] != key[0] + 1:
            reasons.append(f"non-adjacent material interval {key}")
            continue
        signatures = {(c.glass_name, c.nd, c.vd, c.thickness_mm) for c in group}
        if len(signatures) != 1:
            reasons.append(f"conflicting material declarations for interval {key}")
            continue
        claim = group[0]
        if claim.surface_type and claim.surface_type.upper() == "NSS":
            reasons.append(f"NSS interval {key} cannot be uniquely identified")
            continue
        if not _positive_finite(claim.thickness_mm):
            reasons.append(f"interval {key} has missing/non-positive thickness")
            continue
        if not _valid_nd_vd(claim.nd, claim.vd):
            reasons.append(f"interval {key} has invalid Nd/Vd")
            continue
        if not claim.glass_name or claim.glass_name.strip().upper() in _AIR_NAMES:
            reasons.append(f"interval {key} has no material name")
            continue
        valid.append(claim)
    regions = tuple(
        MaterialRegionIdentity(
            region_id=f"z1:s{c.start_surface}-s{c.end_surface}",
            start_surface=c.start_surface,
            end_surface=c.end_surface,
            thickness_mm=float(c.thickness_mm),
            source_glass_name=str(c.glass_name).strip(),
            nd=float(c.nd),
            vd=float(c.vd),
            cemented_before=any(x.end_surface == c.start_surface for x in valid),
            cemented_after=any(x.start_surface == c.end_surface for x in valid),
        )
        for c in valid
    )
    if not regions:
        reasons.append("no uniquely identifiable glass material intervals")
    return IdentityBuildResult(regions, tuple(dict.fromkeys(reasons)))


@dataclass(frozen=True)
class SnapProposal:
    region: MaterialRegionIdentity
    result: SnapResult
    spectral_definition: str
    dispersion_weight: float
    disposition: str
    reason: str


def propose_material_snaps(
    identity: IdentityBuildResult,
    catalog: tuple[CatalogEntry, ...],
    *,
    spectral_definition: str,
    catalog_spectral_definition: str,
    tolerance: float = UNVALIDATED_DEFAULT_SNAP_TOLERANCE,
    dispersion_weight: float = 1.0,
) -> tuple[SnapProposal, ...]:
    """Propose once per identity; the uncalibrated threshold never authorizes writes."""

    if not identity.writable:
        return ()
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and non-negative")
    proposals: list[SnapProposal] = []
    for region in identity.regions:
        raw = snap_glass(
            region.nd,
            region.vd,
            catalog,
            spectral_definition=spectral_definition,
            catalog_spectral_definition=catalog_spectral_definition,
            dispersion_weight=dispersion_weight,
        )
        result = replace(raw, tolerance=tolerance)
        within = result.within_tolerance
        proposals.append(
            SnapProposal(
                region=region,
                result=result,
                spectral_definition=spectral_definition,
                dispersion_weight=dispersion_weight,
                disposition="proposed" if within else "keep-fictitious",
                reason=(
                    "within uncalibrated proposal tolerance; write-back still requires verification"
                    if within
                    else "nearest catalog entry exceeds uncalibrated proposal tolerance"
                ),
            )
        )
    return tuple(proposals)


def build_glass_freeze_reopt_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
    proposals: tuple[SnapProposal, ...],
    session_run_id: str,
    configuration_fingerprint: str,
    max_cycles: int = UNVALIDATED_DEFAULT_SHORT_AUT_MAX_CYCLES,
    min_cycles: int = UNVALIDATED_DEFAULT_SHORT_AUT_MIN_CYCLES,
    apply_snaps: bool = True,
    run_aut: bool = True,
) -> str:
    """Build only: catalog assignment/freeze/AUT grammar awaits real-machine verification."""

    if not session_run_id.strip() or not configuration_fingerprint.strip():
        raise ValueError("session_run_id and configuration_fingerprint are required")
    if max_cycles < 1 or min_cycles < 1 or min_cycles > max_cycles:
        raise ValueError("cycle budget must satisfy 1 <= min_cycles <= max_cycles")
    ensure_codev_safe_input_path(source_zmx, role="source_zmx")
    accepted = [p for p in proposals if p.disposition == "proposed" and p.result.entry]
    if apply_snaps and (len(accepted) != len(proposals) or not accepted):
        raise ValueError("every material identity needs one in-tolerance proposal")
    if len({p.region.region_id for p in accepted}) != len(accepted):
        raise ValueError("each material identity must appear exactly once")
    lines = [
        "! P13 glass snap chain; NEW glass assignment/freeze grammar pending real-machine verification.",
        "OUT NO",
        f'IN CV_MACRO:ZEMAXOS_TO_CV "{Path(source_zmx).as_posix()}"',
        *_snapshot_block("before-fictitious", session_run_id, configuration_fingerprint),
    ]
    for proposal in accepted if apply_snaps else ():
        entry = proposal.result.entry
        if entry is None:  # Defensive: accepted filter above should make this unreachable.
            raise ValueError("accepted proposal is missing its catalog entry")
        s = proposal.region.start_surface
        lines += [
            f"! catalog={entry.catalog_id} name={entry.glass_name} version={entry.version}",
            f"! explicit offline Nd={entry.nd:.12g} Vd={entry.vd:.12g}",
            f"GLA S{s} {entry.nd:.12g}:{entry.vd:.12g}",
            # Freeze = declare NO glass variable at all (opt3 precedent:
            # "GLC Sk 0" *opens* glass as an AUT variable; an unverified
            # "GLC Sk 100" freeze guess risks the opposite semantics).
            # The matrix C-arm readback proves glass stayed frozen.
        ]
    lines += _snapshot_block("after-snap-frozen", session_run_id, configuration_fingerprint)
    if run_aut:
        lines += [
            "AUT",
            "  SUR N",
            "  CHG SA",
            "  ! GLC intentionally absent: glass remains frozen",
            "  ! Existing authorized ASP A..G DOF only; pending real-machine verification",
            "  FOR ^s 1 (NUM S)",
            '    IF (TYP SUR S^s) = "ASP"',
            *[f"      {c}C S^s 0" for c in "ABCDEFG"],
            "    END IF",
            "  END FOR",
            f"  MXC {max_cycles}",
            f"  MNC {min_cycles}",
            "  IMP 0.001",
            "GO",
        ]
    lines += [
        *_snapshot_block("after-snap-reopt", session_run_id, configuration_fingerprint),
        *_snapshot_export_block(session_run_id, configuration_fingerprint),
        f'BUF EXP B1 "{Path(result_path).as_posix()}"',
        "BUF DEL B1",
        "OUT YES",
        "EXI YES",
        "",
    ]
    return "\n".join(lines)


def _snapshot_export_block(run_id: str, fingerprint: str) -> list[str]:
    lines = ["^row == 1"]
    for key, value in (
        ("schema", '"atelier-glass-snap-snapshots-v1"'),
        ("status", '"ok"'),
        ("session_run_id", f'"{run_id}"'),
        ("configuration_fingerprint", f'"{fingerprint}"'),
    ):
        lines += [f'BUF PUT B1 I^row J1 "{key}"', f"BUF PUT B1 I^row J2 {value}", "^row == ^row+1"]
    for stage in ("before_fictitious", "after_snap_frozen", "after_snap_reopt"):
        for metric in ("efl", "rmswfe"):
            key = f"{stage.replace('_', '-')}.{metric}"
            lines += [
                f'BUF PUT B1 I^row J1 "{key}"',
                f"BUF PUT B1 I^row J2 ^{stage}_{metric}",
                "^row == ^row+1",
            ]
    return lines


def _snapshot_block(stage: str, run_id: str, fingerprint: str) -> list[str]:
    """Structural placeholder using established EFY/RMSWE calls; values come only from CODE V."""

    prefix = stage.replace("-", "_")
    return [
        f"! SNAPSHOT {stage} run={run_id} config={fingerprint}",
        f"^{prefix}_efl == ABSF((EFY))",
        f"^{prefix}_rmswfe == 0",
        f"^ok == RMSWE(1,0,60,^{prefix}_rmswfe,'NOM')",
        "! per-field/per-wavelength RMS spot, chromatic detail: pending real-machine macro verification",
    ]


class MaterialIdentity(StrEnum):
    FICTITIOUS = "fictitious"
    CATALOG_NATIVE = "catalog-native"
    CATALOG_SNAPPED = "catalog-snapped"
    CATALOG_CONFLICT = "catalog-conflict"


class SnapVerificationStatus(StrEnum):
    COMPLETE = "complete"
    UNAVAILABLE = "unavailable"
    INCONSISTENT = "inconsistent"
    AUT_FAILED = "aut-failed"


class SnapshotMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: str
    session_run_id: str
    prescription_hash: str
    configuration_fingerprint: str
    efl_mm: Annotated[float, Field(allow_inf_nan=False)]
    rms_spot_um: tuple[Annotated[float, Field(allow_inf_nan=False)], ...]
    rms_wfe_waves: tuple[Annotated[float, Field(allow_inf_nan=False)], ...]
    lateral_color_um: tuple[Annotated[float, Field(allow_inf_nan=False)], ...]
    axial_color_mm: tuple[Annotated[float, Field(allow_inf_nan=False)], ...]


class ElementSnapLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    region_id: str
    planned_catalog_identity: tuple[str, str, str]
    readback_catalog_identity: tuple[str, str, str] | None = None
    readback_matches: bool = False


class SnapVerification(BaseModel):
    """Closed, fail-closed two-axis provenance summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    source_was_fictitious: bool
    aut_completed: bool
    ledger: tuple[ElementSnapLedger, ...]
    snapshots: tuple[SnapshotMetrics, ...]

    @model_validator(mode="after")
    def validate_unique_ledger(self) -> SnapVerification:
        ids = [item.region_id for item in self.ledger]
        if len(ids) != len(set(ids)):
            raise ValueError("ledger region_id must be unique")
        return self

    @computed_field
    @property
    def snap_verification_status(self) -> SnapVerificationStatus:
        by_stage = {item.stage: item for item in self.snapshots}
        required = {"before-fictitious", "after-snap-frozen", "after-snap-reopt"}
        if set(by_stage) != required:
            return SnapVerificationStatus.UNAVAILABLE
        if not self.aut_completed:
            return SnapVerificationStatus.AUT_FAILED
        axes = {
            (s.session_run_id, s.prescription_hash, s.configuration_fingerprint)
            for s in self.snapshots
        }
        if len(axes) != 1:
            return SnapVerificationStatus.INCONSISTENT
        return SnapVerificationStatus.COMPLETE

    @computed_field
    @property
    def material_identity(self) -> MaterialIdentity:
        ledger_conflict = any(
            not item.readback_matches
            or item.readback_catalog_identity != item.planned_catalog_identity
            for item in self.ledger
        )
        if ledger_conflict:
            return MaterialIdentity.CATALOG_CONFLICT
        if (
            self.source_was_fictitious
            and self.ledger
            and self.snap_verification_status is SnapVerificationStatus.COMPLETE
        ):
            return MaterialIdentity.CATALOG_SNAPPED
        if self.source_was_fictitious:
            return MaterialIdentity.FICTITIOUS
        return MaterialIdentity.CATALOG_NATIVE


def configuration_fingerprint(payload: dict[str, object]) -> str:
    """Stable digest for focus/aperture/field/wavelength/vignetting/zoom configuration."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def _is_glass(name: str | None, nd: float | None) -> bool:
    return bool(name and name.strip().upper() not in _AIR_NAMES and nd is not None and nd > 1.05)


def _positive_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _valid_nd_vd(nd: float | None, vd: float | None) -> bool:
    return (
        nd is not None
        and vd is not None
        and math.isfinite(nd)
        and math.isfinite(vd)
        and nd > 1
        and vd > 0
    )
