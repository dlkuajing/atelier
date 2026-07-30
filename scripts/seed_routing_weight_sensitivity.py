"""Does re-weighting `rank_seeds` move the North Star's main indicator at all?

The question this answers
-------------------------
`case_library.rank_seeds` weights `fov` at 0.46, the largest of its terms. Those weights
were tuned while 253 of 442 corpus cases stored a **half** field angle in `fov_deg`
(`scripts/fov_unit_census.py`). After the 2026-07-29 re-anchor to full angle, the obvious
suspicion is that the weights are now mis-tuned and should be re-fitted.

A weighting cannot be re-tuned by eye. `.planning/NORTH-STAR.md` §3 supplies the only
criterion that means anything here: a seed is good insofar as the candidate grown from it
can par against its control. The measurable proxy, on data already on disk, is **how many
P2 pairs start with a seed that already images better than the control it must par
against** -- CODE V RMS spot diameter on both sides, same census, same ruler.

`rank_seeds` picks the seed (argmin per control), so that count is a function of the
weights. This script measures the function.

What it measured (2026-07-30, `perfield-census.jsonl` of `trace-census-20260728`)
--------------------------------------------------------------------------------
**Nothing moves.** Across the whole grid -- including `fov -> 0`, EFL-only and FOV-only --
the count stays at **6/49** and the median seed/control ratio at **13.93**. The most
extreme variants re-route 2-4 of the 49 pairings; none of them changes the criterion.

The reason is structural and is visible in the pool-size histogram this script prints:
**45 of the 49 controls have a cross-source seed pool of exactly 4 seeds.** A scoring
function choosing 1 of 4 has almost no leverage. The corpus, the brand rule and the domain
screen decide the pairing before the weights are consulted -- the same conclusion
`.planning/evidence/domain-bounds-vs-market-2026-07-29.md` reached from the other side
("打分不是瓶颈，可选项的数量才是").

So this script's output is a *negative* result, and that is its point: it is the evidence
that re-tuning these weights is not defensible work, and the record that can be re-run
when the corpus grows enough for the pool sizes to change.

Method note
-----------
The grid re-weights the **live** `distance_parts` returned by a real `rank_seeds` call
rather than re-implementing the distance, so a recomputed argmin cannot drift from
production. This is sound because the parts do not depend on the weight *values*, only on
which keys are active; `_seed_spec_guard_penalty` is an additive, weight-independent term,
recomputed here from the same inputs. Ties are broken the way `rank_seeds` breaks them
(stable sort over pool order, strict `<`), so `moved` counts real re-routings and not
tiebreak noise. `--verify` asserts the reconstruction reproduces production's argmin on
every pair before any variant is reported.

Usage::

    uv run python scripts/seed_routing_weight_sensitivity.py
    uv run python scripts/seed_routing_weight_sensitivity.py --gate p50
    uv run python scripts/seed_routing_weight_sensitivity.py --json out.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import statistics
import sys
import warnings
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: Runtime product, lives outside the worktree. Same census the P2 trial judges with.
DEFAULT_CENSUS = Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl")

#: Weight variants to test. Keys must already be active in the production weight dict for
#: this call shape -- raising a term that has no `distance_parts` entry (e.g. `imh` when
#: the caller passes no image height) would consume normalised weight while contributing
#: nothing, which is not a weighting anyone would ship.
WEIGHT_GRID: list[tuple[str, dict[str, float]]] = [
    ("fov 0.46 -> 0.30", {"fov": 0.30}),
    ("fov 0.46 -> 0.20", {"fov": 0.20}),
    ("fov 0.46 -> 0.10", {"fov": 0.10}),
    ("fov -> 0", {"fov": 0.0}),
    ("efl 0.20 -> 0.46", {"efl": 0.46}),
    ("efl 0.20 -> 0.60", {"efl": 0.60}),
    ("efl = fov = 0.33", {"efl": 0.33, "fov": 0.33}),
    ("efl 0.46 / fov 0.20 (swap)", {"efl": 0.46, "fov": 0.20}),
    ("fnum 0.05 -> 0.20", {"fnum": 0.20}),
    ("quality -> 0", {"quality": 0.0}),
    ("quality -> 0.60", {"quality": 0.60}),
    ("efl only", {"fov": 0.0, "fnum": 0.0, "quality": 0.0, "nel": 0.0}),
    ("fov only", {"efl": 0.0, "fnum": 0.0, "quality": 0.0, "nel": 0.0}),
]


def _spec_guard_penalty(case: Any, *, fov_deg: float) -> float:
    """Mirror of `case_library._seed_spec_guard_penalty` for the census call shape.

    The census passes no `image_height_mm`, so that function's image-height limb is dead
    and only the FOV limb is reproduced here. `--verify` is what keeps this mirror honest:
    if the original grows a term, the reconstructed argmin stops matching production and
    the run fails before reporting anything.
    """
    fov_miss = abs(case.metadata.fov_deg - fov_deg)
    return 0.0 if fov_miss <= 5.0 else 0.04 + (fov_miss - 5.0) / 20.0


def build_population(census_path: Path, *, gate: float | None) -> list[dict[str, Any]]:
    """Rebuild the P2 pairing population, keeping each pool's distance parts.

    Pairing screens are imported from `p2_pair_census` rather than restated, so this
    script and the trial planner cannot drift.
    """
    warnings.simplefilter("ignore")
    from app.core.case_library import cases_for_scenario, rank_seeds
    from app.core.lens_system import Scenario
    from scripts.p2_pair_census import (
        CASE_INDEX,
        codev_rms_by_zmx,
        default_seed_quality_limit_um,
        load_provenance,
        load_usable_case_ids,
    )

    provenance = load_provenance()
    usable_ids, _ = load_usable_case_ids(census_path)
    usable_set = set(usable_ids)
    limit = default_seed_quality_limit_um() if gate is None else gate
    codev_rms = codev_rms_by_zmx(census_path)
    index_by_case = {r["case_id"]: r for r in json.loads(CASE_INDEX.read_text(encoding="utf-8"))}

    def rms_of(case_id: str) -> float | None:
        record = index_by_case.get(case_id)
        return None if record is None else codev_rms.get(str(record.get("source_zmx")))

    by_id: dict[str, Any] = {}
    for scenario in Scenario:
        for case in cases_for_scenario(scenario):
            by_id.setdefault(case.metadata.case_id, case)

    population: list[dict[str, Any]] = []
    for control_id in usable_ids:
        control = by_id.get(control_id)
        if control is None:
            continue
        control_brand = provenance.brand_of_case(control_id)
        if control_brand is None:
            continue
        pool = [
            case
            for case_id, case in by_id.items()
            if case_id != control_id
            and case_id in usable_set
            and provenance.brand_of_case(case_id) not in (None, control_brand)
            and (lambda v: v is not None and v <= limit)(rms_of(case_id))
        ]
        if not pool:
            continue
        target_fov = control.metadata.fov_deg
        ranking = rank_seeds(
            pool,
            efl_mm=control.metadata.computed_efl_mm,
            fov_deg=target_fov,
            fnum=control.paraxial.f_number,
            n_elements=control.metadata.n_pieces,
        )
        parts_by_id = {rc.case_id: dict(rc.distance_parts) for rc in ranking.ranked}
        # Pool order, not ranked order: `rank_seeds` sorts with a stable sort, so ties
        # fall to the order the pool was built in. Reproducing that order is what makes
        # the `moved` column trustworthy.
        order = [c.metadata.case_id for c in pool]
        population.append(
            {
                "control": control_id,
                "control_rms_um": rms_of(control_id),
                "pool_size": len(pool),
                "order": order,
                "parts": parts_by_id,
                "guards": {
                    c.metadata.case_id: _spec_guard_penalty(c, fov_deg=target_fov) for c in pool
                },
                "seed_rms_um": {cid: rms_of(cid) for cid in order},
                "production_seed": ranking.best.metadata.case_id,
                "production_weights": dict(ranking.weights),
            }
        )
    return population


def _argmin_seed(entry: dict[str, Any], weights: dict[str, float]) -> str:
    best_id, best_d = entry["order"][0], math.inf
    for case_id in entry["order"]:
        parts = entry["parts"][case_id]
        distance = math.sqrt(sum(weights[k] * parts.get(k, 0.0) ** 2 for k in weights))
        distance += entry["guards"][case_id]
        if distance < best_d:
            best_id, best_d = case_id, distance
    return best_id


def _resolve_weights(base: dict[str, float], override: dict[str, float]) -> dict[str, float]:
    merged = {k: override.get(k, v) for k, v in base.items()}
    live = {k: v for k, v in merged.items() if v > 0}
    total = sum(live.values())
    return {k: v / total for k, v in live.items()} if total else {}


def evaluate(
    population: list[dict[str, Any]], override: dict[str, float] | None = None
) -> dict[str, Any]:
    """Score one weight variant against the criterion."""
    ahead = 0
    ratios: list[float] = []
    seeds: collections.Counter[str] = collections.Counter()
    moved = 0
    for entry in population:
        weights = (
            dict(entry["production_weights"])
            if not override
            else _resolve_weights(entry["production_weights"], override)
        )
        seed_id = _argmin_seed(entry, weights)
        if seed_id != entry["production_seed"]:
            moved += 1
        seeds[seed_id] += 1
        seed_rms, control_rms = entry["seed_rms_um"][seed_id], entry["control_rms_um"]
        if seed_rms and control_rms:
            ratios.append(seed_rms / control_rms)
            if seed_rms < control_rms:
                ahead += 1
    return {
        "trials": len(population),
        "seed_ahead": ahead,
        "judged": len(ratios),
        "median_seed_over_control": statistics.median(ratios) if ratios else None,
        "distinct_seeds": len(seeds),
        "pairings_moved": moved,
    }


def verify(population: list[dict[str, Any]]) -> None:
    """The reconstruction must reproduce production's argmin on every pair."""
    for entry in population:
        rebuilt = _argmin_seed(entry, entry["production_weights"])
        if rebuilt != entry["production_seed"]:
            raise AssertionError(
                f"reconstruction disagrees with rank_seeds for control {entry['control']}: "
                f"{rebuilt!r} != {entry['production_seed']!r}"
            )


