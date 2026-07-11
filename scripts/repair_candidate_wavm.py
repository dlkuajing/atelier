"""Pad candidate ZMX wavelength tables to the 24-slot CODE V import convention."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.repair_legacy_zmx_glass import decode_zmx_text, encode_zmx_text  # noqa: E402

_WAVM_RE = re.compile(r"^(?P<indent>\s*)WAVM\s+(?P<slot>\d+)\b")


def pad_wavm_text(text: str) -> tuple[str, int]:
    """Return padded text and number of rows added; reject missing/malformed tables."""

    lines = text.splitlines(keepends=True)
    rows = [(index, match) for index, line in enumerate(lines) if (match := _WAVM_RE.match(line))]
    if not rows:
        raise ValueError("no WAVM rows; refusing to invent a wavelength table")
    slots = [int(match.group("slot")) for _, match in rows]
    if slots != list(range(1, len(slots) + 1)) or len(slots) > 24:
        raise ValueError(f"WAVM slots must be contiguous 1..N with N <= 24; got {slots}")
    if len(slots) == 24:
        return text, 0

    last_index, last_match = rows[-1]
    last_line = lines[last_index]
    newline = "\r\n" if last_line.endswith("\r\n") else "\n" if last_line.endswith("\n") else ""
    indent = last_match.group("indent")
    padding = [f"{indent}WAVM {slot} 0.55 1{newline}" for slot in range(len(slots) + 1, 25)]
    lines[last_index + 1:last_index + 1] = padding
    return "".join(lines), len(padding)


def repair_wavm_file(path: Path, *, write: bool = False) -> int:
    """Audit one ZMX and optionally write padding; return the number of added rows."""

    raw = path.read_bytes()
    text, encoding = decode_zmx_text(raw)
    repaired, added = pad_wavm_text(text)
    if write and added:
        path.write_bytes(encode_zmx_text(repaired, encoding))
    return added


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
            added = repair_wavm_file(path, write=args.write)
        except (OSError, ValueError) as exc:
            failed = True
            print(f"refused {path}: {exc}")
            continue
        verdict = "already-24-slot" if not added else ("repaired" if args.write else "would-pad")
        print(f"{verdict} {path}: {added} WAVM row(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
