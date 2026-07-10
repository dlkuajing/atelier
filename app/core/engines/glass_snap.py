"""Deterministic offline matching from fictitious glass to real catalog entries."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

# Distance is measured in the (Nd, dn=(Nd-1)/Vd) plane.  A match at or below
# this limit is accepted; a farther nearest neighbour is reported but not snapped.
DEFAULT_SNAP_TOLERANCE = 0.01


@dataclass(frozen=True)
class SnapResult:
    """Nearest-catalog result; ``glass_name=None`` means fail-closed."""

    glass_name: str | None
    nd: float | None
    vd: float | None
    distance: float | None
    delta_nd: float | None
    delta_dn: float | None
    tolerance: float = DEFAULT_SNAP_TOLERANCE

    @property
    def snapped(self) -> bool:
        return self.glass_name is not None


def snap_glass(
    nd: float,
    vd: float,
    catalog: Mapping[str, tuple[float, float]],
    *,
    disp_factor: float = 1.0,
) -> SnapResult:
    """Return the nearest real glass when it is within the acceptance tolerance.

    The metric mirrors CODE V's ``GLASSFIT`` matching coordinates::

        sqrt((Nd_target - Nd_catalog)**2
             + (disp_factor * (dn_target - dn_catalog))**2)

    where ``dn = (Nd - 1) / Vd``. Invalid inputs raise ``ValueError`` rather
    than silently producing a match. An empty catalog, or a nearest neighbour
    beyond ``DEFAULT_SNAP_TOLERANCE``, returns an unsnapped result.
    """
    target_nd = _validate_nd_vd(nd, vd, label="target")[0]
    target_vd = float(vd)
    weight = float(disp_factor)
    if not math.isfinite(weight) or weight < 0:
        raise ValueError("disp_factor must be finite and non-negative")

    target_dn = (target_nd - 1.0) / target_vd
    nearest: tuple[float, str, float, float, float, float] | None = None
    for name, values in catalog.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("catalog glass names must be non-empty strings")
        try:
            catalog_nd, catalog_vd = values
        except (TypeError, ValueError) as exc:
            raise ValueError(f"catalog entry {name!r} must be an (nd, vd) pair") from exc
        catalog_nd, catalog_vd = _validate_nd_vd(
            catalog_nd, catalog_vd, label=f"catalog entry {name!r}"
        )
        delta_nd = target_nd - catalog_nd
        delta_dn = target_dn - (catalog_nd - 1.0) / catalog_vd
        distance = math.hypot(delta_nd, weight * delta_dn)
        candidate = (distance, name, catalog_nd, catalog_vd, delta_nd, delta_dn)
        if nearest is None or candidate[:2] < nearest[:2]:
            nearest = candidate

    if nearest is None:
        return SnapResult(None, None, None, None, None, None)

    distance, name, catalog_nd, catalog_vd, delta_nd, delta_dn = nearest
    within_tolerance = distance <= DEFAULT_SNAP_TOLERANCE or math.isclose(
        distance, DEFAULT_SNAP_TOLERANCE, rel_tol=0.0, abs_tol=1e-12
    )
    if not within_tolerance:
        return SnapResult(None, catalog_nd, catalog_vd, distance, delta_nd, delta_dn)
    return SnapResult(name, catalog_nd, catalog_vd, distance, delta_nd, delta_dn)


def _validate_nd_vd(nd: float, vd: float, *, label: str) -> tuple[float, float]:
    numeric_nd = float(nd)
    numeric_vd = float(vd)
    if not math.isfinite(numeric_nd) or numeric_nd <= 1.0:
        raise ValueError(f"{label} nd must be finite and greater than 1")
    if not math.isfinite(numeric_vd) or numeric_vd <= 0:
        raise ValueError(f"{label} vd must be finite and positive")
    return numeric_nd, numeric_vd
