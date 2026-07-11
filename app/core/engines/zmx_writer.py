"""Zemax text writer for CODE V prescription readouts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from app.core.engines.codev_readout import (
    CodeVFieldReadout,
    CodeVReadout,
    CodeVSurfaceReadout,
    CodeVWavelengthReadout,
)
from app.core.zmx_materials import _CODEV_MODEL_GLASS_MARKER_RE

_WRITABLE_ASPHERE_TERMS: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G")
_UNSUPPORTED_EVENASPH_TERMS: tuple[str, ...] = ("H", "J")
_AIR_GLASS_NAMES = {"", "AIR", "NONE", "NULL"}
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
_APERTURE_TYPES = {"FNO", "EPD"}


def build_zmx_from_codev_readout(
    readout: CodeVReadout,
    *,
    name: str | None = None,
    f_number: float | None = None,
    entrance_pupil_diameter_mm: float | None = None,
    wavelengths_um: Sequence[float] | None = None,
    semi_diameter_mm: float | None = None,
) -> str:
    """Return an ASCII Zemax ``.zmx`` prescription with LF newlines.

    The input is the structured readout produced by ``codev_readout``. CODE V
    exposes vignetting as upper/lower pupil limits; Zemax stores equivalent
    decenter/compression arrays, so both ``VDXN/VDYN`` and ``VCXN/VCYN`` are
    emitted to preserve the four readout values.

    Line endings MUST be LF: real-machine proof (2026-07-11, byte-identical
    A/B import of the same 24-slot file) shows CRLF endings break
    ZEMAXOS_TO_CV's WAVM wavelength parsing — the lens imports with NO
    wavelength data ("No wavelength data specified"), silently killing
    dispersion/vd and chromatic evaluation. The LF variant imports all
    wavelengths and yields dispersion-measured vd. The seed corpus in
    data/zmx/ is LF on disk and imports correctly.
    """

    surfaces = _ordered_surfaces(readout)
    fields = _ordered_fields(readout)
    wavelengths = _resolved_wavelengths(readout, wavelengths_um=wavelengths_um)
    system_name = _ascii_text(name or Path(readout.source_zmx).stem)

    lines: list[str] = [
        "VERS 191028 13541 33913 33913",
        "MODE SEQ",
        f"NAME {system_name}",
        "UNIT MM X W X CM MR CPMM",
    ]
    _append_aperture(
        lines,
        readout,
        f_number=f_number,
        entrance_pupil_diameter_mm=entrance_pupil_diameter_mm,
    )
    _append_fields(lines, readout, fields, wavelengths)
    _append_wavelengths(lines, wavelengths, readout.reference_wavelength_index)
    _append_object_surface(lines)
    for surface in surfaces:
        _append_surface(lines, surface, semi_diameter_override_mm=semi_diameter_mm)

    text = "\n".join(lines) + "\n"
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
    """Write a CODE V readout as an ASCII/LF Zemax file and return its path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_zmx_from_codev_readout(readout, **kwargs).encode("ascii"))
    return path


def write_zmx_text(readout: CodeVReadout, output_path: Path | str, **kwargs: object) -> Path:
    """Compatibility alias for writing the generated ZMX text to disk."""

    return write_zmx_from_codev_readout(readout, output_path, **kwargs)