def render(result: dict[str, Any]) -> str:
    lines = [
        "rank_seeds weight sensitivity vs the P2 par-reachability criterion",
        "=" * 84,
        f"  census            {result['census']}",
        f"  seed quality gate {result['gate']}",
        f"  pairs             {result['trials']}",
        f"  pool sizes        {result['pool_sizes']}",
        "",
        "  criterion = pairs whose routed seed already images better than its control",
        "              (CODE V RMS spot diameter, both sides, same census)",
        "",
        f"  {'variant':<30}{'ahead':>7}{'judged':>8}{'median':>9}{'seeds':>7}{'moved':>7}",
        "  " + "-" * 68,
    ]
    for row in result["rows"]:
        median = (
            "-"
            if row["median_seed_over_control"] is None
            else f"{row['median_seed_over_control']:.3f}"
        )
        lines.append(
            f"  {row['variant']:<30}{row['seed_ahead']:>7}{row['judged']:>8}"
            f"{median:>9}{row['distinct_seeds']:>7}{row['pairings_moved']:>7}"
        )
    lines += [
        "",
        "  'moved' counts pairings whose seed changed. A variant that moves pairings but",
        "  leaves 'ahead' flat has re-routed without improving anything.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument(
        "--gate",
        default="off",
        help="seed quality gate: 'off' (the pool the real P2 runs use), 'p50' (the corpus "
        "median default), or a number in um",
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--verify", action="store_true", help="assert parity with rank_seeds")
    args = parser.parse_args(argv)

    if not args.census.is_file():
        parser.error(f"census not found: {args.census}")
    if args.gate == "off":
        gate: float | None = math.inf
    elif args.gate == "p50":
        gate = None
    else:
        gate = float(args.gate)

    population = build_population(args.census, gate=gate)
    if not population:
        parser.error("no pairs formed -- check the census path and the gate")
    if args.verify:
        verify(population)

    rows = [{"variant": "production", **evaluate(population)}]
    rows += [{"variant": name, **evaluate(population, override)} for name, override in WEIGHT_GRID]
    result = {
        "census": str(args.census),
        "gate": "off" if gate == math.inf else ("corpus p50" if gate is None else f"{gate} um"),
        "trials": len(population),
        "pool_sizes": dict(sorted(collections.Counter(e["pool_size"] for e in population).items())),
        "rows": rows,
    }
    print(render(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
