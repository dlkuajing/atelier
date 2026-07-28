"""Normalize Zemax ``.zmx`` files so CODE V's import macro reads their wavelengths.

Root cause (macro source ``D:/CODEV115/macro/zemaxos_to_cv.seq``, confirmed by
real-machine A/B 2026-07-27): ``ZEMAXOS_TO_CV`` learns the active wavelength
count from ``FTYP`` column ``j5`` (``^nwl == (buf.num ic j5)``, L801) and then
only *buffers* each ``WAVM`` row::

    if ^zwlnum <= ^nwl                 ! buffer this row
        buf put b^bufw i^zwlnum ...
    else if ^zwlnum = ^nwl+1           ! <-- the ONLY place `wl`/`wtw` are emitted
        buf srt b^bufw j2 des
        ...
        $wlstr                         ! `wl 656.3 587.6 486.1`
        $wtwstr

The ``wl``/``wtw`` commands are emitted solely by the ``^zwlnum = ^nwl+1``
branch. A file whose ``WAVM`` row count *equals* its declared ``^nwl`` never
supplies that sentinel row, so the flush never fires, no ``wl`` command is ever
issued, and the lens imports with CODE V's built-in default single wavelength.
The 2016 "Temporary fix for single WL in WAVM format" (macro L1116) only covers
``^nwl = 1``, not ``rows == ^nwl``.

Zemax itself always writes 24 ``WAVM`` rows (real wavelengths followed by
``0.55`` filler slots), which is why files that made a CODE V round trip import
correctly while raw patent-derived seeds do not. Rows past ``^nwl+1`` match
neither branch and are ignored, and the sentinel row's own values are never
read — only its *index* matters.

Real-machine evidence (2026-07-27, 10 sequential runs, D:/CODEV115):

===========================  ==========  =========  =====  =============
seed                         WAVM rows   FTYP nwl   NUM W  vd measured
===========================  ==========  =========  =====  =============
US-10101561-B2-e3 (as-is)             3          3      1  0/6
US-10101561-B2-e3 (+1 row)            4          3      3  6/6
US-10101561-B2-e3 (24 slots)         24          3      3  6/6
US-12228698-B2-e5 (as-is)             3          3      1  0/10
US-12228698-B2-e5 (+1 row)            4          3      3  10/10
US-20220050269-A1-e3 (as-is)          3          3      1  0/6
US-20220050269-A1-e3 (+1 row)         4          3      3  6/6
===========================  ==========  =========  =====  =============

Consequences of the collapse, all downstream of this one defect:

* ``@lcum`` measures ``|W1 image point - W(NUM W) image point|``; with
  ``NUM W = 1`` both ends name the same wavelength, so lateral color reads
  exactly ``0.0`` — "perfectly achromatic" reported for a system whose
  dispersion was never evaluated (fail-closed in PR #90; root-caused here).
* ``codev_readout``'s vd probe is gated on ``IF (NUM W) >= 3``, so every glass
  reports ``vd_source=None``; ``zmx_writer`` then emits ``vd=0`` and the next
  import cannot rebuild an ``nd.vd`` model glass, surfacing as
  ``<code> is not in a catalog - quotes needed for private cat. glass``.

Line endings are *not* the discriminator. All 442 corpus files are CRLF,
including the 39 that import their full wavelength set; the control run above
(CRLF, 24 slots) read back all 5 wavelengths with ``vd 4/4``. Padding therefore
preserves each file's existing encoding and newline style rather than rewriting
them.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.core.engines.codev_batch import ensure_codev_safe_input_path

#: Zemax writes this many ``WAVM`` slots; CODE V consumes the first ``^nwl``
#: and needs row ``^nwl+1`` to exist as a flush sentinel.
CODEV_WAVM_SLOTS = 24

#: Sub-directory of ``work_dir`` that holds CODE V-ready copies. Deliberately
#: short: Stage C run directories are already deep and Windows caps paths at 260.
STAGED_INPUT_DIRNAME = "cvin"

_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"
_WAVM_RE = re.compile(r"^(?P<indent>\s*)WAVM\s+(?P<slot>\d+)\b")


def decode_zmx_text(raw: bytes) -> tuple[str, str]:
    """Decode ZMX bytes, returning ``(text, encoding_tag)`` for a lossless roundtrip.

    ``encoding_tag`` is one of ``utf-16-le-bom`` / ``utf-16-be-bom`` /
    ``latin-1``; :func:`encode_zmx_text` reverses it byte-for-byte (latin-1 is
    the identity byte<->str mapping for non-BOM files).
    """

    if raw.startswith(_UTF16_LE_BOM):
        return raw[len(_UTF16_LE_BOM) :].decode("utf-16-le"), "utf-16-le-bom"
    if raw.startswith(_UTF16_BE_BOM):
        return raw[len(_UTF16_BE_BOM) :].decode("utf-16-be"), "utf-16-be-bom"
    return raw.decode("latin-1"), "latin-1"


def encode_zmx_text(text: str, encoding_tag: str) -> bytes:
    """Re-encode text produced by :func:`decode_zmx_text`."""

    if encoding_tag == "utf-16-le-bom":
        return _UTF16_LE_BOM + text.encode("utf-16-le")
    if encoding_tag == "utf-16-be-bom":
        return _UTF16_BE_BOM + text.encode("utf-16-be")
    return text.encode("latin-1")


def count_wavm_rows(text: str) -> int:
    """Return the number of ``WAVM`` rows in a ZMX prescription."""

    return sum(1 for line in text.splitlines() if _WAVM_RE.match(line))


def declared_wavelength_count(text: str) -> int | None:
    """Return the wavelength count CODE V reads from ``FTYP`` column ``j5``.

    This is the ``^nwl`` the import macro compares every ``WAVM`` slot against,
    so ``count_wavm_rows(text) > declared_wavelength_count(text)`` is exactly the
    condition for the flush sentinel to exist. ``None`` when the file declares no
    usable ``FTYP`` row (the macro only reads j5 when ``FTYP`` has >= 8 columns).
    """

    for line in text.splitlines():
        if not line.startswith("FTYP"):
            continue
        fields = line.split()
        if len(fields) < 8:
            return None
        try:
            return int(float(fields[4]))
        except ValueError:
            return None
    return None


def pad_wavm_slots(text: str) -> tuple[str, int]:
    """Pad the ``WAVM`` table to :data:`CODEV_WAVM_SLOTS` rows.

    Returns ``(text, rows_added)``. Files with no ``WAVM`` table are returned
    unchanged with ``0`` — older Zemax files declare wavelengths via ``WAVL``,
    which the import macro handles through a separate branch that needs no
    sentinel. A malformed table raises instead of being guessed at: inventing a
    wavelength table would manufacture the very kind of unearned number this
    module exists to prevent.

    Raises:
        ValueError: when ``WAVM`` slots are not contiguous ``1..N`` with
            ``N <= CODEV_WAVM_SLOTS``.
    """

    lines = text.splitlines(keepends=True)
    rows = [(index, match) for index, line in enumerate(lines) if (match := _WAVM_RE.match(line))]
    if not rows:
        return text, 0
    slots = [int(match.group("slot")) for _, match in rows]
    if slots != list(range(1, len(slots) + 1)) or len(slots) > CODEV_WAVM_SLOTS:
        raise ValueError(
            f"WAVM slots must be contiguous 1..N with N <= {CODEV_WAVM_SLOTS}; got {slots}"
        )
    if len(slots) == CODEV_WAVM_SLOTS:
        return text, 0

    last_index, last_match = rows[-1]
    last_line = lines[last_index]
    if last_line.endswith("\r\n"):
        newline = "\r\n"
    elif last_line.endswith("\n"):
        newline = "\n"
    else:
        newline = ""
    indent = last_match.group("indent")
    padding = [
        f"{indent}WAVM {slot} 0.55 1{newline}"
        for slot in range(len(slots) + 1, CODEV_WAVM_SLOTS + 1)
    ]
    lines[last_index + 1 : last_index + 1] = padding
    return "".join(lines), len(padding)


def pad_wavm_bytes(raw: bytes) -> tuple[bytes, int]:
    """Byte-level :func:`pad_wavm_slots`, preserving the file's encoding."""

    text, encoding = decode_zmx_text(raw)
    padded, added = pad_wavm_slots(text)
    if added == 0:
        return raw, 0
    return encode_zmx_text(padded, encoding), added


