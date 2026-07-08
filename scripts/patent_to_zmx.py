"""Convert USPTO embodiment prescription tables into staging Zemax files."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import html
import json
import math
import re
import sys
import unicodedata
import warnings
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.engines.codev_readout import (  # noqa: E402
    CodeVFieldReadout,
    CodeVReadout,
    CodeVSurfaceReadout,
    CodeVWavelengthReadout,
)
from app.core.engines.zmx_writer import write_zmx_from_codev_readout  # noqa: E402
from app.core.zmx_ingest import load_normalized_zmx  # noqa: E402
from scripts.patent_crawler import _ppubs_access_token, _ppubs_patent_html  # noqa: E402

DEFAULT_POOL_GLOB = "uspto-smartphone-batch*.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "zmx-staging"
DEFAULT_REPORT_PATH = ROOT / ".planning" / "loop" / "patent2zmx-spike-report.md"
DEFAULT_CASE_INDEX_PATH = ROOT / "app" / "data" / "optical_cases" / "index.json"
TRACE_WAVELENGTH_UM = 0.5876
TRACE_PROVISIONAL_SEMI_DIAMETER_MM = 100.0
TRACE_APERTURE_CLEARANCE = 1.02
MIN_TRACE_SEMI_DIAMETER_MM = 0.05
ND_PHYSICAL_RANGE = (1.3, 2.2)
VD_PHYSICAL_RANGE = (10.0, 100.0)
NUMBER_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[-+]?\d+)?"
PRESCRIPTION_FINGERPRINT_SURFACES = 8
PRESCRIPTION_FINGERPRINT_QUANTUM_MM = 0.001
DUPLICATE_PRESCRIPTION_DETAIL = "prescription fingerprint|duplicate_prescription"
ASPHERE_ORDER_TO_CODEV = {
    4: "A",
    6: "B",
    8: "C",
    10: "D",
    12: "E",
    14: "F",
    16: "G",
    18: "H",
    20: "J",
    22: "A22",
    24: "A24",
    26: "A26",
    28: "A28",
    30: "A30",
}
SUPPORTED_ASPHERE_ORDERS = set(ASPHERE_ORDER_TO_CODEV)
XASPHERE_WRITABLE_TERMS = (
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "J",
    "A22",
    "A24",
    "A26",
    "A28",
    "A30",
)
XASPHERE_HIGH_TERMS = set(XASPHERE_WRITABLE_TERMS[7:])
MATERIAL_TOKENS = {
    "PLASTIC",
    "GLASS",
    "CEMENTED",
    "RESIN",
    "FILTER",
    "CG",
    "IR",
    "IR-CUT",
    "CEMENT",
}
SURFACE_TYPE_TOKENS = {"ASP", "ASPH", "SPH", "SPHERICAL"}


class PatentParseError(ValueError):
    """Raised when a patent table is unavailable or unsafe to convert."""


@dataclass(frozen=True)
class PatentCandidate:
    patent_id: str
    title: str
    source_url: str
    pool_path: Path
    line_number: int


@dataclass
class PatentSurface:
    index: int
    label: str
    radius_mm: float | None
    thickness_mm: float | None
    material: str | None
    nd: float | None
    vd: float | None
    surface_type: str | None
    asphere_coefficients: dict[str, float] = field(default_factory=dict)


@dataclass
class PatentPrescription:
    patent_id: str
    embodiment: str
    focal_length_mm: float
    f_number: float
    hfov_deg: float
    surfaces: list[PatentSurface]
    unsupported_asphere_terms: list[str] = field(default_factory=list)

    @property
    def image_height_mm(self) -> float:
        return self.focal_length_mm * math.tan(math.radians(self.hfov_deg))


@dataclass(frozen=True)
class _EmbodimentMeta:
    embodiment: str
    start: int
    end: int
    focal_length_mm: float
    f_number: float
    hfov_deg: float


@dataclass(frozen=True)
class TraceApertureAudit:
    semi_diameters_mm: dict[int, float]
    real_image_height_mm: float
    sanity_image_height_mm: float
    measured_surfaces: tuple[int, ...]
    interpolated_surfaces: tuple[int, ...]
    finite_final_rays: int
    total_rays: int


@dataclass
class ConversionAttempt:
    patent_id: str
    title: str
    status: str
    reason: str
    embodiment: str = ""
    zmx_path: str = ""
    efl_mm: float | None = None
    real_image_height_mm: float | None = None
    sanity_image_height_mm: float | None = None
    coverage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _PrescriptionParseAttempt:
    embodiment_number: int
    embodiment: str
    prescription: PatentPrescription | None = None
    error: Exception | None = None


@dataclass(frozen=True)
class _PatentTableBlock:
    number: int
    text: str
    start: int
    end: int


def normalize_patent_text(value: str) -> str:
    """Return PPUBS HTML/plain text normalized for deterministic regex parsing."""

    text = re.sub(r"<maths.*?</maths>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", html.unescape(text))
    replacements = {
        "\u2212": "-",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": " -- ",
        "\u2015": " -- ",
        "\u221e": "Infinity",
        "\u00a0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def parse_patent_prescription(raw_text: str, *, patent_id: str = "") -> PatentPrescription:
    """Parse the first USPTO embodiment prescription table in ``raw_text``."""

    return parse_patent_prescriptions(raw_text, patent_id=patent_id)[0]


def parse_patent_prescriptions(raw_text: str, *, patent_id: str = "") -> list[PatentPrescription]:
    """Parse every USPTO embodiment/example prescription table in ``raw_text``."""

    attempts = _parse_prescription_attempts(raw_text, patent_id=patent_id)
    prescriptions: list[PatentPrescription] = []
    for attempt in attempts:
        if attempt.error is not None:
            raise attempt.error
        if attempt.prescription is None:
            raise PatentParseError(f"{attempt.embodiment} did not produce a prescription")
        prescriptions.append(attempt.prescription)
    return prescriptions


def _parse_prescription_attempts(
    raw_text: str,
    *,
    patent_id: str = "",
) -> list[_PrescriptionParseAttempt]:
    """Parse embodiment tables independently so one bad table does not hide later ones."""

    text = normalize_patent_text(raw_text)
    try:
        metas = _find_embodiment_metas(text)
    except PatentParseError:
        attempts = _parse_fujifilm_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_aac_raytech_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        raise
    attempts: list[_PrescriptionParseAttempt] = []
    for index, meta in enumerate(metas, start=1):
        next_meta_index = index
        section_end = metas[next_meta_index].start if next_meta_index < len(metas) else len(text)
        try:
            prescription = _parse_prescription_at_meta(text, meta, section_end, patent_id)
        except Exception as exc:  # noqa: BLE001 - surfaced as a per-embodiment failure
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=index,
                    embodiment=meta.embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=meta.embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _parse_prescription_at_meta(
    text: str,
    meta: _EmbodimentMeta,
    section_end: int,
    patent_id: str,
) -> PatentPrescription:
    coeff_start = _find_required_before(text, "Aspheric Coefficients", meta.end, section_end)
    surface_table = _surface_table_text(text, meta.end, coeff_start)
    surfaces = _parse_surface_table(surface_table)
    coefficients, unsupported = _parse_asphere_coefficients(
        text,
        coeff_start,
        section_end=section_end,
    )
    if unsupported:
        raise PatentParseError(
            "unsupported nonzero high-order asphere terms: " + ", ".join(unsupported[:8])
        )
    for surface in surfaces:
        surface.asphere_coefficients.update(coefficients.get(surface.index, {}))
        if surface.asphere_coefficients and not surface.surface_type:
            surface.surface_type = "ASP"

    optical_surfaces = [surface for surface in surfaces if surface.index > 0]
    if len(optical_surfaces) < 3:
        raise PatentParseError("surface table did not contain a usable sequential prescription")

    return PatentPrescription(
        patent_id=patent_id,
        embodiment=meta.embodiment,
        focal_length_mm=meta.focal_length_mm,
        f_number=meta.f_number,
        hfov_deg=meta.hfov_deg,
        surfaces=optical_surfaces,
        unsupported_asphere_terms=unsupported,
    )


_FUJIFILM_BASIC_TABLE_PATTERN = re.compile(
    r"\bTABLE-US-\d+\s+TABLE\s+\d+\s+Example\s+(?P<example>\d+)\s+"
    r"Sn\s+R\s+D\s+Nd\s+\S+\s+\S+\s+SG(?:\s+ED)?\s+",
    flags=re.IGNORECASE,
)
_FUJIFILM_INLINE_TABLE_PATTERN = re.compile(
    rf"\bTABLE-US-\d+\s+TABLE\s+\d+\s+Example\s+(?P<example>\d+)\s+"
    rf"Basic\s+Lens\s+Data\s+f\s*=\s*(?P<f>{NUMBER_PATTERN})\s*,?\s+"
    rf"BF\s*=\s*(?P<bf>{NUMBER_PATTERN})\s*,?\s+2\S*\s*=\s*"
    rf"(?P<full_angle>{NUMBER_PATTERN})\s*,?\s+FNo\.?\s*=\s*"
    rf"(?P<fno>{NUMBER_PATTERN})\s+Si\s+Ri\s+Di\s+Ndj\s+\S+\s+",
    flags=re.IGNORECASE,
)


def _parse_fujifilm_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse Fujifilm basic-lens/specification table pairs."""

    basic_matches = list(_FUJIFILM_BASIC_TABLE_PATTERN.finditer(text))
    if not basic_matches:
        return _parse_fujifilm_inline_table_attempts(text, patent_id=patent_id)

    attempts: list[_PrescriptionParseAttempt] = []
    for index, basic_match in enumerate(basic_matches, start=1):
        example_number = int(basic_match.group("example"))
        embodiment = f"Example {example_number}"
        next_basic_start = (
            basic_matches[index].start() if index < len(basic_matches) else len(text)
        )
        try:
            spec_match = _fujifilm_spec_match(
                text,
                example_number=example_number,
                start=basic_match.end(),
                end=next_basic_start,
            )
            surfaces = _parse_fujifilm_surface_table(
                text[basic_match.end() : spec_match.start()],
                example_number=example_number,
            )
            coefficients = _parse_fujifilm_asphere_coefficients(
                text,
                example_number=example_number,
                start=spec_match.end(),
                end=next_basic_start,
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.asphere_coefficients.update(coefficients[surface.index])
                    surface.surface_type = "ASP"
            if surfaces:
                surfaces.append(
                    PatentSurface(
                        index=surfaces[-1].index + 1,
                        label="Image",
                        radius_mm=0.0,
                        thickness_mm=0.0,
                        material=None,
                        nd=None,
                        vd=None,
                        surface_type=None,
                    )
                )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=_parse_number(spec_match.group("f")),
                f_number=_parse_number(spec_match.group("fno")),
                hfov_deg=_parse_number(spec_match.group("full_angle")) / 2.0,
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - kept as a per-example failure
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=index,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _parse_fujifilm_inline_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse older Fujifilm tables whose specs are embedded in the basic table heading."""

    inline_matches = list(_FUJIFILM_INLINE_TABLE_PATTERN.finditer(text))
    attempts: list[_PrescriptionParseAttempt] = []
    for index, inline_match in enumerate(inline_matches, start=1):
        example_number = int(inline_match.group("example"))
        embodiment = f"Example {example_number}"
        next_start = inline_matches[index].start() if index < len(inline_matches) else len(text)
        try:
            asphere_match = _fujifilm_asphere_header_match(
                text,
                example_number=example_number,
                start=inline_match.end(),
                end=next_start,
            )
            surface_end = asphere_match.start() if asphere_match is not None else next_start
            surfaces = _parse_fujifilm_surface_table(
                text[inline_match.end() : surface_end],
                example_number=example_number,
            )
            coefficients = _parse_fujifilm_asphere_coefficients(
                text,
                example_number=example_number,
                start=inline_match.end(),
                end=next_start,
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.asphere_coefficients.update(coefficients[surface.index])
                    surface.surface_type = "ASP"
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=_parse_number(inline_match.group("f")),
                f_number=_parse_number(inline_match.group("fno")),
                hfov_deg=_parse_number(inline_match.group("full_angle")) / 2.0,
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - kept as a per-example failure
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=index,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _fujifilm_spec_match(
    text: str,
    *,
    example_number: int,
    start: int,
    end: int,
) -> re.Match[str]:
    pattern = re.compile(
        rf"\bTABLE-US-\d+\s+TABLE\s+\d+\s+Example\s+{example_number}\s+"
        rf"f\s+(?P<f>{NUMBER_PATTERN})\s+Bf\s+(?P<bf>{NUMBER_PATTERN})\s+"
        rf"FNo\.?\s+(?P<fno>{NUMBER_PATTERN})\s+2\S*\s+"
        rf"(?P<full_angle>{NUMBER_PATTERN})",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text, start, end)
    if match is None:
        raise PatentParseError(f"Fujifilm Example {example_number} specification table not found")
    return match


def _parse_fujifilm_surface_table(
    table_text: str,
    *,
    example_number: int,
) -> list[PatentSurface]:
    tokens = _tokenize_fujifilm_table(table_text)
    starts = [
        (pos, marker)
        for pos, token in enumerate(tokens)
        if (marker := _fujifilm_surface_marker(token)) is not None
    ]
    if not starts:
        raise PatentParseError(f"Fujifilm Example {example_number} surface table had no rows")

    surfaces: list[PatentSurface] = []
    expected_index = 1
    for row_index, (pos, marker) in enumerate(starts):
        surface_index, is_stop, is_asphere = marker
        if surface_index != expected_index:
            raise PatentParseError(
                "Fujifilm surface table index break: "
                f"expected {expected_index}, found {surface_index}"
            )
        row_end = starts[row_index + 1][0] if row_index + 1 < len(starts) else len(tokens)
        row = tokens[pos + 1 : row_end]
        row_is_stop = is_stop or any(_strip_parens(token).upper() == "ST" for token in row)
        row = [token for token in row if _strip_parens(token).upper() != "ST"]
        if len(row) < 2:
            if row_index + 1 < len(starts):
                raise PatentParseError(f"Fujifilm surface {surface_index} row is incomplete")
            row = [*row, "0"]
        radius = _distance_value(row[0], field_name=f"surface {surface_index} radius")
        thickness = _distance_value(row[1], field_name=f"surface {surface_index} thickness")
        nd = vd = None
        if len(row) >= 4:
            try:
                candidate_nd = _parse_number(row[2])
                candidate_vd = _parse_number(row[3])
            except PatentParseError:
                candidate_nd = candidate_vd = None
            if (
                candidate_nd is not None
                and candidate_vd is not None
                and _is_physical_nd(candidate_nd)
                and _is_physical_vd(candidate_vd)
            ):
                nd = candidate_nd
                vd = candidate_vd
        _validate_material_indices(surface_index=surface_index, nd=nd, vd=vd)
        surfaces.append(
            PatentSurface(
                index=surface_index,
                label="Stop" if row_is_stop else f"Surface {surface_index}",
                radius_mm=radius,
                thickness_mm=thickness,
                material="Glass" if nd is not None else None,
                nd=nd,
                vd=vd,
                surface_type="ASP" if is_asphere else None,
            )
        )
        expected_index += 1
    return surfaces


def _fujifilm_asphere_header_match(
    text: str,
    *,
    example_number: int,
    start: int,
    end: int,
) -> re.Match[str] | None:
    pattern = re.compile(
        rf"\bTABLE-US-\d+\s+TABLE\s+\d+\s+Example\s+{example_number}\s+"
        rf"(?:Sn|Aspherical\s+Surface\s+Coefficient\s+Si)\s+",
        flags=re.IGNORECASE,
    )
    return pattern.search(text, start, end)


def _parse_fujifilm_asphere_coefficients(
    text: str,
    *,
    example_number: int,
    start: int,
    end: int,
) -> dict[int, dict[str, float]]:
    match = _fujifilm_asphere_header_match(
        text,
        example_number=example_number,
        start=start,
        end=end,
    )
    if match is None:
        return {}
    body = text[match.end() : end]
    cutoffs = [
        cutoff.start()
        for pattern in (r"\bExample\s+\d+\s+\[\d+\]", r"\s\[\d+\]\s")
        if (cutoff := re.search(pattern, body))
    ]
    if cutoffs:
        body = body[: min(cutoffs)]
    tokens = _tokenize_coefficients(body)
    pos = 0
    surface_ids: list[int] = []
    while pos < len(tokens) and tokens[pos].isdigit():
        surface_ids.append(int(tokens[pos]))
        pos += 1
    if not surface_ids:
        raise PatentParseError(f"Fujifilm Example {example_number} asphere table had no Sn row")

    coefficients: dict[int, dict[str, float]] = {}
    while pos < len(tokens):
        label = tokens[pos].upper().rstrip("=")
        pos += 1
        if label == "=":
            continue
        if pos < len(tokens) and tokens[pos] == "=":
            pos += 1
        values: list[float] = []
        for _surface_id in surface_ids:
            if pos >= len(tokens):
                raise PatentParseError(
                    f"Fujifilm Example {example_number} asphere row {label} is incomplete"
                )
            values.append(_parse_number(tokens[pos]))
            pos += 1
        if label in {"K", "KA"}:
            codev_label = "K"
        else:
            order_match = re.fullmatch(r"A(\d+)", label)
            if order_match is None:
                continue
            order = int(order_match.group(1))
            if order not in SUPPORTED_ASPHERE_ORDERS:
                unsupported = [
                    f"S{surface_id}:A{order}={value:.3g}"
                    for surface_id, value in zip(surface_ids, values, strict=True)
                    if abs(value) > 0.0
                ]
                if unsupported:
                    raise PatentParseError(
                        "unsupported nonzero Fujifilm asphere terms: "
                        + ", ".join(unsupported[:8])
                    )
                continue
            codev_label = ASPHERE_ORDER_TO_CODEV[order]
        for surface_id, value in zip(surface_ids, values, strict=True):
            coefficients.setdefault(surface_id, {})[codev_label] = value
    return coefficients


_PATENT_TABLE_BLOCK_PATTERN = re.compile(
    r"\bTABLE-US-\d+\s+TABLE\s+(?P<number>\d+)\s+",
    flags=re.IGNORECASE,
)
_AAC_RAYTECH_SURFACE_HEADER_PATTERN = re.compile(
    r"\bR\s+d\s+nd\s+(?:vd|νd)\s+(?:S1|ST)\b",
    flags=re.IGNORECASE,
)


def _parse_aac_raytech_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse AAC/Raytech compact R/d surface tables plus detached summary metadata."""

    blocks = _patent_table_blocks(text)
    surface_blocks: list[tuple[int, _PatentTableBlock, re.Match[str]]] = []
    for block_index, block in enumerate(blocks):
        header_match = _AAC_RAYTECH_SURFACE_HEADER_PATTERN.search(block.text)
        if header_match is not None:
            surface_blocks.append((block_index, block, header_match))
    if not surface_blocks:
        return []

    metas = _aac_raytech_summary_metas(blocks)
    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, (block_index, block, header_match) in enumerate(
        surface_blocks,
        start=1,
    ):
        embodiment = f"AAC Raytech example {embodiment_number}"
        try:
            meta = metas.get(embodiment_number)
            if meta is None:
                raise PatentParseError(
                    "AAC Raytech summary metadata did not contain f/F number/FOV "
                    f"for example {embodiment_number}"
                )
            surfaces, surface_index_by_label = _parse_aac_raytech_surface_table(
                block.text[header_match.start() :],
                example_number=embodiment_number,
            )
            coefficients: dict[int, dict[str, float]] = {}
            if block_index + 1 < len(blocks):
                coefficients = _parse_aac_raytech_asphere_table(
                    blocks[block_index + 1].text,
                    surface_index_by_label=surface_index_by_label,
                )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.asphere_coefficients.update(coefficients[surface.index])
                    surface.surface_type = "ASP"
            if surfaces:
                surfaces.append(
                    PatentSurface(
                        index=surfaces[-1].index + 1,
                        label="Image",
                        radius_mm=0.0,
                        thickness_mm=0.0,
                        material=None,
                        nd=None,
                        vd=None,
                        surface_type=None,
                    )
                )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=meta.focal_length_mm,
                f_number=meta.f_number,
                hfov_deg=meta.hfov_deg,
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - kept as a per-example failure
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _patent_table_blocks(text: str) -> list[_PatentTableBlock]:
    matches = list(_PATENT_TABLE_BLOCK_PATTERN.finditer(text))
    blocks: list[_PatentTableBlock] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(
            _PatentTableBlock(
                number=int(match.group("number")),
                text=text[match.start() : end],
                start=match.start(),
                end=end,
            )
        )
    return blocks


def _aac_raytech_summary_metas(blocks: list[_PatentTableBlock]) -> dict[int, _EmbodimentMeta]:
    metas: dict[int, _EmbodimentMeta] = {}
    narrative_full_fovs: list[float] = []
    narrative_image_heights: list[float] = []
    for block in blocks:
        if re.search(r"Aspheric|Aspherical", block.text, flags=re.IGNORECASE) is None:
            continue
        narrative_full_fovs.extend(
            _aac_summary_row_values(block.text, {"FOV"}, cut_narrative=False)
        )
        narrative_image_heights.extend(
            _aac_summary_row_values(block.text, {"IH", "IMGHT", "IMAGEHEIGHT"}, cut_narrative=False)
        )

    for block in blocks:
        focal_lengths = _aac_summary_row_values(block.text, {"F"}, cut_narrative=True)
        f_numbers = _aac_summary_row_values(
            block.text,
            {"FNO", "F-NUMBER", "FNUMBER"},
            cut_narrative=True,
        )
        full_fovs = _aac_summary_row_values(block.text, {"FOV"}, cut_narrative=True)
        image_heights = _aac_summary_row_values(
            block.text,
            {"IH", "IMGHT", "IMAGEHEIGHT"},
            cut_narrative=True,
        )
        if not focal_lengths or not f_numbers or (not full_fovs and not image_heights):
            if not focal_lengths or not f_numbers:
                continue
            full_fovs = narrative_full_fovs
            image_heights = narrative_image_heights
            if not full_fovs and not image_heights:
                continue
        count = min(
            len(focal_lengths),
            len(f_numbers),
            len(full_fovs) if full_fovs else len(image_heights),
        )
        for index in range(count):
            if full_fovs:
                hfov = full_fovs[index] / 2.0
            else:
                hfov = math.degrees(math.atan(image_heights[index] / focal_lengths[index]))
            metas.setdefault(
                index + 1,
                _EmbodimentMeta(
                    embodiment=f"AAC Raytech example {index + 1}",
                    start=block.start,
                    end=block.end,
                    focal_length_mm=focal_lengths[index],
                    f_number=f_numbers[index],
                    hfov_deg=hfov,
                ),
            )
    return metas


def _aac_summary_row_values(
    table_text: str,
    labels: set[str],
    *,
    cut_narrative: bool = False,
) -> list[float]:
    source = _cut_aac_table_narrative(table_text) if cut_narrative else table_text
    tokens = _tokenize_aac_raytech_table(source)
    normalized_labels = {_aac_summary_label(label) for label in labels}
    for pos, token in enumerate(tokens):
        if _aac_summary_label(token) not in normalized_labels:
            continue
        values: list[float] = []
        value_pos = pos + 1
        while value_pos < len(tokens):
            try:
                values.append(_parse_aac_number(tokens[value_pos]))
            except PatentParseError:
                if values:
                    break
            value_pos += 1
        if values:
            return values
    return []


def _parse_aac_raytech_surface_table(
    table_text: str,
    *,
    example_number: int,
) -> tuple[list[PatentSurface], dict[str, int]]:
    body = _cut_aac_table_narrative(table_text)
    tokens = _tokenize_aac_raytech_table(body)
    stop_pos = next(
        (pos for pos, token in enumerate(tokens) if token.upper() in {"S1", "ST"}),
        None,
    )
    if stop_pos is None or stop_pos + 1 >= len(tokens):
        raise PatentParseError(f"AAC Raytech example {example_number} stop row not found")

    row_starts = [
        (pos, label)
        for pos, token in enumerate(tokens)
        if (label := _aac_surface_label(token)) is not None
    ]
    if not row_starts:
        raise PatentParseError(f"AAC Raytech example {example_number} surface rows not found")

    first_surface_pos = row_starts[0][0]
    stop_row = tokens[stop_pos + 2 : first_surface_pos]
    surfaces = [
        PatentSurface(
            index=1,
            label="Stop",
            radius_mm=_distance_value(tokens[stop_pos + 1], field_name="stop radius"),
            thickness_mm=_aac_distance_after_label(stop_row, "d0", field_name="stop thickness"),
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    ]
    surface_index_by_label: dict[str, int] = {}
    for row_index, (pos, label) in enumerate(row_starts):
        row_end = row_starts[row_index + 1][0] if row_index + 1 < len(row_starts) else len(tokens)
        row = tokens[pos + 1 : row_end]
        if not row:
            raise PatentParseError(f"AAC Raytech {label} row is incomplete")
        surface_index = len(surfaces) + 1
        thickness = _aac_distance_after_label(
            row[1:],
            f"d{label[1:]}",
            field_name=f"{label} thickness",
        )
        nd, vd = _aac_material_indices(row, surface_index=surface_index)
        surfaces.append(
            PatentSurface(
                index=surface_index,
                label=f"Surface {label}",
                radius_mm=_distance_value(row[0], field_name=f"{label} radius"),
                thickness_mm=thickness,
                material="Glass" if nd is not None else None,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )
        surface_index_by_label[label.upper()] = surface_index
    return surfaces, surface_index_by_label


def _parse_aac_raytech_asphere_table(
    table_text: str,
    *,
    surface_index_by_label: dict[str, int],
) -> dict[int, dict[str, float]]:
    if re.search(r"Aspheric|Aspherical", table_text, flags=re.IGNORECASE) is None:
        return {}

    tokens = _tokenize_aac_raytech_table(_cut_aac_table_narrative(table_text))
    coefficients: dict[int, dict[str, float]] = {}
    current_labels: list[str] = []
    pos = 0
    while pos < len(tokens):
        token = tokens[pos]
        if token.upper() == "K":
            current_labels = ["K"]
            pos += 1
            while pos < len(tokens) and re.fullmatch(r"A\d+", tokens[pos], re.IGNORECASE):
                current_labels.append(tokens[pos].upper())
                pos += 1
            continue

        surface_label = _aac_surface_label(token)
        if surface_label is None or not current_labels:
            pos += 1
            continue

        values: list[float] = []
        pos += 1
        for _label in current_labels:
            if pos >= len(tokens):
                raise PatentParseError(f"AAC Raytech {surface_label} asphere row is incomplete")
            values.append(_parse_aac_number(tokens[pos]))
            pos += 1
        surface_index = surface_index_by_label.get(surface_label.upper())
        if surface_index is None:
            continue
        for label, value in zip(current_labels, values, strict=True):
            codev_label = _aac_codev_asphere_label(label, value, surface_label)
            if codev_label is not None:
                coefficients.setdefault(surface_index, {})[codev_label] = value
    return coefficients


def _aac_distance_after_label(
    tokens: list[str],
    label: str,
    *,
    field_name: str,
) -> float | None:
    label_upper = label.upper()
    for pos, token in enumerate(tokens[:-1]):
        if token.upper() == label_upper:
            return _distance_value(tokens[pos + 1], field_name=field_name)
    for token in tokens:
        try:
            return _distance_value(token, field_name=field_name)
        except PatentParseError:
            continue
    raise PatentParseError(f"{field_name} is not numeric")


def _aac_material_indices(
    row: list[str],
    *,
    surface_index: int,
) -> tuple[float | None, float | None]:
    nd = vd = None
    for pos, token in enumerate(row[:-1]):
        if re.fullmatch(r"nd\w*", token, flags=re.IGNORECASE):
            nd = _parse_aac_number(row[pos + 1])
        if re.fullmatch(r"(?:v|ν)d?\w*", token, flags=re.IGNORECASE):
            vd = _parse_aac_number(row[pos + 1])
    _validate_material_indices(surface_index=surface_index, nd=nd, vd=vd)
    return nd, vd


def _aac_codev_asphere_label(
    label: str,
    value: float,
    surface_label: str,
) -> str | None:
    if label == "K":
        return "K"
    order_match = re.fullmatch(r"A(\d+)", label, flags=re.IGNORECASE)
    if order_match is None:
        return None
    order = int(order_match.group(1))
    if order not in SUPPORTED_ASPHERE_ORDERS:
        if abs(value) > 0.0:
            raise PatentParseError(
                f"unsupported nonzero AAC Raytech asphere term: {surface_label}:A{order}={value:.3g}"
            )
        return None
    return ASPHERE_ORDER_TO_CODEV[order]


def _tokenize_aac_raytech_table(text: str) -> list[str]:
    text = _normalize_decimal_commas(text)
    text = text.replace("=", " ")
    text = text.replace("°", "")
    return [token.strip(";,|") for token in text.split() if token.strip(";,|")]


def _cut_aac_table_narrative(text: str) -> str:
    return re.split(r"\s\[\d+\]\s", text, maxsplit=1)[0]


def _aac_surface_label(token: str) -> str | None:
    match = re.fullmatch(r"R(?!p)(\d+)", token, flags=re.IGNORECASE)
    return f"R{match.group(1)}" if match is not None else None


def _aac_summary_label(token: str) -> str:
    return re.sub(r"[^A-Z0-9-]+", "", token.upper())


def _parse_aac_number(token: str) -> float:
    if token == "/" or _is_empty_value(token):
        return 0.0
    return _parse_number(token.rstrip("°"))


def prescription_fingerprint(prescription: PatentPrescription) -> str:
    """Hash the first eight surface radius/thickness pairs for duplicate screening."""

    sequence = [
        (
            _fingerprint_value(surface.radius_mm),
            _fingerprint_value(surface.thickness_mm),
        )
        for surface in prescription.surfaces[:PRESCRIPTION_FINGERPRINT_SURFACES]
    ]
    payload = json.dumps(sequence, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]


def build_readout_from_prescription(
    prescription: PatentPrescription,
    *,
    semi_diameters_mm: dict[int, float] | None = None,
    image_height_y_mm: float | None = None,
) -> CodeVReadout:
    """Build the existing CODE V readout DTO consumed by ``zmx_writer``."""

    _validate_prescription_materials(prescription)
    stop_surface = _stop_surface_index(prescription.surfaces)
    surfaces = tuple(
        CodeVSurfaceReadout(
            index=surface.index,
            radius_y_mm=_finite_or_zero(surface.radius_mm),
            thickness_mm=_finite_or_zero(surface.thickness_mm),
            semi_diameter_mm=_surface_semi_diameter_for_readout(surface, semi_diameters_mm),
            glass="___BLANK" if surface.nd and surface.nd > 1.000001 else None,
            nd=surface.nd,
            vd=surface.vd,
            surface_type=surface.surface_type or "SPH",
            is_stop=surface.index == stop_surface,
            asphere_coefficients=dict(surface.asphere_coefficients),
        )
        for surface in prescription.surfaces
    )
    fields = (
        CodeVFieldReadout(
            index=1,
            definition_type="ANG",
            x=0.0,
            y=0.0,
            vuy=0.0,
            vly=0.0,
            vux=0.0,
            vlx=0.0,
        ),
        CodeVFieldReadout(
            index=2,
            definition_type="ANG",
            x=0.0,
            y=prescription.hfov_deg,
            vuy=0.0,
            vly=0.0,
            vux=0.0,
            vlx=0.0,
        ),
    )
    wavelengths = (
        CodeVWavelengthReadout(index=1, wavelength_um=0.4861, weight=1.0),
        CodeVWavelengthReadout(index=2, wavelength_um=0.5876, weight=1.0),
        CodeVWavelengthReadout(index=3, wavelength_um=0.6563, weight=1.0),
    )
    return CodeVReadout(
        source_zmx=f"{_safe_stem(prescription.patent_id)}.zmx",
        units="MM",
        aperture_type="FNO",
        f_number=prescription.f_number,
        entrance_pupil_diameter_mm=None,
        num_surfaces=len(surfaces),
        num_fields=len(fields),
        num_wavelengths=len(wavelengths),
        num_zooms=1,
        stop_surface=stop_surface,
        field_type="ANG",
        reference_wavelength_index=2,
        image_height_y_mm=(
            image_height_y_mm if image_height_y_mm is not None else prescription.image_height_mm
        ),
        surfaces=surfaces,
        fields=fields,
        wavelengths=wavelengths,
    )


def load_patent_pool(pool_dir: Path, pattern: str = DEFAULT_POOL_GLOB) -> list[PatentCandidate]:
    """Load de-duplicated USPTO patent candidates from local JSONL pool files."""

    candidates: list[PatentCandidate] = []
    seen: set[str] = set()
    for path in sorted(pool_dir.glob(pattern)):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                patent_id = str(record.get("id") or "").strip()
                normalized = _normalized_patent_id(patent_id)
                if not patent_id or normalized in seen:
                    continue
                seen.add(normalized)
                candidates.append(
                    PatentCandidate(
                        patent_id=patent_id,
                        title=str(record.get("title") or ""),
                        source_url=str(record.get("source_url") or ""),
                        pool_path=path,
                        line_number=line_number,
                    )
                )
    return candidates


def load_formal_case_stems(index_path: Path = DEFAULT_CASE_INDEX_PATH) -> frozenset[str]:
    """Load formally ingested case/ZMX stems from the runtime case index."""

    if not index_path.exists():
        return frozenset()
    records = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise PatentParseError(f"case index must be a list: {index_path}")

    stems: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("case_id", "source_zmx"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                stems.add(Path(value).stem)
    return frozenset(stems)


def _formal_case_contains_embodiment(
    formal_case_stems: frozenset[str] | set[str],
    patent_id: str,
    embodiment_number: int,
) -> bool:
    return f"{_safe_stem(patent_id)}-e{embodiment_number}" in formal_case_stems


async def run_conversion(
    *,
    pool_dir: Path,
    output_dir: Path,
    report_path: Path,
    target_successes: int,
    max_attempts: int,
    case_index_path: Path | None = DEFAULT_CASE_INDEX_PATH,
) -> list[ConversionAttempt]:
    """Fetch USPTO HTML, parse prescriptions, write ZMX files, and report attempts."""

    candidates = load_patent_pool(pool_dir)
    attempts: list[ConversionAttempt] = []
    seen_prescription_fingerprints: set[str] = set()
    successes = 0
    formal_case_stems = (
        load_formal_case_stems(case_index_path) if case_index_path is not None else frozenset()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=60) as client:
        token = await _ppubs_access_token(client)
        for candidate in candidates:
            if len(attempts) >= max_attempts or successes >= target_successes:
                break
            candidate_attempts = await _convert_candidate(
                client,
                token,
                candidate,
                output_dir,
                formal_case_stems=formal_case_stems,
                seen_prescription_fingerprints=seen_prescription_fingerprints,
            )
            attempts.extend(candidate_attempts)
            successes += sum(attempt.status == "success" for attempt in candidate_attempts)
            await asyncio.sleep(0.25)

    _write_report(report_path, attempts, target_successes=target_successes)
    return attempts


async def _convert_candidate(
    client: httpx.AsyncClient,
    token: str,
    candidate: PatentCandidate,
    output_dir: Path,
    *,
    formal_case_stems: frozenset[str] | set[str] | None = None,
    seen_prescription_fingerprints: set[str] | None = None,
) -> list[ConversionAttempt]:
    try:
        page_html = await _fetch_patent_html(client, token, candidate.patent_id)
        parse_attempts = _parse_prescription_attempts(page_html, patent_id=candidate.patent_id)
    except Exception as exc:  # noqa: BLE001 - report per-patent failure reason
        return [
            ConversionAttempt(
                patent_id=candidate.patent_id,
                title=candidate.title,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
            )
        ]

    attempts: list[ConversionAttempt] = []
    formal_case_stems = formal_case_stems or frozenset()
    for parse_attempt in parse_attempts:
        if parse_attempt.error is not None:
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="failed",
                    reason=f"{type(parse_attempt.error).__name__}: {parse_attempt.error}",
                    embodiment=parse_attempt.embodiment,
                )
            )
            continue
        if parse_attempt.prescription is None:
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="failed",
                    reason="PatentParseError: embodiment did not produce a prescription",
                    embodiment=parse_attempt.embodiment,
                )
            )
            continue

        prescription = parse_attempt.prescription
        fingerprint = prescription_fingerprint(prescription)
        if seen_prescription_fingerprints is not None:
            if fingerprint in seen_prescription_fingerprints:
                attempts.append(
                    ConversionAttempt(
                        patent_id=candidate.patent_id,
                        title=candidate.title,
                        status="duplicate_prescription",
                        reason=(
                            "duplicate_prescription: "
                            f"{DUPLICATE_PRESCRIPTION_DETAIL} {fingerprint}"
                        ),
                        embodiment=prescription.embodiment,
                        coverage=_coverage(prescription),
                    )
                )
                continue
            seen_prescription_fingerprints.add(fingerprint)
        if _formal_case_contains_embodiment(
            formal_case_stems,
            candidate.patent_id,
            parse_attempt.embodiment_number,
        ):
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="skipped",
                    reason="formal case index already contains this patent embodiment",
                    embodiment=prescription.embodiment,
                )
            )
            continue
        output_path = output_dir / (
            f"{_safe_stem(candidate.patent_id)}-e{parse_attempt.embodiment_number}.zmx"
        )
        try:
            trace_audit = write_patent_zmx(prescription, output_path)
            optic = load_normalized_zmx(output_path)
            efl = float(optic.paraxial.f2())
            if not math.isfinite(efl):
                raise PatentParseError("generated ZMX loaded but EFL was not finite")
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="success",
                    reason="parsed and ingested",
                    embodiment=prescription.embodiment,
                    zmx_path=_display_path(output_path),
                    efl_mm=efl,
                    real_image_height_mm=trace_audit.real_image_height_mm,
                    sanity_image_height_mm=trace_audit.sanity_image_height_mm,
                    coverage=_coverage(prescription, trace_audit=trace_audit),
                )
            )
        except Exception as exc:  # noqa: BLE001 - report per-embodiment failure reason
            with contextlib.suppress(FileNotFoundError):
                output_path.unlink()
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="failed",
                    reason=f"{type(exc).__name__}: {exc}",
                    embodiment=prescription.embodiment,
                )
            )
    return attempts


