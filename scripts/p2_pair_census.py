"""How many valid 异源 P2 trials can today's corpus actually supply?

`.planning/NORTH-STAR.md` §3 makes 异源打平率 the main indicator and leaves its
threshold blank until measured. Before any threshold can be measured, one prior
question has to be answered: **how many trials does the corpus even support?**
A trial needs a control patent design and a seed that is spec-compatible with it
and **not in the same patent family**. This script counts those trials.

It measures nothing about 打平率 itself and produces no quality number.

Why the same-source rule is deliberately over-broad
---------------------------------------------------
The dangerous direction is calling a same-family pair 异源: the pipeline is
`spec -> nearest seed -> optimise -> candidate`, so if the seed *is* the control
patent's relative, "no worse than it" is circular and the headline rises for
free. Excluding a genuinely cross-family pair only costs sample size. So every
ambiguity resolves toward 同源, and any case whose provenance cannot be
established is dropped rather than assumed cross-family.

The repository has no authoritative family data (no INPADOC/DOCDB family ids;
`family_hint` in `data/patents/*.jsonl` is an assignee+title near-duplicate
heuristic covering 360/714 discovery records). The rule therefore buckets by
**assignee brand**, which is a conservative superset of the family relation for
this corpus: family members share an assignee, so same-brand always implies
same-or-unknown family. The cost is real and is reported.

Assignee strings must be normalised first. Raw strings split one company across
several buckets -- Sunny appears as three, AAC as four, Ability as two (one
spelled with an em-dash) -- and an unmerged bucket makes two same-company
patents look cross-family, which is exactly the fail-open direction.

Usage::

    uv run python scripts/p2_pair_census.py
    uv run python scripts/p2_pair_census.py --json out.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_INDEX = ROOT / "app" / "data" / "optical_cases" / "index.json"
PATENT_POOL = ROOT / "data" / "patents"
QUARANTINE = ROOT / ".planning" / "evidence" / "corpus-fidelity-quarantine.json"

#: Corporate, industry and geographic tokens that carry no company identity.
#: Merging too much is safe here (it only shrinks the trial count); merging too
#: little is not, so this list errs long.
ASSIGNEE_STOPWORDS = frozenset(
    {
        "co",
        "ltd",
        "inc",
        "corp",
        "corporation",
        "company",
        "limited",
        "pte",
        "llc",
        "gmbh",
        "kk",
        "plc",
        "holdings",
        "group",
        "sa",
        "ag",
        "bv",
        "nv",
        "optics",
        "optical",
        "opto",
        "optronics",
        # `raytech` used to sit here. It is a **company name**, not an industry
        # word like `optics` or `precision`, and stopping it made
        # `Changzhou Raytech Optronics Co., Ltd.` and
        # `Raytech Optical (Changzhou) Co., Ltd.` tokenise to nothing at all --
        # each became its own brand and both read as cross-source against AAC
        # and against each other. Leaving it in place lets the corpus's own
        # string `Changzhou AAC Raytech Optronics Co., Ltd.` do the merging,
        # which is evidence rather than an attribution someone asserted.
        "electronics",
        "electro",
        "mechanics",
        "precision",
        "industrial",
        "technology",
        "technologies",
        "solutions",
        "imaging",
        "lens",
        "photonics",
        "device",
        "devices",
        "digital",
        "enterprise",
        "zhejiang",
        "changzhou",
        "jiangxi",
        "shenzhen",
        "ningbo",
        "suzhou",
        "taiwan",
        "china",
        "japan",
        "korea",
        "kabushiki",
        "kaisha",
        "seiki",
        "and",
        "of",
        "the",
    }
)

#: Three case-id shapes coexist in the index. A regex covering only the
#: embodiment-suffixed one silently reclassifies 25 patent cases as hand-built
#: real designs (there are 17 real designs, not 42).
_PATENT_ID_RE = re.compile(r"^(US(?:\d{11}|\d{7,8})[A-Z]\d?)")
_NEAR_DUPLICATE_RE = re.compile(r"near_duplicate_of=([A-Za-z0-9-]+)")


def normalise_patent_id(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def patent_id_of_case(case_id: str) -> str | None:
    """`US-10120164-B2-e2` / `US-12468127-B2` / `US20170045714A1` -> canonical id."""
    match = _PATENT_ID_RE.match(normalise_patent_id(case_id))
    return match.group(1) if match else None


#: Source-data token spellings that name one company but do not *share* a token
#: with its other spellings, so the connected-components grouping below cannot
#: merge them. Punctuation is already handled; a misspelling is not, because it
#: changes the token itself.
#:
#: Every entry is a fail-**closed** correction: merging two brands can only ever
#: shrink the 异源 sample, never inflate 打平率. Left unmerged, two publications
#: of one company read as cross-source against each other and manufacture par
#: pairs out of a spelling difference -- the exact failure
#: `tests/test_p2_pair_census.py` was written to prevent.
#:
#: Deliberately a table, not a fuzzy matcher. `Cognex` / `Fujinon` sit at 0.76
#: string similarity and are unrelated companies, so any similarity threshold
#: loose enough to catch `corephontonics` also merges those.
#:
#: Every entry is justified by **another string in the same corpus**, not by
#: outside knowledge. An earlier draft also merged `fujinon` into `fujifilm` on
#: the strength of the 2010 corporate absorption; that is a real fact but it is
#: not evidence *this repository holds*, so it was removed rather than shipped as
#: a code comment stating a fact nobody here can check. It is recorded as an open
#: question in the evidence trail instead.
ASSIGNEE_TOKEN_SPELLING_FIXES: dict[str, str] = {
    # `Corephontonics Ltd.` (one record) vs `COREPHOTONICS LTD.` /
    # `Corephotonics Ltd.` -- an `n` where an `o` belongs.
    "corephontonics": "corephotonics",
    # `Largen Precision Co., Ltd.` vs `Largan Precision Co., Ltd.` -- 0.9615
    # string similarity, an `e` where an `a` belongs. This one matters most:
    # LARGAN is the dominant control brand, so a mis-bucketed Largan design reads
    # as cross-source against Largan controls -- the exact fail-open this table
    # exists to close.
    "largen": "largan",
    # `Jiangxi OFLM Optical Co., Ltd.` vs `Jiangxi OFILM Optical Co., Ltd.`
    # -- 0.9836, a dropped `I`.
    "oflm": "ofilm",
}


def assignee_tokens(raw: str) -> frozenset[str]:
    """Distinctive tokens of an assignee string.

    Any punctuation (including the em-dash that appears in one Ability record)
    becomes a separator, so ``opto-electronics`` and ``opto—electronics``
    normalise identically. Known source-data misspellings are folded onto the
    canonical token via :data:`ASSIGNEE_TOKEN_SPELLING_FIXES`, because a typo
    changes the token and no amount of punctuation handling recovers it.
    """
    cleaned = re.sub(r"[^0-9a-z]+", " ", raw.lower())
    # Stopwords are filtered first, so a fix can never resurrect an industry word.
    # An earlier version reversed this to reach `raytech`, which was a stopword;
    # the right answer was that `raytech` is a company name and does not belong in
    # the stopword list at all -- see `ASSIGNEE_STOPWORDS`. Both routes produce
    # bit-identical buckets (40, zero members differ); this one asserts nothing.
    return frozenset(
        ASSIGNEE_TOKEN_SPELLING_FIXES.get(t, t)
        for t in cleaned.split()
        if t and t not in ASSIGNEE_STOPWORDS
    )


def brand_of_assignee(assignees: set[str]) -> dict[str, str]:
    """Group assignee strings into brands by shared distinctive tokens.

    Connected components over "shares at least one distinctive token". The
    representative is the lexicographically smallest member so the label is
    deterministic across runs -- picking, say, the shortest member makes the
    output depend on set iteration order whenever two members tie.
    """
    tokens = {a: assignee_tokens(a) for a in assignees}
    parent = {a: a for a in assignees}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_token: dict[str, list[str]] = {}
    for assignee, ts in tokens.items():
        for token in ts:
            by_token.setdefault(token, []).append(assignee)
    for members in by_token.values():
        head = find(members[0])
        for other in members[1:]:
            root = find(other)
            if root != head:
                parent[root] = head

    groups: dict[str, list[str]] = {}
    for assignee in assignees:
        groups.setdefault(find(assignee), []).append(assignee)
    return {a: min(sorted(g)) for g in groups.values() for a in g}


@dataclass(frozen=True)
class Provenance:
    """Brand lookup for case ids, plus the raw tables it was built from."""

    assignee_of_patent: dict[str, str]
    near_duplicate_of: dict[str, str]
    brand_of: dict[str, str]

    def brand_of_case(self, case_id: str) -> str | None:
        """Conservative family bucket, or ``None`` when provenance is unknown.

        ``None`` means *excluded*, never *cross-family with everything*. An
        earlier revision fell back to a per-patent bucket for records with no
        assignee, which made those patents look cross-family against the whole
        corpus -- the fail-open direction this whole rule exists to avoid.
        """
        patent = patent_id_of_case(case_id)
        if patent is None:
            return None
        # Walk the whole near-duplicate chain rather than only its head. A chain
        # can be cyclic, and stopping at "wherever the walk happened to end"
        # gives two members of one cycle different answers depending on which
        # end you start from. Resolving over the collected chain, smallest id
        # first, makes every member of a chain agree.
        chain: list[str] = [patent]
        seen = {patent}
        current = patent
        while current in self.near_duplicate_of:
            current = self.near_duplicate_of[current]
            if current in seen:
                break
            seen.add(current)
            chain.append(current)
        attributed = sorted(p for p in chain if p in self.assignee_of_patent)
        if not attributed:
            return None
        return self.brand_of[self.assignee_of_patent[attributed[0]]]


def load_provenance(pool_dir: Path = PATENT_POOL) -> Provenance:
    assignee: dict[str, str] = {}
    near_duplicate: dict[str, str] = {}
    for path in sorted(pool_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            patent = normalise_patent_id(str(record["id"]))
            if record.get("assignee"):
                assignee[patent] = str(record["assignee"]).strip()
            match = _NEAR_DUPLICATE_RE.search(str(record.get("family_hint") or ""))
            if match:
                near_duplicate[patent] = normalise_patent_id(match.group(1))
    return Provenance(assignee, near_duplicate, brand_of_assignee(set(assignee.values())))


def load_usable_case_ids(
    census_path: Path,
    *,
    case_index_path: Path = CASE_INDEX,
    quarantine_path: Path = QUARANTINE,
    require_in_domain: bool = True,
) -> tuple[list[str], list[str]]:
    """Return (usable, all) case ids.

    Usable needs **three** independent screens, not two:

    1. **strictly traceable** -- every field produces a spot radius, else the
       design yields no per-field 像质指标 and cannot be a control
    2. **fidelity-clean** -- a seed stripped of its aspheric terms is a *worse*
       lens than the patent, which biases 打平率 up
    3. **inside the product's domain** -- the control's own spec must pass
       ``parameter_guards.validate_scenario_params``

    Screen 3 was added 2026-07-29 after the pilot exposed the gap. A control
    defines the spec a customer would ask for; if the product's own guard would
    reject that request with HTTP 400, measuring against it says nothing about
    the product. Re-measured 2026-07-30 on `data/zmx`: of the 192 that pass
    screens 1+2, **74 (38.54%)** pass this one -- the 55 (28.6%) this docstring
    used to claim predates the `fov_deg` re-anchor, which moved the scenario
    labels and therefore which bounds each case is judged against -- the corpus's own `scenario` labels are far
    looser than ``SCENARIO_BOUNDS`` (violations: FOV 88, EFL 60, image height
    44, f/# 32, n_elements 31).

    The consequence is not cosmetic. In the 24-trial pilot, **both** trials that
    scored 打平 sat on specs the guard rejects, so the headline 8.3% was carried
    entirely by out-of-domain designs; in-domain it was 0.

    ``require_in_domain=False`` reproduces the old two-screen number for
    comparison. It is not the reporting default.
    """
    strict: dict[str, bool] = {}
    for line in census_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        strict[row["seed"]] = row["num_fields"] > 0 and row["n_positive"] == row["num_fields"]
    defective = set(
        json.loads(quarantine_path.read_text(encoding="utf-8"))["pools"]["data/zmx"]["defective"]
    )
    index = json.loads(case_index_path.read_text(encoding="utf-8"))
    everything = [r["case_id"] for r in index]
    usable = [
        r["case_id"]
        for r in index
        if strict.get(r["source_zmx"], False)
        and r["source_zmx"] not in defective
        and (not require_in_domain or spec_is_in_product_domain(r))
    ]
    return usable, everything


def spec_is_in_product_domain(record: Mapping[str, object]) -> bool:
    """Would the product accept this case's own spec as a request?

    Imported lazily so the pure-provenance helpers stay importable without the
    optical stack.
    """

    from app.core.lens_system import Scenario
    from app.core.parameter_guards import ParameterGuardError, validate_scenario_params

    try:
        validate_scenario_params(
            Scenario(str(record["scenario"])),
            efl_mm=float(record["efl_mm"]),  # type: ignore[arg-type]
            f_number=float(record["fnum"]),  # type: ignore[arg-type]
            fov_deg=float(record["fov_deg"]),  # type: ignore[arg-type]
            image_height_mm=float(record["image_height_mm"]),  # type: ignore[arg-type]
            n_elements=int(record["n_pieces"]),  # type: ignore[arg-type]
        )
    except (ParameterGuardError, ValueError, KeyError, TypeError):
        return False
    return True


def codev_rms_by_zmx(census_path: Path) -> dict[str, float]:
    """CODE V max-over-fields RMS spot diameter per ZMX, from the perfield census.

    Same source and same ruler the P2 trial judges with: the census's per-field value is
    ``SPOTDATA(...) -> ^spot(1)`` in mm, which is exactly ``@rmssum``'s per-field operand
    before its ``*1000``. Using it here is the whole point -- the routing gate this
    replaces read an *Optiland radius* measured over *half* the field, and passed a seed
    that CODE V calls a 101 um lens.
    """

    out: dict[str, float] = {}
    for line in census_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        declared = row.get("num_fields")
        if row.get("error") is not None or not declared or row.get("n_positive") != declared:
            continue
        spots = [field[1] * 1000.0 for field in row.get("fields", []) if field[0] == 0]
        if spots:
            out[row["seed"]] = max(spots)
    return out


def default_seed_quality_limit_um() -> float:
    """The corpus median, not a number anyone chose."""

    from app.core.corpus_quality import load_distribution

    return float(load_distribution()["percentiles"]["p50"])


#: How far the optimiser can stretch a seed's focal length and still converge.
#: Measured previously on the real machine and recorded in
#: `project-optimize-spike-setup-not-fundamental`: shrinking the focal length converges
#: across the board, stretching starts failing at about +25%. Shrinking is left
#: unbounded here because it was measured to converge, not because it is untested.
MAX_SEED_EFL_STRETCH = 0.25


def seed_efl_is_reachable(seed_efl_mm: float, target_efl_mm: float) -> bool:
    """Can the optimiser get this seed to that focal length at all?

    This is the constraint the quality gate must not override. Measured 2026-07-30 the
    hard way: gating the pool on quality ALONE pushed 53 of 59 trials past the +25%
    stretch limit (median seed/target EFL 1.209 -> 0.608), and the first four real-machine
    trials came back `aut_not_converged` at 14.0% / 17.0% / 22.6% EFL deviation. The
    "zero trial cost" that justified the quality gate had been measured on *planned*
    trials, which is the wrong quantity -- a planned trial that cannot converge is not a
    trial.
    """

    if not (seed_efl_mm > 0.0) or not (target_efl_mm > 0.0):
        return False
    return (target_efl_mm / seed_efl_mm) - 1.0 <= MAX_SEED_EFL_STRETCH


def census(
    census_path: Path, *, seed_quality_limit_um: float | None = None
) -> dict:
    # Imported lazily: the optical stack costs ~2s and the pure-provenance
    # helpers above are useful (and unit-tested) without it.
    warnings.simplefilter("ignore")
    from app.core.case_library import cases_for_scenario, rank_seeds
    from app.core.lens_system import Scenario

    provenance = load_provenance()
    usable_ids, all_ids = load_usable_case_ids(census_path)
    usable_set = set(usable_ids)

    # Seed-side quality gate, on the same ruler the trial judges with. `None` means
    # "use the corpus median"; pass math.inf to disable it and reproduce the old pool.
    limit = default_seed_quality_limit_um() if seed_quality_limit_um is None else float(
        seed_quality_limit_um
    )
    codev_rms = codev_rms_by_zmx(census_path)
    index_by_case = {r["case_id"]: r for r in json.loads(CASE_INDEX.read_text(encoding="utf-8"))}

    def seed_quality_ok(case_id: str) -> bool:
        record = index_by_case.get(case_id)
        if record is None:
            return False
        value = codev_rms.get(str(record.get("source_zmx")))
        # Fail closed: a seed whose CODE V quality is unknown cannot be shown to be
        # competitive, and admitting it is how a 101 um lens got in.
        return value is not None and value <= limit

    def seed_reachable(case_id: str, target_efl_mm: float) -> bool:
        record = index_by_case.get(case_id)
        if record is None:
            return False
        try:
            return seed_efl_is_reachable(float(record["efl_mm"]), target_efl_mm)
        except (KeyError, TypeError, ValueError):
            return False

    by_id: dict[str, object] = {}
    for scenario in Scenario:
        for case in cases_for_scenario(scenario):
            by_id.setdefault(case.metadata.case_id, case)

    trials: list[dict] = []
    excluded: collections.Counter[str] = collections.Counter()
    seed_pool_basis: collections.Counter[str] = collections.Counter()
    for control_id in usable_ids:
        control = by_id.get(control_id)
        if control is None:
            excluded["control_not_in_scenario_buckets"] += 1
            continue
        control_brand = provenance.brand_of_case(control_id)
        if control_brand is None:
            excluded["control_provenance_unknown"] += 1
            continue
        target_efl = control.metadata.computed_efl_mm
        cross_source = [
            case
            for case_id, case in by_id.items()
            if case_id != control_id
            and case_id in usable_set
            and provenance.brand_of_case(case_id) not in (None, control_brand)
        ]
        # Reachability first, quality second. The two constraints are NOT
        # interchangeable: an unreachable seed yields no candidate at all, while a
        # merely mediocre one still yields a judgeable trial. Filtering on quality alone
        # was measured to push 53 of 59 trials past the stretch limit.
        reachable = [
            case
            for case in cross_source
            if seed_reachable(case.metadata.case_id, target_efl)  # type: ignore[union-attr]
        ]
        preferred = [
            case
            for case in reachable
            if seed_quality_ok(case.metadata.case_id)  # type: ignore[union-attr]
        ]
        # Fall back rather than drop the control: "no seed both reachable and good"
        # is a real state worth measuring, and recording it beats silently shrinking
        # the sample.
        pool = preferred or reachable or cross_source
        if preferred:
            seed_pool_basis["reachable_and_quality"] += 1
        elif reachable:
            seed_pool_basis["reachable_only"] += 1
        elif cross_source:
            seed_pool_basis["neither"] += 1
        if not pool:
            excluded["no_cross_brand_seed_available"] += 1
            continue
        ranking = rank_seeds(
            pool,
            efl_mm=control.metadata.computed_efl_mm,
            fov_deg=control.metadata.fov_deg,
            fnum=control.paraxial.f_number,
            n_elements=control.metadata.n_pieces,
        )
        seed_id = ranking.best.metadata.case_id
        trials.append(
            {
                "control": control_id,
                "control_brand": control_brand,
                "seed": seed_id,
                "seed_brand": provenance.brand_of_case(seed_id),
            }
        )

    seed_use = collections.Counter(t["seed"] for t in trials)
    return {
        "cases_total": len(all_ids),
        "cases_usable": len(usable_ids),
        "trials": len(trials),
        "excluded": dict(excluded),
        "seed_quality_limit_um": limit,
        "seed_efl_max_stretch": MAX_SEED_EFL_STRETCH,
        "seed_pool_basis": dict(seed_pool_basis),
        "distinct_seeds_used": len(seed_use),
        "top5_seed_share": sum(n for _, n in seed_use.most_common(5)),
        "seed_reuse": seed_use.most_common(10),
        "control_brand_counts": dict(
            sorted(collections.Counter(t["control_brand"] for t in trials).items())
        ),
        "usable_brand_counts": dict(
            sorted(
                collections.Counter(
                    provenance.brand_of_case(c) or "(unknown)" for c in usable_ids
                ).items()
            )
        ),
        "trial_pairs": trials,
    }


def render(result: dict) -> str:
    lines = [
        "P2 异源 trial feasibility",
        "=" * 60,
        f"  case index                      {result['cases_total']}",
        f"  usable (traceable AND clean)    {result['cases_usable']}",
        f"  valid cross-brand trials        {result['trials']}",
    ]
    for reason, count in sorted(result["excluded"].items()):
        lines.append(f"    excluded: {reason:<34}{count}")
    lines += [
        "",
        "  WARNING -- trials are NOT independent samples:",
        f"    distinct seeds used           {result['distinct_seeds_used']}",
        f"    trials served by top-5 seeds  {result['top5_seed_share']} / {result['trials']}",
        "",
        "  usable cases by brand:",
    ]
    for brand, count in sorted(result["usable_brand_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"    {count:>5}  {brand}")
    lines.append("")
    lines.append("  This counts trials only. It reports no 打平率 and no quality number.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--census",
        type=Path,
        required=True,
        help="per-field traceability census JSONL for data/zmx (evidence, not in-repo)",
    )
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    result = census(args.census)
    print(render(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
