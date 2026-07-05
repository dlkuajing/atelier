"""CODE V ZMX import smoke and ZMX fidelity comparison helpers."""

from __future__ import annotations

import codecs
import math
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.engines.codev_batch import (
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchResult,
    run_codev_batch,
)
from app.core.engines.codev_readout import CodeVReadoutResult, run_codev_readout
from app.core.engines.zmx_writer import write_zmx_from_codev_readout
from app.core.prescription_table import PrescriptionTable, extract_prescription_table
from app.core.zmx_ingest import ZMX_AMMO_DIR, load_normalized_zmx

CODEV_ROUNDTRIP_RESULT_SCHEMA = "atelier-codev-roundtrip-v1"
DEFAULT_PATENT_ROUNDTRIP_SEED = "US20170003482A1.zmx"
EFL_REL_TOLERANCE_PCT = 2.0

_ROUNDTRIP_SEQUENCE_NAME = "atelier_codev_zmx_import.seq"
_ROUNDTRIP_RESULT_NAME = "atelier_codev_zmx_import.tsv"
_ROUNDTRIP_COMMAND_EXPORT_NAME = "atelier_codev_roundtrip_export.seq"
_ROUNDTRIP_REQUIRED_KEYS = (
    "schema",
    "status",
    "source_zmx",
    "efl_y_mm",
    "max_image_height_y_mm",
    "num_surfaces",
    "num_fields",
    "native_zmx_export",
    "command_export_path",
)
_VIGNETTING_ALIASES = {
    "VDX": "VDX",
    "VDXN": "VDX",
    "ZVDX": "VDX",
    "VDY": "VDY",
    "VDYN": "VDY",
    "ZVDY": "VDY",
    "VCX": "VCX",
    "VCXN": "VCX",
    "ZVCX": "VCX",
    "VCY": "VCY",
    "VCYN": "VCY",
    "ZVCY": "VCY",
}


@dataclass(frozen=True)
class CodeVZmxImportResult:
    """Structured facts from a CODE V import of one Zemax file."""

    batch: CodeVBatchResult
    source_zmx: Path
    command_export_path: Path

    @property
    def data(self) -> dict[str, str]:
        return self.batch.data

    @property
    def efl_y_mm(self) -> float:
        return float(self.data["efl_y_mm"])

    @property
    def max_image_height_y_mm(self) -> float:
        return float(self.data["max_image_height_y_mm"])


@dataclass(frozen=True)
class GlassRow:
    """Per-surface glass facts from zmx_ingest normalization."""

    surface_index: int
    glass: str | None
    nd: float
    vd: float


@dataclass(frozen=True)
class ZmxFidelityFacts:
    """Comparable facts extracted from a ZMX through zmx_ingest."""

    path: Path
    efl_mm: float
    f_number: float | None
    entrance_pupil_diameter_mm: float | None
    wavelength_count: int
    glass_rows: tuple[GlassRow, ...]
    asphere_term_counts: dict[int, int]
    asphere_coefficients: dict[int, tuple[float, ...]]
    vignetting: dict[str, tuple[float, ...]]


@dataclass(frozen=True)
class ZmxRoundTripComparison:
    """Fidelity comparison between source and round-tripped ZMX files."""

    source: ZmxFidelityFacts
    exported: ZmxFidelityFacts
    efl_deviation_pct: float
    glass_mismatches: tuple[str, ...]
    asphere_term_mismatches: tuple[str, ...]
    vignetting_mismatches: tuple[str, ...]

    @property
    def efl_within_tolerance(self) -> bool:
        return self.efl_deviation_pct < EFL_REL_TOLERANCE_PCT

    @property
    def passed(self) -> bool:
        return (
            self.efl_within_tolerance
            and not self.glass_mismatches
            and not self.asphere_term_mismatches
            and not self.vignetting_mismatches
        )

    def describe(self) -> dict[str, object]:
        return {
            "source_zmx": str(self.source.path),
            "exported_zmx": str(self.exported.path),
            "efl_deviation_pct": self.efl_deviation_pct,
            "efl_within_2pct": self.efl_within_tolerance,
            "source_f_number": self.source.f_number,
            "exported_f_number": self.exported.f_number,
            "source_entrance_pupil_diameter_mm": self.source.entrance_pupil_diameter_mm,
            "exported_entrance_pupil_diameter_mm": self.exported.entrance_pupil_diameter_mm,
            "source_wavelength_count": self.source.wavelength_count,
            "exported_wavelength_count": self.exported.wavelength_count,
            "glass_mismatches": list(self.glass_mismatches),
            "asphere_term_mismatches": list(self.asphere_term_mismatches),
            "vignetting_mismatches": list(self.vignetting_mismatches),
            "passed": self.passed,
        }


