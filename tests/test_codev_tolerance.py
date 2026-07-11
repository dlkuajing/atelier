"""Offline tests for the Phase 14 TOR contract."""

from pathlib import Path

import pytest

from app.core.engines.codev_batch import CodeVBatchError
from app.core.engines.codev_tolerance import (
    TorCompensators,
    TorMonteCarlo,
    TorParseStatus,
    TorToleranceTable,
    build_codev_tor_sequence,
    parse_codev_tor_exports,
    run_codev_tor,
)
from app.core.engines.tor_yield import UNRATIFIED_TOR_YIELD_POLICY, TorYieldPolicy, compute_mc_yield

FIXTURES = Path(__file__).parent / "data" / "codev_tor"
REAL_PER = next(FIXTURES.glob("real_sample_per_*.txt"))
REAL_MC = next(FIXTURES.glob("real_sample_mc_*.txt"))
REAL_ZMX = Path("data/zmx/US20170003482A1.zmx")


def _build(**overrides: object) -> str:
    kwargs = {
        "source_path": REAL_ZMX,
        "performance_result_path": Path("tor_per.tsv"),
        "monte_carlo_result_path": Path("tor_mc.tsv"),
        "tolerance_table": TorToleranceTable(("DLT S1 0.01",), "expert fixture"),
        "compensators": TorCompensators(
            ("CMP DLZ SI",), "expert fixture", "active focus compensation after assembly"
        ),
        "monte_carlo": TorMonteCarlo(1000),
        "metric": "mtf",
        "mtf_frequency_lp_per_mm": 100.0,
    }
    kwargs.update(overrides)
    return build_codev_tor_sequence(**kwargs)  # type: ignore[arg-type]


def test_build_tor_sequence_uses_verified_single_go_two_buffer_grammar() -> None:
    sequence = _build()
    assert "TOR\nFRE 100\nAZI 90\nNTR 1000" in sequence
    assert "WBF B1 PER\nWBF B2 MC\nGO" in sequence
    assert 'BUF EXP B1 "tor_per.tsv"' in sequence
    assert 'BUF EXP B2 "tor_mc.tsv"' in sequence
    assert sequence.count("\nGO\n") == 1


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("tolerance_table", TorToleranceTable((), "expert"), "explicit and non-empty"),
        (
            "compensators",
            TorCompensators((), "expert", "assembly sequence"),
            "explicit and non-empty",
        ),
        ("monte_carlo", TorMonteCarlo(0), "between 1 and 1000000"),
        ("monte_carlo", TorMonteCarlo(1_000_001), "between 1 and 1000000"),
        ("monte_carlo", TorMonteCarlo(True), "must be an integer"),
        ("metric", "MTF", "metric must be"),
        ("metric", "spot", "metric must be"),
        ("source_path", Path("seed.seq"), "must be a ZMX"),
        ("performance_result_path", Path("tor_mc.tsv"), "must differ"),
        ("performance_result_path", REAL_ZMX, "differ from source"),
        ("source_path", Path("missing.zmx"), "must exist"),
    ],
)
def test_build_tor_sequence_rejects_illegal_input_matrix(
    field: str, value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _build(**{field: value})


@pytest.mark.parametrize("separator", ["\n", "\r", "\r\n"])
def test_provenance_cannot_inject_codev_commands(separator: str) -> None:
    table = TorToleranceTable(("DLT S1 0.01",), f"expert{separator}DEF TOL S1..17")
    with pytest.raises(ValueError, match="single-line metadata"):
        _build(tolerance_table=table)


@pytest.mark.parametrize("value", ["DEF TOL S1..17", "GO", "BUF DEL B1"])
def test_command_like_provenance_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="non-command"):
        _build(tolerance_table=TorToleranceTable(("DLT S1 0.01",), value))


def test_semicolon_command_injection_is_rejected() -> None:
    with pytest.raises(ValueError, match="single commands"):
        _build(tolerance_table=TorToleranceTable(("DLT S1 0.01; GO",), "expert"))


def test_def_tol_requires_explicit_surface_range() -> None:
    with pytest.raises(ValueError, match="explicit surface"):
        _build(tolerance_table=TorToleranceTable(("DEF TOL",), "smoke only"))
    assert "DEF TOL S1..17" in _build(
        tolerance_table=TorToleranceTable(("DEF TOL S1..17",), "smoke only")
    )


def test_mtf_azimuth_is_explicit_and_validated() -> None:
    assert "AZI 0" in _build(mtf_azimuth_deg=0.0)
    for value in (-1.0, 180.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="mtf_azimuth_deg"):
            _build(mtf_azimuth_deg=value)


def test_build_rms_tor_rejects_mtf_parameters() -> None:
    with pytest.raises(ValueError, match="only valid for MTF"):
        _build(metric="rms", mtf_frequency_lp_per_mm=None, mtf_azimuth_deg=0.0)