async def _fetch_patent_html(client: httpx.AsyncClient, token: str, patent_id: str) -> str:
    sources = [_source_for_patent_id(patent_id), "USPAT", "US-PGPUB", "USOCR"]
    seen: set[str] = set()
    errors: list[str] = []
    for source in sources:
        if source in seen:
            continue
        seen.add(source)
        try:
            return await _ppubs_patent_html(client, token, patent_id, source)
        except Exception as exc:  # noqa: BLE001 - try alternate PPUBS source buckets
            errors.append(f"{source}: {type(exc).__name__}")
    raise PatentParseError("USPTO HTML unavailable (" + "; ".join(errors) + ")")


def _find_embodiment_metas(text: str) -> list[_EmbodimentMeta]:
    label_pattern = re.compile(
        r"(?P<embodiment>"
        r"\d+(?:st|nd|rd|th)\s+Embodiment|"
        r"Embodiment\s+\d+|"
        r"(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\s+"
        r"Embodiment|"
        r"(?:Working\s+)?Example(?:\s+No\.?)?\s+\d+"
        r")",
        flags=re.IGNORECASE,
    )
    label_matches = list(label_pattern.finditer(text))
    metas: list[_EmbodimentMeta] = []
    for index, match in enumerate(label_matches):
        next_start = label_matches[index + 1].start() if index + 1 < len(label_matches) else len(text)
        window = text[match.start() : min(next_start, match.start() + 900)]
        surface_start = re.search(r"\b0\s+Object\b", window, flags=re.IGNORECASE)
        if surface_start is None:
            continue
        meta_window = window[: surface_start.start()]
        try:
            focal_length, focal_end = _extract_meta_number(
                meta_window,
                r"effective\s+focal\s+length|focal\s+length|EFL|(?<![A-Za-z])f(?![A-Za-z/#])",
                "focal length",
            )
            f_number, fno_end = _extract_meta_number(
                meta_window,
                r"F\s*no\.?|FNO|F-number|F\s*number|F\s*/\s*#?|F/#|F\s*#",
                "F number",
            )
            hfov, hfov_end = _extract_meta_number(
                meta_window,
                r"HFOV|Half\s+FOV|Half\s+Field\s+of\s+View|"
                r"Half\s+Angle\s+of\s+View|Half\s+View\s+Angle|Semi\s+Field\s+Angle",
                "HFOV",
            )
        except PatentParseError:
            continue
        metas.append(
            _EmbodimentMeta(
                embodiment=match.group("embodiment"),
                start=match.start(),
                end=match.start() + max(focal_end, fno_end, hfov_end),
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=hfov,
            )
        )
    if not metas:
        raise PatentParseError("embodiment f/Fno/HFOV line not found")
    return metas


