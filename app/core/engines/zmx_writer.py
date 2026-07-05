"""Zemax text writer for CODE V prescription readouts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from app.core.engines.codev_readout import CodeVFieldReadout, CodeVReadout, CodeVSurfaceReadout

_DEFAULT_WAVELENGTHS_UM: tuple[float, ...] = (0.4861, 0.5876, 0.6563)
_DEFAULT_PRIMARY_WAVELENGTH_INDEX = 2
_ASPHERE_TERMS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G")
_AIR_GLASS_NAMES = {"", "AIR", "NONE", "NULL", "___BLANK"}
_FIELD_TYPE_TO_FTYP = {
    "ANG": 0,
    "ANGLE": 0,
    "OBJ": 1,
    "OBJECT": 1,
    "PIM": 2,
    "PARAXIAL_IMAGE_HEIGHT": 2,
    "IMG": 3,
    "IMAGE": 3,
    "RIH": 3,
    "REAL_IMAGE_HEIGHT": 3,
}


def build_zmx_from_codev_readout(
    readout: CodeVReadout,
    *,
    name: str | None = None,
    f_number: float | None = 2.8,
    entrance_pupil_diameter_mm: float | None = None,
    wavelengths_um: Sequence[float] = _DEFAULT_WAVELENGTHS_UM,
    semi_diameter_mm: float | None = None,
) -> str:
    """Return an ASCII Zemax ``.zmx`` prescription with CRLF newlines.

    The input is the structured readout produced by ``codev_readout``. CODE V
    exposes vignetting as upper/lower pupil limits; Zemax stores equivalent
    decenter/compression arrays, so both ``VDXN/VDYN`` and ``VCXN/VCYN`` are
    emitted to preserve the four readout values.
    """

    surfaces = _ordered_surfaces(readout)
    fields = _ordered_fields(readout)
    wavelengths = _validated_wavelengths(wavelengths_um)
    system_name = _ascii_text(name or Path(readout.source_zmx).stem)
    semi_diameter = semi_diameter_mm or _default_semi_diameter(readout, fields)

    lines: list[str] = [
        "VERS 191028 13541 33913 33913",
        "MODE SEQ",
        f"NAME {system_name}",
        "UNIT MM X W X CM MR CPMM",
    ]
    _append_aperture(
        lines,
        f_number=f_number,
        entrance_pupil_diameter_mm=entrance_pupil_diameter_mm,
    )
    _append_fields(lines, readout, fields, wavelengths)
    _append_wavelengths(lines, wavelengths, readout.reference_wavelength_index)
    _append_object_surface(lines)
    for surface in surfaces:
        _append_surface(lines, surface, semi_diameter=semi_diameter)

    text = "\r\n".join(lines) + "\r\n"
    text.encode("ascii")
    return text


def build_zmx_text(readout: CodeVReadout, **kwargs: object) -> str:
    """Compatibility alias for callers that only need the textual ZMX body."""

    return build_zmx_from_codev_readout(readout, **kwargs)


def write_zmx_from_codev_readout(
    readout: CodeVReadout,
    output_path: Path | str,
    **kwargs: object,
) -> Path:
    """Write a CODE V readout as an ASCII/CRLF Zemax file and return its path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_zmx_from_codev_readout(readout, **kwargs).encode("ascii"))
    return path


def write_zmx_text(readout: CodeVReadout, output_path: Path | str, **kwargs: object) -> Path:
    """Compatibility alias for writing the generated ZMX text to disk."""

    return write_zmx_from_codev_readout(readout, output_path, **kwargs)


def _append_aperture(
    lines: list[str],
    *,
    f_number: float | None,
    entrance_pupil_diameter_mm: float | None,
) -> None:
    if entrance_pupil_diameter_mm is not None:
        lines.append(f"ENPD {_fmt_positive(entrance_pupil_diameter_mm, 'entrance_pupil_diameter_mm')}")
        return
    if f_number is None:
        raise ValueError("Either f_number or entrance_pupil_diameter_mm must be provided")
    lines.append(f"FNUM {_fmt_positive(f_number, 'f_number')} 0")