def test_parser_missing_exports_is_unavailable(tmp_path: Path) -> None:
    result = parse_codev_tor_exports(tmp_path / "per.tsv", tmp_path / "mc.tsv")
    assert result.status is TorParseStatus.UNAVAILABLE
    assert "missing" in result.reason


def test_parser_real_machine_fixtures_returns_structure_not_yield() -> None:
    result = parse_codev_tor_exports(REAL_PER, REAL_MC)
    assert result.status is TorParseStatus.UNAVAILABLE
    assert result.declared_trials == 20
    assert len(result.performance_rows) == 3
    assert len(result.monte_carlo_rows) == 60
    assert result.performance_rows[0].azimuth_deg == 90
    assert result.performance_rows[0].probability_columns[0] == pytest.approx(5.08389)
    assert result.monte_carlo_rows[18].value == pytest.approx(0.186827)
    assert "not ratified" in result.reason


def test_parser_rejects_unknown_or_same_path_exports(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.tsv"
    unknown.write_text("unknown", encoding="ascii")
    same = parse_codev_tor_exports(unknown, unknown)
    assert "identical" in same.reason
    other = tmp_path / "other.tsv"
    other.write_text("unknown", encoding="ascii")
    result = parse_codev_tor_exports(unknown, other)
    assert result.status is TorParseStatus.UNAVAILABLE
    assert "parse failed" in result.reason


def test_parser_rejects_nonfinite_mc_value(tmp_path: Path) -> None:
    mc = tmp_path / "mc.tsv"
    mc.write_text(REAL_MC.read_text(encoding="utf-8").replace("0.186827", "nan"), encoding="utf-8")
    result = parse_codev_tor_exports(REAL_PER, mc)
    assert "must be finite" in result.reason


def test_tor_runner_accepts_rc1_and_parses_both_exports(tmp_path: Path) -> None:
    def fake(command, **kwargs):
        (Path(kwargs["cwd"]) / "atelier_tor_per.tsv").write_bytes(REAL_PER.read_bytes())
        (Path(kwargs["cwd"]) / "atelier_tor_mc.tsv").write_bytes(REAL_MC.read_bytes())
        return type("P", (), {"returncode": 1, "stderr": ""})()
    result = run_codev_tor(source_zmx=REAL_ZMX, work_dir=tmp_path / "tor", runner=fake, tolerance_table=TorToleranceTable(("DLT S1 0.01",), "expert"), compensators=TorCompensators(("CMP DLZ SI",), "expert", "assembly"), monte_carlo=TorMonteCarlo(20), metric="mtf", mtf_frequency_lp_per_mm=100.0)
    assert result.returncode == 1
    assert len(result.parse_result.monte_carlo_rows) == 60


def test_tor_runner_missing_mc_is_unavailable(tmp_path: Path) -> None:
    def fake(command, **kwargs):
        (Path(kwargs["cwd"]) / "atelier_tor_per.tsv").write_bytes(REAL_PER.read_bytes())
        return type("P", (), {"returncode": 0, "stderr": ""})()
    result = run_codev_tor(source_zmx=REAL_ZMX, work_dir=tmp_path / "tor", runner=fake, tolerance_table=TorToleranceTable(("DLT S1 0.01",), "expert"), compensators=TorCompensators(("CMP DLZ SI",), "expert", "assembly"), monte_carlo=TorMonteCarlo(20), metric="mtf", mtf_frequency_lp_per_mm=100)
    assert "missing" in result.parse_result.reason


def test_tor_runner_rc2_errors(tmp_path: Path) -> None:
    with pytest.raises(CodeVBatchError):
        run_codev_tor(source_zmx=REAL_ZMX, work_dir=tmp_path / "tor", runner=lambda *a, **k: type("P", (), {"returncode": 2, "stderr": "bad"})(), tolerance_table=TorToleranceTable(("DLT S1 0.01",), "expert"), compensators=TorCompensators(("CMP DLZ SI",), "expert", "assembly"), monte_carlo=TorMonteCarlo(20), metric="mtf", mtf_frequency_lp_per_mm=100)


def test_tor_yield_default_off_and_ratified_math() -> None:
    parsed = parse_codev_tor_exports(REAL_PER, REAL_MC)
    assert compute_mc_yield(parsed, UNRATIFIED_TOR_YIELD_POLICY).status == "unavailable"
    measured = compute_mc_yield(parsed, TorYieldPolicy("MTF", 0.1, "min", True, "Tolerancing.pdf + probe"))
    assert measured.status == "measured"
    assert measured.trials == 20
    assert measured.yield_fraction == pytest.approx(0.0)
    assert measured.per_field_yield["z1:f1"] == pytest.approx(0.9)
    assert measured.saturation_fraction == pytest.approx(58 / 60)
