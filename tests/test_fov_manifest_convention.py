"""The re-anchor used to be one `generate_cases.py` run away from being undone.

`index.json`'s `fov_deg` is not computed from the ZMX -- it is written straight from the
intake manifest. Traced: `scripts/generate_cases.py` passes `a["nominal_fov_deg"]` into
`build_sample_from_optic`, and `app/core/case_library.py` sets `fov_deg=nominal_fov_deg`
on the metadata it returns. The same value also drives
`regularize_fields_to_angle(optic, nominal_fov_deg)` and
`_classify_scenario(nominal_fov_deg, ...)`, and the parameter it is assigned from
elsewhere in that function is named `full_fov_deg` -- so the contract is *full* angle.

Measured 2026-07-30, before the fix: **253 of 442** manifest rows held the half angle,
i.e. exactly half the re-anchored `index.json` value, so regenerating the corpus would
have written half angles back over the re-anchor for those 253 cases. All 253 came from
two intake waves whose converters wrote the ZMX's outermost ``YFLN`` verbatim
(`data06c_manifest.json` 67, `data09d1_manifest.json` 186); a Zemax ``FTYP 0`` field
angle is by definition measured from the axis, so that value is the half angle and the
full FOV is twice it. One further row, `US10330891B2.zmx`, held a third convention --
the patent text's rounded 100.0 against the ZMX's 101.6 -- and was read off the ZMX
rather than doubled.

The debt is now zero, so this file asserts zero rather than pinning a count. An
assertion of zero is only worth anything if the classifier behind it can still come back
non-zero, so both non-empty buckets keep a control that feeds them a row on purpose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

INDEX_PATH = Path("app") / "data" / "optical_cases" / "index.json"

#: The one row that was neither the full angle nor half of it. Kept named, because an
#: unnamed third convention is how a defect survives a bucket count.
_THIRD_CONVENTION_CASE = "US10330891B2.zmx"

#: What that row must now hold: 2 x the ZMX's outermost YFLN (50.8), not the patent
#: text's rounded 100.0. Pinned as a literal so a regeneration that re-reads the rounded
#: value fails here instead of quietly shrinking the traced field by 1.6%.
_THIRD_CONVENTION_FOV_DEG = 101.6


def _bucket(manifest_fov: float, index_fov: float) -> str:
    if abs(manifest_fov - index_fov) < 1e-6:
        return "agrees"
    if abs(manifest_fov * 2.0 - index_fov) < 1e-3:
        return "half"
    return "neither"


def _manifest_vs_index(overrides: dict[str, float] | None = None) -> dict[str, list[str]]:
    """Bucket every manifest row against its index row.

    ``overrides`` replaces a row's manifest value in memory only; it exists so the
    zero-assertions below can be shown to be falsifiable.
    """

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
        manifest_fov = float((overrides or {}).get(entry["filename"], entry["nominal_fov_deg"]))
        buckets[_bucket(manifest_fov, float(row["fov_deg"]))].append(entry["filename"])
    return buckets


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_every_manifest_row_matches_an_index_row() -> None:
    """The comparison is only meaningful if nothing silently drops out of it."""

    assert _manifest_vs_index()["unmatched"] == []


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_no_manifest_row_still_holds_a_half_angle() -> None:
    """Regenerating the corpus must reproduce the re-anchor, not undo it.

    A row in ``half`` means `index.json` currently states twice what the manifest holds,
    so the next `generate_cases.py` run would halve it -- and would trace that case at
    half its true field angle on the way. A new intake wave that repeats the DATA-06c /
    DATA-09d1 converter convention lands here.
    """

    from tests.data.zmx_manifest import ZMX_AMMO

    buckets = _manifest_vs_index()
    assert buckets["half"] == []
    assert buckets["neither"] == []
    assert len(buckets["agrees"]) == len(ZMX_AMMO)


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_a_reintroduced_half_angle_row_is_actually_caught() -> None:
    """Control for the assertion above: an empty bucket has to be an empty bucket, not a
    classifier that stopped classifying."""

    from tests.data.zmx_manifest import ZMX_AMMO

    victim = ZMX_AMMO[0]["filename"]
    buckets = _manifest_vs_index({victim: float(ZMX_AMMO[0]["nominal_fov_deg"]) / 2.0})
    assert buckets["half"] == [victim]


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_a_third_convention_row_is_actually_caught() -> None:
    """Same control for ``neither``. A value that is neither equal nor half must not be
    absorbed by the tolerance of the ``agrees`` test."""

    buckets = _manifest_vs_index({_THIRD_CONVENTION_CASE: 100.0})
    assert buckets["neither"] == [_THIRD_CONVENTION_CASE]


@pytest.mark.skipif(not INDEX_PATH.is_file(), reason="case index not present")
def test_the_row_that_had_a_third_convention_is_anchored_to_its_zmx() -> None:
    from tests.data.zmx_manifest import ZMX_AMMO

    stored = {a["filename"]: a["nominal_fov_deg"] for a in ZMX_AMMO}[_THIRD_CONVENTION_CASE]
    assert stored == pytest.approx(_THIRD_CONVENTION_FOV_DEG)