def _extract_meta_number(
    text: str,
    label_pattern: str,
    field_name: str,
) -> tuple[float, int]:
    pattern = re.compile(
        rf"(?:{label_pattern})\s*(?:\([^)]*\))?\s*(?:=|:)?\s*(?P<value>{NUMBER_PATTERN})",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        raise PatentParseError(f"{field_name} not found in embodiment metadata")
    return _parse_number(match.group("value")), match.end()


def _surface_table_text(text: str, start: int, coeff_start: int) -> str:
    table_region = text[start:coeff_start]
    start_match = re.search(r"\b0\s+Object\b", table_region, flags=re.IGNORECASE)
    if start_match is None:
        raise PatentParseError("surface table did not start with surface 0 Object")
    table_region = table_region[start_match.start() :]
    cutoff_matches = [
        match.start()
        for pattern in (
            r"\bNote\s*:",
            r"\bReference wavelength\b",
            r"\bTABLE-US-\d+\b",
        )
        if (match := re.search(pattern, table_region, flags=re.IGNORECASE))
    ]
    if cutoff_matches:
        table_region = table_region[: min(cutoff_matches)]
    return table_region


def _parse_surface_table(table_text: str) -> list[PatentSurface]:
    tokens = _tokenize_table(table_text)
    surfaces: list[PatentSurface] = []
    pos = 0
    expected_index = 0
    while pos < len(tokens):
        token = tokens[pos]
        if not token.isdigit():
            pos += 1
            continue
        index = int(token)
        if index != expected_index:
            raise PatentParseError(
                f"surface table index break: expected {expected_index}, found {index}"
            )
        pos += 1
        label, pos = _consume_surface_label(tokens, pos)
        radius, pos = _consume_required_distance(tokens, pos, field_name=f"surface {index} radius")
        surface_type = None
        if pos < len(tokens) and _strip_parens(tokens[pos]).upper() in SURFACE_TYPE_TOKENS:
            surface_type = _strip_parens(tokens[pos]).upper()
            pos += 1
        thickness, pos = _consume_optional_distance(
            tokens,
            pos,
            field_name=f"surface {index} thickness",
        )
        material = None
        nd = None
        vd = None
        if pos < len(tokens) and _material_token(tokens[pos]):
            material = tokens[pos]
            pos += 1
            nd, vd, pos = _consume_material_indices(tokens, pos, surface_index=index)
        surfaces.append(
            PatentSurface(
                index=index,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=material,
                nd=nd,
                vd=vd,
                surface_type=surface_type,
            )
        )
        expected_index += 1
    if not surfaces or surfaces[0].index != 0:
        raise PatentParseError("surface table had no object row")
    return surfaces


def _parse_asphere_coefficients(
    text: str,
    coeff_start: int,
    *,
    section_end: int | None = None,
) -> tuple[dict[int, dict[str, float]], list[str]]:
    end = _find_coefficients_end(text, coeff_start)
    if section_end is not None:
        end = min(end, section_end)
    coeff_text = text[coeff_start:end]
    blocks = re.split(r"\bSurface\s+#\s+", coeff_text, flags=re.IGNORECASE)[1:]
    if not blocks:
        raise PatentParseError("aspheric coefficient table had no Surface # block")

    coefficients: dict[int, dict[str, float]] = {}
    unsupported: list[str] = []
    for block in blocks:
        tokens = _tokenize_coefficients(block)
        pos = 0
        surface_ids: list[int] = []
        while pos < len(tokens) and tokens[pos].isdigit():
            surface_ids.append(int(tokens[pos]))
            pos += 1
        if not surface_ids:
            continue
        while pos < len(tokens):
            label = tokens[pos].upper()
            pos += 1
            if label == "=":
                continue
            if pos < len(tokens) and tokens[pos] == "=":
                pos += 1
            if label in {"K", "K="}:
                for surface_id in surface_ids:
                    value, pos = _consume_optional_number(tokens, pos)
                    coefficients.setdefault(surface_id, {})["K"] = value or 0.0
                continue
            order_match = re.fullmatch(r"A(\d+)", label.rstrip("="))
            if order_match is None:
                continue
            order = int(order_match.group(1))
            values: list[float] = []
            for _surface_id in surface_ids:
                value, pos = _consume_optional_number(tokens, pos)
                values.append(value or 0.0)
            if order in SUPPORTED_ASPHERE_ORDERS:
                codev_label = ASPHERE_ORDER_TO_CODEV[order]
                for surface_id, value in zip(surface_ids, values, strict=True):
                    coefficients.setdefault(surface_id, {})[codev_label] = value
            else:
                for surface_id, value in zip(surface_ids, values, strict=True):
                    if abs(value) > 0.0:
                        unsupported.append(f"S{surface_id}:A{order}={value:.3g}")
    return coefficients, unsupported


def _find_coefficients_end(text: str, coeff_start: int) -> int:
    tail = text[coeff_start:]
    patterns = (
        r"\s(?:\(\d+\)|\[\d+\])\s+In Table\b",
        r"\bIn Table\s+\d+[A-Z]?,\s+k represents\b",
        r"\b2nd\s+Embodiment\b",
        r"\bEmbodiment\s+2\b",
        r"\bSecond\s+Embodiment\b",
        r"\bEXAMPLE\s+2\b",
    )
    ends = [
        match.start()
        for pattern in patterns
        if (match := re.search(pattern, tail, flags=re.IGNORECASE))
    ]
    return coeff_start + min(ends) if ends else len(text)


def _tokenize_table(text: str) -> list[str]:
    text = _normalize_decimal_commas(text)
    text = text.replace("(", " ").replace(")", " ")
    text = re.sub(r"(?<!\d),(?!\d)", " ", text)
    text = text.replace("=", " = ")
    return [token.strip() for token in text.split() if token.strip()]


def _tokenize_coefficients(text: str) -> list[str]:
    text = _normalize_decimal_commas(text)
    text = text.replace("=", " = ")
    text = re.sub(r"(?<!\d),(?!\d)", " ", text)
    return [token.strip() for token in text.split() if token.strip()]


def _tokenize_fujifilm_table(text: str) -> list[str]:
    text = _normalize_decimal_commas(text)
    text = re.sub(r"(?<!\d),(?!\d)", " ", text)
    return [token.strip() for token in text.split() if token.strip()]


def _normalize_decimal_commas(text: str) -> str:
    return re.sub(r"(?<=\d),(?=\d)", ".", text)


def _consume_surface_label(tokens: list[str], pos: int) -> tuple[str, int]:
    if pos >= len(tokens):
        raise PatentParseError("unexpected end of surface row")
    token = tokens[pos]
    upper = token.upper()
    if upper == "LENS" and pos + 1 < len(tokens):
        return f"Lens {tokens[pos + 1]}", pos + 2
    if upper in {"APE.", "APE"} and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "STOP":
        return "Ape. Stop", pos + 2
    if upper in {"APE.", "APE"}:
        return "Ape.", pos + 1
    if upper == "IR-CUT" and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "FILTER":
        return "IR-cut filter", pos + 2
    if upper in {"IR-CUT", "IRCUT"}:
        return "IR-cut", pos + 1
    if upper == "COVER" and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "GLASS":
        return "Cover glass", pos + 2
    if upper == "PRISM":
        return "Prism", pos + 1
    if upper in {"OBJECT", "IMAGE", "STOP", "FILTER", "COVER"}:
        return token, pos + 1
    return "", pos


def _consume_required_distance(
    tokens: list[str],
    pos: int,
    *,
    field_name: str,
) -> tuple[float | None, int]:
    if pos >= len(tokens):
        raise PatentParseError(f"missing {field_name}")
    value = _distance_value(tokens[pos], field_name=field_name)
    return value, pos + 1


def _consume_optional_distance(
    tokens: list[str],
    pos: int,
    *,
    field_name: str,
) -> tuple[float | None, int]:
    if pos >= len(tokens):
        return 0.0, pos
    value = _distance_value(tokens[pos], field_name=field_name)
    return value, pos + 1


def _consume_optional_number(tokens: list[str], pos: int) -> tuple[float | None, int]:
    if pos >= len(tokens):
        return None, pos
    token = tokens[pos]
    if _is_empty_value(token):
        return None, pos + 1
    try:
        return _parse_number(token), pos + 1
    except PatentParseError:
        return None, pos


def _consume_material_indices(
    tokens: list[str],
    pos: int,
    *,
    surface_index: int,
) -> tuple[float | None, float | None, int]:
    values: list[float] = []
    while (
        pos < len(tokens)
        and len(values) < 3
        and not _is_next_surface_index(tokens[pos], surface_index + 1)
    ):
        token = tokens[pos]
        if _is_empty_value(token):
            pos += 1
            continue
        try:
            values.append(_parse_number(token))
        except PatentParseError:
            break
        pos += 1

    has_reference_nd_column = (
        len(values) >= 3
        and _is_physical_nd(values[0])
        and _is_physical_nd(values[1])
        and _is_physical_vd(values[2])
    )
    if has_reference_nd_column:
        nd = values[1]
        vd = values[2]
    else:
        nd = values[0] if values else None
        vd = values[1] if len(values) >= 2 else None
    _validate_material_indices(surface_index=surface_index, nd=nd, vd=vd)
    return nd, vd, pos


def _validate_prescription_materials(prescription: PatentPrescription) -> None:
    for surface in prescription.surfaces:
        _validate_material_indices(surface_index=surface.index, nd=surface.nd, vd=surface.vd)


def _validate_material_indices(
    *,
    surface_index: int,
    nd: float | None,
    vd: float | None,
) -> None:
    if nd is None and vd is None:
        return
    if nd is None or vd is None:
        raise PatentParseError(
            f"surface {surface_index} material has incomplete nd/vd: nd={nd}, vd={vd}"
        )
    if not _is_physical_nd(nd) or not _is_physical_vd(vd):
        raise PatentParseError(
            f"surface {surface_index} material nd/vd outside physical bounds: "
            f"nd={nd:.9g} allowed [{ND_PHYSICAL_RANGE[0]}, {ND_PHYSICAL_RANGE[1]}], "
            f"vd={vd:.9g} allowed [{VD_PHYSICAL_RANGE[0]}, {VD_PHYSICAL_RANGE[1]}]"
        )


def _is_physical_nd(value: float) -> bool:
    return ND_PHYSICAL_RANGE[0] <= value <= ND_PHYSICAL_RANGE[1]


def _is_physical_vd(value: float) -> bool:
    return VD_PHYSICAL_RANGE[0] <= value <= VD_PHYSICAL_RANGE[1]


def _distance_value(token: str, *, field_name: str) -> float | None:
    stripped = _strip_parens(token)
    upper = stripped.upper()
    if upper in {"PLANO", "PIANO"}:
        return 0.0
    if upper in {"INFINITY", "INF"}:
        return math.inf
    if _is_empty_value(stripped):
        return 0.0
    try:
        return _parse_number(stripped)
    except PatentParseError as exc:
        raise PatentParseError(f"{field_name} is not numeric: {token}") from exc


def _parse_number(token: str) -> float:
    cleaned = _strip_parens(token).replace("−", "-")
    if "," in cleaned:
        if "." not in cleaned and re.fullmatch(
            r"[-+]?\d+,\d+(?:E[-+]?\d+)?",
            cleaned,
            re.I,
        ):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    cleaned = cleaned.rstrip(".;")
    if not re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[-+]?\d+)?", cleaned, re.I):
        raise PatentParseError(f"not a number: {token}")
    value = float(cleaned)
    if not math.isfinite(value):
        raise PatentParseError(f"non-finite number: {token}")
    return value


