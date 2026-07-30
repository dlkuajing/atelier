"""Relative cost index -- the fourth 交付物 piece.

NORTH-STAR §1.1 requires four deliverables per candidate and this is the one
that was never implemented. Its definition there is exact about two things:

* the drivers are **片数、材料牌号、非球面数量、口径厚度**
* it is **relative**, never a price. `.planning/NORTH-STAR.md` §4 lists
  「绝对成本报价（元/颗）」 as an explicit 反目标 -- the project holds no real
  quotation data and will never be able to produce one honestly.

Why coarse weights are acceptable here, stated by the North Star itself (§3):

    公差表与成本模型的绝对值可以不准：同一张表**同时**施加于候选与对照专利，
    表错了两边一起错，**排序不变**。

So the contract this module owes is *not* accuracy. It is:

1. **the same table is applied to both sides** -- enforced by there being one
   table and one function, with no per-call tuning knobs
2. **the output is a ratio** -- `cost_ratio(candidate, control)`, dimensionless
3. **it fails closed** -- see below

Failing closed matters more here than the weights do. Every driver is additive,
so a prescription whose materials failed to parse would total a *lower* cost and
read as the cheaper, better design -- the ninth instance of this project's
recurring trap, where the degenerate value is indistinguishable from a good
reading. Cost is therefore a positive-definite quantity and anything that cannot
be computed returns ``None`` rather than a partial sum.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

#: Relative cost weight per material family, in arbitrary units where a
#: moulded plastic element is 1.0. Ordering, not magnitude, is what these
#: encode: moulded plastics are the cheap high-volume case, common crown/flint
#: glass costs more to grind and centre, and high-index lanthanum glasses are
#: the expensive end. Values are deliberately coarse -- see module docstring for
#: why that is sound. Applied identically to candidate and control.
_MATERIAL_COST_UNITS: tuple[tuple[str, float], ...] = (
    ("ZEONEX", 1.0),
    ("APL", 1.0),
    ("OKP", 1.1),
    ("EP", 1.1),
    ("SP", 1.1),
    ("D263T", 2.2),
    ("BK7", 2.2),
    ("N-BK7", 2.2),
    ("SILICA", 2.6),
    ("H-LAK", 3.2),
    ("H-ZLAF", 4.0),
)
_DEFAULT_MATERIAL_COST_UNITS = 1.5

#: Model-glass fallback, used when the ZMX names no real material. CODE V writes
#: a **model** glass (``___BLANK`` with an nd/vd pair, or ``<name>_BLANK`` from
#: `repair_legacy_zmx_glass`) whenever glass is a degree of freedom, so the
#: optimiser's ``extra_dof="both"`` arm lands on an nd/vd point with **no name at
#: all**. Pricing those by name gave every one of them the same default weight --
#: i.e. the glass DOF was free, and NORTH-STAR §1.1's 「材料牌号」 cost driver
#: never fired on the arm that actually moves glass.
#:
#: So price them by the only material fact the file carries: refractive index.
#: Higher index costs more -- that ordering is the whole content here, and it is
#: the same ordering the named table above encodes (plastics ~1.53 at 1.0,
#: crown ~1.52 at 2.2 is the one crossing, high-index lanthanum ~1.8+ at 4.0).
#: Anchored at the two ends of the named table so a model glass never prices
#: outside the range a named one can.
_MODEL_GLASS_ND_ANCHORS: tuple[tuple[float, float], ...] = (
    (1.45, 1.0),
    (1.55, 1.1),
    (1.65, 1.6),
    (1.75, 2.6),
    (1.90, 4.0),
)

#: A ZMX ``GLAS`` line is ``GLAS <name> <model_flag> <?> <nd> <vd> ...``.
_ZMX_GLAS_ND_FIELD = 4

#: An aspheric surface needs a diamond-turned mould insert and its own
#: metrology; a spherical one does not. Charged per aspheric surface.
_ASPHERE_SURCHARGE = 0.8

#: Larger and thicker elements cost more material and more cycle time. Kept
#: mild and referenced to a 1 mm semi-diameter / 0.5 mm thickness element so a
#: typical mobile element lands near 1.0.
_REFERENCE_SEMI_DIAMETER_MM = 1.0
_REFERENCE_THICKNESS_MM = 0.5
_SIZE_EXPONENT = 0.5


@dataclass(frozen=True)
class ElementCost:
    """One physical element's contribution, kept for auditability."""

    index: int
    material: str
    material_units: float
    aspheric_surfaces: int
    semi_diameter_mm: float
    thickness_mm: float
    units: float


@dataclass(frozen=True)
class CostIndex:
    """Total relative cost of one prescription. ``None`` is never 0."""

    total_units: float
    element_count: int
    aspheric_surface_count: int
    elements: tuple[ElementCost, ...]


def model_glass_cost_units(nd: float) -> float:
    """Cost weight for a model glass, from its refractive index alone.

    Piecewise-linear through `_MODEL_GLASS_ND_ANCHORS` and clamped at both ends,
    so a model glass can never price outside the range a *named* material can.
    """

    if not math.isfinite(nd) or nd <= 0.0:
        return _DEFAULT_MATERIAL_COST_UNITS
    anchors = _MODEL_GLASS_ND_ANCHORS
    if nd <= anchors[0][0]:
        return anchors[0][1]
    if nd >= anchors[-1][0]:
        return anchors[-1][1]
    for (lo_nd, lo_u), (hi_nd, hi_u) in zip(anchors, anchors[1:], strict=False):
        if lo_nd <= nd <= hi_nd:
            span = hi_nd - lo_nd
            return lo_u + (hi_u - lo_u) * ((nd - lo_nd) / span)
    return _DEFAULT_MATERIAL_COST_UNITS


