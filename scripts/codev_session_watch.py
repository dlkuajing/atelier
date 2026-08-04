"""Continuous CODE V single-instance watch for the duration of a real-machine batch.

NORTH-STAR.md 红线① (v2.1) requires two things, and the batch runners only do the
first: prove zero sessions before the run, **and** monitor throughout, aborting and
marking the attempt contaminated the moment a second CODE V instance appears.
`p2_crosssource_trial.py` samples the count at `pre-run` and again in its `finally`,
which cannot see a second instance that comes and goes in between -- and a
transient second instance is exactly what corrupted P18 job-0020/0021.

Deliberately imports `p2_crosssource_trial.codev_sessions` rather than
re-deriving "what counts as a session" (a test pins the identity). Two rulers for one quantity is this
project's most expensive recurring defect (routing read an Optiland half-field
radius while the judge read a CODE V full-field diameter for weeks), and a watch
that disagrees with the runner about what it is watching is worse than no watch.

Emits one line per event on stdout, line-buffered, so it can drive a monitor:

    OK      <iso> sessions=<n>          (heartbeat, every --heartbeat samples)
    ALERT   <iso> sessions=<n> <pids>   (n > --max, i.e. the red line tripped)
    CLEAR   <iso> sessions=<n>          (back at or below --max after an ALERT)

Exit code 2 if the red line ever tripped, 0 otherwise, so a wrapper can fail the
batch on the watch alone.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.p2_crosssource_trial import codev_sessions  # noqa: E402


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between samples")
    parser.add_argument(
        "--max",
        type=int,
        default=1,
        dest="max_sessions",
        help=(
            "sessions allowed. 1 during a batch (the batch's own CODE V); 0 to assert "
            "an idle machine. The red line is about a *second* instance, not any instance."
        ),
    )
    parser.add_argument(
        "--heartbeat",
        type=int,
        default=60,
        help="emit an OK line every N samples so silence never reads as 'still fine'",
    )
    parser.add_argument("--duration", type=float, default=0.0, help="seconds to watch; 0 = forever")
    parser.add_argument(
        "--samples",
        type=int,
        default=0,
        help="stop after N samples; 0 = unbounded. Bounded runs are what make this testable.",
    )
    args = parser.parse_args(argv)

    started = time.time()
    tripped = False
    alerting = False
    sample = 0
    print(f"WATCH   {_now()} start interval={args.interval}s max={args.max_sessions}", flush=True)
    try:
        while True:
            sessions = codev_sessions()
            n = len(sessions)
            if n > args.max_sessions:
                tripped = True
                if not alerting:
                    pids = [s["pid"] for s in sessions]
                    print(f"ALERT   {_now()} sessions={n} pids={pids} RED LINE TRIPPED", flush=True)
                    alerting = True
            elif alerting:
                print(f"CLEAR   {_now()} sessions={n}", flush=True)
                alerting = False
            elif args.heartbeat and sample % args.heartbeat == 0:
                print(f"OK      {_now()} sessions={n}", flush=True)
            sample += 1
            if args.samples and sample >= args.samples:
                break
            if args.duration and time.time() - started >= args.duration:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    # Never say "clean" on the strength of the final sample alone: the whole point is
    # that a transient second instance is invisible to an endpoint check.
    verdict = "CONTAMINATED" if tripped else "clean"
    print(f"WATCH   {_now()} end samples={sample} verdict={verdict}", flush=True)
    return 2 if tripped else 0


if __name__ == "__main__":
    raise SystemExit(main())