def _fingerprint_value(value: float | None) -> str | int:
    if value is None:
        return "none"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return int(round(value / PRESCRIPTION_FINGERPRINT_QUANTUM_MM))


def _coverage(
    prescription: PatentPrescription,
    *,
    trace_audit: TraceApertureAudit | None = None,
) -> dict[str, Any]:
    surfaces = prescription.surfaces
    asphere_surfaces = [surface for surface in surfaces if surface.asphere_coefficients]
    glass_rows = [surface for surface in surfaces if surface.nd is not None and surface.vd is not None]
    coverage = {
        "surfaces": len(surfaces),
        "r": f"{sum(surface.radius_mm is not None for surface in surfaces)}/{len(surfaces)}",
        "d": f"{sum(surface.thickness_mm is not None for surface in surfaces)}/{len(surfaces)}",
        "nd_vd": f"{len(glass_rows)}/{len(surfaces)}",
        "asphere_surfaces": len(asphere_surfaces),
        "f_mm": prescription.focal_length_mm,
        "f_number": prescription.f_number,
        "hfov_deg": prescription.hfov_deg,
        "sanity_image_height_mm": prescription.image_height_mm,
        "semi_diameter_policy": "Optiland real-ray surface envelope; interpolated only when no finite ray reached a surface",
    }
    if trace_audit is not None:
        coverage.update(
            {
                "real_image_height_mm": trace_audit.real_image_height_mm,
                "aperture_interpolated_surfaces": ",".join(
                    str(index) for index in trace_audit.interpolated_surfaces
                )
                or "none",
                "finite_final_rays": f"{trace_audit.finite_final_rays}/{trace_audit.total_rays}",
            }
        )
    return coverage