@dataclass(frozen=True)
class CodeVRoundTripCloseResult:
    """Completed ENGINE-04c readout -> rebuilt ZMX -> comparison loop."""

    source_zmx: Path
    readout: CodeVReadoutResult
    exported_zmx: Path
    comparison: ZmxRoundTripComparison

    def describe(self) -> dict[str, object]:
        return {
            "source_zmx": str(self.source_zmx),
            "readout": self.readout.describe(),
            "exported_zmx": str(self.exported_zmx),
            "comparison": self.comparison.describe(),
        }


def default_patent_roundtrip_seed() -> Path:
    """Return the selected patent seed for ENGINE-03c."""

    return ZMX_AMMO_DIR / DEFAULT_PATENT_ROUNDTRIP_SEED


def build_zmx_import_sequence(
    *,
    source_zmx: Path | str,
    result_path: Path | str,
    command_export_path: Path | str,
) -> str:
    """Build a CODE V macro that imports ZMX and writes explicit metrics TSV.

    CODE V 11.5 ships the official ``CV_MACRO:ZEMAXOS_TO_CV`` import macro. Its
    documented command-file export is ``WRL``; that artifact is intentionally
    labeled as a command export, not as a Zemax ZMX export.
    """

    source_zmx = Path(source_zmx)
    result_path = Path(result_path)
    command_export_path = Path(command_export_path)
    rows = (
        ("schema", f'"{CODEV_ROUNDTRIP_RESULT_SCHEMA}"'),
        ("status", '"ok"'),
        ("source_zmx", f'"{source_zmx.name}"'),
        ("efl_y_mm", "(EFY)"),
        ("max_image_height_y_mm", "^maximh"),
        ("num_surfaces", "(NUM S)"),
        ("num_fields", "(NUM F)"),
        ("native_zmx_export", '"unavailable_in_codev_11_5_docs"'),
        ("command_export_path", f'"{command_export_path.name}"'),
    )

    lines = [
        "! Generated by app.core.engines.codev_roundtrip.",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "^maximh == 0",
        "FOR ^f 1 (NUM F)",
        "  ^yh == (YRI F^f Z1)",
        "  IF ABSF(^yh) > ^maximh",
        "    ^maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
    ]
    for index, (key, value) in enumerate(rows, start=1):
        lines.append(f'BUF PUT B1 I{index} J1 "{key}"')
        lines.append(f"BUF PUT B1 I{index} J2 {value}")
    lines.extend(
        [
            f"BUF EXP B1 {_quote_codev_path(result_path)}",
            "BUF DEL B1",
            f"WRL {_quote_codev_path(command_export_path)}",
            "OUT YES",
            "EXI YES",
            "",
        ]
    )
    return "\n".join(lines)


def write_zmx_import_sequence(
    *,
    sequence_path: Path | str,
    source_zmx: Path | str,
    result_path: Path | str,
    command_export_path: Path | str,
) -> Path:
    """Write a CODE V ZMX import sequence and return its path."""

    sequence_path = Path(sequence_path)
    sequence_path.parent.mkdir(parents=True, exist_ok=True)
    sequence_path.write_text(
        build_zmx_import_sequence(
            source_zmx=source_zmx,
            result_path=result_path,
            command_export_path=command_export_path,
        ),
        encoding="ascii",
    )
    return sequence_path


def run_codev_zmx_import(
    *,
    source_zmx: Path | str,
    work_dir: Path | str,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 90.0,
    platform_name: str = os.name,
) -> CodeVZmxImportResult:
    """Import one ZMX into CODE V and export structured import facts."""

    source_zmx = Path(source_zmx)
    work_dir = Path(work_dir)
    sequence_path = work_dir / _ROUNDTRIP_SEQUENCE_NAME
    result_path = work_dir / _ROUNDTRIP_RESULT_NAME
    command_export_path = work_dir / _ROUNDTRIP_COMMAND_EXPORT_NAME
    for stale in (command_export_path,):
        if stale.exists():
            stale.unlink()
    write_zmx_import_sequence(
        sequence_path=sequence_path,
        source_zmx=source_zmx,
        result_path=result_path,
        command_export_path=command_export_path,
    )
    batch = run_codev_batch(
        sequence_path=sequence_path,
        result_path=result_path,
        executable=executable,
        work_dir=work_dir,
        timeout_seconds=timeout_seconds,
        platform_name=platform_name,
        expected_schema=CODEV_ROUNDTRIP_RESULT_SCHEMA,
        required_keys=_ROUNDTRIP_REQUIRED_KEYS,
    )
    return CodeVZmxImportResult(
        batch=batch,
        source_zmx=source_zmx,
        command_export_path=command_export_path,
    )


