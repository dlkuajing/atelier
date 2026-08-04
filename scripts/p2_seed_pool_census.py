"""Is P2's seed concentration a *supply* problem or a *selection* problem?

`.planning/PENDING-RULINGS.md` §00 tells 主公 that P2 has no clean path without a
ruling, and rests that on one claim:

    四闸把合格域钉死在 9 个互异 seed 设计上，普查加不进一个条目

Two things about that claim need measuring rather than repeating:

1. **9 is how many seeds were *chosen*, not how many were *eligible*.** The
   2026-08-04 run routed 59 controls to 13 distinct seeds because
   ``rank_seeds`` returns one ``best`` per control -- that number is a property
   of the router, not of the pool it ranked.
2. **The third of the "four gates" does not exist.** ``rank_seeds`` applies no
   hard ``|Δfov| ≤ cap``; ``_seed_spec_guard_penalty`` adds a *soft* penalty for
   ``fov_miss > 5°`` to the distance. Only three screens actually remove a seed
   from a control's pool: cross-brand, EFL reachability, and the CODE V quality
   limit -- and those three are exactly what :class:`p2_pair_census.SeedSupply`
   builds.

So this script walks the same pools ``p2_pair_census.census`` routes from --
through the same :meth:`~p2_pair_census.SeedSupply.pool_for`, never a second
copy of the chain -- and asks, for every control, **how rectilinear the most
rectilinear eligible seed is, at each stage of the screen chain**:

    cross_source  -> reachable -> preferred(=pool) -> chosen by rank_seeds

Reading the result
------------------
Distortion is the one North Star metric the candidates lose on (2026-08-04:
distortion par 1/48 against RMS 45/48 and MTF 44/48), and it is inherited from
the seed. Where the low-distortion options disappear tells you what to fix:

============================  ==========================================
first stage with no low-|d|   what that means
============================  ==========================================
``chosen`` only               **selection**: the option was in the pool and
                              ``rank_seeds`` -- whose signature has no
                              distortion term -- ranked it below others.
``preferred``                 the CODE V quality limit removed it.
``reachable``                 the ±25% EFL stretch limit removed it.
``cross_source``              **supply**: the corpus has no such seed for
                              this control. PENDING-RULINGS §00 is right.
============================  ==========================================

What the distortion number here is, and is not
----------------------------------------------
There is no stored CODE V distortion for seeds, so this uses the **first-order
proxy** ``image_height / (f · tan(half-field)) - 1``, built from
:func:`image_height_gate.first_order_image_height_mm` (the production helper)
and the same accessors ``rank_seeds`` scores with. Three limits, all real:

* ``image_height_mm`` in the corpus index is the **max over the exit pupil**,
  not the chief ray (corpus-truth audit, 2026-07-30). The proxy inherits that.
* The trial judges with CODE V ``@dstpct`` over the rebuilt field, not with a
  first-order ratio at the seed's native field.
* The seed is rescaled to the control's field before optimisation, so a seed's
  native proxy is not its distortion in the trial.

That makes this a **screen, not a verdict**. It is strong in one direction: if
no eligible seed is anywhere near rectilinear, none can become one. A pool that
*does* hold rectilinear options is a lead that needs the real machine to
confirm -- which is the whole point, because today that lead is being reported
to 主公 as impossible.

Usage::

    uv run python scripts/p2_seed_pool_census.py --census <perfield.jsonl>
    uv run python scripts/p2_seed_pool_census.py --census <...> --json out.json
"""

from __future__ import annotations

import argparse
import collections
import functools
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.image_height_gate import first_order_image_height_mm  # noqa: E402
from scripts.p2_pair_census import (  # noqa: E402
    STAGING_ZMX_DIR,
    ControlSeedPool,
    SeedSupply,
    patent_id_of_case,
)

ZMX_DIR = ROOT / "data" / "zmx"


