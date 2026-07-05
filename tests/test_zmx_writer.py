from __future__ import annotations

import math
from pathlib import Path

import pytest

from app.core.engines.codev_readout import CodeVFieldReadout, CodeVReadout, CodeVSurfaceReadout
from app.core.engines.zmx_writer import build_zmx_from_codev_readout, write_zmx_from_codev_readout
from app.core.zmx_ingest import load_normalized_zmx


def _manual_readout() -> CodeVReadout:
    return CodeVReadout(
        source_zmx="manual-lens.zmx",
        units="MM",
        num_surfaces=3,
        num_fields=2,
        num_zooms=1,
        stop_surface=1,
        field_type="RIH",
        reference_wavelength_index=2,
        image_height_y_mm=3.0,
        surfaces=(
            CodeVSurfaceReadout(
                index=1,
                radius_y_mm=20.0,
                thickness_mm=2.0,
                glass="BK7",
                nd=1.5168,
                vd=64.17,
                surface_type="ASP",
                is_stop=True,
                asphere_coefficients={"K": -0.2, "A": 1.0e-4, "B": -2.0e-6},
            ),
            CodeVSurfaceReadout(
                index=2,
                radius_y_mm=-20.0,
                thickness_mm=20.0,
                glass=None,
                nd=1.0,
                vd=0.0,
                surface_type="SPH",
                is_stop=False,
                asphere_coefficients={},
            ),
            CodeVSurfaceReadout(
                index=3,
                radius_y_mm=0.0,
                thickness_mm=0.0,
                glass="___BLANK",
                nd=1.0,
                vd=0.0,
                surface_type="SPH",
                is_stop=False,
                asphere_coefficients={},
            ),
        ),
        fields=(
            CodeVFieldReadout(
                index=1,
                definition_type="RIH",
                x=0.0,
                y=0.0,
                vuy=0.0,
                vly=0.0,
                vux=0.0,
                vlx=0.0,
            ),
            CodeVFieldReadout(
                index=2,
                definition_type="RIH",
                x=0.0,
                y=3.0,
                vuy=0.3,
                vly=0.1,
                vux=0.2,
                vlx=-0.1,
            ),
        ),
    )


def test_build_zmx_from_codev_readout_emits_zemax_tokens() -> None:
    text = build_zmx_from_codev_readout(_manual_readout(), f_number=2.4)

    assert text.startswith("VERS 191028")
    assert "\r\n" in text
    assert "\n" not in text.replace("\r\n", "")
    text.encode("ascii")
    assert "MODE SEQ\r\n" in text
    assert "UNIT MM X W X CM MR CPMM\r\n" in text
    assert "FNUM 2.4 0\r\n" in text
    assert "FTYP 3 0 2 3 0 0 0 2\r\n" in text
    assert "WAVM 2 0.5876 1\r\n" in text
    assert "SURF 0\r\n" in text
    assert "SURF 1\r\n  STOP\r\n  TYPE EVENASPH\r\n" in text
    assert "  CURV 0.05 0 0 0 0 \"\"\r\n" in text
    assert "  GLAS BK7 0 0 1.5168 64.17 0 0 0 0 0 0 \r\n" in text
    assert "  CONI -0.2\r\n" in text
    assert "  PARM 1 0\r\n" in text
    assert "  PARM 2 0.0001\r\n" in text
    assert "  PARM 3 -2e-06\r\n" in text
    assert "VDXN 0 0.05\r\n" in text
    assert "VDYN 0 0.2\r\n" in text
    assert "VCXN 0 0.15\r\n" in text
    assert "VCYN 0 0.1\r\n" in text


def test_write_zmx_from_codev_readout_roundtrips_through_normalized_ingest(
    tmp_path: Path,
) -> None:
    output_path = write_zmx_from_codev_readout(
        _manual_readout(),
        tmp_path / "manual-lens.zmx",
        f_number=2.4,
    )

    raw = output_path.read_bytes()
    assert raw.decode("ascii")
    assert b"\r\n" in raw
    assert b"\n" not in raw.replace(b"\r\n", b"")

    optic = load_normalized_zmx(output_path)
    efl = float(optic.paraxial.f2())

    assert math.isfinite(efl)
    assert abs(efl) > 1.0


def test_write_zmx_from_codev_readout_can_emit_entrance_pupil_diameter() -> None:
    text = build_zmx_from_codev_readout(
        _manual_readout(),
        f_number=None,
        entrance_pupil_diameter_mm=4.2,
    )

    assert "ENPD 4.2\r\n" in text
    assert "FNUM" not in text


def test_build_zmx_from_codev_readout_rejects_missing_aperture() -> None:
    with pytest.raises(ValueError, match="Either f_number or entrance_pupil"):
        build_zmx_from_codev_readout(_manual_readout(), f_number=None)