def run_codev_roundtrip_close(
    *,
    source_zmx: Path | str | None = None,
    work_dir: Path | str,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 120.0,
    exported_filename: str = "exported.zmx",
    asphere_abs_tol: float = 1e-6,
) -> CodeVRoundTripCloseResult:
    """Close the ENGINE-04c loop through CODE V readout and rebuilt ZMX."""

    source_zmx = default_patent_roundtrip_seed() if source_zmx is None else Path(source_zmx)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    readout = run_codev_readout(
        source_zmx=source_zmx,
        work_dir=work_dir,
        executable=executable,
        timeout_seconds=timeout_seconds,
    )
    exported_zmx = write_zmx_from_codev_readout(
        readout.readout,
        work_dir / exported_filename,
        name=f"{source_zmx.stem}-exported",
    )
    comparison = compare_roundtrip_zmx(
        source_zmx,
        exported_zmx,
        asphere_abs_tol=asphere_abs_tol,
    )
    return CodeVRoundTripCloseResult(
        source_zmx=source_zmx,
        readout=readout,
        exported_zmx=exported_zmx,
        comparison=comparison,
    )


def extract_zmx_fidelity_facts(path: Path | str) -> ZmxFidelityFacts:
    """Extract the four fidelity gates from a ZMX via the existing ingest path."""

    zmx_path = Path(path)
    optic = load_normalized_zmx(zmx_path)
    table = extract_prescription_table(optic, source_zmx=zmx_path)
    asphere_coefficients = _asphere_coefficients(table)
    raw_text = _read_zmx_text(zmx_path)
    system_facts = _parse_system_facts(raw_text)
    return ZmxFidelityFacts(
        path=zmx_path,
        efl_mm=float(optic.paraxial.f2()),
        f_number=system_facts["f_number"],
        entrance_pupil_diameter_mm=system_facts["entrance_pupil_diameter_mm"],
        wavelength_count=system_facts["wavelength_count"],
        glass_rows=_glass_rows(table),
        asphere_term_counts={
            surface_index: len(coefficients)
            for surface_index, coefficients in asphere_coefficients.items()
        },
        asphere_coefficients=asphere_coefficients,
        vignetting=_parse_vignetting(raw_text),
    )


def compare_roundtrip_zmx(
    source_zmx: Path | str,
    exported_zmx: Path | str,
    *,
    nd_abs_tol: float = 1e-6,
    vd_abs_tol: float = 1e-4,
    asphere_abs_tol: float = 1e-6,
) -> ZmxRoundTripComparison:
    """Compare source and round-tripped ZMX across the ENGINE-03c/04c gates."""

    source = extract_zmx_fidelity_facts(source_zmx)
    exported = extract_zmx_fidelity_facts(exported_zmx)
    efl_deviation_pct = abs(exported.efl_mm - source.efl_mm) / abs(source.efl_mm) * 100.0
    return ZmxRoundTripComparison(
        source=source,
        exported=exported,
        efl_deviation_pct=efl_deviation_pct,
        glass_mismatches=_glass_mismatches(
            source.glass_rows,
            exported.glass_rows,
            nd_abs_tol=nd_abs_tol,
            vd_abs_tol=vd_abs_tol,
        ),
        asphere_term_mismatches=_dict_mismatches(
            "surface",
            source.asphere_term_counts,
            exported.asphere_term_counts,
        )
        + _asphere_coefficient_mismatches(
            source.asphere_coefficients,
            exported.asphere_coefficients,
            abs_tol=asphere_abs_tol,
        ),
        vignetting_mismatches=_dict_mismatches("vignetting", source.vignetting, exported.vignetting),
    )


def _glass_rows(table: PrescriptionTable) -> tuple[GlassRow, ...]:
    rows: list[GlassRow] = []
    for surface in table.surfaces:
        nd = surface.refractive_index_d
        vd = surface.abbe_number
        if nd is None or vd is None or math.isclose(nd, 1.0, abs_tol=1e-12):
            continue
        rows.append(GlassRow(surface.index, surface.glass, nd, vd))
    return tuple(rows)


