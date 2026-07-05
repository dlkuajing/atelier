from __future__ import annotations

import pytest

from app.api.optical import OpticalSpecRequest
from app.core.case_library import match_case
from app.core.lens_system import Scenario


def test_us_patent_seed_routes_with_rebased_index_image_height() -> None:
    spec = OpticalSpecRequest(
        scenario=Scenario.SMARTPHONE_ULTRAWIDE,
        focal_length_mm=3.62,
        f_number=2.32,
        field_of_view_deg=91.0,
        image_height_mm=3.62257,
        n_elements=7,
        analysis_depth="seed_only",
    )

    sample = match_case(
        spec.scenario,
        spec.focal_length_mm,
        spec.f_number,
        spec.field_of_view_deg,
        image_height_mm=spec.image_height_mm,
        n_elements=spec.n_elements,
        include_design_assessment=True,
        lightweight_design_assessment=True,
    )

    assert sample is not None
    assert sample.metadata is not None
    assert sample.design_assessment is not None
    assert sample.metadata.case_id == "US20170003482A1"
    assert sample.design_assessment.matched_case_id == "US20170003482A1"

    candidate = next(
        item
        for item in sample.design_assessment.candidate_comparison
        if item.case_id == "US20170003482A1"
    )
    assert candidate.role == "best_match"
    assert candidate.image_height_mm == pytest.approx(3.62257)
    assert candidate.image_height_mm > 0.0
