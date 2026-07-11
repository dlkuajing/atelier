"""Build the Phase 16 Stage C offline plan; never invokes CODE V.

The manifest contains native plus two explicit IMH targets for at least eight
eligible seeds.  Machine outputs remain absent and blocked by construction.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.engines.stagec_field import reconstruct_image_fields  # noqa: E402

INDEX_PATH = ROOT / "app" / "data" / "optical_cases" / "index.json"
ZMX_DIR = ROOT / "data" / "zmx"


def build_manifest(*, output_dir: Path, seed_count: int = 8) -> dict[str, object]:
    """Construct temporary artifacts and a blocked real-machine execution plan."""

    if seed_count < 8:
        raise ValueError("Stage C matrix requires at least eight seeds")
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    cells: list[dict[str, object]] = []
    selected: list[str] = []
    artifacts = output_dir / "temporary-zmx"
    for record in records:
        source_name = record.get("source_zmx")
        native_imh = record.get("image_height_mm")
        if not isinstance(source_name, str) or not isinstance(native_imh, (int, float)):
            continue
        source = ZMX_DIR / source_name
        if not source.is_file() or native_imh <= 0:
            continue
        trial: list[tuple[str, float]] = [
            ("native", float(native_imh)),
            ("target-low", float(native_imh) * 0.9),
            ("target-high", float(native_imh) * 1.1),
        ]
        seed_cells: list[dict[str, object]] = []
        eligible = True
        for label, target_imh in trial:
            output = artifacts / f"{record['case_id']}--{label}.zmx"
            result = reconstruct_image_fields(
                source_zmx=source,
                output_zmx=output,
                target_image_height_mm=target_imh,
            )
            if result.status != "constructed":
                eligible = False
                break
            seed_cells.append(
                {
                    "cell_id": f"{record['case_id']}--{label}",
                    "case_id": record["case_id"],
                    "arm": label,
                    "target_image_height_mm": target_imh,
                    "derived_fov_deg": (
                        2 * math.degrees(math.atan(target_imh / float(record["efl_mm"])))
                    ),
                    "field_reconstruction": result.model_dump(mode="json"),
                    "machine_execution_status": "blocked",
                    "machine_execution_reason": (
                        "CODE V window not assigned; ANG-to-IMG macro syntax, RSI and real "
                        "chief-ray verification remain pending"
                    ),
                    "machine_result": None,
                    "expert_verdict": None,
                }
            )
        if not eligible:
            for cell in seed_cells:
                artifact = cell["field_reconstruction"]["output_path"]  # type: ignore[index]
                if artifact:
                    Path(str(artifact)).unlink(missing_ok=True)
            continue
        cells.extend(seed_cells)
        selected.append(str(record["case_id"]))
        if len(selected) == seed_count:
            break
    if len(selected) < seed_count:
        raise RuntimeError(f"only {len(selected)} eligible zero-vignetting FTYP0 seeds found")
    return {
        "schema": "atelier-p16-stagec-offline-plan-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "execution_scope": "offline-only",
        "codev_invoked": False,
        "seed_count": len(selected),
        "arms_per_seed": ["native", "target-low", "target-high"],
        "cell_count": len(cells),
        "selected_case_ids": selected,
        "cells": cells,
        "truth_notice": (
            "No real-machine result is present. FOV is derived-only. Production usability "
            "and [EXPERT] verdicts are intentionally absent."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed-count", type=int, default=8)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(output_dir=args.output_dir, seed_count=args.seed_count)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
