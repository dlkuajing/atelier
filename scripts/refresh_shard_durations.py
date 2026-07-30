"""Refresh `tests/ci-shard-durations.json` from durations CI actually measured.

Why this exists: the committed durations were measured **locally** on 2026-07-29 with
`--durations=0`, before the `fov_deg` re-anchor. The re-anchor enlarged the routable
pool, which made the routing-heavy tests slower, and `ci.yml` records the consequence:
in one run shard 1 took 27 minutes and shard 4 took 20 while shards 2 and 3 were both
cut off at the 40-minute cap. The cap was raised to 60 to let work land, and the comment
there says plainly that refreshing this file is the actual fix.

Two reasons to harvest from CI rather than re-measure locally:

* CI is the target. The runner has `nproc=2`; this workstation does not, and it is
  usually also running a CODE V batch. A local number is the wrong number.
* It costs no extra CI cycle. Each shard already runs `--durations=25`, and per the
  partition module's own measurement the top 25 are the great majority of the wall
  clock, so harvesting them fixes the balance exactly where the mass is.

Durations are a hint only -- `ci_shards.partition` gives an unknown test
`DEFAULT_WEIGHT` and still assigns it, and the union/disjointness check runs before any
test does. So a partial refresh can cost balance and can never cost coverage.

Usage:
    uv run python scripts/refresh_shard_durations.py --run <github-run-id>
    uv run python scripts/refresh_shard_durations.py --run <id> --check
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DURATIONS = ROOT / "tests" / "ci-shard-durations.json"

#: pytest prints `12.34s call     tests/x.py::test_y`. Only `call` is taken: setup and
#: teardown are attributed separately and adding them would double-count the fixtures a
#: parametrised test shares.
_DURATION_LINE = re.compile(
    r"(?P<seconds>\d+\.\d+)s\s+call\s+(?P<node_id>tests/[^\s]+::[^\s]+)\s*$"
)


def parse_durations(log_text: str) -> dict[str, float]:
    """Extract {node_id: seconds} from a CI job log.

    Keeps the MAXIMUM when a node id appears more than once. A log can contain a retry
    or a re-run, and taking the last occurrence would let a warm, fast repeat overwrite
    the cold measurement the partition needs to plan for.
    """

    found: dict[str, float] = {}
    for line in log_text.splitlines():
        match = _DURATION_LINE.search(line.strip())
        if match is None:
            continue
        node_id = match.group("node_id")
        seconds = float(match.group("seconds"))
        if seconds > found.get(node_id, 0.0):
            found[node_id] = seconds
    return found


def _gh(args: list[str], timeout: int = 900) -> str:
    out = subprocess.run(
        ["gh", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {(out.stderr or '')[:300]}")
    return out.stdout or ""


def fetch_run_logs(run_id: str) -> str:
    """Concatenated logs of every COMPLETED job in a run.

    Per-job rather than `gh run view --log`, for two reasons that both matter here:
    `--log` refuses a run that is still in progress, and a run where one shard failed
    still has three shards of perfectly good measurements. Harvesting per job means a
    partially-finished or partially-red run still contributes.
    """

    jobs = json.loads(_gh(["run", "view", run_id, "--json", "jobs"], timeout=120)).get("jobs", [])
    chunks: list[str] = []
    skipped: list[str] = []
    for job in jobs:
        if job.get("status") != "completed":
            skipped.append(str(job.get("name")))
            continue
        job_id = job.get("databaseId")
        if job_id is None:
            continue
        try:
            chunks.append(_gh(["api", f"repos/{{owner}}/{{repo}}/actions/jobs/{job_id}/logs"]))
        except RuntimeError as exc:  # one unreadable job must not lose the others
            skipped.append(f"{job.get('name')} ({exc})")
    if skipped:
        print(f"skipped (not complete or unreadable): {skipped}", file=sys.stderr)
    return chr(10).join(chunks)


def merge(existing: dict[str, float], measured: dict[str, float]) -> tuple[dict[str, float], dict]:
    """Overlay measured durations on the existing map and report what moved.

    Never drops an existing entry that CI did not report: `--durations=25` reports only
    the slowest per shard, so absence from this harvest means "not measured this time",
    not "now fast". Dropping them would silently reset hundreds of tests to
    DEFAULT_WEIGHT and make the balance worse than the stale file it replaced.
    """

    merged = dict(existing)
    changed: list[dict[str, object]] = []
    for node_id, seconds in measured.items():
        before = existing.get(node_id)
        merged[node_id] = seconds
        if before is None or abs(before - seconds) > 0.5:
            changed.append({"node_id": node_id, "before": before, "after": seconds})
    changed.sort(key=lambda row: -(float(row["after"])))  # type: ignore[arg-type]
    return merged, {
        "measured": len(measured),
        "existing": len(existing),
        "merged": len(merged),
        "new": sum(1 for row in changed if row["before"] is None),
        "moved": sum(1 for row in changed if row["before"] is not None),
        "biggest_moves": changed[:15],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="GitHub Actions run id to harvest")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would change without writing",
    )
    parser.add_argument(
        "--base",
        type=Path,
        default=DURATIONS,
        help=(
            "durations to overlay onto. Separate from --out on purpose: when they were "
            "the same argument, writing to a different --out silently read that "
            "(nonexistent) file as the base and discarded every existing entry -- "
            "defeating the never-drop property this tool exists to preserve."
        ),
    )
    parser.add_argument("--out", type=Path, default=DURATIONS)
    args = parser.parse_args(argv)

    measured = parse_durations(fetch_run_logs(args.run))
    if not measured:
        print(
            f"no duration lines found in run {args.run} -- was it run without --durations?",
            file=sys.stderr,
        )
        return 1

    existing = json.loads(args.base.read_text(encoding="utf-8")) if args.base.is_file() else {}
    if not existing:
        print(
            f"base {args.base} is missing or empty -- refusing to write a durations file "
            "built from one harvest alone; that would reset every unmeasured test to "
            "DEFAULT_WEIGHT and make the balance worse than the stale file.",
            file=sys.stderr,
        )
        return 1
    merged, report = merge(existing, measured)

    print(f"measured {report['measured']}  existing {report['existing']}  merged {report['merged']}")
    print(f"  new {report['new']}   moved >0.5s {report['moved']}")
    for row in report["biggest_moves"]:  # type: ignore[union-attr]
        before = "new" if row["before"] is None else f"{float(row['before']):.1f}s"
        print(f"  {float(row['after']):8.1f}s  (was {before:>8})  {row['node_id']}")

    if args.check:
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(dict(sorted(merged.items())), indent=1) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
