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
import math
import re
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.simplefilter("ignore")

from app.core.case_library import _classify_scenario, match_case  # noqa: E402
from app.core.lens_system import Scenario  # noqa: E402
from scripts.image_height_gate import (  # noqa: E402
    ImageHeightVerdict,
    describe_failure,
    first_order_image_height_mm,
    screen_image_height,
)

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "tests" / "data" / "eval_golden.json"
INDEX_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"
ZMX_DIR = Path(__file__).resolve().parents[1] / "data" / "zmx"

# Index vs ZMX-tail agreement. This is a *desync* check and nothing more: both
# numbers are the same real-ray reading, one copied into index.json and one
# written into the ZMX tail by the same call. It can catch a corpus half
# regenerated -- it can never catch a wrong reading, because a wrong reading is
# identical on both sides. The screen that can is `_screen_corpus_image_heights`.
ZMX_REAL_IMH_MAX_DEVIATION = 0.02
_REAL_IMH_RE = re.compile(r"^!\s*ATELIER_REAL_IMH_MM\s+([-+0-9.eE]+)", re.MULTILINE)
_FTAN_IMH_RE = re.compile(r"^!\s*ATELIER_FTAN_IMH_SANITY_MM\s+([-+0-9.eE]+)", re.MULTILINE)

# Corpus rows whose declared image height cannot be a real chief-ray intercept,
# pinned by case_id so the debt is counted and rings instead of being carried
# silently. All 34 were produced by the max-over-pupil derivation that
# `scripts/patent_to_zmx.py::_edge_field_image_height` used to use -- eight of
# them near 6e17 mm and five between 40 and 52 mm. They are pinned rather than
# asserted to zero because clearing them means regenerating 403 corpus rows,
# which moves routing, `rank_seeds` ordering and the sweet-zone floors; that is
# a separate shovel. Both directions fail closed: a new implausible row raises
# because it is not on the list, and a listed row that starts screening
# plausible raises because the pin has gone stale.
# Evidence: `.planning/evidence/corpus-truth-audit-triage-2026-07-30.md` (2).
_PINNED_IMPLAUSIBLE_IMAGE_HEIGHT_CASES = frozenset(
    {
        "US-10921568-B2-e2",
        "US-11719917-B2-e2",
        "US-11719917-B2-e3",
        "US-11719917-B2-e4",
        "US-11719917-B2-e5",
        "US-11719917-B2-e6",
        "US-11815662-B2-e3",
        "US-11933948-B2-e12",
        "US-11966029-B2-e5",
        "US-11966029-B2-e6",
        "US-12032139-B2-e2",
        "US-12032139-B2-e4",
        "US-12032139-B2-e6",
        "US-12044826-B2-e3",
        "US-12105260-B2-e1",
        "US-12140735-B2-e8",
        "US-12210142-B2-e3",
        "US-12210142-B2-e6",
        "US-12228698-B2-e2",
        "US-12228698-B2-e3",
        "US-12228698-B2-e5",
        "US-12259531-B2-e12",
        "US-12282142-B2-e9",
        "US-12345855-B2-e2",
        "US-12345855-B2-e3",
        "US-12345855-B2-e4",
        "US-12436366-B2-e3",
        "US-12436366-B2-e6",
        "US-12607827-B2-e3",
        "US-20240168263-A1-e12",
        "US-20250035890-A1-e2",
        "US-20250189767-A1-e12",
        "US-20250216655-A1-e9",
        "US-20260126622-A1-e2",
    }
)

# No corpus row currently has an unscreenable first-order reference. Pinned at
# empty so one appearing is a failure rather than a shrug -- a row whose
# reference blows up (half field at 90 deg, or a negative `tan`) has no screen
# at all, which is worse than failing one.
_PINNED_UNSCREENABLE_IMAGE_HEIGHT_CASES: frozenset[str] = frozenset()

