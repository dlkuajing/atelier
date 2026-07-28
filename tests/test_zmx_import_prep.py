"""Gate: every CODE V import carries a WAVM flush sentinel.

Root cause guarded against (macro source ``D:/CODEV115/macro/zemaxos_to_cv.seq``
plus real-machine A/B 2026-07-27): ``ZEMAXOS_TO_CV`` emits the ``wl``/``wtw``
commands only from its ``else if ^zwlnum = ^nwl+1`` branch, where ``^nwl`` is
read from ``FTYP`` column j5. A prescription whose ``WAVM`` row count *equals*
its declared wavelength count never supplies that sentinel row, so the flush
never fires and the lens imports with CODE V's built-in single default
wavelength — silently. 403 of the 442 corpus seeds are in exactly that shape.

The damage is not a missing feature but a *wrong number*: ``@lcum`` measures
``|W1 image point - W(NUM W) image point|``, which with ``NUM W = 1`` is
identically ``0.0`` — "perfectly achromatic" reported for a system whose
dispersion was never evaluated. Every glass also reports ``vd_source=None``
because the readout macro gates its dispersion probe on ``IF (NUM W) >= 3``.

Real-machine measurements behind these assertions (10 sequential runs):
three 3-row seeds each read ``NUM W=1`` with ``0/N`` measurable vd as-is, and
``NUM W=3`` with ``N/N`` vd once a single sentinel row is appended; the 24-row
control read ``NUM W=5`` with ``4/4``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.engines.codev_batch import ensure_codev_safe_input_path
from app.core.engines.zmx_import_prep import (
    CODEV_WAVM_SLOTS,
    STAGED_INPUT_DIRNAME,
    count_wavm_rows,
    declared_field_count,
    declared_wavelength_count,
    decode_zmx_text,
    encode_zmx_text,
    pad_wavm_bytes,
    pad_wavm_slots,
    stage_zmx_for_codev,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR

_THREE_ROW_HEADER = (
    "VERS 191028 13541 33913 33913\n"
    "MODE SEQ\n"
    "NAME probe\n"
    "FTYP 0 0 2 3 0 0 0 2\n"
    "WAVM 1 0.4861 1\n"
    "WAVM 2 0.5876 1\n"
    "WAVM 3 0.6563 1\n"
    "PWAV 2\n"
    "SURF 0\n"
)


def _wavm_slots(text: str) -> list[int]:
    return [int(line.split()[1]) for line in text.splitlines() if line.startswith("WAVM")]


def test_pad_wavm_slots_appends_the_flush_sentinel() -> None:
    padded, added = pad_wavm_slots(_THREE_ROW_HEADER)

    assert added == CODEV_WAVM_SLOTS - 3
    assert _wavm_slots(padded) == list(range(1, CODEV_WAVM_SLOTS + 1))
    # The sentinel is the whole point: the macro flushes on slot ^nwl+1, and
    # ^nwl comes from FTYP, not from the row count.
    nwl = declared_wavelength_count(padded)
    assert nwl == 3
    assert count_wavm_rows(padded) > nwl


def test_pad_wavm_slots_keeps_the_declared_wavelengths_verbatim() -> None:
    padded, _added = pad_wavm_slots(_THREE_ROW_HEADER)

    real_rows = [line for line in padded.splitlines() if line.startswith("WAVM")][:3]
    assert real_rows == ["WAVM 1 0.4861 1", "WAVM 2 0.5876 1", "WAVM 3 0.6563 1"]


def test_pad_wavm_slots_is_a_noop_when_the_table_is_already_full() -> None:
    full = _THREE_ROW_HEADER.replace(
        "WAVM 3 0.6563 1\n",
        "WAVM 3 0.6563 1\n"
        + "".join(f"WAVM {slot} 0.55 1\n" for slot in range(4, CODEV_WAVM_SLOTS + 1)),
    )

    padded, added = pad_wavm_slots(full)

    assert added == 0
    assert padded == full


def test_pad_wavm_slots_preserves_crlf_line_endings() -> None:
    crlf = _THREE_ROW_HEADER.replace("\n", "\r\n")

    padded, added = pad_wavm_slots(crlf)

    assert added == CODEV_WAVM_SLOTS - 3
    assert "\n" not in padded.replace("\r\n", "")
    # Line endings are not the discriminator: all 442 corpus files are CRLF,
    # including the 39 that import their full wavelength set.
    assert padded.count("\r\n") == crlf.count("\r\n") + added


def test_pad_wavm_slots_passes_through_files_with_no_wavm_table() -> None:
    wavl_only = "VERS 1\nFTYP 0 0 2 3 0 0 0 2\nWAVL 0.4861 0.5876 0.6563\nSURF 0\n"

    padded, added = pad_wavm_slots(wavl_only)

    # The macro handles WAVL through a separate branch that needs no sentinel;
    # inventing a WAVM table here would manufacture wavelengths.
    assert (padded, added) == (wavl_only, 0)


@pytest.mark.parametrize(
    "slots",
    [
        [1, 2, 4],
        [0, 1, 2],
        [2, 3, 4],
        list(range(1, CODEV_WAVM_SLOTS + 2)),
    ],
)
def test_pad_wavm_slots_rejects_malformed_tables(slots: list[int]) -> None:
    rows = "".join(f"WAVM {slot} 0.55 1\n" for slot in slots)
    text = f"VERS 1\nFTYP 0 0 2 3 0 0 0 2\n{rows}SURF 0\n"

    with pytest.raises(ValueError, match="contiguous"):
        pad_wavm_slots(text)


def test_pad_wavm_bytes_round_trips_a_utf16_bom_file() -> None:
    raw = encode_zmx_text(_THREE_ROW_HEADER, "utf-16-le-bom")

    padded_raw, added = pad_wavm_bytes(raw)
    text, encoding = decode_zmx_text(padded_raw)

    assert added == CODEV_WAVM_SLOTS - 3
    assert encoding == "utf-16-le-bom"
    assert count_wavm_rows(text) == CODEV_WAVM_SLOTS


def test_stage_zmx_for_codev_pads_the_copy_and_leaves_the_source_untouched(tmp_path) -> None:
    source = tmp_path / "seed.zmx"
    source.write_bytes(encode_zmx_text(_THREE_ROW_HEADER, "latin-1"))
    original = source.read_bytes()
    work = tmp_path / "work"

    staged = stage_zmx_for_codev(source, work)

    assert staged.parent == work / STAGED_INPUT_DIRNAME
    assert staged != source
    # data/zmx is the project's data anchor; staging must never write back to it.
    assert source.read_bytes() == original
    assert count_wavm_rows(decode_zmx_text(staged.read_bytes())[0]) == CODEV_WAVM_SLOTS


def test_stage_zmx_for_codev_copies_an_already_padded_file_verbatim(tmp_path) -> None:
    full, _added = pad_wavm_slots(_THREE_ROW_HEADER)
    source = tmp_path / "seed.zmx"
    source.write_bytes(encode_zmx_text(full, "latin-1"))

    staged = stage_zmx_for_codev(source, tmp_path / "work")

    assert staged.read_bytes() == source.read_bytes()


def test_stage_zmx_for_codev_returns_an_absolute_path_for_a_relative_work_dir(
    tmp_path, monkeypatch
) -> None:
    """A relative work_dir would be applied twice and import a dummy system.

    The staged path is written into ``IN CV_MACRO:ZEMAXOS_TO_CV``, and CODE V
    resolves a relative path there against its own working directory -- which
    ``run_codev_batch`` sets to ``work_dir``. Only three of the five runners
    resolved their ``work_dir`` themselves, so the guarantee belongs here.
    """

    source = tmp_path / "seed.zmx"
    source.write_bytes(encode_zmx_text(_THREE_ROW_HEADER, "latin-1"))
    monkeypatch.chdir(tmp_path)

    staged = stage_zmx_for_codev(source, Path("relative-work"))

    assert staged.is_absolute()
    assert staged.is_file()
    assert staged.parent == (tmp_path / "relative-work" / STAGED_INPUT_DIRNAME).resolve()


def test_stage_zmx_for_codev_rejects_a_dot_prefixed_work_dir(tmp_path) -> None:
    """CODE V cannot import from a dotted path, so such a work_dir must fail loudly.

    Real regression (2026-07-28 adversarial review): ``precompute_demo_cache``
    ran under ``ROOT/.tmp/demo-cache-codev``. That was fine while the dotted
    directory only held OUTPUT, but staging put the run's ZMX *input* there too.
    """

    source = tmp_path / "seed.zmx"
    source.write_bytes(encode_zmx_text(_THREE_ROW_HEADER, "latin-1"))

    with pytest.raises(ValueError, match="dot-prefixed"):
        stage_zmx_for_codev(source, tmp_path / ".tmp" / "run")


def test_codev_work_dirs_in_repo_scripts_are_importable() -> None:
    """Guard the caller that this regression actually broke.

    A dot-prefixed run directory is only detectable at run time on a machine with
    CODE V, so pin the constant itself rather than waiting for a real-machine run.
    """

    from scripts.precompute_demo_cache import _CODEV_CACHE_WORK_ROOT

    ensure_codev_safe_input_path(_CODEV_CACHE_WORK_ROOT, role="demo_cache_work_root")


def test_every_corpus_seed_imports_with_a_flush_sentinel_after_staging() -> None:
    """Library-wide invariant, stated with its denominator."""

    seeds = sorted(p for p in ZMX_AMMO_DIR.iterdir() if p.suffix.lower() == ".zmx")
    assert seeds, f"no ZMX seeds found under {ZMX_AMMO_DIR}"

    offenders: list[str] = []
    for seed in seeds:
        text, _encoding = decode_zmx_text(seed.read_bytes())
        padded, _added = pad_wavm_slots(text)
        rows = count_wavm_rows(padded)
        if rows == 0:
            continue  # WAVL-style declaration; a different macro branch.
        nwl = declared_wavelength_count(padded)
        if nwl is None or rows <= nwl:
            offenders.append(f"{seed.name}: wavm_rows={rows} declared_nwl={nwl}")

    assert not offenders, (
        f"{len(offenders)}/{len(seeds)} seeds would still collapse to a single "
        f"wavelength on CODE V import: {offenders[:5]}"
    )


def test_every_codev_import_site_routes_through_the_prep() -> None:
    """Seam guard: a new CODE V import must not bypass wavelength normalization."""

    import app.core.engines.codev_optimize as codev_optimize
    import app.core.engines.codev_readout as codev_readout
    import app.core.engines.codev_roundtrip as codev_roundtrip
    import app.core.engines.codev_tolerance as codev_tolerance
    import app.core.engines.glass_snap_matrix as glass_snap_matrix

    modules = {
        "codev_readout": codev_readout,
        "codev_optimize": codev_optimize,
        "codev_roundtrip": codev_roundtrip,
        "codev_tolerance": codev_tolerance,
        "glass_snap_matrix": glass_snap_matrix,
    }
    missing = [
        name
        for name, module in modules.items()
        if not hasattr(module, "stage_zmx_for_codev") and not hasattr(module, "pad_wavm_bytes")
    ]
    assert not missing, f"CODE V import sites without wavelength normalization: {missing}"


def test_declared_field_count_reads_the_column_left_of_wavelengths() -> None:
    """FTYP j4 is fields, j5 is wavelengths -- an off-by-one here silently
    injects the wrong num_fields into the autovig ladder."""
    text = "FTYP 0 0 2 3 0 0 0 2\nWAVM 1 0.4861 1\n"
    assert declared_field_count(text) == 2
    assert declared_wavelength_count(text) == 3


def test_declared_field_count_needs_a_full_ftyp_row() -> None:
    """A short row declares nothing usable; 0 would be a wrong answer, not a missing one."""
    assert declared_field_count("FTYP 0 0 2 3\n") is None
    assert declared_field_count("NAME lens\n") is None


def test_declared_field_count_rejects_non_numeric_columns() -> None:
    assert declared_field_count("FTYP 0 0 x 3 0 0 0 2\n") is None


def test_declared_field_count_matches_a_real_corpus_seed() -> None:
    from pathlib import Path

    from app.core.engines.zmx_import_prep import decode_zmx_text

    seed = Path("data/zmx/US-12124006-B2-e2.zmx")
    text, _ = decode_zmx_text(seed.read_bytes())
    # CODE V read (NUM F) == 2 for this seed in the 2026-07-28 pilot.
    assert declared_field_count(text) == 2
