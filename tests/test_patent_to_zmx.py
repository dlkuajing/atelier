from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from app.core.engines.zmx_writer import write_zmx_from_codev_readout
from app.core.zmx_ingest import load_normalized_zmx
from scripts.patent_to_zmx import (
    PatentParseError,
    build_readout_from_prescription,
    parse_patent_prescription,
    write_patent_zmx,
)


PRESCRIPTION_TEXT = """
TABLE-US-00001 TABLE 1A 1st Embodiment f = 12.99 mm, Fno = 1.71,
HFOV = 20.0 deg. Surface # Curvature Radius Thickness Material Index Abbe #
Focal Length 0 Object Infinity Infinity 1 Ape. Stop Plano 0.890
2 Lens 1 43.6006 (SPH) 2.486 Glass 1.835 42.7 55.43
3 Lens 2 17.6926 (ASP) 1.752 Plastic 1.541 47.2 -55.65
4 10.7541 (ASP) 0.668 5 Image Plano -- Note: Reference wavelength is
587.6 nm (d-line). TABLE-US-00002 TABLE 1B Aspheric Coefficients
Surface # 3 4 k= -2.80433E+01 -1.30575E+00
A4= -5.6789E-05 -3.8862E-04 A6= -2.7992E-05 -2.0211E-05
A16= 1.0E-10 -- [0141] In Table 1B, k represents the conic coefficient.
"""


def test_parse_patent_prescription_extracts_surface_and_asphere_fields() -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")

    assert prescription.embodiment == "1st Embodiment"
    assert prescription.focal_length_mm == pytest.approx(12.99)
    assert prescription.f_number == pytest.approx(1.71)
    assert prescription.hfov_deg == pytest.approx(20.0)
    assert len(prescription.surfaces) == 5

    stop = prescription.surfaces[0]
    assert stop.index == 1
    assert stop.label == "Ape. Stop"
    assert stop.radius_mm == 0.0
    assert stop.thickness_mm == pytest.approx(0.890)

    first_lens = prescription.surfaces[1]
    assert first_lens.label == "Lens 1"
    assert first_lens.radius_mm == pytest.approx(43.6006)
    assert first_lens.nd == pytest.approx(1.835)
    assert first_lens.vd == pytest.approx(42.7)
    assert first_lens.surface_type == "SPH"

    asphere = prescription.surfaces[2]
    assert asphere.surface_type == "ASP"
    assert asphere.asphere_coefficients["K"] == pytest.approx(-28.0433)
    assert asphere.asphere_coefficients["A"] == pytest.approx(-5.6789e-5)
    assert asphere.asphere_coefficients["B"] == pytest.approx(-2.7992e-5)
    assert asphere.asphere_coefficients["G"] == pytest.approx(1.0e-10)

    image = prescription.surfaces[-1]
    assert image.label == "Image"
    assert image.thickness_mm == 0.0
    assert prescription.image_height_mm == pytest.approx(12.99 * math.tan(math.radians(20.0)))


@pytest.mark.parametrize(
    "meta_line",
    [
        "Embodiment 1 f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "First Embodiment f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "EXAMPLE 1 f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "Ｅｍｂｏｄｉｍｅｎｔ １ ｆ = １２．９９ ｍｍ, Ｆｎｏ = １．７１, ＨＦＯＶ = ２０．０ ｄｅｇ.",
    ],
)
def test_parse_patent_prescription_accepts_nfkc_and_meta_variants(meta_line: str) -> None:
    text = re.sub(
        r"1st Embodiment f = 12\.99 mm, Fno = 1\.71,\s+HFOV = 20\.0 deg\.",
        meta_line,
        PRESCRIPTION_TEXT,
    )

    prescription = parse_patent_prescription(text, patent_id="US-VARIANT-A1")

    assert prescription.focal_length_mm == pytest.approx(12.99)
    assert prescription.f_number == pytest.approx(1.71)
    assert prescription.hfov_deg == pytest.approx(20.0)
    assert len(prescription.surfaces) == 5


def test_build_readout_from_patent_prescription_roundtrips_through_zmx_ingest(
    tmp_path: Path,
) -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")
    readout = build_readout_from_prescription(prescription)

    output_path = write_zmx_from_codev_readout(readout, tmp_path / "patent.zmx")
    optic = load_normalized_zmx(output_path)
    efl = float(optic.paraxial.f2())

    assert math.isfinite(efl)
    assert abs(efl) > 1.0


def test_build_readout_does_not_use_ftan_image_height_for_surface_diameters() -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")
    readout = build_readout_from_prescription(prescription)
    forbidden_global = prescription.image_height_mm * 1.1

    assert readout.surfaces
    assert all(surface.semi_diameter_mm != pytest.approx(forbidden_global) for surface in readout.surfaces)


def test_write_patent_zmx_persists_real_imh_and_real_ray_surface_diameters(
    tmp_path: Path,
) -> None:
    prescription = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-EXAMPLE-A1")
    output_path = tmp_path / "patent.zmx"

    trace_audit = write_patent_zmx(prescription, output_path)
    zmx_text = output_path.read_text(encoding="ascii")
    optic = load_normalized_zmx(output_path)

    assert math.isfinite(float(optic.paraxial.f2()))
    assert trace_audit.real_image_height_mm > 0.0
    assert trace_audit.real_image_height_mm != pytest.approx(prescription.image_height_mm)
    assert "! ATELIER_REAL_IMH_MM" in zmx_text
    assert "! ATELIER_FTAN_IMH_SANITY_MM" in zmx_text
    assert "ATELIER_APERTURE_INTERPOLATED_SURFACES none" in zmx_text
    assert f"DIAM {prescription.image_height_mm * 1.1:.15g}" not in zmx_text


def test_parse_patent_prescription_rejects_unsupported_high_order_asphere_terms() -> None:
    text = PRESCRIPTION_TEXT.replace("A16= 1.0E-10 --", "A18= 1.0E-10 --")

    with pytest.raises(PatentParseError, match="unsupported nonzero high-order"):
        parse_patent_prescription(text, patent_id="US-UNSUPPORTED-A1")
