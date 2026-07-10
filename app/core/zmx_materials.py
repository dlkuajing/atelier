"""Real optical-material nd/vd table for the Zemax ammo designs.

Optiland 0.6's glass catalog doesn't recognize the Japanese optical resins
(ZEONEX / OKP / APL / EP) and several CDGM glasses used in real smartphone lens
designs. The zmx GLAS rows carry only coarse placeholder nd/vd (commonly 1.5/40),
so the reader falls back to AbbeMaterial(placeholder) — under-estimating the
refractive index and drifting the paraxial EFL (measured ~18% on a 5-element
design before this table was applied).

This table maps material name -> (nd@587.6nm, vd) from manufacturer datasheets
so the glass patch in `optiland_patches.py` can rebuild a faithful AbbeMaterial.

All values are public datasheet figures:
  nd = refractive index at the d-line (587.6 nm), vd = Abbe number (n_d-based).
No values are fabricated — unknown materials fall back to the zmx placeholder (if
usable) or a conservative typical-plastic default, with a logged warning.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Canonical name (UPPERCASE, factory _NN suffix stripped) -> (nd, vd).
MATERIAL_ND_VD: dict[str, tuple[float, float]] = {
    # --- Zeon cyclo-olefin polymers (COP) ---
    "ZEONEX-E48R": (1.531, 56.0),  # Zeon Corp E48R
    "ZEONEX-K26R": (1.535, 56.0),  # Zeon K26R
    "ZEONEX-F52R": (1.535, 56.0),  # Zeon F52R
    # --- Osaka Gas Chemicals OKP high-index resins ---
    "OKP1": (1.636, 22.5),  # OKP1
    "OKP4": (1.607, 27.0),  # OKP4 (if present)
    # --- Mitsubishi Gas Chemical EP high-index resins ---
    "EP8000": (1.651, 21.5),  # EP8000
    "EP6000": (1.640, 23.0),  # EP6000
    "EP5000": (1.634, 23.9),  # EP5000 (if present)
    # --- Mitsui APEL cyclo-olefin ---
    "APL5014CL": (1.544, 56.0),  # APEL 5014CL
    "APL5514": (1.544, 56.0),  # APEL 5514
    # --- misc high-index plastic ---
    "SP3810": (1.640, 23.3),
    # --- CDGM (Chengdu Guangming) optical glass ---
    "H-ZLAF78B": (1.883, 40.8),
    "H-LAK53A": (1.678, 55.5),
    "H-LAK51A": (1.697, 55.5),
    # --- SCHOTT / fused silica ---
    "D263T": (1.523, 55.0),  # SCHOTT D263 T eco — cover glass / IR-filter substrate
    "N-BK7": (1.5168, 64.17),  # SCHOTT N-BK7
    "BK7": (1.5168, 64.17),  # SCHOTT BK7
    "SILICA": (1.4585, 67.8),  # fused silica @587.6nm
}

_SUFFIX_RE = re.compile(r"_\d+$")
# CODE V model-glass marker appended by scripts/repair_legacy_zmx_glass.py
# (ZEMAXOS_TO_CV selects its model-glass branch by substring match on "BLANK";
# the marker keeps the trade name in-file while making CODE V honor the inline
# nd/vd). The lookbehind spares the plain Zemax "___BLANK" placeholder name.
_CODEV_MODEL_GLASS_MARKER_RE = re.compile(r"(?<=[^_])_BLANK$")


def _canon(name: str) -> str:
    """Uppercase + strip the repair marker (``_BLANK``) and the Zemax factory
    suffix (e.g. ``_14``), so ``APL5014CL_14_BLANK`` -> ``APL5014CL``."""
    if not name:
        return ""
    text = _CODEV_MODEL_GLASS_MARKER_RE.sub("", name.strip().upper())
    return _SUFFIX_RE.sub("", text)


def lookup_nd_vd(name: str) -> tuple[float, float] | None:
    """Return the real (nd, vd) for a zmx material name, or None if unknown."""
    canon = _canon(name)
    if canon in MATERIAL_ND_VD:
        return MATERIAL_ND_VD[canon]
    base = canon.split("_")[0]
    if base in MATERIAL_ND_VD:
        return MATERIAL_ND_VD[base]
    return None


def _abbe(nd: float, vd: float):
    """Build an ``AbbeMaterial`` pinned to the polynomial dispersion model.

    Optiland 0.6 defaults to ``model='polynomial'``; v0.7 switches the default to
    ``'buchdahl'``, which shifts indices and would invalidate our EFL<2%
    verification. We pin ``polynomial`` explicitly so a future Optiland bump
    can't silently change our computed optics (and to silence the 0.6
    FutureWarning).
    """
    from optiland.materials import AbbeMaterial

    return AbbeMaterial(nd, vd, model="polynomial")


def resolve_material(
    name: str,
    fallback_nd: float | None = None,
    fallback_vd: float | None = None,
):
    """Return an optiland ``AbbeMaterial`` for a zmx material name.

    Resolution order (honest — never fabricates an index):
    1. name in the real datasheet table -> AbbeMaterial(real nd, real vd)
    2. else a usable zmx placeholder (fallback_nd > 1.4) -> AbbeMaterial(fallback)
    3. else a conservative typical optical-plastic default (1.54 / 56) + warning
    """
    real = lookup_nd_vd(name)
    if real is not None:
        return _abbe(real[0], real[1])
    if fallback_nd is not None and fallback_nd > 1.4:
        return _abbe(fallback_nd, fallback_vd if (fallback_vd and fallback_vd > 0) else 50.0)
    logger.warning(
        "zmx_materials: unknown material %r with unusable placeholder nd; "
        "using conservative 1.54/56 default",
        name,
    )
    return _abbe(1.54, 56.0)
