"""Re-aim a seed's field definition at the requested field angle.

Why this exists
---------------
The optimisation path targets EFL and F/# and **nothing else**.
:func:`app.core.engines.codev_optimize.build_target_standard` says so in its own
docstring -- "未落地：IMH/FOV ... ``target_imh_mm`` 目前仅透传进三快照读数" -- so a
candidate keeps whatever field its seed was drawn with, no matter what the spec
asked for. Measured on 2026-07-29: one seed, two trials at different target EFLs,
candidate ``imh/efl`` identical to six digits (0.3317 = tan 18.35°) against
controls at 37.5° and 33.1°. The EFL half of the spec landed to 2e-11 %; the
field half never left the seed.

What this module changes and what it deliberately does not
----------------------------------------------------------
It rewrites exactly one line of the ZMX -- ``YFLN`` -- rescaling the seed's own
normalised field fractions so the **outermost** field sits at the requested
angle. Field *type* stays angular (``FTYP 0``), field *count* stays as drawn, and
the sampling pattern between axis and edge stays as drawn, because the
vignetting block and ``autovig`` address fields positionally and a re-sampled
field list would silently re-point them.

It does **not** pin the image height. With EFL locked by AUT and the field angle
locked here, the paraxial reference ``EFL*tan(theta)`` becomes identical on both
sides of a comparison, which makes 畸变 -- already one of the three metrics
NORTH-STAR §3 judges -- carry exactly the information "did the design land the
requested field on the requested sensor". Adding a second, separately-tuned image
height constraint would double-count that and invent a knob.

Fail-closed
-----------
Every unsupported shape returns a rejection with a reason instead of a rewritten
file. A seed we cannot re-aim is a trial we cannot run, which is strictly better
than a trial that quietly answers a different question -- that is the failure
this module exists to end.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.core.engines.zmx_import_prep import decode_zmx_text, encode_zmx_text

__all__ = [
    "FieldProfile",
    "SeedFieldRebuild",
    "max_field_angle_deg",
    "read_field_profile",
    "rebuild_seed_field_angles",
]

#: ``FTYP 0`` is Zemax's angular field type; 3 is real image height. Only the
#: angular form carries a field *angle*, which is the quantity a spec states.
ANGULAR_FIELD_TYPE = 0

_FIELD_ROW = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Z]+)(?P<gap>[ \t]+)(?P<body>.*)$")
_VIGNETTING_KEYS = ("VDXN", "VDYN", "VCXN", "VCYN")


@dataclass(frozen=True)
class FieldProfile:
    """The field rows of a ZMX, as read -- never as declared elsewhere."""

    field_type: int | None
    x_fields: tuple[float, ...]
    y_fields: tuple[float, ...]

    @property
    def is_angular(self) -> bool:
        return self.field_type == ANGULAR_FIELD_TYPE

    @property
    def max_y(self) -> float | None:
        if not self.y_fields:
            return None
        edge = max(abs(value) for value in self.y_fields)
        return edge if edge > 0.0 else None


@dataclass(frozen=True)
class SeedFieldRebuild:
    """Outcome of a re-aim attempt. ``text`` is ``None`` unless ``rebuilt``."""

    rebuilt: bool
    reason: str
    text: str | None = None
    encoding_tag: str | None = None
    source_max_angle_deg: float | None = None
    target_max_angle_deg: float | None = None
    normalised_fractions: tuple[float, ...] = ()

    @property
    def scale(self) -> float | None:
        if not self.source_max_angle_deg or self.target_max_angle_deg is None:
            return None
        return self.target_max_angle_deg / self.source_max_angle_deg


def _floats(body: str) -> tuple[float, ...]:
    values: list[float] = []
    for token in body.split():
        try:
            values.append(float(token))
        except ValueError:
            return ()
    return tuple(values)


def read_field_profile(text: str) -> FieldProfile:
    """Read ``FTYP``/``XFLN``/``YFLN`` out of ZMX text."""

    field_type: int | None = None
    x_fields: tuple[float, ...] = ()
    y_fields: tuple[float, ...] = ()
    for line in text.splitlines():
        match = _FIELD_ROW.match(line)
        if match is None:
            continue
        key, body = match.group("key"), match.group("body")
        if key == "FTYP":
            values = _floats(body)
            if values:
                field_type = int(values[0])
        elif key == "XFLN":
            x_fields = _floats(body)
        elif key == "YFLN":
            y_fields = _floats(body)
    return FieldProfile(field_type=field_type, x_fields=x_fields, y_fields=y_fields)


def max_field_angle_deg(text: str) -> float | None:
    """The outermost field **angle**, or ``None`` when the ZMX states no angle.

    A ``FTYP 3`` file states real image heights, not angles; returning its
    ``YFLN`` here would hand back millimetres labelled as degrees. That is the
    unit-confusion this project has already been bitten by (``^maximh`` is a
    paraxial ``EFL*tan(theta)``, not the real ray height), so it fails closed.
    """

    profile = read_field_profile(text)
    if not profile.is_angular:
        return None
    return profile.max_y


def rebuild_seed_field_angles(seed_bytes: bytes, target_max_angle_deg: float) -> SeedFieldRebuild:
    """Rescale a seed's field angles so its outermost field is ``target``.

    Only the ``YFLN`` row changes. Encoding and line endings survive byte-for-byte
    through :func:`decode_zmx_text` / :func:`encode_zmx_text`, so nothing but the
    field angles differs from the seed.
    """

    if not math.isfinite(target_max_angle_deg) or not 0.0 < target_max_angle_deg < 90.0:
        return SeedFieldRebuild(
            rebuilt=False,
            reason="target field angle must be a finite half-angle in (0, 90) degrees",
            target_max_angle_deg=target_max_angle_deg,
        )

    text, encoding_tag = decode_zmx_text(seed_bytes)
    profile = read_field_profile(text)
    if profile.field_type is None or not profile.y_fields or not profile.x_fields:
        return SeedFieldRebuild(
            rebuilt=False,
            reason="FTYP/XFLN/YFLN field rows are missing",
            target_max_angle_deg=target_max_angle_deg,
        )
    if not profile.is_angular:
        return SeedFieldRebuild(
            rebuilt=False,
            reason=f"only angular FTYP 0 seeds can be re-aimed; this one is FTYP {profile.field_type}",
            target_max_angle_deg=target_max_angle_deg,
        )
    if len(profile.x_fields) != len(profile.y_fields) or len(profile.y_fields) < 2:
        return SeedFieldRebuild(
            rebuilt=False,
            reason="XFLN/YFLN lengths disagree, or fewer than two fields are defined",
            target_max_angle_deg=target_max_angle_deg,
        )
    if any(value != 0.0 for value in profile.x_fields):
        return SeedFieldRebuild(
            rebuilt=False,
            reason="only meridional seeds (XFLN all zero) are supported",
            target_max_angle_deg=target_max_angle_deg,
        )
    source_edge = profile.max_y
    if source_edge is None:
        return SeedFieldRebuild(
            rebuilt=False,
            reason="seed YFLN has no positive outermost field",
            target_max_angle_deg=target_max_angle_deg,
        )

    fractions = tuple(value / source_edge for value in profile.y_fields)
    scaled = " ".join(format(fraction * target_max_angle_deg, ".17g") for fraction in fractions)

    replaced = 0
    rebuilt_lines: list[str] = []
    for line in text.split("\n"):
        match = _FIELD_ROW.match(line.rstrip("\r"))
        if match is not None and match.group("key") == "YFLN":
            carriage = "\r" if line.endswith("\r") else ""
            rebuilt_lines.append(
                f"{match.group('indent')}YFLN{match.group('gap')}{scaled}{carriage}"
            )
            replaced += 1
            continue
        rebuilt_lines.append(line)
    if replaced != 1:
        return SeedFieldRebuild(
            rebuilt=False,
            reason=f"expected exactly one YFLN row to rewrite, found {replaced}",
            source_max_angle_deg=source_edge,
            target_max_angle_deg=target_max_angle_deg,
        )

    return SeedFieldRebuild(
        rebuilt=True,
        reason="YFLN rescaled to the requested outermost field angle",
        text="\n".join(rebuilt_lines),
        encoding_tag=encoding_tag,
        source_max_angle_deg=source_edge,
        target_max_angle_deg=target_max_angle_deg,
        normalised_fractions=fractions,
    )


def rebuilt_bytes(result: SeedFieldRebuild) -> bytes:
    """Encode a successful rebuild back to ZMX bytes in the seed's own encoding."""

    if not result.rebuilt or result.text is None or result.encoding_tag is None:
        raise ValueError("only a successful rebuild can be encoded")
    return encode_zmx_text(result.text, result.encoding_tag)
