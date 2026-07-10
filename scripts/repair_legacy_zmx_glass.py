"""Repair legacy real-design ZMX glass lines so CODE V can resolve them.

Root cause (real-machine evidence 2026-07-10, Phase-1 diagnosis of the Mode3
``zmx_rebuild_error: non-finite EFL: -inf`` fail-closed skips): the 17 legacy
real-design seeds (``data/zmx/{3P,4P,5P}_*.zmx``, commit 7762b7a, pre-CODE-V
era) encode their plastic lens elements as *named catalog glass*
(``GLAS <trade-name> 0 0 <placeholder-nd> <placeholder-vd> ...``,
model_flag=0) using Japanese optical-resin trade names (APL5014CL_14, OKP1_14,
ZEONEX-E48R_14, EP8000, ...) that exist in no catalog CODE V loads. CODE V's
``ZEMAXOS_TO_CV`` importer silently drops each unresolved glass to air
(nd=1.0), producing an all-air, zero-power system (baseline EFL sentinel
1e35) — the entire optimize pipeline then runs on garbage. Optiland never
noticed because ``app/core/optiland_patches.py::_patch_zemax_glass_materials``
substitutes real datasheet nd/vd from ``app/core/zmx_materials.py`` at parse
time; CODE V has no equivalent fallback.

Fix: rewrite ONLY the affected ``GLAS`` lines to the explicit *model glass*
mechanism the patent-derived seeds already use (inline nd/vd), keeping the
trade name recoverable via a ``_BLANK`` marker suffix::

    GLAS APL5014CL_14 0 0 1.5 40 ...  ->  GLAS APL5014CL_14_BLANK 1 0 1.544 56 ...

nd/vd are taken from ``app.core.zmx_materials.lookup_nd_vd`` — the *same*
normalization + lookup code path the Optiland fallback uses — so the inline
values equal what Optiland resolves today and every Optiland-derived number
(EFL goldens, case library, MTF) is unchanged by construction (verified: EFL
delta exactly 0.0 on the probe seed). No value is invented; a flag-0 name that
is neither CODE-V-resolvable nor in the lookup table raises instead of
guessing.

Emitted-name verdicts (all real-machine verified 2026-07-10,
scratch_diag/rebuild_inf_efl/verify_*_glass.stdout.log):

1. **Named model glass (bare trade name + model_flag=1) is REJECTED**:
   ``GLAS APL5014CL_14 1 0 1.544 56`` still imports as air. CODE V's importer
   keys on the glass-name *string*, not the flag.
2. Root mechanism (macro source ``D:/CODEV115/macro/zemaxos_to_cv.seq``
   L1523): the model-glass branch is selected by **substring** match —
   ``locstr(^string,"BLANK") <> 0`` — and then reads nd/vd from the numeric
   columns, ignoring the rest of the name.
3. **``<trade-name>_BLANK`` + model_flag=1 is ACCEPTED**: every repaired
   surface imports as a fictitious glass with the written nd/vd (probe:
   APL5014CL_14_BLANK -> 544000.560000, nd 1.546 @ ref wavelength).

Trade-off vs the plain ``___BLANK`` fallback: ``___BLANK`` would erase the
material identity that ``app/core/case_library.py::_materials_from_zmx`` and
``app/core/prescription_table.py`` read from GLAS rows (and that
``tests/test_prescription_table.py`` / ``tests/test_case_library.py`` pin).
The ``_BLANK`` marker keeps the identity in-file; the Python readers strip the
marker (``zmx_materials._canon`` / ``prescription_table``), so canonical
material names, case metadata and prescription display are all unchanged.

Names deliberately NOT rewritten (model_flag=0 kept): catalog names verified
on the real machine to resolve inside CODE V — see
``CODEV_RESOLVABLE_GLASS_NAMES``. Rewriting those would *change* CODE V
behavior (catalog dispersion -> model glass), which this repair must not do.

Deterministic and idempotent: only GLAS lines with model_flag=0 and a
non-allowlisted name are touched; a second run is a no-op. Everything else in
each file — encoding (UTF-16 LE BOM), line endings (CRLF), token separators,
every other line — is preserved byte-for-byte.

Usage (from the backend root)::

    uv run python scripts/repair_legacy_zmx_glass.py            # repair data/zmx
    uv run python scripts/repair_legacy_zmx_glass.py --check    # dry-run, exit 1 if dirty
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.zmx_materials import lookup_nd_vd  # noqa: E402

ZMX_DIR = Path(__file__).resolve().parents[1] / "data" / "zmx"

# Named catalog glasses (model_flag=0) verified ON THE REAL CODE V MACHINE
# (2026-07-10, scratch_diag/rebuild_inf_efl readouts) to resolve to a catalog
# glass on ZEMAXOS_TO_CV import:
#   BK7      -> SCHOTT BK7, imported nd 1.51827 (5P_F2.0_FOV78.7 readout)
#   H-LAK51A -> catalog 'HLAK51A', imported nd 1.70114 (4P_F1.9_FOV60.1 readout)
#   H-LAK53A -> catalog 'HLAK53A', imported nd 1.75999 (4P_F1.9_FOV60.0 readout)
# Every other flag-0 name in data/zmx imported as air (nd=1.0) and must be
# rewritten to explicit model glass. Extend only with real-machine evidence.
CODEV_RESOLVABLE_GLASS_NAMES = frozenset({"BK7", "H-LAK51A", "H-LAK53A"})

# Marker suffix that makes ZEMAXOS_TO_CV take its model-glass branch (substring
# match on "BLANK", macro L1523) while keeping the trade name recoverable.
# Python readers strip it: zmx_materials._canon / prescription_table.
CODEV_MODEL_GLASS_MARKER = "_BLANK"

_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"


def decode_zmx_text(raw: bytes) -> tuple[str, str]:
    """Decode ZMX bytes, returning (text, encoding_tag) for a lossless roundtrip.

    encoding_tag is one of ``utf-16-le-bom`` / ``utf-16-be-bom`` / ``latin-1``;
    ``encode_zmx_text`` reverses it byte-for-byte (latin-1 is the identity
    byte<->str mapping for non-BOM files, whose GLAS content is ASCII anyway).
    """
    if raw.startswith(_UTF16_LE_BOM):
        return raw[len(_UTF16_LE_BOM):].decode("utf-16-le"), "utf-16-le-bom"
    if raw.startswith(_UTF16_BE_BOM):
        return raw[len(_UTF16_BE_BOM):].decode("utf-16-be"), "utf-16-be-bom"
    return raw.decode("latin-1"), "latin-1"


def encode_zmx_text(text: str, encoding_tag: str) -> bytes:
    if encoding_tag == "utf-16-le-bom":
        return _UTF16_LE_BOM + text.encode("utf-16-le")
    if encoding_tag == "utf-16-be-bom":
        return _UTF16_BE_BOM + text.encode("utf-16-be")
    return text.encode("latin-1")


def iter_glas_lines(text: str):
    """Yield ``(line_number, tokens)`` for every GLAS line (1-based numbering)."""
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("GLAS"):
            yield line_number, stripped.split()


def _fmt_number(value: float) -> str:
    return f"{float(value):.15g}"


def glas_line_needs_repair(tokens: list[str]) -> bool:
    """A GLAS row needs repair iff it names a catalog glass (model_flag=0) that
    the real CODE V machine cannot resolve (not in the verified allowlist)."""
    if len(tokens) < 6 or tokens[0] != "GLAS":
        return False
    name, flag = tokens[1], tokens[2]
    if name.upper() == "MIRROR" or name == "___BLANK":
        return False
    return flag == "0" and name not in CODEV_RESOLVABLE_GLASS_NAMES


def repair_glas_line(line: str) -> tuple[str, bool]:
    """Rewrite one GLAS line to explicit model glass, preserving whitespace.

    Only four tokens change: the name gains the ``_BLANK`` marker (what
    actually makes CODE V's importer treat the row as model glass — verified
    substring match, see module docstring), model_flag 0 -> 1 (documentation
    of intent; CODE V ignores it), and the placeholder nd/vd -> the datasheet
    values from ``lookup_nd_vd`` (the Optiland fallback's own table). Raises
    if the material is unknown — never invents an index.
    """
    parts = re.split(r"(\s+)", line)
    token_slots = [i for i, part in enumerate(parts) if part and not part.isspace()]
    tokens = [parts[i] for i in token_slots]
    if not glas_line_needs_repair(tokens):
        return line, False
    name = tokens[1]
    real = lookup_nd_vd(name)
    if real is None:
        raise ValueError(
            f"GLAS name {name!r} is neither CODE-V-resolvable (allowlist) nor in "
            "app.core.zmx_materials.MATERIAL_ND_VD; refusing to invent nd/vd"
        )
    nd, vd = real
    parts[token_slots[1]] = f"{name}{CODEV_MODEL_GLASS_MARKER}"
    parts[token_slots[2]] = "1"
    parts[token_slots[4]] = _fmt_number(nd)
    parts[token_slots[5]] = _fmt_number(vd)
    return "".join(parts), True


def repair_zmx_file(path: Path, *, apply: bool = True) -> list[tuple[str, str]]:
    """Repair one ZMX file in place; return the (old, new) stripped line pairs."""
    raw = path.read_bytes()
    text, encoding_tag = decode_zmx_text(raw)
    changes: list[tuple[str, str]] = []
    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        new_line, changed = repair_glas_line(line)
        if changed:
            changes.append((line.strip(), new_line.strip()))
        out_lines.append(new_line)
    if changes and apply:
        path.write_bytes(encode_zmx_text("".join(out_lines), encoding_tag))
    return changes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="dry-run: report files needing repair, exit 1 if any (no writes)",
    )
    parser.add_argument(
        "--zmx-dir", type=Path, default=ZMX_DIR,
        help=f"directory of .zmx files to repair (default: {ZMX_DIR})",
    )
    args = parser.parse_args(argv)

    dirty = 0
    for path in sorted(args.zmx_dir.iterdir()):
        if path.suffix.lower() != ".zmx":
            continue
        changes = repair_zmx_file(path, apply=not args.check)
        if not changes:
            continue
        dirty += 1
        verb = "would repair" if args.check else "repaired"
        print(f"{verb} {path.name}: {len(changes)} GLAS line(s)")
        for old, new in changes:
            print(f"  - {old}")
            print(f"  + {new}")
    if dirty == 0:
        print("all GLAS lines already CODE-V-resolvable; nothing to do")
    return 1 if (args.check and dirty) else 0


if __name__ == "__main__":
    raise SystemExit(main())
