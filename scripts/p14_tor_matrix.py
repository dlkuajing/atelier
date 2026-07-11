"""Plan and execute the P14 TOR matrix without conflating routing proxies."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.engines.codev_tolerance import (  # noqa: E402
    TorCompensators,
    TorMonteCarlo,
    TorToleranceTable,
    build_codev_tor_sequence,
    run_codev_tor,
)
from app.core.engines.tor_yield import (  # noqa: E402
    UNRATIFIED_TOR_YIELD_POLICY,
    compute_mc_yield,
)

HEADER_NOTE = (
    "[EXPERT] TOR/PER/MC semantics and threshold policy require expert ratification; "
    "routing proxy and true TOR are mutually incomparable."
)
FIELDS = ["candidate", "variant", "source_zmx", "status", "yield", "trials", "saturation", "per_field", "tor_section", "routing_proxy_section"]


def _rows(candidates: Sequence[Path]) -> list[dict[str, str]]:
    return [{"candidate": p.stem, "variant": variant, "source_zmx": str(p), "status": "not-run", "yield": "unavailable", "trials": "", "saturation": "", "per_field": "", "tor_section": "true TOR only", "routing_proxy_section": "routing proxy: separate/non-comparable"} for p in candidates for variant in ("baseline-positive-control", "optimized")]


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {HEADER_NOTE}\n")
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def plan(candidates: Sequence[Path], output: Path) -> list[dict[str, str]]:
    if len(candidates) < 2:
        raise ValueError("plan requires at least two candidate ZMX paths")
    rows = _rows(candidates)
    _write(output, rows)
    return rows


def _config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_matrix(candidates: Sequence[Path], output: Path, evidence_dir: Path, config_path: Path, *, run_codev: bool, tor_runner: Callable[..., Any] = run_codev_tor) -> list[dict[str, str]]:
    cfg = _config(config_path)
    table = TorToleranceTable(tuple(cfg["tolerance_commands"]), cfg["tolerance_provenance"])
    compensators = TorCompensators(tuple(cfg["compensator_commands"]), cfg["compensator_provenance"], cfg["assembly_assumptions"])
    mc = TorMonteCarlo(int(cfg["trials"]))
    rows = _rows(candidates)
    for row in rows:
        cell = evidence_dir / row["candidate"] / row["variant"]
        cell.mkdir(parents=True, exist_ok=True)
        staged = cell / "candidate.zmx"
        shutil.copy2(row["source_zmx"], staged)
        kwargs = dict(source_zmx=staged, work_dir=cell, tolerance_table=table, compensators=compensators, monte_carlo=mc, metric=cfg["metric"], mtf_frequency_lp_per_mm=cfg.get("mtf_frequency_lp_per_mm"))
        if not run_codev:
            (cell / "atelier_tor.seq").write_text(build_codev_tor_sequence(source_path=staged, performance_result_path=cell / "atelier_tor_per.tsv", monte_carlo_result_path=cell / "atelier_tor_mc.tsv", tolerance_table=table, compensators=compensators, monte_carlo=mc, metric=cfg["metric"], mtf_frequency_lp_per_mm=cfg.get("mtf_frequency_lp_per_mm")), encoding="ascii")
            row["status"] = "built-not-run"
            continue
        try:
            result = tor_runner(**kwargs)
            parsed = result.parse_result
            (cell / "parse.json").write_text(json.dumps({"status": parsed.status, "reason": parsed.reason, "declared_trials": parsed.declared_trials, "performance_rows": len(parsed.performance_rows), "monte_carlo_rows": len(parsed.monte_carlo_rows)}, indent=2), encoding="utf-8")
            derived = compute_mc_yield(parsed, UNRATIFIED_TOR_YIELD_POLICY)
            row.update({"status": "ok" if parsed.monte_carlo_rows else f"unavailable:{parsed.reason}", "yield": "unavailable", "trials": str(parsed.declared_trials or ""), "saturation": "unavailable" if derived.saturation_fraction is None else str(derived.saturation_fraction), "per_field": "unavailable" if not derived.per_field_yield else json.dumps(derived.per_field_yield, sort_keys=True)})
        except Exception as exc:  # CLI evidence collector must preserve all remaining cells.
            row["status"] = f"failed:run:{type(exc).__name__}"
    _write(output, rows)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        cmd = sub.add_parser(name)
        cmd.add_argument("candidates", nargs="+", type=Path)
        cmd.add_argument("--output", type=Path, required=True)
        cmd.add_argument("--config", type=Path)
        cmd.add_argument("--evidence-dir", type=Path)
        if name == "run":
            cmd.add_argument("--run-codev", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan(args.candidates, args.output)
    else:
        if args.config is None or args.evidence_dir is None:
            parser.error("run requires --config and --evidence-dir")
        run_matrix(args.candidates, args.output, args.evidence_dir, args.config, run_codev=args.run_codev)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
