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
    prescription_fingerprint,
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
    "A16= 1.0E-10 -- A18= 2.5E-12 -3.5E-12 "
    "A20= 4.5E-14 -5.5E-14 A22= 6.5E-12 -7.5E-12 "
    "A24= 8.5E-12 -9.5E-12 A26= 1.5E-12 -2.5E-12 "
    "A28= 3.5E-12 -4.5E-12 A30= 5.5E-12 -6.5E-12",
)

THREE_COLUMN_MATERIAL_TEXT = PRESCRIPTION_TEXT.replace(
    "Glass 1.835 42.7 55.43",
    "Plastic 1.634 1.660 20.4",
    1,
).replace(
    "Plastic 1.541 47.2 -55.65",
    "Glass 1.508 1.517 64.2",
    1,
)

LARGAN_COMPONENT_TEXT = """
TABLE-US-00001 TABLE 1 1st Embodiment f = 2.89 mm, Fno = 2.30,
HFOV = 38.0 deg. Surface # Curvature Radius Thickness Material Index Abbe #
Focal Length 0 Object Plano Infinity 1 Ape. Plano -0.075 Stop
2 Lens 1 1.741 ASP 0.334 Plastic 1.536 58.3 7.92
3 2.758 ASP 0.105 4 Lens 2 1.865 ASP 0.295 Plastic 1.639
18,4 5.61 5 IR-cut Piano 0.110 Glass 1.517 64.2 -- filter
6 Prism Plano 0.365 Glass 1.517 64.2 -- 7 Image Plano --
TABLE-US-00002 TABLE 2 Aspheric Coefficients Surface # 2 3 4
k= -1.0 2.0 -3.0 A4= -1.0E-02 -2.0E-02 -3.0E-02
A22= 1.0E-12 -2.0E-12 3.0E-12 A30= 4.0E-15 -5.0E-15 6.0E-15
-- [0001] In Table 2, k represents the conic coefficient.
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


def test_parse_patent_prescription_uses_d_line_columns_when_material_table_has_reference_index() -> None:
    prescription = parse_patent_prescription(
        THREE_COLUMN_MATERIAL_TEXT,
        patent_id="US-THREE-COLUMN-A1",
    )

    first_lens = prescription.surfaces[1]
    assert first_lens.nd == pytest.approx(1.660)
    assert first_lens.vd == pytest.approx(20.4)

    filter_surface = prescription.surfaces[2]
    assert filter_surface.nd == pytest.approx(1.517)
    assert filter_surface.vd == pytest.approx(64.2)


def test_parse_patent_prescription_rejects_unphysical_material_indices() -> None:
    text = PRESCRIPTION_TEXT.replace("Glass 1.835 42.7 55.43", "Glass 1.835 1.66", 1)

    with pytest.raises(PatentParseError, match="outside physical bounds"):
        parse_patent_prescription(text, patent_id="US-BAD-MATERIAL-A1")


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
    assert asphere.asphere_coefficients["A22"] == pytest.approx(6.5e-12)
    assert asphere.asphere_coefficients["A30"] == pytest.approx(5.5e-12)

    output_path = tmp_path / "xasphere.zmx"
    write_patent_zmx(prescription, output_path)
    zmx_text = output_path.read_text(encoding="ascii")
    optic = load_normalized_zmx(output_path)

    assert math.isfinite(float(optic.paraxial.f2()))
    assert "TYPE XASPHERE" in zmx_text
    assert "XDAT 11 2.5e-12 0 0 1 0 0" in zmx_text
    assert "XDAT 12 4.5e-14 0 0 1 0 0" in zmx_text
    assert "XDAT 13 6.5e-12 0 0 1 0 0" in zmx_text
    assert "XDAT 17 5.5e-12 0 0 1 0 0" in zmx_text


def test_parse_patent_prescription_accepts_largan_component_rows() -> None:
    prescription = parse_patent_prescription(
        LARGAN_COMPONENT_TEXT,
        patent_id="US-LARGAN-FIXTURE-A1",
    )

    assert len(prescription.surfaces) == 7
    assert prescription.surfaces[0].label == "Ape."
    assert prescription.surfaces[0].radius_mm == 0.0
    assert prescription.surfaces[3].vd == pytest.approx(18.4)

    ir_cut = prescription.surfaces[4]
    assert ir_cut.label == "IR-cut"
    assert ir_cut.radius_mm == 0.0
    assert ir_cut.nd == pytest.approx(1.517)
    assert ir_cut.vd == pytest.approx(64.2)

    prism = prescription.surfaces[5]
    assert prism.label == "Prism"
    assert prism.radius_mm == 0.0
    assert prism.nd == pytest.approx(1.517)
    assert prism.vd == pytest.approx(64.2)

    assert prescription.surfaces[1].asphere_coefficients["A22"] == pytest.approx(1.0e-12)
    assert prescription.surfaces[1].asphere_coefficients["A30"] == pytest.approx(4.0e-15)


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


def test_convert_candidate_skips_formal_index_embodiments_but_not_staging_files(
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
    formal_index = tmp_path / "index.json"
    formal_index.write_text(
        '[{"case_id": "US-MULTI-A1-e2", "source_zmx": "US-MULTI-A1-e2.zmx"}]',
        encoding="utf-8",
    )
    (tmp_path / "US-MULTI-A1-e1.zmx").write_text("stale staging artifact", encoding="ascii")

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "local-token",
            candidate,
            tmp_path,
            formal_case_stems=patent_to_zmx.load_formal_case_stems(formal_index),
        )
    )

    assert [attempt.status for attempt in attempts] == ["success", "skipped"]
    assert attempts[1].reason == "formal case index already contains this patent embodiment"
    assert (tmp_path / "US-MULTI-A1-e1.zmx").read_text(encoding="ascii") != "stale staging artifact"
    assert not (tmp_path / "US-MULTI-A1-e2.zmx").exists()


def test_parse_patent_prescription_rejects_unsupported_high_order_asphere_terms() -> None:
    text = PRESCRIPTION_TEXT.replace("A16= 1.0E-10 --", "A32= 1.0E-10 --")

    with pytest.raises(PatentParseError, match="unsupported nonzero high-order"):
        parse_patent_prescription(text, patent_id="US-UNSUPPORTED-A1")


def test_prescription_fingerprint_uses_first_eight_radius_thickness_values() -> None:
    base = parse_patent_prescription(PRESCRIPTION_TEXT, patent_id="US-FP-A1")
    meta_changed = parse_patent_prescription(
        PRESCRIPTION_TEXT.replace("f = 12.99 mm", "f = 13.49 mm", 1),
        patent_id="US-FP-A2",
    )
    radius_changed = parse_patent_prescription(
        PRESCRIPTION_TEXT.replace("43.6006", "44.6006", 1),
        patent_id="US-FP-A3",
    )

    fingerprint = prescription_fingerprint(base)

    assert len(fingerprint) == 16
    assert fingerprint == prescription_fingerprint(meta_changed)
    assert fingerprint != prescription_fingerprint(radius_changed)


def test_convert_candidate_skips_duplicate_prescription_without_writing_zmx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "zmx"
    seen_prescription_fingerprints: set[str] = set()

    class FakeParaxial:
        def f2(self) -> float:
            return 12.34

    class FakeOptic:
        paraxial = FakeParaxial()

    async def fake_fetch(_client: object, _token: str, _patent_id: str) -> str:
        return PRESCRIPTION_TEXT

    def fake_write(
        _prescription: patent_to_zmx.PatentPrescription,
        output_path: Path,
    ) -> patent_to_zmx.TraceApertureAudit:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("fake zmx", encoding="ascii")
        return patent_to_zmx.TraceApertureAudit(
            semi_diameters_mm={},
            real_image_height_mm=1.0,
            sanity_image_height_mm=2.0,
            measured_surfaces=(),
            interpolated_surfaces=(),
            finite_final_rays=1,
            total_rays=1,
        )

    monkeypatch.setattr(patent_to_zmx, "ROOT", tmp_path)
    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(patent_to_zmx, "write_patent_zmx", fake_write)
    monkeypatch.setattr(patent_to_zmx, "load_normalized_zmx", lambda _path: FakeOptic())

    first = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id="US-DUP-A1",
                title="first",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            output_dir,
            seen_prescription_fingerprints=seen_prescription_fingerprints,
        )
    )
    second = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "token",
            patent_to_zmx.PatentCandidate(
                patent_id="US-DUP-A2",
                title="second",
                source_url="",
                pool_path=tmp_path / "pool.jsonl",
                line_number=2,
            ),
            output_dir,
            seen_prescription_fingerprints=seen_prescription_fingerprints,
        )
    )

    assert [attempt.status for attempt in first] == ["success"]
    assert [attempt.status for attempt in second] == ["duplicate_prescription"]
    assert "prescription fingerprint" in second[0].reason
    assert (output_dir / "US-DUP-A1-e1.zmx").is_file()
    assert not (output_dir / "US-DUP-A2-e1.zmx").exists()


def test_patent_to_zmx_report_includes_failure_reason_counts(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"

    patent_to_zmx._write_report(
        report_path,
        [
            patent_to_zmx.ConversionAttempt(
                patent_id="US-FAIL-A1",
                title="parse failure",
                status="failed",
                reason="PatentParseError: no embodiment table",
            ),
            patent_to_zmx.ConversionAttempt(
                patent_id="US-DUP-A1",
                title="duplicate",
                status="duplicate_prescription",
                reason="duplicate_prescription: prescription fingerprint abc123",
            ),
        ],
        target_successes=1,
    )

    report = report_path.read_text(encoding="utf-8")

    assert "- failure_reason_counts:" in report
    assert "  - PatentParseError: 1" in report
    assert "  - duplicate_prescription: 1" in report