@functools.cache
def _fingerprint(zmx: str, staging: bool) -> str | None:
    from app.core.engines.prescription_identity import fingerprint_zmx

    path = (STAGING_ZMX_DIR if staging else ZMX_DIR) / zmx
    return fingerprint_zmx(path) if path.is_file() else None


def distinct_prescriptions(supply: SeedSupply, case_ids: list[str]) -> int:
    """How many *designs* a list of case ids is, not how many files or patents.

    Continuations carry the same prescription under a different patent number:
    ``US-10073249-B2-e12`` and ``US-10191250-B2-e12`` agree to every digit of
    EFL, field, distortion and CODE V quality. Counting patents would report
    them as two options when a router only ever has one, so anything that
    counts "how many seeds could serve this control" has to fold them first.
    Unfingerprintable files are counted individually rather than folded, so a
    decode failure can never quietly shrink a denominator.
    """
    seen: set[str] = set()
    unreadable = 0
    for case_id in case_ids:
        fact = supply.staging_facts.get(case_id)
        if fact is not None:
            fingerprint = _fingerprint(str(fact["zmx"]), True)
        else:
            record = supply.index_by_case.get(case_id) or {}
            source = record.get("source_zmx")
            fingerprint = _fingerprint(str(source), False) if source else None
        if fingerprint is None:
            unreadable += 1
        else:
            seen.add(fingerprint)
    return len(seen) + unreadable

#: Thresholds the stage decomposition is reported at, in percent of first-order
#: distortion. Swept rather than fixed on purpose: a single constant deciding
#: the headline is the failure mode this repository keeps hitting. 2% is where
#: the 2026-08-04 controls sit (judged median 1.93%), the rest bracket it.
RECTILINEAR_SWEEP_PCT = (1.0, 2.0, 3.0, 5.0)

#: The threshold the human-readable summary leads with. Every other number in
#: the sweep is printed next to it, so this picks the emphasis, not the answer.
RECTILINEAR_PROXY_PCT = 2.0


@dataclass(frozen=True)
class SeedDistortion:
    case_id: str
    patent: str | None
    pool: str
    efl_mm: float | None
    fov_deg: float | None
    image_height_mm: float | None
    first_order_image_height_mm: float | None
    image_height_ratio: float | None
    proxy_distortion_pct: float | None

    @property
    def readable(self) -> bool:
        return self.proxy_distortion_pct is not None and math.isfinite(
            self.proxy_distortion_pct
        )

    @property
    def magnitude(self) -> float:
        """|distortion|, or +inf when the proxy could not be formed.

        Unmeasurable sorts to the bottom rather than the top: an unknown seed
        must never win a "most rectilinear option" comparison. Because that
        makes blindness look like "no rectilinear option here", every stage
        also reports its readable fraction and no conclusion is drawn from a
        stage whose coverage is incomplete.
        """
        if not self.readable:
            return math.inf
        return abs(self.proxy_distortion_pct)  # type: ignore[arg-type]


def _declared_facts(supply: SeedSupply, case_id: str) -> tuple[dict | None, str]:
    """The declared (EFL, FOV, image height) row for a design, and its pool.

    Deliberately **not** ``case.metadata`` / ``_case_image_height_mm``: those
    return 0.0 image height for every staging design (they resolve through the
    corpus index, which staging seeds are not in), and a 0.0 silently becomes an
    unreadable proxy on exactly the 54-of-59 seeds the router actually picks.
    Reading both pools' declared values instead keeps one ruler across the two.
    """
    fact = supply.staging_facts.get(case_id)
    if fact is not None:
        return fact, "staging"
    record = supply.index_by_case.get(case_id)
    return record, "corpus"


