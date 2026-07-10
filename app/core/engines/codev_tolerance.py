"""Strict offline contract for CODE V 11.5 TOR tolerancing exports."""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from app.core.engines.codev_batch import ensure_buf_exp_safe_filename

TorMetric = Literal["mtf", "rms"]
_COMMAND_PREFIX = re.compile(
    r"^(?:DEF|DLT|CMP|TOR|FRE|AZI|NTR|CHT|WBF|GO|BUF|OUT|IN|RES|EXI)\b",
    re.IGNORECASE,
)
_SURFACE_RANGE = re.compile(r"\bS(?:I|\d+)(?:\.\.(?:J|\d+))?\b", re.IGNORECASE)


class TorParseStatus(StrEnum):
    """Closed parser states; availability is intentionally not constructible here."""

    UNAVAILABLE = "unavailable"


class TorProvenance(StrEnum):
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class TorToleranceTable:
    commands: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class TorCompensators:
    commands: tuple[str, ...]
    provenance: str
    assembly_assumptions: str


@dataclass(frozen=True)
class TorMonteCarlo:
    trials: int


@dataclass(frozen=True)
class TorPerformanceRow:
    zoom: int
    field: int
    frequency_lp_per_mm: float
    azimuth_deg: float
    criterion: str
    design: float
    probability_columns: tuple[float, ...]


@dataclass(frozen=True)
class TorMonteCarloRow:
    sample: int
    zoom: int
    field: int
    criterion: str
    value: float


@dataclass(frozen=True)
class TorParseResult:
    status: TorParseStatus
    provenance: TorProvenance
    reason: str
    declared_trials: int | None = None
    performance_rows: tuple[TorPerformanceRow, ...] = ()
    monte_carlo_rows: tuple[TorMonteCarloRow, ...] = ()


def _quote_codev_path(path: Path) -> str:
    return f'"{str(path).replace("/", "\\\\")}"'


def _validate_commands(commands: Sequence[str], name: str) -> None:
    if not commands:
        raise ValueError(f"{name} must be explicit and non-empty")
    if any(
        not command.strip() or "\n" in command or "\r" in command or ";" in command
        for command in commands
    ):
        raise ValueError(f"{name} commands must be non-empty single commands")


def _validate_provenance(value: str, name: str) -> str:
    clean = value.strip()
    if not clean or "\n" in value or "\r" in value or _COMMAND_PREFIX.match(clean):
        raise ValueError(f"{name} must be non-command, single-line metadata")
    return clean


def _validate_tolerance_ranges(commands: Sequence[str]) -> None:
    for command in commands:
        if command.lstrip().upper().startswith("DEF TOL") and not _SURFACE_RANGE.search(command):
            raise ValueError("DEF TOL requires an explicit surface or surface range")


def build_codev_tor_sequence(
    *,
    source_path: Path | str,
    performance_result_path: Path | str,
    monte_carlo_result_path: Path | str,
    tolerance_table: TorToleranceTable,
    compensators: TorCompensators,
    monte_carlo: TorMonteCarlo,
    metric: TorMetric,
    mtf_frequency_lp_per_mm: float | None = None,
    mtf_azimuth_deg: float = 90.0,
) -> str:
    """Build the verified single-GO, two-buffer sequence for a ZMX source."""

    source = Path(source_path)
    performance_path = Path(performance_result_path)
    mc_path = Path(monte_carlo_result_path)
    if source.suffix.lower() != ".zmx":
        raise ValueError("source_path must be a ZMX file")
    if not source.is_file():
        raise ValueError("source_path must exist")
    ensure_buf_exp_safe_filename(performance_path)
    ensure_buf_exp_safe_filename(mc_path)
    resolved_source = source.resolve()
    resolved_performance = performance_path.resolve()
    resolved_mc = mc_path.resolve()
    if resolved_performance == resolved_mc:
        raise ValueError("PER and MC output paths must differ")
    if resolved_source in {resolved_performance, resolved_mc}:
        raise ValueError("output paths must differ from source_path")
    _validate_commands(tolerance_table.commands, "tolerance_table")
    _validate_commands(compensators.commands, "compensators")
    _validate_tolerance_ranges(tolerance_table.commands)
    tolerance_provenance = _validate_provenance(
        tolerance_table.provenance, "tolerance provenance"
    )
    compensator_provenance = _validate_provenance(
        compensators.provenance, "compensator provenance"
    )
    assembly_assumptions = _validate_provenance(
        compensators.assembly_assumptions, "assembly assumptions"
    )
    if not isinstance(monte_carlo.trials, int) or isinstance(monte_carlo.trials, bool):
        raise ValueError("monte_carlo.trials must be an integer")
    if not 1 <= monte_carlo.trials <= 1_000_000:
        raise ValueError("monte_carlo.trials must be between 1 and 1000000")
    if metric not in ("mtf", "rms"):
        raise ValueError("metric must be 'mtf' or 'rms'")
    if metric == "mtf":
        if mtf_frequency_lp_per_mm is None or not math.isfinite(mtf_frequency_lp_per_mm):
            raise ValueError("finite mtf_frequency_lp_per_mm is required for MTF TOR")
        if mtf_frequency_lp_per_mm <= 0:
            raise ValueError("mtf_frequency_lp_per_mm must be positive")
        if not math.isfinite(mtf_azimuth_deg) or not 0 <= mtf_azimuth_deg < 180:
            raise ValueError("mtf_azimuth_deg must be finite and in [0, 180)")
    elif mtf_frequency_lp_per_mm is not None or mtf_azimuth_deg != 90.0:
        raise ValueError("MTF frequency/azimuth parameters are only valid for MTF TOR")

    lines = [
        "! Generated by app.core.engines.codev_tolerance; verified TOR contract.",
        f"! tolerance provenance: {tolerance_provenance}",
        f"! compensator provenance: {compensator_provenance}",
        f"! assembly assumptions: {assembly_assumptions}",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source)}",
        *tolerance_table.commands,
        *compensators.commands,
        "TOR",
    ]
    if metric == "mtf":
        lines.extend(
            [f"FRE {mtf_frequency_lp_per_mm:.12g}", f"AZI {mtf_azimuth_deg:.12g}"]
        )
    lines.extend(
        [
            f"NTR {monte_carlo.trials}",
            "CHT N",
            "WBF B1 PER",
            "WBF B2 MC",
            "GO",
            f"BUF EXP B1 {_quote_codev_path(performance_path)}",
            f"BUF EXP B2 {_quote_codev_path(mc_path)}",
            "BUF DEL B1",
            "BUF DEL B2",
            "OUT YES",
            "EXI YES",
            "",
        ]
    )
    return "\n".join(lines)


