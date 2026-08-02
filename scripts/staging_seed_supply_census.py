"""The healthy cross-source seeds we already have, in `data/zmx-staging`.

Why this exists
---------------
`scripts/upstream_supply_funnel.py` measures how the shipped corpus starves the
异源 seed pool: a LARGAN control -- 54 of 59 trials -- can be seeded from **5**
designs, and the one that carries 48/59 is a 101 um lens.

`data/zmx-staging/patent-local-replay` holds **613 git-tracked ZMX with zero
filename overlap with the 442-file corpus**, and the 2026-07-28 census already
measured 238 of them at full field. It has been looked at once before
(`.planning/evidence/staging-domain-ceiling-2026-07-29.md`) and only ever with
the **control-side** question -- "how many are inside the product's parameter
domain" (58). That screen is control-side reasoning by its own docstring in
`p2_pair_census.load_usable_case_ids`; a seed is not a customer request. The
seed-side question had never been asked.

What it measures
----------------
For each corpus control, whether the staging pool can supply a cross-assignee
seed that is simultaneously

* **fidelity-clean** -- not in the staging quarantine pool,
* **measured at full field by CODE V** and at or below the corpus median,
* **EFL-reachable** under the measured `+25%` stretch limit,
* **field-matched** within a stated FOV cap -- the constraint that killed the
  naive "just drop screen 3" idea (its seeds missed by a median 43.9 deg).

EFL without receipt pairing
---------------------------
Staging ZMX carry `! ATELIER_FTAN_IMH_SANITY_MM` = `EFL * tan(half field)` in
their trailer and the half field in `YFLN`, so `EFL = FTAN_IMH / tan(YFLN_max)`
is readable from the file alone. That matters: the only other route is the
conversion receipt, and `staging-domain-ceiling-2026-07-29.md` records **9 known
receipt-to-ZMX misalignments** across 3 patents, where a receipt lookup returns
the neighbouring embodiment's parameters. `--check-derivation` validates the
formula against the corpus, where `index.json` states EFL independently.

Usage
-----
    uv run python scripts/staging_seed_supply_census.py \
        --census D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl \
        --staging-census D:/atelier-stagec-runs/trace-census-20260728/perfield-staging-census.jsonl \
        --json .planning/evidence/staging-seed-supply-2026-08-02.json
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.engines.zmx_import_prep import decode_zmx_text  # noqa: E402
from scripts.p2_pair_census import (  # noqa: E402
    CASE_INDEX,
    QUARANTINE,
    codev_rms_by_zmx,
    default_seed_quality_limit_um,
    load_provenance,
    load_usable_case_ids,
    normalise_patent_id,
    seed_efl_is_reachable,
)

STAGING_DIR = REPO_ROOT / "data" / "zmx-staging" / "patent-local-replay"
ZMX_DIR = REPO_ROOT / "data" / "zmx"

#: Full-angle degrees. Not tuned: 20 deg is simply the point at which the
#: "drop screen 3" pool stops being field-matched at all (its picks miss by a
#: median 43.9 deg). Every reported number is given at several caps so the
#: reader can see the shape rather than trust one.
DEFAULT_FOV_CAPS: tuple[float | None, ...] = (None, 20.0, 10.0, 5.0)

#: `tan` stops being a usable divisor near 90 deg -- same reasoning, and the same
#: number, as `scripts/image_height_gate.MAX_REFERENCE_HALF_FIELD_DEG`.
MAX_HALF_FIELD_DEG = 85.0

_YFLN = re.compile(r"^\s*YFLN\s+(.*)$")
_FTYP = re.compile(r"^\s*FTYP\s+(\S+)")
_FTAN = re.compile(r"^\s*!\s*ATELIER_FTAN_IMH_SANITY_MM\s+(\S+)")


def read_first_order(path: Path) -> dict[str, float | None]:
    """Half field, and EFL derived from the trailer's own first-order reference."""

    try:
        text, _ = decode_zmx_text(path.read_bytes())
    except (OSError, ValueError, UnicodeError):
        return {}
    half_field: float | None = None
    field_type: int | None = None
    ftan: float | None = None
    for line in text.splitlines():
        match = _YFLN.match(line)
        if match:
            values = []
            for token in match.group(1).split():
                try:
                    values.append(abs(float(token)))
                except ValueError:
                    continue
            half_field = max(values) if values else None
            continue
        match = _FTYP.match(line)
        if match:
            try:
                field_type = int(float(match.group(1)))
            except ValueError:
                field_type = None
            continue
        match = _FTAN.match(line)
        if match:
            try:
                ftan = float(match.group(1))
            except ValueError:
                ftan = None
    if field_type != 0 or not half_field or not ftan:
        return {"half_field_deg": half_field, "efl_mm": None}
    if not 0.0 < half_field < MAX_HALF_FIELD_DEG:
        return {"half_field_deg": half_field, "efl_mm": None}
    tangent = math.tan(math.radians(half_field))
    if tangent <= 1e-9 or not math.isfinite(ftan):
        return {"half_field_deg": half_field, "efl_mm": None}
    return {"half_field_deg": half_field, "efl_mm": ftan / tangent}