def material_cost_units(name: str, *, nd: float | None = None) -> float:
    """Cost weight for a glass/plastic name, or for its index when unnamed.

    A named material is priced from the table. A **model** glass -- what CODE V
    writes whenever glass is a degree of freedom -- carries no usable name, so it
    is priced from ``nd`` instead. Without that, every glass the optimiser
    invented cost the same default and the glass DOF was free.

    Unknown names with no ``nd`` still get a mid-range weight rather than 0: an
    unrecognised glass is still an element that must be made, and charging 0
    would make an unparsable prescription look free.
    """

    canon = re.sub(r"[^A-Z0-9-]", "", (name or "").upper())
    for prefix, units in _MATERIAL_COST_UNITS:
        if canon.startswith(prefix):
            return units
    if nd is not None:
        return model_glass_cost_units(nd)
    return _DEFAULT_MATERIAL_COST_UNITS


def element_cost_units(
    *,
    material: str,
    aspheric_surfaces: int,
    semi_diameter_mm: float,
    thickness_mm: float,
    nd: float | None = None,
) -> float:
    """Cost of one element, in the same arbitrary units for every caller."""

    size = (max(semi_diameter_mm, 1e-6) / _REFERENCE_SEMI_DIAMETER_MM) ** _SIZE_EXPONENT
    bulk = (max(thickness_mm, 1e-6) / _REFERENCE_THICKNESS_MM) ** _SIZE_EXPONENT
    shape = 1.0 + _ASPHERE_SURCHARGE * max(0, aspheric_surfaces)
    return material_cost_units(material, nd=nd) * shape * size * bulk


def cost_ratio(candidate: CostIndex | None, control: CostIndex | None) -> float | None:
    """Candidate cost relative to its control. ``None`` when either is unknown.

    This is the only number meant to leave this module. An absolute total is an
    arbitrary-unit sum with no external meaning; the ratio is what NORTH-STAR
    §1.1 asks for and the only form that survives the weights being coarse.
    """

    if candidate is None or control is None:
        return None
    if not math.isfinite(control.total_units) or control.total_units <= 0.0:
        return None
    if not math.isfinite(candidate.total_units) or candidate.total_units <= 0.0:
        return None
    return candidate.total_units / control.total_units


#: Zemax surface types that carry an aspheric profile.
_ASPHERIC_ZMX_TYPES = frozenset({"EVENASPH", "XASPHERE", "XOSPHERE", "ODDASPHE", "ASPHERE"})
_AIR_GLASS_NAMES = frozenset({"", "___BLANK"})


def cost_index_from_zmx(text: str) -> CostIndex | None:
    """Read the four cost drivers straight out of a ZMX prescription.

    All four are present in the file -- element count and material from ``GLAS``,
    aspheric count from ``TYPE``, and 口径/厚度 from ``DIAM``/``DISZ`` -- so this
    needs neither CODE V nor a paraxial solve.

    Returns ``None`` when the file yields no glass element. That is fail-closed
    on purpose: an unparsable prescription must not total 0 units and read as
    the cheapest design in the comparison.
    """

    surfaces: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SURF "):
            if current is not None:
                surfaces.append(current)
            current = {"type": "STANDARD", "glass": "", "diam": 0.0, "disz": 0.0, "nd": None}
            continue
        if current is None:
            continue
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "TYPE" and len(parts) >= 2:
            current["type"] = parts[1].upper()
        elif key == "GLAS" and len(parts) >= 2:
            current["glass"] = parts[1]
            # A model glass ("___BLANK", or "<name>_BLANK" from the legacy repair)
            # names no material -- but the same line carries its refractive index,
            # which is the fact `material_cost_units` prices it from. Without this
            # every glass the optimiser invented cost the same default.
            if len(parts) > _ZMX_GLAS_ND_FIELD:
                current["nd"] = _float_or_zero(parts[_ZMX_GLAS_ND_FIELD]) or None
        elif key == "DIAM" and len(parts) >= 2:
            current["diam"] = _float_or_zero(parts[1])
        elif key == "DISZ" and len(parts) >= 2:
            current["disz"] = _float_or_zero(parts[1])
    if current is not None:
        surfaces.append(current)

    elements: list[ElementCost] = []
    aspheric_total = 0
    for index, surface in enumerate(surfaces):
        glass = str(surface["glass"]).strip()
        if glass.upper() in _AIR_GLASS_NAMES and glass != "___BLANK":
            continue
        if not glass:
            continue
        # A glass record marks the *entry* surface of an element; its exit
        # surface is the next one, so both count toward the aspheric surcharge.
        aspheric = sum(
            1 for s in surfaces[index : index + 2] if str(s["type"]).upper() in _ASPHERIC_ZMX_TYPES
        )
        aspheric_total += aspheric
        semi = float(surface["diam"])  # type: ignore[arg-type]
        thick = abs(float(surface["disz"]))  # type: ignore[arg-type]
        nd_value = surface.get("nd")
        units = element_cost_units(
            material=glass,
            aspheric_surfaces=aspheric,
            semi_diameter_mm=semi,
            nd=float(nd_value) if isinstance(nd_value, (int, float)) else None,
            thickness_mm=thick,
        )
        elements.append(
            ElementCost(
                index=index,
                material=glass,
                material_units=material_cost_units(glass),
                aspheric_surfaces=aspheric,
                semi_diameter_mm=semi,
                thickness_mm=thick,
                units=units,
            )
        )

    if not elements:
        return None
    total = sum(e.units for e in elements)
    if not math.isfinite(total) or total <= 0.0:
        return None
    return CostIndex(
        total_units=total,
        element_count=len(elements),
        aspheric_surface_count=aspheric_total,
        elements=tuple(elements),
    )


def _float_or_zero(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0