def seed_distortion(supply: SeedSupply, case_id: str) -> SeedDistortion:
    """First-order distortion proxy for one design, same formula in both pools.

    ``image_height / (f · tan(half-field)) - 1``, with every input taken from
    the design's declared record. This is the identical construction
    ``scripts/p2_staging_seed_manifest`` already stores as
    ``image_height_ratio``; :func:`self_check_ratio_formula` proves the two
    agree on all 157 staging rows rather than assuming it.
    """
    row, pool_name = _declared_facts(supply, case_id)
    patent = patent_id_of_case(case_id)
    if row is None:
        return SeedDistortion(
            case_id, patent, pool_name, None, None, None, None, None, None
        )

    def num(key: str) -> float | None:
        value = row.get(key)
        try:
            out = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return out if math.isfinite(out) else None

    efl_mm = num("efl_mm")
    fov_deg = num("fov_deg")
    image_height_mm = num("image_height_mm")
    reference: float | None = None
    ratio: float | None = None
    proxy: float | None = None
    if efl_mm is not None and fov_deg is not None:
        reference = first_order_image_height_mm(efl_mm, fov_deg / 2.0)
    if reference is not None and image_height_mm is not None and image_height_mm > 0.0:
        ratio = image_height_mm / reference
        proxy = (ratio - 1.0) * 100.0
    return SeedDistortion(
        case_id=case_id,
        patent=patent,
        pool=pool_name,
        efl_mm=efl_mm,
        fov_deg=fov_deg,
        image_height_mm=image_height_mm,
        first_order_image_height_mm=reference,
        image_height_ratio=ratio,
        proxy_distortion_pct=proxy,
    )


def self_check_ratio_formula(supply: SeedSupply) -> dict[str, object]:
    """Prove this module's ratio is the one the staging manifest already stores.

    The manifest carries ``image_height_ratio`` per seed, computed at manifest
    time by :mod:`scripts.p2_staging_seed_manifest`. If this module's
    reconstruction disagrees with it, every distortion number below is on a
    different ruler than the rest of the repository -- the precise failure this
    project has already shipped once (routing read a half-field Optiland radius
    while the judge read a full-field CODE V diameter).
    """
    checked = 0
    worst = 0.0
    mismatches: list[dict[str, object]] = []
    for case_id, fact in supply.staging_facts.items():
        stored = fact.get("image_height_ratio")
        mine = seed_distortion(supply, case_id).image_height_ratio
        if stored is None or mine is None:
            mismatches.append({"seed": case_id, "stored": stored, "recomputed": mine})
            continue
        checked += 1
        delta = abs(float(stored) - mine)
        worst = max(worst, delta)
        if delta > 1e-9:
            mismatches.append(
                {"seed": case_id, "stored": float(stored), "recomputed": mine}
            )
    return {
        "staging_rows": len(supply.staging_facts),
        "checked": checked,
        "max_abs_delta": worst,
        "mismatches": mismatches[:10],
        "mismatch_count": len(mismatches),
        "agrees": not mismatches,
    }


def _best(entries: list[SeedDistortion]) -> SeedDistortion | None:
    """The most rectilinear entry, or None when the stage is empty.

    ⚠️ On its own this is a **degenerate** optimum and must not be read as "the
    option the router should have taken". Measured 2026-08-05: the winner for 51
    of 59 controls is a 10-degree telephoto, which is trivially rectilinear and
    useless for a 90-degree wide-angle spec -- only 2 of 59 sit within 5 degrees
    of their control's field. ``dominating_alternatives`` is the reading that
    survives that objection; this one is kept only to show the distribution.
    """
    if not entries:
        return None
    return min(entries, key=lambda e: e.magnitude)


def _fov_miss(entry: SeedDistortion, control: SeedDistortion) -> float | None:
    if entry.fov_deg is None or control.fov_deg is None:
        return None
    return abs(entry.fov_deg - control.fov_deg)


def _efl_miss(entry: SeedDistortion, control: SeedDistortion) -> float | None:
    """|log(seed EFL / control EFL)| -- symmetric, so 2x and 0.5x score alike."""
    if not entry.efl_mm or not control.efl_mm or entry.efl_mm <= 0 or control.efl_mm <= 0:
        return None
    return abs(math.log(entry.efl_mm / control.efl_mm))