def check_derivation(sample: int = 200) -> dict[str, Any]:
    """Validate `EFL = FTAN_IMH / tan(half field)` where EFL is independently known."""

    index = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    ratios: list[float] = []
    for record in index[:sample]:
        path = ZMX_DIR / str(record["source_zmx"])
        if not path.exists():
            continue
        derived = read_first_order(path).get("efl_mm")
        try:
            stated = float(record["efl_mm"])
        except (KeyError, TypeError, ValueError):
            continue
        if derived and stated > 0:
            ratio = derived / stated
            if math.isfinite(ratio):
                ratios.append(ratio)
    ratios.sort()
    if not ratios:
        return {"n": 0}
    return {
        "n": len(ratios),
        "median": statistics.median(ratios),
        "within_1pct": sum(1 for r in ratios if 0.99 <= r <= 1.01),
        "min": ratios[0],
        "max": ratios[-1],
    }


def _patent_of(zmx_name: str) -> str:
    stem = re.sub(r"-e\d+$", "", zmx_name.rsplit(".", 1)[0], flags=re.IGNORECASE)
    return normalise_patent_id(stem)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(census_path: Path, staging_census_path: Path) -> dict[str, Any]:
    limit = default_seed_quality_limit_um()
    provenance = load_provenance()
    quarantine = json.loads(QUARANTINE.read_text(encoding="utf-8"))["pools"]
    staging_defective = set(quarantine.get("data/zmx-staging", {}).get("defective", {}))

    index = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    by_case = {record["case_id"]: record for record in index}
    corpus_rms = codev_rms_by_zmx(census_path)
    staging_rms = codev_rms_by_zmx(staging_census_path)

    # ---- the staging seed pool ----
    from app.core.engines.prescription_identity import fingerprint_zmx

    staging_pool: list[dict[str, Any]] = []
    dropped: collections.Counter[str] = collections.Counter()
    for name, rms in staging_rms.items():
        if name in staging_defective:
            dropped["fidelity_quarantined"] += 1
            continue
        path = STAGING_DIR / name
        if not path.exists():
            dropped["file_missing"] += 1
            continue
        first_order = read_first_order(path)
        assignee = provenance.assignee_of_patent.get(_patent_of(name))
        brand = provenance.brand_of.get(assignee) if assignee else None
        if brand is None:
            dropped["provenance_unknown"] += 1
            continue
        if not first_order.get("efl_mm") or not first_order.get("half_field_deg"):
            dropped["first_order_not_derivable"] += 1
            continue
        try:
            fingerprint = fingerprint_zmx(path)
        except Exception:  # noqa: BLE001 - a file we cannot fingerprint is its own design
            fingerprint = name
        staging_pool.append(
            {
                "zmx": name,
                "patent": _patent_of(name),
                "brand": brand,
                "rms_spot_diameter_um": rms,
                "efl_mm": first_order["efl_mm"],
                "fov_deg": float(first_order["half_field_deg"]) * 2.0,
                "fingerprint": fingerprint,
                "at_or_below_corpus_median": rms <= limit,
            }
        )

    healthy = [row for row in staging_pool if row["at_or_below_corpus_median"]]

    # ---- corpus controls, and the corpus's own seed pool for comparison ----
    in_domain, _ = load_usable_case_ids(census_path)
    two_screen, _ = load_usable_case_ids(census_path, require_in_domain=False)
    controls = [
        case_id
        for case_id in in_domain
        if provenance.brand_of_case(case_id)
        and corpus_rms.get(str(by_case[case_id]["source_zmx"])) is not None
    ]
    corpus_pool = [
        {
            "id": case_id,
            "brand": provenance.brand_of_case(case_id),
            "rms_spot_diameter_um": corpus_rms[str(by_case[case_id]["source_zmx"])],
            "efl_mm": float(by_case[case_id]["efl_mm"]),
            "fov_deg": float(by_case[case_id]["fov_deg"]),
            "fingerprint": case_id,
        }
        for case_id in two_screen
        if provenance.brand_of_case(case_id)
        and corpus_rms.get(str(by_case[case_id]["source_zmx"])) is not None
    ]

    def serve(pool: list[dict[str, Any]], cap: float | None) -> dict[str, Any]:
        served = 0
        bests: list[float] = []
        distinct: list[int] = []
        winners: collections.Counter[str] = collections.Counter()
        for control_id in controls:
            record = by_case[control_id]
            brand = provenance.brand_of_case(control_id)
            efl, fov = float(record["efl_mm"]), float(record["fov_deg"])
            options = [
                row
                for row in pool
                if row.get("id") != control_id
                and row["brand"] not in (None, brand)
                and row["rms_spot_diameter_um"] <= limit
                and seed_efl_is_reachable(float(row["efl_mm"]), efl)
                and (cap is None or abs(float(row["fov_deg"]) - fov) <= cap)
            ]
            distinct.append(len({row["fingerprint"] for row in options}))
            if options:
                served += 1
                best = min(options, key=lambda row: row["rms_spot_diameter_um"])
                bests.append(best["rms_spot_diameter_um"])
                winners[f"{best['brand']} | {best.get('patent') or best.get('id')}"] += 1
        ordered = sorted(distinct)
        return {
            "controls": len(controls),
            "served": served,
            "best_rms_median": statistics.median(bests) if bests else None,
            "distinct_options_median": statistics.median(ordered) if ordered else 0,
            "distinct_options_max": ordered[-1] if ordered else 0,
            "controls_with_zero_options": sum(1 for value in ordered if value == 0),
            "controls_with_one_option": sum(1 for value in ordered if value == 1),
            "lowest_rms_pick_concentration": dict(winners.most_common(5)),
        }

    comparison: dict[str, dict[str, Any]] = {}
    for label, pool in (
        ("corpus seeds only (two-screen)", corpus_pool),
        ("staging seeds only", staging_pool),
        ("corpus + staging", corpus_pool + staging_pool),
    ):
        for cap in DEFAULT_FOV_CAPS:
            key = f"{label} @ {'any' if cap is None else f'{cap:.0f}deg'}"
            comparison[key] = serve(pool, cap)

    by_brand = collections.Counter(row["brand"] for row in healthy)
    fovs = sorted(row["fov_deg"] for row in healthy)

    return {
        "schema": "atelier-staging-seed-supply-v1",
        "inputs": {
            "census_sha256": _sha256(census_path),
            "staging_census_sha256": _sha256(staging_census_path),
            "case_index_sha256": _sha256(CASE_INDEX),
            "quarantine_sha256": _sha256(QUARANTINE),
            "seed_quality_limit_um": limit,
            "fov_caps_deg": [c for c in DEFAULT_FOV_CAPS if c is not None],
        },
        "efl_derivation_check": check_derivation(),
        "staging_pool": {
            "zmx_on_disk": len(list(STAGING_DIR.glob("*.zmx"))),
            "full_field_readings": len(staging_rms),
            "admitted": len(staging_pool),
            "dropped": dict(dropped),
            "at_or_below_corpus_median": len(healthy),
            "healthy_by_brand": dict(by_brand.most_common()),
            "healthy_distinct_prescriptions": len({row["fingerprint"] for row in healthy}),
            "healthy_distinct_patents": len({row["patent"] for row in healthy}),
            "healthy_fov_median": statistics.median(fovs) if fovs else None,
            "healthy_fov_range": [fovs[0], fovs[-1]] if fovs else None,
        },
        "controls": len(controls),
        "comparison": comparison,
    }


