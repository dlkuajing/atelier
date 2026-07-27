"""Pad candidate ZMX wavelength tables to the 24-slot CODE V import convention."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.engines.zmx_import_prep import (  # noqa: E402
    count_wavm_rows,
    decode_zmx_text,
    encode_zmx_text,
    pad_wavm_slots,
)

_WAVM_RE = re.compile(r"^(?P<indent>\s*)WAVM\s+(?P<slot>\d+)\b")
_NUMERIC_GLAS_RE = re.compile(
    r"^(?P<indent>\s*)GLAS\s+(?P<name>\d{6}\.\d+)\s+(?P<flag>\S+)\s+(?P<rest>.*)$"
)


def rename_numeric_glass_names(text: str) -> tuple[str, int]:
    """Rewrite numeric model-glass code GLAS names to ``___BLANK 1``.

    ZEMAXOS_TO_CV parses a numeric NAME as a float and derives the fictitious
    glass's dispersion from the mangled result (real-machine proof 2026-07-11:
    declared vd 54.0607 became vd 40.154 inside CODE V). ``___BLANK`` with
    model_flag=1 makes the importer honor the explicit nd/vd columns instead.
    """

    lines = text.splitlines(keepends=True)
    renamed = 0
    for index, line in enumerate(lines):
        match = _NUMERIC_GLAS_RE.match(line.rstrip("\r\n"))
        if match is None:
            continue
        # Gate (review MAJOR): rename only when the leading six digits encode
        # this line's explicit nd ((nd-1)*1e6, the model-glass code contract).
        # A numeric name that does NOT encode its own nd could be a legitimate
        # catalog trade name — leave it untouched.
        rest_fields = match.group("rest").split()
        try:
            explicit_nd = float(rest_fields[1])
        except (IndexError, ValueError):
            continue
        encoded_nd = 1.0 + int(match.group("name")[:6]) / 1e6
        if abs(encoded_nd - explicit_nd) > 5e-4:
            continue
        eol = line[len(line.rstrip("\r\n")):]
        lines[index] = f"{match.group('indent')}GLAS ___BLANK 1 {match.group('rest')}{eol}"
        renamed += 1
    return "".join(lines), renamed


def pad_wavm_text(text: str) -> tuple[str, int]:
    """Return padded text and number of rows added; reject missing/malformed tables.

    Padding itself lives in ``app.core.engines.zmx_import_prep`` so the import
    path and this repair tool cannot drift apart. The extra rule here is this
    tool's own: a *candidate* ZMX we generated must already carry a wavelength
    table, so a missing one is a defect to report rather than a file to leave
    alone (the shared helper passes such files through untouched, because a
    ``WAVL``-style seed legitimately has no ``WAVM`` rows).
    """

    if count_wavm_rows(text) == 0:
        raise ValueError("no WAVM rows; refusing to invent a wavelength table")
    return pad_wavm_slots(text)


def repair_wavm_file(path: Path, *, write: bool = False) -> tuple[int, bool, int]:
    """Audit one ZMX; return (rows added, endings normalized, GLAS renamed).

    Output is always LF-normalized: real-machine proof (2026-07-11, byte-identical
    A/B import) shows CRLF endings break ZEMAXOS_TO_CV's WAVM wavelength parsing
    (lens imports with no wavelength data). A file that is already 24-slot but
    CRLF still gets rewritten to LF. Numeric model-glass code names are renamed
    to ``___BLANK 1`` (see ``rename_numeric_glass_names``).
    """

    raw = path.read_bytes()
    text, encoding = decode_zmx_text(raw)
    repaired, added = pad_wavm_text(text)
    repaired, renamed = rename_numeric_glass_names(repaired)
    normalized = repaired.replace("\r\n", "\n").replace("\r", "\n")
    eol_fixed = normalized != repaired or "\r" in text
    if write and (added or eol_fixed or renamed):
        path.write_bytes(encode_zmx_text(normalized, encoding))
    return added, eol_fixed, renamed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="candidate ZMX file(s) or directories")
    parser.add_argument("--write", action="store_true", help="apply repairs (default: dry-run)")
    args = parser.parse_args(argv)

    files = sorted(
        {child for path in args.paths for child in (path.glob("*.zmx") if path.is_dir() else [path])}
    )
    failed = False
    for path in files:
        try:
            added, eol_fixed, renamed = repair_wavm_file(path, write=args.write)
        except (OSError, ValueError) as exc:
            failed = True
            print(f"refused {path}: {exc}")
            continue
        if not added and not eol_fixed and not renamed:
            verdict = "already-compliant"
        else:
            verdict = "repaired" if args.write else "would-repair"
        print(
            f"{verdict} {path}: {added} WAVM row(s), eol_normalized={eol_fixed}, "
            f"glas_renamed={renamed}"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
