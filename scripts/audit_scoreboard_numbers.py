"""Recompute every headline number in a north-star scoreboard and diff it against the page.

Why this is a script and **not** a test: it needs a real-machine run directory, which
lives outside the repo. A test would have to carry `skipif(run_dir.exists())`, and a
test that disarms itself when its subject is absent stays silent on the one run that
needed it -- this repo has already paid for that once.

Why it exists at all: typing a number into a markdown table is not measuring it. On its
first use (2026-08-04) it caught a real defect in the page it was written to check --
「N 的需求 spec 数」was filled in as 31, which is the count covered by the **M** rows;
across all N rows it is 37. Putting an M-side denominator next to N is exactly the class
of error this repo makes most often, and no amount of re-reading the page finds it.

    uv run python scripts/audit_scoreboard_numbers.py \
        --page .planning/evidence/north-star-scoreboard-2026-08-04.md \
        --run D:/atelier-p1-runs/p3-fourpiece-20260804 \
        --p4 D:/atelier-p1-runs/p4-recheck-20260804.json

Exit 1 on any mismatch, so it can gate a docs commit.
"""

from __future__ import annotations

import argparse
import glob
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ZMX_DIR = ROOT / "data" / "zmx"


def _pieces_ok(record: dict) -> bool:
    """The four 交付物 pieces, by the same rule `_deliverable_pieces` uses."""

    metrics = record.get("metrics") or {}
    tolerance = (record.get("tolerance") or {}).get("candidate") or {}
    return (
        bool(record.get("candidate_zmx"))
        and all(
            (metrics.get(k) or {}).get("candidate") is not None
            for k in ("rms_spot_um", "mtf_min", "distortion_pct")
        )
        and isinstance((record.get("relative_cost_index") or {}).get("ratio"), (int, float))
        and isinstance(tolerance.get("yield_fraction"), (int, float))
    )


def _spec_key(record: dict) -> tuple:
    plan = record["plan"]
    return (
        round(plan["spec_efl_mm"], 6),
        round(plan["spec_f_number"], 4),
        round(plan["spec_fov_deg"], 4),
        round(plan["spec_imh_mm"], 6),
    )


def audit(page_path: Path, run_dir: Path, p4_path: Path | None) -> list[tuple]:
    from app.core.engines.prescription_identity import fingerprint_zmx

    page = page_path.read_text(encoding="utf-8")
    rows = [json.loads(Path(p).read_text(encoding="utf-8"))
            for p in sorted(glob.glob(str(run_dir / "trial_*.json")))]
    if not rows:
        raise SystemExit(f"no trial_*.json under {run_dir}")

    fails: list[tuple] = []

    def check(label: str, actual, claimed) -> None:
        # Two separate questions, and both must hold: does the page contain this number
        # at all, and does the number we recomputed equal it. A page that simply omits
        # the figure must not pass.
        present = str(claimed) in page
        equal = str(actual) == str(claimed)
        ok = present and equal
        if not ok:
            fails.append((label, actual, claimed, present))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: recomputed={actual} "
              f"page={claimed} present={present}")

    elapsed = [r.get("elapsed_s") or 0 for r in rows]
    total = sum(elapsed)
    complete = [r for r in rows if _pieces_ok(r)]
    on_spec = [r for r in complete if not r.get("blocked_at")]
    informative = [r for r in on_spec
                   if ((r.get("tolerance") or {}).get("candidate") or {}).get("yield_is_informative")]

    print("=== P1 ===")
    check("N trials", len(rows), 59)
    check("T seconds", round(total), 1888)
    check("T minutes", round(total / 60, 1), 31.5)
    check("median trial s", st.median(elapsed), 24.9)
    check("all_four", len(complete), 50)
    check("on_spec_four", len(on_spec), 49)
    check("informative four", len(informative), 45)
    check("distinct control designs",
          len({fingerprint_zmx(ZMX_DIR / r["plan"]["control_zmx"]) for r in rows}), 37)
    check("distinct candidate designs",
          len({fingerprint_zmx(Path(str(r["candidate_zmx"])))
               for r in rows if r.get("candidate_zmx") and Path(str(r["candidate_zmx"])).is_file()}), 30)
    # Two populations, two numbers. Reporting one of them next to the other's label is
    # the defect this script caught the first time it ran.
    check("distinct specs (all N)", len({_spec_key(r) for r in rows}), 37)
    check("distinct specs (M rows)", len({_spec_key(r) for r in complete}), 31)

    print("\n=== P2 ===")
    judged = [r for r in rows if r["verdict"] in ("par", "worse")]
    check("judged", len(judged), 48)
    check("par", sum(1 for r in rows if r["verdict"] == "par"), 1)
    for metric, claimed in (("rms_spot_um", 45), ("mtf_min", 44), ("distortion_pct", 1)):
        check(f"{metric} par",
              sum(1 for r in judged if ((r.get("metrics") or {}).get(metric) or {}).get("verdict") == "par"),
              claimed)
    check("judged control designs",
          len({fingerprint_zmx(ZMX_DIR / r["plan"]["control_zmx"]) for r in judged}), 29)

    print("\n=== P1 autovig tail ===")
    clipped = [r.get("elapsed_s") or 0 for r in rows
               if r.get("autovig_edge_used") is not None and float(r["autovig_edge_used"]) > 0]
    check("autovig>0 trials", len(clipped), 3)
    check("autovig>0 seconds", round(sum(clipped), 1), 413.3)
    check("autovig>0 share %", round(100 * sum(clipped) / total, 1), 21.9)

    if p4_path and p4_path.is_file():
        print("\n=== P4 ===")
        reported = json.loads(p4_path.read_text(encoding="utf-8"))[
            "reproduction_ratio_optiland_over_codev"]["reported"]
        for metric, n, median in (("efl_mm", 109, 0.9996), ("distortion_pct", 81, 1.0005),
                                  ("max_rms_spot_um", 73, 1.5887), ("mtf_min", 73, 0.7695)):
            check(f"P4 {metric} n", reported[metric]["n"], n)
            check(f"P4 {metric} median", reported[metric]["median"], median)

    return fails


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--p4", type=Path, default=None)
    args = parser.parse_args(argv)

    fails = audit(args.page, args.run, args.p4)
    print("\n" + "=" * 60)
    if fails:
        print(f"{len(fails)} MISMATCH(ES):")
        for row in fails:
            print("  ", row)
        return 1
    print("all scoreboard headline numbers reproduce from the artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
