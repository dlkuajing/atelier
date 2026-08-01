"""Re-anchor every case's ``fov_deg`` to the ZMX that is actually traced.

Why
---
`.planning/evidence/fov-unit-mix-2026-07-29.md` measured the corpus against its
own ZMX files: 253 cases store a **half** field angle in ``fov_deg`` and 172
store a **full** FOV, with no third ratio. Both `app/core/optical_sample.py`
("Nominal full FOV from the manifest") and `app/core/lens_system.py` ("nominal
full field angle") document one convention, so at most one group can be right.
An independent physical check settles which: the declared image height sits at
``EFL * tan(theta)`` in **both** groups (medians 0.9957 / 1.0004), so ``theta``
-- the outermost ``YFLN`` of each case's own ZMX -- is the true half angle
everywhere and the manifest is what disagrees with itself.

That column is not decorative. ``rank_seeds`` weights ``fov`` at 0.46, the
largest of any dimension (``efl`` gets 0.20), and ``_classify_scenario`` takes it
as its only field input while ``cases_for_scenario`` picks the seed pool by the
resulting bucket.

What this does
--------------
Rewrites ``fov_deg`` to ``2 * theta`` **and the ``scenario`` label that
``_classify_scenario`` derives from it**, in ``index.json`` and in every per-case
JSON.

Both files, because `load_case_library` reads the per-case files, **not** the
index. Both fields, because moving the FOV alone leaves the corpus
self-contradictory: `load_case_library` re-derives the scenario at load time and
would disagree with the persisted string, while `p2_pair_census`'s in-domain
screen reads the *persisted* label and would check the new FOV against the old
bucket's bounds. Measured: re-anchoring the FOV alone puts 104/442 labels at odds
with the classifier, up from 2.

The edit is textual and touches exactly one ``"fov_deg"`` line and one
``"scenario"`` line per case. Re-serialising 442 files of Pydantic output would
rewrite every float in the corpus to chase two fields.

Fail-closed
-----------
A case whose ZMX is missing, or whose ZMX is not angular (``FTYP 3`` states real
image heights in millimetres, not degrees), has no angle to anchor to and is
**left untouched and reported**. Guessing a value for it would put an invented
number where a measured one belongs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASES_DIR = ROOT / "app" / "data" / "optical_cases"
ZMX_DIR = ROOT / "data" / "zmx"

#: Written with enough digits to round-trip the doubled readout without adding
#: noise; the source values carry at most 9 significant figures. Doubling can
#: land on a binary artefact (0.1 + 0.1 style), which ``.9g`` rounds away.
_FOV_FORMAT = ".9g"
_FOV_LINE = re.compile(r'^(?P<lead>\s*"fov_deg"\s*:\s*)(?P<value>-?[\d.eE+]+)(?P<tail>,?\s*)$')
_SCENARIO_LINE = re.compile(r'^(?P<lead>\s*"scenario"\s*:\s*)"(?P<value>[^"]*)"(?P<tail>,?\s*)$')

__all__ = ["CaseAnchor", "ReanchorPlan", "apply_plan", "plan_reanchor", "render_fov"]


def render_fov(value: float) -> str:
    """``.9g`` with a decimal point kept, so the field stays a JSON float."""

    rendered = format(value, _FOV_FORMAT)
    if "." not in rendered and "e" not in rendered and "E" not in rendered:
        rendered += ".0"
    return rendered


@dataclass(frozen=True)
class CaseAnchor:
    """The two fields that have to move together."""

    fov_deg: float
    scenario: str


@dataclass(frozen=True)
class ReanchorPlan:
    """What would change, computed before anything is written."""

    #: case_id -> anchored (fov_deg, scenario)
    targets: dict[str, CaseAnchor]
    #: case_id -> the stored values, for cases whose text would actually move
    changed: dict[str, CaseAnchor]
    #: case_id -> why it could not be anchored
    skipped: dict[str, str]

    @property
    def is_clean(self) -> bool:
        """True when every anchorable case already carries its anchored values."""

        return not self.changed


def plan_reanchor(*, cases_dir: Path = CASES_DIR, zmx_dir: Path = ZMX_DIR) -> ReanchorPlan:
    from app.core.engines.seed_field_rebuild import max_field_angle_deg
    from app.core.engines.zmx_import_prep import decode_zmx_text
    from app.core.lens_system import _classify_scenario

    index_path = cases_dir / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    targets: dict[str, CaseAnchor] = {}
    changed: dict[str, CaseAnchor] = {}
    skipped: dict[str, str] = {}
    for entry in entries:
        case_id = str(entry.get("case_id", ""))
        zmx_path = zmx_dir / str(entry.get("source_zmx", ""))
        if not zmx_path.is_file():
            skipped[case_id] = "source ZMX is missing"
            continue
        theta = max_field_angle_deg(decode_zmx_text(zmx_path.read_bytes())[0])
        if theta is None:
            skipped[case_id] = "ZMX is not angular (FTYP 3 states millimetres)"
            continue
        efl = entry.get("efl_mm")
        if not isinstance(efl, (int, float)):
            skipped[case_id] = "index row has no usable efl_mm to classify with"
            continue
        anchored = 2.0 * theta
        scenario = _classify_scenario(anchored, float(efl))
        anchor = CaseAnchor(
            fov_deg=anchored,
            scenario=scenario.value if hasattr(scenario, "value") else str(scenario),
        )
        targets[case_id] = anchor
        current_fov = entry.get("fov_deg")
        current_scenario = str(entry.get("scenario", ""))
        # ``fov_deg`` is compared on the *rendered* string, which is what actually
        # lands in the file. A stored 16.8885802 and a freshly doubled 8.4442901
        # differ in the last binary bit while rendering identically; comparing the
        # doubles would mark such a case dirty forever and make ``--check``
        # unusable as a gate.
        fov_moves = not isinstance(current_fov, (int, float)) or render_fov(
            float(current_fov)
        ) != render_fov(anchored)
        if fov_moves or current_scenario != anchor.scenario:
            changed[case_id] = CaseAnchor(
                fov_deg=(
                    float(current_fov) if isinstance(current_fov, (int, float)) else float("nan")
                ),
                scenario=current_scenario,
            )
    return ReanchorPlan(targets=targets, changed=changed, skipped=skipped)


def _scenario_row(match: re.Match[str], scenario: str, carriage: str) -> str:
    quoted = '"' + scenario + '"'
    return f"{match.group('lead')}{quoted}{match.group('tail').rstrip()}{carriage}"


def _fov_row(match: re.Match[str], value: float, carriage: str) -> str:
    return f"{match.group('lead')}{render_fov(value)}{match.group('tail').rstrip()}{carriage}"


def _rewrite_case_text(text: str, anchor: CaseAnchor) -> str:
    """Rewrite the one ``fov_deg`` line and the one ``scenario`` line, nothing else."""

    out: list[str] = []
    hits = {"fov_deg": 0, "scenario": 0}
    for line in text.split("\n"):
        bare = line.rstrip("\r")
        carriage = "\r" if line.endswith("\r") else ""
        fov_match = _FOV_LINE.match(bare)
        if fov_match is not None:
            out.append(_fov_row(fov_match, anchor.fov_deg, carriage))
            hits["fov_deg"] += 1
            continue
        scenario_match = _SCENARIO_LINE.match(bare)
        if scenario_match is not None:
            out.append(_scenario_row(scenario_match, anchor.scenario, carriage))
            hits["scenario"] += 1
            continue
        out.append(line)
    for field, count in hits.items():
        if count != 1:
            raise ValueError(f"expected exactly one {field} line, found {count}")
    return "\n".join(out)


def apply_plan(plan: ReanchorPlan, *, cases_dir: Path = CASES_DIR) -> dict[str, int]:
    """Write the plan. Per-case files first, then the index."""

    written = 0
    for case_id in plan.changed:
        case_path = cases_dir / f"{case_id}.json"
        if not case_path.is_file():
            continue
        text = case_path.read_text(encoding="utf-8")
        case_path.write_text(_rewrite_case_text(text, plan.targets[case_id]), encoding="utf-8")
        written += 1

    index_path = cases_dir / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    index_text = index_path.read_text(encoding="utf-8")
    order = [str(entry.get("case_id", "")) for entry in entries]
    # index.json lists "scenario" before "fov_deg" inside each object, so the two
    # fields get their own cursors rather than sharing one position counter.
    cursors = {"scenario": 0, "fov_deg": 0}
    rebuilt: list[str] = []
    for line in index_text.split("\n"):
        bare = line.rstrip("\r")
        carriage = "\r" if line.endswith("\r") else ""
        fov_match = _FOV_LINE.match(bare)
        scenario_match = None if fov_match is not None else _SCENARIO_LINE.match(bare)
        if fov_match is None and scenario_match is None:
            rebuilt.append(line)
            continue
        field = "fov_deg" if fov_match is not None else "scenario"
        case_id = order[cursors[field]] if cursors[field] < len(order) else ""
        cursors[field] += 1
        if case_id not in plan.changed:
            rebuilt.append(line)
            continue
        anchor = plan.targets[case_id]
        if fov_match is not None:
            rebuilt.append(_fov_row(fov_match, anchor.fov_deg, carriage))
        else:
            assert scenario_match is not None
            rebuilt.append(_scenario_row(scenario_match, anchor.scenario, carriage))
    for field, count in cursors.items():
        if count != len(order):
            raise ValueError(f"index.json has {count} {field} rows for {len(order)} cases")
    index_path.write_text("\n".join(rebuilt), encoding="utf-8")
    return {"per_case_written": written, "index_rows": cursors["fov_deg"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero if any case is not anchored; writes nothing",
    )
    args = parser.parse_args(argv)
    plan = plan_reanchor()
    print(f"anchorable cases      {len(plan.targets)}")
    print(f"already anchored      {len(plan.targets) - len(plan.changed)}")
    print(f"would change          {len(plan.changed)}")
    print(f"skipped (no angle)    {len(plan.skipped)}")
    if args.check:
        if plan.is_clean:
            print("corpus is anchored to its own ZMX field angles")
            return 0
        for case_id, old in sorted(plan.changed.items())[:10]:
            new = plan.targets[case_id]
            print(
                f"  {case_id:<28} {old.fov_deg} {old.scenario}"
                f" -> {render_fov(new.fov_deg)} {new.scenario}"
            )
        return 1
    counts = apply_plan(plan)
    print(f"written: {counts}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
