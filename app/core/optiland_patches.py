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
            "reference_cs": (
                self.reference_cs.to_dict() if self.reference_cs else None
            ),
        }

    _cs.CoordinateSystem.to_dict = _safe_to_dict


def apply_all() -> None:
    """Apply every patch. Called once from `app/main.py`."""
    _patch_coordinate_system_to_dict()
