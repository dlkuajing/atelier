"""Compute SCENARIO_BOUNDS statistics from the real ammo designs (phase v2-02).

Groups the manifest by scenario (FOV>=85 -> ultrawide, else wide) and prints
min/max/mean per parameter plus suggested bounds (min with -5% margin, max with
+5% margin) for hand-transcribing into parameter_guards.py. Uses the manifest
*nominal* values (design intent), not Optiland-recomputed values.

Run:  cd lumira-backend && uv run python scripts/compute_bounds_stats.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# backend root on path so `tests.data.zmx_manifest` imports from a plain script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.data.zmx_manifest import ZMX_AMMO  # noqa: E402


def _scenario(fov_deg: float) -> str:
    return "smartphone-ultrawide" if fov_deg >= 85 else "smartphone-wide"


def _stat(items: list[dict], key: str) -> tuple[float, float, float]:
    vals = [i[key] for i in items]
    return min(vals), max(vals), sum(vals) / len(vals)


def main() -> None:
    groups: dict[str, list[dict]] = {"smartphone-wide": [], "smartphone-ultrawide": []}
    for a in ZMX_AMMO:
        groups[_scenario(a["nominal_fov_deg"])].append(a)

    total = sum(len(v) for v in groups.values())
    print(f"=== SCENARIO_BOUNDS stats from {total} real ammo designs ===")
    for scen, items in groups.items():
        if not items:
            print(f"\n[{scen}] n=0 (no ammo in this scenario)")
            continue
        efl = _stat(items, "nominal_efl_mm")
        fnum = _stat(items, "nominal_fnum")
        fov = _stat(items, "nominal_fov_deg")
        imh = _stat(items, "nominal_imh_mm")
        pieces = sorted({i["n_pieces"] for i in items})
        print(f"\n[{scen}] n={len(items)}  element-counts={pieces}")
        print(
            f"  EFL  min={efl[0]:.2f} max={efl[1]:.2f} mean={efl[2]:.2f}"
            f"   -> bound [{efl[0] * 0.95:.1f}, {efl[1] * 1.05:.1f}]"
        )
        print(
            f"  F#   min={fnum[0]:.2f} max={fnum[1]:.2f} mean={fnum[2]:.2f}"
            f"   -> bound [{max(1.4, fnum[0] * 0.95):.1f}, {fnum[1] * 1.05:.1f}]"
        )
        print(
            f"  FOV  min={fov[0]:.1f} max={fov[1]:.1f} mean={fov[2]:.1f}"
            f"   -> bound [{fov[0] * 0.95:.0f}, {fov[1] * 1.05:.0f}]"
        )
        print(
            f"  IMH  min={imh[0]:.2f} max={imh[1]:.2f} mean={imh[2]:.2f}"
            f"   -> bound [{imh[0] * 0.95:.1f}, {imh[1] * 1.05:.1f}]"
        )
        print(f"  n_elements  min={min(pieces)} max={max(pieces)}")


if __name__ == "__main__":
    main()