def _append_aperture(
    lines: list[str],
    readout: CodeVReadout,
    *,
    f_number: float | None,
    entrance_pupil_diameter_mm: float | None,
) -> None:
    if f_number is not None and entrance_pupil_diameter_mm is not None:
        raise ValueError("Only one of f_number or entrance_pupil_diameter_mm can be provided")
    if entrance_pupil_diameter_mm is not None:
        lines.append(f"ENPD {_fmt_positive(entrance_pupil_diameter_mm, 'entrance_pupil_diameter_mm')}")
        return
    if f_number is not None:
        lines.append(f"FNUM {_fmt_positive(f_number, 'f_number')} 0")
        return

    aperture_type = _normalized_aperture_type(readout.aperture_type)
    if aperture_type == "FNO":
        if readout.f_number is None:
            raise ValueError("CODE V readout is missing f_number for FNO aperture")
        lines.append(f"FNUM {_fmt_positive(readout.f_number, 'f_number')} 0")
        return
    if aperture_type == "EPD":
        if readout.entrance_pupil_diameter_mm is None:
            raise ValueError("CODE V readout is missing entrance_pupil_diameter_mm for EPD aperture")
        lines.append(
            "ENPD "
            f"{_fmt_positive(readout.entrance_pupil_diameter_mm, 'entrance_pupil_diameter_mm')}"
        )
        return
    raise ValueError(
        "CODE V readout aperture_type must be one of FNO or EPD",
        {"aperture_type": readout.aperture_type},
    )


def _append_fields(
    lines: list[str],
    readout: CodeVReadout,
    fields: tuple[CodeVFieldReadout, ...],
    wavelengths: tuple[CodeVWavelengthReadout, ...],
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
    wavelengths: tuple[CodeVWavelengthReadout, ...],
    readout_primary_index: int,
) -> None:
    for wavelength in wavelengths:
        lines.append(
            f"WAVM {wavelength.index} "
            f"{_fmt_number(wavelength.wavelength_um)} {_fmt_number(wavelength.weight)}"
        )
    for slot in range(len(wavelengths) + 1, 25):
        lines.append(f"WAVM {slot} 0.55 1")
    primary = readout_primary_index
    if primary < 1 or primary > len(wavelengths):
        raise ValueError(
            "CODE V readout reference_wavelength_index is outside the wavelength table",
            {
                "reference_wavelength_index": readout_primary_index,
                "num_wavelengths": len(wavelengths),
            },
        )
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
    semi_diameter_override_mm: float | None,
) -> None:
    surface_type = _zemax_surface_type(surface)
    semi_diameter = _surface_semi_diameter(surface, override_mm=semi_diameter_override_mm)
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
    # CODE V A..G. CODE V H/J correspond to r^18/r^20 and do not fit here.
    _reject_nonzero_unsupported_evenasphere_terms(surface)
    lines.append("  PARM 1 0")
    for offset, label in enumerate(_WRITABLE_ASPHERE_TERMS, start=2):
        value = surface.asphere_coefficients.get(label, 0.0)
        lines.append(f"  PARM {offset} {_fmt_number(value)}")


def _glass_line(surface: CodeVSurfaceReadout) -> str | None:
    nd = surface.nd
    vd = surface.vd
    if nd is None or not math.isfinite(nd):
        return None
    # Unknown dispersion is NOT air: single-wavelength CODE V imports (short
    # WAVM tables, see the LF/WAVM dossier) yield vd=None after PR#70 made vd
    # fail-closed. Dropping the whole GLAS here rebuilt every such candidate
    # as an all-air system (-inf EFL, real-machine regression 2026-07-11).
    # Zemax's own convention for "index known, dispersion unspecified" is
    # vd=0 — keep the measured nd, write vd 0.
    if vd is None or not math.isfinite(vd):
        vd = 0.0
    if nd <= 1.000001:
        return None
    name = _optional_glass_name(surface.glass)
    if name is None:
        return None
    # Model glass needs flag=1 both for plain "___BLANK" and for the repair
    # marker form "<trade-name>_BLANK" (scripts/repair_legacy_zmx_glass.py):
    # CODE V echoes the marker name back in its readout, and a rebuilt ZMX
    # emitted with flag=0 would carry catalog-name semantics that real Zemax
    # (and a second ZEMAXOS_TO_CV import, e.g. Stage-B or 资深 Verify)
    # resolves as AIR — reproducing the all-air seed bug on the deliverable.
    is_model_glass = (
        name.upper() == "___BLANK"
        or _CODEV_MODEL_GLASS_MARKER_RE.search(name.upper()) is not None
    )
    model_flag = 1 if is_model_glass else 0
    return f"  GLAS {name} {model_flag} 0 {_fmt_number(nd)} {_fmt_number(vd)} 0 0 0 0 0 0 "