def stage_zmx_for_codev(
    source_zmx: Path | str,
    work_dir: Path | str,
    *,
    role: str = "staged_zmx",
) -> Path:
    """Write a CODE V-ready copy of ``source_zmx`` under ``work_dir`` and return it.

    Every CODE V import goes through here so that the wavelength table survives
    ``ZEMAXOS_TO_CV`` (see module docstring). The source asset is never
    modified: ``data/zmx`` is the project's data anchor, and a corpus rewrite
    would still leave newly collected seeds defective.

    The copy is byte-identical to the source apart from the appended ``WAVM``
    filler rows, so encoding, line endings and every optical value are carried
    through untouched. Already-padded files are copied verbatim.

    ``work_dir`` is resolved to an absolute path first. The staged path is what
    gets written into the macro's ``IN CV_MACRO:ZEMAXOS_TO_CV`` line, and CODE V
    resolves a relative path there against its own working directory -- which
    ``run_codev_batch`` sets to ``work_dir``. A relative ``work_dir`` would
    therefore be applied twice and the import would silently fall back to a dummy
    system. Three of the five CODE V runners already resolved their ``work_dir``
    for exactly this reason (``codev_readout``, ``run_codev_target``,
    ``codev_tolerance``); resolving here covers the remaining two without
    depending on each caller to remember.

    Raises:
        ValueError: when the staged path would contain a dot-prefixed component.
            CODE V cannot import from such a path (``ensure_codev_safe_input_path``),
            so a run directory like ``.tmp/...`` has to be renamed rather than
            worked around -- staging the copy somewhere else would hide a run's
            input outside its own work directory.
    """

    source_zmx = Path(source_zmx)
    staged_dir = Path(work_dir).resolve() / STAGED_INPUT_DIRNAME
    staged = staged_dir / source_zmx.name
    ensure_codev_safe_input_path(staged, role=role)
    staged_dir.mkdir(parents=True, exist_ok=True)

    padded, added = pad_wavm_bytes(source_zmx.read_bytes())
    if added == 0:
        # copy2 keeps mtime, which several probes use to spot stale artifacts.
        shutil.copy2(source_zmx, staged)
    else:
        staged.write_bytes(padded)
    return staged
