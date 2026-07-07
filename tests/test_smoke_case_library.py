"""Lightweight tests for case-library smoke decisions."""

from __future__ import annotations

import math

from app.core.aberration import MTFResult
from app.core.case_library import CASES_DIR
from app.core.lens_system import LayoutSVG
from app.core.optical_sample import OpticalSampleData
from scripts.smoke_case_library import (
    render_markdown_report,
    smoke_case_file,
    smoke_case_paths,
    smoke_case_sample,
)

SEED_CASE_IDS = (
    "3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56",
    "3P_F2.5_FOV78.1_EFL2.8_IMH2.3_TTL4.33",
    "4P_F1.9_FOV60.0_EFL3.7_IMH2.1_TTL6.00",
    "4P_F1.9_FOV60.1_EFL3.7_IMH2.1_TTL6.00",
    "4P_F2.0_FOV84.1_EFL2.5_IMH2.3_TTL3.34",
)


def _seed_sample(case_id: str = SEED_CASE_IDS[0]) -> OpticalSampleData:
    path = CASES_DIR / f"{case_id}.json"
    return OpticalSampleData.model_validate_json(path.read_text(encoding="utf-8"))


def test_fixed_seed_payloads_pass_smoke_logic():
    results = [smoke_case_sample(_seed_sample(case_id)) for case_id in SEED_CASE_IDS]

    assert all(result.ok for result in results)
    assert [result.case_id for result in results] == list(SEED_CASE_IDS)


def test_non_finite_key_metrics_are_reported_on_fixed_seed():
    sample = _seed_sample()
    broken = sample.model_copy(
        update={
            "paraxial": sample.paraxial.model_copy(
                update={"effective_focal_length_mm": math.nan}
            )
        }
    )

    result = smoke_case_sample(broken)

    assert not result.ok
    assert any(
        issue.field == "paraxial.effective_focal_length_mm"
        and issue.reason == "expected finite positive value"
        for issue in result.issues
    )


def test_nan_rms_spot_is_reported_on_fixed_seed():
    sample = _seed_sample(SEED_CASE_IDS[1])
    broken_mtf = sample.mtf.model_copy(
        update={
            "rms_spot_radius_um_by_field": [
                math.nan,
                *sample.mtf.rms_spot_radius_um_by_field[1:],
            ]
        }
    )
    broken = sample.model_copy(update={"mtf": broken_mtf})

    result = smoke_case_sample(broken)

    assert not result.ok
    assert any(
        issue.field == "mtf.rms_spot_radius_um_by_field[0]"
        and issue.reason == "expected finite non-NaN value"
        for issue in result.issues
    )


def test_missing_payload_sections_are_reported_on_fixed_seed():
    sample = _seed_sample(SEED_CASE_IDS[2])
    empty_mtf = MTFResult(
        freq_lp_per_mm=[],
        fields=[],
        diff_limited=[],
        cutoff_freq_lp_per_mm=sample.mtf.cutoff_freq_lp_per_mm,
        airy_disc_diameter_um=sample.mtf.airy_disc_diameter_um,
        rms_spot_radius_um_by_field=[],
    )
    broken = sample.model_copy(
        update={
            "mtf": empty_mtf,
            "layout_svg": LayoutSVG(width_px=1200, height_px=600, svg_content="not svg"),
            "surfaces": [],
        }
    )

    result = smoke_case_sample(broken)
    fields = {issue.field for issue in result.issues}

    assert "mtf.freq_lp_per_mm" in fields
    assert "mtf.fields" in fields
    assert "mtf.rms_spot_radius_um_by_field" in fields
    assert "layout_svg.svg_content" in fields
    assert "surfaces" in fields


def test_bad_json_is_classified_as_crash(tmp_path):
    path = tmp_path / "BROKEN.json"
    path.write_text("{", encoding="utf-8")

    result = smoke_case_file(path)

    assert not result.ok
    assert result.case_id == "BROKEN"
    assert result.crash is not None


def test_aggregate_report_lists_crashes_and_nan_issues(tmp_path):
    good_path = CASES_DIR / f"{SEED_CASE_IDS[3]}.json"
    bad_path = tmp_path / "BROKEN.json"
    bad_path.write_text("{", encoding="utf-8")

    report = smoke_case_paths([good_path, bad_path])
    markdown = render_markdown_report(report)

    assert report.total == 2
    assert report.passed == 1
    assert len(report.crashes) == 1
    assert "Total cases: 2" in markdown
    assert "`BROKEN`" in markdown
    assert "## NaN List" in markdown
