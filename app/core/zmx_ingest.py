"""Normalized Zemax loader for the real smartphone main/wide ammo designs.

Wraps ``optiland.fileio.load_zemax_file`` with the normalizations our real
production designs need so that paraxial / raytrace / MTF are all computable:

1. **xasphere surfaces** — `optiland_patches._patch_zemax_xasphere_reader`
   teaches the reader to treat Extended Asphere (XDAT) as even_asphere.
2. **real material nd/vd** — `optiland_patches._patch_zemax_glass_materials`
   replaces the coarse GLAS placeholder index with datasheet values from
   `app.core.zmx_materials`.
3. **visible F/d/C wavelength band** — applied here, post-load.

(1) and (2) are parser-level patches (must be active before load); (3) is a
post-load step. After `load_normalized_zmx`, ``optic.paraxial.f2()`` returns an
EFL within 2% of the design nominal for all 18 ammo files — see
`tests/test_zmx_ingest.py::test_load_efl_within_2pct`.
"""

from __future__ import annotations

import contextlib
import warnings
from pathlib import Path

# Patches must be applied before any load_zemax_file call. Importing this module
# applies them once (idempotent); app/main.py also calls apply_all() at startup.
from app.core.optiland_patches import apply_all

apply_all()

from optiland.fileio import load_zemax_file  # noqa: E402  (must follow apply_all)

# data/zmx lives under the backend root: core -> app -> <root> / data / zmx
ZMX_AMMO_DIR = Path(__file__).resolve().parents[2] / "data" / "zmx"

# Visible F / d / C reference lines in micrometres (d-line primary). Matches the
# MTF convention in app/core/aberration.py and keeps AbbeMaterial dispersion in
# its valid (visible) range.
_FDC: tuple[tuple[float, bool], ...] = (
    (0.4861, False),  # F line (H-beta) 486.1 nm
    (0.5876, True),  # d line (He) 587.6 nm  -- primary
    (0.6563, False),  # C line (H-alpha) 656.3 nm
)


def _normalize_wavelengths(optic) -> None:
    """Reset the optic's spectrum to the visible F/d/C band (d-line primary).

    Real ammo zmx files carry mixed wavelengths; standardizing to F/d/C keeps
    AbbeMaterial dispersion valid and matches the downstream MTF band.
    """
    optic.wavelengths.wavelengths.clear()
    for value, is_primary in _FDC:
        optic.add_wavelength(value, is_primary=is_primary)


def load_normalized_zmx(path: str | Path):
    """Load a real Zemax design and normalize it for Optiland computation.

    xasphere + material normalizations are applied at parse time by
    `optiland_patches`; wavelength normalization happens here. A best-effort
    robust ray aimer is set for wide-FOV designs (paraxial works regardless).

    Returns an ``optiland.optic.Optic`` ready for paraxial / raytrace / MTF.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optic = load_zemax_file(str(path))
        _normalize_wavelengths(optic)
        # Wide-FOV scaled prescriptions can produce NaN with the default paraxial
        # aimer; robust aimer mirrors optical_engine.py. Best-effort: paraxial
        # (EFL) is unaffected if this is unavailable.
        with contextlib.suppress(Exception):
            optic.ray_tracer.set_aiming("robust", max_iter=20)
    return optic


# Canonical MTF field fractions (axis, mid, 0.7-zone, full) that lens datasheets
# cite. 4 points keep GeometricMTF fast while covering the field; 0.7 is the
# de-facto "image quality" zone for phone lenses.
_MTF_FIELD_FRACS: tuple[float, ...] = (0.0, 0.5, 0.7, 1.0)


def regularize_fields_to_angle(optic, full_fov_deg: float) -> None:
    """Switch the optic to ANGLE fields at standard MTF fractions (in place).

    **Mandatory before MTF / layout-SVG.** The real zmx designs define fields as
    RealImageHeight (~12 dense points). GeometricMTF then ray-aims by iteratively
    *solving* for the object-space ray that lands at each image height — on a
    real multi-element design this hangs (>25 s, effectively non-terminating).
    Verified fix: ANGLE fields aim directly (no inverse solve), dropping MTF +
    SVG from >25 s to ~0.3 s. We also collapse the 12 dense fields to the 4
    canonical MTF fractions.

    half-FOV (chief-ray max angle) ≈ ``full_fov_deg / 2`` from the manifest
    nominal (design-intent FOV; an image-height→angle conversion would need the
    distortion curve). Paraxial EFL is unaffected (it doesn't depend on field
    type), so the Plan-01 EFL<2% guarantee still holds.
    """
    half = full_fov_deg / 2.0
    optic.set_field_type("angle")
    optic.fields.fields.clear()
    for frac in _MTF_FIELD_FRACS:
        optic.add_field(y=half * frac)
    with contextlib.suppress(Exception):
        optic.ray_tracer.set_aiming("robust", max_iter=20)
