"""Runtime monkey-patches for known Optiland 0.6.0 bugs.

These get applied at module import time — `app/main.py` imports this module
once, the patches stick for the lifetime of the worker.

Each patch carries the upstream issue / PR reference so it's obvious when
the patch can be deleted (after we pin a fixed Optiland release).
"""

from __future__ import annotations

import numpy as np


def _safe_float(value) -> float:
    """Convert any numpy scalar/0-d/1-element array to a python float.

    Optiland's CoordinateSystem stores coordinates as numpy values that, after
    backend-state changes (e.g. `updater.scale_system`), can end up as ndarray
    of shape (1,) rather than scalar. NumPy 2.x rejects `float(ndarray)`
    for shape != () with the error our users hit:

        TypeError: only 0-dimensional arrays can be converted to Python scalars

    `.item()` is the safe primitive — it works for both 0-d arrays and size-1
    n-d arrays.
    """
    arr = np.asarray(value)
    if arr.size == 0:
        return 0.0
    return float(arr.flatten()[0])


def _patch_coordinate_system_to_dict() -> None:
    """Patch `optiland.coordinate_system.CoordinateSystem.to_dict`.

    Upstream bug: every coordinate (x, y, z, rx, ry, rz) is coerced with
    `float(self.x)`. If `self.x` is a numpy array of shape `(1,)` instead of
    a scalar, NumPy 2.x raises TypeError and the surrounding endpoint returns
    an unstructured 500. We rewrite the method using `_safe_float`.

    Trigger: hit reliably on `smartphone-ultrawide` scenario (Optiland's
    `WideAngle100FOV` reference design) regardless of EFL, because
    `WideAngle100FOV.__init__` builds its surface array-style. Other
    scenarios (Telephoto, CookeTriplet, DoubleGauss) happen to use scalar
    z values so they don't trip this.

    Remove this patch when we move to Optiland >= 0.7 (or whatever release
    includes the fix for the v0.6 coordinate-system serialization).
    """
    from optiland import coordinate_system as _cs

    def _safe_to_dict(self) -> dict:
        return {
            "x": _safe_float(self.x),
            "y": _safe_float(self.y),
            "z": _safe_float(self.z),
            "rx": _safe_float(self.rx),
            "ry": _safe_float(self.ry),
            "rz": _safe_float(self.rz),
            "reference_cs": (self.reference_cs.to_dict() if self.reference_cs else None),
        }

    _cs.CoordinateSystem.to_dict = _safe_to_dict


def _patch_zemax_xasphere_reader() -> None:
    """Teach Optiland 0.6's Zemax reader to handle XASPHERE (Extended Asphere).

    Upstream gap (verified against the installed 0.6.0 source):
    - `ZemaxDataParser._operand_table` has no ``XDAT`` handler, so an Extended
      Asphere's coefficient rows are silently dropped.
    - `ZemaxDataParser._read_surf_type` has no XASPHERE entry, so it falls
      through to ``"xasphere"``, which
      `ZemaxToOpticConverter._configure_surface_coefficients` rejects with
      ``ValueError: Unsupported Zemax surface type: xasphere``.

    Real smartphone lens designs use XASPHERE heavily (11 of our 21 ammo files).
    Extended Asphere and Even Asphere are the same family (conic + even-power
    polynomial). The normalization radius (XDAT 2) is 1.0 across every ammo
    file, so the XDAT polynomial coefficients map 1:1 onto even-asphere params.

    Mapping (verified against raw UTF-16 ZMX blocks, cross-checked against the
    EVENASPH PARM/CONI layout; see .planning/quick/260702-xasphere-ingest-fidelity):
      XDAT 1     = polynomial term count N -> ignored (length flows from rows)
      XDAT 2     = normalization radius    -> asserted == 1.0 (fail loud)
      XDAT (3+i) = r^(2(i+1)) coefficient  -> data["param_i"]  (i = 0..N-1)
      conic      = standard CONI row       -> handled by the stock parser
    surf_type XASPHERE is then reported as ``even_asphere``. The previous
    mapping (XDAT 3 -> conic, XDAT 4..11 -> param_0..7) shifted every
    coefficient one even order AND truncated 10-term files to 8 terms — the
    dropped terms are O(1) at the clear-aperture edge, which silently destroyed
    off-axis image quality on all 9 XASPHERE seeds while leaving paraxial EFL
    (r -> 0) untouched, so the EFL<2% ingest gate never caught it.

    The stock ``_configure_surface_coefficients`` hardcodes param_0..7 for
    even_asphere, so it is also patched below to consume every param_k present
    (>= 8), keeping 10-term XASPHERE polynomials intact.

    Remove when Optiland ships native XASPHERE support (>= 0.7?).
    """
    from optiland.fileio.zemax.reader.converter import ZemaxToOpticConverter
    from optiland.fileio.zemax.reader.parser import ZemaxDataParser

    if getattr(ZemaxDataParser, "_xasphere_patched", False):
        return

    _orig_init = ZemaxDataParser.__init__
    _orig_read_surf_type = ZemaxDataParser._read_surf_type

    def _read_xdat(self, data: list) -> None:
        try:
            idx = int(float(data[1]))
            val = float(data[2])
        except (ValueError, IndexError):
            return
        if idx == 1:
            return  # term count; actual length flows from the coefficient rows
        if idx == 2:
            if abs(val - 1.0) > 1e-9:
                raise ValueError(
                    f"XASPHERE normalization radius {val} != 1.0 is not "
                    "supported; coefficients would need r_norm^(2i) rescaling"
                )
            return
        # XDAT (3+i) -> param_i, i.e. the r^(2(i+1)) even-asphere coefficient
        self._current_surf_data[f"param_{idx - 3}"] = val

    def _patched_read_surf_type(self, data: list) -> None:
        if len(data) > 1 and data[1] == "XASPHERE":
            self._current_surf_data["type"] = "even_asphere"
            return
        _orig_read_surf_type(self, data)

    def _patched_init(self, filename: str) -> None:
        _orig_init(self, filename)
        self._operand_table["XDAT"] = self._read_xdat

    _orig_configure_coeffs = ZemaxToOpticConverter._configure_surface_coefficients

    def _patched_configure_coeffs(self, data: dict):
        if data["type"] == "even_asphere":
            param_indices = [
                int(key.removeprefix("param_"))
                for key in data
                if key.startswith("param_") and key.removeprefix("param_").isdigit()
            ]
            n_terms = max(8, max(param_indices) + 1 if param_indices else 0)
            return [data.get(f"param_{k}", 0.0) for k in range(n_terms)]
        return _orig_configure_coeffs(self, data)

    ZemaxDataParser._read_xdat = _read_xdat
    ZemaxDataParser._read_surf_type = _patched_read_surf_type
    ZemaxDataParser.__init__ = _patched_init
    ZemaxToOpticConverter._configure_surface_coefficients = _patched_configure_coeffs
    ZemaxDataParser._xasphere_patched = True


