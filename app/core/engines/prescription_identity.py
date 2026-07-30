"""Identity of a *design*, as distinct from identity of a *file*.

Measured 2026-07-30: the 442 committed corpus ZMX are **354 distinct prescriptions**.
62 prescriptions are carried by more than one file, 150 files are involved, and the
largest groups are fours -- e.g. `US-11933948-B2-e10`, `US-12259531-B2-e10`,
`US-20240176110-A1-e8`, `US-20250383531-A1-e8` are byte-identical optical rows filed
under four publication numbers. That is what a patent family looks like from the
intake side: continuations republish the same embodiment, and the crawler files each
publication as its own case.

Why this module has to exist before any P2 rate is quoted: counting `case_id` counts
publications, and a rate whose denominator counts the same design four times is not
the rate it claims to be. The project has already been burned by reporting a ratio
before pinning its denominator, so the fingerprint is the denominator's definition.

Scope, honestly: this identifies *identical* prescriptions, byte-for-byte on the
optical rows. Two files that differ in the last digit of one radius are a different
fingerprint and will be counted as two designs even though a patent examiner would
call them one family. So the distinct count here is an **upper bound** on the number
of independent designs -- it can only overstate independence, never understate it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

#: Rows that describe the lens itself. Everything else in a ZMX (title, comments,
#: field/wavelength setup, apertures, vignetting) describes how we chose to *look* at
#: the lens, and two files that differ only there carry the same design.
#:
#: `DIAM` is deliberately excluded: it is the writer's declared clear aperture, and the
#: corpus-truth audit found it is derived from the same wandering edge ray that
#: corrupts the recorded image height. Including it would let a defect in a *derived*
#: field split one design into two.
_OPTICAL_ROW_PREFIXES = ("CURV", "DISZ", "GLAS", "CONI", "PARM", "XDAT")

_WHITESPACE = re.compile(r"\s+")


def prescription_rows(text: str) -> list[str]:
    """The optical rows of a ZMX, whitespace-normalised, in file order."""

    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_OPTICAL_ROW_PREFIXES):
            rows.append(_WHITESPACE.sub(" ", stripped))
    return rows


def prescription_fingerprint(text: str) -> str | None:
    """Stable digest of a prescription; ``None`` when there is no prescription.

    The `None` matters more than it looks: an earlier attempt at this measurement
    decoded the files with the wrong codec, every row list came out empty, and 211
    unrelated files hashed identically -- a "distinct designs = 215" reading that was
    an artifact of the decoder. Returning `None` for an empty row list makes that
    failure mode loud instead of arithmetic.
    """

    rows = prescription_rows(text)
    if not rows:
        return None
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def fingerprint_zmx(path: Path) -> str | None:
    """Fingerprint a ZMX on disk, decoded the way the rest of the pipeline decodes it."""

    from app.core.engines.zmx_import_prep import decode_zmx_text

    return prescription_fingerprint(decode_zmx_text(Path(path).read_bytes())[0])


def distinct_designs(paths: list[Path]) -> dict[str, object]:
    """Group ZMX paths by design. Report the groups *and* what could not be read.

    An unreadable file is never folded into the distinct count -- it is listed, so a
    denominator can never be quietly inflated or deflated by a decode failure.
    """

    groups: dict[str, list[str]] = {}
    unfingerprinted: list[str] = []
    for path in paths:
        fingerprint = fingerprint_zmx(path)
        if fingerprint is None:
            unfingerprinted.append(Path(path).name)
            continue
        groups.setdefault(fingerprint, []).append(Path(path).name)
    return {
        "files": len(paths),
        "distinct_designs": len(groups),
        "shared_prescriptions": sum(1 for names in groups.values() if len(names) > 1),
        "files_in_shared_prescriptions": sum(
            len(names) for names in groups.values() if len(names) > 1
        ),
        "unfingerprinted": unfingerprinted,
        "groups": {fingerprint: sorted(names) for fingerprint, names in groups.items()},
    }