def dominating_alternatives(
    entries: list[SeedDistortion], chosen: SeedDistortion, control: SeedDistortion
) -> list[SeedDistortion]:
    """Eligible seeds that beat the chosen one on distortion **without giving
    anything up** on the two axes the router weights most.

    A seed qualifies only when it is *no worse* than the chosen seed in field
    match and in focal-length match, and *strictly better* in first-order
    distortion. That makes the obvious rebuttal -- "the rectilinear option was
    off-spec, the router was right to skip it" -- unavailable: a dominating
    seed is at least as on-spec as the one actually used.

    Ties are excluded (``<`` not ``<=``) so a seed cannot dominate itself.
    """
    chosen_fov = _fov_miss(chosen, control)
    chosen_efl = _efl_miss(chosen, control)
    if chosen_fov is None or chosen_efl is None or not chosen.readable:
        return []
    out: list[SeedDistortion] = []
    for entry in entries:
        if entry.case_id == chosen.case_id or not entry.readable:
            continue
        fov = _fov_miss(entry, control)
        efl = _efl_miss(entry, control)
        if fov is None or efl is None:
            continue
        if fov <= chosen_fov and efl <= chosen_efl and entry.magnitude < chosen.magnitude:
            out.append(entry)
    return sorted(out, key=lambda e: e.magnitude)


def _describe(entry: SeedDistortion | None) -> dict[str, object] | None:
    if entry is None:
        return None
    return {
        "case_id": entry.case_id,
        "patent": entry.patent,
        "pool": entry.pool,
        "proxy_distortion_pct": entry.proxy_distortion_pct,
        "image_height_ratio": entry.image_height_ratio,
        "efl_mm": entry.efl_mm,
        "fov_deg": entry.fov_deg,
        "image_height_mm": entry.image_height_mm,
    }


STAGES = ("cross_source", "reachable", "preferred")

#: How near a seed's field has to be to the control's to count as "could serve
#: this spec". Reused from `rank_seeds._seed_spec_guard_penalty`, which starts
#: penalising a seed above exactly this miss -- not a new constant.
FIELD_WINDOW_DEG = 5.0


def same_brand_counterfactual(
    supply: SeedSupply,
    options: ControlSeedPool,
    control: SeedDistortion,
    *,
    threshold_pct: float,
    field_window_deg: float = FIELD_WINDOW_DEG,
) -> dict[str, object]:
    """What the cross-source rule costs this control, in seeds.

    Counts every usable design -- **ignoring the brand screen, and only the
    brand screen** -- that could actually serve this control's spec: EFL
    reachable, CODE V quality within the limit, field within
    ``field_window_deg``, and first-order distortion within ``threshold_pct``.
    Then splits the survivors into cross-source and same-brand.

    This is the number PENDING-RULINGS §00 turns on. "The corpus has no
    rectilinear wide-angle seed" and "the corpus has them but they are all the
    control's own brand" are different worlds with different fixes, and only
    this split tells them apart. Every screen except the brand one is applied
    through ``supply``, so the two arms cannot drift from what census routes on.
    """
    target_efl = options.target_efl_mm
    control_fov = control.fov_deg
    if target_efl is None or control_fov is None:
        return {"cross_source": 0, "same_brand": 0, "same_brand_brands": {}}

    control_patent = patent_id_of_case(options.control_id)
    cross: list[str] = []
    same_other_patent: list[str] = []
    same_own_patent: list[str] = []
    for case_id in list(supply.by_id) + list(supply.staging_by_id):
        if case_id == options.control_id:
            continue
        # Staging designs are seeds in either arm; corpus designs have to be in
        # the usable set to be a seed at all, exactly as `pool_for` requires.
        if case_id not in supply.staging_by_id and case_id not in supply.usable_set:
            continue
        brand = supply.seed_brand(case_id)
        if brand is None:
            continue
        if not supply.seed_reachable(case_id, target_efl):
            continue
        if not supply.seed_quality_ok(case_id):
            continue
        entry = seed_distortion(supply, case_id)
        if entry.fov_deg is None or abs(entry.fov_deg - control_fov) > field_window_deg:
            continue
        if entry.magnitude > threshold_pct:
            continue
        if brand != options.control_brand:
            cross.append(case_id)
        elif entry.patent is not None and entry.patent == control_patent:
            # Another embodiment of the control's own patent. Same brand *and*
            # same document: no family definition, however drawn, would ever
            # admit it. Counting it under "what the brand rule costs" would
            # inflate the case for changing that rule.
            same_own_patent.append(case_id)
        else:
            same_other_patent.append(case_id)
    return {
        "cross_source": len(cross),
        "cross_source_designs": distinct_prescriptions(supply, cross),
        "same_brand": len(same_other_patent) + len(same_own_patent),
        "same_brand_other_patent": len(same_other_patent),
        # The number that matters: files and patent numbers both overcount,
        # because continuations repeat one prescription across documents.
        "same_brand_other_patent_designs": distinct_prescriptions(
            supply, same_other_patent
        ),
        "same_brand_own_patent": len(same_own_patent),
        "same_brand_other_patents": len(
            {patent_id_of_case(c) for c in same_other_patent} - {None}
        ),
        "cross_source_examples": sorted(cross)[:5],
        "same_brand_other_patent_examples": sorted(same_other_patent)[:5],
    }