def _write_report(
    report_path: Path,
    attempts: list[ConversionAttempt],
    *,
    target_successes: int,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    successes = [attempt for attempt in attempts if attempt.status == "success"]
    failure_reason_counts = _failure_reason_counts(attempts)
    lines = [
        "# DATA-06a patent-to-ZMX spike report",
        "",
        f"- target_successes: {target_successes}",
        f"- attempts: {len(attempts)}",
        f"- successes: {len(successes)}",
        f"- success_rate: {len(successes)}/{len(attempts)} ({(len(successes) / len(attempts) * 100 if attempts else 0.0):.1f}%)",
        f"- rechecked_failures: {len(attempts) - len(successes)}",
        "- failure_reason_counts:",
        *(
            [f"  - {reason}: {count}" for reason, count in sorted(failure_reason_counts.items())]
            if failure_reason_counts
            else ["  - none: 0"]
        ),
        "- source: local data/patents/uspto-smartphone-batch*.jsonl + USPTO PPUBS HTML",
        "- parser: deterministic NFKC-normalized embodiment table parse; no numeric LLM fill",
        "- clear_aperture: ZMX -> zmx_ingest/Optiland real-ray sampled per-surface envelope; f*tan(HFOV) is sanity-only",
        "- imh: Optiland edge-field finite-ray image height persisted in report and ZMX tail comments",
        "",
        "## Per-patent attempts",
        "",
        "| patent | embodiment | status | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |",
        "|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for attempt in attempts:
        coverage = _format_coverage(attempt.coverage)
        efl = "" if attempt.efl_mm is None else f"{attempt.efl_mm:.6g}"
        real_imh = (
            "" if attempt.real_image_height_mm is None else f"{attempt.real_image_height_mm:.6g}"
        )
        sanity_imh = (
            "" if attempt.sanity_image_height_mm is None else f"{attempt.sanity_image_height_mm:.6g}"
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _md_cell(attempt.patent_id),
                    _md_cell(attempt.embodiment),
                    attempt.status,
                    _md_cell(attempt.zmx_path),
                    efl,
                    real_imh,
                    sanity_imh,
                    _md_cell(coverage),
                    _md_cell(attempt.reason),
                )
            )
            + " |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _failure_reason_counts(attempts: list[ConversionAttempt]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for attempt in attempts:
        if attempt.status == "success":
            continue
        if attempt.status == "duplicate_prescription":
            counts["duplicate_prescription"] += 1
            continue
        reason = attempt.reason.strip()
        if not reason:
            counts["unknown"] += 1
            continue
        match = re.match(r"([A-Za-z_][A-Za-z0-9_.]*)(?::|$)", reason)
        counts[match.group(1) if match else reason.split(maxsplit=1)[0]] += 1
    return counts


def _format_coverage(coverage: dict[str, Any]) -> str:
    if not coverage:
        return ""
    keys = (
        "surfaces",
        "r",
        "d",
        "nd_vd",
        "asphere_surfaces",
        "f_mm",
        "f_number",
        "hfov_deg",
        "real_image_height_mm",
        "sanity_image_height_mm",
        "finite_final_rays",
        "aperture_interpolated_surfaces",
    )
    return "; ".join(f"{key}={coverage[key]}" for key in keys if key in coverage)


def write_patent_zmx(
    prescription: PatentPrescription,
    output_path: Path,
) -> TraceApertureAudit:
    """Write a final patent ZMX after real-ray surface aperture auditing."""

    _validate_prescription_materials(prescription)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.trace-tmp")
    provisional_readout = build_readout_from_prescription(prescription)
    try:
        _write_patent_readout_zmx(
            provisional_readout,
            temp_path,
            name=_safe_stem(prescription.patent_id),
        )
        trace_audit = _trace_surface_apertures(temp_path, prescription)
        final_readout = build_readout_from_prescription(
            prescription,
            semi_diameters_mm=trace_audit.semi_diameters_mm,
            image_height_y_mm=trace_audit.real_image_height_mm,
        )
        _write_patent_readout_zmx(
            final_readout,
            temp_path,
            name=_safe_stem(prescription.patent_id),
        )
        _append_zmx_tail_comments(temp_path, trace_audit)
        temp_path.replace(output_path)
        return trace_audit
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()
        raise


def _write_patent_readout_zmx(
    readout: CodeVReadout,
    output_path: Path,
    *,
    name: str,
) -> Path:
    xasphere_coefficients = _xasphere_surface_coefficients(readout)
    if not xasphere_coefficients:
        return write_zmx_from_codev_readout(readout, output_path, name=name)

    base_readout = _readout_without_xasphere_high_terms(readout)
    path = write_zmx_from_codev_readout(base_readout, output_path, name=name)
    _rewrite_high_order_aspheres_as_xdat(path, xasphere_coefficients)
    return path


def _xasphere_surface_coefficients(readout: CodeVReadout) -> dict[int, dict[str, float]]:
    result: dict[int, dict[str, float]] = {}
    for surface in readout.surfaces:
        if any(abs(surface.asphere_coefficients.get(label, 0.0)) > 0.0 for label in XASPHERE_HIGH_TERMS):
            result[surface.index] = dict(surface.asphere_coefficients)
    return result


def _readout_without_xasphere_high_terms(readout: CodeVReadout) -> CodeVReadout:
    surfaces = []
    for surface in readout.surfaces:
        coefficients = dict(surface.asphere_coefficients)
        for label in XASPHERE_HIGH_TERMS:
            coefficients[label] = 0.0
        surfaces.append(replace(surface, asphere_coefficients=coefficients))
    return replace(readout, surfaces=tuple(surfaces))


def _rewrite_high_order_aspheres_as_xdat(
    output_path: Path,
    xasphere_coefficients: dict[int, dict[str, float]],
) -> None:
    lines = output_path.read_text(encoding="ascii").splitlines()
    rewritten: list[str] = []
    index = 0
    while index < len(lines):
        surf_match = re.fullmatch(r"SURF\s+(\d+)", lines[index].strip())
        if surf_match is None or int(surf_match.group(1)) not in xasphere_coefficients:
            rewritten.append(lines[index])
            index += 1
            continue

        surface_index = int(surf_match.group(1))
        block = [lines[index]]
        index += 1
        while index < len(lines) and not re.fullmatch(r"SURF\s+\d+", lines[index].strip()):
            block.append(lines[index])
            index += 1
        rewritten.extend(
            _xasphere_surface_block(block, xasphere_coefficients[surface_index])
        )
    output_path.write_bytes(("\r\n".join(rewritten) + "\r\n").encode("ascii"))


def _xasphere_surface_block(block: list[str], coefficients: dict[str, float]) -> list[str]:
    result: list[str] = []
    inserted_xdat = False
    for line in block:
        stripped = line.strip()
        if stripped == "TYPE EVENASPH":
            result.append("  TYPE XASPHERE")
            continue
        if re.fullmatch(r"PARM\s+\d+\s+.+", stripped):
            if not inserted_xdat:
                result.extend(_xdat_lines(coefficients))
                inserted_xdat = True
            continue
        if stripped.startswith("DISZ ") and not inserted_xdat:
            result.extend(_xdat_lines(coefficients))
            inserted_xdat = True
        result.append(line)
    return result


def _xdat_lines(coefficients: dict[str, float]) -> list[str]:
    lines = [
        "  XDAT 1 10 0 0 1 0 0 \"\"",
        "  XDAT 2 1 0 0 1 0 0 \"\"",
        "  XDAT 3 0 0 0 1 0 0 \"\"",
    ]
    for xdat_index, label in enumerate(XASPHERE_WRITABLE_TERMS, start=4):
        value = coefficients.get(label, 0.0)
        lines.append(f"  XDAT {xdat_index} {_fmt_zmx_number(value)} 0 0 1 0 0 \"\"")
    return lines


def _fmt_zmx_number(value: float) -> str:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"ZMX numeric value must be finite: {value!r}")
    if abs(numeric) < 1e-15:
        numeric = 0.0
    return f"{numeric:.15g}"


