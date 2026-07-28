"""Audit the ZMX corpus for prescriptions that cannot be the design they claim.

Motivation (north star P2). The corpus is the *control group* for the
异源打平率 measurement: a candidate is judged by whether it is no worse than the
patent design it is compared against. A seed whose prescription silently lost
data is therefore not merely unusable -- it biases the headline metric
**upward**, because a lens stripped of its aspheric terms is easier to beat.

The existing traceability census cannot catch this class. A conic-only surface
is smooth and well behaved, so a corrupted seed traces at least as easily as an
intact one (measured: fidelity-defective seeds trace *no worse* than clean ones
in both pools). Trace health and prescription fidelity are independent axes and
must be measured separately.

Two families of finding, kept apart because they carry different confidence:

``hard``
    Physically impossible for any lens in air, so the value is self-evidently
    wrong without consulting the patent.

    ``fno_below_physical_limit``
        Image-space F/# < 0.5 is NA > 1.0 in air. Nothing is faster.
    ``angular_field_at_or_beyond_90deg``
        With an angular field type the field is a half-angle whose tangent sets
        the image height; at 90 deg it diverges and beyond it changes sign. A
        rectilinear angular field can never reach 90 deg. (Typically the patent
        quoted a *full* field of view and it was recorded as a half-angle --
        note that the same mistake below 90 deg stays invisible to this check.)

``fidelity``
    Not impossible, but the file is not the design it claims to be.

    ``aspheric_surface_without_terms``
        A surface typed EVENASPH/XASPHERE whose polynomial coefficients are all
        zero. Verified against retained sources for the staging pool: for
        US-12216248-B2 the patent publishes A4..A20 for S1-S6 while the seed
        carries only the conic constant.

Field-type note: seeds written by the patent pipeline use an angular field
type, while the 17 hand-built real designs use a paraxial-image-height field
type, so ``angular_field_at_or_beyond_90deg`` does not apply to them by
construction -- that is a real exemption, not a silent pass.

Usage::

    uv run python scripts/corpus_fidelity_audit.py
    uv run python scripts/corpus_fidelity_audit.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Pools of ZMX assets, in the order they are reported. ``data/zmx`` is the
#: formal routable corpus; the staging pool is raw material that has not been
#: promoted (its ledger is fail-closed), so the two are never summed silently.
DEFAULT_POOLS: tuple[tuple[str, Path], ...] = (
    ("data/zmx", ROOT / "data" / "zmx"),
    ("data/zmx-staging", ROOT / "data" / "zmx-staging" / "patent-local-replay"),
)

#: f/0.5 is NA 1.0 in air; a smaller image-space F/# is not a slow lens, it is
#: an impossible one.
MIN_PHYSICAL_F_NUMBER = 0.5

#: Angular field type identifier in the ZMX ``FTYP`` record.
FTYP_ANGLE = 0

#: Aspheric surface types whose polynomial terms this audit inspects.
ASPHERIC_SURFACE_TYPES = frozenset({"EVENASPH", "XASPHERE"})

#: ``XDAT`` slots 1-3 carry control words (max order, term type, normalisation)
#: rather than coefficients; only slot 4 onwards holds polynomial terms.
XDAT_CONTROL_SLOTS = 3

_NUMBER = r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?"
_FNUM_RE = re.compile(rf"^FNUM\s+({_NUMBER})", re.MULTILINE)
_ENPD_RE = re.compile(rf"^ENPD\s+({_NUMBER})", re.MULTILINE)
_FTYP_RE = re.compile(r"^FTYP\s+(\d+)", re.MULTILINE)
_YFLN_RE = re.compile(r"^YFLN\s+(.+)$", re.MULTILINE)
_SURF_SPLIT_RE = re.compile(r"^SURF\s+\d+\s*$", re.MULTILINE)
_TYPE_RE = re.compile(r"^\s*TYPE\s+(\S+)", re.MULTILINE)
_PARM_RE = re.compile(rf"^\s*PARM\s+\d+\s+({_NUMBER})\s*$", re.MULTILINE)
_XDAT_RE = re.compile(rf"^\s*XDAT\s+\d+\s+({_NUMBER})", re.MULTILINE)


class CorpusFidelityError(ValueError):
    """Raised when a ZMX asset cannot be read well enough to audit."""


@dataclass(frozen=True)
class SeedAudit:
    """One ZMX asset's audit result."""

    name: str
    pool: str
    f_number: float | None
    field_type: int | None
    max_field: float | None
    aspheric_surfaces: int
    aspheric_surfaces_without_terms: int
    hard: tuple[str, ...] = ()
    fidelity: tuple[str, ...] = ()

    @property
    def is_clean(self) -> bool:
        return not self.hard and not self.fidelity


@dataclass
class PoolAudit:
    """Aggregate for one pool. Every count is reported against ``total``."""

    pool: str
    root: str
    total: int
    seeds: list[SeedAudit] = field(default_factory=list)

    def with_hard(self) -> list[SeedAudit]:
        return [s for s in self.seeds if s.hard]

    def with_fidelity(self) -> list[SeedAudit]:
        return [s for s in self.seeds if s.fidelity]

    def defective(self) -> list[SeedAudit]:
        return [s for s in self.seeds if not s.is_clean]

    def reason_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for seed in self.seeds:
            for reason in (*seed.hard, *seed.fidelity):
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))