def _patch_zemax_glass_materials() -> None:
    """Override the placeholder-AbbeMaterial fallback with real datasheet nd/vd.

    Real smartphone designs use Japanese optical resins (ZEONEX/OKP/APL/EP) and
    CDGM glasses that Optiland's catalog doesn't recognize. The zmx GLAS rows
    carry coarse placeholder nd/vd (e.g. ``APL5014CL → 1.5/40``, real ≈
    1.544/56), so `_read_glass` falls back to ``AbbeMaterial(placeholder)``,
    under-estimating the index → paraxial EFL drifts (measured 18% on a 5P
    design, well past our 2% gate).

    We wrap `_read_glass`: after the original runs, if the resolved material is
    the placeholder ``AbbeMaterial`` (i.e. the catalog lookup missed) AND the
    name is in our real table (`app.core.zmx_materials`), rebuild it with the
    datasheet nd/vd. Catalog-resolved ``Material`` objects (full dispersion) are
    left untouched, so we only ever *improve* fidelity, never degrade it.

    Remove when Optiland ships these materials in its catalog.
    """
    from optiland.fileio.zemax.reader.parser import ZemaxDataParser
    from optiland.materials import AbbeMaterial

    if getattr(ZemaxDataParser, "_glass_materials_patched", False):
        return

    _orig_read_glass = ZemaxDataParser._read_glass

    def _patched_read_glass(self, data: list) -> None:
        _orig_read_glass(self, data)
        name = data[1] if len(data) > 1 else ""
        from app.core.zmx_materials import _CODEV_MODEL_GLASS_MARKER_RE, _abbe, lookup_nd_vd

        # The `_BLANK` marker (scripts/repair_legacy_zmx_glass.py) makes CODE V
        # treat the row as model glass; it must be *transparent* to Optiland.
        # If the marked name missed the catalog, retry the original resolution
        # with the bare trade name so a catalog-resolvable material (e.g.
        # D263T, fuzzy-matched by Optiland) keeps its full-dispersion Material
        # exactly as it did before the repair (bit-identical EFL).
        stripped = _CODEV_MODEL_GLASS_MARKER_RE.sub("", name)
        if stripped != name and isinstance(self._current_surf_data.get("material"), AbbeMaterial):
            _orig_read_glass(self, [data[0], stripped, *data[2:]])

        mat = self._current_surf_data.get("material")
        if not isinstance(mat, AbbeMaterial):
            return  # catalog Material or "mirror" — keep full-fidelity result

        real = lookup_nd_vd(name)
        if real is not None:
            nd, vd = real
            self._current_surf_data["material"] = _abbe(nd, vd)
            self._current_surf_data["index"] = nd
            self._current_surf_data["abbe"] = vd

    ZemaxDataParser._read_glass = _patched_read_glass
    ZemaxDataParser._glass_materials_patched = True


def apply_all() -> None:
    """Apply every patch. Called once from `app/main.py`."""
    _patch_coordinate_system_to_dict()
    _patch_zemax_xasphere_reader()
    _patch_zemax_glass_materials()