def _trace_surface_apertures(
    output_path: Path,
    prescription: PatentPrescription,
) -> TraceApertureAudit:
    optic = load_normalized_zmx(output_path)
    samples = _trace_aperture_samples()
    h_x = np.array([sample[0] for sample in samples], dtype=float)
    h_y = np.array([sample[1] for sample in samples], dtype=float)
    p_x = np.array([sample[2] for sample in samples], dtype=float)
    p_y = np.array([sample[3] for sample in samples], dtype=float)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        rays = optic.trace_generic(h_x, h_y, p_x, p_y, TRACE_WAVELENGTH_UM)

    measured: dict[int, float] = {}
    surface_indices = sorted(surface.index for surface in prescription.surfaces)
    for surface_index in surface_indices:
        if surface_index >= len(optic.surfaces.surfaces):
            continue
        surface = optic.surfaces.surfaces[surface_index]
        x = np.asarray(getattr(surface, "x", []), dtype=float)
        y = np.asarray(getattr(surface, "y", []), dtype=float)
        radius = np.sqrt(x * x + y * y)
        finite = radius[np.isfinite(radius)]
        if finite.size:
            measured[surface_index] = float(np.max(finite))

    semi_diameters, interpolated = _interpolate_missing_surface_apertures(
        measured,
        surface_indices,
    )
    semi_diameters = {
        index: max(MIN_TRACE_SEMI_DIAMETER_MM, value * TRACE_APERTURE_CLEARANCE)
        for index, value in semi_diameters.items()
    }

    real_image_height = _edge_field_image_height(rays, samples)
    finite_final = int(np.isfinite(np.asarray(rays.y, dtype=float)).sum())

    return TraceApertureAudit(
        semi_diameters_mm=semi_diameters,
        real_image_height_mm=real_image_height,
        sanity_image_height_mm=prescription.image_height_mm,
        measured_surfaces=tuple(sorted(measured)),
        interpolated_surfaces=tuple(interpolated),
        finite_final_rays=finite_final,
        total_rays=len(samples),
    )


