"""Measure the *healthy* inter-output gap of a CODE V run.

Why this exists
---------------
``scripts/p2_crosssource_trial.py::IDLE_TIMEOUT_SECONDS`` kills a CODE V rung
that has written nothing for N seconds. Its comment recorded the watchdog's
purpose but no measurement of how long a healthy run legitimately stays quiet,
and the batch records cannot supply one: every run that *completed* did so with
a gap below the bound by construction. That is censored evidence -- it can never
show a healthy gap longer than the current bound, which is exactly the number
the bound has to clear.

Breaking the censoring needs one thing: run with the watchdog **watching but not
killing** (``idle_timeout_seconds=None, observe_idle_gaps=True``) and record
every gap. That is what this does, by replaying rung ``.seq`` files that real
batches already produced -- both rungs the watchdog killed and rungs that
finished -- so the two populations are measured on the same machine with the
same sequences.

Usage::

    uv run python scripts/codev_idle_gap_bench.py \
        --rung D:/atelier-stagec-runs/idle-bench/trial_X/optimize/asphere/atelier_codev_target_A_vig0600.seq \
        --out D:/atelier-stagec-runs/idle-gap-bench --timeout 600

Red line ①: CODE V is single-instance. The bench proves zero live sessions
before and after, and every process still runs under the shared batch lock.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Finer than the 5s production poll: a healthy rung can finish in ~5s, so a 5s
#: poll would quantise its whole gap profile into a single bucket and answer
#: "at most 5s" no matter what the truth is.
BENCH_POLL_SECONDS = 0.5

BENCH_SCHEMA = "atelier-codev-idle-gap-bench-v1"


_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/][^\"']+")


def _replay_dir(rung_seq: Path, out_dir: Path, index: int) -> tuple[Path, Path]:
    """Copy one rung into a fresh directory with its absolute paths rewritten.

    A rung ``.seq`` hard-codes the absolute path of its source ZMX and of both
    ``BUF EXP`` targets. Replaying it in place would overwrite the very batch
    artifacts being used as evidence, so every absolute path is redirected into
    the replay directory.

    Rewriting is by **basename**, not by substring: the recorded paths are the
    ones that existed when the batch ran, and a run directory renamed since then
    (``p2-phase1-20260730`` -> ``...-VIGNETTE-CONTAMINATED``) no longer contains
    its own recorded prefix. A substring rewrite silently matches nothing there,
    and CODE V then answers ``ERROR - Unable to open file`` while the replay
    still reports "completed" -- a measurement of nothing. The post-condition
    below is the guard: after rewriting, no absolute path may point outside the
    replay directory.
    """

    source_dir = rung_seq.parent
    replay = out_dir / f"{index:02d}_{source_dir.parent.name}_{source_dir.name}_{rung_seq.stem}"
    replay.mkdir(parents=True, exist_ok=True)
    if (source_dir / "cvin").is_dir():
        shutil.copytree(source_dir / "cvin", replay / "cvin", dirs_exist_ok=True)

    def _redirect(match: re.Match[str]) -> str:
        original = PureWindowsPath(match.group(0))
        if original.parent.name.casefold() == "cvin":
            return str(replay / "cvin" / original.name)
        return str(replay / original.name)

    text = _ABSOLUTE_PATH.sub(_redirect, rung_seq.read_text(encoding="ascii"))
    stray = [
        found
        for found in _ABSOLUTE_PATH.findall(text)
        if not found.casefold().startswith(str(replay).casefold())
    ]
    if stray:
        raise RuntimeError(f"replay .seq still points outside the replay dir: {stray[:2]}")

    replay_seq = replay / rung_seq.name
    replay_seq.write_text(text, encoding="ascii")
    return replay, replay_seq


def _listing_facts(listing: Path) -> dict[str, Any]:
    if not listing.is_file():
        return {"listing_bytes": 0, "aut_cycles": 0, "reached_aut": False}
    text = listing.read_text(encoding="utf-8", errors="replace")
    return {
        "listing_bytes": listing.stat().st_size,
        # A healthy AUT prints one of these per optimisation cycle, so their
        # count says whether a quiet process was working or parked.
        "aut_cycles": len(re.findall(r"^ *CYCLE NUMBER", text, flags=re.MULTILINE)),
        "reached_aut": "Constraints added:" in text,
    }


def replay_rung(rung_seq: Path, *, out_dir: Path, index: int, timeout_seconds: float) -> dict[str, Any]:
    from app.core.engines.codev_batch import (
        CodeVBatchError,
        resolve_default_codev_executable,
        run_codev_process_bytes,
    )

    replay, replay_seq = _replay_dir(rung_seq, out_dir, index)
    command = [str(resolve_default_codev_executable()), "/B", replay_seq.name]
    record: dict[str, Any] = {
        "source_seq": str(rung_seq),
        "replay_dir": str(replay),
        "hard_timeout_seconds": timeout_seconds,
        "poll_seconds": BENCH_POLL_SECONDS,
    }
    started = time.monotonic()
    try:
        capture = run_codev_process_bytes(
            command,
            work_dir=replay,
            timeout_seconds=timeout_seconds,
            # Watch without killing. This is the whole point of the bench: the
            # bound under test must not be allowed to censor its own evidence.
            idle_timeout_seconds=None,
            observe_idle_gaps=True,
            idle_poll_seconds=BENCH_POLL_SECONDS,
        )
    except CodeVBatchError as exc:
        record["outcome"] = f"error:{exc.kind}"
        record["error"] = exc.message
        record["gaps_seconds"] = exc.details.get("idle_gaps_seconds")
        gaps = [float(gap) for gap in (record["gaps_seconds"] or [])]
        record["max_gap_seconds"] = max(gaps) if gaps else None
        record["duration_seconds"] = round(time.monotonic() - started, 2)
    else:
        record["outcome"] = "completed"
        record["returncode"] = capture.process.returncode
        record["gaps_seconds"] = [round(gap, 2) for gap in capture.idle_gaps]
        record["max_gap_seconds"] = (
            round(capture.max_idle_gap_seconds, 2)
            if capture.max_idle_gap_seconds is not None
            else None
        )
        record["duration_seconds"] = round(capture.duration_seconds, 2)

    record.update(_listing_facts(replay_seq.with_suffix(".lis")))
    record["exports_written"] = sorted(p.name for p in replay.glob("*.tsv"))
    # Fidelity check. A replay that quietly did something else is worse than no
    # measurement: it reports a number for work that never happened. The
    # original rung's listing is the reference -- a faithful replay reproduces
    # its size and cycle count closely.
    record["source_listing"] = _listing_facts(rung_seq.with_suffix(".lis"))
    record["replay_matches_source"] = (
        record["aut_cycles"] == record["source_listing"]["aut_cycles"]
        and record["reached_aut"] == record["source_listing"]["reached_aut"]
    )
    return record


def main() -> int:
    from scripts.p2_crosssource_trial import assert_no_codev_session, codev_sessions

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rung", action="append", required=True, type=Path,
                        help="rung .seq from a previous batch; repeatable")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=600.0,
                        help="hard bound per replay; must be far above the watchdog under test")
    args = parser.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    before = assert_no_codev_session("idle-gap-bench pre-run")
    print(f"红线① pre-run CODE V sessions: {len(before)}", flush=True)

    records: list[dict[str, Any]] = []
    for index, rung in enumerate(args.rung, start=1):
        print(f"[{index}/{len(args.rung)}] {rung}", flush=True)
        record = replay_rung(rung, out_dir=out_dir, index=index, timeout_seconds=args.timeout)
        records.append(record)
        print(
            f"    -> {record['outcome']} in {record['duration_seconds']}s"
            f" | max gap {record['max_gap_seconds']}s"
            f" | {record['aut_cycles']} AUT cycles"
            f" | listing {record['listing_bytes']}B",
            flush=True,
        )
        (out_dir / "bench.json").write_text(
            json.dumps({"schema": BENCH_SCHEMA, "runs": records}, indent=2), encoding="utf-8"
        )

    after = codev_sessions()
    print(f"红线① post-run CODE V sessions: {len(after)} {after}", flush=True)

    completed = [r for r in records if r["outcome"] == "completed" and r["max_gap_seconds"] is not None]
    if completed:
        worst = max(completed, key=lambda r: r["max_gap_seconds"])
        print()
        print("healthy (completed) runs:")
        for r in completed:
            print(f"  max gap {r['max_gap_seconds']:>7.2f}s  over {r['duration_seconds']:>7.2f}s"
                  f"  {Path(r['source_seq']).parent.parent.parent.name}/{Path(r['source_seq']).stem}")
        print(f"  worst healthy gap: {worst['max_gap_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