def render(result: dict[str, Any]) -> str:
    pool = result["staging_pool"]
    check = result["efl_derivation_check"]
    lines = [
        "staging 池能不能补上异源 seed 的缺口",
        "=" * 72,
        f"  EFL 推导自检（在语料上，EFL 是已知的）  n={check.get('n')} "
        f"中位 {check.get('median', float('nan')):.4f}  ±1% 内 {check.get('within_1pct')}",
        "",
        f"  staging ZMX 在盘                 {pool['zmx_on_disk']}",
        f"  其中有 CODE V 全场读数           {pool['full_field_readings']}",
        f"  过保真度 + 受让人 + 一阶量可导    {pool['admitted']}   丢弃原因 {pool['dropped']}",
        f"  且 ≤ 语料中位                    {pool['at_or_below_corpus_median']}"
        f"（{pool['healthy_distinct_prescriptions']} 个不同处方 / {pool['healthy_distinct_patents']} 件专利）",
        f"  健康件受让人构成                 {pool['healthy_by_brand']}",
        f"  健康件视场                       中位 {pool['healthy_fov_median']}  区间 {pool['healthy_fov_range']}",
        "",
        f"  逐对照能不能拿到「异源 + 可达 + 视场匹配 + 达标」的 seed（对照 {result['controls']} 个）",
    ]
    header = f"    {'seed 池 @ 视场上限':<44}{'served':>10}{'best rms':>10}{'distinct 中位':>14}{'零选项':>8}"
    lines.append(header)
    for key, row in result["comparison"].items():
        best = f"{row['best_rms_median']:.2f}" if row["best_rms_median"] else "-"
        lines.append(
            f"    {key:<44}{row['served']:>4}/{row['controls']:<5}{best:>10}"
            f"{row['distinct_options_median']:>14}{row['controls_with_zero_options']:>8}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--staging-census", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build(args.census, args.staging_census)
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