def _trace_aperture_samples() -> list[tuple[float, float, float, float]]:
    return [
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, -1.0),
    ]


def _edge_field_image_height(rays: Any, samples: list[tuple[float, float, float, float]]) -> float:
    y = np.asarray(rays.y, dtype=float)
    edge_indices = [
        index
        for index, sample in enumerate(samples)
        if math.isclose(sample[1], 1.0, abs_tol=1e-12)
    ]
    edge_y = np.abs(y[edge_indices])
    finite = edge_y[np.isfinite(edge_y)]
    if finite.size:
        return float(np.max(finite))
    raise PatentParseError("full-field real rays did not reach image surface")


def _interpolate_missing_surface_apertures(
    measured: dict[int, float],
    surface_indices: list[int],
) -> tuple[dict[int, float], list[int]]:
    if not measured:
        raise PatentParseError("real-ray trace produced no finite surface heights")

    result: dict[int, float] = {}
    interpolated: list[int] = []
    measured_indices = sorted(measured)
    for index in surface_indices:
        if index in measured:
            result[index] = measured[index]
            continue
        interpolated.append(index)
        lower = max((candidate for candidate in measured_indices if candidate < index), default=None)
        upper = min((candidate for candidate in measured_indices if candidate > index), default=None)
        if lower is not None and upper is not None:
            ratio = (index - lower) / (upper - lower)
            result[index] = measured[lower] + (measured[upper] - measured[lower]) * ratio
        elif lower is not None:
            result[index] = measured[lower]
        elif upper is not None:
            result[index] = measured[upper]
        else:
            raise PatentParseError(f"surface {index} aperture could not be interpolated")
    return result, interpolated


