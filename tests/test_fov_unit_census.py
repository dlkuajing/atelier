"""``fov_deg`` claims to be one quantity; the census has to be able to say it isn't."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.fov_unit_census import census, render

_ZMX = "\r\n".join(
    [
        "VERS 190513",
        "MODE SEQ",
        "FTYP 0 0 3 3 0 0 0",
        "XFLN 0 0 0",
        "YFLN 0 {half:g} {edge:g}",
        "SURF 0",
        "",
    ]
)


def _corpus(tmp_path: Path, cases: list[dict[str, object]], angles: dict[str, float]) -> tuple:
    zmx_dir = tmp_path / "zmx"
    zmx_dir.mkdir()
    for name, edge in angles.items():
        (zmx_dir / name).write_bytes(
            _ZMX.format(half=edge / 2.0, edge=edge).encode("latin-1")
        )
    index = tmp_path / "index.json"
    index.write_text(json.dumps(cases), encoding="utf-8")
    return index, zmx_dir


def test_a_half_angle_row_and_a_full_fov_row_are_told_apart(tmp_path: Path) -> None:
    index, zmx_dir = _corpus(
        tmp_path,
        [
            {
                "case_id": "HALF", "scenario": "smartphone-wide", "source_zmx": "a.zmx",
                "fov_deg": 40.0, "efl_mm": 4.0, "image_height_mm": 4.0 * 0.8391,
            },
            {
                "case_id": "FULL", "scenario": "smartphone-wide", "source_zmx": "b.zmx",
                "fov_deg": 80.0, "efl_mm": 4.0, "image_height_mm": 4.0 * 0.8391,
            },
        ],
        {"a.zmx": 40.0, "b.zmx": 40.0},
    )
    rows, summary = census(case_index=index, zmx_dir=zmx_dir)
    assert {r.case_id: r.convention for r in rows} == {"HALF": "half", "FULL": "full"}
    assert summary["mixed"] is True
    assert "MIXED UNITS" in render(summary)


def test_a_single_convention_corpus_is_not_reported_as_mixed(tmp_path: Path) -> None:
    """The negative control: this census must be able to come back clean."""
    index, zmx_dir = _corpus(
        tmp_path,
        [
            {
                "case_id": f"C{i}", "scenario": "smartphone-wide", "source_zmx": "a.zmx",
                "fov_deg": 80.0, "efl_mm": 4.0, "image_height_mm": 3.3564,
            }
            for i in range(3)
        ],
        {"a.zmx": 40.0},
    )
    _, summary = census(case_index=index, zmx_dir=zmx_dir)
    assert summary["conventions"] == {"full": 3}
    assert summary["mixed"] is False
    assert "single convention throughout" in render(summary)


def test_the_image_height_check_separates_a_wrong_zmx_from_a_wrong_manifest(
    tmp_path: Path,
) -> None:
    """If theta were double the true half angle, imh/(EFL*tan θ) lands near 0.5."""
    index, zmx_dir = _corpus(
        tmp_path,
        [
            {
                "case_id": "GOOD", "scenario": "s", "source_zmx": "a.zmx",
                "fov_deg": 80.0, "efl_mm": 4.0, "image_height_mm": 4.0 * 0.8391,
            },
            {
                "case_id": "ZMX_TOO_WIDE", "scenario": "s", "source_zmx": "b.zmx",
                "fov_deg": 80.0, "efl_mm": 4.0, "image_height_mm": 4.0 * 0.36397,
            },
        ],
        {"a.zmx": 40.0, "b.zmx": 40.0},
    )
    rows = {r.case_id: r for r in census(case_index=index, zmx_dir=zmx_dir)[0]}
    assert rows["GOOD"].rectilinear_consistency == pytest.approx(1.0, rel=1e-3)
    assert rows["ZMX_TOO_WIDE"].rectilinear_consistency == pytest.approx(0.4337, rel=1e-2)


def test_non_angular_and_missing_inputs_are_skipped_not_guessed(tmp_path: Path) -> None:
    index, zmx_dir = _corpus(
        tmp_path,
        [
            {"case_id": "NOZMX", "scenario": "s", "source_zmx": "gone.zmx", "fov_deg": 80.0},
            {"case_id": "RIH", "scenario": "s", "source_zmx": "r.zmx", "fov_deg": 80.0},
            {"case_id": "NOFOV", "scenario": "s", "source_zmx": "a.zmx", "fov_deg": 0.0},
        ],
        {"a.zmx": 40.0},
    )
    (zmx_dir / "r.zmx").write_bytes(
        _ZMX.format(half=20.0, edge=40.0).replace("FTYP 0 ", "FTYP 3 ").encode("latin-1")
    )
    rows, summary = census(case_index=index, zmx_dir=zmx_dir)
    assert rows == []
    assert summary["skipped"] == {
        "zmx_missing": 1,
        "zmx_not_angular": 1,
        "fov_deg_unusable": 1,
    }


def test_the_real_corpus_now_carries_one_convention() -> None:
    """The migration's witness, from the same census that found the split.

    Measured before `reanchor_fov_deg` ran: 253 half + 172 full, both with
    imh/(EFL*tan θ) ~ 1.0 -- which is what proved the ZMX side was right in both
    groups and the manifest was what disagreed with itself. After the migration
    every anchorable case states a full FOV. The negative control above proves
    this census can still come back "mixed", so a clean answer here is a finding,
    not a broken screen.
    """
    _, summary = census()
    assert summary["mixed"] is False
    assert summary["conventions"] == {"full": summary["full_n"]}
    assert summary["full_n"] > 400
    assert summary["full_rectilinear_consistency_median"] == pytest.approx(1.0, abs=0.05)
