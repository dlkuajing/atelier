"""Tests for the real-zmx normalized loader (phase v2-02 wave 1).

Goal gates (from BRIEF §5):
- all ammo zmx load with zero failures
- every loaded EFL is within 2% of the design nominal
- xasphere surfaces no longer raise "Unsupported Zemax surface type"
- real material names resolve to faithful refractive indices (not air placeholder)
"""

import math
import warnings

from app.core.optiland_patches import _safe_float, apply_all
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx
from app.core.zmx_materials import lookup_nd_vd, resolve_material
from tests.data.zmx_manifest import ZMX_AMMO


def test_manifest_has_entries():
    assert len(ZMX_AMMO) == 361
    for a in ZMX_AMMO:
        assert a["nominal_efl_mm"] > 0, a
        assert a["filename"]
        assert a["nominal_fov_deg"] > 0, a


def test_data06c_manifest_increases_library_and_has_real_image_height():
    data06c = [a for a in ZMX_AMMO if a.get("intake_batch") == "DATA-06c"]
    data06f = [a for a in ZMX_AMMO if a.get("intake_batch") == "DATA-06f"]
    data06f_b11 = [a for a in ZMX_AMMO if a.get("intake_batch") == "DATA-06f-b11"]
    data06i = [a for a in ZMX_AMMO if a.get("intake_batch") == "DATA-06i-rescan2"]
    data06 = [a for a in ZMX_AMMO if str(a.get("intake_batch", "")).startswith("DATA-06")]

    assert len(data06c) == 67
    assert len(data06f) == 39
    assert len(data06f_b11) == 12
    assert len(data06i) == 10
    assert len(data06) == 128
    assert all(a["nominal_imh_mm"] > 0.0 for a in data06)


def test_data09d1_manifest_increases_library_and_has_real_image_height():
    data09d1 = [a for a in ZMX_AMMO if a.get("intake_batch") == "DATA-09d1"]

    assert len(data09d1) == 186
    assert all(a["nominal_imh_mm"] > 0.0 for a in data09d1)
    assert all(a.get("image_height_source") == "ATELIER_REAL_IMH_MM" for a in data09d1)


def test_material_table():
    # placeholder air-index (1.0) must be overridden to a real plastic index.
    # _safe_float handles optiland 0.6's numpy-array-shaped .n() return.
    mat = resolve_material("ZEONEX-K26R_14", 1.0, 0.0)
    assert _safe_float(mat.n(0.5876)) > 1.4
    # known datasheet values, factory suffix stripped
    assert lookup_nd_vd("APL5014CL_14") == (1.544, 56.0)
    assert lookup_nd_vd("BK7") == (1.5168, 64.17)
    assert lookup_nd_vd("EP8000") == (1.651, 21.5)
    # unknown material returns None (caller falls back, honestly)
    assert lookup_nd_vd("NO-SUCH-GLASS") is None


def test_patch_idempotent():
    # second apply_all must be a no-op, not raise (sentinel guards)
    apply_all()
    apply_all()


def test_all_load_zero_failure():
    failures = []
    for a in ZMX_AMMO:
        path = ZMX_AMMO_DIR / a["filename"]
        try:
            load_normalized_zmx(path)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{a['filename']}: {type(e).__name__}: {e}")
    assert not failures, "zmx load failures (expected 0):\n" + "\n".join(failures)


def test_xasphere_loads():
    # a known xasphere-bearing design (was "Unsupported Zemax surface type")
    optic = load_normalized_zmx(ZMX_AMMO_DIR / "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15.zmx")
    assert optic is not None
    assert float(optic.paraxial.f2()) > 0


def test_load_efl_within_2pct():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        over = []
        for a in ZMX_AMMO:
            optic = load_normalized_zmx(ZMX_AMMO_DIR / a["filename"])
            efl = float(optic.paraxial.f2())
            nom = a["nominal_efl_mm"]
            if not math.isclose(efl, nom, rel_tol=0.02):
                err = abs(efl - nom) / nom * 100
                over.append(f"{a['filename']}: EFL={efl:.3f} nom={nom} err={err:.1f}%")
        assert not over, "EFL beyond 2% of nominal:\n" + "\n".join(over)
