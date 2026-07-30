"""Build the per-case CODE V full-field RMS spot artifact the routing gate reads.

Sibling of `corpus_quality_distribution.py`: same census, same instrument, same
quantity -- that one collapses the corpus to a distribution, this one keeps every
case's own number so the product can ask "how good is *this* seed" offline.

Why a separate file rather than a column in `app/data/optical_cases/index.json`:

* `index.json` is a bare JSON array with no envelope, so there is nowhere to record
  which census produced the number and what its sha256 was -- and a quality figure
  whose provenance is unstated is how the previous gate went wrong.
* `scripts/generate_cases.py` rewrites `index.json` wholesale from the Optiland
  pipeline. A CODE V-sourced column living there would be silently dropped (or worse,
  silently kept while going stale) on the next regeneration, on a machine that by
  design need not have CODE V at all.

Coverage is partial on purpose: 218 of 442 cases traced every declared field. The
other 224 get **no entry**, which callers must read as "unmeasured" and fail closed
on. Writing a fallback value here is exactly the failure this artifact exists to end.

Usage::

    uv run python scripts/corpus_routing_quality.py --build --census <perfield.jsonl>
    uv run python scripts/corpus_routing_quality.py --check --census <perfield.jsonl>
    uv run python scripts/corpus_routing_quality.py --case US-12436366-B2-e10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.corpus_quality import (  # noqa: E402
    CRITERION,
    INSTRUMENT,
    PER_CASE_PATH,
    PER_CASE_SCHEMA,
    QUANTITY,
    case_rms_spot_um,
    per_case_population,
)

CASE_INDEX = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"


def collect(census_path: Path, *, index_path: Path = CASE_INDEX) -> tuple[dict[str, float], dict]:
    """case_id -> max per-field CODE V RMS spot (um), for fully-traced cases only.

    The census is keyed by ZMX filename; the product is keyed by case id. Resolving
    that join **here**, at build time, is what lets the runtime read this file without
    the census, the ZMX pool, or CODE V.
    """

    index = json.loads(index_path.read_text(encoding="utf-8"))
    case_of_zmx = {record["source_zmx"]: record["case_id"] for record in index}

    rows = [
        json.loads(line)
        for line in census_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_case: dict[str, float] = {}
    excluded = {
        "errored_or_partial_coverage": 0,
        "no_positive_field": 0,
        "not_in_case_index": 0,
    }
    for row in rows:
        declared = row.get("num_fields")
        if row.get("error") is not None or not declared or row.get("n_positive") != declared:
            excluded["errored_or_partial_coverage"] += 1
            continue
        case_id = case_of_zmx.get(row["seed"])
        if case_id is None:
            excluded["not_in_case_index"] += 1
            continue
        spots = [field[1] * 1000.0 for field in row["fields"] if field[0] == 0]
        if not spots:
            excluded["no_positive_field"] += 1
            continue
        by_case[case_id] = max(spots)
    return by_case, {
        "census_rows": len(rows),
        "index_cases": len(index),
        "excluded": excluded,
    }


def build(census_path: Path, *, index_path: Path = CASE_INDEX) -> dict[str, Any]:
    by_case, stats = collect(census_path, index_path=index_path)
    return {
        "schema": PER_CASE_SCHEMA,
        "n": len(by_case),
        "pool": "app/data/optical_cases/index.json (442 cases)",
        "criterion": CRITERION,
        "quantity": QUANTITY,
        # Sorted so a rebuild that changes nothing produces an identical file, and a
        # rebuild that changes something produces a readable diff.
        "rms_spot_um_by_case_id": dict(sorted(by_case.items())),
        "provenance": {
            "census_run": census_path.parent.name,
            "census_file": census_path.name,
            "census_sha256": hashlib.sha256(census_path.read_bytes()).hexdigest(),
            "census_rows": stats["census_rows"],
            "index_cases": stats["index_cases"],
            "index_sha256": hashlib.sha256(index_path.read_bytes()).hexdigest(),
            "excluded": stats["excluded"],
            "instrument": INSTRUMENT,
        },
        "caveats": [
            "coverage is partial: a case absent from this map has no full-field CODE V "
            "reading, which means unmeasured -- never 'good enough'",
            "a present reading is not a sanity certificate: one case reads 8.3e20 um "
            "with every field 'traced'",
            "RMS spot only -- the census carries no per-field MTF or distortion, so the "
            "other two P2 criteria have no per-case number here",
            "keyed by case id against the index sha256 recorded above; regenerating the "
            "case library without rebuilding this file leaves the join stale",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build", action="store_true", help="write the artifact")
    mode.add_argument("--check", action="store_true", help="fail if the artifact is stale")
    mode.add_argument("--case", help="report one case's reading")
    parser.add_argument("--census", type=Path, help="perfield-census.jsonl")
    parser.add_argument("--out", type=Path, default=PER_CASE_PATH)
    args = parser.parse_args(argv)

    if args.case is not None:
        reading = case_rms_spot_um(args.case)
        population = per_case_population()
        if reading is None:
            print(f"{args.case}: no full-field reading (unmeasured -- gates must fail closed)")
            return 1
        print(f"{args.case}: {reading:g} um")
        print(f"  quantity  : {population['quantity']}")
        print(f"  criterion : {population['criterion']}")
        print(f"  census    : {population['census_run']} sha256={population['census_sha256'][:12]}")
        return 0

    if args.census is None:
        parser.error("--build and --check need --census")

    payload = build(args.census)
    if args.build:
        args.out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.out} (n={payload['n']} of {payload['provenance']['index_cases']})")
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
