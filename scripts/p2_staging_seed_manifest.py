"""Screen `data/zmx-staging` for designs sound enough to be P2 **seeds**.

Why this exists. The P2 cross-source par rate is 0, and the measured reason is
not the comparator -- it is the seed supply. In the 2026-08-02 round, 48 of 59
trials optimised from one seed whose own CODE V reading is 101 um, against
controls at 2-11 um. `data/zmx-staging/patent-local-replay` holds 613 git-tracked
ZMX with zero filename overlap with `data/zmx`, produced by this repo's own
patent->ZMX converter, and nothing consumes them because seed selection reads the
case index.

Why a seed manifest and not a corpus promotion. Both were built and measured
(2026-08-03). Putting the screened designs into `app/data/optical_cases` gives
137 trials instead of 59, but 78 of those trials are controls we minted
ourselves this week, and it moves 97 of 445 product routing decisions. Admitting
them as **seeds only** gives the entire quality gain with none of that:

    policy          trials  seed pool basis          selected-seed CODE V p50
    excluded            59  quality 6, fallback 53   101.27 um
    seeds only          59  quality 55, fallback 4     4.54 um
    full (corpus)      137  quality 124, fallback 13   4.54 um

Under `seeds only` the control set is bit-identical to the pre-change baseline
(verified by set equality, zero in either direction), so the par rate stays
comparable against an unchanged denominator -- which is the whole point of a
北极星 main indicator.

What the screens test is **soundness**, not suitability:

  1. a full-field CODE V reading exists            (a file no engine can read
                                                     whole is not a lens we know
                                                     anything about)
  2. not fidelity-quarantined                      (`corpus_fidelity_audit`)
  3. assignee provenance is known                  (cross-source pairing needs it)
  4. first order derivable + a receipt EFL         (the intake ground truth)
  5. the declared image height is plausible        (`image_height_gate`)
  6. its prescription is not already in `data/zmx` (a patent continuation
                                                    republishes one embodiment
                                                    under a new number: measured
                                                    2026-08-03, 30 of the 187
                                                    that pass 1-5 are byte-identical
                                                    to a corpus design. They add no
                                                    supply -- the design is already
                                                    a corpus seed -- and they carry
                                                    a self-pairing risk, because a
                                                    "cross-source" trial whose seed
                                                    IS its control is the most
                                                    flattering possible reading)

Suitability -- is this the right lens to start *this* design from -- belongs to
seed selection, which already applies the +25% reachability test and the quality
limit. An "EFL inside the corpus band" gate was drafted and dropped: it is
circular (the corpus defines the band it screens against) and the corpus's own
EFL floor is 0.438 mm, so the row it was meant to catch was never out of range.

Read-only unless `--emit` is passed.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import statistics
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.simplefilter("ignore")

from app.core.engines.prescription_identity import fingerprint_zmx  # noqa: E402
from app.core.engines.zmx_import_prep import decode_zmx_text  # noqa: E402
from scripts.image_height_gate import (  # noqa: E402
    ImageHeightVerdict,
    first_order_image_height_mm,
    screen_image_height,
)
from scripts.p2_pair_census import (  # noqa: E402
    CASE_INDEX,
    QUARANTINE,
    codev_rms_by_zmx,
    load_provenance,
    normalise_patent_id,
)
from scripts.staging_seed_supply_census import (  # noqa: E402
    STAGING_DIR,
    read_first_order,
    receipt_efl_by_zmx,
)

MANIFEST_PATH = ROOT / "app" / "data" / "p2_staging_seed_manifest.json"
MANIFEST_SCHEMA = "atelier.p2_staging_seed_manifest/v1"

_REAL_IMH = re.compile(r"(?m)^\s*!\s*ATELIER_REAL_IMH_MM\s+(\S+)")
_FNUM = re.compile(r"(?m)^\s*FNUM\s+(\S+)")
_GLAS = re.compile(r"(?m)^\s*GLAS\s+(.*)$")


def _looks_like_index(token: str) -> bool:
    try:
        value = float(token)
    except ValueError:
        return False
    return 1.2 <= value <= 4.0


def count_glass_elements(text: str) -> int:
    """Element count, same heuristic `e2_intake` used for every existing batch.

    Deliberately the same heuristic and not a better one: `n_pieces` is compared
    across corpus rows, so a row counted by a different rule would not be
    comparable with the 425 already there.
    """

    count = 0
    for body in _GLAS.findall(text):
        tokens = body.split()
        named = bool(tokens) and tokens[0] not in ("___BLANK", "0", "MIRROR")
        has_index = any(_looks_like_index(t) for t in tokens[1:5])
        if named or has_index:
            count += 1
    return count


def _corpus_fingerprints() -> set[str]:
    """Every prescription already reachable as a corpus seed.

    Filename overlap between the two pools is zero, which says nothing about
    design identity -- `prescription_identity` exists because 442 corpus files
    already carry only 354 distinct prescriptions.
    """

    index = json.loads(CASE_INDEX.read_text(encoding="utf-8"))
    out: set[str] = set()
    for record in index:
        fingerprint = fingerprint_zmx(ROOT / "data" / "zmx" / str(record["source_zmx"]))
        if fingerprint is not None:
            out.add(fingerprint)
    return out


def _patent_of(name: str) -> str:
    return normalise_patent_id(re.sub(r"-e\d+$", "", name.rsplit(".", 1)[0], flags=re.I))


def screen(staging_census: Path) -> tuple[list[dict], collections.Counter]:
    """Gates 1-5. Returns the survivors and a drop tally by gate."""

    provenance = load_provenance()
    rms = codev_rms_by_zmx(staging_census)
    quarantined = set(
        json.loads(QUARANTINE.read_text(encoding="utf-8"))["pools"]
        .get("data/zmx-staging", {})
        .get("defective", {})
    )
    receipts, _ = receipt_efl_by_zmx()
    corpus_fingerprints = _corpus_fingerprints()

    drops: collections.Counter[str] = collections.Counter()
    kept: list[dict] = []
    for path in sorted(p for p in STAGING_DIR.iterdir() if p.suffix.lower() == ".zmx"):
        name = path.name
        codev_rms = rms.get(name)
        if codev_rms is None:
            drops["1_no_full_field_codev_reading"] += 1
            continue
        if name in quarantined:
            drops["2_fidelity_quarantined"] += 1
            continue
        assignee = provenance.assignee_of_patent.get(_patent_of(name))
        brand = provenance.brand_of.get(assignee or "")
        if brand is None:
            drops["3_provenance_unknown"] += 1
            continue
        efl_mm = receipts.get(name)
        half_field_deg = read_first_order(path).get("half_field_deg")
        if not efl_mm or not half_field_deg:
            drops["4_first_order_unavailable"] += 1
            continue
        text, _ = decode_zmx_text(path.read_bytes())
        real = _REAL_IMH.search(text)
        if real is None:
            drops["5_no_real_image_height"] += 1
            continue
        verdict, ratio = screen_image_height(
            float(real.group(1)), first_order_image_height_mm(efl_mm, half_field_deg)
        )
        if verdict is not ImageHeightVerdict.PLAUSIBLE:
            drops[f"5_image_height_{verdict}"] += 1
            continue
        if fingerprint_zmx(path) in corpus_fingerprints:
            drops["6_prescription_already_in_corpus"] += 1
            continue
        fnum = _FNUM.search(text)
        kept.append(
            {
                "zmx": name,
                "patent": _patent_of(name),
                "assignee": assignee,
                "brand": brand,
                "codev_rms_um": codev_rms,
                "efl_mm": efl_mm,
                "fov_deg": half_field_deg * 2.0,
                "f_number": float(fnum.group(1)) if fnum else None,
                "image_height_mm": float(real.group(1)),
                "image_height_ratio": ratio,
                "glass_elements": count_glass_elements(text),
            }
        )
    return kept, drops


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staging-census",
        type=Path,
        default=Path("D:/atelier-stagec-runs/trace-census-20260728/perfield-staging-census.jsonl"),
        help="per-field CODE V census over the staging pool (screen 1)",
    )
    parser.add_argument("--emit", action="store_true", help="write the seed manifest")
    args = parser.parse_args()

    kept, drops = screen(args.staging_census)
    print("drops by screen:")
    for key, count in sorted(drops.items()):
        print(f"  {key:<38} {count}")
    print(f"\nADMISSIBLE AS SEEDS (screens 1-6): {len(kept)}")

    by_brand = collections.Counter(row["brand"] for row in kept)
    print(f"  brands: {dict(by_brand.most_common())}")
    non_largan = [r for r in kept if r["brand"] != "LARGAN DIGITAL CO., LTD."]
    print(
        f"  non-LARGAN: {len(non_largan)} rows across "
        f"{len({r['patent'] for r in non_largan})} patents"
    )
    values = sorted(r["codev_rms_um"] for r in kept)
    print(
        f"  CODE V full-field RMS spot diameter: min {values[0]:.2f} "
        f"p50 {statistics.median(values):.2f} max {values[-1]:.2f} um"
    )

    if not args.emit:
        print("\n(dry run -- pass --emit to write the manifest)")
        return 0

    payload = {
        "schema": MANIFEST_SCHEMA,
        "pool": "data/zmx-staging/patent-local-replay",
        "screens": [
            "full-field CODE V reading exists",
            "not fidelity-quarantined",
            "assignee provenance known",
            "first order derivable and a receipt EFL exists",
            "declared image height plausible (image_height_gate)",
            "prescription not already present in data/zmx",
        ],
        "role": (
            "seed only -- these designs are never admitted as P2 controls, so the "
            "control set and therefore the par-rate denominator are unchanged"
        ),
        "census": {
            "path": args.staging_census.name,
            "sha256": hashlib.sha256(args.staging_census.read_bytes()).hexdigest(),
        },
        "n": len(kept),
        "seeds": kept,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {MANIFEST_PATH} ({len(kept)} seeds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
