"""Re-aiming a seed's field angles must change the angles and nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.engines.seed_field_rebuild import (
    max_field_angle_deg,
    read_field_profile,
    rebuild_seed_field_angles,
    rebuilt_bytes,
)

ZMX_DIR = Path(__file__).resolve().parents[1] / "data" / "zmx"

SEED = "\r\n".join(
    [
        "VERS 190513",
        "MODE SEQ",
        "NAME seed",
        "FTYP 0 0 3 3 0 0 0",
        "XFLN 0 0 0",
        "YFLN 0 12.5 25",
        "VDXN 0 0 0",
        "VDYN 0 0 0",
        "VCXN 0 0 0",
        "VCYN 0 0 0",
        "SURF 0",
        "",
    ]
)


def _seed_bytes(text: str = SEED) -> bytes:
    return text.encode("latin-1")


def test_profile_is_read_from_the_file_not_from_a_declaration() -> None:
    profile = read_field_profile(SEED)
    assert profile.field_type == 0
    assert profile.y_fields == (0.0, 12.5, 25.0)
    assert profile.max_y == pytest.approx(25.0)
    assert profile.is_angular


def test_rebuild_puts_the_outermost_field_exactly_on_target() -> None:
    result = rebuild_seed_field_angles(_seed_bytes(), 37.5)
    assert result.rebuilt, result.reason
    assert max_field_angle_deg(result.text or "") == pytest.approx(37.5)
    assert result.scale == pytest.approx(1.5)


def test_rebuild_preserves_the_seeds_own_field_sampling() -> None:
    """autovig and the vignetting block address fields positionally."""
    result = rebuild_seed_field_angles(_seed_bytes(), 37.5)
    assert read_field_profile(result.text or "").y_fields == pytest.approx((0.0, 18.75, 37.5))
    assert result.normalised_fractions == pytest.approx((0.0, 0.5, 1.0))


def test_rebuild_touches_only_the_yfln_row() -> None:
    result = rebuild_seed_field_angles(_seed_bytes(), 37.5)
    before = SEED.split("\r\n")
    after = (result.text or "").split("\r\n")
    assert len(before) == len(after)
    differing = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert len(differing) == 1
    assert before[differing[0]].startswith("YFLN ")


def test_rebuild_round_trips_the_seeds_encoding_and_line_endings() -> None:
    payload = rebuilt_bytes(rebuild_seed_field_angles(_seed_bytes(), 37.5))
    assert payload.count(b"\r\n") == SEED.count("\r\n")
    assert b"\n" not in payload.replace(b"\r\n", b"")
    assert not payload.startswith(b"\xff\xfe")


def test_a_utf16_seed_stays_utf16() -> None:
    raw = b"\xff\xfe" + SEED.encode("utf-16-le")
    payload = rebuilt_bytes(rebuild_seed_field_angles(raw, 37.5))
    assert payload.startswith(b"\xff\xfe")
    assert "YFLN 0 18.75 37.5" in payload[2:].decode("utf-16-le")


@pytest.mark.parametrize("angle", [0.0, -5.0, 90.0, 180.0, float("nan"), float("inf")])
def test_an_impossible_target_angle_is_refused(angle: float) -> None:
    assert not rebuild_seed_field_angles(_seed_bytes(), angle).rebuilt


def test_a_real_image_height_seed_is_refused_rather_than_reinterpreted() -> None:
    """FTYP 3 YFLN is millimetres. Rescaling it as degrees is the unit bug."""
    text = SEED.replace("FTYP 0 ", "FTYP 3 ")
    result = rebuild_seed_field_angles(text.encode("latin-1"), 37.5)
    assert not result.rebuilt
    assert "FTYP 3" in result.reason
    assert max_field_angle_deg(text) is None


def test_a_skew_seed_is_refused() -> None:
    text = SEED.replace("XFLN 0 0 0", "XFLN 0 1 2")
    assert not rebuild_seed_field_angles(text.encode("latin-1"), 37.5).rebuilt


def test_a_single_field_seed_is_refused() -> None:
    text = SEED.replace("XFLN 0 0 0", "XFLN 0").replace("YFLN 0 12.5 25", "YFLN 25")
    assert not rebuild_seed_field_angles(text.encode("latin-1"), 37.5).rebuilt


def test_an_axis_only_seed_is_refused() -> None:
    text = SEED.replace("YFLN 0 12.5 25", "YFLN 0 0 0")
    assert not rebuild_seed_field_angles(text.encode("latin-1"), 37.5).rebuilt


def test_missing_field_rows_are_refused() -> None:
    text = "\r\n".join(line for line in SEED.split("\r\n") if not line.startswith("YFLN"))
    assert not rebuild_seed_field_angles(text.encode("latin-1"), 37.5).rebuilt


def test_a_failed_rebuild_cannot_be_encoded() -> None:
    with pytest.raises(ValueError):
        rebuilt_bytes(rebuild_seed_field_angles(_seed_bytes(), 0.0))


@pytest.mark.skipif(not ZMX_DIR.is_dir(), reason="corpus not present")
def test_the_corpus_is_overwhelmingly_re_aimable() -> None:
    """A guard that cannot fire on real data is not a guard. Measured 425/442."""
    files = sorted(ZMX_DIR.glob("*.zmx"))
    assert len(files) > 400
    rebuilt = 0
    for path in files:
        result = rebuild_seed_field_angles(path.read_bytes(), 40.0)
        if result.rebuilt:
            rebuilt += 1
            assert max_field_angle_deg(result.text or "") == pytest.approx(40.0)
    assert rebuilt >= 0.9 * len(files)