# Briefs whose routing winner + quality evidence are golden-ised. Kept in sync
# with the eval's EvalCase requests (same source briefs).
_BASE_GOLDEN_BRIEFS: dict[str, dict] = {
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

_LEGACY_PATENT_GOLDEN_NAMES = {
    "US20170045714A1": "patent_wide_8p_low_f_number_reanchor",
    "US20170003482A1": "patent_ultrawide_7p_full_field_reanchor",
    "US20180143405A1": "patent_ultrawide_6p_fast_reanchor",
    "US10330891B2": "patent_ultrawide_6p_extreme_fov_reanchor",
    "US9651759B2": "patent_wide_6p_full_field_reanchor",
}


def _golden_name_for_case(case_id: str) -> str:
    if not case_id.startswith("US"):
        return f"seed_{case_id.lower()}_reanchor"
    return _LEGACY_PATENT_GOLDEN_NAMES.get(case_id, f"patent_{case_id.lower()}_reanchor")


def _finite_float(value: object) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"expected finite float, got {value!r}")
    return number


def _first_order_image_height_mm(record: dict) -> float | None:
    try:
        efl_mm = _finite_float(record["efl_mm"])
        fov_deg = _finite_float(record["fov_deg"])
    except (KeyError, TypeError, ValueError):
        return None
    # index `fov_deg` is the full field, so the half field is half of it.
    return first_order_image_height_mm(efl_mm, fov_deg / 2.0)


def _screen_corpus_image_heights(records: list) -> dict[str, dict]:
    """Screen every corpus row's image height against its first-order reference.

    This is the check `ZMX_REAL_IMH_MAX_DEVIATION` cannot be: it compares the
    real-ray reading against a number derived from a different quantity (the
    design's own focal length and field), so a wrong reading has nowhere to
    hide. Raises when the set of failures differs from what is pinned above --
    in either direction.
    """

    verdicts: dict[str, dict] = {}
    implausible: dict[str, str] = {}
    unscreenable: dict[str, str] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("case_id"), str):
            continue
        case_id = str(record["case_id"])
        try:
            image_height_mm = _finite_float(record["image_height_mm"])
        except (KeyError, TypeError, ValueError):
            image_height_mm = math.nan
        reference_mm = _first_order_image_height_mm(record)
        verdict, ratio = screen_image_height(image_height_mm, reference_mm)
        verdicts[case_id] = {
            "image_height_plausibility": str(verdict),
            "first_order_image_height_ratio": ratio,
        }
        if verdict is ImageHeightVerdict.IMPLAUSIBLE:
            implausible[case_id] = describe_failure(image_height_mm, reference_mm, verdict, ratio)
        elif verdict is ImageHeightVerdict.REFERENCE_UNUSABLE:
            unscreenable[case_id] = describe_failure(image_height_mm, reference_mm, verdict, ratio)

    _assert_pinned(implausible, _PINNED_IMPLAUSIBLE_IMAGE_HEIGHT_CASES, "implausible")
    _assert_pinned(unscreenable, _PINNED_UNSCREENABLE_IMAGE_HEIGHT_CASES, "unscreenable")
    return verdicts


def _assert_pinned(found: dict[str, str], pinned: frozenset[str], label: str) -> None:
    unpinned = sorted(set(found) - pinned)
    if unpinned:
        detail = "\n".join(f"  {case_id}: {found[case_id]}" for case_id in unpinned)
        raise ValueError(
            f"{len(unpinned)} corpus row(s) newly {label} on image height and not pinned in "
            f"scripts/e2_golden.py:\n{detail}"
        )
    stale = sorted(pinned - set(found))
    if stale:
        raise ValueError(
            f"{len(stale)} case(s) pinned as {label} on image height now screen clean; "
            f"drop them from the pinned set in scripts/e2_golden.py: {', '.join(stale)}"
        )


def _zmx_tail_number(source_zmx: str, pattern: re.Pattern[str]) -> float | None:
    path = ZMX_DIR / source_zmx
    if not path.exists():
        return None
    match = pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    if match is None:
        return None
    return _finite_float(match.group(1))


