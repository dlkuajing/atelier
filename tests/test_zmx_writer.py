from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.engines.codev_readout import (
    CodeVFieldReadout,
    CodeVReadout,
    CodeVSurfaceReadout,
    CodeVWavelengthReadout,
)
from app.core.engines.zmx_writer import build_zmx_from_codev_readout, write_zmx_from_codev_readout
from app.core.zmx_ingest import load_normalized_zmx


def _manual_readout() -> CodeVReadout:
    return CodeVReadout(
        source_zmx="manual-lens.zmx",
        units="MM",
        aperture_type="FNO",
        f_number=2.4,
        entrance_pupil_diameter_mm=4.2,
        num_surfaces=3,
        num_fields=2,
        num_wavelengths=2,
        num_zooms=1,
        stop_surface=1,
        field_type="RIH",
        reference_wavelength_index=1,
        image_height_y_mm=3.0,
        surfaces=(
            CodeVSurfaceReadout(
                index=1,
                radius_y_mm=20.0,
                thickness_mm=2.0,
                semi_diameter_mm=1.1,
                glass="BK7",
                nd=1.5168,
                vd=64.17,
                surface_type="ASP",
                is_stop=True,
                asphere_coefficients={
                    "K": -0.2,
                    "A": 1.0e-4,
                    "B": -2.0e-6,
                    "G": 3.0e-12,
                    "H": 0.0,
                    "J": 0.0,
                },
            ),
            CodeVSurfaceReadout(
                index=2,
                radius_y_mm=-20.0,
                thickness_mm=20.0,
                semi_diameter_mm=2.2,
                glass="___BLANK",
                nd=1.62,
                vd=30.0,
                surface_type="SPH",
                is_stop=False,
                asphere_coefficients={},
            ),
            CodeVSurfaceReadout(
                index=3,
                radius_y_mm=0.0,
                thickness_mm=0.0,
                semi_diameter_mm=3.3,
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
        wavelengths=(
            CodeVWavelengthReadout(index=1, wavelength_um=0.555, weight=1.0),
            CodeVWavelengthReadout(index=2, wavelength_um=0.65, weight=0.107),
        ),
    )


def test_build_zmx_from_codev_readout_emits_zemax_tokens() -> None:
    text = build_zmx_from_codev_readout(_manual_readout())

    assert text.startswith("VERS 191028")
    assert "\r\n" in text
    assert "\n" not in text.replace("\r\n", "")
    text.encode("ascii")
    assert "MODE SEQ\r\n" in text
    assert "UNIT MM X W X CM MR CPMM\r\n" in text
    assert "FNUM 2.4 0\r\n" in text
    assert "FTYP 3 0 2 2 0 0 0 2\r\n" in text
    assert "WAVM 1 0.555 1\r\n" in text
    assert "WAVM 2 0.65 0.107\r\n" in text
    assert "PWAV 1\r\n" in text
    assert "SURF 0\r\n" in text
    assert "SURF 1\r\n  STOP\r\n  TYPE EVENASPH\r\n" in text
    assert "  CURV 0.05 0 0 0 0 \"\"\r\n" in text
    assert "  GLAS BK7 0 0 1.5168 64.17 0 0 0 0 0 0 \r\n" in text
    assert "  GLAS ___BLANK 1 0 1.62 30 0 0 0 0 0 0 \r\n" in text


def test_marker_suffixed_glass_is_written_as_model_glass() -> None:
    """CODE V echoes the repair marker name (e.g. APL5014CL_14_BLANK, see
    scripts/repair_legacy_zmx_glass.py) back in its readout. The rebuilt
    candidate ZMX must carry model_flag=1 for it: flag=0 catalog-name
    semantics would make real Zemax (and a second ZEMAXOS_TO_CV import,
    e.g. Stage-B or expert Verify) resolve the deliverable's glass as air —
    reproducing the all-air seed bug on the output artifact."""
    readout = _manual_readout()
    marked = replace(
        readout.surfaces[0], glass="APL5014CL_14_BLANK", nd=1.544, vd=56.0
    )
    text = build_zmx_from_codev_readout(
        replace(readout, surfaces=(marked, *readout.surfaces[1:]))
    )
    assert "  GLAS APL5014CL_14_BLANK 1 0 1.544 56 0 0 0 0 0 0 \r\n" in text
    # The plain placeholder keeps its existing flag=1 behavior.
    assert "  GLAS ___BLANK 1 0 1.62 30 0 0 0 0 0 0 \r\n" in text
    assert "  CONI -0.2\r\n" in text
    assert "  PARM 1 0\r\n" in text
    assert "  PARM 2 0.0001\r\n" in text
    assert "  PARM 3 -2e-06\r\n" in text
    assert "  PARM 8 3e-12\r\n" in text
    assert "  DIAM 1.1 0 0 0 1 \"\"\r\n" in text
    assert "  DIAM 2.2 0 0 0 1 \"\"\r\n" in text
    assert "  DIAM 3.3 0 0 0 1 \"\"\r\n" in text
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
    readout = replace(_manual_readout(), aperture_type="EPD")
    text = build_zmx_from_codev_readout(readout)

    assert "ENPD 4.2\r\n" in text
    assert "FNUM" not in text


def test_build_zmx_from_codev_readout_rejects_missing_aperture() -> None:
    readout = replace(_manual_readout(), f_number=None)

    with pytest.raises(ValueError, match="missing f_number"):
        build_zmx_from_codev_readout(readout)


def test_build_zmx_from_codev_readout_rejects_missing_surface_diameter() -> None:
    readout = _manual_readout()
    surfaces = (
        replace(readout.surfaces[0], semi_diameter_mm=None),
        *readout.surfaces[1:],
    )

    with pytest.raises(ValueError, match="semi_diameter_mm"):
        build_zmx_from_codev_readout(replace(readout, surfaces=surfaces))


def test_build_zmx_from_codev_readout_rejects_missing_wavelength_table() -> None:
    readout = replace(_manual_readout(), wavelengths=(), num_wavelengths=0)

    with pytest.raises(ValueError, match="wavelength table"):
        build_zmx_from_codev_readout(readout)


def test_build_zmx_from_codev_readout_rejects_nonzero_h_j_asphere_terms() -> None:
    readout = _manual_readout()
    coefficients = dict(readout.surfaces[0].asphere_coefficients)
    coefficients["H"] = 1.0e-14
    surfaces = (replace(readout.surfaces[0], asphere_coefficients=coefficients), *readout.surfaces[1:])

    with pytest.raises(ValueError) as error:
        build_zmx_from_codev_readout(replace(readout, surfaces=surfaces))

    assert error.value.args[1]["surface_index"] == 1
    assert error.value.args[1]["unsupported_coefficients"] == {"H": 1.0e-14}
