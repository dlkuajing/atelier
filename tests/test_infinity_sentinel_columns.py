"""Gate: a patent's `1E+18` may not become a real number in any column.

Patent surface tables print ``1E+18`` where a radius is plano. The conversion
path read it with the ordinary number parser, encoded it on the **radius**
column (`_request_radius_mm`, plus `zmx_writer._fmt_number` collapsing the
resulting ``1e-18`` curvature to ``0``), and passed it through untouched on the
**thickness** column. Eight corpus files therefore carry ``DISZ 1e+18`` on their
last surface -- an image plane 1e18 mm away.

They passed every intake gate because EFL is paraxial and does not move when the
image plane does, and they were invisible to the fidelity audit because it read
``FNUM`` / ``YFLN`` / aspheric terms and never read ``DISZ``.

What is pinned here:

* the **asymmetry is gone** -- both columns now go through one sentinel test;
* the interior/last-surface distinction, because mapping an interior infinite
  gap to ``0`` would invent geometry while mapping the post-image row to ``0``
  adopts the corpus's own convention (375 of 442 files);
* the **void** that makes the magnitude cut a fact rather than a tuning knob;
* the **set equality** that identifies the defect: the files with a huge last
  ``DISZ`` are exactly the files whose CODE V spot is huge.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from scripts.corpus_fidelity_audit import (
    DEFAULT_POOLS,
    MAX_PHYSICAL_SEPARATION_MM,
    audit_seed,
    read_zmx_text,
)
from scripts.patent_to_zmx import (
    INFINITY_SENTINEL_MM,
    PatentParseError,
    _is_infinity_sentinel,
    _request_radius_mm,
    _request_thickness_mm,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
QUARANTINE = REPO_ROOT / ".planning" / "evidence" / "corpus-fidelity-quarantine.json"
_DISZ = re.compile(r"^\s*DISZ\s+([-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?)\s*$", re.MULTILINE)


def _zmx(disz: str, *, fnum: str = "2.0") -> str:
    return (
        "VERS 191028 13541 33913 33913\n"
        "MODE SEQ\n"
        "UNIT MM X W X CM MR CPMM\n"
        f"FNUM {fnum} 0\n"
        "FTYP 0 0 2 3 0 0 0 2\n"
        "XFLN 0 0\n"
        "YFLN 0 20.3\n"
        "WAVM 1 0.4861 1\n"
        "SURF 1\n"
        '  TYPE STANDARD\n  CURV 0.5 0 0 0 0 ""\n'
        f"  DISZ {disz}\n"
    )


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "synthetic.zmx"
    path.write_bytes(text.encode("utf-8"))
    return path


# --------------------------------------------------------------------------
# the sentinel test itself
# --------------------------------------------------------------------------


def test_both_spellings_of_infinity_are_one_test() -> None:
    assert _is_infinity_sentinel(math.inf)
    assert _is_infinity_sentinel(-math.inf)
    assert _is_infinity_sentinel(1e18)
    assert _is_infinity_sentinel(-1e18)
    assert _is_infinity_sentinel(INFINITY_SENTINEL_MM)
    assert not _is_infinity_sentinel(None)
    assert not _is_infinity_sentinel(0.0)
    assert not _is_infinity_sentinel(1200.0)  # the largest real separation measured


def test_the_radius_column_keeps_its_old_behaviour() -> None:
    assert _request_radius_mm(math.inf) == 0.0
    assert _request_radius_mm(1e18) == 0.0
    assert _request_radius_mm(4.2) == 4.2
    assert _request_radius_mm(None) is None


def test_the_last_surface_adopts_the_corpus_convention() -> None:
    """The row after the image plane carries no optics; the corpus writes 0."""

    assert _request_thickness_mm(1e18, is_last_surface=True) == 0.0
    assert _request_thickness_mm(math.inf, is_last_surface=True) == 0.0


def test_an_interior_infinite_gap_fails_closed() -> None:
    """A misread column is not an air gap, and 0 would be an invented number."""

    with pytest.raises(PatentParseError, match="thickness column"):
        _request_thickness_mm(1e18, is_last_surface=False)
    with pytest.raises(PatentParseError):
        _request_thickness_mm(math.inf, is_last_surface=False)


def test_ordinary_thicknesses_are_untouched_in_both_positions() -> None:
    for last in (True, False):
        assert _request_thickness_mm(0.4458, is_last_surface=last) == 0.4458
        assert _request_thickness_mm(-0.4458, is_last_surface=last) == -0.4458
        assert _request_thickness_mm(0.0, is_last_surface=last) == 0.0
        assert _request_thickness_mm(None, is_last_surface=last) is None


# --------------------------------------------------------------------------
# the audit gate, so already-shipped files are caught without regenerating them
# --------------------------------------------------------------------------


def test_the_audit_now_reads_disz(tmp_path: Path) -> None:
    assert audit_seed(_write(tmp_path, _zmx("1e+18")), "t").hard == (
        "separation_beyond_physical_scale",
    )


def test_a_long_but_real_separation_is_not_flagged(tmp_path: Path) -> None:
    """1200 mm is the largest separation actually present in either pool."""

    audit = audit_seed(_write(tmp_path, _zmx("1200")), "t")
    assert audit.hard == ()
    assert audit.max_separation_mm == 1200.0


def test_an_object_at_infinity_is_spelled_INFINITY_and_is_legitimate(tmp_path: Path) -> None:
    """`DISZ INFINITY` is the normal object row. Screening it would flag the corpus."""

    audit = audit_seed(_write(tmp_path, _zmx("INFINITY")), "t")
    assert audit.hard == ()


# --------------------------------------------------------------------------
# the corpus-level facts the fix rests on
# --------------------------------------------------------------------------


def _pool_separations() -> dict[str, list[tuple[float, str]]]:
    out: dict[str, list[tuple[float, str]]] = {}
    for pool, root in DEFAULT_POOLS:
        rows: list[tuple[float, str]] = []
        for path in sorted(root.iterdir()):
            if path.suffix.lower() != ".zmx":
                continue
            text = read_zmx_text(path).replace("\r\n", "\n")
            for value in _DISZ.findall(text):
                rows.append((abs(float(value)), path.name))
        out[pool] = rows
    return out


def test_the_magnitude_cut_sits_in_a_void() -> None:
    """The cut is only defensible because nothing lives near it. Measured
    2026-08-02: largest real separation 1200 mm, next value up 1e+18."""

    rows = [row for pool_rows in _pool_separations().values() for row in pool_rows]
    below = [value for value, _ in rows if value < MAX_PHYSICAL_SEPARATION_MM]
    above = [value for value, _ in rows if value >= MAX_PHYSICAL_SEPARATION_MM]
    assert below and above
    assert max(below) < MAX_PHYSICAL_SEPARATION_MM <= min(above)
    assert min(above) / max(below) > 1e6, (
        "real and sentinel separations are no longer separated by a void; the cut "
        "has to be re-derived rather than kept"
    )


def test_exactly_the_eight_known_files_trip_the_new_gate() -> None:
    """Set equality, not a count: a new asset acquiring this defect must show up
    as a quarantine change, not be absorbed by a tolerance."""

    tripped = {
        name
        for pool_rows in _pool_separations().values()
        for value, name in pool_rows
        if value >= MAX_PHYSICAL_SEPARATION_MM
    }
    recorded = {
        name
        for pool in json.loads(QUARANTINE.read_text(encoding="utf-8"))["pools"].values()
        for name, reasons in pool["defective"].items()
        if "separation_beyond_physical_scale" in reasons
    }
    assert tripped == recorded
    assert len(tripped) == 8


def test_the_defect_lives_only_on_the_last_surface() -> None:
    """The reason the eight are repairable at all: every earlier surface is intact,
    which is why their EFL still matches the patent's declared value."""

    for pool, root in DEFAULT_POOLS:
        for path in sorted(root.iterdir()):
            if path.suffix.lower() != ".zmx":
                continue
            values = [abs(float(v)) for v in _DISZ.findall(read_zmx_text(path).replace("\r\n", "\n"))]
            huge = [i for i, v in enumerate(values) if v >= MAX_PHYSICAL_SEPARATION_MM]
            if not huge:
                continue
            assert huge == [len(values) - 1], (
                f"{pool}/{path.name}: sentinel on an interior surface {huge}; the "
                "last-surface repair story does not apply to this file"
            )
