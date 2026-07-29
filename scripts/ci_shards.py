"""Split the pytest suite into balanced shards for parallel CI jobs.

Why shard at all
----------------
CI is one serial ``pytest`` job taking ~57 minutes, and ``pytest -n`` has been
measured as a *negative* optimisation three times (``ci.yml`` records ~35 min
serial vs 37m38 at ``-n 4`` and 40m30 at ``-n 2``; the runner has ``nproc=2``
and every worker re-imports Optiland/scipy/numpy). Separate runner VMs do not
share either root cause.

Why node-id granularity rather than by file
-------------------------------------------
Measured locally (2026-07-29, full suite, ``--durations=0``), a single file is
over half the wall clock::

    tests/test_patent_to_zmx.py           854.5s   52.0%
    tests/test_acceptance_task_export.py  347.1s   21.1%
    tests/test_optical_match.py           251.8s   15.3%
    tests/test_eval_golden_seeds.py        49.9s    3.0%   <- 1328 tests!

Sharding by file therefore cannot go below 52%, and sharding by *test count*
would be actively wrong: ``test_eval_golden_seeds.py`` holds 1328 of 4329 tests
and 3% of the time.

The safety property
-------------------
A shard split that silently drops tests reads as a *faster green*, which is this
project's recurring failure mode in a new place. So the partition is checked
before anything runs: the union of the shards must equal the full collected
node-id list exactly, and shards must be pairwise disjoint. The full list is
collected at CI time (``--collect-only``), never assumed from the durations
file, so a newly added test is assigned rather than skipped.

Durations are a *hint* only. Unknown tests get ``DEFAULT_WEIGHT`` and still land
in a shard; a stale durations file costs balance, never coverage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DURATIONS = ROOT / "tests" / "ci-shard-durations.json"

#: Seconds assumed for a test with no recorded duration. Most unknowns are tests
#: pytest omitted from --durations because they ran under its 0.005s reporting
#: threshold, so this is small on purpose; a genuinely new slow test costs
#: balance for one run and is picked up the next time durations are refreshed.
#: Coverage never depends on it -- the union check does.
DEFAULT_WEIGHT = 0.05


def collect_node_ids(pytest_args: list[str] | None = None) -> list[str]:
    """The authoritative list: what pytest would actually run, right now."""

    cmd = [
        sys.executable, "-m", "pytest", "--collect-only", "-q",
        "-m", "not real_machine", *(pytest_args or []),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    node_ids = [
        line.strip()
        for line in proc.stdout.splitlines()
        if "::" in line and not line.startswith(("<", " "))
    ]
    if not node_ids:
        raise SystemExit(
            f"collect-only produced no node ids (rc={proc.returncode})\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    return node_ids


def load_durations() -> dict[str, float]:
    if not DURATIONS.is_file():
        return {}
    return json.loads(DURATIONS.read_text(encoding="utf-8"))


def partition(node_ids: list[str], shards: int, durations: dict[str, float]) -> list[list[str]]:
    """Greedy longest-processing-time bin packing.

    Sorted by descending weight so the few very expensive tests are placed
    first; LPT is within 4/3 of optimal, which is far tighter than the spread
    between the slowest test and the rest.
    """

    if shards < 1:
        raise ValueError("shards must be >= 1")
    weighted = sorted(
        ((durations.get(n, DEFAULT_WEIGHT), n) for n in node_ids),
        key=lambda pair: (-pair[0], pair[1]),
    )
    buckets: list[list[str]] = [[] for _ in range(shards)]
    totals = [0.0] * shards
    for weight, node in weighted:
        i = min(range(shards), key=lambda k: totals[k])
        buckets[i].append(node)
        totals[i] += weight
    return buckets


def verify(node_ids: list[str], buckets: list[list[str]]) -> None:
    """Refuse to run unless the partition provably covers everything.

    This runs *before* the tests, because the failure it guards against -- tests
    quietly vanishing -- looks exactly like success.
    """

    full = set(node_ids)
    if len(full) != len(node_ids):
        dupes = len(node_ids) - len(full)
        raise SystemExit(f"collection contains {dupes} duplicate node ids; refusing to shard")
    union: set[str] = set()
    for i, bucket in enumerate(buckets):
        overlap = union & set(bucket)
        if overlap:
            raise SystemExit(f"shard {i} overlaps an earlier shard on {len(overlap)} tests")
        union |= set(bucket)
    missing = full - union
    extra = union - full
    if missing or extra:
        raise SystemExit(
            f"shard union != collected tests (missing {len(missing)}, unexpected {len(extra)})"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shards", type=int, required=True)
    parser.add_argument("--index", type=int, help="1-based shard to print (omit to only verify)")
    parser.add_argument("--out", type=Path, help="write the shard's node ids here")
    args = parser.parse_args(argv)

    node_ids = collect_node_ids()
    buckets = partition(node_ids, args.shards, load_durations())
    verify(node_ids, buckets)

    durations = load_durations()
    totals = [sum(durations.get(n, DEFAULT_WEIGHT) for n in b) for b in buckets]
    for i, (bucket, total) in enumerate(zip(buckets, totals, strict=True), start=1):
        marker = " <-" if args.index == i else ""
        print(f"shard {i}/{args.shards}: {len(bucket):5d} tests, ~{total:7.1f}s{marker}",
              file=sys.stderr)
    print(
        f"partition verified: {len(node_ids)} tests, "
        f"spread {min(totals):.0f}s..{max(totals):.0f}s",
        file=sys.stderr,
    )

    if args.index is not None:
        if not 1 <= args.index <= args.shards:
            raise SystemExit(f"--index must be in 1..{args.shards}")
        chosen = buckets[args.index - 1]
        # The shard file is consumed one line per argument by xargs -d newline,
        # so a node id containing a newline would split into two bogus
        # arguments. Quotes, backslashes and spaces are fine there (taken
        # literally) and are common in parametrised ids; a newline is not.
        embedded = [n for n in chosen if "\n" in n or "\r" in n]
        if embedded:
            raise SystemExit(f"{len(embedded)} node id(s) contain a newline; cannot shard safely")
        if args.out:
            args.out.write_text("\n".join(chosen) + "\n", encoding="utf-8")
        else:
            print("\n".join(chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
