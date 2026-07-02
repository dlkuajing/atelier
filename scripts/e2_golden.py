"""Regenerate the eval routing-winner golden (E2-01 batch-0 hybrid contract).

The design-agent eval hardcodes *routing-winner* expectations -- which seed each
brief selects and that seed's floor-gap / min-250lp/mm quality evidence. Every
ingest batch changes the winners, forcing a hand re-anchor of those literals.
This script recomputes them from the real pipeline and writes
`tests/data/eval_golden.json`, so a batch re-anchor becomes "run this + review
the diff" instead of editing scattered assertions. The *behaviour* contracts
(blocked, forbidden_claims, frozen payload, replay gate) stay hardcoded in the
eval -- only the volatile winner data is golden-ised.

Run:  cd lumira-backend && uv run python scripts/e2_golden.py
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

from app.core.case_library import match_case  # noqa: E402

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "data" / "eval_golden.json"

# Briefs whose routing winner + quality evidence are golden-ised. Kept in sync
# with the eval's EvalCase requests (same source briefs).
GOLDEN_BRIEFS: dict[str, dict] = {
    "balanced_main_default": {
        "scenario": "SMARTPHONE_WIDE", "efl_mm": 3.0, "fnum": 2.0, "fov_deg": 78.0,
        "image_height_mm": 2.3, "n_elements": 5, "priority": "balanced",
    },
    "performance_full_field_seed_blocks_low_mtf": {
        "scenario": "SMARTPHONE_WIDE", "efl_mm": 2.9, "fnum": 1.8, "fov_deg": 74.1,
        "image_height_mm": 2.3, "n_elements": 5, "priority": "performance",
        "manufacturing_tier": "premium",
    },
    "relaxed_full_field_fallback_blocks_low_mtf": {
        "scenario": "SMARTPHONE_WIDE", "efl_mm": 3.8059, "fnum": 2.05, "fov_deg": 78.8,
        "image_height_mm": 3.2, "n_elements": 5,
    },
}

_FLOOR_GAP_RE = re.compile(r"floor gap ([0-9.]+)")
_MIN250_RE = re.compile(r"min250 ([0-9.]+)")


def _quality_actual(assessment) -> str | None:
    if assessment is None or assessment.seed_selection_scorecard is None:
        return None
    for item in assessment.seed_selection_scorecard.metric_scores:
        if item.metric_id == "quality":
            return item.actual
    return None


def compute_golden() -> dict:
    from app.core.lens_system import Scenario

    golden: dict[str, dict] = {}
    for name, brief in GOLDEN_BRIEFS.items():
        kwargs = dict(brief)
        kwargs["scenario"] = getattr(Scenario, kwargs["scenario"])
        sample = match_case(**kwargs)
        entry: dict = {"selected_case_id": sample.metadata.case_id}
        actual = _quality_actual(sample.design_assessment)
        if actual:
            gap = _FLOOR_GAP_RE.search(actual)
            min250 = _MIN250_RE.search(actual)
            if gap:
                entry["quality_floor_gap"] = gap.group(1)
            if min250:
                entry["quality_min250"] = min250.group(1)
        golden[name] = entry
    return golden


def main() -> None:
    golden = compute_golden()
    GOLDEN_PATH.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")
    print(f"wrote {GOLDEN_PATH} ({len(golden)} briefs)")
    for name, entry in golden.items():
        print(f"  {name}: {entry}")


if __name__ == "__main__":
    main()
