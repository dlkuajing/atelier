"""Mock-only tests for the P14 TOR matrix driver."""

import json
from pathlib import Path

from app.core.engines.codev_tolerance import CodeVTorRunResult, parse_codev_tor_exports
from scripts.p14_tor_matrix import plan, run_matrix

FIXTURES = Path(__file__).parent / "data" / "codev_tor"
PER = next(FIXTURES.glob("real_sample_per_*.txt"))
MC = next(FIXTURES.glob("real_sample_mc_*.txt"))


def _inputs(tmp_path: Path):
    candidates = []
    source = Path("data/zmx/US20170003482A1.zmx")
    for index in range(2):
        baseline = tmp_path / f"base{index}" / "same.zmx"
        optimized = tmp_path / f"opt{index}" / "same.zmx"
        baseline.parent.mkdir()
        optimized.parent.mkdir()
        baseline.write_bytes(source.read_bytes() + f"baseline-{index}".encode())
        optimized.write_bytes(source.read_bytes() + f"optimized-{index}".encode())
        candidates.append(f"{baseline}\t{optimized}")
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"tolerance_commands": ["DLT S1 0.01"], "tolerance_provenance": "expert", "compensator_commands": ["CMP DLZ SI"], "compensator_provenance": "expert", "assembly_assumptions": "assembled", "trials": 20, "metric": "mtf", "mtf_frequency_lp_per_mm": 100}), encoding="utf-8")
    return candidates, cfg


def test_plan_and_dry_run_statuses(tmp_path: Path):
    candidates, cfg = _inputs(tmp_path)
    assert {r["status"] for r in plan(candidates, tmp_path / "plan.tsv")} == {"not-run"}
    rows = run_matrix(candidates, tmp_path / "run.tsv", tmp_path / "evidence", cfg, run_codev=False)
    assert {r["status"] for r in rows} == {"built-not-run"}
    assert len({r["candidate"] for r in rows}) == 2
    for candidate in {r["candidate"] for r in rows}:
        baseline = tmp_path / "evidence" / candidate / "baseline-positive-control" / "candidate.zmx"
        optimized = tmp_path / "evidence" / candidate / "optimized" / "candidate.zmx"
        assert baseline.read_bytes() != optimized.read_bytes()


def test_run_with_fake_runner_keeps_yield_unavailable(tmp_path: Path):
    candidates, cfg = _inputs(tmp_path)
    def fake(**kwargs):
        work = Path(kwargs["work_dir"])
        per, mc = work / "atelier_tor_per.tsv", work / "atelier_tor_mc.tsv"
        per.write_bytes(PER.read_bytes())
        mc.write_bytes(MC.read_bytes())
        return CodeVTorRunResult(Path("fake.exe"), work / "atelier_tor.seq", per, mc, 1, 0.1, parse_codev_tor_exports(per, mc))
    rows = run_matrix(candidates, tmp_path / "run.tsv", tmp_path / "evidence", cfg, run_codev=True, tor_runner=fake)
    assert {r["status"] for r in rows} == {"ok"}
    assert {r["yield"] for r in rows} == {"unavailable"}
    assert {r["saturation"] for r in rows} == {str(58 / 60)}
    assert all((tmp_path / "evidence" / r["candidate"] / r["variant"] / "parse.json").is_file() for r in rows)


def test_run_requires_two_candidate_pairs(tmp_path: Path):
    candidates, cfg = _inputs(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="at least two"):
        run_matrix(candidates[:1], tmp_path / "run.tsv", tmp_path / "evidence", cfg, run_codev=False)


def test_failure_writes_structured_evidence(tmp_path: Path):
    candidates, cfg = _inputs(tmp_path)
    def fail(**kwargs):
        raise RuntimeError("deliberate failure detail")
    rows = run_matrix(candidates, tmp_path / "run.tsv", tmp_path / "evidence", cfg, run_codev=True, tor_runner=fail)
    assert all("deliberate failure detail" in row["status"] for row in rows)
    assert all((tmp_path / "evidence" / row["candidate"] / row["variant"] / "failure.json").is_file() for row in rows)