def _append_zmx_tail_comments(output_path: Path, trace_audit: TraceApertureAudit) -> None:
    comments = [
        f"! ATELIER_REAL_IMH_MM {_fmt_comment_number(trace_audit.real_image_height_mm)}",
        f"! ATELIER_FTAN_IMH_SANITY_MM {_fmt_comment_number(trace_audit.sanity_image_height_mm)}",
        f"! ATELIER_APERTURE_POLICY Optiland real-ray per-surface envelope; clearance={TRACE_APERTURE_CLEARANCE:.3g}",
        "! ATELIER_APERTURE_INTERPOLATED_SURFACES "
        + (",".join(str(index) for index in trace_audit.interpolated_surfaces) or "none"),
    ]
    with output_path.open("ab") as handle:
        for comment in comments:
            handle.write((comment + "\r\n").encode("ascii"))


def _fmt_comment_number(value: float) -> str:
    return f"{value:.10g}"


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _display_path(path: Path) -> str:
    with contextlib.suppress(ValueError):
        return str(path.relative_to(ROOT))
    return str(path)


def _find_required(text: str, needle: str, start: int) -> int:
    index = text.lower().find(needle.lower(), start)
    if index < 0:
        raise PatentParseError(f"{needle!r} section not found")
    return index


def _find_required_before(text: str, needle: str, start: int, end: int) -> int:
    index = text.lower().find(needle.lower(), start, end)
    if index < 0:
        raise PatentParseError(f"{needle!r} section not found in embodiment")
    return index


def _material_token(token: str) -> bool:
    return _strip_parens(token).upper() in MATERIAL_TOKENS


def _strip_parens(token: str) -> str:
    return token.strip().strip("()")


def _is_empty_value(token: str) -> bool:
    return _strip_parens(token).upper() in {"-", "--", "---", "—", "N/A", "NA"}


def _is_next_surface_index(token: str, expected: int) -> bool:
    return token.isdigit() and int(token) == expected


def _fujifilm_surface_marker(token: str) -> tuple[int, bool, bool] | None:
    match = re.fullmatch(r"(?P<asphere>\*)?(?P<index>\d+)(?P<stop>\(St\))?", token, re.I)
    if match is None:
        return None
    return (
        int(match.group("index")),
        bool(match.group("stop")),
        bool(match.group("asphere")),
    )


def _stop_surface_index(surfaces: list[PatentSurface]) -> int:
    for surface in surfaces:
        if "APE" in surface.label.upper() and "STOP" in surface.label.upper():
            return surface.index
    for surface in surfaces:
        if surface.label.upper() == "STOP":
            return surface.index
    return surfaces[0].index


def _surface_semi_diameter_for_readout(
    surface: PatentSurface,
    semi_diameters_mm: dict[int, float] | None,
) -> float:
    if semi_diameters_mm is not None and surface.index in semi_diameters_mm:
        return semi_diameters_mm[surface.index]
    return TRACE_PROVISIONAL_SEMI_DIAMETER_MM


def _finite_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    return value if math.isfinite(value) else 0.0


def _source_for_patent_id(patent_id: str) -> str:
    normalized = patent_id.upper()
    if re.search(r"-A\d+$", normalized):
        return "US-PGPUB"
    return "USPAT"


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return stem.strip("-") or "patent"


def _normalized_patent_id(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert USPTO patent embodiment prescription tables to staging ZMX files."
    )
    parser.add_argument("--pool-dir", type=Path, default=ROOT / "data" / "patents")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--target-successes", type=int, default=5)
    parser.add_argument("--max-attempts", type=int, default=40)
    parser.add_argument(
        "--case-index",
        type=Path,
        default=DEFAULT_CASE_INDEX_PATH,
        help="Formal case index used to skip already ingested patent embodiments.",
    )
    args = parser.parse_args()

    attempts = asyncio.run(
        run_conversion(
            pool_dir=args.pool_dir,
            output_dir=args.out_dir,
            report_path=args.report,
            target_successes=args.target_successes,
            max_attempts=args.max_attempts,
            case_index_path=args.case_index,
        )
    )
    successes = sum(attempt.status == "success" for attempt in attempts)
    return 0 if successes >= args.target_successes else 1


if __name__ == "__main__":
    sys.exit(main())
