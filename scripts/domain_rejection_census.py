"""Which bound rejects whose designs, and does the market agree with the bound?

Why
---
`p2_pair_census` needs a control **and** a cross-brand seed. The corpus has six
assignees, but after its three usability screens only one brand survives in any
number, so a Largan control's cross-brand seed pool is two lenses and one seed
carries 40+ of the 49 trials. Sample independence, not corpus size, is what caps
the North Star's main indicator.

Measured 2026-07-29, per brand, through the three screens:

    brand                 all  traceable  +fidelity  +in-domain
    LARGAN                245        114        108          44
    NINGBO SUNNY           68         24         17           1
    (unknown)              38         28         25          25
    KANTATSU               34         15         15           0
    SAMSUNG ELECTRO-MECH   26         24         18           0
    AAC                    18          7          3           1
    ABILITY                13          6          6           0

Diversity survives screens 1 and 2 (Largan 108, Samsung 18, Sunny 17, Kantatsu
15). **Screen 3 -- the product's own ``SCENARIO_BOUNDS`` -- is what collapses it.**

What this script answers
------------------------
For every case that clears traceability and fidelity but fails the domain guard,
which bound rejected it, and **how many independent assignees ship designs on the
far side of that bound**.

That last number is the point. A bound crossed by designs from a single assignee
may be describing a genuine edge case. A bound crossed by designs from several
independent assignees is describing **our window, not the market** -- the corpus
itself is the market evidence, so no external number has to be invented to say so.

This script proposes nothing and changes nothing. Widening a bound changes what
the product claims to accept, and `AGENTS.md` records that the website's slider
BOUNDS must stay a subset of ``SCENARIO_BOUNDS`` -- so the decision is a product
decision that wants this table in front of it, not a side effect of wanting a
bigger sample.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASE_INDEX = ROOT / "app" / "data" / "optical_cases" / "index.json"
QUARANTINE = ROOT / ".planning" / "evidence" / "corpus-fidelity-quarantine.json"

#: A violation message reads e.g. "f/# 4.4 out of [1.8, 4.0] for smartphone-telephoto".
#: Only the parameter name and the scenario are kept; the offending value varies
#: per case and would fragment the grouping.
_VIOLATION = re.compile(r"^(?P<field>.+?)\s+\S+.*?\bfor\s+(?P<scenario>[\w-]+)\s*$")

#: Readings this far outside any plausible lens are the corpus's own known
#: degenerate modes, not evidence about the market. They are counted separately
#: rather than silently dropped.
_ABSURD_IMAGE_HEIGHT_MM = 100.0


@dataclass(frozen=True)
class BoundRejection:
    field: str
    scenario: str
    cases: int
    brands: int
    brand_names: tuple[str, ...]


def _violation_key(message: str) -> tuple[str, str] | None:
    match = _VIOLATION.match(message.strip())
    if match is None:
        return None
    return match.group("field").strip(), match.group("scenario").strip()


def census(
    *, census_path: Path, case_index: Path = CASE_INDEX, quarantine: Path = QUARANTINE
) -> tuple[list[BoundRejection], dict[str, object]]:
    from app.core.lens_system import Scenario
    from app.core.parameter_guards import ParameterGuardError, validate_scenario_params
    from scripts.p2_pair_census import load_provenance

    provenance = load_provenance()
    strict: dict[str, bool] = {}
    for line in census_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        strict[row["seed"]] = row["num_fields"] > 0 and row["n_positive"] == row["num_fields"]
    defective = set(json.loads(quarantine.read_text(encoding="utf-8"))["pools"]["data/zmx"]["defective"])

    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    considered = 0
    accepted = 0
    absurd = 0
    for entry in json.loads(case_index.read_text(encoding="utf-8")):
        if not strict.get(str(entry.get("source_zmx", "")), False):
            continue
        if str(entry.get("source_zmx", "")) in defective:
            continue
        considered += 1
        image_height = float(entry["image_height_mm"])
        if image_height > _ABSURD_IMAGE_HEIGHT_MM:
            absurd += 1
            continue
        brand = provenance.brand_of_case(str(entry["case_id"])) or "(unknown)"
        try:
            validate_scenario_params(
                Scenario(str(entry["scenario"])),
                efl_mm=float(entry["efl_mm"]),
                f_number=float(entry["fnum"]),
                fov_deg=float(entry["fov_deg"]),
                image_height_mm=image_height,
                n_elements=int(entry["n_pieces"]),
            )
        except ParameterGuardError as exc:
            for violation in getattr(exc, "violations", ()) or ():
                message = violation if isinstance(violation, str) else str(violation)
                key = _violation_key(message)
                if key is None:
                    key = ("(unparsed)", str(entry["scenario"]))
                by_key[key].add(brand)
                counts[key] += 1
            continue
        except (ValueError, KeyError, TypeError):
            key = ("(malformed row)", str(entry.get("scenario", "")))
            by_key[key].add(brand)
            counts[key] += 1
            continue
        accepted += 1

    rows = [
        BoundRejection(
            field=field,
            scenario=scenario,
            cases=counts[(field, scenario)],
            brands=len(by_key[(field, scenario)]),
            brand_names=tuple(sorted(by_key[(field, scenario)])),
        )
        for field, scenario in by_key
    ]
    rows.sort(key=lambda r: (-r.brands, -r.cases))
    summary = {
        "considered": considered,
        "accepted": accepted,
        "absurd_image_height": absurd,
        "rejected": considered - accepted - absurd,
        "bounds_crossed_by_multiple_brands": sum(1 for r in rows if r.brands >= 2),
        "bounds_crossed_by_one_brand": sum(1 for r in rows if r.brands == 1),
    }
    return rows, summary


def render(rows: list[BoundRejection], summary: dict[str, object]) -> str:
    lines = [
        "domain rejections among traceable + fidelity-clean cases",
        "=" * 58,
        f"considered                {summary['considered']}",
        f"accepted by the guard     {summary['accepted']}",
        f"rejected                  {summary['rejected']}",
        f"absurd image height       {summary['absurd_image_height']}   (corpus defect, not market evidence)",
        "",
        "bounds crossed by 2+ independent assignees -- these describe our window,",
        "not the market (the corpus is the evidence; no outside number needed):",
    ]
    for row in rows:
        if row.brands < 2:
            continue
        lines.append(
            f"  {row.field:<16} {row.scenario:<22} cases={row.cases:<4} brands={row.brands}"
            f"  {', '.join(b.split()[0] for b in row.brand_names)}"
        )
    lines.append("")
    lines.append(f"bounds crossed by exactly one assignee: {summary['bounds_crossed_by_one_brand']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True, help="perfield census jsonl")
    parser.add_argument("--json", type=Path, help="write the full table here")
    args = parser.parse_args(argv)
    rows, summary = census(census_path=args.census)
    if args.json:
        args.json.write_text(
            json.dumps(
                {"summary": summary, "rows": [asdict(r) for r in rows]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(render(rows, summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
