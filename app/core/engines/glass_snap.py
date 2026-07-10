"""Deterministic offline proposals from fictitious glass to catalog entries.

This module deliberately does not authorize a CODE V material write-back.  Its
temporary metric and tolerance only rank and annotate proposals pending
same-spectral-definition, per-element calibration on the licensed runtime.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from app.core.zmx_materials import MATERIAL_ND_VD

DEFAULT_SNAP_TOLERANCE = 0.01
DEFAULT_DISPERSION_WEIGHT = 1.0
PLASTIC_GLASS_NAMES = (
    "ZEONEX-E48R",
    "OKP1",
    "EP8000",
    "APL5014CL",
    "SP3810",
)


@dataclass(frozen=True)
class CatalogEntry:
    """One versioned catalog identity; glass names alone are not unique."""

    catalog_id: str
    glass_name: str
    version: str
    nd: float
    vd: float


@dataclass(frozen=True)
class SnapResult:
    """Nearest proposal with its complete catalog identity."""

    entry: CatalogEntry | None
    distance: float | None
    delta_nd: float | None
    delta_dn: float | None
    tolerance: float = DEFAULT_SNAP_TOLERANCE

    @property
    def within_tolerance(self) -> bool:
        """Whether the proposal meets the uncalibrated Atelier threshold."""

        return self.entry is not None and self.distance is not None and self.distance <= self.tolerance


def build_plastic_catalog() -> tuple[CatalogEntry, ...]:
    """Build the explicitly allow-listed five-entry offline plastic catalog."""

    return tuple(
        CatalogEntry("atelier-plastics", name, "zmx-materials-v1", *MATERIAL_ND_VD[name])
        for name in PLASTIC_GLASS_NAMES
    )


def snap_glass(
    nd: float,
    vd: float,
    catalog: Iterable[CatalogEntry],
    *,
    spectral_definition: str,
    catalog_spectral_definition: str,
    dispersion_weight: float = DEFAULT_DISPERSION_WEIGHT,
) -> SnapResult:
    """Return the nearest catalog proposal in the Atelier metric.

    Target and catalog values are comparable only when their non-empty spectral
    definition provenance strings are identical.  Every malformed input raises
    ``ValueError`` and invalidates the whole operation.  The result is a proposal,
    never permission to write a glass name into CODE V.
    """

    target_nd, target_vd = _validate_nd_vd(nd, vd, label="target")
    target_provenance = _validate_text(spectral_definition, label="target spectral definition")
    catalog_provenance = _validate_text(
        catalog_spectral_definition, label="catalog spectral definition"
    )
    if target_provenance != catalog_provenance:
        raise ValueError("target and catalog spectral definitions must match")
    weight = _validate_weight(dispersion_weight)

    try:
        entries = tuple(catalog)
    except TypeError as exc:
        raise ValueError("catalog must be an iterable of CatalogEntry") from exc
    validated: list[CatalogEntry] = []
    identities: set[tuple[str, str, str]] = set()
    for position, entry in enumerate(entries):
        if not isinstance(entry, CatalogEntry):
            raise ValueError(f"catalog entry {position} must be a CatalogEntry")
        catalog_id = _validate_text(entry.catalog_id, label=f"catalog entry {position} catalog_id")
        glass_name = _validate_text(entry.glass_name, label=f"catalog entry {position} glass_name")
        version = _validate_text(entry.version, label=f"catalog entry {position} version")
        entry_nd, entry_vd = _validate_nd_vd(
            entry.nd, entry.vd, label=f"catalog entry {position}"
        )
        identity = (catalog_id, glass_name, version)
        if identity in identities:
            raise ValueError(f"duplicate catalog identity: {identity!r}")
        identities.add(identity)
        validated.append(CatalogEntry(catalog_id, glass_name, version, entry_nd, entry_vd))

    if not validated:
        return SnapResult(None, None, None, None)

    target_dn = (target_nd - 1.0) / target_vd
    candidates: list[tuple[float, tuple[str, str, str], CatalogEntry, float, float]] = []
    for entry in validated:
        delta_nd = target_nd - entry.nd
        delta_dn = target_dn - (entry.nd - 1.0) / entry.vd
        distance = math.hypot(delta_nd, weight * delta_dn)
        identity = (entry.catalog_id, entry.glass_name, entry.version)
        candidates.append((distance, identity, entry, delta_nd, delta_dn))

    distance, _, entry, delta_nd, delta_dn = min(candidates, key=lambda candidate: candidate[:2])
    return SnapResult(entry, distance, delta_nd, delta_dn)


def _validate_text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_weight(value: object) -> float:
    try:
        weight = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("dispersion_weight must be finite and non-negative") from exc
    if not math.isfinite(weight) or weight < 0:
        raise ValueError("dispersion_weight must be finite and non-negative")
    return weight


def _validate_nd_vd(nd: object, vd: object, *, label: str) -> tuple[float, float]:
    try:
        numeric_nd = float(nd)  # type: ignore[arg-type]
        numeric_vd = float(vd)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} nd/vd must be numeric") from exc
    if not math.isfinite(numeric_nd) or numeric_nd <= 1.0:
        raise ValueError(f"{label} nd must be finite and greater than 1")
    if not math.isfinite(numeric_vd) or numeric_vd <= 0:
        raise ValueError(f"{label} vd must be finite and positive")
    return numeric_nd, numeric_vd
