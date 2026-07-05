"""Precompute offline demo analysis bundles under data/demo_cache/.

Run:
    python scripts/precompute_demo_cache.py 3P_F2.5_FOV78.0_EFL2.7_IMH2.3_TTL3.56
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.demo_cache import (  # noqa: E402
    DEFAULT_DEMO_CASE_IDS,
    DEMO_CACHE_DIR,
    build_demo_cache_bundle_for_case,
    write_demo_cache_bundle,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Precompute Atelier demo analysis cache bundles.",
    )
    parser.add_argument(
        "case_ids",
        nargs="*",
        help="Generated case ids, with or without .json/.zmx suffix.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEMO_CACHE_DIR,
        help=f"Output cache directory (default: {DEMO_CACHE_DIR}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    case_ids = tuple(args.case_ids) or DEFAULT_DEMO_CASE_IDS
    written: list[dict[str, str]] = []

    for case_id in case_ids:
        bundle = build_demo_cache_bundle_for_case(case_id)
        path = write_demo_cache_bundle(bundle, cache_dir=args.cache_dir)
        item = {
            "case_id": bundle.source_case_id,
            "cache_key": bundle.cache_key,
            "path": str(path),
        }
        written.append(item)
        if not args.json:
            print(f"OK {item['case_id']} -> {item['path']}", flush=True)

    if args.json:
        print(json.dumps({"written": written}, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
