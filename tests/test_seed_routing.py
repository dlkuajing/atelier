from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.optical import OpticalSpecRequest
from app.core import case_library
from app.core.lens_system import Scenario

TARGET_CASE_ID = "US20170003482A1"
INDEX_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"


def _target_record() -> dict[str, object]:
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return next(record for record in records if record["case_id"] == TARGET_CASE_ID)


def _reanchored_patent_spec() -> OpticalSpecRequest:
    record = _target_record()
    return OpticalSpecRequest(
        scenario=Scenario.SMARTPHONE_ULTRAWIDE,
        focal_length_mm=float(record["efl_mm"]),
        f_number=float(record["fnum"]),
        field_of_view_deg=float(record["fov_deg"]),
        image_height_mm=float(record["image_height_mm"]),
        n_elements=int(record["n_pieces"]),
        analysis_depth="seed_only",
    )


def _match_reanchored_patent_spec(spec: OpticalSpecRequest):
    return case_library.match_case(
        spec.scenario,
        spec.focal_length_mm,
        spec.f_number,
        spec.field_of_view_deg,
        image_height_mm=spec.image_height_mm,
        n_elements=spec.n_elements,
        include_design_assessment=True,
        lightweight_design_assessment=True,
    )


def test_us_patent_seed_routes_with_rebased_index_image_height() -> None:
    spec = _reanchored_patent_spec()

    sample = _match_reanchored_patent_spec(spec)

    assert sample is not None
    assert sample.metadata is not None
    assert sample.design_assessment is not None
    assert sample.metadata.case_id == TARGET_CASE_ID
    assert sample.design_assessment.matched_case_id == TARGET_CASE_ID

    candidate = next(
        item
        for item in sample.design_assessment.candidate_comparison
        if item.case_id == TARGET_CASE_ID
    )
    assert candidate.role == "best_match"
    assert candidate.image_height_mm == pytest.approx(spec.image_height_mm)
    assert candidate.image_height_mm > 0.0


def test_us_patent_seed_score_gets_worse_without_candidate_image_height(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _reanchored_patent_spec()

    baseline = _match_reanchored_patent_spec(spec)
    assert baseline is not None
    assert baseline.design_assessment is not None
    assert baseline.metadata is not None
    assert baseline.metadata.case_id == TARGET_CASE_ID

    monkeypatch.setattr(case_library, "_case_image_height_mm", lambda _case: 0.0)
    degraded = _match_reanchored_patent_spec(spec)

    assert degraded is not None
    assert degraded.design_assessment is not None
    assert degraded.design_assessment.score < baseline.design_assessment.score - 0.20
    assert (
        degraded.design_assessment.normalized_distance
        > baseline.design_assessment.normalized_distance + 0.50
    )

    degraded_candidate = next(
        item
        for item in degraded.design_assessment.candidate_comparison
        if item.case_id == TARGET_CASE_ID
    )
    assert degraded_candidate.image_height_mm == pytest.approx(0.0)
    assert degraded_candidate.score < baseline.design_assessment.score - 0.20
