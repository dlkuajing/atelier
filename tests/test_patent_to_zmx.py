from __future__ import annotations

import asyncio
import math
import re
from pathlib import Path

import pytest

from app.core.engines.zmx_writer import write_zmx_from_codev_readout
from app.core.zmx_ingest import load_normalized_zmx
from scripts import patent_to_zmx
from scripts.patent_to_zmx import (
    PatentParseError,
    build_readout_from_prescription,
    parse_patent_prescription,
    parse_patent_prescriptions,
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

SECOND_PRESCRIPTION_TEXT = PRESCRIPTION_TEXT.replace(
    "1st Embodiment f = 12.99 mm, Fno = 1.71,\nHFOV = 20.0 deg.",
    "EXAMPLE 2: effective focal length = 13.50 mm; F/# = 1.80; "
    "Half Angle of View = 21.0 degrees.",
).replace("-5.6789E-05", "-6.6789E-05", 1)

MULTI_EMBODIMENT_TEXT = PRESCRIPTION_TEXT + "\n" + SECOND_PRESCRIPTION_TEXT

XASPHERE_TEXT = PRESCRIPTION_TEXT.replace(
    "A16= 1.0E-10 --",
    "A16= 1.0E-10 -- A18= 2.5E-12 -3.5E-12 A20= 4.5E-14 -5.5E-14",
)


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


def test_parse_patent_prescriptions_extracts_all_embodiments() -> None:
    prescriptions = parse_patent_prescriptions(
        MULTI_EMBODIMENT_TEXT,
        patent_id="US-MULTI-A1",
    )

    assert [prescription.embodiment for prescription in prescriptions] == [
        "1st Embodiment",
        "EXAMPLE 2",
    ]
    assert [prescription.focal_length_mm for prescription in prescriptions] == pytest.approx(
        [12.99, 13.50]
    )
    assert prescriptions[1].f_number == pytest.approx(1.80)
    assert prescriptions[1].hfov_deg == pytest.approx(21.0)
    assert prescriptions[0].surfaces[2].asphere_coefficients["A"] == pytest.approx(-5.6789e-5)
    assert prescriptions[1].surfaces[2].asphere_coefficients["A"] == pytest.approx(-6.6789e-5)


def test_parse_patent_prescriptions_skips_narrative_embodiment_references() -> None:
    text = (
        "The image capturing unit according to the 1st embodiment has f = 1.00 mm, "
        "Fno = 2.00, HFOV = 30.0 deg. The detailed optical data follow. "
        + PRESCRIPTION_TEXT
    )

    prescriptions = parse_patent_prescriptions(text, patent_id="US-NARRATIVE-A1")

    assert len(prescriptions) == 1
    assert prescriptions[0].embodiment == "1st Embodiment"
    assert prescriptions[0].focal_length_mm == pytest.approx(12.99)


@pytest.mark.parametrize(
    "meta_line",
    [
        "Embodiment 1 f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "First Embodiment f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "EXAMPLE 1 f = 12.99 mm, Fno = 1.71, HFOV = 20.0 deg.",
        "Example No. 1: effective focal length: 12.99 mm; F/#: 1.71; Half Angle of View: 20.0 degrees.",
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


def test_write_patent_zmx_emits_xasphere_xdat_for_a18_a20(tmp_path: Path) -> None:
    prescription = parse_patent_prescription(XASPHERE_TEXT, patent_id="US-XASPHERE-A1")

    asphere = prescription.surfaces[2]
    assert asphere.asphere_coefficients["H"] == pytest.approx(2.5e-12)
    assert asphere.asphere_coefficients["J"] == pytest.approx(4.5e-14)

    output_path = tmp_path / "xasphere.zmx"
    write_patent_zmx(prescription, output_path)
    zmx_text = output_path.read_text(encoding="ascii")
    optic = load_normalized_zmx(output_path)

    assert math.isfinite(float(optic.paraxial.f2()))
    assert "TYPE XASPHERE" in zmx_text
    assert "XDAT 11 2.5e-12 0 0 1 0 0" in zmx_text
    assert "XDAT 12 4.5e-14 0 0 1 0 0" in zmx_text


def test_convert_candidate_writes_each_embodiment_with_e_suffix_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_patent_html(_client: object, _token: str, patent_id: str) -> str:
        assert patent_id == "US-MULTI-A1"
        return MULTI_EMBODIMENT_TEXT

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch_patent_html)
    candidate = patent_to_zmx.PatentCandidate(
        patent_id="US-MULTI-A1",
        title="multi embodiment fixture",
        source_url="local-fixture",
        pool_path=tmp_path / "pool.jsonl",
        line_number=1,
    )

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(object(), "local-token", candidate, tmp_path)
    )

    assert [attempt.status for attempt in attempts] == ["success", "success"]
    assert [attempt.embodiment for attempt in attempts] == ["1st Embodiment", "EXAMPLE 2"]
    assert (tmp_path / "US-MULTI-A1-e1.zmx").is_file()
    assert (tmp_path / "US-MULTI-A1-e2.zmx").is_file()
    assert attempts[0].zmx_path.endswith("US-MULTI-A1-e1.zmx")
    assert attempts[1].zmx_path.endswith("US-MULTI-A1-e2.zmx")


def test_convert_candidate_keeps_later_embodiments_after_parse_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken_first = PRESCRIPTION_TEXT.replace("3 Lens 2", "6 Lens 2", 1)

    async def fake_fetch_patent_html(_client: object, _token: str, patent_id: str) -> str:
        assert patent_id == "US-PARTIAL-A1"
        return broken_first + "\n" + SECOND_PRESCRIPTION_TEXT

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch_patent_html)
    candidate = patent_to_zmx.PatentCandidate(
        patent_id="US-PARTIAL-A1",
        title="partial embodiment fixture",
        source_url="local-fixture",
        pool_path=tmp_path / "pool.jsonl",
        line_number=1,
    )

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(object(), "local-token", candidate, tmp_path)
    )

    assert [attempt.status for attempt in attempts] == ["failed", "success"]
    assert "surface table index break" in attempts[0].reason
    assert attempts[0].embodiment == "1st Embodiment"
    assert attempts[1].embodiment == "EXAMPLE 2"
    assert not (tmp_path / "US-PARTIAL-A1-e1.zmx").exists()
    assert (tmp_path / "US-PARTIAL-A1-e2.zmx").is_file()
    assert attempts[1].zmx_path.endswith("US-PARTIAL-A1-e2.zmx")


def test_parse_patent_prescription_rejects_unsupported_high_order_asphere_terms() -> None:
    text = PRESCRIPTION_TEXT.replace("A16= 1.0E-10 --", "A22= 1.0E-10 --")

    with pytest.raises(PatentParseError, match="unsupported nonzero high-order"):
        parse_patent_prescription(text, patent_id="US-UNSUPPORTED-A1")
