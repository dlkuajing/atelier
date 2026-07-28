"""CODE V database readout macros for imported Zemax prescriptions."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from app.core.engines.codev_batch import (
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    CodeVBatchResult,
    ensure_codev_safe_input_path,
    parse_codev_result_file,
    run_codev_batch,
)
from app.core.engines.zmx_import_prep import stage_zmx_for_codev

CODEV_READOUT_RESULT_SCHEMA = "atelier-codev-readout-v1"

#: Factor applied to aspheric coefficients before ``BUF EXP`` writes them.
#:
#: CODE V's export format was characterised on real hardware (2026-07-28, 18
#: known values spanning 1e17 down to 1e-20):
#:
#:   * ``|x| >= 1e-4``  -> 6 significant figures        (relative error ~1e-6)
#:   * ``1e-6 <= |x| < 1e-4`` -> **fixed 6 decimals**   (0.0000123457 -> "0.000012",
#:     2.8% error; 0.00000123457 -> "0.000001", **19% error**)
#:   * ``|x| <= 1e-7``  -> scientific, 7 significant figures
#:
#: The value in CODE V's database is full precision -- ``(SCO S1 C17)`` exported
#: "0.000059" while ``(SCO S1 C17)*1000000`` exported "59.426" for a true
#: 5.9426e-05. Only the export formatting loses digits.
#:
#: Aspheric high-order terms live at 1e-3..1e-9, i.e. straddling the bad band,
#: and production readouts already show the signature (``D = 0.000051``,
#: ``G = -0.000003``). Scaling by 1e12 moves every plausible coefficient into a
#: safe range: 1.23e-6 -> 1.23e6 and 0.13 -> 1.3e11 both export in scientific
#: notation with 7 significant figures, and 1e-24 -> 1e-12 stays scientific.
#: Measured end to end: ``0.00000123456789*1e12`` exports "1.234568e+06",
#: recovering the value with 9e-8 relative error instead of 19%.
ASPHERE_EXPORT_SCALE = 1.0e12

_READOUT_SEQUENCE_NAME = "atelier_codev_readout.seq"
_READOUT_RESULT_NAME = "atelier_codev_readout.tsv"
_READOUT_REQUIRED_KEYS = (
    "schema",
    "status",
    "source_zmx",
    "units",
    "aperture_type",
    "f_number",
    "entrance_pupil_diameter_mm",
    "num_surfaces",
    "num_fields",
    "num_wavelengths",
    "num_zooms",
    "stop_surface",
    "field_type",
    "reference_wavelength_index",
    "image_height_y_mm",
)
_READOUT_OK_RETURNCODES = {0, 1}
_ASPHERE_COEFFICIENT_LABELS = ("K", "A", "B", "C", "D", "E", "F", "G", "H", "J")
_FIELD_COORDINATE_BY_TYPE = {
    "OBJ": ("XOB", "YOB"),
    "IMG": ("XIM", "YIM"),
    "ANG": ("XAN", "YAN"),
    "RIH": ("XRI", "YRI"),
}


@dataclass(frozen=True)
class CodeVSurfaceReadout:
    """Per-surface facts read from the CODE V lens database."""

    index: int
    radius_y_mm: float | None
    thickness_mm: float | None
    semi_diameter_mm: float | None
    glass: str | None
    nd: float | None
    vd: float | None
    surface_type: str | None
    is_stop: bool
    asphere_coefficients: dict[str, float]
    vd_source: str | None = None

    def describe(self) -> dict[str, object]:
        return {
            "index": self.index,
            "radius_y_mm": self.radius_y_mm,
            "thickness_mm": self.thickness_mm,
            "semi_diameter_mm": self.semi_diameter_mm,
            "glass": self.glass,
            "nd": self.nd,
            "vd": self.vd,
            "vd_source": self.vd_source,
            "surface_type": self.surface_type,
            "is_stop": self.is_stop,
            "asphere_coefficients": self.asphere_coefficients,
        }


@dataclass(frozen=True)
class CodeVWavelengthReadout:
    """Per-wavelength value and analysis weight read from CODE V."""

    index: int
    wavelength_um: float
    weight: float

    def describe(self) -> dict[str, object]:
        return {
            "index": self.index,
            "wavelength_um": self.wavelength_um,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class CodeVFieldReadout:
    """Per-field definition and vignetting read from CODE V."""

    index: int
    definition_type: str
    x: float | None
    y: float | None
    vuy: float | None
    vly: float | None
    vux: float | None
    vlx: float | None

    def describe(self) -> dict[str, object]:
        return {
            "index": self.index,
            "definition_type": self.definition_type,
            "x": self.x,
            "y": self.y,
            "vuy": self.vuy,
            "vly": self.vly,
            "vux": self.vux,
            "vlx": self.vlx,
        }


@dataclass(frozen=True)
class CodeVReadout:
    """Structured CODE V prescription readout parsed from TSV."""

    source_zmx: str
    units: str
    aperture_type: str
    f_number: float | None
    entrance_pupil_diameter_mm: float | None
    num_surfaces: int
    num_fields: int
    num_wavelengths: int
    num_zooms: int
    stop_surface: int
    field_type: str
    reference_wavelength_index: int
    image_height_y_mm: float
    surfaces: tuple[CodeVSurfaceReadout, ...]
    fields: tuple[CodeVFieldReadout, ...]
    wavelengths: tuple[CodeVWavelengthReadout, ...]

    def describe(self) -> dict[str, object]:
        return {
            "source_zmx": self.source_zmx,
            "units": self.units,
            "aperture_type": self.aperture_type,
            "f_number": self.f_number,
            "entrance_pupil_diameter_mm": self.entrance_pupil_diameter_mm,
            "num_surfaces": self.num_surfaces,
            "num_fields": self.num_fields,
            "num_wavelengths": self.num_wavelengths,
            "num_zooms": self.num_zooms,
            "stop_surface": self.stop_surface,
            "field_type": self.field_type,
            "reference_wavelength_index": self.reference_wavelength_index,
            "image_height_y_mm": self.image_height_y_mm,
            "surfaces": [surface.describe() for surface in self.surfaces],
            "fields": [field.describe() for field in self.fields],
            "wavelengths": [wavelength.describe() for wavelength in self.wavelengths],
        }


@dataclass(frozen=True)
class CodeVReadoutResult:
    """A completed CODE V readout batch and its parsed prescription facts."""

    batch: CodeVBatchResult
    source_zmx: Path
    staged_zmx: Path | None
    readout: CodeVReadout

    @property
    def data(self) -> dict[str, str]:
        return self.batch.data

    def describe(self) -> dict[str, object]:
        return {
            "batch": self.batch.describe(),
            "source_zmx": str(self.source_zmx),
            "staged_zmx": str(self.staged_zmx) if self.staged_zmx else None,
            "readout": self.readout.describe(),
        }


def build_codev_readout_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
) -> str:
    """Build a CODE V macro that imports ZMX and exports database items as TSV."""

    source_zmx = Path(source_zmx)
    ensure_codev_safe_input_path(source_zmx, role="source_zmx")
    result_path = Path(result_path)
    lines = [
        "! Generated by app.core.engines.codev_readout.",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "^row == 1",
        "^refw == (REF)",
        "^numsur == (NUM S)",
        "^numfld == (NUM F)",
        "^numwav == (NUM W)",
        "^numz == (NUM Z)",
        "^stop == (STO)",
        "^units == (DIM)",
        "^apetype == (TYP APE)",
        "^field_type == (TYP FLD)",
        "^maximh == 0",
        "^pi == 4*ATANF(1)",
        "^deg_to_rad == ^pi/180",
        "^efy == ABSF((EFY))",
        "FOR ^f 1 ^numfld",
        "  ^yh == (YRI F^f Z1)",
        '  IF ^field_type = "ANG"',
        "    ^field_angle_y == (YAN F^f Z1)",
        "    ^field_angle_y_rad == ^field_angle_y * ^deg_to_rad",
        "    ^yh == ^efy * TANF(^field_angle_y_rad)",
        '  ELS IF ^field_type = "IMG"',
        "    ^yh == (YIM F^f Z1)",
        "  END IF",
        "  IF ABSF(^yh) > ^maximh",
        "    ^maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
    ]

    _append_put_row(lines, '"schema"', f'"{CODEV_READOUT_RESULT_SCHEMA}"')
    _append_put_row(lines, '"status"', '"ok"')
    _append_put_row(lines, '"source_zmx"', f'"{source_zmx.name}"')
    _append_put_row(lines, '"units"', "^units")
    _append_put_row(lines, '"aperture_type"', "^apetype")
    _append_put_row(lines, '"f_number"', "(FNO)")
    _append_put_row(lines, '"entrance_pupil_diameter_mm"', "(EPD)")
    _append_put_row(lines, '"num_surfaces"', "^numsur")
    _append_put_row(lines, '"num_fields"', "^numfld")
    _append_put_row(lines, '"num_wavelengths"', "^numwav")
    _append_put_row(lines, '"num_zooms"', "^numz")
    _append_put_row(lines, '"stop_surface"', "^stop")
    _append_put_row(lines, '"field_type"', "^field_type")
    _append_put_row(lines, '"reference_wavelength_index"', "^refw")
    _append_put_row(lines, '"image_height_y_mm"', "^maximh")

    lines.extend(
        [
            "FOR ^s 1 ^numsur",
            '  ^surface_prefix == "surface."',
            "  ^surface_prefix == CONCAT(^surface_prefix, NUM_TO_STR(^s))",
            "  ^surf_type == (TYP SUR S^s)",
            "  ^glass == (GLA S^s)",
            "  ^nd == ABSF((IND S^s W^refw))",
            "  ^vd == 0",
            "  IF (NUM W) >= 3",
            "    ^n1 == ABSF((IND S^s W1))",
            "    ^nl == ABSF((IND S^s WL))",
            "    ^diffn == ^nl - ^n1",
            "    IF ABSF(^diffn) > 1.0E-12",
            "      ^vd == (^nd - 1) / ^diffn",
            "    END IF",
            "  END IF",
            "  ^isstop == 0",
            "  IF ^s = ^stop",
            "    ^isstop == 1",
            "  END IF",
            "  ^coefK == 0",
            "  ^coefA == 0",
            "  ^coefB == 0",
            "  ^coefC == 0",
            "  ^coefD == 0",
            "  ^coefE == 0",
            "  ^coefF == 0",
            "  ^coefG == 0",
            "  ^coefH == 0",
            "  ^coefJ == 0",
            '  IF ^surf_type = "ASP"',
            "    ^coefK == (K S^s)",
            "    ^coefA == (A S^s)",
            "    ^coefB == (B S^s)",
            "    ^coefC == (C S^s)",
            "    ^coefD == (D S^s)",
            "    ^coefE == (E S^s)",
            "    ^coefF == (F S^s)",
            "    ^coefG == (G S^s)",
            "    ^coefH == (H S^s)",
            "    ^coefJ == (J S^s)",
            '  ELS IF ^surf_type = "CON"',
            "    ^coefK == (K S^s)",
            "  END IF",
        ]
    )
    _append_dynamic_surface_row(lines, ".radius_y_mm", "(RDY S^s)")
    _append_dynamic_surface_row(lines, ".thickness_mm", "(THI S^s)")
    _append_dynamic_surface_row(lines, ".semi_diameter_mm", "(MAP S^s)")
    _append_dynamic_surface_row(lines, ".glass", "^glass")
    _append_dynamic_surface_row(lines, ".nd", "^nd")
    _append_dynamic_surface_row(lines, ".vd", "^vd")
    _append_dynamic_surface_row(lines, ".surface_type", "^surf_type")
    _append_dynamic_surface_row(lines, ".is_stop", "^isstop")
    for label in _ASPHERE_COEFFICIENT_LABELS:
        _append_dynamic_surface_row(lines, f".asphere.{label}", f"^coef{label}")
        # Scaled twin -- see ASPHERE_EXPORT_SCALE. CODE V's BUF EXP writes a
        # value like 1.23e-06 as the fixed-point "0.000001", a 19% error, and
        # aspheric high-order terms sit squarely in that band. Multiplying into
        # the safe range before export costs one extra row per coefficient.
        _append_dynamic_surface_row(
            lines,
            f".asphere_scaled.{label}",
            f"^coef{label}*{ASPHERE_EXPORT_SCALE:.0f}",
        )
    lines.append("END FOR")

    lines.extend(
        [
            "FOR ^w 1 ^numwav",
            '  ^wavelength_prefix == "wavelength."',
            "  ^wavelength_prefix == CONCAT(^wavelength_prefix, NUM_TO_STR(^w))",
        ]
    )
    _append_dynamic_wavelength_row(lines, ".wavelength_nm", "(WL W^w)")
    _append_dynamic_wavelength_row(lines, ".weight", "(WTW Z1 W^w)")
    lines.append("END FOR")

    lines.extend(
        [
            "FOR ^f 1 ^numfld",
            '  ^field_prefix == "field."',
            "  ^field_prefix == CONCAT(^field_prefix, NUM_TO_STR(^f))",
            "  ^field_x == 0",
            "  ^field_y == 0",
            '  IF ^field_type = "OBJ"',
            "    ^field_x == (XOB F^f Z1)",
            "    ^field_y == (YOB F^f Z1)",
            '  ELS IF ^field_type = "IMG"',
            "    ^field_x == (XIM F^f Z1)",
            "    ^field_y == (YIM F^f Z1)",
            '  ELS IF ^field_type = "ANG"',
            "    ^field_x == (XAN F^f Z1)",
            "    ^field_y == (YAN F^f Z1)",
            "  ELS",
            "    ^field_x == (XRI F^f Z1)",
            "    ^field_y == (YRI F^f Z1)",
            "  END IF",
        ]
    )
    _append_dynamic_field_row(lines, ".definition_type", "^field_type")
    _append_dynamic_field_row(lines, ".x", "^field_x")
    _append_dynamic_field_row(lines, ".y", "^field_y")
    _append_dynamic_field_row(lines, ".vuy", "(VUY F^f Z1)")
    _append_dynamic_field_row(lines, ".vly", "(VLY F^f Z1)")
    _append_dynamic_field_row(lines, ".vux", "(VUX F^f Z1)")
    _append_dynamic_field_row(lines, ".vlx", "(VLX F^f Z1)")
    lines.extend(
        [
            "END FOR",
            f"BUF EXP B1 {_quote_codev_path(result_path)}",
            "BUF DEL B1",
            "OUT YES",
            "EXI YES",
            "",
        ]
    )
    return "\n".join(lines)


def write_codev_readout_sequence(
    *,
    sequence_path: Path | str,
    source_zmx: Path | str,
    result_path: Path | str,
) -> Path:
    """Write the CODE V readout macro and return the sequence path."""

    sequence_path = Path(sequence_path)
    sequence_path.parent.mkdir(parents=True, exist_ok=True)
    sequence_path.write_text(
        build_codev_readout_sequence(source_zmx=source_zmx, result_path=result_path),
        encoding="ascii",
    )
    return sequence_path


def run_codev_readout(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 90.0,
    platform_name: str = os.name,
) -> CodeVReadoutResult:
    """Import one ZMX into CODE V and read database-backed prescription facts."""

    source_zmx = Path(source_zmx).resolve()
    work_dir = Path(work_dir).resolve()
    ensure_codev_safe_input_path(work_dir, role="work_dir")
    work_dir.mkdir(parents=True, exist_ok=True)
    # Always import through a staged copy: the WAVM table needs a flush
    # sentinel or CODE V silently drops to one default wavelength, which also
    # takes every vd with it (see zmx_import_prep). Staging doubles as the
    # escape hatch for source paths CODE V cannot open.
    staged_zmx: Path | None = stage_zmx_for_codev(source_zmx, work_dir)
    import_zmx = staged_zmx
    sequence_path = work_dir / _READOUT_SEQUENCE_NAME
    result_path = work_dir / _READOUT_RESULT_NAME
    write_codev_readout_sequence(
        sequence_path=sequence_path,
        source_zmx=import_zmx,
        result_path=result_path,
    )
    batch = run_codev_batch(
        sequence_path=sequence_path,
        result_path=result_path,
        executable=executable,
        work_dir=work_dir,
        timeout_seconds=timeout_seconds,
        platform_name=platform_name,
        expected_schema=CODEV_READOUT_RESULT_SCHEMA,
        required_keys=_READOUT_REQUIRED_KEYS,
        allow_nonzero_ok_result=True,
    )
    if batch.returncode not in _READOUT_OK_RETURNCODES:
        raise CodeVBatchError(
            "failure",
            "CODE V readout exited with an unsupported returncode despite an ok result file",
            details={
                "returncode": batch.returncode,
                "allowed_returncodes": sorted(_READOUT_OK_RETURNCODES),
                "data": batch.data,
                "result_path": str(batch.result_path),
            },
        )
    return CodeVReadoutResult(
        batch=batch,
        source_zmx=source_zmx,
        staged_zmx=staged_zmx,
        readout=parse_codev_readout_data(batch.data),
    )


def parse_codev_readout_file(result_path: Path | str) -> CodeVReadout:
    """Parse a CODE V readout TSV exported by ``BUF EXP``."""

    data = parse_codev_result_file(
        result_path,
        expected_schema=CODEV_READOUT_RESULT_SCHEMA,
        required_keys=_READOUT_REQUIRED_KEYS,
    )
    return parse_codev_readout_data(data)


def parse_codev_readout_data(data: Mapping[str, str]) -> CodeVReadout:
    """Convert flat readout TSV keys into a structured prescription model."""

    if data.get("schema") != CODEV_READOUT_RESULT_SCHEMA:
        raise CodeVBatchError(
            "failure",
            "CODE V readout data has an unexpected schema",
            details={
                "expected_schema": CODEV_READOUT_RESULT_SCHEMA,
                "actual_schema": data.get("schema"),
            },
        )
    if data.get("status") != "ok":
        raise CodeVBatchError(
            "failure",
            "CODE V readout data reported a non-ok status",
            details={"status": data.get("status")},
        )

    num_surfaces = _required_int(data, "num_surfaces")
    num_fields = _required_int(data, "num_fields")
    num_wavelengths = _required_int(data, "num_wavelengths")
    stop_surface = _required_int(data, "stop_surface")
    field_type = _required_text(data, "field_type")
    return CodeVReadout(
        source_zmx=_required_text(data, "source_zmx"),
        units=_required_text(data, "units"),
        aperture_type=_required_text(data, "aperture_type"),
        f_number=_required_float(data, "f_number"),
        entrance_pupil_diameter_mm=_required_float(data, "entrance_pupil_diameter_mm"),
        num_surfaces=num_surfaces,
        num_fields=num_fields,
        num_wavelengths=num_wavelengths,
        num_zooms=_required_int(data, "num_zooms"),
        stop_surface=stop_surface,
        field_type=field_type,
        reference_wavelength_index=_required_int(data, "reference_wavelength_index"),
        image_height_y_mm=_required_float(data, "image_height_y_mm"),
        surfaces=tuple(
            _parse_surface(data, surface_index, stop_surface=stop_surface)
            for surface_index in range(1, num_surfaces + 1)
        ),
        fields=tuple(
            _parse_field(data, field_index, default_field_type=field_type)
            for field_index in range(1, num_fields + 1)
        ),
        wavelengths=tuple(
            _parse_wavelength(data, wavelength_index)
            for wavelength_index in range(1, num_wavelengths + 1)
        ),
    )


def _parse_surface(
    data: Mapping[str, str],
    surface_index: int,
    *,
    stop_surface: int,
) -> CodeVSurfaceReadout:
    prefix = f"surface.{surface_index}"
    coefficients = {
        label: value
        for label in _ASPHERE_COEFFICIENT_LABELS
        if (value := _asphere_coefficient(data, prefix, label)) is not None
    }
    is_stop = _optional_bool(data.get(f"{prefix}.is_stop"))
    glass = _optional_text(data.get(f"{prefix}.glass"))
    nd = _optional_float(data.get(f"{prefix}.nd"))
    vd = _optional_float(data.get(f"{prefix}.vd"))
    # Real-machine evidence (2026-07-11) proves GLA fractional digits are
    # import-name mangling debris, not dispersion. Declared 546401.540607
    # (nd=1.5464, vd=54.0607) reads back as 546000.401540; the same rule fits
    # 542965.529055, 639236.228034, 539906.552927, 638139.228307, and
    # 550536.504741. Seed-path names such as 544000.559000 can survive
    # verbatim, so only the macro's measured dispersion is admissible.
    if vd in (None, 0.0):
        vd = None
        vd_source = None
    else:
        vd_source = "dispersion-measured"
    return CodeVSurfaceReadout(
        index=surface_index,
        radius_y_mm=_required_float(data, f"{prefix}.radius_y_mm"),
        thickness_mm=_required_float(data, f"{prefix}.thickness_mm"),
        semi_diameter_mm=_required_float(data, f"{prefix}.semi_diameter_mm"),
        glass=glass,
        nd=nd,
        vd=vd,
        vd_source=vd_source,
        surface_type=_optional_text(data.get(f"{prefix}.surface_type")),
        is_stop=(surface_index == stop_surface if is_stop is None else is_stop),
        asphere_coefficients=coefficients,
    )


def _asphere_coefficient(data: Mapping[str, str], prefix: str, label: str) -> float | None:
    """One aspheric coefficient, preferring the precision-preserving twin.

    The scaled row is authoritative when present (see ``ASPHERE_EXPORT_SCALE``).
    Result files written before it existed carry only the unscaled row, and
    those are read as-is rather than rejected -- the value is degraded, not
    absent, and refusing to parse old artefacts would buy nothing.
    """

    scaled = _optional_float(data.get(f"{prefix}.asphere_scaled.{label}"))
    if scaled is not None:
        return scaled / ASPHERE_EXPORT_SCALE
    return _optional_float(data.get(f"{prefix}.asphere.{label}"))


def _parse_field(
    data: Mapping[str, str],
    field_index: int,
    *,
    default_field_type: str,
) -> CodeVFieldReadout:
    prefix = f"field.{field_index}"
    return CodeVFieldReadout(
        index=field_index,
        definition_type=_optional_text(data.get(f"{prefix}.definition_type")) or default_field_type,
        x=_required_float(data, f"{prefix}.x"),
        y=_required_float(data, f"{prefix}.y"),
        vuy=_required_float(data, f"{prefix}.vuy"),
        vly=_required_float(data, f"{prefix}.vly"),
        vux=_required_float(data, f"{prefix}.vux"),
        vlx=_required_float(data, f"{prefix}.vlx"),
    )


def _parse_wavelength(data: Mapping[str, str], wavelength_index: int) -> CodeVWavelengthReadout:
    prefix = f"wavelength.{wavelength_index}"
    wavelength_nm = _required_float(data, f"{prefix}.wavelength_nm")
    return CodeVWavelengthReadout(
        index=wavelength_index,
        wavelength_um=wavelength_nm / 1000.0,
        weight=_required_float(data, f"{prefix}.weight"),
    )


def _append_put_row(lines: list[str], key: str, value: str) -> None:
    lines.append(f"BUF PUT B1 I^row J1 {key}")
    lines.append(f"BUF PUT B1 I^row J2 {value}")
    lines.append("^row == ^row+1")


def _append_dynamic_surface_row(lines: list[str], suffix: str, value: str) -> None:
    lines.append(f'  ^key == CONCAT(^surface_prefix, "{suffix}")')
    lines.append("  BUF PUT B1 I^row J1 ^key")
    lines.append(f"  BUF PUT B1 I^row J2 {value}")
    lines.append("  ^row == ^row+1")


def _append_dynamic_field_row(lines: list[str], suffix: str, value: str) -> None:
    lines.append(f'  ^key == CONCAT(^field_prefix, "{suffix}")')
    lines.append("  BUF PUT B1 I^row J1 ^key")
    lines.append(f"  BUF PUT B1 I^row J2 {value}")
    lines.append("  ^row == ^row+1")


def _append_dynamic_wavelength_row(lines: list[str], suffix: str, value: str) -> None:
    lines.append(f'  ^key == CONCAT(^wavelength_prefix, "{suffix}")')
    lines.append("  BUF PUT B1 I^row J1 ^key")
    lines.append(f"  BUF PUT B1 I^row J2 {value}")
    lines.append("  ^row == ^row+1")


def _required_text(data: Mapping[str, str], key: str) -> str:
    value = _optional_text(data.get(key))
    if value is None:
        _raise_missing_key(key)
    return value


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _required_int(data: Mapping[str, str], key: str) -> int:
    return int(_required_float(data, key))


def _required_float(data: Mapping[str, str], key: str) -> float:
    value = _optional_float(data.get(key))
    if value is None:
        _raise_missing_key(key)
    return value


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.upper() in {"NA", "N/A", "NONE", "NULL"}:
        return None
    try:
        return float(stripped)
    except ValueError as exc:
        raise CodeVBatchError(
            "failure",
            "CODE V readout data contains a non-numeric value",
            details={"value": value},
        ) from exc


def _optional_bool(value: str | None) -> bool | None:
    text = _optional_text(value)
    if text is None:
        return None
    normalized = text.lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise CodeVBatchError(
        "failure",
        "CODE V readout data contains a non-boolean value",
        details={"value": value},
    )


def _raise_missing_key(key: str) -> None:
    raise CodeVBatchError(
        "failure",
        "CODE V readout data is missing a required field",
        details={"missing_key": key},
    )


def _quote_codev_path(path: Path) -> str:
    value = str(path)
    if any(char in value for char in ('"', "\r", "\n")):
        raise ValueError(f"CODE V path cannot contain quotes or newlines: {value!r}")
    return f'"{value}"'
