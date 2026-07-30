"""Build the corpus RMS-spot reference distribution from the traceability census.

Why a rank rather than a floor: see `app/core/corpus_quality`. This script is the
builder and the auditor for the artifact that module reads.

The instrument is identical to the one P2 reports with, and that is the whole point of
reusing the census instead of re-measuring: the census's per-field value is
`SPOTDATA(1,f,1,0.01,'CEN',0,0,^spot)` -> `^spot(1)`, in mm, which is exactly
`@rmssum`'s per-field operand before its `*1000`. Same call, same array index, so the
percentile compares like with like. Verified by hand against `census.jsonl`, whose
`rms_spot_um` equals 1000x the largest per-field entry in `perfield-census.jsonl`.

Usage:
    uv run python scripts/corpus_quality_distribution.py --build --census <perfield.jsonl>
    uv run python scripts/corpus_quality_distribution.py --check --census <perfield.jsonl>
    uv run python scripts/corpus_quality_distribution.py --rank 97.97
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.corpus_quality import (  # noqa: E402
    DISTRIBUTION_PATH,
    DISTRIBUTION_SCHEMA,
    reference_population,
    rms_percentile,
)

CASE_INDEX = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"

#: Reported percentiles. Not a policy -- just the shape of the distribution, so a
#: reader can see the tail without loading every value.
_QUANTILES = (0.0, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 1.0)


def _quantile(sorted_values: list[float], q: float) -> float:
    k = (len(sorted_values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] * (hi - k) + sorted_values[hi] * (k - lo)


def collect(census_path: Path) -> tuple[list[float], dict[str, Any]]:
    """Per-case max RMS spot over fields, for cases that traced **every** field.

    The full-coverage screen is not decoration: `@rmssum` skips fields whose trace
    failed and returns the maximum over the survivors, so a partially-traced case
    reports a *smaller* number than it deserves. Admitting those would bias the
    reference population optimistic exactly where it matters.
    """

    rows = [
        json.loads(line)
        for line in census_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    values: list[float] = []
    excluded = {"errored_or_partial_coverage": 0, "no_positive_field": 0}
    for row in rows:
        declared = row.get("num_fields")
        if row.get("error") is not None or not declared or row.get("n_positive") != declared:
            excluded["errored_or_partial_coverage"] += 1
            continue
        spots = [field[1] * 1000.0 for field in row["fields"] if field[0] == 0]
        if not spots:
            excluded["no_positive_field"] += 1
            continue
        values.append(max(spots))
    values.sort()
    return values, {"census_rows": len(rows), "excluded": excluded}


def build(census_path: Path) -> dict[str, Any]:
    values, stats = collect(census_path)
    digest = hashlib.sha256(census_path.read_bytes()).hexdigest()
    return {
        "schema": DISTRIBUTION_SCHEMA,
        "n": len(values),
        "pool": "data/zmx (442 committed case ZMX)",
        "criterion": (
            "no CODE V error and every declared field produced a positive per-field "
            "SPOTDATA reading (n_positive == num_fields)"
        ),
        "quantity": (
            "max over fields of CODE V's RMS spot size, in um -- a diameter, not a radius"
        ),
        "percentiles": {f"p{int(q * 100)}": _quantile(values, q) for q in _QUANTILES},
        "sorted_rms_spot_um": values,
        "provenance": {
            "census_run": census_path.parent.name,
            "census_file": census_path.name,
            "census_sha256": digest,
            "census_rows": stats["census_rows"],
            "excluded": stats["excluded"],
            "instrument": (
                "SPOTDATA(1,f,1,0.01,'CEN',0,0,^spot) -> ^spot(1) in mm, x1000 -- "
                "identical to @rmssum's per-field operand"
            ),
        },
        "caveats": [
            # Every one of these was measured while building the artifact, and each
            # would otherwise be read into the number by a reader who assumed better.
            "heavy-tailed: p50 and p90 differ by roughly 40x, and the maximum is not "
            "a physically meaningful spot size -- use the rank, never the raw spread",
            "this pool is the traceable subset of data/zmx, NOT the P2-eligible control "
            "population (which is additionally fidelity-clean and inside the product's "
            "own parameter bounds); it is a broader and more forgiving reference",
            "full field coverage does not imply physical sanity: one case reads 8.3e20 um "
            "with every field 'traced', and its stored image_height_mm is 5.9e17 mm",
            "RMS spot only: the census carries no MTF or distortion per field, so no "
            "percentile is offered for the other two P2 criteria",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true", help="write the artifact")
    mode.add_argument("--check", action="store_true", help="fail if the artifact is stale")
    mode.add_argument("--rank", type=float, help="report where one RMS spot value sits")
    parser.add_argument("--census", type=Path, help="perfield-census.jsonl")
    parser.add_argument("--out", type=Path, default=DISTRIBUTION_PATH)
    args = parser.parse_args(argv)

    if args.rank is not None:
        pct = rms_percentile(args.rank)
        population = reference_population()
        if pct is None:
            print(f"{args.rank} is not a usable reading (non-positive or non-finite)")
            return 1
        print(f"{args.rank:g} um -> p{pct:.1f} of n={population['n']}")
        print(f"  pool      : {population['pool']}")
        print(f"  criterion : {population['criterion']}")
        print(f"  census    : {population['census_run']}")
        for caveat in population["caveats"]:
            print(f"  caveat    : {caveat}")
        return 0

    if args.census is None:
        parser.error("--build and --check need --census")

    payload = build(args.census)
    if args.build:
        args.out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.out} (n={payload['n']})")
        for name, value in payload["percentiles"].items():
            print(f"  {name:>5} = {value:.4g} um")
        return 0

    current = json.loads(args.out.read_text(encoding="utf-8"))
    if current == payload:
        print(f"{args.out} matches the census (n={payload['n']})")
        return 0
    print(f"{args.out} is STALE against {args.census}", file=sys.stderr)
    for key in sorted(set(current) | set(payload)):
        if current.get(key) != payload.get(key):
            print(f"  differs: {key}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