def _zemax_surface_type(surface: CodeVSurfaceReadout) -> str:
    raw_type = (surface.surface_type or "").strip().upper()
    has_even_terms = any(
        abs(surface.asphere_coefficients.get(label, 0.0)) > 0.0
        for label in (*_WRITABLE_ASPHERE_TERMS, *_UNSUPPORTED_EVENASPH_TERMS)
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
    raise ValueError("CODE V readout has no fields")


def _surface_semi_diameter(
    surface: CodeVSurfaceReadout,
    *,
    override_mm: float | None,
) -> float:
    if override_mm is not None:
        return _positive_number(override_mm, "semi_diameter_mm")
    if surface.semi_diameter_mm is None:
        raise ValueError(
            "CODE V readout is missing surface semi_diameter_mm",
            {"surface_index": surface.index},
        )
    return _positive_number(surface.semi_diameter_mm, "semi_diameter_mm")


def _resolved_wavelengths(
    readout: CodeVReadout,
    *,
    wavelengths_um: Sequence[float] | None,
) -> tuple[CodeVWavelengthReadout, ...]:
    if wavelengths_um is not None:
        return _validated_wavelengths(wavelengths_um)
    wavelengths = tuple(sorted(readout.wavelengths, key=lambda wavelength: wavelength.index))
    if not wavelengths:
        raise ValueError("CODE V readout has no wavelength table")
    for wavelength in wavelengths:
        _positive_number(wavelength.wavelength_um, "wavelength_um")
        _require_finite(wavelength.weight, "wavelength_weight")
    return wavelengths


def _validated_wavelengths(wavelengths: Sequence[float]) -> tuple[CodeVWavelengthReadout, ...]:
    values = tuple(
        CodeVWavelengthReadout(index=index, wavelength_um=float(value), weight=1.0)
        for index, value in enumerate(wavelengths, start=1)
    )
    if not values:
        raise ValueError("At least one wavelength is required")
    for value in values:
        _positive_number(value.wavelength_um, "wavelength_um")
    return values


def _normalized_aperture_type(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    return normalized if normalized in _APERTURE_TYPES else normalized


def _normalized_field_type(value: str | None) -> str:
    return (value or "RIH").strip().upper()


def _optional_glass_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text.upper() in _AIR_GLASS_NAMES:
        return None
    return _ascii_text(text)


def _reject_nonzero_unsupported_evenasphere_terms(surface: CodeVSurfaceReadout) -> None:
    unsupported = {
        label: value
        for label in _UNSUPPORTED_EVENASPH_TERMS
        if (value := surface.asphere_coefficients.get(label, 0.0)) != 0.0
    }
    if unsupported:
        raise ValueError(
            "EVENASPH supports only PARM 1..8; CODE V H/J would require r^18/r^20",
            {
                "surface_index": surface.index,
                "unsupported_coefficients": unsupported,
                "supported_mapping": "A..G -> PARM 2..8",
            },
        )


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
    return _fmt_number(_positive_number(value, field_name))


def _fmt_number(value: float) -> str:
    numeric = float(value)
    _require_finite(numeric, "ZMX numeric value")
    if abs(numeric) < 1e-15:
        numeric = 0.0
    return f"{numeric:.15g}"


def _require_finite(value: float, field_name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite: {value!r}")


def _positive_number(value: float, field_name: str) -> float:
    numeric = float(value)
    _require_finite(numeric, field_name)
    if numeric <= 0.0:
        raise ValueError(f"{field_name} must be positive: {value!r}")
    return numeric


def _value_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    numeric = float(value)
    return numeric if math.isfinite(numeric) else 0.0
