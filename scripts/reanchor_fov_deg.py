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
Rewrites ``fov_deg`` to ``2 * theta`` in ``index.json`` and in each per-case JSON
(`load_case_library` reads the per-case files, **not** the index, and re-derives
the scenario from ``fov_deg`` at load time -- so both have to move together or
routing and reporting drift apart).

The edit is textual and touches exactly the one ``"fov_deg": ...`` line in each
file. Re-serialising 442 files of Pydantic output would rewrite every float in
the corpus to chase one field.

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

__all__ = ["ReanchorPlan", "apply_plan", "plan_reanchor", "render_fov"]


def render_fov(value: float) -> str:
    """``.9g`` with a decimal point kept, so the field stays a JSON float."""

    rendered = format(value, _FOV_FORMAT)
    if "." not in rendered and "e" not in rendered and "E" not in rendered:
        rendered += ".0"
    return rendered


@dataclass(frozen=True)
class ReanchorPlan:
    """What would change, computed before anything is written."""

    #: case_id -> new fov_deg
    targets: dict[str, float]
    #: case_id -> old fov_deg (only for cases whose value actually moves)
    changed: dict[str, float]
    #: case_id -> why it could not be anchored
    skipped: dict[str, str]

    @property
    def is_clean(self) -> bool:
        """True when every anchorable case already carries its anchored value."""

        return not self.changed


def plan_reanchor(*, cases_dir: Path = CASES_DIR, zmx_dir: Path = ZMX_DIR) -> ReanchorPlan:
    from app.core.engines.seed_field_rebuild import max_field_angle_deg
    from app.core.engines.zmx_import_prep import decode_zmx_text

    index_path = cases_dir / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    targets: dict[str, float] = {}
    changed: dict[str, float] = {}
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
        anchored = 2.0 * theta
        targets[case_id] = anchored
        current = entry.get("fov_deg")
        # Compared on the *rendered* string, which is what actually lands in the
        # file. A stored 16.8885802 and a freshly doubled 8.4442901 differ in the
        # last binary bit while rendering identically; comparing the doubles
        # would mark such a case dirty forever and make ``--check`` unusable as
        # a gate. Only a case whose written text would differ counts as changed.
        if not isinstance(current, (int, float)) or render_fov(
            float(current)
        ) != render_fov(anchored):
            changed[case_id] = float(current) if isinstance(current, (int, float)) else float("nan")
    return ReanchorPlan(targets=targets, changed=changed, skipped=skipped)


def _rewrite_fov_line(text: str, value: float, *, expected: int) -> str:
    rendered = render_fov(value)
    out: list[str] = []
    hits = 0
    for line in text.split("\n"):
        match = _FOV_LINE.match(line.rstrip("\r"))
        if match is None:
            out.append(line)
            continue
        carriage = "\r" if line.endswith("\r") else ""
        out.append(f"{match.group('lead')}{rendered}{match.group('tail').rstrip()}{carriage}")
        hits += 1
    if hits != expected:
        raise ValueError(f"expected {expected} fov_deg line(s), found {hits}")
    return "\n".join(out)


def apply_plan(plan: ReanchorPlan, *, cases_dir: Path = CASES_DIR) -> dict[str, int]:
    """Write the plan. Per-case files first, then the index."""

    written = 0
    for case_id in plan.changed:
        value = plan.targets[case_id]
        case_path = cases_dir / f"{case_id}.json"
        if not case_path.is_file():
            continue
        text = case_path.read_text(encoding="utf-8")
        case_path.write_text(_rewrite_fov_line(text, value, expected=1), encoding="utf-8")
        written += 1

    index_path = cases_dir / "index.json"
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    index_text = index_path.read_text(encoding="utf-8")
    lines = index_text.split("\n")
    order = [
        str(entry.get("case_id", ""))
        for entry in entries
    ]
    position = 0
    rebuilt: list[str] = []
    for line in lines:
        match = _FOV_LINE.match(line.rstrip("\r"))
        if match is None:
            rebuilt.append(line)
            continue
        case_id = order[position] if position < len(order) else ""
        position += 1
        if case_id not in plan.changed:
            rebuilt.append(line)
            continue
        carriage = "\r" if line.endswith("\r") else ""
        rendered = render_fov(plan.targets[case_id])
        rebuilt.append(
            f"{match.group('lead')}{rendered}{match.group('tail').rstrip()}{carriage}"
        )
    if position != len(order):
        raise ValueError(f"index.json has {position} fov_deg rows for {len(order)} cases")
    index_path.write_text("\n".join(rebuilt), encoding="utf-8")
    return {"per_case_written": written, "index_rows": position}


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
            print(f"  {case_id:<28} {old} -> {render_fov(plan.targets[case_id])}")
        return 1
    counts = apply_plan(plan)
    print(f"written: {counts}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
