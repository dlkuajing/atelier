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

from app.core.engines.stagec_field import (  # noqa: E402
    FieldTargetStatus,
    reconstruct_image_fields,
    resolve_field_target,
)
from app.core.lens_system import Scenario  # noqa: E402
from app.core.parameter_guards import (  # noqa: E402
    SCENARIO_BOUNDS,
    ParameterGuardError,
    validate_scenario_params,
)

INDEX_PATH = ROOT / "app" / "data" / "optical_cases" / "index.json"
ZMX_DIR = ROOT / "data" / "zmx"


def build_manifest(*, output_dir: Path, seed_count: int = 8) -> dict[str, object]:
    """Construct temporary artifacts and a blocked real-machine execution plan."""

    if seed_count < 8:
        raise ValueError("Stage C matrix requires at least eight seeds")
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    cells: list[dict[str, object]] = []
    blocked_seeds: list[dict[str, str]] = []
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
        try:
            scenario = Scenario(str(record["scenario"]))
            bounds = SCENARIO_BOUNDS[scenario]
            efl_mm = float(record["efl_mm"])
            fnum = float(record["fnum"])
            n_pieces = int(record["n_pieces"])
            imh_from_fov_min = efl_mm * math.tan(math.radians(bounds.fov_deg_min / 2))
            imh_from_fov_max = efl_mm * math.tan(math.radians(bounds.fov_deg_max / 2))
            lower = max(bounds.image_height_mm_min, imh_from_fov_min)
            upper = min(bounds.image_height_mm_max, imh_from_fov_max)
            native = float(native_imh)
            if not lower < native < upper:
                raise ValueError(
                    f"native IMH {native} lacks bidirectional in-bounds room [{lower}, {upper}]"
                )
            low = (lower + native) / 2
            high = (native + upper) / 2
        except (KeyError, TypeError, ValueError) as exc:
            blocked_seeds.append({"case_id": str(record.get("case_id")), "reason": str(exc)})
            continue
        trial: list[tuple[str, float]] = [
            ("native-imh-reconstructed-control", native),
            ("target-low", low),
            ("target-high", high),
        ]
        seed_cells: list[dict[str, object]] = []
        eligible = True
        for label, target_imh in trial:
            resolved = resolve_field_target(
                efl_mm=efl_mm, image_height_mm=target_imh, full_fov_deg=None
            )
            if resolved.status is not FieldTargetStatus.RESOLVED or resolved.full_fov_deg is None:
                eligible = False
                blocked_seeds.append(
                    {"case_id": str(record["case_id"]), "reason": f"{label}: resolver blocked"}
                )
                break
            try:
                validate_scenario_params(
                    scenario,
                    efl_mm=efl_mm,
                    f_number=fnum,
                    fov_deg=resolved.full_fov_deg,
                    image_height_mm=target_imh,
                    n_elements=n_pieces,
                )
            except ParameterGuardError as exc:
                eligible = False
                blocked_seeds.append(
                    {"case_id": str(record["case_id"]), "reason": f"{label}: {exc.violations}"}
                )
                break
            output = artifacts / f"{record['case_id']}--{label}.zmx"
            result = reconstruct_image_fields(
                source_zmx=source,
                output_zmx=output,
                resolved_target=resolved,
            )
            if result.status != "constructed":
                eligible = False
                blocked_seeds.append(
                    {
                        "case_id": str(record["case_id"]),
                        "reason": f"{label}: {result.status}: {result.reason}",
                    }
                )
                break
            seed_cells.append(
                {
                    "cell_id": f"{record['case_id']}--{label}",
                    "case_id": record["case_id"],
                    "scenario": scenario.value,
                    "arm": label,
                    "target_image_height_mm": target_imh,
                    "target_efl_mm": efl_mm,
                    "derived_fov_deg": resolved.full_fov_deg,
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
        "arms_per_seed": [
            "native-imh-reconstructed-control", "target-low", "target-high"
        ],
        "cell_count": len(cells),
        "selected_case_ids": selected,
        "blocked_seeds": blocked_seeds,
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
