"""Is ``index.json``'s ``fov_deg`` one quantity, or two wearing one name?

`app/core/optical_sample.py` documents the field as "Nominal full FOV from the
manifest" and `app/core/lens_system.py` repeats it ("`fov_deg` is the nominal
full field angle") before using it to classify every case into a scenario. This
script checks that claim against the only runtime truth available -- the field
angle written into each case's own ZMX, which is what CODE V actually traces.

Method
------
For every case with an angular (``FTYP 0``) ZMX:

* ``theta`` = the outermost ``YFLN`` value, i.e. the half field angle as built.
* Classify ``fov_deg / theta``: ~1 means the manifest stored a **half** angle,
  ~2 means it stored a **full** FOV.
* Independently sanity-check that ``theta`` really is the half angle, using the
  case's own declared image height: a rectilinear lens puts the outermost field
  at ``EFL * tan(theta)``. If ``theta`` were double the true half angle, this
  ratio would sit near 0.5, not near 1.

Nothing here mutates data. It answers "which convention is each row in", and the
image-height check answers "which convention is *correct*", so a migration can be
argued from measurement instead of from the field's name.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASE_INDEX = ROOT / "app" / "data" / "optical_cases" / "index.json"
ZMX_DIR = ROOT / "data" / "zmx"

#: ``fov_deg / theta`` within this of 1.0 (or 2.0) is that convention. The two
#: populations are separated by a factor of two, so any tolerance far below 0.5
#: gives the same partition; this one is tight enough that a row landing in
#: neither bucket is reported as ``other`` rather than forced into one.
RATIO_TOLERANCE = 0.05


@dataclass(frozen=True)
class CaseFovRow:
    case_id: str
    scenario: str
    fov_deg: float
    zmx_half_angle_deg: float
    ratio: float
    convention: str
    image_height_mm: float | None
    efl_mm: float | None
    #: declared image height / (EFL * tan(theta)); ~1 confirms theta is the half angle.
    rectilinear_consistency: float | None


def _convention(ratio: float) -> str:
    if abs(ratio - 1.0) <= RATIO_TOLERANCE:
        return "half"
    if abs(ratio - 2.0) <= 2 * RATIO_TOLERANCE:
        return "full"
    return "other"


def census(
    *, case_index: Path = CASE_INDEX, zmx_dir: Path = ZMX_DIR
) -> tuple[list[CaseFovRow], dict[str, object]]:
    from app.core.engines.seed_field_rebuild import max_field_angle_deg
    from app.core.engines.zmx_import_prep import decode_zmx_text

    cases = json.loads(case_index.read_text(encoding="utf-8"))
    rows: list[CaseFovRow] = []
    skipped: Counter[str] = Counter()

    for case in cases:
        zmx_path = zmx_dir / str(case.get("source_zmx", ""))
        if not zmx_path.is_file():
            skipped["zmx_missing"] += 1
            continue
        theta = max_field_angle_deg(decode_zmx_text(zmx_path.read_bytes())[0])
        if theta is None:
            # FTYP 3 states real image heights; there is no angle to compare.
            skipped["zmx_not_angular"] += 1
            continue
        fov = case.get("fov_deg")
        if not isinstance(fov, (int, float)) or not math.isfinite(fov) or fov <= 0:
            skipped["fov_deg_unusable"] += 1
            continue
        efl = case.get("efl_mm")
        imh = case.get("image_height_mm")
        consistency: float | None = None
        if isinstance(efl, (int, float)) and isinstance(imh, (int, float)) and efl > 0:
            radians = math.radians(theta)
            if radians < math.radians(89.0):
                reference = efl * math.tan(radians)
                consistency = imh / reference if reference > 0 else None
        ratio = fov / theta
        rows.append(
            CaseFovRow(
                case_id=str(case.get("case_id", "")),
                scenario=str(case.get("scenario", "")),
                fov_deg=float(fov),
                zmx_half_angle_deg=theta,
                ratio=ratio,
                convention=_convention(ratio),
                image_height_mm=float(imh) if isinstance(imh, (int, float)) else None,
                efl_mm=float(efl) if isinstance(efl, (int, float)) else None,
                rectilinear_consistency=consistency,
            )
        )

    conventions = Counter(row.convention for row in rows)
    summary: dict[str, object] = {
        "cases_in_index": len(cases),
        "cases_measured": len(rows),
        "skipped": dict(skipped),
        "conventions": dict(conventions),
        "mixed": len([c for c in conventions if c in {"half", "full"}]) > 1,
    }
    for convention in ("half", "full", "other"):
        group = [r for r in rows if r.convention == convention]
        checks = [
            r.rectilinear_consistency for r in group if r.rectilinear_consistency is not None
        ]
        summary[f"{convention}_n"] = len(group)
        summary[f"{convention}_rectilinear_consistency_median"] = (
            round(statistics.median(checks), 4) if checks else None
        )
    return rows, summary


def render(summary: dict[str, object]) -> str:
    lines = [
        "fov_deg unit census (manifest vs the ZMX actually traced)",
        "=" * 58,
        f"cases in index            {summary['cases_in_index']}",
        f"measured                  {summary['cases_measured']}",
        f"skipped                   {summary['skipped']}",
        "convention (fov_deg / ZMX half angle):",
    ]
    for convention, count in sorted(summary["conventions"].items()):  # type: ignore[union-attr]
        median = summary.get(f"{convention}_rectilinear_consistency_median")
        lines.append(
            f"  {convention:<8} {count:>4}   declared imh / (EFL*tan θ) median "
            + (f"{median}" if median is not None else "n/a")
        )
    lines.append(
        "MIXED UNITS -- fov_deg is not one quantity"
        if summary.get("mixed")
        else "single convention throughout"
    )
    lines.append(
        "(a median near 1.0 in *both* groups means θ is the true half angle in both,"
    )
    lines.append(" so the disagreement is in the manifest, not in the ZMX)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="write the per-case rows here")
    args = parser.parse_args(argv)
    rows, summary = census()
    if args.json:
        args.json.write_text(
            json.dumps(
                {"summary": summary, "rows": [asdict(r) for r in rows]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(render(summary))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