def _read_tsv(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.reader(text.splitlines(), delimiter="\t"))


def _parse_per(rows: list[list[str]]) -> tuple[TorPerformanceRow, ...]:
    header = ["Eval Zoom", "Eval Field", "X", "Y", "Frequency", "Azimuth", "Weight", "Design", "Criterion"]
    index = next((i for i, row in enumerate(rows) if row[:9] == header), None)
    if index is None or not any("probability density function:" in "\t".join(r) for r in rows):
        raise ValueError("PER declarations/header missing")
    parsed = []
    for row in rows[index + 1 :]:
        if not any(row):
            continue
        if len(row) != 17:
            raise ValueError("PER data row has unexpected column count")
        frequency = float(row[4])
        azimuth = float(row[5])
        design = float(row[7])
        probability_columns = tuple(float(value) for value in row[9:17])
        if not all(
            math.isfinite(value) for value in (frequency, azimuth, design, *probability_columns)
        ):
            raise ValueError("PER numeric values must be finite")
        parsed.append(
            TorPerformanceRow(
                zoom=int(row[0]), field=int(row[1]), frequency_lp_per_mm=frequency,
                azimuth_deg=azimuth, criterion=row[8], design=design,
                probability_columns=probability_columns,
            )
        )
    if not parsed:
        raise ValueError("PER contains no data rows")
    return tuple(parsed)


def _parse_mc(rows: list[list[str]]) -> tuple[int, tuple[TorMonteCarloRow, ...]]:
    declaration = next(
        (
            row
            for row in rows
            if any(cell.strip() == "Number of Monte-Carlo samples:" for cell in row)
        ),
        None,
    )
    header_index = next((i for i, row in enumerate(rows) if row == ["Sample", "Zoom", "Field", "Criterion", "Value"]), None)
    if declaration is None or header_index is None:
        raise ValueError("MC declaration/header missing")
    declaration_values = [cell.strip() for cell in declaration if cell.strip()]
    if len(declaration_values) != 2:
        raise ValueError("MC trial declaration malformed")
    declared = int(declaration_values[1])
    parsed = []
    for row in rows[header_index + 1 :]:
        if not any(row):
            continue
        if len(row) != 5:
            raise ValueError("MC data row has unexpected column count")
        value = float(row[4])
        if not math.isfinite(value):
            raise ValueError("MC value must be finite")
        parsed.append(TorMonteCarloRow(int(row[0]), int(row[1]), int(row[2]), row[3], value))
    if not parsed or {row.sample for row in parsed} != set(range(1, declared + 1)):
        raise ValueError("MC sample coverage does not match declared trials")
    return declared, tuple(parsed)


def parse_codev_tor_exports(
    performance_result_path: Path | str, monte_carlo_result_path: Path | str
) -> TorParseResult:
    """Parse verified CODE V 11.5 structures while withholding yield semantics."""

    performance_path = Path(performance_result_path)
    mc_path = Path(monte_carlo_result_path)
    if performance_path == mc_path:
        return TorParseResult(TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, "PER and MC paths are identical")
    missing = [str(path) for path in (performance_path, mc_path) if not path.is_file()]
    if missing:
        return TorParseResult(TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, f"TOR BUF EXP file missing: {', '.join(missing)}")
    try:
        performance_rows = _parse_per(_read_tsv(performance_path))
        declared, mc_rows = _parse_mc(_read_tsv(mc_path))
    except (OSError, UnicodeError, ValueError) as exc:
        return TorParseResult(TorParseStatus.UNAVAILABLE, TorProvenance.UNAVAILABLE, f"TOR export parse failed: {exc}")
    return TorParseResult(
        TorParseStatus.UNAVAILABLE,
        TorProvenance.UNAVAILABLE,
        "structures parsed; PER probability semantics and yield policy are not ratified",
        declared,
        performance_rows,
        mc_rows,
    )