def _append_fields(
    lines: list[str],
    readout: CodeVReadout,
    fields: tuple[CodeVFieldReadout, ...],
    wavelengths: tuple[float, ...],
) -> None:
    field_type = _normalized_field_type(readout.field_type or fields[0].definition_type)
    ftyp = _FIELD_TYPE_TO_FTYP.get(field_type, 3)
    lines.append(f"FTYP {ftyp} 0 {len(fields)} {len(wavelengths)} 0 0 0 {len(fields)}")

    x_values = [_value_or_zero(field.x) for field in fields]
    y_values = [_value_or_zero(field.y) for field in fields]
    vdx_values, vcx_values = _vignette_axis(fields, upper_attr="vux", lower_attr="vlx")
    vdy_values, vcy_values = _vignette_axis(fields, upper_attr="vuy", lower_attr="vly")
    zeros = [0.0] * len(fields)
    ones = [1.0] * len(fields)

    lines.append(f"XFLN {_fmt_values(x_values)}")
    lines.append(f"YFLN {_fmt_values(y_values)}")
    lines.append(f"FWGN {_fmt_values(ones)}")
    lines.append(f"VDXN {_fmt_values(vdx_values)}")
    lines.append(f"VDYN {_fmt_values(vdy_values)}")
    lines.append(f"VCXN {_fmt_values(vcx_values)}")
    lines.append(f"VCYN {_fmt_values(vcy_values)}")
    lines.append(f"VANN {_fmt_values(zeros)}")


def _append_wavelengths(
    lines: list[str],
    wavelengths: tuple[float, ...],
    readout_primary_index: int,
) -> None:
    for index, wavelength in enumerate(wavelengths, start=1):
        lines.append(f"WAVM {index} {_fmt_number(wavelength)} 1")
    primary = readout_primary_index
    if primary < 1 or primary > len(wavelengths):
        primary = min(_DEFAULT_PRIMARY_WAVELENGTH_INDEX, len(wavelengths))
    lines.append(f"PWAV {primary}")


def _append_object_surface(lines: list[str]) -> None:
    lines.extend(
        [
            "SURF 0",
            "  TYPE STANDARD",
            "  FIMP ",
            "  CURV 0 0 0 0 0 \"\"",
            "  HIDE 0 0 0 0 0 0 0 0 0 0",
            "  MIRR 2 0",
            "  SLAB 0",
            "  DISZ INFINITY",
            "  DIAM 0 0 0 0 1 \"\"",
            "  MEMA 0 0 0 0 1 \"\"",
            "  POPS 0 0 0 0 0 0 0 0 1 1 1 1 0 0 0 0",
        ]
    )


def _append_surface(
    lines: list[str],
    surface: CodeVSurfaceReadout,
    *,
    semi_diameter: float,
) -> None:
    surface_type = _zemax_surface_type(surface)
    lines.append(f"SURF {surface.index}")
    if surface.is_stop:
        lines.append("  STOP")
    lines.extend(
        [
            f"  TYPE {surface_type}",
            "  FIMP ",
            f"  CURV {_fmt_number(_curvature(surface.radius_y_mm))} 0 0 0 0 \"\"",
            "  HIDE 0 0 0 0 0 0 0 0 0 0",
            "  MIRR 2 0",
            f"  SLAB {surface.index}",
        ]
    )
    if surface_type == "EVENASPH":
        _append_even_asphere_terms(lines, surface)
    lines.append(f"  DISZ {_fmt_distance(surface.thickness_mm)}")
    glass = _glass_line(surface)
    if glass is not None:
        lines.append(glass)
    conic = surface.asphere_coefficients.get("K")
    if conic is not None and math.isfinite(conic):
        lines.append(f"  CONI {_fmt_number(conic)}")
    lines.extend(
        [
            f"  DIAM {_fmt_number(semi_diameter)} 0 0 0 1 \"\"",
            f"  MEMA {_fmt_number(semi_diameter)} 0 0 0 1 \"\"",
            "  POPS 0 0 0 0 0 0 0 0 1 1 1 1 0 0 0 0",
        ]
    )


def _append_even_asphere_terms(lines: list[str], surface: CodeVSurfaceReadout) -> None:
    # Existing data/zmx EVENASPH files reserve PARM 1 and use PARM 2..8 for
    # CODE V A..G. Emitting H/J would change the source term count.
    lines.append("  PARM 1 0")
    for offset, label in enumerate(_ASPHERE_TERMS, start=2):
        value = surface.asphere_coefficients.get(label, 0.0)
        lines.append(f"  PARM {offset} {_fmt_number(value)}")