def read_zmx_text(path: Path) -> str:
    """Decode a ZMX asset.

    Zemax writes native files as UTF-16 with a BOM while the patent pipeline
    writes ASCII. Reading everything as UTF-8 makes native files parse as if
    every record were missing, which reads as a corpus-wide defect rather than
    as a decoding mistake -- so the BOM is honoured explicitly.
    """
    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16-le", errors="replace")
    if raw[:2] == b"\xfe\xff":
        return raw.decode("utf-16-be", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _surface_blocks(text: str) -> Iterator[str]:
    yield from _SURF_SPLIT_RE.split(text)[1:]


def _aspheric_term_values(block: str) -> list[float]:
    values = [float(match) for match in _PARM_RE.findall(block)]
    xdat = [float(match) for match in _XDAT_RE.findall(block)]
    values.extend(xdat[XDAT_CONTROL_SLOTS:])
    return values


def audit_seed(path: Path, pool: str) -> SeedAudit:
    """Audit a single ZMX asset."""
    text = read_zmx_text(path).replace("\r\n", "\n")

    f_number_match = _FNUM_RE.search(text)
    f_number = float(f_number_match.group(1)) if f_number_match else None
    field_type_match = _FTYP_RE.search(text)
    field_type = int(field_type_match.group(1)) if field_type_match else None
    yfln_match = _YFLN_RE.search(text)
    fields = [float(value) for value in yfln_match.group(1).split()] if yfln_match else []
    max_field = max((abs(value) for value in fields), default=None)

    if f_number is None and not _ENPD_RE.search(text):
        raise CorpusFidelityError(f"{path.name}: no FNUM and no ENPD aperture record")
    if max_field is None:
        raise CorpusFidelityError(f"{path.name}: no YFLN field record")

    aspheric = 0
    aspheric_empty = 0
    for block in _surface_blocks(text):
        type_match = _TYPE_RE.search(block)
        if type_match is None or type_match.group(1) not in ASPHERIC_SURFACE_TYPES:
            continue
        aspheric += 1
        if not any(value != 0.0 for value in _aspheric_term_values(block)):
            aspheric_empty += 1

    hard: list[str] = []
    if f_number is not None and f_number < MIN_PHYSICAL_F_NUMBER:
        hard.append("fno_below_physical_limit")
    if field_type == FTYP_ANGLE and max_field >= 90.0:
        hard.append("angular_field_at_or_beyond_90deg")

    fidelity: list[str] = []
    if aspheric_empty:
        fidelity.append("aspheric_surface_without_terms")

    return SeedAudit(
        name=path.name,
        pool=pool,
        f_number=f_number,
        field_type=field_type,
        max_field=max_field,
        aspheric_surfaces=aspheric,
        aspheric_surfaces_without_terms=aspheric_empty,
        hard=tuple(hard),
        fidelity=tuple(fidelity),
    )


def audit_pool(pool: str, root: Path) -> PoolAudit:
    """Audit every ZMX asset in one pool.

    Matching is case-insensitive on purpose: ``data/zmx`` holds 5 assets with an
    upper-case ``.ZMX`` suffix, and a case-sensitive glob silently reports 437
    where the pool is 442.
    """
    if not root.is_dir():
        raise CorpusFidelityError(f"pool directory does not exist: {root}")
    paths = sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".zmx")
    audit = PoolAudit(pool=pool, root=str(root), total=len(paths))
    audit.seeds = [audit_seed(path, pool) for path in paths]
    return audit


def audit_corpus(pools: Iterable[tuple[str, Path]] = DEFAULT_POOLS) -> list[PoolAudit]:
    return [audit_pool(pool, root) for pool, root in pools]


def _format_pool(audit: PoolAudit) -> list[str]:
    total = audit.total
    lines = [
        f"POOL {audit.pool}  ({audit.root})",
        f"  assets                              {total}",
    ]
    if not total:
        return lines

    def line(label: str, count: int) -> str:
        return f"  {label:<34}{count:>5} / {total}  ({100 * count / total:.1f}%)"

    lines.append(line("physically impossible (hard)", len(audit.with_hard())))
    lines.append(line("prescription fidelity defect", len(audit.with_fidelity())))
    lines.append(line("defective by either family", len(audit.defective())))
    for reason, count in audit.reason_counts().items():
        lines.append(f"    - {reason:<44}{count:>5}")
    return lines


def render_report(audits: list[PoolAudit]) -> str:
    lines: list[str] = ["Corpus fidelity audit", "=" * 60]
    for audit in audits:
        lines.extend(_format_pool(audit))
        lines.append("")
    total = sum(a.total for a in audits)
    defective = sum(len(a.defective()) for a in audits)
    lines.append(
        f"ALL POOLS  {defective} / {total} defective ({100 * defective / total:.1f}%)"
        if total
        else "ALL POOLS  no assets"
    )
    lines.append(
        "Pools are reported separately because only data/zmx is promoted to "
        "routable seeds; the staging ledger is fail-closed."
    )
    return "\n".join(lines)


def to_payload(audits: list[PoolAudit]) -> dict:
    return {
        "pools": [
            {
                "pool": a.pool,
                "root": a.root,
                "total": a.total,
                "hard": len(a.with_hard()),
                "fidelity": len(a.with_fidelity()),
                "defective": len(a.defective()),
                "reasons": a.reason_counts(),
                "seeds": [
                    {
                        "name": s.name,
                        "hard": list(s.hard),
                        "fidelity": list(s.fidelity),
                        "f_number": s.f_number,
                        "field_type": s.field_type,
                        "max_field": s.max_field,
                        "aspheric_surfaces": s.aspheric_surfaces,
                        "aspheric_surfaces_without_terms": s.aspheric_surfaces_without_terms,
                    }
                    for s in a.defective()
                ],
            }
            for a in audits
        ]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write the full payload as JSON")
    args = parser.parse_args(argv)

    audits = audit_corpus()
    print(render_report(audits))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(to_payload(audits), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