def analyse_control(supply: SeedSupply, options: ControlSeedPool) -> dict[str, object]:
    """One control: pool sizes, the chosen seed, and the best option per stage."""
    from app.core.case_library import rank_seeds

    control = options.control
    stages: dict[str, list[SeedDistortion]] = {
        name: [
            seed_distortion(supply, case.metadata.case_id)  # type: ignore[union-attr]
            for case in cases
        ]
        for name, cases in (
            ("cross_source", options.cross_source),
            ("reachable", options.reachable),
            ("preferred", options.preferred),
        )
    }

    ranking = rank_seeds(
        options.pool,
        efl_mm=control.metadata.computed_efl_mm,
        fov_deg=control.metadata.fov_deg,
        fnum=control.paraxial.f_number,
        n_elements=control.metadata.n_pieces,
    )
    chosen_id = ranking.best.metadata.case_id
    by_id = {entry.case_id: entry for entry in stages["cross_source"]}
    chosen = by_id[chosen_id]

    # Where the chosen seed and the most rectilinear eligible seed sit in the
    # router's own order, so "it was passed over" is a rank, not an adjective.
    order = [ranked.case_id for ranked in ranking.ranked]
    rank_of = {case_id: i + 1 for i, case_id in enumerate(order)}
    pool_entries = [by_id[case_id] for case_id in order]
    best_in_pool = _best(pool_entries)

    control_entry = seed_distortion(supply, options.control_id)
    dominating = dominating_alternatives(pool_entries, chosen, control_entry)
    return {
        "control": options.control_id,
        "control_brand": options.control_brand,
        "control_proxy_distortion_pct": control_entry.proxy_distortion_pct,
        "control_efl_mm": control_entry.efl_mm,
        "control_fov_deg": control_entry.fov_deg,
        "basis": options.basis,
        "chosen_fov_miss_deg": _fov_miss(chosen, control_entry),
        "chosen_efl_log_miss": _efl_miss(chosen, control_entry),
        "counterfactual": {
            f"{threshold:g}": same_brand_counterfactual(
                supply, options, control_entry, threshold_pct=threshold
            )
            for threshold in RECTILINEAR_SWEEP_PCT
        },
        "dominating": {
            "count": len(dominating),
            "distinct_patents": len({e.patent for e in dominating if e.patent}),
            "best": (
                {
                    **(_describe(dominating[0]) or {}),
                    "rank": rank_of.get(dominating[0].case_id),
                    "quality_um": supply.seed_quality_um(dominating[0].case_id),
                    "fov_miss_deg": _fov_miss(dominating[0], control_entry),
                    "efl_log_miss": _efl_miss(dominating[0], control_entry),
                }
                if dominating
                else None
            ),
        },
        "sizes": {
            **{name: len(entries) for name, entries in stages.items()},
            "pool": len(options.pool),
        },
        # Blindness must never be readable as "no rectilinear option here".
        "readable": {
            name: sum(1 for e in entries if e.readable) for name, entries in stages.items()
        },
        "distinct_patents": {
            name: len({e.patent for e in entries if e.patent})
            for name, entries in stages.items()
        },
        "chosen": {
            **(_describe(chosen) or {}),
            "rank": rank_of.get(chosen_id),
            "quality_um": supply.seed_quality_um(chosen_id),
        },
        "best_by_stage": {
            **{name: _describe(_best(entries)) for name, entries in stages.items()},
            "pool": (
                {
                    **(_describe(best_in_pool) or {}),
                    "rank": rank_of.get(best_in_pool.case_id),
                    "quality_um": supply.seed_quality_um(best_in_pool.case_id),
                }
                if best_in_pool
                else None
            ),
        },
        "rectilinear_counts": {
            f"{threshold:g}": {
                name: sum(1 for e in entries if e.magnitude <= threshold)
                for name, entries in stages.items()
            }
            for threshold in RECTILINEAR_SWEEP_PCT
        },
    }