def _case_anchor_metadata(record: dict, verdict: dict) -> dict:
    case_id = str(record["case_id"])
    source_zmx = str(record["source_zmx"])
    image_height_mm = _finite_float(record["image_height_mm"])
    first_order_imh = _first_order_image_height_mm(record)
    first_order_deviation = (
        abs(image_height_mm - first_order_imh) / abs(first_order_imh)
        if first_order_imh is not None
        else None
    )
    zmx_real_imh = _zmx_tail_number(source_zmx, _REAL_IMH_RE)
    zmx_real_deviation = None
    anchor_source = "index:image_height_mm"
    if zmx_real_imh is not None:
        if zmx_real_imh <= 0.0:
            raise ValueError(f"{case_id} has non-positive ATELIER_REAL_IMH_MM: {zmx_real_imh}")
        zmx_real_deviation = abs(image_height_mm - zmx_real_imh) / zmx_real_imh
        if zmx_real_deviation > ZMX_REAL_IMH_MAX_DEVIATION:
            # Two copies of one reading disagreeing: the corpus is half
            # regenerated, not mismeasured. Says so, so the next reader does not
            # mistake this for evidence that the reading itself was checked.
            raise ValueError(
                f"{case_id} index image_height_mm={image_height_mm:.9g} is out of sync with its "
                f"own ZMX tail ATELIER_REAL_IMH_MM={zmx_real_imh:.9g} by "
                f"{zmx_real_deviation:.3%}; regenerate index.json and data/zmx together"
            )
        anchor_source = "zmx_tail:ATELIER_REAL_IMH_MM"
    return {
        "source_case_id": case_id,
        "image_height_anchor_source": anchor_source,
        "zmx_real_image_height_mm": zmx_real_imh,
        "zmx_real_image_height_deviation_frac": zmx_real_deviation,
        "first_order_image_height_mm": first_order_imh,
        "first_order_image_height_deviation_frac": first_order_deviation,
        "zmx_ftan_image_height_sanity_mm": _zmx_tail_number(source_zmx, _FTAN_IMH_RE),
        **verdict,
    }


def _case_golden_briefs() -> tuple[dict[str, dict], dict[str, dict]]:
    records = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"case index must be a list: {INDEX_PATH}")

    verdicts = _screen_corpus_image_heights(records)

    briefs: dict[str, dict] = {}
    metadata_by_name: dict[str, dict] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        case_id = record.get("case_id")
        if not isinstance(case_id, str):
            continue
        # Derive scenario from the classifier (single source of truth), not the
        # baked index.json label — the generated data predates the telephoto tier
        # so its stored `scenario` freezes long-focus seeds as wide. Keying on the
        # same (fov, efl) pair as load_case_library keeps golden briefs and the
        # runtime routing pool in lockstep (index.efl_mm == computed_efl_mm).
        scenario = _classify_scenario(float(record["fov_deg"]), float(record["efl_mm"]))
        name = _golden_name_for_case(case_id)
        metadata_by_name[name] = _case_anchor_metadata(record, verdicts[case_id])
        briefs[name] = {
            "source_case_id": case_id,
            "scenario": scenario.name,
            "efl_mm": float(record["efl_mm"]),
            "fnum": float(record["fnum"]),
            "fov_deg": float(record["fov_deg"]),
            "image_height_mm": float(record["image_height_mm"]),
            "n_elements": int(record["n_pieces"]),
            "priority": "performance" if float(record["fnum"]) < 2.0 else "balanced",
        }
    return briefs, metadata_by_name


CASE_GOLDEN_BRIEFS, CASE_GOLDEN_METADATA = _case_golden_briefs()
CASE_GOLDEN_CASE_NAMES = tuple(CASE_GOLDEN_BRIEFS)
PATENT_GOLDEN_CASE_NAMES = tuple(
    name
    for name in CASE_GOLDEN_CASE_NAMES
    if CASE_GOLDEN_BRIEFS[name]["source_case_id"].startswith("US")
)
GOLDEN_BRIEFS: dict[str, dict] = {**_BASE_GOLDEN_BRIEFS, **CASE_GOLDEN_BRIEFS}

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
    golden: dict[str, dict] = {}
    for name, brief in GOLDEN_BRIEFS.items():
        kwargs = dict(brief)
        source_case_id = kwargs.pop("source_case_id", None)
        kwargs["scenario"] = getattr(Scenario, kwargs["scenario"])
        kwargs["lightweight_design_assessment"] = True
        sample = match_case(**kwargs)
        entry: dict = {"selected_case_id": sample.metadata.case_id}
        if source_case_id is not None:
            entry["source_case_id"] = source_case_id
            entry.update(CASE_GOLDEN_METADATA.get(name, {}))
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
