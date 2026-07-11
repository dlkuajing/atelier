"""Offline tests for the Phase 14 TOR contract."""

from dataclasses import replace
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
from app.core.engines.tor_yield import (
    UNRATIFIED_TOR_YIELD_POLICY,
    TorYieldPolicy,
    compute_mc_yield,
    mc_saturation_fraction,
)

FIXTURES = Path(__file__).parent / "data" / "codev_tor"
REAL_PER = FIXTURES / "real_sample_per_US20170003482A1_defttol_ntr20_fre100.txt"
REAL_MC = FIXTURES / "real_sample_mc_US20170003482A1_deftol_ntr20_fre100.txt"
CMP_FIXTURES = (
    ("s17", "DLZ S18"),
    ("s19", "DLZ S20"),
)
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
    assert result.compensator_names == ()
    assert len(result.monte_carlo_rows) == 60
    assert result.performance_rows[0].azimuth_deg == 90
    assert result.performance_rows[0].probability_columns[0] == pytest.approx(5.08389)
    assert result.monte_carlo_rows[18].value == pytest.approx(0.186827)
    assert "not ratified" in result.reason


@pytest.mark.parametrize(("family", "compensator_name"), CMP_FIXTURES)
def test_parser_real_machine_compensator_fixtures(
    family: str, compensator_name: str
) -> None:
    per = FIXTURES / f"real_sample_per_cmpdlz_{family}_ntr100_fre100.txt"
    mc = FIXTURES / f"real_sample_mc_cmpdlz_{family}_ntr100_fre100.txt"

    result = parse_codev_tor_exports(per, mc)

    assert result.compensator_names == (compensator_name,)
    assert len(result.performance_rows) == 3
    assert all(len(row.compensator_ranges) == 1 for row in result.performance_rows)
    assert result.declared_trials == 100
    assert {row.sample for row in result.monte_carlo_rows} == set(range(1, 101))


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        ("\t0.595796", ""),
        ("\t0.595796", "\t0.595796\t0.1"),
        ("\t0.595796", "\tnan"),
    ],
)
def test_parser_rejects_compensator_width_and_nonfinite_values(
    tmp_path: Path, replacement: str, reason: str
) -> None:
    source = FIXTURES / "real_sample_per_cmpdlz_s17_ntr100_fre100.txt"
    per = tmp_path / "per.tsv"
    per.write_text(
        source.read_text(encoding="utf-8").replace(replacement, reason, 1),
        encoding="utf-8",
    )
    mc = FIXTURES / "real_sample_mc_cmpdlz_s17_ntr100_fre100.txt"

    result = parse_codev_tor_exports(per, mc)

    assert "parse failed" in result.reason


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
    with pytest.raises(CodeVBatchError, match="fresh export"):
        run_codev_tor(source_zmx=REAL_ZMX, work_dir=tmp_path / "tor", runner=fake, tolerance_table=TorToleranceTable(("DLT S1 0.01",), "expert"), compensators=TorCompensators(("CMP DLZ SI",), "expert", "assembly"), monte_carlo=TorMonteCarlo(20), metric="mtf", mtf_frequency_lp_per_mm=100)


def test_tor_runner_deletes_stale_exports_before_rc1_run(tmp_path: Path) -> None:
    work = tmp_path / "tor"
    work.mkdir()
    (work / "atelier_tor_per.tsv").write_bytes(REAL_PER.read_bytes())
    (work / "atelier_tor_mc.tsv").write_bytes(REAL_MC.read_bytes())
    with pytest.raises(CodeVBatchError, match="fresh export"):
        run_codev_tor(source_zmx=REAL_ZMX, work_dir=work, runner=lambda *a, **k: type("P", (), {"returncode": 1, "stderr": ""})(), tolerance_table=TorToleranceTable(("DLT S1 0.01",), "expert"), compensators=TorCompensators(("CMP DLZ SI",), "expert", "assembly"), monte_carlo=TorMonteCarlo(20), metric="mtf", mtf_frequency_lp_per_mm=100)
    assert not (work / "atelier_tor_per.tsv").exists()


def test_default_tor_runner_uses_shared_process_discipline(monkeypatch, tmp_path: Path) -> None:
    import app.core.engines.codev_tolerance as module
    called = {}
    def shared(command, **kwargs):
        called.update(kwargs)
        return type("P", (), {"returncode": 1})(), "out", "err", 0.1
    monkeypatch.setattr(module, "run_codev_process", shared)
    result = module._default_tor_runner(["codev"], cwd=tmp_path, timeout=3)
    assert result.returncode == 1
    assert called["timeout_seconds"] == 3


def test_tor_runner_rc2_errors(tmp_path: Path) -> None:
    with pytest.raises(CodeVBatchError):
        run_codev_tor(source_zmx=REAL_ZMX, work_dir=tmp_path / "tor", runner=lambda *a, **k: type("P", (), {"returncode": 2, "stderr": "bad"})(), tolerance_table=TorToleranceTable(("DLT S1 0.01",), "expert"), compensators=TorCompensators(("CMP DLZ SI",), "expert", "assembly"), monte_carlo=TorMonteCarlo(20), metric="mtf", mtf_frequency_lp_per_mm=100)


def test_tor_yield_default_off_and_ratified_math() -> None:
    parsed = parse_codev_tor_exports(REAL_PER, REAL_MC)
    assert compute_mc_yield(parsed, UNRATIFIED_TOR_YIELD_POLICY).status == "unavailable"
    measured = compute_mc_yield(parsed, TorYieldPolicy("MTF", 0.1, "min", True, "Tolerancing.pdf + probe", 1.0))
    assert measured.status == "measured"
    assert measured.trials == 20
    assert measured.yield_fraction == pytest.approx(0.0)
    assert measured.per_field_yield["z1:f1"] == pytest.approx(0.9)
    assert measured.saturation_fraction == pytest.approx(58 / 60)


def test_saturation_is_policy_independent_and_gates_ratified_yield() -> None:
    parsed = parse_codev_tor_exports(REAL_PER, REAL_MC)
    saturated = replace(parsed, monte_carlo_rows=tuple(replace(row, value=1.0) for row in parsed.monte_carlo_rows))
    assert mc_saturation_fraction(saturated) == 1.0
    blocked = compute_mc_yield(saturated, TorYieldPolicy("MTF", 0.1, "min", True, "pinned", 0.5))
    assert blocked.status == "unavailable"
    assert "1" in blocked.reason and "0.5" in blocked.reason
    measured = compute_mc_yield(saturated, TorYieldPolicy("MTF", 0.1, "min", True, "pinned", 1.0))
    assert measured.status == "measured"


@pytest.mark.parametrize("mutation, reason", [
    (lambda rows: rows + (rows[0],), "duplicate"),
    (lambda rows: tuple(row for row in rows if not (row.sample == 1 and row.field == 1)), "coverage"),
    (lambda rows: (replace(rows[0], criterion="RMS"), *rows[1:]), "criterion"),
])
def test_yield_fail_closed_branches(mutation, reason: str) -> None:
    parsed = parse_codev_tor_exports(REAL_PER, REAL_MC)
    changed = replace(parsed, monte_carlo_rows=tuple(mutation(parsed.monte_carlo_rows)))
    result = compute_mc_yield(changed, TorYieldPolicy("MTF", 0.1, "min", True, "pinned", 1.0))
    assert result.status == "unavailable"
    assert reason in result.reason
