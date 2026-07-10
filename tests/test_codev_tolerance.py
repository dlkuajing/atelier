"""Offline tests for the Phase 14 TOR contract."""

from pathlib import Path

import pytest

from app.core.engines.codev_tolerance import (
    TorCompensators,
    TorMonteCarlo,
    TorToleranceTable,
    build_codev_tor_sequence,
    parse_codev_tor_exports,
)


def _build(**overrides: object) -> str:
    kwargs = {
        "source_path": Path("seed.zmx"),
        "performance_result_path": Path("tor_per.tsv"),
        "monte_carlo_result_path": Path("tor_mc.tsv"),
        "tolerance_table": TorToleranceTable(("DLT S1 0.01",), "expert fixture"),
        "compensators": TorCompensators(("CMP DLZ SI",), "expert fixture"),
        "monte_carlo": TorMonteCarlo(1000),
        "metric": "mtf",
        "mtf_frequency_lp_per_mm": 100.0,
    }
    kwargs.update(overrides)
    return build_codev_tor_sequence(**kwargs)  # type: ignore[arg-type]


def test_build_tor_sequence_uses_explicit_tables_and_buffer_exports() -> None:
    sequence = _build()
    assert "DLT S1 0.01\nCMP DLZ SI\nTOR\nFRE 100\nNTR 1000" in sequence
    assert "WBF PER\nGO\nBUF EXP B1 \"tor_per.tsv\"" in sequence
    assert "WBF MC\nGO\nBUF EXP B1 \"tor_mc.tsv\"" in sequence
    assert "DEF TOL" not in sequence


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tolerance_table", TorToleranceTable((), "expert"), "explicit and non-empty"),
        ("compensators", TorCompensators((), "expert"), "explicit and non-empty"),
        ("monte_carlo", TorMonteCarlo(0), "must be positive"),
    ],
)
def test_build_tor_sequence_rejects_implicit_configuration(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _build(**{field: value})


def test_build_rms_tor_rejects_mtf_frequency() -> None:
    with pytest.raises(ValueError, match="only valid for MTF"):
        _build(metric="rms", mtf_frequency_lp_per_mm=100.0)


def test_parser_missing_exports_is_unavailable(tmp_path: Path) -> None:
    result = parse_codev_tor_exports(tmp_path / "per.tsv", tmp_path / "mc.tsv")
    assert result.status == "unavailable"
    assert result.provenance == "unavailable"
    assert "missing" in result.reason


def test_parser_existing_unknown_exports_does_not_invent_yield(tmp_path: Path) -> None:
    per = tmp_path / "per.tsv"
    mc = tmp_path / "mc.tsv"
    per.write_text("unknown real-format placeholder", encoding="ascii")
    mc.write_text("unknown real-format placeholder", encoding="ascii")
    result = parse_codev_tor_exports(per, mc)
    assert result.status == "unavailable"
    assert "awaits a real-machine sample" in result.reason
