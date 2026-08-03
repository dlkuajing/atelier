"""Where the P2 cross-source sample actually goes: 442 -> 4 usable seeds.

Why this exists
---------------
`p2_pair_census.py` reports the *end* of the funnel (49 trials, 5 distinct seeds)
without showing which screen removed what. Measured 2026-08-02, the answer is not
the one the scoreboard implies:

* the **+25% focal-stretch limit was never binding** in the 2026-08-02 real-machine
  round -- all 49 trials asked for a *shrink* or at most +19.3%, so
  ``seed_pool_basis = {reachable_only: 46}`` is a **quality** shortage wearing a
  reachability label;
* the seed pool inherits screen 3 (**would the product accept this case's own spec
  as a request**), whose own justification in
  :func:`scripts.p2_pair_census.load_usable_case_ids` is written entirely about
  *controls* -- "A control defines the spec a customer would ask for". A seed is
  not a request, and applying the screen to seeds costs 192 -> 74;
* after cross-brand exclusion a LARGAN control -- most of the trials -- can be
  seeded from a handful of designs in the whole corpus, which is why one seed
  carries the great majority of them;
* those few are drawn from the parts of the corpus with the worst readings, and
  the badness groups by **assignee**, not by intake batch -- KANTATSU and AAC sit
  inside the batch that looks healthy and are 0-for-19 against the corpus median,
  while that batch's own median is carried by LARGAN being 58 of its 103 readings.
  ``quality_by_batch_and_brand`` in the artefact is the cross-tab that kills the
  batch reading; the batch table is kept only because it is what a reader tries
  first.

This script recomputes every number above from the two inputs, so the report is
reproducible rather than transcribed. It reads only the per-field census and the
case index -- no CODE V, no Optiland, no ray tracing.

Usage
-----
    uv run python scripts/upstream_supply_funnel.py \
        --census D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl \
        --json .planning/evidence/upstream-supply-funnel-2026-08-02.json
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.image_height_gate import (  # noqa: E402
    ImageHeightVerdict,
    first_order_image_height_mm,
    screen_image_height,
)
from scripts.p2_pair_census import (  # noqa: E402
    CASE_INDEX,
    QUARANTINE,
    codev_rms_by_zmx,
    default_seed_quality_limit_um,
    load_provenance,
    load_usable_case_ids,
    seed_efl_is_reachable,
    seed_quality_limit_basis,
)

#: Magnitude above which a corpus number stops being a large reading and starts
#: being a diverged trace. Not a tuned threshold: the corpus leaves a void of
#: sixteen orders of magnitude on both sides of it -- the largest real image
#: height is 51.9 mm and the next one up is 5.8e17 mm; the largest real RMS spot
#: diameter is 17358 um and the next one up is 3.2e20 um. `build()` reports both
#: edges so the void is visible in the artefact rather than asserted here.
DIVERGED_MAGNITUDE = 1e6

#: Full-angle degrees. Bands exist so "is this design bad or merely hard?" is
#: answered against comparable designs instead of against a corpus median that
#: mixes a 17 deg telephoto with a 133 deg ultra-wide.
FOV_BANDS: tuple[tuple[str, float, float], ...] = (
    ("<40", 0.0, 40.0),
    ("40-60", 40.0, 60.0),
    ("60-75", 60.0, 75.0),
    ("75-85", 75.0, 85.0),
    (">=85", 85.0, 1e9),
)


def fov_band(fov_deg: float) -> str:
    for name, lo, hi in FOV_BANDS:
        if lo <= fov_deg < hi:
            return name
    return ">=85"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
    }


def build(census_path: Path) -> dict[str, Any]:
    index = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    by_case = {record["case_id"]: record for record in index}
    rms_by_zmx = codev_rms_by_zmx(census_path)
    rms_of_case = {
        case_id: rms_by_zmx.get(str(record.get("source_zmx")))
        for case_id, record in by_case.items()
    }
    quarantined = set(
        json.loads(QUARANTINE.read_text(encoding="utf-8"))["pools"]["data/zmx"]["defective"]
    )
    provenance = load_provenance()
    limit = default_seed_quality_limit_um()

    in_domain, everything = load_usable_case_ids(census_path)
    trace_and_fidelity, _ = load_usable_case_ids(census_path, require_in_domain=False)

    # ---------- the screen-by-screen funnel ----------
    measured = [c for c, v in rms_of_case.items() if v is not None]
    funnel = {
        "case_index": len(everything),
        "full_field_codev_reading": len(measured),
        "trace_and_fidelity_clean": len(trace_and_fidelity),
        "and_in_product_domain": len(in_domain),
    }

    # ---------- who can seed whom ----------
    brand_of = {c: provenance.brand_of_case(c) for c in everything}
    control_pool = [c for c in in_domain if brand_of.get(c)]
    seed_supply: dict[str, dict[str, int]] = {}
    for label, pool in (
        ("today (3 screens)", in_domain),
        ("screen 3 on controls only", trace_and_fidelity),
    ):
        counts: collections.Counter[str] = collections.Counter()
        for control_id in control_pool:
            brand = brand_of[control_id]
            counts[control_id] = sum(
                1
                for seed_id in pool
                if seed_id != control_id and brand_of.get(seed_id) not in (None, brand)
            )
        values = sorted(counts.values())
        seed_supply[label] = {
            "controls": len(values),
            "cross_source_seeds_min": values[0] if values else 0,
            "cross_source_seeds_median": int(statistics.median(values)) if values else 0,
            "cross_source_seeds_max": values[-1] if values else 0,
        }

    # ---------- was reachability ever the binding screen? ----------
    reach_funnel: dict[str, list[int]] = collections.defaultdict(list)
    for control_id in control_pool:
        record = by_case[control_id]
        brand = brand_of[control_id]
        try:
            target_efl = float(record["efl_mm"])
        except (KeyError, TypeError, ValueError):
            continue
        cross = [
            s
            for s in trace_and_fidelity
            if s != control_id
            and brand_of.get(s) not in (None, brand)
            and rms_of_case.get(s) is not None
        ]
        reach_funnel["cross_source"].append(len(cross))
        reachable = [
            s
            for s in cross
            if seed_efl_is_reachable(float(by_case[s]["efl_mm"]), target_efl)
        ]
        reach_funnel["and_efl_reachable"].append(len(reachable))
        good = [s for s in reachable if rms_of_case[s] <= limit]
        reach_funnel["and_at_or_below_corpus_median"].append(len(good))

    # ---------- quality is batch-shaped ----------
    by_batch: dict[str, list[float]] = collections.defaultdict(list)
    by_brand: dict[str, list[float]] = collections.defaultdict(list)
    by_band: dict[str, list[float]] = collections.defaultdict(list)
    batch_brands: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for case_id in measured:
        record = by_case[case_id]
        value = rms_of_case[case_id]
        assert value is not None
        batch = str(record.get("intake_batch"))
        by_batch[batch].append(value)
        batch_brands[batch][brand_of.get(case_id) or "(unknown)"] += 1
        by_brand[brand_of.get(case_id) or "(unknown)"].append(value)
        with contextlib.suppress(KeyError, TypeError, ValueError):
            by_band[fov_band(float(record["fov_deg"]))].append(value)

    # The peer median has to exclude the rows this project already calls broken,
    # or "no worse than your own field band" becomes a bar set by defects. Measured
    # 2026-08-02 on the unfiltered version: the 40-60 band's median was 927.27 um
    # (8 rows, 2 of them diverged traces, 2 already quarantined), so "at or below
    # the band median" there meant "better than 927 um".
    def _healthy_for_band(case_id: str) -> bool:
        record = by_case.get(case_id) or {}
        if str(record.get("source_zmx")) in quarantined:
            return False
        value = rms_of_case.get(case_id)
        return value is not None and value < DIVERGED_MAGNITUDE

    healthy_by_band: dict[str, list[float]] = collections.defaultdict(list)
    for case_id in measured:
        if not _healthy_for_band(case_id):
            continue
        value = rms_of_case[case_id]
        record = by_case[case_id]
        assert value is not None
        with contextlib.suppress(KeyError, TypeError, ValueError):
            healthy_by_band[fov_band(float(record["fov_deg"]))].append(value)
    band_median = {band: statistics.median(v) for band, v in healthy_by_band.items() if v}
    band_population = {
        band: {"all": len(by_band.get(band, [])), "healthy": len(values)}
        for band, values in sorted(healthy_by_band.items())
    }

    def group_row(values: list[float], ids: list[str]) -> dict[str, Any]:
        row = _stats(values)
        row["at_or_below_corpus_median"] = sum(1 for v in values if v <= limit)
        # The like-for-like question: is this design bad, or is its field hard?
        # Both sides of this comparison must exclude the rows this project already
        # calls broken. An earlier version filtered only the *yardstick*: quarantined
        # rows were kept out of the band median but still counted toward the tally,
        # and 11 of them scored -- 8 in DATA-09d1, **0 in DATA-10b** -- which widened
        # the very contrast the evidence page rests on, in one direction only.
        in_band = 0
        scored = 0
        for case_id in ids:
            if not _healthy_for_band(case_id):
                continue
            value = rms_of_case.get(case_id)
            record = by_case.get(case_id) or {}
            try:
                band = fov_band(float(record["fov_deg"]))
            except (KeyError, TypeError, ValueError):
                continue
            if band not in band_median or value is None:
                continue
            scored += 1
            if value <= band_median[band]:
                in_band += 1
        row["at_or_below_own_fov_band_median"] = in_band
        row["scored_against_own_fov_band"] = scored
        return row

    ids_by_batch: dict[str, list[str]] = collections.defaultdict(list)
    ids_by_brand: dict[str, list[str]] = collections.defaultdict(list)
    for case_id in measured:
        ids_by_batch[str((by_case[case_id]).get("intake_batch"))].append(case_id)
        ids_by_brand[brand_of.get(case_id) or "(unknown)"].append(case_id)

    batches = {
        batch: {
            **group_row(values, ids_by_batch[batch]),
            "brands": dict(batch_brands[batch].most_common()),
        }
        for batch, values in sorted(by_batch.items(), key=lambda kv: -len(kv[1]))
    }
    brands = {
        brand: group_row(values, ids_by_brand[brand])
        for brand, values in sorted(by_brand.items(), key=lambda kv: -len(kv[1]))
    }

    # ---------- which variable is quality actually grouped by? ----------
    # "DATA-10b is a bad batch" survives a batch-level table and dies in this
    # cross-tab: KANTATSU and AAC sit *inside* the batch called healthy and are
    # as broken as anything in DATA-10b, while DATA-09d1's healthy median is
    # carried by LARGAN being 58 of its 103 readings. The grouping variable is
    # the assignee -- which is the parser family that read that assignee's
    # patent tables -- not the intake run.
    cells: dict[str, list[float]] = collections.defaultdict(list)
    cell_ids: dict[str, list[str]] = collections.defaultdict(list)
    for case_id in measured:
        key = f"{by_case[case_id].get('intake_batch')} | {brand_of.get(case_id) or '(unknown)'}"
        value = rms_of_case[case_id]
        assert value is not None
        cells[key].append(value)
        cell_ids[key].append(case_id)
    cross_tab = {
        key: group_row(values, cell_ids[key])
        for key, values in sorted(cells.items(), key=lambda kv: -len(kv[1]))
        if len(values) >= 3
    }

    # ---------- readings that describe no imaging system ----------
    # Definitional, not a chosen threshold: when the RMS spot *diameter* exceeds
    # the design's own image height, the blur from a single object point covers
    # the whole image. Reported at several ratios so the reader can see that the
    # catastrophic tail is nowhere near any borderline.
    impossible: list[dict[str, Any]] = []
    ratios: list[float] = []
    for case_id in measured:
        record = by_case[case_id]
        value = rms_of_case[case_id]
        try:
            imh_um = float(record["image_height_mm"]) * 1000.0
        except (KeyError, TypeError, ValueError):
            continue
        if imh_um <= 0 or value is None:
            continue
        ratio = value / imh_um
        ratios.append(ratio)
        if ratio >= 1.0:
            impossible.append(
                {
                    "case_id": case_id,
                    "rms_spot_diameter_um": value,
                    "image_height_um": imh_um,
                    "ratio": ratio,
                    "intake_batch": record.get("intake_batch"),
                    "brand": brand_of.get(case_id),
                    "quarantined": str(record.get("source_zmx")) in quarantined,
                }
            )
    ordered_ratios = sorted(ratios)
    spot_vs_image = {
        "cases_with_both_numbers": len(ordered_ratios),
        "ratio_median": statistics.median(ordered_ratios) if ordered_ratios else None,
        "at_or_above_1.0": sum(1 for r in ordered_ratios if r >= 1.0),
        "at_or_above_0.5": sum(1 for r in ordered_ratios if r >= 0.5),
        "at_or_above_0.1": sum(1 for r in ordered_ratios if r >= 0.1),
        "largest_ratio_below_1.0": max((r for r in ordered_ratios if r < 1.0), default=None),
        "cases": sorted(impossible, key=lambda row: -row["ratio"]),
    }

    # ---------- diverged traces, and the void that makes the cut a fact ----------
    imh_values = [
        float(r["image_height_mm"])
        for r in index
        if isinstance(r.get("image_height_mm"), (int, float))
    ]
    rms_values = [v for v in rms_of_case.values() if v is not None]
    diverged_imh = [
        r["case_id"] for r in index
        if isinstance(r.get("image_height_mm"), (int, float))
        and float(r["image_height_mm"]) >= DIVERGED_MAGNITUDE
    ]
    diverged_rms = [c for c, v in rms_of_case.items() if v is not None and v >= DIVERGED_MAGNITUDE]
    diverged = {
        "cut": DIVERGED_MAGNITUDE,
        "image_height_mm": {
            "over_cut": len(diverged_imh),
            "largest_under_cut": max((v for v in imh_values if v < DIVERGED_MAGNITUDE), default=None),
            "smallest_over_cut": min((v for v in imh_values if v >= DIVERGED_MAGNITUDE), default=None),
            "cases": sorted(diverged_imh),
        },
        "rms_spot_diameter_um": {
            "over_cut": len(diverged_rms),
            "largest_under_cut": max((v for v in rms_values if v < DIVERGED_MAGNITUDE), default=None),
            "smallest_over_cut": min((v for v in rms_values if v >= DIVERGED_MAGNITUDE), default=None),
            "cases": sorted(diverged_rms),
        },
        "union": sorted(set(diverged_imh) | set(diverged_rms)),
    }

    # ---------- does the shipped index still carry rows its own gate rejects? ----------
    # `scripts/image_height_gate.py` is applied at generation time inside
    # `patent_to_zmx.py`. The shipped `index.json` predates it, and no consumer
    # re-applies it -- so a control whose declared image height is 6e17 mm can
    # still hand that number to the optimiser as `spec_imh_mm`.
    gate_counts: collections.Counter[str] = collections.Counter()
    gate_reject: list[str] = []
    for record in index:
        try:
            reference = first_order_image_height_mm(
                float(record["efl_mm"]), float(record["fov_deg"]) / 2.0
            )
            verdict, _ratio = screen_image_height(float(record["image_height_mm"]), reference)
        except (KeyError, TypeError, ValueError):
            gate_counts["unreadable"] += 1
            continue
        gate_counts[str(verdict)] += 1
        if verdict is not ImageHeightVerdict.PLAUSIBLE:
            gate_reject.append(record["case_id"])
    rejected = set(gate_reject)
    image_height_gate = {
        "verdicts_over_shipped_index": dict(gate_counts),
        "rejected": sorted(rejected),
        "still_inside_trace_and_fidelity_pool": sorted(rejected & set(trace_and_fidelity)),
        "still_inside_in_domain_pool": sorted(rejected & set(in_domain)),
    }

    return {
        "schema": "atelier-upstream-supply-funnel-v1",
        "inputs": {
            "census_path": str(census_path),
            "census_sha256": _sha256(census_path),
            "case_index_sha256": _sha256(CASE_INDEX),
            "quarantine_sha256": _sha256(QUARANTINE),
            "seed_quality_limit_um": limit,
            "seed_quality_limit_basis": seed_quality_limit_basis(),
        },
        "funnel": funnel,
        "cross_source_seed_supply": seed_supply,
        "per_control_pool": {k: _stats([float(x) for x in v]) for k, v in reach_funnel.items()},
        "per_control_pool_zero_options": {
            k: sum(1 for x in v if x == 0) for k, v in reach_funnel.items()
        },
        "quality_by_intake_batch": batches,
        "quality_by_brand": brands,
        "quality_by_batch_and_brand": cross_tab,
        "fov_band_median_um": band_median,
        "fov_band_population": band_population,
        "spot_vs_image_height": spot_vs_image,
        "diverged_traces": diverged,
        "image_height_gate": image_height_gate,
    }


def render(result: dict[str, Any]) -> str:
    funnel = result["funnel"]
    lines = [
        "P2 上游供给漏斗（本表每个数字都由本脚本从 census + index 重算；",
        "  证据页第二/四/八节来自一次性探针，不在本脚本内）",
        "=" * 66,
        f"  语料索引                          {funnel['case_index']}",
        f"  有 CODE V 全场读数                {funnel['full_field_codev_reading']}",
        f"  且过 可追迹+保真度 两闸           {funnel['trace_and_fidelity_clean']}",
        f"  且过 产品参数闸（screen 3）       {funnel['and_in_product_domain']}",
        "",
        "  异源 seed 供给（每个对照能取到几颗跨受让人 seed）",
    ]
    for label, row in result["cross_source_seed_supply"].items():
        lines.append(
            f"    {label:<28} 中位 {row['cross_source_seeds_median']:>4}"
            f"  (min {row['cross_source_seeds_min']}, max {row['cross_source_seeds_max']})"
        )
    lines += ["", "  逐对照池，一层层筛下去（seed 池 = 两闸口径）"]
    for key, row in result["per_control_pool"].items():
        zero = result["per_control_pool_zero_options"][key]
        lines.append(
            f"    {key:<32} 中位 {row.get('median', 0):>6.1f}   零选项的对照 {zero}"
        )
    lines += ["", "  质量按 intake_batch（<=语料中位 / <=同 FOV 桶中位）"]
    for batch, row in result["quality_by_intake_batch"].items():
        lines.append(
            f"    {batch:<18} n={row['n']:>4}  中位 {row.get('median', 0):>12.2f} um"
            f"  <=全库 {row['at_or_below_corpus_median']:>3}"
            f"  <=同桶 {row['at_or_below_own_fov_band_median']:>3}"
        )
    lines += ["", "  同一份读数按 批次 × 受让人 切开（分组变量到底是哪个）"]
    for key, row in result["quality_by_batch_and_brand"].items():
        lines.append(
            f"    {key[:56]:<56} n={row['n']:>4}  中位 {row.get('median', 0):>12.2f} um"
            f"  <=全库 {row['at_or_below_corpus_median']:>3}"
        )

    spot = result["spot_vs_image_height"]
    lines += [
        "",
        "  点列直径 / 自身像高（>=1 表示单点的弥散斑铺满整幅像，不是成像系统）",
        f"    有两侧数字的                    {spot['cases_with_both_numbers']}",
        f"    >= 1.0                          {spot['at_or_above_1.0']}",
        f"    >= 0.5                          {spot['at_or_above_0.5']}",
        f"    >= 0.1                          {spot['at_or_above_0.1']}",
        f"    小于 1.0 的最大值               {spot['largest_ratio_below_1.0']}",
    ]
    for case in spot["cases"][:8]:
        lines.append(
            f"      {case['case_id']:<24} ratio={case['ratio']:.3e}"
            f"  batch={case['intake_batch']}  已隔离={case['quarantined']}"
        )

    div = result["diverged_traces"]
    lines += ["", f"  发散追迹（截断在 {div['cut']:.0g}，两侧留空档而不是贴着阈值）"]
    for key in ("image_height_mm", "rms_spot_diameter_um"):
        row = div[key]
        lines.append(
            f"    {key:<24} 越线 {row['over_cut']:>3}"
            f"   线下最大 {row['largest_under_cut']!r}   线上最小 {row['smallest_over_cut']!r}"
        )
    lines.append(f"    并集                     {len(div['union'])} 颗")

    gate = result["image_height_gate"]
    lines += [
        "",
        "  已出厂 index.json 过一遍它自己的像高闸（生成期已有，消费期无人复核）",
        f"    判决                            {gate['verdicts_over_shipped_index']}",
        f"    被拒但仍在 两闸池 里            {len(gate['still_inside_trace_and_fidelity_pool'])}",
        f"    被拒但仍在 域内池 里            {len(gate['still_inside_in_domain_pool'])}",
    ]
    if gate["still_inside_in_domain_pool"]:
        lines.append(f"      {', '.join(gate['still_inside_in_domain_pool'][:10])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build(args.census)
    print(render(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
