from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.e2_golden import (
    _PINNED_IMPLAUSIBLE_IMAGE_HEIGHT_CASES,
    _PINNED_UNSCREENABLE_IMAGE_HEIGHT_CASES,
    _screen_corpus_image_heights,
)
from scripts.image_height_gate import (
    RATIO_MAX,
    RATIO_MIN,
    ImageHeightVerdict,
    first_order_image_height_mm,
    screen_image_height,
)

INDEX_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"
INDEX_RECORDS = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "data" / "eval_golden.json"


def test_first_order_reference_matches_f_tan_theta() -> None:
    assert first_order_image_height_mm(4.0, 30.0) == pytest.approx(4.0 * math.tan(math.radians(30)))


@pytest.mark.parametrize(
    "focal_length_mm, half_field_deg",
    [
        (4.0, 90.0),  # tan blows up
        (4.0, 89.9999999),  # 1.7e16 mm -- finite, and useless as a divisor
        (4.0, 120.0),  # negative tan
        (4.0, 85.0),  # at the boundary, excluded
        (4.0, 0.0),
        (-4.0, 30.0),
        (float("nan"), 30.0),
        (4.0, float("inf")),
    ],
)
def test_unusable_reference_returns_none_rather_than_a_large_number(
    focal_length_mm: float,
    half_field_deg: float,
) -> None:
    assert first_order_image_height_mm(focal_length_mm, half_field_deg) is None


def test_reference_unusable_is_its_own_verdict_not_a_pass() -> None:
    verdict, ratio = screen_image_height(2.3, None)

    assert verdict is ImageHeightVerdict.REFERENCE_UNUSABLE
    assert ratio is None


@pytest.mark.parametrize("ratio", [RATIO_MIN, 1.0, RATIO_MAX])
def test_band_edges_are_inclusive(ratio: float) -> None:
    reference = 2.0
    verdict, measured = screen_image_height(reference * ratio, reference)

    assert verdict is ImageHeightVerdict.PLAUSIBLE
    assert measured == pytest.approx(ratio)


@pytest.mark.parametrize(
    "image_height_mm",
    [
        6.15709e17,  # US-12032139-B2-e2 as the corpus carries it today
        51.8754,  # US-12210142-B2-e6 -- 52 mm on a phone lens
        0.0,
        -2.3,
        float("nan"),
    ],
)
def test_impossible_image_heights_are_rejected(image_height_mm: float) -> None:
    verdict, _ = screen_image_height(image_height_mm, 2.0)

    assert verdict is ImageHeightVerdict.IMPLAUSIBLE


def test_band_admits_every_projection_law_a_real_lens_uses() -> None:
    """Distortion is not a defect: the gate must clear the compressive mappings.

    f*sin(theta) is the most compressive projection ever built into a lens and
    f*theta the usual fisheye; both stay well inside the band at the widest half
    field the corpus reaches, so no real design can trip the gate on distortion.
    """

    focal_length_mm = 4.0
    for half_field_deg in (30.0, 45.0, 60.0, 75.0):
        theta = math.radians(half_field_deg)
        reference = first_order_image_height_mm(focal_length_mm, half_field_deg)
        assert reference is not None
        for mapped in (focal_length_mm * math.sin(theta), focal_length_mm * theta):
            verdict, _ = screen_image_height(mapped, reference)
            assert verdict is ImageHeightVerdict.PLAUSIBLE, half_field_deg


def test_corpus_screen_pins_the_known_bad_rows() -> None:
    """The 34 rows the max-over-pupil derivation left behind, counted not hidden.

    They stay in the corpus until it is regenerated; pinning them means the
    debt rings when it changes instead of accumulating silently.
    """

    verdicts = _screen_corpus_image_heights(INDEX_RECORDS)
    implausible = {
        case_id
        for case_id, entry in verdicts.items()
        if entry["image_height_plausibility"] == ImageHeightVerdict.IMPLAUSIBLE
    }

    assert len(INDEX_RECORDS) == 442
    assert len(verdicts) == 442
    assert implausible == set(_PINNED_IMPLAUSIBLE_IMAGE_HEIGHT_CASES)
    assert len(implausible) == 34
    assert not _PINNED_UNSCREENABLE_IMAGE_HEIGHT_CASES


def test_shipped_golden_carries_the_verdict_for_every_case() -> None:
    """The verdict has to reach the artifact, not just the run that computed it."""

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    case_entries = {
        name: entry for name, entry in golden.items() if "source_case_id" in entry
    }
    recorded_implausible = {
        entry["source_case_id"]
        for entry in case_entries.values()
        if entry["image_height_plausibility"] == ImageHeightVerdict.IMPLAUSIBLE
    }

    assert len(case_entries) == 442
    assert all("first_order_image_height_ratio" in entry for entry in case_entries.values())
    assert recorded_implausible == set(_PINNED_IMPLAUSIBLE_IMAGE_HEIGHT_CASES)


def test_corpus_screen_rejects_a_newly_implausible_row() -> None:
    records = [
        {"case_id": "NEW-ROW", "efl_mm": 4.0, "fov_deg": 76.0, "image_height_mm": 4.0e17},
    ]

    with pytest.raises(ValueError, match="newly implausible"):
        _screen_corpus_image_heights(records)


def test_corpus_screen_rejects_a_pin_that_has_gone_stale() -> None:
    """A pinned row that starts screening clean must not pass unnoticed.

    Otherwise the quarantine list outlives the defect and the next reader
    believes 34 rows are still broken when they are not.
    """

    records = [
        {"case_id": case_id, "efl_mm": 4.0, "fov_deg": 76.0, "image_height_mm": 3.13}
        for case_id in sorted(_PINNED_IMPLAUSIBLE_IMAGE_HEIGHT_CASES)
    ]

    with pytest.raises(ValueError, match="now screen clean"):
        _screen_corpus_image_heights(records)