def _glass_line(surface: CodeVSurfaceReadout) -> str | None:
    name = _optional_glass_name(surface.glass)
    if name is None:
        return None
    nd = surface.nd
    vd = surface.vd
    if nd is None or vd is None or not math.isfinite(nd) or not math.isfinite(vd):
        return None
    if nd <= 1.000001:
        return None
    return f"  GLAS {name} 0 0 {_fmt_number(nd)} {_fmt_number(vd)} 0 0 0 0 0 0 "


def _zemax_surface_type(surface: CodeVSurfaceReadout) -> str:
    raw_type = (surface.surface_type or "").strip().upper()
    has_even_terms = any(
        abs(surface.asphere_coefficients.get(label, 0.0)) > 0.0 for label in _ASPHERE_TERMS
    )
    if raw_type in {"ASP", "ASPH", "EVENASPH", "XASPHERE"} or has_even_terms:
        return "EVENASPH"
    return "STANDARD"


def _vignette_axis(
    fields: tuple[CodeVFieldReadout, ...],
    *,
    upper_attr: str,
    lower_attr: str,
) -> tuple[list[float], list[float]]:
    decenter: list[float] = []
    compression: list[float] = []
    for field in fields:
        upper = _value_or_zero(getattr(field, upper_attr))
        lower = _value_or_zero(getattr(field, lower_attr))
        decenter.append((upper + lower) / 2.0)
        compression.append((upper - lower) / 2.0)
    return decenter, compression


def _ordered_surfaces(readout: CodeVReadout) -> tuple[CodeVSurfaceReadout, ...]:
    surfaces = tuple(sorted(readout.surfaces, key=lambda surface: surface.index))
    if not surfaces:
        raise ValueError("CODE V readout has no surfaces")
    for surface in surfaces:
        if surface.index < 1:
            raise ValueError(f"ZMX writer expects positive CODE V surface indices: {surface.index}")
    return surfaces


def _ordered_fields(readout: CodeVReadout) -> tuple[CodeVFieldReadout, ...]:
    fields = tuple(sorted(readout.fields, key=lambda field: field.index))
    if fields:
        return fields
    return (
        CodeVFieldReadout(
            index=1,
            definition_type=readout.field_type or "RIH",
            x=0.0,
            y=0.0,
            vuy=0.0,
            vly=0.0,
            vux=0.0,
            vlx=0.0,
        ),
    )


def _default_semi_diameter(
    readout: CodeVReadout,
    fields: tuple[CodeVFieldReadout, ...],
) -> float:
    values = [abs(_value_or_zero(readout.image_height_y_mm))]
    for field in fields:
        values.append(abs(_value_or_zero(field.x)))
        values.append(abs(_value_or_zero(field.y)))
    return max(1.0, max(values))


def _validated_wavelengths(wavelengths: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in wavelengths)
    if not values:
        raise ValueError("At least one wavelength is required")
    for value in values:
        _require_finite(value, "wavelength")
        if value <= 0.0:
            raise ValueError(f"wavelength must be positive: {value!r}")
    return values


def _normalized_field_type(value: str | None) -> str:
    return (value or "RIH").strip().upper()


def _optional_glass_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text.upper() in _AIR_GLASS_NAMES:
        return None
    return _ascii_text(text)


def _ascii_text(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise ValueError("ZMX text values cannot contain newlines")
    value.encode("ascii")
    return value


def _curvature(radius_y_mm: float | None) -> float:
    if radius_y_mm is None:
        return 0.0
    radius = float(radius_y_mm)
    if not math.isfinite(radius) or abs(radius) < 1e-15:
        return 0.0
    return 1.0 / radius


def _fmt_distance(value: float | None) -> str:
    if value is None:
        return "0"
    distance = float(value)
    if math.isinf(distance):
        return "INFINITY"
    return _fmt_number(distance)


def _fmt_values(values: Sequence[float]) -> str:
    return " ".join(_fmt_number(value) for value in values)


def _fmt_positive(value: float, field_name: str) -> str:
    numeric = float(value)
    _require_finite(numeric, field_name)
    if numeric <= 0.0:
        raise ValueError(f"{field_name} must be positive: {value!r}")
    return _fmt_number(numeric)


def _fmt_number(value: float) -> str:
    numeric = float(value)
    _require_finite(numeric, "ZMX numeric value")
    if abs(numeric) < 1e-15:
        numeric = 0.0
    return f"{numeric:.15g}"


def _require_finite(value: float, field_name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite: {value!r}")


def _value_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    return numeric if math.isfinite(numeric) else 0.0