def _asphere_coefficients(table: PrescriptionTable) -> dict[int, tuple[float, ...]]:
    return {
        surface.index: tuple(surface.asphere_coefficients)
        for surface in table.surfaces
        if surface.asphere_coefficients
    }


def _glass_mismatches(
    source: tuple[GlassRow, ...],
    exported: tuple[GlassRow, ...],
    *,
    nd_abs_tol: float,
    vd_abs_tol: float,
) -> tuple[str, ...]:
    source_by_surface = {row.surface_index: row for row in source}
    exported_by_surface = {row.surface_index: row for row in exported}
    mismatches: list[str] = []
    for surface_index in sorted(set(source_by_surface) | set(exported_by_surface)):
        left = source_by_surface.get(surface_index)
        right = exported_by_surface.get(surface_index)
        if left is None or right is None:
            mismatches.append(f"S{surface_index}: glass row missing")
            continue
        if abs(left.nd - right.nd) > nd_abs_tol or abs(left.vd - right.vd) > vd_abs_tol:
            mismatches.append(
                f"S{surface_index}: nd/vd {left.nd:.8g}/{left.vd:.8g} -> "
                f"{right.nd:.8g}/{right.vd:.8g}"
            )
    return tuple(mismatches)


def _dict_mismatches(
    label: str,
    source: dict[int, int] | dict[str, tuple[float, ...]],
    exported: dict[int, int] | dict[str, tuple[float, ...]],
) -> tuple[str, ...]:
    mismatches: list[str] = []
    for key in sorted(set(source) | set(exported), key=str):
        if source.get(key) != exported.get(key):
            mismatches.append(f"{label} {key}: {source.get(key)!r} -> {exported.get(key)!r}")
    return tuple(mismatches)


def _asphere_coefficient_mismatches(
    source: dict[int, tuple[float, ...]],
    exported: dict[int, tuple[float, ...]],
    *,
    abs_tol: float,
) -> tuple[str, ...]:
    mismatches: list[str] = []
    for surface_index in sorted(set(source) | set(exported)):
        source_coefficients = source.get(surface_index, ())
        exported_coefficients = exported.get(surface_index, ())
        if len(source_coefficients) != len(exported_coefficients):
            continue
        for coefficient_index, (left, right) in enumerate(
            zip(source_coefficients, exported_coefficients, strict=True),
            start=1,
        ):
            if abs(left - right) > abs_tol:
                mismatches.append(
                    f"surface {surface_index} coefficient {coefficient_index}: "
                    f"{left:.8g} -> {right:.8g}"
                )
    return tuple(mismatches)


def _parse_system_facts(text: str) -> dict[str, float | int | None]:
    f_number: float | None = None
    entrance_pupil_diameter_mm: float | None = None
    wavelength_count = 0
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if not parts:
            continue
        key = parts[0].upper()
        if key == "FNUM":
            f_number = _first_float(parts[1:])
        elif key == "ENPD":
            entrance_pupil_diameter_mm = _first_float(parts[1:])
        elif key == "WAVM":
            wavelength_count += 1
    return {
        "f_number": f_number,
        "entrance_pupil_diameter_mm": entrance_pupil_diameter_mm,
        "wavelength_count": wavelength_count,
    }


def _parse_vignetting(text: str) -> dict[str, tuple[float, ...]]:
    values: dict[str, list[float]] = {"VDX": [], "VDY": [], "VCX": [], "VCY": []}
    for raw_line in text.splitlines():
        parts = raw_line.strip().split()
        if not parts:
            continue
        canonical_key = _VIGNETTING_ALIASES.get(parts[0].upper())
        if canonical_key is None:
            continue
        values[canonical_key].extend(_float_tokens(parts[1:]))
    return {key: tuple(value) for key, value in values.items()}


def _read_zmx_text(path: Path) -> str:
    # BOM-based dispatch: blind utf-16 attempts on even-length ASCII files
    # "succeed" into CJK mojibake (no exception), silently dropping every
    # VDX/VDY token. Bit us on CI where LF checkout made the file even-sized.
    raw = path.read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16")
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _float_tokens(tokens: list[str]) -> list[float]:
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _first_float(tokens: list[str]) -> float | None:
    values = _float_tokens(tokens)
    return values[0] if values else None


def _quote_codev_path(path: Path) -> str:
    value = str(path)
    if any(char in value for char in ('"', "\r", "\n")):
        raise ValueError(f"CODE V path cannot contain quotes or newlines: {value!r}")
    return f'"{value}"'
