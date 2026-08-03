"""Commit the CODE V full-field readings the routing gate needs, keyed by ZMX.

`app/core/case_library.py` cannot read the per-field census: it is a runtime
product that lives outside the worktree (`D:/atelier-stagec-runs/...`), and a
machine without CODE V must still be able to route. `corpus_quality_distribution
.json` already set this precedent for the percentile ruler; this does the same for
the per-seed reading behind it.

The value is CODE V's max-over-fields RMS spot **diameter** in microns, admitted
only when the census row is error-free and **every declared field** produced a
positive reading -- the identical rule `p2_pair_census.codev_rms_by_zmx` applies,
imported rather than restated so the two cannot drift.

Rebuild:  uv run python scripts/build_seed_quality_artifact.py \
            --census D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl \
            --census D:/atelier-stagec-runs/trace-census-20260728/perfield-staging-census.jsonl
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.p2_pair_census import codev_rms_by_zmx  # noqa: E402

ARTIFACT_PATH = ROOT / "app" / "data" / "codev_seed_quality.json"
CASE_INDEX = ROOT / "app" / "data" / "optical_cases" / "index.json"
SCHEMA = "atelier.codev_seed_quality/v1"


def build(census_paths: list[Path]) -> dict:
    readings: dict[str, float] = {}
    provenance: list[dict] = []
    for path in census_paths:
        rows = codev_rms_by_zmx(path)
        collisions = sorted(set(rows) & set(readings))
        if collisions:
            raise SystemExit(
                f"{path.name} re-reads {len(collisions)} ZMX already covered "
                f"(e.g. {collisions[:3]}); merging would silently pick one"
            )
        readings.update(rows)
        provenance.append(
            {
                "census": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "rows_admitted": len(rows),
            }
        )

    index = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    wanted = {str(record["source_zmx"]) for record in index}
    # Only what the corpus actually contains. The censuses also cover staging
    # files that were never promoted; carrying them would be dead weight in a
    # committed artifact and would make its `n` mean something other than
    # "corpus rows we have a reading for".
    kept = {name: value for name, value in readings.items() if name in wanted}
    values = sorted(kept.values())
    by_batch: collections.Counter[str] = collections.Counter()
    for record in index:
        if str(record["source_zmx"]) in kept:
            by_batch[str(record.get("intake_batch") or "(none)")] += 1

    return {
        "schema": SCHEMA,
        "quantity": (
            "CODE V max-over-fields RMS spot size in um -- SPOTDATA output(1), a "
            "**diameter** (twice the root-mean-square spot radius), at zero defocus"
        ),
        "criterion": (
            "no CODE V error and every declared field produced a positive per-field "
            "SPOTDATA reading (n_positive == num_fields)"
        ),
        "keyed_by": "index.json source_zmx",
        "n": len(kept),
        "corpus_rows": len(index),
        "coverage_by_intake_batch": dict(sorted(by_batch.items())),
        "percentiles": {
            "p50": round(statistics.median(values), 4) if values else None,
            "min": values[0] if values else None,
            "max": values[-1] if values else None,
        },
        "provenance": provenance,
        "readings": dict(sorted(kept.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, default=ARTIFACT_PATH)
    args = parser.parse_args()

    payload = build(args.census)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out}: {payload['n']} of {payload['corpus_rows']} corpus rows")
    for batch, count in payload["coverage_by_intake_batch"].items():
        print(f"  {batch:<20}{count}")
    print(f"  p50 {payload['percentiles']['p50']} um  "
          f"min {payload['percentiles']['min']}  max {payload['percentiles']['max']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
