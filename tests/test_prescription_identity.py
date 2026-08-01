"""Design identity, because publication counts overstate independence.

Measured on the committed corpus: 442 ZMX files carry 354 distinct prescriptions. 62
prescriptions are shared by more than one file and 150 files are involved -- patent
continuations republish the same embodiment under a new number, and intake files each
publication as its own case. A P2 rate whose denominator counts `case_id` therefore
counts some designs up to four times.

The first attempt at this measurement decoded the files with the wrong codec, every
optical-row list came out empty, and 211 unrelated files hashed identically -- a
"distinct designs = 215" reading that was purely an artifact. Several tests below exist
because of that: an empty prescription must be loud, not arithmetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.engines.prescription_identity import (
    distinct_designs,
    fingerprint_zmx,
    prescription_fingerprint,
    prescription_rows,
)

ZMX_DIR = Path("data") / "zmx"

_TWO_SURFACES = """VERS 1
UNIT MM
CURV 0.1234 0 0 0
DISZ 0.5
GLAS PLASTIC 1 0 1.544 56.0
CURV -0.2 0 0 0
DISZ 1.0
"""


def test_only_optical_rows_enter_the_fingerprint() -> None:
    """Two files that differ only in how we look at the lens carry the same design."""

    looked_at_differently = _TWO_SURFACES.replace("UNIT MM", "UNIT MM\nXFLN 0 0 0\nWAVM 1 0.55 1")
    assert prescription_fingerprint(_TWO_SURFACES) == prescription_fingerprint(
        looked_at_differently
    )


def test_a_changed_radius_is_a_different_design() -> None:
    assert prescription_fingerprint(_TWO_SURFACES) != prescription_fingerprint(
        _TWO_SURFACES.replace("CURV 0.1234", "CURV 0.1235")
    )


def test_whitespace_is_normalised_but_values_are_not() -> None:
    assert prescription_fingerprint(_TWO_SURFACES) == prescription_fingerprint(
        _TWO_SURFACES.replace("DISZ 0.5", "DISZ    0.5")
    )


def test_a_text_with_no_optical_rows_has_no_fingerprint() -> None:
    """The decoder-failure guard. An empty row list must never hash to a value, or
    every unreadable file becomes "the same design" and the count collapses silently."""

    assert prescription_fingerprint("VERS 1\nUNIT MM\nENVD 20 1 0\n") is None
    assert prescription_fingerprint("") is None


def test_diam_is_excluded_from_the_fingerprint() -> None:
    """`DIAM` is a *derived* field written from the same wandering edge ray that
    corrupts the recorded image height, so letting it in would split one design in two
    on the strength of a known defect."""

    assert "DIAM" not in " ".join(prescription_rows(_TWO_SURFACES + "DIAM 3.5 0 0 0 0\n"))
    assert prescription_fingerprint(_TWO_SURFACES) == prescription_fingerprint(
        _TWO_SURFACES + "DIAM 3.5 0 0 0 0\n"
    )


def test_unreadable_files_are_listed_not_counted(tmp_path: Path) -> None:
    """A denominator must never be moved by a file nobody could read."""

    good = tmp_path / "good.zmx"
    good.write_bytes(_TWO_SURFACES.encode("utf-8"))
    empty = tmp_path / "empty.zmx"
    empty.write_bytes(b"VERS 1\nUNIT MM\n")

    result = distinct_designs([good, empty])
    assert result["files"] == 2
    assert result["distinct_designs"] == 1
    assert result["unfingerprinted"] == ["empty.zmx"]


def test_duplicate_files_collapse_to_one_design(tmp_path: Path) -> None:
    a = tmp_path / "a.zmx"
    b = tmp_path / "b.zmx"
    a.write_bytes(_TWO_SURFACES.encode("utf-8"))
    b.write_bytes(_TWO_SURFACES.encode("utf-8"))
    result = distinct_designs([a, b])
    assert result["distinct_designs"] == 1
    assert result["shared_prescriptions"] == 1
    assert result["files_in_shared_prescriptions"] == 2


@pytest.mark.skipif(not ZMX_DIR.is_dir(), reason="corpus ZMX not present")
def test_the_corpus_has_fewer_designs_than_files() -> None:
    """The measurement this module exists for. Asserted as an inequality plus an
    exact-count regression pin, so a future intake change that silently starts
    republishing duplicates shows up here rather than in a headline rate.
    """

    paths = sorted({p.name.lower(): p for p in ZMX_DIR.iterdir() if p.is_file()}.values())
    result = distinct_designs(paths)
    assert result["unfingerprinted"] == [], "a corpus ZMX could not be fingerprinted"
    assert result["distinct_designs"] < result["files"]
    assert (result["files"], result["distinct_designs"]) == (442, 354)


@pytest.mark.skipif(not ZMX_DIR.is_dir(), reason="corpus ZMX not present")
def test_a_known_family_group_shares_one_prescription() -> None:
    """Named example, so the abstract count has something concrete behind it: four
    publication numbers, one embodiment."""

    family = [
        "US-11933948-B2-e10.zmx",
        "US-12259531-B2-e10.zmx",
        "US-20240168263-A1-e10.zmx",
        "US-20250189767-A1-e10.zmx",
    ]
    fingerprints = {fingerprint_zmx(ZMX_DIR / name) for name in family}
    assert len(fingerprints) == 1
    assert None not in fingerprints
