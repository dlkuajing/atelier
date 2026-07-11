from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_PATH = Path(__file__).parents[1] / "scripts/p13_mystery_bisect.py"
SPEC = importlib.util.spec_from_file_location("p13_mystery_bisect", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_grid_has_anchors_hybrids_and_budget() -> None:
    grid = module.build_grid()
    assert len(grid) == 28
    assert {cell.source for cell in grid} == set(module.SOURCES)
    assert {cell.command for cell in grid} == set(module.COMMANDS)
    assert all(
        any(cell.source == source and cell.command == "import" for cell in grid)
        for source in module.SOURCES
    )
    assert all(
        any(cell.source == source and cell.command == command for cell in grid)
        for source in ("seed", "candidate")
        for command in module.COMMANDS
    )


def test_sources_are_deterministic_single_block_swaps() -> None:
    seed = module.SEED.read_text(encoding="ascii")
    candidate = module.CANDIDATE.read_text(encoding="ascii")
    sources = module.build_sources(seed, candidate)
    assert sources["hybrid-header"].startswith(seed.split("SURF 0", 1)[0])
    assert "NAME 2017" in sources["hybrid-name"]
    assert "WAVM 1 0.48613269999999997 1" in sources["hybrid-wavelength"]
    assert sources == module.build_sources(seed, candidate)


def test_command_sequences_and_crlf() -> None:
    for command in module.COMMANDS:
        sequence = module.build_sequence(command)
        assert '\r\nIN CV_MACRO:ZEMAXOS_TO_CV "inputzmx"' in sequence
        assert "\n" not in sequence.replace("\r\n", "")
    assert "FCT @p13ok" in module.build_sequence("fct")
    assert "LCL NUM ^p13row" in module.build_sequence("lcl")
    assert "BUF EXP B1" in module.build_sequence("readout")
    assert "SAV probe_lens.1" in module.build_sequence("sav")
    assert "WRL probe_lens" in module.build_sequence("wrl")


def test_verdict_parser() -> None:
    assert module.classify_listing("completed normally").kind == "clean"
    cascade = module.classify_listing("ERROR - Zero or negative value for row qualifier\n" * 3)
    assert (cascade.kind, cascade.detail) == ("row-cascade", "3")
    assert module.classify_listing("*** Syntax error in FCT").kind == "compile-error"
    assert module.classify_listing("", timed_out=True).kind == "timeout"


def test_fake_runner_and_tsv_shape(tmp_path: Path) -> None:
    def fake_runner(command: list[str], *, work_dir: Path, timeout_seconds: float):
        assert command[-2:] == ["/B", "probe.seq"]
        assert timeout_seconds == 1
        (work_dir / "probe.lis").write_text("completed normally", encoding="ascii")
        return SimpleNamespace(returncode=0), "", "", 0.25

    cell = module.Cell(0, "seed", "import")
    result = module.run_cell(cell, "NAME seed\nSURF 0\n", tmp_path, timeout=1, runner=fake_runner)
    module.write_reports([result], tmp_path)
    with (tmp_path / "summary.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert list(rows[0]) == [
        "cell",
        "source",
        "command_set",
        "verdict",
        "detail",
        "returncode",
        "duration_seconds",
        "seq",
        "lis",
    ]
    assert rows[0]["verdict"] == "clean"
    assert result.sequence_path.read_bytes().count(b"\r\n") > 1