def _first_stage_without_rectilinear(row: dict, threshold: float) -> str:
    """The earliest screen at which this control ran out of rectilinear options.

    ``chosen`` means the pool still held one and the router did not pick it --
    the selection reading. The stage names are ordered from loosest to
    tightest, so the first miss is the screen that did the removing.
    """
    counts = row["rectilinear_counts"][f"{threshold:g}"]
    for stage in STAGES:
        if counts[stage] == 0:
            return stage
    chosen = row["chosen"].get("proxy_distortion_pct")
    if chosen is not None and abs(chosen) <= threshold:
        return "none"
    return "chosen"


def run(census_path: Path, *, admit_staging_seeds: bool = True) -> dict:
    supply = SeedSupply(census_path, admit_staging_seeds=admit_staging_seeds)
    formula_check = self_check_ratio_formula(supply)
    rows: list[dict] = []
    excluded: collections.Counter[str] = collections.Counter()
    eligible_cases: set[str] = set()
    eligible_patents: set[str] = set()
    for control_id in supply.usable_ids:
        options = supply.pool_for(control_id)
        if options.excluded is not None:
            excluded[options.excluded] += 1
            continue
        for case in options.pool:
            case_id = case.metadata.case_id  # type: ignore[union-attr]
            eligible_cases.add(case_id)
            if (patent := patent_id_of_case(case_id)) is not None:
                eligible_patents.add(patent)
        rows.append(analyse_control(supply, options))

    chosen_cases = {row["chosen"]["case_id"] for row in rows}
    chosen_patents = {row["chosen"]["patent"] for row in rows if row["chosen"]["patent"]}
    return {
        "schema": "atelier.p2_seed_pool_census/v2",
        "census": str(census_path),
        "rectilinear_sweep_pct": list(RECTILINEAR_SWEEP_PCT),
        "seed_quality_limit_um": supply.limit,
        "ratio_formula_self_check": formula_check,
        "controls_analysed": len(rows),
        "controls_excluded": dict(excluded),
        "eligible_seed_cases": len(eligible_cases),
        "eligible_seed_patents": len(eligible_patents),
        "chosen_seed_cases": len(chosen_cases),
        "chosen_seed_patents": len(chosen_patents),
        "proxy_coverage": {
            stage: {
                "readable": sum(r["readable"][stage] for r in rows),
                "total": sum(r["sizes"][stage] for r in rows),
            }
            for stage in STAGES
        },
        "chosen_proxy_readable": sum(
            1 for r in rows if r["chosen"].get("proxy_distortion_pct") is not None
        ),
        "controls_with_dominating_alternative": sum(
            1 for r in rows if r["dominating"]["count"] > 0
        ),
        "first_stage_without_rectilinear": {
            f"{threshold:g}": dict(
                collections.Counter(
                    _first_stage_without_rectilinear(row, threshold) for row in rows
                )
            )
            for threshold in RECTILINEAR_SWEEP_PCT
        },
        "pool_size_median": statistics.median(r["sizes"]["pool"] for r in rows)
        if rows
        else None,
        "controls": rows,
    }


