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
    for name in ("one.zmx", "two.zmx"):
        path = tmp_path / name
        path.write_bytes(source.read_bytes())
        candidates.append(path)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"tolerance_commands": ["DLT S1 0.01"], "tolerance_provenance": "expert", "compensator_commands": ["CMP DLZ SI"], "compensator_provenance": "expert", "assembly_assumptions": "assembled", "trials": 20, "metric": "mtf", "mtf_frequency_lp_per_mm": 100}), encoding="utf-8")
    return candidates, cfg


def test_plan_and_dry_run_statuses(tmp_path: Path):
    candidates, cfg = _inputs(tmp_path)
    assert {r["status"] for r in plan(candidates, tmp_path / "plan.tsv")} == {"not-run"}
    rows = run_matrix(candidates, tmp_path / "run.tsv", tmp_path / "evidence", cfg, run_codev=False)
    assert {r["status"] for r in rows} == {"built-not-run"}


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
    assert all((tmp_path / "evidence" / r["candidate"] / r["variant"] / "parse.json").is_file() for r in rows)
