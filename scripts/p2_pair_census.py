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
        "electronics",
        "electro",
        "mechanics",
        "precision",
        "industrial",
        "technology",
        "technologies",
        "solutions",
        "raytech",
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


def assignee_tokens(raw: str) -> frozenset[str]:
    """Distinctive tokens of an assignee string.

    Any punctuation (including the em-dash that appears in one Ability record)
    becomes a separator, so ``opto-electronics`` and ``opto—electronics``
    normalise identically.
    """
    cleaned = re.sub(r"[^0-9a-z]+", " ", raw.lower())
    return frozenset(t for t in cleaned.split() if t and t not in ASSIGNEE_STOPWORDS)


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


def census(census_path: Path) -> dict:
    # Imported lazily: the optical stack costs ~2s and the pure-provenance
    # helpers above are useful (and unit-tested) without it.
    warnings.simplefilter("ignore")
    from app.core.case_library import cases_for_scenario, rank_seeds
    from app.core.lens_system import Scenario

    provenance = load_provenance()
    usable_ids, all_ids = load_usable_case_ids(census_path)
    usable_set = set(usable_ids)

    by_id: dict[str, object] = {}
    for scenario in Scenario:
        for case in cases_for_scenario(scenario):
            by_id.setdefault(case.metadata.case_id, case)

    trials: list[dict] = []
    excluded: collections.Counter[str] = collections.Counter()
    for control_id in usable_ids:
        control = by_id.get(control_id)
        if control is None:
            excluded["control_not_in_scenario_buckets"] += 1
            continue
        control_brand = provenance.brand_of_case(control_id)
        if control_brand is None:
            excluded["control_provenance_unknown"] += 1
            continue
        pool = [
            case
            for case_id, case in by_id.items()
            if case_id != control_id
            and case_id in usable_set
            and provenance.brand_of_case(case_id) not in (None, control_brand)
        ]
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