def render(result: dict) -> str:
    rows = result["controls"]
    check = result["ratio_formula_self_check"]
    out = [
        "P2 seed pool census -- eligible vs chosen",
        "=" * 68,
        f"  controls analysed              {result['controls_analysed']}",
        f"  excluded                       {result['controls_excluded']}",
        "",
        "  proxy coverage (read this before any number below)",
    ]
    for stage in STAGES:
        cover = result["proxy_coverage"][stage]
        pct = 100.0 * cover["readable"] / cover["total"] if cover["total"] else 0.0
        out.append(
            f"    {stage:14s} {cover['readable']:6d} / {cover['total']:<6d} readable  ({pct:5.1f}%)"
        )
    out.append(
        f"    chosen seed    {result['chosen_proxy_readable']:6d} / "
        f"{result['controls_analysed']:<6d} readable"
    )
    out.append(
        f"    ratio formula matches the staging manifest's own: "
        f"{'YES' if check['agrees'] else 'NO'} "
        f"({check['checked']}/{check['staging_rows']}, max delta {check['max_abs_delta']:.2e})"
    )
    out += [
        "",
        "  eligible vs chosen (the claim under test)",
        f"    distinct seed CASES eligible   {result['eligible_seed_cases']}",
        f"    distinct seed CASES chosen     {result['chosen_seed_cases']}",
        f"    distinct seed PATENTS eligible {result['eligible_seed_patents']}",
        f"    distinct seed PATENTS chosen   {result['chosen_seed_patents']}",
        "",
        "  per-control pool size (seeds handed to rank_seeds)",
    ]
    if rows:
        sizes = sorted(r["sizes"]["pool"] for r in rows)
        out.append(
            f"    min {sizes[0]}  median {statistics.median(sizes):.0f}  max {sizes[-1]}"
        )
        out.append("")
        out.append("  where the rectilinear options run out, by threshold")
        labels = {
            "cross_source": "SUPPLY -- corpus has none for this control",
            "reachable": "removed by the +-25% EFL stretch limit",
            "preferred": "removed by the CODE V quality limit",
            "chosen": "SELECTION -- in the pool, ranked below others",
            "none": "the chosen seed is already rectilinear",
        }
        header = "    stage          " + "".join(
            f"{t:g}%".rjust(7) for t in result["rectilinear_sweep_pct"]
        )
        out.append(header + "   meaning")
        for stage, label in labels.items():
            cells = "".join(
                str(
                    result["first_stage_without_rectilinear"][f"{t:g}"].get(stage, 0)
                ).rjust(7)
                for t in result["rectilinear_sweep_pct"]
            )
            out.append(f"    {stage:14s}{cells}   {label}")
        out.append("")
        out.append("  DOMINATING alternatives -- eligible seeds that are no worse in")
        out.append("  field match AND no worse in focal-length match AND strictly more")
        out.append("  rectilinear than the seed the router actually picked")
        dom = [r for r in rows if r["dominating"]["count"] > 0]
        out.append(
            f"    controls with at least one          {len(dom)} / {len(rows)}"
        )
        if dom:
            counts = sorted(r["dominating"]["count"] for r in dom)
            out.append(
                f"    how many per control                min {counts[0]}  "
                f"median {statistics.median(counts):.0f}  max {counts[-1]}"
            )
            out.append(
                "    |distortion| chosen -> best dominating   "
                f"{statistics.median(abs(r['chosen']['proxy_distortion_pct']) for r in dom):.2f}%"
                f" -> {statistics.median(abs(r['dominating']['best']['proxy_distortion_pct']) for r in dom):.2f}%"
            )
            ranks = [
                r["dominating"]["best"]["rank"]
                for r in dom
                if r["dominating"]["best"]["rank"] is not None
            ]
            if ranks:
                out.append(
                    f"    its rank in the router's own order   median "
                    f"{statistics.median(ranks):.0f}  max {max(ranks)}"
                )
            out.append(
                "    distinct patents supplying them     "
                f"{len({r['dominating']['best']['patent'] for r in dom if r['dominating']['best']['patent']})}"
            )
        out.append("")
        out.append(
            "  WHAT THE CROSS-SOURCE RULE COSTS: seeds that could serve the spec"
        )
        out.append(
            f"  (EFL reachable AND quality within limit AND field within "
            f"{FIELD_WINDOW_DEG:g} deg AND rectilinear),"
        )
        out.append("  counted with the brand screen -- and only the brand screen -- lifted")
        out.append(
            "  controls with at least one such seed, by where the seed comes from:"
        )
        out.append(
            "    threshold   cross-source   same brand,   same brand,   median same-brand"
        )
        out.append(
            "                               OTHER patent  OWN patent    other-patent DESIGNS"
        )
        for threshold in result["rectilinear_sweep_pct"]:
            key = f"{threshold:g}"
            cross = sum(1 for r in rows if r["counterfactual"][key]["cross_source"] > 0)
            other = sum(
                1 for r in rows if r["counterfactual"][key]["same_brand_other_patent"] > 0
            )
            own = sum(
                1 for r in rows if r["counterfactual"][key]["same_brand_own_patent"] > 0
            )
            med = statistics.median(
                r["counterfactual"][key]["same_brand_other_patent_designs"] for r in rows
            )
            out.append(
                f"    {key + '%':>9s}   {cross:>12d}   {other:>12d}  {own:>11d}   {med:>20.0f}"
            )
        out.append(
            "    ^ 'OTHER patent' is the population a family-based 异源 rule could admit"
        )
        out.append(
            "      and today's assignee-based rule cannot. 'OWN patent' never qualifies"
        )
        out.append(
            "      under any family definition and is shown so it is not double-counted."
        )
        out.append(
            "    ! different patent number is NECESSARY but NOT SUFFICIENT for different"
        )
        out.append(
            "      family -- continuations repeat one prescription across documents, so"
        )
        out.append("      this is an UPPER BOUND on what a family rule would admit.")
        out.append("")
        out.append("  naive min-|distortion| in pool (DEGENERATE -- see _best docstring)")
        gaps = []
        for row in rows:
            best = row["best_by_stage"].get("pool") or {}
            chosen = row["chosen"].get("proxy_distortion_pct")
            best_pct = best.get("proxy_distortion_pct")
            if chosen is None or best_pct is None:
                continue
            gaps.append((abs(chosen), abs(best_pct), best.get("rank")))
        if gaps:
            out.append(f"    controls with both readable    {len(gaps)} / {len(rows)}")
            out.append(
                f"    median |chosen|                {statistics.median(g[0] for g in gaps):.2f}%"
            )
            out.append(
                f"    median |best in pool|          {statistics.median(g[1] for g in gaps):.2f}%"
            )
            strictly_better = [g for g in gaps if g[1] < g[0] - 1e-9]
            out.append(
                "    pools holding a MORE rectilinear option than the one chosen"
                f"   {len(strictly_better)} / {len(gaps)}"
            )
            if strictly_better:
                ranks = [g[2] for g in strictly_better if g[2] is not None]
                if ranks:
                    out.append(
                        "    that option's rank in the router's order: median "
                        f"{statistics.median(ranks):.0f}  max {max(ranks)}"
                    )
    out += [
        "",
        "  This is a first-order screen, not a CODE V verdict. See module docstring.",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--no-staging-seeds", action="store_true")
    args = parser.parse_args(argv)

    result = run(args.census, admit_staging_seeds=not args.no_staging_seeds)
    print(render(result))
    if args.json:
        args.json.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
