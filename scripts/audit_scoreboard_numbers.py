"""Recompute every headline number in a north-star scoreboard and diff it against the page.

Why this is a script and **not** a test: it needs a real-machine run directory, which
lives outside the repo. A test would have to carry `skipif(run_dir.exists())`, and a
test that disarms itself when its subject is absent stays silent on the one run that
needed it -- this repo has already paid for that once.

Why it exists at all: typing a number into a markdown table is not measuring it. On its
first use (2026-08-04) it emitted `[FAIL] distinct specs: recomputed=36 page_claims=31`
and exited 1, which is how the page's 「N 的需求 spec 数」 was found to be an **M**-side
count. Precise credit, because the loose version of this story is itself a flattering
claim: the script did not know the right answer was 37 -- its own spec key differed from
the page's, and the disagreement is what surfaced the defect. After aligning the key, the
N-side count is 37 and the M-side count is 31, and both are now checked separately.

Known limits, stated because a checker that oversells itself is worse than none:

* Every expected value is a hard-coded literal for ONE run. Point it at a different run
  and the numbers are meaningless -- it is a golden file, not a general validator.
* It covers the P1/P2/autovig/P4 headline figures only (see the count it prints). The
  tolerance-robustness table, the dose-response table, and single numbers quoted in prose
  are **not** covered.
* `--p4` is required rather than optional, so a run that silently skips 8 of the checks
  cannot still print a success line.

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
    """The four 交付物 pieces -- delegated, never re-implemented.

    An earlier version of this function restated the rule by hand and dropped two of
    production's conditions (`Path(candidate_zmx).is_file()` and `math.isfinite(ratio)`).
    Measured: with the run's `optimize/` subtree deleted it still reported 50 complete
    while production reported 0, and with one `ratio = inf` it reported 50 against
    production's 49. **A checker looser than the thing it checks is not a checker**, so
    it now calls the production predicate itself and can only ever agree with it.
    """

    from scripts.p2_crosssource_trial import _deliverable_pieces

    return all(_deliverable_pieces(record).values())


def _spec_key(record: dict) -> tuple:
    plan = record["plan"]
    return (
        round(plan["spec_efl_mm"], 6),
        round(plan["spec_f_number"], 4),
        round(plan["spec_fov_deg"], 4),
        round(plan["spec_imh_mm"], 6),
    )


def audit(page_path: Path, run_dir: Path, p4_path: Path) -> list[tuple]:
    from app.core.engines.prescription_identity import fingerprint_zmx

    page = page_path.read_text(encoding="utf-8")
    rows = [json.loads(Path(p).read_text(encoding="utf-8"))
            for p in sorted(glob.glob(str(run_dir / "trial_*.json")))]
    if not rows:
        raise SystemExit(f"no trial_*.json under {run_dir}")

    fails: list[tuple] = []
    checked = 0

    def check(label: str, actual, claimed, anchor: str) -> None:
        """`anchor` must appear on the same line as `claimed` in the page.

        A bare `str(claimed) in page` is a vacuous test and was one: "1" occurs 82 times
        in this page and "3" 56 times, so deleting the whole P2 block still left every
        P2 number "present". Requiring an anchor on the same line makes the presence half
        mean something -- delete the row and the check fails.
        """

        nonlocal checked
        checked += 1
        present = any(str(claimed) in line and anchor in line for line in page.splitlines())
        equal = str(actual) == str(claimed)
        ok = present and equal
        if not ok:
            fails.append((label, actual, claimed, present))
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: recomputed={actual} "
              f"page={claimed} on_a_line_with({anchor!r})={present}")

    elapsed = [r.get("elapsed_s") or 0 for r in rows]
    total = sum(elapsed)
    complete = [r for r in rows if _pieces_ok(r)]
    on_spec = [r for r in complete if not r.get("blocked_at")]
    informative = [r for r in on_spec
                   if ((r.get("tolerance") or {}).get("candidate") or {}).get("yield_is_informative")]

    print("=== P1 ===")
    check("N trials", len(rows), 59, "一次运行覆盖的独立需求")
    check("T seconds", round(total), 1888, "总耗时")
    check("T minutes", round(total / 60, 1), 31.5, "总耗时")
    check("median trial s", st.median(elapsed), 24.9, "总耗时")
    check("all_four", len(complete), 50, "完整四件套交付物")
    check("on_spec_four", len(on_spec), 49, "完整四件套交付物")
    check("distinct candidate designs",
          len({fingerprint_zmx(Path(str(r["candidate_zmx"])))
               for r in rows if r.get("candidate_zmx") and Path(str(r["candidate_zmx"])).is_file()}),
          30, "完整四件套交付物")
    check("informative four", len(informative), 45, "良率**有意义**")
    check("distinct control designs",
          len({fingerprint_zmx(ZMX_DIR / r["plan"]["control_zmx"]) for r in rows}), 37,
          "一次运行覆盖的独立需求")
    # Two populations, two numbers. Reporting one next to the other's label is the defect
    # that made this script exit 1 the first time it ran.
    check("distinct specs (all N)", len({_spec_key(r) for r in rows}), 37,
          "一次运行覆盖的独立需求")
    check("distinct specs (M rows)", len({_spec_key(r) for r in complete}), 31,
          "完整四件套交付物")

    print("\n=== P2 ===")
    judged = [r for r in rows if r["verdict"] in ("par", "worse")]
    check("judged", len(judged), 48, "judged 48")
    check("par", sum(1 for r in rows if r["verdict"] == "par"), 1, "par 1")
    for metric, claimed, anchor in (("rms_spot_um", 45, "rms_spot_um"),
                                    ("mtf_min", 44, "mtf_min"),
                                    ("distortion_pct", 1, "distortion_pct")):
        check(f"{metric} par",
              sum(1 for r in judged
                  if ((r.get("metrics") or {}).get(metric) or {}).get("verdict") == "par"),
              claimed, anchor)
    check("judged control designs",
          len({fingerprint_zmx(ZMX_DIR / r["plan"]["control_zmx"]) for r in judged}), 29,
          "judged 48")

    print("\n=== P1 autovig tail ===")
    clipped = [r.get("elapsed_s") or 0 for r in rows
               if r.get("autovig_edge_used") is not None and float(r["autovig_edge_used"]) > 0]
    check("autovig>0 trials", len(clipped), 3, "裁瞳梯级真的跑了")
    check("autovig>0 seconds", round(sum(clipped), 1), 413.3, "裁瞳梯级真的跑了")
    check("autovig>0 share %", round(100 * sum(clipped) / total, 1), 21.9, "裁瞳梯级真的跑了")

    # Required, not optional: an earlier version skipped this whole block when --p4 was
    # omitted and still printed a success line, so 20 checks and 28 checks looked alike.
    print("\n=== P4 ===")
    reported = json.loads(p4_path.read_text(encoding="utf-8"))[
        "reproduction_ratio_optiland_over_codev"]["reported"]
    for metric, n, median in (("efl_mm", 109, 0.9996), ("distortion_pct", 81, 1.0005),
                              ("max_rms_spot_um", 73, 1.5887), ("mtf_min", 73, 0.7695)):
        check(f"P4 {metric} n", reported[metric]["n"], n, metric)
        check(f"P4 {metric} median", reported[metric]["median"], median, metric)

    print(f"\n{checked} checks executed")
    return fails


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    # Required: see the P4 block. Optional was how 8 checks could vanish silently.
    parser.add_argument("--p4", type=Path, required=True)
    args = parser.parse_args(argv)

    fails = audit(args.page, args.run, args.p4)
    print("\n" + "=" * 60)
    if fails:
        print(f"{len(fails)} MISMATCH(ES):")
        for row in fails:
            print("  ", row)
        return 1
    print("all checked scoreboard numbers reproduce from the artifacts "
          "(P1/P2/autovig/P4 headline figures only -- see docstring for what is NOT covered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
