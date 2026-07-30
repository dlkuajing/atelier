"""The re-anchor is one `generate_cases.py` run away from being undone.

`index.json`'s `fov_deg` is not computed from the ZMX -- it is written straight from the
intake manifest. Traced: `scripts/generate_cases.py:126` passes
`a["nominal_fov_deg"]` into `build_sample_from_optic`, and
`app/core/case_library.py` sets `fov_deg=nominal_fov_deg` on the metadata it returns.
The same value also drives `regularize_fields_to_angle(optic, nominal_fov_deg)` and
`_classify_scenario(nominal_fov_deg, ...)`, and the parameter it is assigned from
elsewhere in that function is named `full_fov_deg` -- so the contract is *full* angle.

Measured 2026-07-30 on this branch: **253 of 442** manifest rows still hold the half
angle, i.e. exactly half the re-anchored `index.json` value. Regenerating the corpus
today would write half angles back over the re-anchor for those 253 cases.

This file does not fix that -- re-anchoring the manifest changes what
`build_sample_from_optic` traces, which changes the committed per-case artifacts, and
that is its own shovel. What this file does is make the debt **counted and loud**: the
count is pinned, so it cannot drift in either direction unnoticed, and the day the
manifest is re-anchored this test fails and says what the new number should be.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

INDEX_PATH = Path("app") / "data" / "optical_cases" / "index.json"

#: Measured on this branch. `agrees` + `half` + `neither` == every matched row.
#:
#: `neither` is one case, `US10330891B2.zmx`: manifest 100.0 vs index 101.6. That is a
#: third convention -- a rounded nominal from the patent text rather than either the
#: half or the full traced angle -- and it is pinned separately so it cannot hide inside
#: a bucket it does not belong to.
EXPECTED_AGREES = 188
EXPECTED_STILL_HALF = 253
EXPECTED_NEITHER = 1


def _manifest_vs_index() -> dict[str, list[str]]:
    from tests.data.zmx_manifest import ZMX_AMMO

    index = {
        row["source_zmx"]: row
        for row in json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    }
    buckets: dict[str, list[str]] = {"agrees": [], "half": [], "neither": [], "unmatched": []}
    for entry in ZMX_AMMO:
        row = index.get(entry["filename"])
        if row is None:
            buckets["unmatched"].append(entry["filename"])
            continue
        manifest_fov = float(entry["nominal_fov_deg"])
        index_fov = float(row["fov_deg"])
        if abs(manifest_fov - index_fov) < 1e-6:
            buckets["agrees"].append(entry["filename"])
        elif abs(manifest_fov * 2.0 - index_fov) < 1e-3:
            buckets["half"].append(entry["filename"])
        else:
            buckets["neither"].append(entry["filename"])
    return buckets


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_every_manifest_row_matches_an_index_row() -> None:
    """The comparison is only meaningful if nothing silently drops out of it."""

    assert _manifest_vs_index()["unmatched"] == []


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_the_manifest_half_angle_debt_is_exactly_as_measured() -> None:
    """Pinned, not asserted-away.

    A pin rather than `== 0` because the fix is a corpus regeneration, not an edit. But
    a pin still does the job a silent debt cannot: if someone re-anchors the manifest
    this fails and tells them the new number, and if a future intake wave adds more
    half-angle rows this fails too instead of quietly enlarging the hole.
    """

    buckets = _manifest_vs_index()
    assert len(buckets["half"]) == EXPECTED_STILL_HALF
    assert len(buckets["agrees"]) == EXPECTED_AGREES
    assert len(buckets["neither"]) == EXPECTED_NEITHER


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_the_odd_case_is_the_one_we_know_about() -> None:
    """`neither` must stay identified. An unnamed third convention is how a defect
    survives a bucket count."""

    assert _manifest_vs_index()["neither"] == ["US10330891B2.zmx"]


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_the_half_angle_rows_really_are_half_and_not_a_coincidence() -> None:
    """Positive control on the classifier: a doubling relation on hundreds of rows is
    strong evidence of a convention mismatch, but only if the rows are spread across the
    fov range rather than clustered at one value where 2x could be arithmetic luck."""

    from tests.data.zmx_manifest import ZMX_AMMO

    by_name = {entry["filename"]: float(entry["nominal_fov_deg"]) for entry in ZMX_AMMO}
    half_values = sorted(by_name[name] for name in _manifest_vs_index()["half"])
    assert len(set(half_values)) > 20, "half-angle rows cluster too tightly to be a convention"
    assert min(half_values) < 20.0 < max(half_values)
