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
import time
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
from app.core.patent_conversion_process import (  # noqa: E402
    DEFAULT_CONVERSION_TIMEOUT_SECONDS,
    PatentConversionRequest,
    PatentPrescriptionInput,
    PatentSurfaceInput,
    SourceDocumentEvidence,
    TraceAuditResult,
    run_patent_conversion_attempt,
    sha256_bytes,
)
from app.core.patent_replay import (  # noqa: E402
    SourceFetchAttempt,
    SourceFetchState,
)
from app.core.zmx_ingest import load_normalized_zmx  # noqa: E402
from scripts.patent_crawler import _ppubs_access_token, _ppubs_patent_html  # noqa: E402

DEFAULT_POOL_GLOB = "uspto-smartphone-batch*.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "zmx-staging"
DEFAULT_RAW_DOCUMENT_DIR = ROOT / "data" / "patent-lake" / "uspto-ppubs-html"
DEFAULT_ATTEMPTS_DIR = ROOT / "data" / "patent-conversion-attempts"
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


class PatentTraceError(RuntimeError):
    """Raised when deterministic prescription tracing or ZMX validation fails."""


class PatentFulltextFetchError(PatentParseError):
    """Raised after every configured PPUBS source bucket failed with evidence."""

    def __init__(self, attempts: tuple[SourceFetchAttempt, ...]) -> None:
        self.attempts = attempts
        summary = "; ".join(
            f"{item.source_bucket}:{item.state.value}:{item.http_status or item.exception_type}"
            for item in attempts
        )
        super().__init__(f"USPTO HTML unavailable ({summary})")


@dataclass(frozen=True)
class PatentCandidate:
    patent_id: str
    title: str
    source_url: str
    pool_path: Path
    line_number: int


@dataclass(frozen=True)
class FetchedPatentHtml:
    html: str
    source_bucket: str
    attempts: tuple[SourceFetchAttempt, ...] = ()


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
    reason_code: str = ""
    attempt_id: str = ""
    request_sha256: str = ""
    receipt_path: str = ""
    raw_document_path: str = ""
    raw_document_sha256: str = ""
    source_bucket: str = ""
    source_attempts: tuple[SourceFetchAttempt, ...] = ()
    embodiment_number: int | None = None
    prescription_fingerprint: str = ""
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
        # NEWMAX carries exact metadata inside its family-specific TABLE header.
        # Keep this strict fallback separate so primary does not grow permissive.
        attempts = _parse_newmax_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_fujifilm_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_apple_exemplary_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_mobile_imaging_lens_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_kantatsu_six_lens_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_kantatsu_ih_first_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_kantatsu_inline_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_kantatsu_nine_lens_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_folded_macro_tele_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_samsung_wide_fov_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_folded_zoom_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_aac_raytech_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_sunny_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_sekonix_table_attempts(text, patent_id=patent_id)
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
    coeff_start = _find_required_before_any(
        text,
        # Ability Opto (DATA-10b family expansion) titles the block
        # "Coefficients of the aspheric surfaces" instead of the primary
        # "Aspheric Coefficients" heading.
        ("Aspheric Coefficients", "Coefficients of the aspheric surfaces"),
        meta.end,
        section_end,
    )
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


# ---------------------------------------------------------------------------
# NEWMAX fallback family. Static publications pair a prescription table with
# the immediately following asphere table and carry f/Fno/full FOV in-header.
# ---------------------------------------------------------------------------

_NEWMAX_HEADER_RE = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Embodiment\s+(?P<embodiment>\d+)\s+"
    rf"f(?:\s*\(\s*focal\s+length\s*\))?\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm\s*,?\s*"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s*,?\s*"
    rf"FOV(?:\s*\(\s*field\s+of\s+view\s+2\s*[ωw]\s*\))?\s*=\s*"
    rf"(?P<fov>{NUMBER_PATTERN})\s*(?:deg\.?|°)",
    re.IGNORECASE,
)
_NEWMAX_ORDINAL_HEADER_RE = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+"
    rf"(?P<ordinal>First|Second|Third|Fourth|Fifth|Sixth|Seventh)\s+Embodiment\s+"
    rf"f\s*\(\s*focal\s+length\s*\)\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm"
    rf"(?:\s*\(\s*millimeters?\s*\))?\s*,\s*"
    rf"Fno\s*\(\s*f-number\s*\)\s*=\s*(?P<fno>{NUMBER_PATTERN})\s*,\s*"
    rf"FOV\s*\(\s*field\s+of\s+view(?:\s+2\s*(?:ω|w))?\s*\)\s*=\s*"
    rf"(?P<fov>{NUMBER_PATTERN})\s*deg\.?"
    rf"(?:\s*\(\s*degrees?\s*\))?",
    re.IGNORECASE,
)
_NEWMAX_ORDINAL_FULL_FIELD_DEFINITION_RE = re.compile(
    r"\b(?:A\s+)?half\s+of\s+(?:a|the)\s+maximum\s+field\s+of\s+view\b"
    r".{0,160}\bHFOV\b",
    re.IGNORECASE | re.DOTALL,
)
_NEWMAX_COEFFICIENT_LABEL_RE = re.compile(r"[A-Z]:?|A\d+:?", re.IGNORECASE)
_NEWMAX_OBJECT_ROW_RE = re.compile(r"\b0\s+Object\b", re.IGNORECASE)
_NEWMAX_ORDINAL_LENS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
}


def _newmax_table_header(block_text: str) -> re.Match[str] | None:
    return _NEWMAX_HEADER_RE.search(block_text) or _NEWMAX_ORDINAL_HEADER_RE.search(block_text)


def _parse_newmax_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse NEWMAX static surface/coefficient table pairs independently."""

    blocks = _patent_table_blocks(text)
    surface_blocks = [
        (index, block, match)
        for index, block in enumerate(blocks)
        if (match := _newmax_table_header(block.text)) is not None
        and _NEWMAX_OBJECT_ROW_RE.search(block.text)
    ]
    if not surface_blocks:
        return []

    attempts: list[_PrescriptionParseAttempt] = []
    for block_index, block, header in surface_blocks:
        ordinal = header.groupdict().get("ordinal")
        embodiment_number = (
            _NEWMAX_ORDINAL_LENS[ordinal.lower()]
            if ordinal is not None
            else int(header.group("embodiment"))
        )
        embodiment = f"Embodiment {embodiment_number}"
        try:
            if ordinal is not None:
                if block.number != embodiment_number * 2 - 1:
                    raise PatentParseError(
                        f"NEWMAX {embodiment} surface table number is not ordinal-bound"
                    )
                if _NEWMAX_ORDINAL_FULL_FIELD_DEFINITION_RE.search(text) is None:
                    raise PatentParseError(
                        "NEWMAX ordinal family maximum-FOV/HFOV definition not found"
                    )
            surfaces, index_by_label = _parse_newmax_surface_table(
                block.text, embodiment_number=embodiment_number
            )
            if block_index + 1 >= len(blocks):
                raise PatentParseError(f"NEWMAX {embodiment} lacks paired coefficient table")
            coefficient_block = blocks[block_index + 1]
            if coefficient_block.number != block.number + 1:
                raise PatentParseError(f"NEWMAX {embodiment} coefficient table is not adjacent")
            coefficients = _parse_newmax_asphere_table(
                coefficient_block.text, index_by_label=index_by_label
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.asphere_coefficients.update(coefficients[surface.index])
                    surface.surface_type = "ASP"
            focal_length = _parse_number(header.group("f"))
            f_number = _parse_number(header.group("fno"))
            half_field = _parse_number(header.group("fov")) / 2.0
            if focal_length <= 0 or f_number <= 0 or not 0 < half_field < 90:
                raise PatentParseError(f"NEWMAX {embodiment} has invalid f/Fno/full-FOV metadata")
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - per-embodiment fail-loud ledger
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


def _parse_newmax_surface_table(
    block_text: str,
    *,
    embodiment_number: int,
) -> tuple[list[PatentSurface], dict[str, int]]:
    """Parse NEWMAX rows after normalizing only documented label variants."""

    match = _NEWMAX_OBJECT_ROW_RE.search(block_text)
    if match is None:
        raise PatentParseError(f"NEWMAX embodiment {embodiment_number} object row not found")
    table_text = block_text[match.start() :]
    table_text = re.sub(
        r"\b(First|Second|Third|Fourth|Fifth|Sixth|Seventh)\s+lens\b",
        _newmax_ordinal_lens,
        table_text,
        flags=re.IGNORECASE,
    )
    table_text = re.sub(
        r"\b(?:IR-filter|IR\s+bandpass|Optical\s+filter)\b",
        "Filter",
        table_text,
        flags=re.IGNORECASE,
    )
    table_text = re.sub(r"\bImage\s+plane\b", "Image", table_text, flags=re.IGNORECASE)
    surfaces = _parse_surface_table(table_text)
    for surface in surfaces:
        if surface.material is not None and (surface.nd is None or surface.vd is None):
            raise PatentParseError(f"NEWMAX surface {surface.index} material lacks printed nd/vd")
    optical_surfaces = [surface for surface in surfaces if surface.index > 0]
    if len(optical_surfaces) < 4 or optical_surfaces[-1].label.upper() != "IMAGE":
        raise PatentParseError(f"NEWMAX embodiment {embodiment_number} surface table is incomplete")
    if sum(surface.label.upper() == "STOP" for surface in optical_surfaces) != 1:
        raise PatentParseError(
            f"NEWMAX embodiment {embodiment_number} must publish exactly one stop"
        )
    return optical_surfaces, {str(surface.index): surface.index for surface in optical_surfaces}


def _newmax_ordinal_lens(match: re.Match[str]) -> str:
    return f"Lens {_NEWMAX_ORDINAL_LENS[match.group(1).lower()]}"


def _parse_newmax_asphere_table(
    block_text: str,
    *,
    index_by_label: dict[str, int],
) -> dict[int, dict[str, float]]:
    """Map the two published NEWMAX monomial coefficient conventions."""

    block_text = re.split(r"\s(?:\(\d+\)|\[\d+\])\s", block_text, maxsplit=1)[0]
    tokens = block_text.split()
    coefficients: dict[int, dict[str, float]] = {}
    pos = 0
    while pos < len(tokens):
        if tokens[pos].lower() != "surface":
            pos += 1
            continue
        pos += 1
        surface_labels: list[str] = []
        while pos < len(tokens) and tokens[pos].isdigit():
            surface_labels.append(tokens[pos])
            pos += 1
        if not surface_labels:
            continue
        while pos < len(tokens):
            raw_label = tokens[pos]
            if raw_label.lower() == "surface":
                break
            if _NEWMAX_COEFFICIENT_LABEL_RE.fullmatch(raw_label) is None:
                pos += 1
                continue
            label = raw_label.rstrip(":").upper()
            pos += 1
            values: list[float] = []
            for surface_label in surface_labels:
                if pos >= len(tokens):
                    raise PatentParseError(
                        f"NEWMAX {label} row is incomplete at surface {surface_label}"
                    )
                try:
                    values.append(_parse_number(tokens[pos]))
                except PatentParseError as exc:
                    raise PatentParseError(
                        f"NEWMAX {label} row has nonnumeric data token: {tokens[pos]}"
                    ) from exc
                pos += 1
            for surface_label, value in zip(surface_labels, values, strict=True):
                codev_label = _newmax_codev_asphere_label(label, value, surface_label)
                if codev_label is None:
                    continue
                surface_index = index_by_label.get(surface_label)
                if surface_index is None:
                    raise PatentParseError(
                        f"NEWMAX coefficient references unknown surface {surface_label}"
                    )
                coefficients.setdefault(surface_index, {})[codev_label] = value
    if not coefficients:
        raise PatentParseError("NEWMAX asphere table had no coefficient rows")
    return coefficients


def _newmax_codev_asphere_label(label: str, value: float, surface_label: str) -> str | None:
    if label == "K":
        return "K"
    # US-10101561-B2, Equation 1 (Google Patents, verbatim term sequence):
    # ``A h^4 + B h^6 + C h^8 + D h^10 + E h^12 + G h^14 + ...``.
    # The published coefficient table prints its sixth row as ``F`` while the
    # equation names that h^14 term ``G`` (the letter F is skipped in the
    # equation).  Table rows A..F therefore map positionally to h^4..h^14 --
    # but any table letter beyond F is ambiguous between the two lettering
    # schemes (positional G=h^16 vs equation G=h^14), so nonzero values there
    # must fail loud rather than risk an order-shift (E1-01 incident class).
    if len(label) == 1 and "A" <= label <= "Z":
        if label > "F":
            if abs(value) > 0.0:
                raise PatentParseError(
                    "ambiguous NEWMAX alphabetic coefficient beyond F "
                    f"(equation lettering skips F): surface {surface_label}:{label}={value:.3g}"
                )
            return None
        order = 4 + 2 * (ord(label) - ord("A"))
    else:
        order_match = re.fullmatch(r"A(\d+)", label)
        if order_match is None:
            raise PatentParseError(f"unsupported NEWMAX coefficient label: {label}")
        order = int(order_match.group(1))
        # US-12596237-B2, Equation 2 (Google Patents, verbatim):
        # ``z(h) = ch^2/{1+[1-(k+1)c^2h^2]^0.5} + Σ(A_i)·(h^i)``.
        # A2 multiplies h^2. It is verified zero and never shifted into A4.
        if order == 2:
            if abs(value) > 0.0:
                raise PatentParseError(
                    f"nonzero NEWMAX A2 term: surface {surface_label}:A2={value:.3g}"
                )
            return None
    codev_label = ASPHERE_ORDER_TO_CODEV.get(order)
    if codev_label is None:
        if abs(value) > 0.0:
            raise PatentParseError(
                f"unsupported nonzero NEWMAX asphere term: surface {surface_label}:{label}={value:.3g}"
            )
        return None
    return codev_label


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
        next_basic_start = basic_matches[index].start() if index < len(basic_matches) else len(text)
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
                        "unsupported nonzero Fujifilm asphere terms: " + ", ".join(unsupported[:8])
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
_SUFFIXED_PATENT_TABLE_BLOCK_PATTERN = re.compile(
    r"\bTABLE-US-\d+\s+TABLE\s+(?P<number>\d+)(?P<suffix>[A-Z])\s+",
    flags=re.IGNORECASE,
)
_APPLE_EXEMPLARY_HEADER_PATTERN = re.compile(
    rf"\bOptical\s+data\s+for\s+a\s+"
    rf"(?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+"
    rf"exemplary\s+embodiment\s+shown\s+in\s+FIG\.\s+\d+\s+"
    rf"f\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm\s*,\s*"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s*,\s*"
    rf"HFOV\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s*deg\s*,\s*"
    rf"TTL\s*=\s*(?P<ttl>{NUMBER_PATTERN})\s*mm\s+"
    r"S\.sub\.i\s+Component\s+R\.sub\.i\s+Shape\s+D\.sub\.i\s+"
    r"Material\s+N\.sub\.d\s+V\.sub\.d\s+f\.sub\.l\b",
    flags=re.IGNORECASE,
)
_APPLE_EXEMPLARY_ROW_PATTERN = re.compile(
    rf"(?<!\S)(?P<index>\d+)\s+"
    rf"(?=(?:Object\b|L\.sub\.\d+\b|IR\b|Image\b|INF\b|{NUMBER_PATTERN}))",
    flags=re.IGNORECASE,
)
_MOBILE_IMAGING_LENS_SURFACE_HEADER_PATTERN = re.compile(
    rf"\bf\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"ω\s*=\s*(?P<hfov>{NUMBER_PATTERN})°\s+"
    r"i\s+r\s+d\s+n\s+d\s+νd\s+\[mm\]\s+",
    flags=re.IGNORECASE,
)
_MOBILE_IMAGING_LENS_HALF_FIELD_DEFINITION = re.compile(
    r"ω\s+represents\s+a\s+half\s+field\s+of\s+view\b",
    flags=re.IGNORECASE,
)
_MOBILE_IMAGING_LENS_SURFACE_ROW_PATTERN = re.compile(
    r"(?<!\S)(?:(?P<label>L[1-8]|ST)\s+)?"
    r"(?P<index>(?:[1-9]|1[0-9]))(?P<star>\*)?\s+",
    flags=re.IGNORECASE,
)
_MOBILE_IMAGING_LENS_SINGLE_ASPHERE_HEADER = re.compile(
    r"\bAspheric\s+[Ss]urface\s+Data:\s+(?:i\s+)?"
    r"k\s+A4\s+A6\s+A8\s+A10\s+A12\s+A14\s+A16\s+",
    flags=re.IGNORECASE,
)
_MOBILE_IMAGING_LENS_SPLIT_ASPHERE_HEADER = re.compile(
    r"\bAspheric\s+[Ss]urface\s+Data:\s+i\s+"
    r"k\s+A4\s+A6\s+A8\s+A10\s+",
    flags=re.IGNORECASE,
)
_MOBILE_IMAGING_LENS_SECOND_ASPHERE_HEADER = (
    "i",
    "A12",
    "A14",
    "A16",
    "A18",
    "A20",
)
_KANTATSU_INLINE_HEADER_PATTERN = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Example\s+(?P<example>[lL]|\d+)\s+"
    rf"Unit\s+mm\s+f\s*=\s*(?P<f>{NUMBER_PATTERN})\s+"
    rf"ih\s*=\s*(?P<ih>{NUMBER_PATTERN})\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"TTL\s*=\s*(?P<ttl>{NUMBER_PATTERN})\s+"
    rf"\u03c9\s*\(\s*\u00b0\s*\)\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s+"
    r"Surface\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_INLINE_BINDING_PATTERN = re.compile(
    r"\bExample\s+(?P<example>\d+)\s+\[\d+\]\s+The\s+basic\s+lens\s+data\s+"
    r"is\s+shown\s+below\s+in\s+Table\s+(?P<table>\d+)\.\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<header_table>\d+)\s+"
    r"Example\s+(?P<header_example>[lL]|\d+)\s+Unit\s+mm\b",
    flags=re.IGNORECASE,
)
_KANTATSU_INLINE_HALF_FIELD_DEFINITION = re.compile(
    r"\bIn\s+each\s+example,\s+f\s+denotes\s+the\s+focal\s+length\s+of\s+the\s+"
    r"overall\s+optical\s+system\s+of\s+the\s+imaging\s+lens,\s+Fno\s+denotes\s+"
    r"a\s+F-number,\s+\u03c9\s+denotes\s+a\s+half\s+field\s+of\s+view,\s+ih\s+"
    r"denotes\s+a\s+maximum\s+image\s+height,\s+and\s+TTL\s+denotes\s+(?:a\s+)?"
    r"total\s+track\s+length\b",
    flags=re.IGNORECASE,
)
_KANTATSU_INLINE_ASPHERE_DEFINITION = re.compile(
    r"\bA4,\s+A6,\s+A8,\s+A10,\s+A12,\s+A14,\s+A16,\s+A18\s+and\s+A20\s+"
    r"denote\s+aspheric\s+surface\s+coefficients\b",
    flags=re.IGNORECASE,
)
_KANTATSU_INLINE_SURFACE_ROW_PATTERN = re.compile(
    r"(?<!\S)(?P<index>\d+)(?P<star>\*)?\s+(?P<stop>\(Stop\))?\s*",
    flags=re.IGNORECASE,
)
_KANTATSU_INLINE_MATERIAL_SUFFIX = re.compile(
    r"\((?:v|\u03bd)d(?P<lens>\d+)\)",
    flags=re.IGNORECASE,
)
_KANTATSU_INLINE_ORDINALS = {
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
}
_KANTATSU_INLINE_ORDINAL_PATTERN = "|".join(_KANTATSU_INLINE_ORDINALS)
_KANTATSU_INLINE_ASPHERE_GROUP_PATTERN = re.compile(
    rf"(?P<headings>(?:(?:{_KANTATSU_INLINE_ORDINAL_PATTERN})\s+Surface\s+)+)k\s+",
    flags=re.IGNORECASE,
)
_KANTATSU_SIX_LENS_ASPHERE_GROUP_PATTERN = re.compile(
    rf"(?P<headings>(?:(?:{_KANTATSU_INLINE_ORDINAL_PATTERN})\s+){{6}}"
    r"(?:Surface\s+){6})k\s+",
    flags=re.IGNORECASE,
)
_KANTATSU_SIX_LENS_HEADER_PATTERN = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Example\s+(?P<example>\d+)\s+"
    rf"Unit\s+mm\s+f\s*=\s*(?P<f>{NUMBER_PATTERN})\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"[^\s=]+\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s+"
    rf"h\s*=\s*(?P<ih>{NUMBER_PATTERN})\s+"
    rf"TTL\s*=\s*(?P<ttl>{NUMBER_PATTERN})\s+Surface\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_SIX_LENS_BINDING_PATTERN = re.compile(
    r"\bExample\s+(?P<example>\d+)\s+\[\d+\]\s+The\s+basic\s+lens\s+data\s+"
    r"is\s+shown\s+below\s+in\s+Table\s+(?P<table>\d+)\.\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<header_table>\d+)\s+"
    r"Example\s+(?P<header_example>\d+)\s+Unit\s+mm\b",
    flags=re.IGNORECASE,
)
_KANTATSU_SIX_LENS_HALF_FIELD_DEFINITION = re.compile(
    r"\bIn\s+each\s+example,\s+f\s+denotes\s+a\s+focal\s+length\s+of\s+the\s+"
    r"overall\s+optical\s+system\s+of\s+the\s+imaging\s+lens,\s+Fno\s+denotes\s+"
    r"a\s+F-number,\s+\S+\s+denotes\s+a\s+half\s+field\s+of\s+view,\s+ih\s+"
    r"denotes\s+a\s+maximum\s+image\s+height,\s+and\s+TTL\s+denotes\s+a\s+"
    r"total\s+track\s+length\b",
    flags=re.IGNORECASE,
)
_KANTATSU_SIX_LENS_ASPHERE_DEFINITION = re.compile(
    r"\bA4,\s+A6,\s+A8,\s+A10,\s+A12,\s+A14\s+and\s+A16\s+denote\s+"
    r"aspheric\s+surface\s+coefficients\b",
    flags=re.IGNORECASE,
)
_KANTATSU_IH_FIRST_HEADER_PATTERN = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Example\s*(?P<example>\d+)\s+"
    rf"Unit\s+mm\s+f\s*=\s*(?P<f>{NUMBER_PATTERN})\s+"
    rf"i\s*h\s*=\s*(?P<ih>{NUMBER_PATTERN})\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"TTL\s*=\s*(?P<ttl>{NUMBER_PATTERN})\s+"
    rf"\S+\s*\(\s*\)\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s+Surface\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_IH_FIRST_BINDING_PATTERN = re.compile(
    r"\bExample\s+(?P<example>\d+)\s+\[\d+\]\s+The\s+basic\s+lens\s+data\s+"
    r"is\s+shown\s+below\s+in\s+Table\s+(?P<table>\d+)\.\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<header_table>\d+)\s+"
    r"Example\s*(?P<header_example>\d+)\s+Unit\s+mm\b",
    flags=re.IGNORECASE,
)
_KANTATSU_IH_FIRST_HALF_FIELD_DEFINITION = re.compile(
    r"\bIn\s+each\s+example,\s+f\s+denotes\s+the\s+focal\s+length\s+of\s+the\s+"
    r"overall\s+optical\s+system\s+of\s+the\s+imaging\s+lens,\s+Fno\s+denotes\s+"
    r"an\s+F-number,\s+\S+\s+denotes\s+a\s+half\s+field\s+of\s+view,\s+ih\s+"
    r"denotes\s+a\s+maximum\s+image\s+height,\s+and\s+TTL\s+denotes\s+a\s+"
    r"total\s+track\s+length\b",
    flags=re.IGNORECASE,
)
_KANTATSU_IH_FIRST_ASPHERE_DEFINITION = re.compile(
    r"\bA4,\s+A6,\s+A8,\s+A10,\s+A12,\s+A14\s+and\s+A16\s+denote\s+"
    r"aspheric\s+surface\s+coefficients\b",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_BINDING_PATTERN = re.compile(
    r"\bNumerical\s+Data\s+Example\s+(?P<example>\d+)\s+\[\d+\]\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<table>\d+)\s+Basic\s+Lens\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_PRETABLE_BINDING_PATTERN = re.compile(
    r"\bNumerical\s+Data\s+Example\s+(?P<example>\d+)\s+"
    r"Basic\s+Lens\s+Data\s+\[\d+\]\s+TABLE-US-\d+\s+"
    r"TABLE\s+(?P<table>\d+)\b",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_META_PATTERN = re.compile(
    rf"\bf\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"ω\s*=\s*(?P<hfov>{NUMBER_PATTERN})°",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_HALF_FIELD_DEFINITION = re.compile(
    r"\bf\s+represents\s+a\s+focal\s+length\s+of\s+the\s+whole\s+lens\s+system,\s+"
    r"Fno\s+represents\s+an\s+F-number,\s+and\s+ω\s+represents\s+a\s+half\s+"
    r"angle\s+of\s+view\b",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_UNIT_PATTERN = re.compile(
    r"\bBasic\s+Lens\s+Data\b.*?\[(?P<unit>[mn]m)\]",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_PRETABLE_UNIT_PATTERN = re.compile(
    r"\bi\s+r\s+d\s+n\s+d\s+ν\s+d\s+\[(?P<unit>[mn]m)\]",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_FIRST_SURFACE_PATTERN = re.compile(
    r"\bL1\s+1\s*\*\s*\(ST\)\s+",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_SURFACE_ROW_PATTERN = re.compile(
    r"(?<!\S)(?:(?P<label>L[1-9])\s+)?"
    r"(?P<index>(?:[1-9]|1[0-9]|20))\s*(?P<star>\*)?\s*"
    r"(?P<stop>\(ST\))?\s+",
    flags=re.IGNORECASE,
)
_KANTATSU_NINE_LENS_ASPHERE_HEADER = re.compile(
    r"\bAspherical\s+surface\s+data\s+i\s+k\s+A4\s+A6\s+A8\s+A10\s+"
    r"A12\s+A14\s+A16\s+",
    flags=re.IGNORECASE,
)
_FOLDED_MACRO_TELE_SIGNATURE = re.compile(
    rf"\bLens\s+system\s+200\s+EFL\s*=\s*{NUMBER_PATTERN}\s*mm\s*,\s*"
    rf"F\s+number\s*=\s*{NUMBER_PATTERN}\s*,\s*"
    rf"(?:Half\s+FOV|HFOV)\s*=\s*{NUMBER_PATTERN}\s*deg\.?",
    flags=re.IGNORECASE,
)
_FOLDED_MACRO_TELE_HALF_FIELD_DEFINITION = re.compile(
    r"\bHalf\s+FOV\s*\(HFOV\)\s+are\s+given\b",
    flags=re.IGNORECASE,
)
_FOLDED_MACRO_TELE_HEADER = re.compile(
    rf"\b(?:Lens\s+system|Embodiment)\s+(?P<system>200|220|230|240|290)\s+"
    rf"(?P<focal_label>EFL|F)\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm\s*,\s*"
    rf"F\s+number\s*=\s*(?P<fno>{NUMBER_PATTERN})\s*,\s*"
    rf"(?:Half\s+FOV|HFOV)\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s*deg\.?\s+"
    r"Aperture\s+Curvature\s+Radius\s+Focal\s+Surface\s+#\s+Comment\s+Type\s+"
    r"Radius\s+Thickness\s+\(D/2\)\s+Material\s+Index\s+Abbe\s+#\s+Length\s+",
    flags=re.IGNORECASE,
)
_FOLDED_MACRO_TELE_SYSTEM_TABLES = {
    "200": (1, 2, 3, 6),
    "220": (5, 6, 7, 7),
    "230": (9, 10, 11, 8),
    "240": (13, 14, 16, 6),
    "290": (19, 20, 21, 8),
}
_SAMSUNG_WIDE_FOV_BINDING_PATTERN = re.compile(
    r"\bTables\s+(?P<surface_table>\d+)\s+and\s+(?P<coefficient_table>\d+)\s+below\s+"
    r"list\s+the\s+lens\s+properties\s+and\s+aspherical\s+values\s+of\s+the\s+"
    r"(?P<ordinal>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+"
    r"embodiment\s+of\s+the\s+imaging\s+lens\s+system\.",
    flags=re.IGNORECASE,
)
_SAMSUNG_WIDE_FOV_SURFACE_HEADER_PATTERN = re.compile(
    r"\bSurface\s+Radius\s+of\s+Thickness/\s+Refractive\s+Abbe\s+Effective\s+"
    r"No\.\s+Component\s+Curvature\s+Distance\s+Index\s+Number\s+Radius\s+",
    flags=re.IGNORECASE,
)
_SAMSUNG_WIDE_FOV_COEFFICIENT_HEADER_PATTERN = re.compile(
    r"\bSurface\s+No\.\s+S3\s+S4\s+S5\s+S6\s+S13\s+S14\s+",
    flags=re.IGNORECASE,
)
_SAMSUNG_WIDE_FOV_FULL_FIELD_DEFINITION = re.compile(
    r"\bHFOV\s+is\s+a\s+field\s+of\s+view\s+of\s+the\s+imaging\s+plane\s+in\s+a\s+"
    r"horizontal\s+direction\s+expressed\s+in\s+degrees\b",
    flags=re.IGNORECASE,
)
_FOLDED_ZOOM_ASP_SURFACE_HEADER_PATTERN = re.compile(
    r"\bOptical\s+lens\s+system\s+(?P<system>\d+)\s+.*?"
    r"\bSurface(?:\s+Curvature\s+Aperture\s+Radius\s+Abbe\s+Focal)?\s+"
    r"#\s+Comment\s+Type\s+Radius\s+Thickness\b",
    flags=re.IGNORECASE,
)
_FOLDED_ZOOM_QTYP_SURFACE_HEADER_PATTERN = re.compile(
    r"\bOptical\s+lens\s+system\s+(?P<system>\d+)\s+.*?"
    r"\bGroup\s+Lens\s+Surface\s+Type\s+R\s+\[mm\]\s+T\s+\[mm\]",
    flags=re.IGNORECASE,
)
_FOLDED_ZOOM_NUMERIC_ROW_PATTERN = re.compile(
    r"(?<!\S)(?P<index>\d+)\s+"
    r"(?=(?:Lens\s+\d+\b|Filter\b|Image\b|[-+]?(?:\d|\.)|Infinity\b))",
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


def _parse_apple_exemplary_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact Apple ``TABLE nA/nB`` exemplary prescription pairs."""

    blocks = _suffixed_patent_table_blocks(text)
    surface_blocks = [
        (number, block_text, header)
        for (number, suffix), block_text in sorted(blocks.items())
        if suffix == "A"
        and (header := _APPLE_EXEMPLARY_HEADER_PATTERN.search(block_text)) is not None
    ]
    if not surface_blocks:
        return []

    attempts: list[_PrescriptionParseAttempt] = []
    for attempt_number, (number, surface_text, header) in enumerate(surface_blocks, start=1):
        embodiment = f"Apple exemplary embodiment {number}"
        try:
            expected_ordinal = _ordinal_word(number)
            if header.group("ordinal").lower() != expected_ordinal:
                raise PatentParseError(
                    f"Apple TABLE {number}A ordinal does not match its table number"
                )
            coefficient_text = blocks.get((number, "B"))
            if coefficient_text is None:
                raise PatentParseError(f"Apple TABLE {number}B coefficient table not found")
            surfaces = _parse_apple_exemplary_surface_table(
                surface_text,
                header=header,
                embodiment_number=number,
            )
            coefficients = _parse_apple_exemplary_asphere_table(
                coefficient_text,
                embodiment_number=number,
                ordinal=expected_ordinal,
            )
            surface_indices = {surface.index for surface in surfaces}
            if not set(coefficients).issubset(surface_indices):
                raise PatentParseError(
                    f"Apple embodiment {number} coefficient table references an unknown surface"
                )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=_parse_number(header.group("f")),
                f_number=_parse_number(header.group("fno")),
                hfov_deg=_parse_number(header.group("hfov")),
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - retained per exemplary embodiment
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=attempt_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=attempt_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _suffixed_patent_table_blocks(text: str) -> dict[tuple[int, str], str]:
    matches = list(_SUFFIXED_PATENT_TABLE_BLOCK_PATTERN.finditer(text))
    blocks: dict[tuple[int, str], str] = {}
    for index, match in enumerate(matches):
        key = (int(match.group("number")), match.group("suffix").upper())
        if key in blocks:
            raise PatentParseError(f"duplicate suffixed patent table: {key[0]}{key[1]}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[key] = text[match.start() : end]
    return blocks


def _ordinal_word(value: int) -> str:
    words = (
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
        "tenth",
    )
    if not 1 <= value <= len(words):
        raise PatentParseError(f"unsupported ordinal table number: {value}")
    return words[value - 1]


def _parse_apple_exemplary_surface_table(
    table_text: str,
    *,
    header: re.Match[str],
    embodiment_number: int,
) -> list[PatentSurface]:
    candidates = list(_APPLE_EXEMPLARY_ROW_PATTERN.finditer(table_text, header.end()))
    starts: list[re.Match[str]] = []
    expected_index = 0
    for match in candidates:
        if int(match.group("index")) != expected_index:
            continue
        starts.append(match)
        expected_index += 1
    if not starts or int(starts[-1].group("index")) != 9:
        raise PatentParseError(
            f"Apple embodiment {embodiment_number} surface sequence must be exactly S0-S9"
        )

    surfaces: list[PatentSurface] = []
    for row_index, match in enumerate(starts):
        surface_index = int(match.group("index"))
        end = starts[row_index + 1].start() if row_index + 1 < len(starts) else len(table_text)
        row = table_text[match.end() : end].split()
        upper = [token.upper() for token in row]
        shape_pos = next(
            (pos for pos, token in enumerate(upper) if token in {"FLT", "ASP"}),
            None,
        )
        if shape_pos is None or shape_pos == 0:
            raise PatentParseError(
                f"Apple embodiment {embodiment_number} surface {surface_index} shape missing"
            )
        radius = _distance_value(
            row[shape_pos - 1],
            field_name=f"Apple surface {surface_index} radius",
        )
        if surface_index == 9:
            thickness = 0.0
        elif shape_pos + 1 < len(row):
            thickness = _distance_value(
                row[shape_pos + 1],
                field_name=f"Apple surface {surface_index} thickness",
            )
        else:
            raise PatentParseError(
                f"Apple embodiment {embodiment_number} surface {surface_index} thickness missing"
            )

        material = nd = vd = None
        material_pos = next(
            (pos for pos, token in enumerate(upper) if token in {"PLASTIC", "GLASS"}),
            None,
        )
        if material_pos is not None:
            if material_pos + 2 >= len(row):
                raise PatentParseError(
                    f"Apple embodiment {embodiment_number} surface {surface_index} "
                    "material indices missing"
                )
            material = row[material_pos]
            nd = _parse_number(row[material_pos + 1])
            vd = _parse_number(row[material_pos + 2])
            _validate_material_indices(surface_index=surface_index, nd=nd, vd=vd)

        label_text = " ".join(row[: shape_pos - 1])
        if re.search(r"\bObject\s+plane\b", label_text, flags=re.IGNORECASE):
            label = "Object"
        elif re.search(r"\bImage\s+plane\b", label_text, flags=re.IGNORECASE):
            label = "Image"
        elif re.search(r"\bIR\s+filter\b", label_text, flags=re.IGNORECASE):
            label = "IR filter"
        elif lens_match := re.search(r"L\.sub\.(\d+)", label_text, flags=re.I):
            label = f"Lens {lens_match.group(1)}"
        else:
            label = f"Surface {surface_index}"
        if surface_index > 0:
            surfaces.append(
                PatentSurface(
                    index=surface_index,
                    label=label,
                    radius_mm=radius,
                    thickness_mm=thickness,
                    material=material,
                    nd=nd,
                    vd=vd,
                    surface_type="ASP" if upper[shape_pos] == "ASP" else None,
                )
            )
    if not surfaces or surfaces[-1].label != "Image":
        raise PatentParseError(f"Apple embodiment {embodiment_number} image row not found")
    return surfaces


def _parse_apple_exemplary_asphere_table(
    table_text: str,
    *,
    embodiment_number: int,
    ordinal: str,
) -> dict[int, dict[str, float]]:
    title = re.search(
        rf"\bAspheric\s+coefficients\s+for\s+the\s+{ordinal}\s+"
        rf"exemplary\s+embodiment\b",
        table_text,
        flags=re.IGNORECASE,
    )
    if title is None:
        raise PatentParseError(f"Apple embodiment {embodiment_number} coefficient title not found")
    section_matches = list(
        re.finditer(
            r"S\.sub\.i\s+(?P<labels>K\s+A\s+B\s+C|D\s+E\s+F)\s+",
            table_text,
            flags=re.IGNORECASE,
        )
    )
    if [match.group("labels").upper().split() for match in section_matches] != [
        ["K", "A", "B", "C"],
        ["D", "E", "F"],
    ]:
        raise PatentParseError(
            f"Apple embodiment {embodiment_number} coefficient sections are incomplete"
        )

    coefficients: dict[int, dict[str, float]] = {}
    for section_index, section in enumerate(section_matches):
        labels = section.group("labels").upper().split()
        end = (
            section_matches[section_index + 1].start()
            if section_index + 1 < len(section_matches)
            else len(table_text)
        )
        if claims_match := re.search(r"\bClaims\b", table_text[section.end() : end], re.I):
            end = section.end() + claims_match.start()
        row_pattern = re.compile(
            rf"(?<!\S)(?P<surface>[2-6])\s+(?={NUMBER_PATTERN})",
            flags=re.IGNORECASE,
        )
        row_candidates = list(row_pattern.finditer(table_text, section.end(), end))
        starts: list[re.Match[str]] = []
        expected_surface = 2
        for match in row_candidates:
            if int(match.group("surface")) != expected_surface:
                continue
            starts.append(match)
            expected_surface += 1
        if len(starts) != 5:
            raise PatentParseError(
                f"Apple embodiment {embodiment_number} coefficient row sequence is incomplete"
            )
        for row_index, row_match in enumerate(starts):
            surface = int(row_match.group("surface"))
            row_end = starts[row_index + 1].start() if row_index + 1 < len(starts) else end
            values = re.findall(
                NUMBER_PATTERN,
                table_text[row_match.end() : row_end],
                flags=re.IGNORECASE,
            )
            if not values or len(values) > len(labels):
                raise PatentParseError(
                    f"Apple embodiment {embodiment_number} surface {surface} "
                    f"coefficient row has {len(values)} values for {len(labels)} headers"
                )
            if section_index == 0 and len(values) != len(labels):
                raise PatentParseError(
                    f"Apple embodiment {embodiment_number} surface {surface} K/A/B/C row incomplete"
                )
            row = coefficients.setdefault(surface, {})
            for label, value_token in zip(labels, values, strict=False):
                row[label] = _parse_number(value_token)
    required = {"K", "A", "B", "C"}
    if set(coefficients) != set(range(2, 7)) or any(
        not required.issubset(row) for row in coefficients.values()
    ):
        raise PatentParseError(
            f"Apple embodiment {embodiment_number} coefficient coverage is incomplete"
        )
    return coefficients


def _parse_mobile_imaging_lens_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse the exact 12-example ``f/Fno/ω`` mobile imaging-lens family.

    The publication explicitly defines ``ω`` as half field of view.  One
    malformed coefficient token therefore rejects only its published example;
    values are never joined or repaired across whitespace.
    """

    raw_blocks = _patent_table_blocks(text)
    if not any(
        _MOBILE_IMAGING_LENS_SURFACE_HEADER_PATTERN.search(block.text) is not None
        for block in raw_blocks
    ):
        return []

    attempts: list[_PrescriptionParseAttempt] = []
    try:
        blocks = _numbered_patent_table_blocks(text)
        surface_headers = {
            table_number: header
            for table_number, block_text in blocks.items()
            if table_number % 2 == 1
            and (header := _MOBILE_IMAGING_LENS_SURFACE_HEADER_PATTERN.search(block_text))
            is not None
        }
        if set(blocks) != set(range(1, 25)):
            raise PatentParseError("mobile imaging-lens family must contain numbered TABLES 1-24")
        if set(surface_headers) != set(range(1, 24, 2)):
            raise PatentParseError("mobile imaging-lens surface tables must be odd TABLES 1-23")
        if _MOBILE_IMAGING_LENS_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("mobile imaging-lens published half-field definition not found")
    except Exception as exc:  # noqa: BLE001 - retain the disclosed example set
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Mobile imaging-lens example {example_number}",
                error=exc,
            )
            for example_number in range(1, 13)
        ]

    for example_number in range(1, 13):
        embodiment = f"Mobile imaging-lens example {example_number}"
        surface_table = example_number * 2 - 1
        coefficient_table = example_number * 2
        try:
            surface_text = blocks[surface_table]
            coefficient_text = blocks.get(coefficient_table)
            if coefficient_text is None:
                raise PatentParseError(f"mobile imaging-lens TABLE {coefficient_table} not found")
            header = surface_headers[surface_table]
            surfaces = _parse_mobile_imaging_lens_surface_table(
                surface_text,
                header=header,
                example_number=example_number,
            )
            coefficients = _parse_mobile_imaging_lens_asphere_table(
                coefficient_text,
                example_number=example_number,
                split_layout=example_number >= 7,
            )
            surface_indices = {surface.index for surface in surfaces}
            if not set(coefficients).issubset(surface_indices):
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} coefficients "
                    "reference an unknown surface"
                )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
            focal_length = _parse_number(header.group("f"))
            f_number = _parse_number(header.group("fno"))
            half_field = _parse_number(header.group("hfov"))
            if focal_length <= 0 or f_number <= 0 or not 0 < half_field < 90:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} has invalid f/Fno/ω"
                )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retained per published example
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=example_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _parse_mobile_imaging_lens_surface_table(
    table_text: str,
    *,
    header: re.Match[str],
    example_number: int,
) -> list[PatentSurface]:
    body = table_text[header.end() :]
    image_matches = list(re.finditer(r"(?<!\S)\(IM\)\s+Infinity\b", body, re.IGNORECASE))
    if len(image_matches) != 1:
        raise PatentParseError(
            f"mobile imaging-lens example {example_number} must publish one image row"
        )
    surface_body = body[: image_matches[0].start()].strip()
    object_match = re.match(r"Infinity\s+Infinity\s+", surface_body, re.IGNORECASE)
    if object_match is None:
        raise PatentParseError(f"mobile imaging-lens example {example_number} object row not found")
    surface_body = surface_body[object_match.end() :]
    starts = list(_MOBILE_IMAGING_LENS_SURFACE_ROW_PATTERN.finditer(surface_body))
    indices = [int(match.group("index")) for match in starts]
    if indices != list(range(1, 20)):
        raise PatentParseError(
            f"mobile imaging-lens example {example_number} surface sequence must be 1-19"
        )

    surfaces: list[PatentSurface] = []
    current_lens = 0
    stop_count = 0
    for row_position, match in enumerate(starts):
        surface_index = int(match.group("index"))
        end = (
            starts[row_position + 1].start()
            if row_position + 1 < len(starts)
            else len(surface_body)
        )
        tokens = surface_body[match.end() : end].split()
        label_token = (match.group("label") or "").upper()
        has_star = match.group("star") is not None
        nd = vd = None
        material = None

        if label_token == "ST":
            stop_count += 1
            if has_star or len(tokens) != 2:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} stop row is malformed"
                )
            label = "Stop"
        elif label_token.startswith("L"):
            expected_lens = current_lens + 1
            if label_token != f"L{expected_lens}" or not has_star or len(tokens) != 7:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} lens {expected_lens} "
                    "first-surface row is malformed"
                )
            if tokens[4].lower() != f"f{expected_lens}" or tokens[5] != "=":
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} lens {expected_lens} "
                    "published focal-length suffix is malformed"
                )
            _parse_number(tokens[6])
            current_lens = expected_lens
            label = f"Lens {current_lens}"
            nd = _parse_number(tokens[2])
            vd = _parse_number(tokens[3])
            material = "Glass"
        elif surface_index == 18:
            if label_token or has_star or len(tokens) != 4:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} filter row 18 is malformed"
                )
            label = "Filter"
            nd = _parse_number(tokens[2])
            vd = _parse_number(tokens[3])
            material = "Glass"
        elif surface_index == 19:
            if label_token or has_star or len(tokens) != 2:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} filter row 19 is malformed"
                )
            label = "Filter"
        else:
            if label_token or not has_star or len(tokens) != 2 or current_lens == 0:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} surface "
                    f"{surface_index} row is malformed"
                )
            label = f"Lens {current_lens}"

        radius = _distance_value(
            tokens[0],
            field_name=f"mobile imaging-lens surface {surface_index} radius",
        )
        thickness = _distance_value(
            tokens[1],
            field_name=f"mobile imaging-lens surface {surface_index} thickness",
        )
        surfaces.append(
            PatentSurface(
                index=surface_index,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=material,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )

    if current_lens != 8 or stop_count != 1:
        raise PatentParseError(
            f"mobile imaging-lens example {example_number} must contain eight lenses and one stop"
        )
    surfaces.append(
        PatentSurface(
            index=20,
            label="Image",
            radius_mm=math.inf,
            thickness_mm=0.0,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces


def _parse_mobile_imaging_lens_asphere_table(
    table_text: str,
    *,
    example_number: int,
    split_layout: bool,
) -> dict[int, dict[str, float]]:
    if split_layout:
        header = _MOBILE_IMAGING_LENS_SPLIT_ASPHERE_HEADER.search(table_text)
        surface_indices = tuple(range(2, 18))
        first_labels = ("K", "A4", "A6", "A8", "A10")
    else:
        header = _MOBILE_IMAGING_LENS_SINGLE_ASPHERE_HEADER.search(table_text)
        surface_indices = (1, 2, *range(4, 18))
        first_labels = ("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16")
    if header is None:
        raise PatentParseError(
            f"mobile imaging-lens example {example_number} coefficient header not found"
        )

    tokens = table_text[header.end() :].split()
    coefficients, position = _parse_mobile_imaging_lens_coefficient_rows(
        tokens,
        position=0,
        surface_indices=surface_indices,
        labels=first_labels,
        example_number=example_number,
    )
    if split_layout:
        second_header = tuple(tokens[position : position + 6])
        if tuple(label.upper() for label in second_header) != tuple(
            label.upper() for label in _MOBILE_IMAGING_LENS_SECOND_ASPHERE_HEADER
        ):
            raise PatentParseError(
                f"mobile imaging-lens example {example_number} second coefficient header is missing"
            )
        second_coefficients, _ = _parse_mobile_imaging_lens_coefficient_rows(
            tokens,
            position=position + 6,
            surface_indices=surface_indices,
            labels=("A12", "A14", "A16", "A18", "A20"),
            example_number=example_number,
        )
        for surface_index, values in second_coefficients.items():
            coefficients[surface_index].update(values)
    return coefficients


def _parse_mobile_imaging_lens_coefficient_rows(
    tokens: list[str],
    *,
    position: int,
    surface_indices: tuple[int, ...],
    labels: tuple[str, ...],
    example_number: int,
) -> tuple[dict[int, dict[str, float]], int]:
    coefficients: dict[int, dict[str, float]] = {}
    for surface_index in surface_indices:
        if position >= len(tokens) or tokens[position] != str(surface_index):
            actual = tokens[position] if position < len(tokens) else "<end>"
            raise PatentParseError(
                f"mobile imaging-lens example {example_number} coefficient row sequence "
                f"expected {surface_index}, found {actual}"
            )
        position += 1
        row: dict[str, float] = {}
        for label in labels:
            if position >= len(tokens):
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} surface {surface_index} "
                    "coefficient row is incomplete"
                )
            try:
                value = _parse_number(tokens[position])
            except PatentParseError as exc:
                raise PatentParseError(
                    f"mobile imaging-lens example {example_number} surface {surface_index} "
                    f"coefficient {label} is malformed: {tokens[position]}"
                ) from exc
            position += 1
            if label == "K":
                codev_label = "K"
            else:
                order = int(label[1:])
                codev_label = ASPHERE_ORDER_TO_CODEV[order]
            row[codev_label] = value
        coefficients[surface_index] = row
    return coefficients, position


def _parse_kantatsu_six_lens_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact four-example Kantatsu six-lens grouped tables."""

    blocks = _patent_table_blocks(text)
    surface_blocks = [
        (block, header)
        for block in blocks
        if (header := _KANTATSU_SIX_LENS_HEADER_PATTERN.search(block.text)) is not None
    ]
    if not surface_blocks:
        return []

    bindings = list(_KANTATSU_SIX_LENS_BINDING_PATTERN.finditer(text))
    disclosed_examples = max(len(surface_blocks), len(bindings))
    try:
        if disclosed_examples != 4:
            raise PatentParseError(
                f"Kantatsu six-lens family must publish four examples, found {disclosed_examples}"
            )
        if [block.number for block in blocks] != list(range(1, 6)):
            raise PatentParseError(
                "Kantatsu six-lens family tables are not consecutive through the "
                "conditional-expression summary"
            )
        if [block.number for block, _header in surface_blocks] != list(range(1, 5)):
            raise PatentParseError("Kantatsu six-lens prescription tables are not consecutive")
        if _KANTATSU_SIX_LENS_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("Kantatsu six-lens published half-field definition not found")
        if _KANTATSU_SIX_LENS_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu six-lens published A4-A16 asphere definition not found"
            )
        if len(bindings) != disclosed_examples:
            raise PatentParseError(
                "Kantatsu six-lens example/table bindings are incomplete: "
                f"expected {disclosed_examples}, found {len(bindings)}"
            )
        for example_number, binding in enumerate(bindings, start=1):
            bound_values = (
                int(binding.group("example")),
                int(binding.group("table")),
                int(binding.group("header_table")),
                int(binding.group("header_example")),
            )
            if bound_values != (example_number,) * 4:
                raise PatentParseError(
                    "Kantatsu six-lens narrative/header binding is not consecutive at "
                    f"example {example_number}"
                )
    except Exception as exc:  # noqa: BLE001 - retain every disclosed example
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu six-lens example {example_number}",
                error=exc,
            )
            for example_number in range(1, disclosed_examples + 1)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, (block, header) in enumerate(surface_blocks, start=1):
        embodiment = f"Kantatsu six-lens example {example_number}"
        try:
            if (
                int(header.group("table")) != example_number
                or int(header.group("example")) != example_number
            ):
                raise PatentParseError(
                    f"Kantatsu six-lens example {example_number} header is cross-bound"
                )
            surfaces, source_to_output, lens_surface_end = _parse_kantatsu_inline_surface_table(
                block.text,
                example_number=example_number,
                family_label="Kantatsu six-lens",
            )
            if lens_surface_end != 13:
                raise PatentParseError(
                    f"Kantatsu six-lens example {example_number} lens surface coverage "
                    f"must end at 13, found {lens_surface_end}"
                )
            coefficients = _parse_kantatsu_inline_asphere_table(
                block.text,
                example_number=example_number,
                expected_source_surfaces=tuple(range(2, 14)),
                labels=("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16"),
                family_label="Kantatsu six-lens",
                group_pattern=_KANTATSU_SIX_LENS_ASPHERE_GROUP_PATTERN,
                paired_headings=False,
            )
            for source_index, row in coefficients.items():
                output_index = source_to_output[source_index]
                surface = surfaces[output_index - 1]
                surface.surface_type = "ASP"
                surface.asphere_coefficients.update(row)

            focal_length = _parse_number(header.group("f"))
            image_height = _parse_number(header.group("ih"))
            f_number = _parse_number(header.group("fno"))
            total_track = _parse_number(header.group("ttl"))
            half_field = _parse_number(header.group("hfov"))
            if (
                focal_length <= 0
                or image_height <= 0
                or f_number <= 0
                or total_track <= 0
                or not 0 < half_field < 90
            ):
                raise PatentParseError(
                    f"Kantatsu six-lens example {example_number} has invalid "
                    "f/h/Fno/TTL/half-field metadata"
                )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retained per published example
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=example_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _parse_kantatsu_ih_first_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse four-example Kantatsu tables whose metadata lists ``ih`` first."""

    blocks = _patent_table_blocks(text)
    matched_headers = [_KANTATSU_IH_FIRST_HEADER_PATTERN.search(block.text) for block in blocks]
    if not any(matched_headers):
        return []

    bindings = list(_KANTATSU_IH_FIRST_BINDING_PATTERN.finditer(text))
    try:
        if [block.number for block in blocks] != list(range(1, 6)):
            raise PatentParseError(
                "Kantatsu ih-first family tables are not consecutive through the "
                "conditional-expression summary"
            )
        if len(bindings) != 4:
            raise PatentParseError(
                f"Kantatsu ih-first family must bind four examples, found {len(bindings)}"
            )
        if _KANTATSU_IH_FIRST_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("Kantatsu ih-first published half-field definition not found")
        if _KANTATSU_IH_FIRST_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu ih-first published A4-A16 asphere definition not found"
            )
        for example_number, binding in enumerate(bindings, start=1):
            bound_values = (
                int(binding.group("example")),
                int(binding.group("table")),
                int(binding.group("header_table")),
                int(binding.group("header_example")),
            )
            if bound_values != (example_number,) * 4:
                raise PatentParseError(
                    "Kantatsu ih-first narrative/header binding is not consecutive at "
                    f"example {example_number}"
                )
    except Exception as exc:  # noqa: BLE001 - retain all four disclosed examples
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu ih-first example {example_number}",
                error=exc,
            )
            for example_number in range(1, 5)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, block in enumerate(blocks[:4], start=1):
        embodiment = f"Kantatsu ih-first example {example_number}"
        try:
            header = _KANTATSU_IH_FIRST_HEADER_PATTERN.search(block.text)
            if header is None:
                raise PatentParseError(
                    f"Kantatsu ih-first example {example_number} header is source-damaged"
                )
            if (
                int(header.group("table")) != example_number
                or int(header.group("example")) != example_number
            ):
                raise PatentParseError(
                    f"Kantatsu ih-first example {example_number} header is cross-bound"
                )

            # PPUBS inserts spaces inside textual parentheses in this family. Only
            # labels are normalized; numeric tokens remain separate.
            table_text = re.sub(
                r"\(\s*(Object|Stop)\s*\)",
                r"(\1)",
                block.text,
                flags=re.IGNORECASE,
            )
            table_text = re.sub(
                r"\(\s*(?:v|\u03bd)\s*d(\d+)\s*\)",
                r"(vd\1)",
                table_text,
                flags=re.IGNORECASE,
            )
            surfaces, source_to_output, lens_surface_end = _parse_kantatsu_inline_surface_table(
                table_text,
                example_number=example_number,
                family_label="Kantatsu ih-first",
            )
            if lens_surface_end != 13:
                raise PatentParseError(
                    f"Kantatsu ih-first example {example_number} lens surface coverage "
                    f"must end at 13, found {lens_surface_end}"
                )
            coefficients = _parse_kantatsu_inline_asphere_table(
                table_text,
                example_number=example_number,
                expected_source_surfaces=tuple(range(2, 14)),
                labels=("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16"),
                family_label="Kantatsu ih-first",
            )
            for source_index, row in coefficients.items():
                output_index = source_to_output[source_index]
                surface = surfaces[output_index - 1]
                surface.surface_type = "ASP"
                surface.asphere_coefficients.update(row)

            focal_length = _parse_number(header.group("f"))
            image_height = _parse_number(header.group("ih"))
            f_number = _parse_number(header.group("fno"))
            total_track = _parse_number(header.group("ttl"))
            half_field = _parse_number(header.group("hfov"))
            if (
                focal_length <= 0
                or image_height <= 0
                or f_number <= 0
                or total_track <= 0
                or not 0 < half_field < 90
            ):
                raise PatentParseError(
                    f"Kantatsu ih-first example {example_number} has invalid "
                    "f/ih/Fno/TTL/half-field metadata"
                )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retained per published example
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=example_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _parse_kantatsu_inline_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact Kantatsu tables with surface and A4-A20 data in one block."""

    blocks = _patent_table_blocks(text)
    surface_blocks = [
        (block, header)
        for block in blocks
        if (header := _KANTATSU_INLINE_HEADER_PATTERN.search(block.text)) is not None
    ]
    if not surface_blocks:
        return []

    disclosed_examples = len(surface_blocks)
    try:
        if disclosed_examples not in {11, 12}:
            raise PatentParseError(
                f"Kantatsu inline family must publish 11 or 12 examples, found {disclosed_examples}"
            )
        expected_tables = list(range(1, disclosed_examples + 2))
        if [block.number for block in blocks] != expected_tables:
            raise PatentParseError(
                "Kantatsu inline family tables are not consecutive through the "
                "conditional-expression summary"
            )
        if [block.number for block, _header in surface_blocks] != list(
            range(1, disclosed_examples + 1)
        ):
            raise PatentParseError("Kantatsu inline prescription tables are not consecutive")
        if _KANTATSU_INLINE_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("Kantatsu inline published half-field definition not found")
        if _KANTATSU_INLINE_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError("Kantatsu inline published A4-A20 asphere definition not found")
        bindings = list(_KANTATSU_INLINE_BINDING_PATTERN.finditer(text))
        if len(bindings) != disclosed_examples:
            raise PatentParseError(
                "Kantatsu inline example/table bindings are incomplete: "
                f"expected {disclosed_examples}, found {len(bindings)}"
            )
        for example_number, binding in enumerate(bindings, start=1):
            bound_values = (
                int(binding.group("example")),
                int(binding.group("table")),
                int(binding.group("header_table")),
                _kantatsu_inline_example_number(binding.group("header_example")),
            )
            if bound_values != (example_number,) * 4:
                raise PatentParseError(
                    "Kantatsu inline narrative/header binding is not consecutive at "
                    f"example {example_number}"
                )
    except Exception as exc:  # noqa: BLE001 - retain every disclosed example
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu inline example {example_number}",
                error=exc,
            )
            for example_number in range(1, disclosed_examples + 1)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, (block, header) in enumerate(surface_blocks, start=1):
        embodiment = f"Kantatsu inline example {example_number}"
        try:
            if (
                int(header.group("table")) != example_number
                or _kantatsu_inline_example_number(header.group("example")) != example_number
            ):
                raise PatentParseError(
                    f"Kantatsu inline example {example_number} header is cross-bound"
                )
            surfaces, source_to_output, lens_surface_end = _parse_kantatsu_inline_surface_table(
                block.text,
                example_number=example_number,
            )
            coefficients = _parse_kantatsu_inline_asphere_table(
                block.text,
                example_number=example_number,
                expected_source_surfaces=tuple(range(2, lens_surface_end + 1)),
            )
            for source_index, row in coefficients.items():
                output_index = source_to_output[source_index]
                surface = surfaces[output_index - 1]
                surface.surface_type = "ASP"
                surface.asphere_coefficients.update(row)

            focal_length = _parse_number(header.group("f"))
            image_height = _parse_number(header.group("ih"))
            f_number = _parse_number(header.group("fno"))
            total_track = _parse_number(header.group("ttl"))
            half_field = _parse_number(header.group("hfov"))
            if (
                focal_length <= 0
                or image_height <= 0
                or f_number <= 0
                or total_track <= 0
                or not 0 < half_field < 90
            ):
                raise PatentParseError(
                    f"Kantatsu inline example {example_number} has invalid "
                    "f/ih/Fno/TTL/half-field metadata"
                )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retained per published example
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=example_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _kantatsu_inline_example_number(token: str) -> int:
    """Bind the PPUBS ``l`` glyph only to independently numbered example 1."""

    return 1 if token.lower() == "l" else int(token)


def _parse_kantatsu_inline_surface_table(
    table_text: str,
    *,
    example_number: int,
    family_label: str = "Kantatsu inline",
) -> tuple[list[PatentSurface], dict[int, int], int]:
    object_row = re.search(
        r"\(Object\)\s+Infinity\s+Infinity\b",
        table_text,
        re.IGNORECASE,
    )
    image_row = re.search(r"\bImage\s+Plane\s+Infinity\b", table_text, re.IGNORECASE)
    constituent = re.search(r"\bConstituent\s+Lens\s+Data\b", table_text, re.IGNORECASE)
    if (
        object_row is None
        or image_row is None
        or constituent is None
        or not object_row.end() < image_row.start() < constituent.start()
    ):
        raise PatentParseError(
            f"{family_label} example {example_number} object/image rows are incomplete"
        )

    body = table_text[object_row.end() : image_row.start()]
    starts = list(_KANTATSU_INLINE_SURFACE_ROW_PATTERN.finditer(body))
    source_indices = [int(match.group("index")) for match in starts]
    if source_indices == list(range(1, 14)):
        lens_surface_end, filter_front, filter_rear = 11, 12, 13
    elif source_indices == list(range(1, 16)):
        lens_surface_end, filter_front, filter_rear = 13, 14, 15
    elif source_indices == [*range(1, 16), 18, 19]:
        # The official table omits optional source surfaces 16/17 and then prints
        # the remaining filter rows as 18/19. Output indices follow physical row
        # order; no missing optical values or dummy surfaces are synthesized.
        lens_surface_end, filter_front, filter_rear = 15, 18, 19
    else:
        raise PatentParseError(
            f"{family_label} example {example_number} source surface sequence is "
            f"unsupported or damaged: {source_indices}"
        )

    surfaces: list[PatentSurface] = []
    source_to_output: dict[int, int] = {}
    for row_position, match in enumerate(starts):
        source_index = int(match.group("index"))
        row_end = starts[row_position + 1].start() if row_position + 1 < len(starts) else len(body)
        tokens = body[match.end() : row_end].split()
        has_star = match.group("star") is not None
        has_stop = match.group("stop") is not None
        output_index = row_position + 1
        nd = vd = None
        material = None

        if source_index == 1:
            if has_star or not has_stop or len(tokens) != 2:
                raise PatentParseError(
                    f"{family_label} example {example_number} stop row is malformed"
                )
            label = "Stop"
        elif source_index <= lens_surface_end:
            if not has_star or has_stop:
                raise PatentParseError(
                    f"{family_label} example {example_number} lens surface "
                    f"{source_index} marker is malformed"
                )
            lens_number = source_index // 2
            label = f"Lens {lens_number}"
            if source_index % 2 == 0:
                suffix = _KANTATSU_INLINE_MATERIAL_SUFFIX.fullmatch(tokens[-1]) if tokens else None
                if len(tokens) != 5 or suffix is None or int(suffix.group("lens")) != lens_number:
                    raise PatentParseError(
                        f"{family_label} example {example_number} lens {lens_number} "
                        "material row is malformed"
                    )
                nd = _parse_number(tokens[2])
                vd = _parse_number(tokens[3])
                material = "Published nd/vd"
            elif len(tokens) != 2:
                raise PatentParseError(
                    f"{family_label} example {example_number} lens {lens_number} "
                    "second-surface row is malformed"
                )
        elif source_index == filter_front:
            if has_star or has_stop or len(tokens) != 4:
                raise PatentParseError(
                    f"{family_label} example {example_number} filter-front row is malformed"
                )
            label = "Filter"
            nd = _parse_number(tokens[2])
            vd = _parse_number(tokens[3])
            material = "Published nd/vd"
        elif source_index == filter_rear:
            if has_star or has_stop or len(tokens) != 2:
                raise PatentParseError(
                    f"{family_label} example {example_number} filter-rear row is malformed"
                )
            label = "Filter"
        else:  # pragma: no cover - source sequence guard above makes this unreachable
            raise PatentParseError(
                f"{family_label} example {example_number} unexpected source surface {source_index}"
            )

        _validate_material_indices(surface_index=output_index, nd=nd, vd=vd)
        surfaces.append(
            PatentSurface(
                index=output_index,
                label=label,
                radius_mm=_distance_value(
                    tokens[0],
                    field_name=f"{family_label} source surface {source_index} radius",
                ),
                thickness_mm=_distance_value(
                    tokens[1],
                    field_name=f"{family_label} source surface {source_index} thickness",
                ),
                material=material,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )
        source_to_output[source_index] = output_index

    surfaces.append(
        PatentSurface(
            index=len(surfaces) + 1,
            label="Image",
            radius_mm=math.inf,
            thickness_mm=0.0,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces, source_to_output, lens_surface_end


def _parse_kantatsu_inline_asphere_table(
    table_text: str,
    *,
    example_number: int,
    expected_source_surfaces: tuple[int, ...],
    labels: tuple[str, ...] = (
        "K",
        "A4",
        "A6",
        "A8",
        "A10",
        "A12",
        "A14",
        "A16",
        "A18",
        "A20",
    ),
    family_label: str = "Kantatsu inline",
    group_pattern: re.Pattern[str] = _KANTATSU_INLINE_ASPHERE_GROUP_PATTERN,
    paired_headings: bool = True,
) -> dict[int, dict[str, float]]:
    section_start = re.search(r"\bAspheric\s+Surface\s+Data\b", table_text, re.IGNORECASE)
    if section_start is None:
        raise PatentParseError(f"{family_label} example {example_number} asphere section not found")
    section = table_text[section_start.end() :]
    section = re.split(r"\s\[\d{4}\]\s", section, maxsplit=1)[0]
    groups = list(group_pattern.finditer(section))
    if not groups:
        raise PatentParseError(f"{family_label} example {example_number} asphere groups not found")

    coefficients: dict[int, dict[str, float]] = {}
    published_source_surfaces: list[int] = []
    for group_position, group in enumerate(groups):
        heading_suffix = r"\s+Surface" if paired_headings else r"\b"
        source_surfaces = [
            _KANTATSU_INLINE_ORDINALS[match.group("ordinal").lower()]
            for match in re.finditer(
                rf"(?P<ordinal>{_KANTATSU_INLINE_ORDINAL_PATTERN}){heading_suffix}",
                group.group("headings"),
                re.IGNORECASE,
            )
        ]
        published_source_surfaces.extend(source_surfaces)
        group_end = (
            groups[group_position + 1].start() if group_position + 1 < len(groups) else len(section)
        )
        tokens = section[group.end() : group_end].split()
        position = 0
        for label_position, label in enumerate(labels):
            if label_position:
                actual = tokens[position] if position < len(tokens) else "<end>"
                if actual.upper() != label:
                    raise PatentParseError(
                        f"{family_label} example {example_number} coefficient label "
                        f"expected {label}, found {actual}"
                    )
                position += 1
            for source_index in source_surfaces:
                if position >= len(tokens):
                    raise PatentParseError(
                        f"{family_label} example {example_number} coefficient {label} "
                        f"for source surface {source_index} is missing"
                    )
                raw_value = tokens[position]
                try:
                    value = _parse_number(raw_value)
                except PatentParseError as exc:
                    raise PatentParseError(
                        f"{family_label} example {example_number} coefficient {label} "
                        f"for source surface {source_index} is malformed: {raw_value}"
                    ) from exc
                position += 1
                codev_label = "K" if label == "K" else ASPHERE_ORDER_TO_CODEV[int(label[1:])]
                coefficients.setdefault(source_index, {})[codev_label] = value
        if position != len(tokens):
            raise PatentParseError(
                f"{family_label} example {example_number} asphere group has trailing tokens: "
                f"{tokens[position : position + 4]}"
            )

    if tuple(published_source_surfaces) != expected_source_surfaces:
        raise PatentParseError(
            f"{family_label} example {example_number} coefficient surface coverage is "
            f"damaged: {published_source_surfaces}"
        )
    return coefficients


def _parse_kantatsu_nine_lens_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact 10- or 13-pair Kantatsu nine-lens numerical-data tables.

    PPUBS unit damage and split numeric tokens remain per-example failures.
    Only tables explicitly carrying ``[mm]`` are converted.
    """

    bindings = list(_KANTATSU_NINE_LENS_BINDING_PATTERN.finditer(text))
    unit_pattern = _KANTATSU_NINE_LENS_UNIT_PATTERN
    if not bindings:
        bindings = list(_KANTATSU_NINE_LENS_PRETABLE_BINDING_PATTERN.finditer(text))
        unit_pattern = _KANTATSU_NINE_LENS_PRETABLE_UNIT_PATTERN
    if not bindings:
        return []
    blocks = _numbered_patent_table_blocks(text)
    expected_examples = len(blocks) // 2 if len(blocks) % 2 == 0 else 0
    disclosed_examples = expected_examples or max(
        int(binding.group("example")) for binding in bindings
    )
    try:
        if expected_examples not in {10, 13}:
            raise PatentParseError(
                "Kantatsu nine-lens family must contain 10 or 13 surface/asphere "
                f"table pairs, found {len(blocks)} tables"
            )
        if set(blocks) != set(range(1, expected_examples * 2 + 1)):
            raise PatentParseError(
                "Kantatsu nine-lens family tables are not consecutively numbered"
            )
        if len(bindings) != expected_examples:
            raise PatentParseError(
                "Kantatsu nine-lens example/table bindings are incomplete: "
                f"expected {expected_examples}, found {len(bindings)}"
            )
        if _KANTATSU_NINE_LENS_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("Kantatsu nine-lens published half-angle definition not found")
        for example_number, binding in enumerate(bindings, start=1):
            if (
                int(binding.group("example")) != example_number
                or int(binding.group("table")) != example_number * 2 - 1
            ):
                raise PatentParseError(
                    "Kantatsu nine-lens example/table binding is not consecutive at "
                    f"example {example_number}"
                )
    except Exception as exc:  # noqa: BLE001 - retain every disclosed example
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu nine-lens example {example_number}",
                error=exc,
            )
            for example_number in range(1, disclosed_examples + 1)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number in range(1, expected_examples + 1):
        embodiment = f"Kantatsu nine-lens example {example_number}"
        try:
            surface_text = blocks[example_number * 2 - 1]
            coefficient_text = blocks[example_number * 2]
            unit_match = unit_pattern.search(surface_text)
            if unit_match is None:
                raise PatentParseError(
                    f"Kantatsu example {example_number} surface-table unit not found"
                )
            if unit_match.group("unit").lower() != "mm":
                raise PatentParseError(
                    f"Kantatsu example {example_number} surface-table unit is "
                    f"[{unit_match.group('unit')}], not [mm]"
                )
            meta_matches = list(_KANTATSU_NINE_LENS_META_PATTERN.finditer(surface_text))
            if len(meta_matches) != 1:
                raise PatentParseError(
                    f"Kantatsu example {example_number} must publish one f/Fno/ω tuple"
                )
            meta = meta_matches[0]
            surfaces = _parse_kantatsu_nine_lens_surface_table(
                surface_text,
                example_number=example_number,
            )
            coefficients = _parse_kantatsu_nine_lens_asphere_table(
                coefficient_text,
                example_number=example_number,
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
            focal_length = _parse_number(meta.group("f"))
            f_number = _parse_number(meta.group("fno"))
            half_field = _parse_number(meta.group("hfov"))
            if focal_length <= 0 or f_number <= 0 or not 0 < half_field < 90:
                raise PatentParseError(f"Kantatsu example {example_number} has invalid f/Fno/ω")
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retained per published example
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=example_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
            continue
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=embodiment,
                prescription=prescription,
            )
        )
    return attempts


def _parse_kantatsu_nine_lens_surface_table(
    table_text: str,
    *,
    example_number: int,
) -> list[PatentSurface]:
    first_surface = _KANTATSU_NINE_LENS_FIRST_SURFACE_PATTERN.search(table_text)
    image = re.search(r"(?<!\S)\((?:I|1)M\)\s+Infinity\b", table_text, re.IGNORECASE)
    if first_surface is None or image is None or image.start() <= first_surface.start():
        raise PatentParseError(
            f"Kantatsu example {example_number} surface/image rows are incomplete"
        )
    body = table_text[first_surface.start() : image.start()]
    starts = list(_KANTATSU_NINE_LENS_SURFACE_ROW_PATTERN.finditer(body))
    indices = [int(match.group("index")) for match in starts]
    if indices != list(range(1, 21)):
        raise PatentParseError(f"Kantatsu example {example_number} surface sequence must be 1-20")

    surfaces: list[PatentSurface] = []
    for row_position, match in enumerate(starts):
        surface_index = int(match.group("index"))
        end = starts[row_position + 1].start() if row_position + 1 < len(starts) else len(body)
        tokens = body[match.end() : end].split()
        label_token = (match.group("label") or "").upper()
        has_star = match.group("star") is not None
        has_stop = match.group("stop") is not None
        nd = vd = None
        material = None

        if surface_index <= 18 and surface_index % 2 == 1:
            lens_number = (surface_index + 1) // 2
            if (
                label_token != f"L{lens_number}"
                or not has_star
                or has_stop != (surface_index == 1)
                or len(tokens) != 7
            ):
                raise PatentParseError(
                    f"Kantatsu example {example_number} lens {lens_number} "
                    "first-surface row is malformed"
                )
            if tokens[4].lower() != f"f{lens_number}" or tokens[5] != "=":
                raise PatentParseError(
                    f"Kantatsu example {example_number} lens {lens_number} "
                    "published focal-length suffix is malformed"
                )
            _parse_number(tokens[6])
            label = "Stop" if surface_index == 1 else f"Lens {lens_number}"
            nd = _parse_number(tokens[2])
            vd = _parse_number(tokens[3])
            material = "Published nd/vd"
        elif surface_index <= 18:
            lens_number = surface_index // 2
            if label_token or not has_star or has_stop or len(tokens) != 2:
                raise PatentParseError(
                    f"Kantatsu example {example_number} surface {surface_index} row is malformed"
                )
            label = f"Lens {lens_number}"
        elif surface_index == 19:
            if label_token or has_star or has_stop or len(tokens) != 4:
                raise PatentParseError(
                    f"Kantatsu example {example_number} filter row 19 is malformed"
                )
            label = "Filter"
            nd = _parse_number(tokens[2])
            vd = _parse_number(tokens[3])
            material = "Published nd/vd"
        else:
            if label_token or has_star or has_stop or len(tokens) != 2:
                raise PatentParseError(
                    f"Kantatsu example {example_number} filter row 20 is malformed"
                )
            label = "Filter"

        surfaces.append(
            PatentSurface(
                index=surface_index,
                label=label,
                radius_mm=_distance_value(
                    tokens[0],
                    field_name=f"Kantatsu surface {surface_index} radius",
                ),
                thickness_mm=_distance_value(
                    tokens[1],
                    field_name=f"Kantatsu surface {surface_index} thickness",
                ),
                material=material,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )
    surfaces.append(
        PatentSurface(
            index=21,
            label="Image",
            radius_mm=math.inf,
            thickness_mm=0.0,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces


def _parse_kantatsu_nine_lens_asphere_table(
    table_text: str,
    *,
    example_number: int,
) -> dict[int, dict[str, float]]:
    header = _KANTATSU_NINE_LENS_ASPHERE_HEADER.search(table_text)
    if header is None:
        raise PatentParseError(f"Kantatsu example {example_number} coefficient header not found")
    tokens = table_text[header.end() :].split()
    labels = ("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16")
    coefficients: dict[int, dict[str, float]] = {}
    position = 0
    for surface_index in range(1, 19):
        if position >= len(tokens) or tokens[position] != str(surface_index):
            actual = tokens[position] if position < len(tokens) else "<end>"
            raise PatentParseError(
                f"Kantatsu example {example_number} coefficient row sequence "
                f"expected {surface_index}, found {actual}"
            )
        position += 1
        row: dict[str, float] = {}
        for label in labels:
            if position >= len(tokens):
                raise PatentParseError(
                    f"Kantatsu example {example_number} surface {surface_index} "
                    "coefficient row is incomplete"
                )
            try:
                value = _parse_number(tokens[position])
            except PatentParseError as exc:
                raise PatentParseError(
                    f"Kantatsu example {example_number} surface {surface_index} "
                    f"coefficient {label} is malformed: {tokens[position]}"
                ) from exc
            position += 1
            codev_label = "K" if label == "K" else ASPHERE_ORDER_TO_CODEV[int(label[1:])]
            row[codev_label] = value
        coefficients[surface_index] = row
    return coefficients


def _parse_folded_macro_tele_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact folded smartphone macro-tele base prescriptions fail-closed.

    The four published infinity-conjugate systems with explicit EFL metadata
    are convertible. Every finite-object state remains an explicit failure
    because the replay tracer models an infinity conjugate. System 290 remains
    rejected because its whole-system focal token is only labelled ``F`` and
    the official text does not define that token as EFL.
    """

    if _FOLDED_MACRO_TELE_SIGNATURE.search(text) is None:
        return []
    blocks = _numbered_patent_table_blocks(text)
    fallback_labels = [f"Folded macro-tele disclosed state {index}" for index in range(1, 38)]
    try:
        if set(blocks) != set(range(1, 23)):
            raise PatentParseError("folded macro-tele family must contain numbered TABLES 1-22")
        if _FOLDED_MACRO_TELE_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("folded macro-tele Half FOV/HFOV definition not found")
        state_groups: dict[str, list[tuple[str, str, float]]] = {}
        for system in ("200", "220", "230", "290"):
            variation_table = _FOLDED_MACRO_TELE_SYSTEM_TABLES[system][2]
            state_groups[system] = _parse_folded_macro_object_states(
                blocks[variation_table], system=system
            )
        state_groups["240"] = _parse_folded_macro_config_states(blocks[15], blocks[16])
        if [len(state_groups[system]) for system in ("200", "220", "230", "240", "290")] != [
            8,
            8,
            9,
            3,
            9,
        ]:
            raise PatentParseError("folded macro-tele disclosed-state counts changed")
    except Exception as exc:  # noqa: BLE001 - retain all 37 published states
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=label,
                error=exc,
            )
            for index, label in enumerate(fallback_labels, start=1)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    attempt_number = 0
    for system in ("200", "220", "230", "240", "290"):
        surface_table, coefficient_table, _variation_table, lens_count = (
            _FOLDED_MACRO_TELE_SYSTEM_TABLES[system]
        )
        base_prescription: PatentPrescription | None = None
        base_error: Exception | None = None
        try:
            base_prescription = _parse_folded_macro_tele_base_prescription(
                blocks[surface_table],
                blocks[coefficient_table],
                system=system,
                lens_count=lens_count,
                patent_id=patent_id,
            )
        except Exception as exc:  # noqa: BLE001 - apply to every state in this system
            base_error = exc

        for state_index, (state_name, object_distance, _hfov) in enumerate(state_groups[system]):
            attempt_number += 1
            embodiment = f"Folded macro-tele system {system} {state_name}"
            error = base_error
            prescription = None
            if error is None and state_index == 0 and object_distance == "Infinity":
                prescription = base_prescription
            elif error is None:
                error = PatentParseError(
                    "finite-object state is published but unsupported by the "
                    f"infinity-conjugate replay model: object distance {object_distance}"
                )
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=attempt_number,
                    embodiment=embodiment,
                    prescription=prescription,
                    error=error,
                )
            )
    return attempts


def _parse_folded_macro_tele_base_prescription(
    surface_text: str,
    coefficient_text: str,
    *,
    system: str,
    lens_count: int,
    patent_id: str,
) -> PatentPrescription:
    header = _FOLDED_MACRO_TELE_HEADER.search(surface_text)
    if header is None or header.group("system") != system:
        raise PatentParseError(f"folded macro-tele system {system} surface header not found")
    surfaces = _parse_folded_macro_tele_surfaces(
        surface_text[header.end() :], system=system, lens_count=lens_count
    )
    coefficients = _parse_folded_macro_tele_coefficients(
        coefficient_text, system=system, lens_count=lens_count
    )
    for surface in surfaces:
        if surface.index in coefficients:
            surface.asphere_coefficients.update(coefficients[surface.index])
            surface.surface_type = "ASP"
    if header.group("focal_label").upper() != "EFL":
        raise PatentParseError(
            f"folded macro-tele system {system} whole-system focal token F is not "
            "officially defined as EFL"
        )
    focal_length = _parse_number(header.group("f"))
    f_number = _parse_number(header.group("fno"))
    half_field = _parse_number(header.group("hfov"))
    if focal_length <= 0 or f_number <= 0 or not 0 < half_field < 90:
        raise PatentParseError(f"folded macro-tele system {system} has invalid EFL/F-number/HFOV")
    prescription = PatentPrescription(
        patent_id=patent_id,
        embodiment=f"Folded macro-tele system {system} infinity",
        focal_length_mm=focal_length,
        f_number=f_number,
        hfov_deg=half_field,
        surfaces=surfaces,
    )
    _validate_prescription_materials(prescription)
    return prescription


def _parse_folded_macro_tele_surfaces(
    body: str,
    *,
    system: str,
    lens_count: int,
) -> list[PatentSurface]:
    tokens = body.split()
    pos = 0

    def take(expected: str | None = None) -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise PatentParseError(f"folded macro-tele system {system} surface table is incomplete")
        token = tokens[pos]
        pos += 1
        if expected is not None and token.lower() != expected.lower():
            raise PatentParseError(
                f"folded macro-tele system {system} expected {expected}, found {token}"
            )
        return token

    surfaces: list[PatentSurface] = []
    take("1")
    take("A.S")
    if pos < len(tokens) and tokens[pos].lower() == "plano":
        pos += 1
    stop_radius = _distance_value(take(), field_name="folded macro-tele stop radius")
    stop_thickness = _distance_value(take(), field_name="folded macro-tele stop thickness")
    _parse_number(take())  # published aperture radius
    surfaces.append(
        PatentSurface(
            index=1,
            label="Stop",
            radius_mm=stop_radius,
            thickness_mm=stop_thickness,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )

    for lens_number in range(1, lens_count + 1):
        first_index = lens_number * 2
        take(str(first_index))
        take("Lens")
        take(str(lens_number))
        take("ASP")
        first_radius = _distance_value(take(), field_name=f"surface {first_index} radius")
        first_thickness = _distance_value(take(), field_name=f"surface {first_index} thickness")
        _parse_number(take())  # published aperture radius
        take("Plastic")
        nd = _parse_number(take())
        vd = _parse_number(take())
        _parse_number(take())  # published element focal length
        surfaces.append(
            PatentSurface(
                index=first_index,
                label=f"Lens {lens_number}",
                radius_mm=first_radius,
                thickness_mm=first_thickness,
                material="Plastic",
                nd=nd,
                vd=vd,
                surface_type="ASP",
            )
        )

        second_index = first_index + 1
        take(str(second_index))
        second_radius = _distance_value(take(), field_name=f"surface {second_index} radius")
        second_thickness = _distance_value(take(), field_name=f"surface {second_index} thickness")
        _parse_number(take())  # published aperture radius
        surfaces.append(
            PatentSurface(
                index=second_index,
                label=f"Lens {lens_number}",
                radius_mm=second_radius,
                thickness_mm=second_thickness,
                material=None,
                nd=None,
                vd=None,
                surface_type="ASP",
            )
        )

    filter_front = lens_count * 2 + 2
    take(str(filter_front))
    take("Filter")
    if pos < len(tokens) and tokens[pos].lower() == "plano":
        pos += 1
    filter_radius = _distance_value(take(), field_name="filter radius")
    filter_thickness = _distance_value(take(), field_name="filter thickness")
    take("--")
    take("Glass")
    filter_nd = _parse_number(take())
    filter_vd = _parse_number(take())
    surfaces.append(
        PatentSurface(
            index=filter_front,
            label="Filter",
            radius_mm=filter_radius,
            thickness_mm=filter_thickness,
            material="Glass",
            nd=filter_nd,
            vd=filter_vd,
            surface_type=None,
        )
    )

    filter_back = filter_front + 1
    take(str(filter_back))
    back_radius = _distance_value(take(), field_name="filter back radius")
    back_thickness = _distance_value(take(), field_name="filter back thickness")
    take("--")
    surfaces.append(
        PatentSurface(
            index=filter_back,
            label="Filter",
            radius_mm=back_radius,
            thickness_mm=back_thickness,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )

    image_index = filter_back + 1
    take(str(image_index))
    take("Image")
    if pos < len(tokens) and tokens[pos].lower() == "plano":
        pos += 1
    image_radius = _distance_value(take(), field_name="image radius")
    image_thickness = _distance_value(take(), field_name="image thickness")
    take("--")
    if pos < len(tokens) and re.fullmatch(r"\(\d+\)", tokens[pos]) is None:
        raise PatentParseError(
            f"folded macro-tele system {system} surface table has unexpected trailing token "
            f"{tokens[pos]}"
        )
    surfaces.append(
        PatentSurface(
            index=image_index,
            label="Image",
            radius_mm=image_radius,
            thickness_mm=image_thickness,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces


def _parse_folded_macro_tele_coefficients(
    table_text: str,
    *,
    system: str,
    lens_count: int,
) -> dict[int, dict[str, float]]:
    header = re.search(r"\bAspheric\s+Coefficients\s+Surface\s+#\s+", table_text, re.I)
    if header is None:
        raise PatentParseError(f"folded macro-tele system {system} coefficient header not found")
    tokens = table_text[header.end() :].split()
    pos = 0
    last_surface = lens_count * 2 + 1
    coefficients: dict[int, dict[str, float]] = {}
    section_count = 0
    while pos < len(tokens):
        if re.fullmatch(r"\(\d+\)", tokens[pos]):
            break
        if tokens[pos].lower() == "surface":
            pos += 1
            if pos < len(tokens) and tokens[pos] == "#":
                pos += 1
        labels: list[str] = []
        while pos < len(tokens) and re.fullmatch(r"Conic|A\d+", tokens[pos], re.I):
            labels.append(tokens[pos])
            pos += 1
        if not labels or labels[0].lower() != "conic":
            raise PatentParseError(
                f"folded macro-tele system {system} coefficient labels are malformed"
            )
        section_count += 1
        for surface_index in range(2, last_surface + 1):
            if pos >= len(tokens) or tokens[pos] != str(surface_index):
                actual = tokens[pos] if pos < len(tokens) else "<end>"
                raise PatentParseError(
                    f"folded macro-tele system {system} coefficient sequence expected "
                    f"{surface_index}, found {actual}"
                )
            pos += 1
            for label in labels:
                if pos >= len(tokens):
                    raise PatentParseError(
                        f"folded macro-tele system {system} coefficient row is incomplete"
                    )
                value = _parse_number(tokens[pos])
                pos += 1
                if label.lower() == "conic":
                    codev_label = "K"
                else:
                    order = int(label[1:])
                    codev_label = ASPHERE_ORDER_TO_CODEV.get(order)
                    if codev_label is None:
                        if abs(value) > 0.0:
                            raise PatentParseError(
                                f"unsupported folded macro-tele asphere term A{order}={value}"
                            )
                        continue
                coefficients.setdefault(surface_index, {})[codev_label] = value
    if section_count not in {1, 2} or any(
        surface_index not in coefficients for surface_index in range(2, last_surface + 1)
    ):
        raise PatentParseError(
            f"folded macro-tele system {system} coefficient coverage is incomplete"
        )
    return coefficients


def _parse_folded_macro_object_states(
    table_text: str,
    *,
    system: str,
) -> list[tuple[str, str, float]]:
    header = re.search(
        rf"\b(?:Lens\s+system|Embodiment)\s+{system}\s+Variation\s+of\s+lens\s+"
        rf"properties\s+with\s+"
        r"object\s+distance\s+Object\s+Distance\s+BFL\s+HFOV\s+\[mm\]\s+\[mm\]\s+"
        r"\[deg\]\s+Magnification\s+",
        table_text,
        re.I,
    )
    if header is None:
        raise PatentParseError(f"folded macro-tele system {system} state table not found")
    tokens = table_text[header.end() :].split()
    states: list[tuple[str, str, float]] = []
    pos = 0
    while pos < len(tokens) and re.fullmatch(r"\(\d+\)", tokens[pos]) is None:
        if pos + 3 >= len(tokens):
            raise PatentParseError(f"folded macro-tele system {system} state row is incomplete")
        object_distance = tokens[pos]
        if object_distance != "Infinity":
            _parse_number(object_distance)
        _parse_number(tokens[pos + 1])  # BFL
        half_field = _parse_number(tokens[pos + 2])
        _parse_number(tokens[pos + 3])  # magnification
        states.append((f"object {object_distance}", object_distance, half_field))
        pos += 4
    return states


def _parse_folded_macro_config_states(
    thickness_text: str,
    field_text: str,
) -> list[tuple[str, str, float]]:
    thickness = re.search(
        rf"\bLens\s+system\s+240\s+Variation\s+of\s+surface\s+thicknesses\s+"
        rf"Surface\s+#\s+Config\.\s+A\s+Config\.\s+B\s+Config\.\s+C\s+"
        rf"0\s+(?P<a>{NUMBER_PATTERN})\s+(?P<b>{NUMBER_PATTERN})\s+"
        rf"(?P<c>{NUMBER_PATTERN})\s+5\s+{NUMBER_PATTERN}\s+{NUMBER_PATTERN}\s+"
        rf"{NUMBER_PATTERN}\s+13\s+{NUMBER_PATTERN}\s+{NUMBER_PATTERN}\s+{NUMBER_PATTERN}",
        thickness_text,
        re.I,
    )
    fields = re.search(
        rf"\bLens\s+system\s+240\s+Config\.\s+#\s+HFOV\s+Magnification\s+"
        rf"A\s+(?P<a>{NUMBER_PATTERN})\s+deg\s+{NUMBER_PATTERN}\s+"
        rf"B\s+(?P<b>{NUMBER_PATTERN})\s+deg\s+{NUMBER_PATTERN}\s+"
        rf"C\s+(?P<c>{NUMBER_PATTERN})\s+deg\s+{NUMBER_PATTERN}",
        field_text,
        re.I,
    )
    if thickness is None or fields is None:
        raise PatentParseError("folded macro-tele system 240 configuration tables are incomplete")
    states: list[tuple[str, str, float]] = []
    for label in ("a", "b", "c"):
        object_token = thickness.group(label)
        object_distance = "Infinity" if label == "a" else object_token
        states.append(
            (
                f"configuration {label.upper()} object {object_distance}",
                object_distance,
                _parse_number(fields.group(label)),
            )
        )
    return states


def _parse_samsung_wide_fov_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse Samsung 7-lens wide-FOV embodiment table pairs.

    In this exact family, ``HFOV`` is explicitly defined as the full horizontal
    field of view.  The conversion therefore divides the published value by two
    for the pipeline's half-field input.
    """

    bindings = list(_SAMSUNG_WIDE_FOV_BINDING_PATTERN.finditer(text))
    if not bindings:
        return []

    binding_numbers = list(range(1, 11))
    attempts: list[_PrescriptionParseAttempt] = []
    try:
        if len(bindings) != 10:
            raise PatentParseError(
                f"Samsung wide-FOV family must disclose 10 embodiments, found {len(bindings)}"
            )
        if _SAMSUNG_WIDE_FOV_FULL_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("Samsung wide-FOV full-field HFOV definition not found")
        if (
            re.search(
                r"\bA,\s+B,\s+C,\s+D,\s+E,\s+F,\s+G,\s+H,\s+and\s+J\s+"
                r"are\s+aspherical\s+constants\b",
                text,
                flags=re.IGNORECASE,
            )
            is None
        ):
            raise PatentParseError("Samsung wide-FOV A-H/J asphere definition not found")
        blocks = _numbered_patent_table_blocks(text)
        metadata = _parse_samsung_wide_fov_metadata(blocks)
        if set(metadata) != set(range(1, 11)):
            raise PatentParseError("Samsung wide-FOV metadata does not cover embodiments 1-10")
        for embodiment_number, binding in enumerate(bindings, start=1):
            surface_table = int(binding.group("surface_table"))
            coefficient_table = int(binding.group("coefficient_table"))
            if (
                binding.group("ordinal").lower() != _ordinal_word(embodiment_number)
                or surface_table != embodiment_number * 2 - 1
                or coefficient_table != embodiment_number * 2
            ):
                raise PatentParseError(
                    "Samsung wide-FOV table/ordinal binding is not consecutive at "
                    f"embodiment {embodiment_number}"
                )
    except Exception as exc:  # noqa: BLE001 - retain the disclosed embodiment set
        for embodiment_number in binding_numbers:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=f"Samsung wide-FOV embodiment {embodiment_number}",
                    error=exc,
                )
            )
        return attempts

    for embodiment_number in range(1, 11):
        embodiment = f"Samsung wide-FOV embodiment {embodiment_number}"
        try:
            surface_table = embodiment_number * 2 - 1
            coefficient_table = embodiment_number * 2
            surface_text = blocks.get(surface_table)
            if surface_text is None:
                raise PatentParseError(f"Samsung wide-FOV TABLE {surface_table} not found")
            coefficient_text = blocks.get(coefficient_table)
            if coefficient_text is None:
                raise PatentParseError(f"Samsung wide-FOV TABLE {coefficient_table} not found")
            surfaces = _parse_samsung_wide_fov_surface_table(
                surface_text,
                embodiment_number=embodiment_number,
            )
            coefficients = _parse_samsung_wide_fov_asphere_table(
                coefficient_text,
                embodiment_number=embodiment_number,
            )
            surface_indices = {surface.index for surface in surfaces}
            if not set(coefficients).issubset(surface_indices):
                raise PatentParseError(
                    f"Samsung wide-FOV embodiment {embodiment_number} coefficients "
                    "reference an unknown surface"
                )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
            focal_length, f_number, full_horizontal_fov = metadata[embodiment_number]
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=full_horizontal_fov / 2.0,
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - retained per published embodiment
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


def _numbered_patent_table_blocks(text: str) -> dict[int, str]:
    blocks: dict[int, str] = {}
    for block in _patent_table_blocks(text):
        if block.number in blocks:
            raise PatentParseError(f"duplicate numbered patent table: {block.number}")
        blocks[block.number] = block.text
    return blocks


def _parse_samsung_wide_fov_metadata(
    blocks: dict[int, str],
) -> dict[int, tuple[float, float, float]]:
    table = blocks.get(21)
    if table is None:
        raise PatentParseError("Samsung wide-FOV TABLE 21 metadata not found")
    first_header = re.search(
        r"\bOptical\s+First\s+Second\s+Third\s+Fourth\s+Fifth\s+Property\s+"
        r"Embodiment\s+Embodiment\s+Embodiment\s+Embodiment\s+Embodiment\s+",
        table,
        flags=re.IGNORECASE,
    )
    second_header = re.search(
        r"\bOptical\s+Sixth\s+Seventh\s+Eighth\s+Ninth\s+Tenth\s+Property\s+"
        r"Embodiment\s+Embodiment\s+Embodiment\s+Embodiment\s+Embodiment\s+",
        table,
        flags=re.IGNORECASE,
    )
    if first_header is None or second_header is None or second_header.start() <= first_header.end():
        raise PatentParseError("Samsung wide-FOV TABLE 21 metadata headers are incomplete")

    metadata: dict[int, tuple[float, float, float]] = {}
    sections = (
        (range(1, 6), table[first_header.end() : second_header.start()]),
        (range(6, 11), table[second_header.end() :]),
    )
    for embodiment_numbers, section in sections:
        focal_lengths = _parse_exact_five_value_row(section, label="f")
        f_numbers = _parse_exact_five_value_row(section, label="f-number")
        full_fields = _parse_exact_five_value_row(section, label="HFOV")
        for embodiment_number, focal_length, f_number, full_field in zip(
            embodiment_numbers,
            focal_lengths,
            f_numbers,
            full_fields,
            strict=True,
        ):
            metadata[embodiment_number] = (focal_length, f_number, full_field)
    return metadata


def _parse_exact_five_value_row(text: str, *, label: str) -> tuple[float, ...]:
    value_sequence = rf"(?P<values>(?:{NUMBER_PATTERN}\s+){{4}}{NUMBER_PATTERN})"
    matches = list(
        re.finditer(
            rf"(?<!\S){re.escape(label)}(?!\S)\s+{value_sequence}",
            text,
            flags=re.IGNORECASE,
        )
    )
    if len(matches) != 1:
        raise PatentParseError(
            f"Samsung wide-FOV metadata row {label} must occur exactly once per half"
        )
    values = tuple(_parse_number(token) for token in matches[0].group("values").split())
    if len(values) != 5:
        raise PatentParseError(f"Samsung wide-FOV metadata row {label} is incomplete")
    return values


def _parse_samsung_wide_fov_surface_table(
    table_text: str,
    *,
    embodiment_number: int,
) -> list[PatentSurface]:
    header = _SAMSUNG_WIDE_FOV_SURFACE_HEADER_PATTERN.search(table_text)
    if header is None:
        raise PatentParseError(
            f"Samsung wide-FOV embodiment {embodiment_number} surface header not found"
        )
    body = re.split(
        r"\s+(?:\(\d+\)|\[\d+\])\s+",
        table_text[header.end() :],
        maxsplit=1,
    )[0]
    starts = list(re.finditer(r"(?<!\S)S(?P<index>\d+)\s+", body, flags=re.IGNORECASE))
    indices = [int(match.group("index")) for match in starts]
    if indices != list(range(1, 20)):
        raise PatentParseError(
            f"Samsung wide-FOV embodiment {embodiment_number} surface sequence must be S1-S19"
        )

    row_labels: dict[int, tuple[str, ...]] = {
        1: ("First", "Lens"),
        3: ("Second", "Lens"),
        5: ("Third", "Lens"),
        7: ("Fourth", "Lens"),
        9: ("Stop",),
        10: ("Fifth", "Lens"),
        11: ("Sixth", "Lens"),
        13: ("Seventh", "Lens"),
        15: ("Filter",),
        17: ("Cover", "Glass"),
        19: ("Imaging", "Plane"),
    }
    material_surfaces = {1, 3, 5, 7, 10, 11, 13, 15, 17}
    surfaces: list[PatentSurface] = []
    for row_index, match in enumerate(starts):
        surface_index = int(match.group("index"))
        end = starts[row_index + 1].start() if row_index + 1 < len(starts) else len(body)
        tokens = body[match.end() : end].split()
        expected_label = row_labels.get(surface_index, ())
        if tuple(token.lower() for token in tokens[: len(expected_label)]) != tuple(
            token.lower() for token in expected_label
        ):
            raise PatentParseError(
                f"Samsung wide-FOV embodiment {embodiment_number} surface "
                f"S{surface_index} label mismatch"
            )
        values = tokens[len(expected_label) :]
        expected_values = 5 if surface_index in material_surfaces else 3
        if len(values) != expected_values:
            raise PatentParseError(
                f"Samsung wide-FOV embodiment {embodiment_number} surface S{surface_index} "
                f"has {len(values)} values, expected {expected_values}"
            )
        radius = _distance_value(values[0], field_name=f"Samsung S{surface_index} radius")
        thickness = _distance_value(
            values[1],
            field_name=f"Samsung S{surface_index} thickness",
        )
        nd = vd = None
        if surface_index in material_surfaces:
            nd = _parse_number(values[2])
            vd = _parse_number(values[3])
            effective_radius = _parse_number(values[4])
            _validate_material_indices(surface_index=surface_index, nd=nd, vd=vd)
        else:
            effective_radius = _parse_number(values[2])
        if effective_radius <= 0:
            raise PatentParseError(
                f"Samsung wide-FOV embodiment {embodiment_number} surface "
                f"S{surface_index} effective radius must be positive"
            )
        label = " ".join(expected_label) if expected_label else f"Surface {surface_index}"
        surfaces.append(
            PatentSurface(
                index=surface_index,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material="Glass" if nd is not None else None,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )
    return surfaces


def _parse_samsung_wide_fov_asphere_table(
    table_text: str,
    *,
    embodiment_number: int,
) -> dict[int, dict[str, float]]:
    header = _SAMSUNG_WIDE_FOV_COEFFICIENT_HEADER_PATTERN.search(table_text)
    if header is None:
        raise PatentParseError(
            f"Samsung wide-FOV embodiment {embodiment_number} coefficient header not found"
        )
    body = re.split(
        r"\s+(?:\(\d+\)|\[\d+\])\s+",
        table_text[header.end() :],
        maxsplit=1,
    )[0]
    tokens = body.split()
    expected_labels = ("K", "A", "B", "C", "D", "E", "F", "G", "H", "J")
    surface_indices = (3, 4, 5, 6, 13, 14)
    coefficients = {surface_index: {} for surface_index in surface_indices}
    position = 0
    for label in expected_labels:
        if position >= len(tokens) or tokens[position].upper() != label:
            raise PatentParseError(
                f"Samsung wide-FOV embodiment {embodiment_number} coefficient row "
                f"{label} not found in order"
            )
        position += 1
        if position + len(surface_indices) > len(tokens):
            raise PatentParseError(
                f"Samsung wide-FOV embodiment {embodiment_number} coefficient row {label} "
                "is incomplete"
            )
        values = [_parse_number(token) for token in tokens[position : position + 6]]
        position += len(surface_indices)
        for surface_index, value in zip(surface_indices, values, strict=True):
            coefficients[surface_index][label] = value
    if position != len(tokens):
        raise PatentParseError(
            f"Samsung wide-FOV embodiment {embodiment_number} coefficient table has extra tokens"
        )
    return coefficients


def _parse_folded_zoom_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact multi-state folded-zoom surface/configuration table triplets."""

    blocks = _patent_table_blocks(text)
    family_blocks: list[tuple[int, _PatentTableBlock, re.Match[str], bool]] = []
    for block_index, block in enumerate(blocks):
        if block_index + 1 >= len(blocks) or not _is_folded_zoom_configuration_table(
            blocks[block_index + 1].text
        ):
            continue
        asp_match = _FOLDED_ZOOM_ASP_SURFACE_HEADER_PATTERN.search(block.text)
        if asp_match is not None:
            family_blocks.append((block_index, block, asp_match, False))
            continue
        qtyp_match = _FOLDED_ZOOM_QTYP_SURFACE_HEADER_PATTERN.search(block.text)
        if qtyp_match is not None:
            family_blocks.append((block_index, block, qtyp_match, True))
    if not family_blocks:
        return []

    attempts: list[_PrescriptionParseAttempt] = []
    attempt_number = 0
    for block_index, surface_block, header_match, is_qtyp in family_blocks:
        system = int(header_match.group("system"))
        config_block = blocks[block_index + 1]
        if is_qtyp:
            dynamic_surfaces = _folded_zoom_qtyp_dynamic_surfaces(
                surface_block.text,
                table_number=config_block.number,
            )
        else:
            dynamic_surfaces = _folded_zoom_dynamic_surface_indices(
                surface_block.text,
                table_number=config_block.number,
            )
        try:
            configurations = _folded_zoom_configurations(
                config_block.text,
                expected_dynamic_surfaces=dynamic_surfaces,
                system=system,
            )
        except Exception as exc:  # noqa: BLE001 - retained as family evidence
            attempt_number += 1
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=attempt_number,
                    embodiment=f"Folded zoom system {system}",
                    error=exc,
                )
            )
            continue

        if is_qtyp:
            qtyp_error = _folded_zoom_qtyp_rejection(surface_block.text, system=system)
            for config_index, _configuration in enumerate(configurations, start=1):
                attempt_number += 1
                attempts.append(
                    _PrescriptionParseAttempt(
                        embodiment_number=attempt_number,
                        embodiment=(f"Folded zoom system {system} configuration {config_index}"),
                        error=qtyp_error,
                    )
                )
            continue

        try:
            surfaces, surface_dynamic_tables = _parse_folded_zoom_asp_surface_table(
                surface_block.text,
                system=system,
            )
            if set(surface_dynamic_tables) != set(dynamic_surfaces):
                raise PatentParseError(
                    f"folded zoom system {system} dynamic surface set changed during parsing"
                )
            if any(table != config_block.number for table in surface_dynamic_tables.values()):
                raise PatentParseError(
                    f"folded zoom system {system} references a non-adjacent configuration table"
                )
            if block_index + 2 >= len(blocks):
                raise PatentParseError(f"folded zoom system {system} asphere table not found")
            coefficient_end = next(
                surface.index for surface in surfaces if surface.label in {"Filter", "Image"}
            )
            coefficients = _parse_folded_zoom_asphere_table(
                blocks[block_index + 2].text,
                expected_surface_ids=[
                    surface.index for surface in surfaces if surface.index < coefficient_end
                ],
                system=system,
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    # The coefficient table explicitly enumerates both faces of
                    # every ASP lens even where the compact surface table only
                    # repeats the ASP type on the first face.
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
        except Exception as exc:  # noqa: BLE001 - repeated for every disclosed state
            for config_index, _configuration in enumerate(configurations, start=1):
                attempt_number += 1
                attempts.append(
                    _PrescriptionParseAttempt(
                        embodiment_number=attempt_number,
                        embodiment=(f"Folded zoom system {system} configuration {config_index}"),
                        error=exc,
                    )
                )
            continue

        for config_index, configuration in enumerate(configurations, start=1):
            attempt_number += 1
            embodiment = f"Folded zoom system {system} configuration {config_index}"
            try:
                state_surfaces = [
                    replace(
                        surface,
                        thickness_mm=configuration[3].get(
                            surface.index,
                            surface.thickness_mm,
                        ),
                        asphere_coefficients=dict(surface.asphere_coefficients),
                    )
                    for surface in surfaces
                ]
                prescription = PatentPrescription(
                    patent_id=patent_id,
                    embodiment=embodiment,
                    focal_length_mm=configuration[0],
                    f_number=configuration[1],
                    hfov_deg=configuration[2],
                    surfaces=state_surfaces,
                )
            except Exception as exc:  # noqa: BLE001 - retained per configuration
                attempts.append(
                    _PrescriptionParseAttempt(
                        embodiment_number=attempt_number,
                        embodiment=embodiment,
                        error=exc,
                    )
                )
                continue
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=attempt_number,
                    embodiment=embodiment,
                    prescription=prescription,
                )
            )
    return attempts


def _is_folded_zoom_configuration_table(table_text: str) -> bool:
    return (
        len(re.findall(r"\bEFL\s*=", table_text, flags=re.IGNORECASE)) >= 2
        and re.search(r"F\s*/\s*#", table_text, flags=re.IGNORECASE) is not None
        and re.search(r"\bHFOV\b", table_text, flags=re.IGNORECASE) is not None
    )


def _folded_zoom_dynamic_surface_indices(
    surface_text: str,
    *,
    table_number: int,
) -> tuple[int, ...]:
    matches = re.findall(
        rf"(?<!\S)(?P<surface>\d+)\s+{NUMBER_PATTERN}\s+"
        rf"See\s+Table\s+{table_number}\b",
        surface_text,
        flags=re.IGNORECASE,
    )
    return tuple(dict.fromkeys(int(surface) for surface in matches))


def _folded_zoom_qtyp_dynamic_surfaces(
    surface_text: str,
    *,
    table_number: int,
) -> tuple[int, ...]:
    matches = re.findall(
        rf"S\.sub\.(?P<surface>\d+)\s+QTYP\s+{NUMBER_PATTERN}\s+"
        rf"See\s+Table\s+{table_number}\b",
        surface_text,
        flags=re.IGNORECASE,
    )
    return tuple(dict.fromkeys(int(surface) for surface in matches))


def _folded_zoom_configurations(
    table_text: str,
    *,
    expected_dynamic_surfaces: tuple[int, ...],
    system: int,
) -> list[tuple[float, float, float, dict[int, float]]]:
    efls = [
        _parse_number(match.group("value"))
        for match in re.finditer(
            rf"\bEFL\s*=\s*(?P<value>{NUMBER_PATTERN})",
            table_text,
            flags=re.IGNORECASE,
        )
    ]
    if not efls:
        raise PatentParseError(f"folded zoom system {system} EFL row not found")
    count = len(efls)

    fno_match = re.search(
        r"F\s*/\s*#\s+(?P<values>.*?)\s+HFOV\b",
        table_text,
        flags=re.IGNORECASE,
    )
    if fno_match is None:
        raise PatentParseError(f"folded zoom system {system} F/# row not found")
    fnos = _folded_zoom_exact_row_values(
        fno_match.group("values"),
        count=count,
        field=f"system {system} F/#",
    )

    hfov_match = re.search(
        r"\bHFOV(?:\s+\[deg\])?\s+(?P<values>.*)",
        table_text,
        flags=re.IGNORECASE,
    )
    if hfov_match is None:
        raise PatentParseError(f"folded zoom system {system} HFOV row not found")
    hfovs = _folded_zoom_exact_row_values(
        hfov_match.group("values"),
        count=count,
        field=f"system {system} HFOV",
        allow_trailing_narrative=True,
    )

    row_matches = list(
        re.finditer(
            r"(?:\bSurface\s+|\bS\.sub\.)(?P<surface>\d+)\s+",
            table_text,
            flags=re.IGNORECASE,
        )
    )
    dynamic_values: dict[int, list[float]] = {}
    fno_start = fno_match.start()
    for row_index, row_match in enumerate(row_matches):
        surface = int(row_match.group("surface"))
        if surface not in expected_dynamic_surfaces:
            continue
        end = row_matches[row_index + 1].start() if row_index + 1 < len(row_matches) else fno_start
        end = min(end, fno_start)
        dynamic_values[surface] = _folded_zoom_exact_row_values(
            table_text[row_match.end() : end],
            count=count,
            field=f"system {system} surface {surface} thickness",
        )
    if set(dynamic_values) != set(expected_dynamic_surfaces):
        missing = sorted(set(expected_dynamic_surfaces) - set(dynamic_values))
        raise PatentParseError(f"folded zoom system {system} configuration rows missing: {missing}")

    if any(value <= 0.0 for value in (*efls, *fnos, *hfovs)):
        raise PatentParseError(f"folded zoom system {system} metadata must be positive")
    if any(value >= 90.0 for value in hfovs):
        raise PatentParseError(f"folded zoom system {system} HFOV must be below 90 degrees")
    return [
        (
            efls[index],
            fnos[index],
            hfovs[index],
            {surface: values[index] for surface, values in dynamic_values.items()},
        )
        for index in range(count)
    ]


def _folded_zoom_exact_row_values(
    text: str,
    *,
    count: int,
    field: str,
    allow_trailing_narrative: bool = False,
) -> list[float]:
    source = text
    if allow_trailing_narrative:
        source = re.split(r"\s(?:\(\d+\)|\[\d+\])\s", source, maxsplit=1)[0]
    tokens = re.findall(NUMBER_PATTERN, source, flags=re.IGNORECASE)
    if len(tokens) != count:
        raise PatentParseError(
            f"folded zoom {field} row has {len(tokens)} values, expected {count}"
        )
    return [_parse_number(token) for token in tokens]


def _parse_folded_zoom_asp_surface_table(
    table_text: str,
    *,
    system: int,
) -> tuple[list[PatentSurface], dict[int, int]]:
    header = _FOLDED_ZOOM_ASP_SURFACE_HEADER_PATTERN.search(table_text)
    if header is None:
        raise PatentParseError(f"folded zoom system {system} ASP surface header not found")
    candidates = list(_FOLDED_ZOOM_NUMERIC_ROW_PATTERN.finditer(table_text, header.end()))
    starts: list[re.Match[str]] = []
    expected_index = 1
    for match in candidates:
        if int(match.group("index")) != expected_index:
            continue
        starts.append(match)
        expected_index += 1
    if not starts:
        raise PatentParseError(f"folded zoom system {system} surface rows not found")

    surfaces: list[PatentSurface] = []
    dynamic_tables: dict[int, int] = {}
    for row_index, match in enumerate(starts):
        surface_index = int(match.group("index"))
        end = starts[row_index + 1].start() if row_index + 1 < len(starts) else len(table_text)
        row = table_text[match.end() : end].split()
        upper = [token.upper() for token in row]
        if "ASP" in upper:
            radius_pos = upper.index("ASP") + 1
            surface_type = "ASP"
        elif "PLANO" in upper:
            radius_pos = upper.index("PLANO") + 1
            surface_type = None
        else:
            radius_pos = 0
            surface_type = None
        if radius_pos >= len(row):
            raise PatentParseError(
                f"folded zoom system {system} surface {surface_index} radius missing"
            )
        radius = _distance_value(
            row[radius_pos],
            field_name=f"folded zoom surface {surface_index} radius",
        )
        thickness_pos = radius_pos + 1
        if thickness_pos >= len(row):
            raise PatentParseError(
                f"folded zoom system {system} surface {surface_index} thickness missing"
            )
        if (
            len(row) > thickness_pos + 2
            and row[thickness_pos].upper() == "SEE"
            and row[thickness_pos + 1].upper() == "TABLE"
        ):
            table_number = int(_parse_number(row[thickness_pos + 2]))
            thickness = None
            dynamic_tables[surface_index] = table_number
        else:
            thickness = _distance_value(
                row[thickness_pos],
                field_name=f"folded zoom surface {surface_index} thickness",
            )

        material = nd = vd = None
        material_pos = next(
            (pos for pos, token in enumerate(upper) if token in {"PLASTIC", "GLASS"}),
            None,
        )
        if material_pos is not None:
            if material_pos + 2 >= len(row):
                raise PatentParseError(
                    f"folded zoom system {system} surface {surface_index} material indices missing"
                )
            material = row[material_pos]
            nd = _parse_number(row[material_pos + 1])
            vd = _parse_number(row[material_pos + 2])
            _validate_material_indices(surface_index=surface_index, nd=nd, vd=vd)

        joined = " ".join(row[:radius_pos]).upper()
        lens_match = re.search(r"\bLENS\s+(\d+)\b", joined)
        if "STOP" in joined:
            label = "Stop"
        elif lens_match is not None:
            label = f"Lens {lens_match.group(1)}"
        elif "FILTER" in joined:
            label = "Filter"
        elif "IMAGE" in joined:
            label = "Image"
        else:
            label = f"Surface {surface_index}"
        surfaces.append(
            PatentSurface(
                index=surface_index,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=material,
                nd=nd,
                vd=vd,
                surface_type=surface_type,
            )
        )
    if surfaces[-1].label != "Image":
        raise PatentParseError(f"folded zoom system {system} image row not found")
    return surfaces, dynamic_tables


def _parse_folded_zoom_asphere_table(
    table_text: str,
    *,
    expected_surface_ids: list[int],
    system: int,
) -> dict[int, dict[str, float]]:
    header = re.search(
        r"\bAspheric\s+Coefficients\s+Surface\s+#\s+"
        r"(?P<labels>Conic(?:\s+A\d+)+)\s+",
        table_text,
        flags=re.IGNORECASE,
    )
    if header is None:
        raise PatentParseError(f"folded zoom system {system} asphere header not found")
    labels = header.group("labels").upper().split()
    tokens = re.findall(NUMBER_PATTERN, table_text[header.end() :], flags=re.IGNORECASE)
    row_width = 1 + len(labels)
    required = row_width * len(expected_surface_ids)
    if len(tokens) < required:
        raise PatentParseError(f"folded zoom system {system} asphere table is incomplete")
    coefficients: dict[int, dict[str, float]] = {}
    pos = 0
    for expected_surface in expected_surface_ids:
        surface_token = tokens[pos]
        pos += 1
        if not surface_token.isdigit() or int(surface_token) != expected_surface:
            raise PatentParseError(
                f"folded zoom system {system} asphere index break: "
                f"expected {expected_surface}, found {surface_token}"
            )
        row: dict[str, float] = {}
        for label in labels:
            value = _parse_number(tokens[pos])
            pos += 1
            if label == "CONIC":
                row["K"] = value
                continue
            order = int(label[1:])
            if order not in SUPPORTED_ASPHERE_ORDERS:
                if abs(value) > 0.0:
                    raise PatentParseError(
                        f"unsupported nonzero folded zoom asphere term: "
                        f"S{expected_surface}:A{order}={value:.3g}"
                    )
                continue
            row[ASPHERE_ORDER_TO_CODEV[order]] = value
        coefficients[expected_surface] = row
    return coefficients


def _folded_zoom_qtyp_rejection(table_text: str, *, system: int) -> PatentParseError:
    header = _FOLDED_ZOOM_QTYP_SURFACE_HEADER_PATTERN.search(table_text)
    assert header is not None
    indices: list[int] = []
    for match in re.finditer(r"\bS(?:\.sub\.)?(?P<index>\d+)\b", table_text[header.end() :]):
        index = int(match.group("index"))
        indices.append(index)
        if index >= 23:
            break
    for expected, actual in enumerate(indices):
        if actual != expected:
            return PatentParseError(
                f"folded zoom system {system} surface index break: "
                f"expected S{expected}, found S{actual}"
            )
    return PatentParseError(
        f"folded zoom system {system} uses unsupported published QTYP/NR/A0-A6 surfaces"
    )


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


# ---------------------------------------------------------------------------
# SEKONIX fallback family.  Its publications pair an odd-numbered surface
# table with the following even-numbered coefficient table.  Three surface
# headings are in circulation: RDY/THI/Nd/Vd, Sphere/Asphere with Y Radius,
# and Qcon Asphere with a compact numeric Glass Code.
# ---------------------------------------------------------------------------

_SEKONIX_ROW_RE = re.compile(r"^(?:\d+|S\d+|STOP:?|STO:?|IMAGE:?|IMG:?)$", re.IGNORECASE)
_SEKONIX_TYPE_RE = re.compile(r"^(?:sphere|asphere|spherical|aspheric(?:al)?|qcon)$", re.I)
_SEKONIX_RANGE_META_RE = re.compile(
    r"\b(?:FOV|HFOV|Fno|F\s*number|effective\s+focal\s+(?:length|distance)|f)\b"
    r"[^.;]{0,80}(?:<|>|\u2264|\u2265)",
    re.IGNORECASE,
)


def _parse_sekonix_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse SEKONIX odd/even prescription table pairs independently."""

    blocks = _patent_table_blocks(text)
    surface_blocks = [
        (index, block)
        for index, block in enumerate(blocks)
        if block.number % 2 == 1 and _sekonix_surface_signature(block.text)
    ]
    if not surface_blocks:
        return []

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, (block_index, block) in enumerate(surface_blocks, start=1):
        embodiment = f"SEKONIX embodiment {embodiment_number}"
        # Metadata may be printed before the surface table or after its paired
        # coefficient table.  Start at the nearest embodiment marker in the
        # inter-table prose: starting at publication zero would admit prior-art
        # values, while starting at the table would discard leading metadata.
        search_start = 0
        if embodiment_number > 1:
            previous_block_index = surface_blocks[embodiment_number - 2][0]
            previous_pair_index = previous_block_index + 1
            if previous_pair_index < len(blocks):
                search_start = blocks[previous_pair_index].end
        leading_prose = text[search_start : block.start]
        markers = list(re.finditer(r"\b(?:the\s+)?(?:\w+\s+)?embodiment\b", leading_prose, re.I))
        span_start = search_start + markers[-1].start() if markers else block.start
        next_start = (
            surface_blocks[embodiment_number][1].start
            if embodiment_number < len(surface_blocks)
            else len(text)
        )
        try:
            surfaces, index_by_label = _parse_sekonix_surface_table(
                block.text,
                embodiment_number=embodiment_number,
            )
            coefficients: dict[int, dict[str, float]] = {}
            if block_index + 1 < len(blocks):
                coefficient_block = blocks[block_index + 1]
                if coefficient_block.number == block.number + 1:
                    coefficients = _parse_sekonix_asphere_table(
                        coefficient_block.text,
                        index_by_label=index_by_label,
                    )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.asphere_coefficients.update(coefficients[surface.index])
                    surface.surface_type = "ASP"
            meta = _sekonix_meta_for_span(text[span_start:next_start])
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=meta.focal_length_mm,
                f_number=meta.f_number,
                hfov_deg=meta.hfov_deg,
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - per-embodiment fail-loud ledger
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


def _sekonix_surface_signature(block_text: str) -> bool:
    upper = block_text.upper()
    has_header = ("RDY" in upper and "THI" in upper) or (
        "Y RADIUS" in upper and "THICKNESS" in upper
    )
    has_rows = re.search(r"\bOBJECT\b", upper) is not None
    return has_header and has_rows


def _parse_sekonix_surface_table(
    block_text: str,
    *,
    embodiment_number: int,
) -> tuple[list[PatentSurface], dict[str, int]]:
    tokens = block_text.split()
    object_pos = next(
        (pos for pos, token in enumerate(tokens) if token.upper() == "OBJECT"),
        None,
    )
    if object_pos is None:
        raise PatentParseError(f"SEKONIX embodiment {embodiment_number} object row not found")
    tokens = tokens[object_pos + 1 :]
    row_starts = [
        (pos, token.rstrip(":"))
        for pos, token in enumerate(tokens)
        if _SEKONIX_ROW_RE.fullmatch(token)
    ]
    if not row_starts:
        raise PatentParseError(f"SEKONIX embodiment {embodiment_number} surface rows not found")

    glass_code_header = "GLASS CODE" in block_text.upper()
    surfaces: list[PatentSurface] = []
    index_by_label: dict[str, int] = {}
    for row_number, (pos, raw_label) in enumerate(row_starts):
        row_end = row_starts[row_number + 1][0] if row_number + 1 < len(row_starts) else len(tokens)
        row = [token for token in tokens[pos + 1 : row_end] if not _is_empty_value(token)]
        label = raw_label.upper()
        if label in {"IMAGE", "IMG"}:
            row = [token for token in row if not _SEKONIX_TYPE_RE.fullmatch(token)]
            radius = _sekonix_distance(row[0], field_name=f"{label} radius") if row else 0.0
            thickness = (
                _sekonix_distance(row[1], field_name=f"{label} thickness") if len(row) > 1 else 0.0
            )
            surfaces.append(
                PatentSurface(
                    index=len(surfaces) + 1,
                    label="Image",
                    radius_mm=radius,
                    thickness_mm=thickness,
                    material=None,
                    nd=None,
                    vd=None,
                    surface_type=None,
                )
            )
            continue

        is_asphere = False
        while row and _SEKONIX_TYPE_RE.fullmatch(row[0]):
            if row.pop(0).lower() in {"asphere", "aspheric", "aspherical", "qcon"}:
                is_asphere = True
        if len(row) < 2:
            raise PatentParseError(f"SEKONIX surface {raw_label} row is incomplete")
        radius = _sekonix_distance(row[0], field_name=f"{raw_label} radius")
        thickness = _sekonix_distance(row[1], field_name=f"{raw_label} thickness")
        tail = row[2:]
        nd = vd = None
        material = None
        if glass_code_header and tail:
            glass_code = next((token for token in tail if _sekonix_glass_code(token)), None)
            if glass_code is not None:
                nd, vd = _sekonix_glass_code(glass_code) or (None, None)
                material = glass_code
            elif malformed := next(
                (token for token in tail if re.fullmatch(r"\d{5,7}\.\d{3,5}", token)),
                None,
            ):
                raise PatentParseError(f"malformed SEKONIX Glass Code: {malformed}")
            elif any(re.search(r"[A-Za-z]", token) for token in tail[:-1]):
                named = next(token for token in tail[:-1] if re.search(r"[A-Za-z]", token))
                raise PatentParseError(
                    f"SEKONIX Glass Code cannot be split deterministically: {named}"
                )
        elif len(tail) >= 2:
            candidates = []
            for token in tail:
                try:
                    candidates.append(_parse_number(token))
                except PatentParseError:
                    continue
            if (
                len(candidates) >= 2
                and _is_physical_nd(candidates[0])
                and _is_physical_vd(candidates[1])
            ):
                nd, vd = candidates[:2]
                material = "Glass"
        _validate_material_indices(surface_index=len(surfaces) + 1, nd=nd, vd=vd)
        surface_index = len(surfaces) + 1
        surface = PatentSurface(
            index=surface_index,
            label="Stop" if label in {"STOP", "STO"} else f"Surface {raw_label}",
            radius_mm=radius,
            thickness_mm=thickness,
            material=material,
            nd=nd,
            vd=vd,
            surface_type="ASP" if is_asphere else None,
        )
        surfaces.append(surface)
        index_by_label[label] = surface_index
        if label.startswith("S") and label[1:].isdigit():
            index_by_label[label[1:]] = surface_index

    if len(surfaces) < 4:
        raise PatentParseError(
            f"SEKONIX embodiment {embodiment_number} surface table too short: {len(surfaces)} rows"
        )
    return surfaces, index_by_label


def _sekonix_distance(token: str, *, field_name: str) -> float:
    if token.lower() in {"infinite", "infinity", "inf"}:
        return math.inf
    try:
        return _sekonix_number(token)
    except PatentParseError as exc:
        raise PatentParseError(f"SEKONIX {field_name} is not numeric: {token}") from exc


def _sekonix_glass_code(token: str) -> tuple[float, float] | None:
    match = re.fullmatch(r"(?P<nd>\d{6})\.(?P<vd>\d{4})", token)
    if match is None:
        return None
    return 1.0 + int(match.group("nd")) / 1_000_000.0, int(match.group("vd")) / 100.0


def _sekonix_number(token: str) -> float:
    """Accept the ``3.36681.E+02`` numeric spelling emitted by PPUBS."""

    return _parse_number(re.sub(r"\.E(?=[+-]?\d+$)", "E", token, flags=re.IGNORECASE))


def _parse_sekonix_asphere_table(
    block_text: str,
    *,
    index_by_label: dict[str, int],
) -> dict[int, dict[str, float]]:
    tokens = block_text.split()
    coefficients: dict[int, dict[str, float]] = {}
    if "QCON COEFFICIENT" in block_text.upper():
        # US-12619054-B2, Mathematical Expression 1, and US-12498545-B2,
        # Mathematical Expression 1, define the departure as
        # ``u^4 * sum(a_m * Q_m^con(u^2))`` with ``u=r/r_n``.  Those Forbes
        # Qcon coefficients are not monomial r^4/r^6 coefficients.
        raise PatentParseError("Qcon basis conversion not implemented")

    header_pos = next(
        (
            pos
            for pos, token in enumerate(tokens)
            if token.upper() == "K"
            and pos + 1 < len(tokens)
            and re.fullmatch(r"A\d+", tokens[pos + 1], re.IGNORECASE)
        ),
        None,
    )
    if header_pos is None:
        return coefficients
    # US-11099361-B2, Equation 1 (verbatim term sequence):
    # ``A3 * Y^4 + A4 * Y^6 + A5 * Y^8 + A6 * Y^10 + ... + A14 * Y^26``.
    # Therefore its A-number is an even-order sequence index, not the power.
    labels: list[str] = []
    while header_pos < len(tokens) and re.fullmatch(r"K|A\d+", tokens[header_pos], re.I):
        labels.append(tokens[header_pos].upper())
        header_pos += 1
    pos = header_pos
    while pos < len(tokens):
        surface_match = re.fullmatch(r"S(\d+)", tokens[pos], re.I)
        if surface_match is None:
            pos += 1
            continue
        surface_label = surface_match.group(1)
        pos += 1
        for label in labels:
            if pos >= len(tokens):
                raise PatentParseError(f"SEKONIX S{surface_label} asphere row is incomplete")
            value = 0.0 if _is_empty_value(tokens[pos]) else _sekonix_number(tokens[pos])
            pos += 1
            if label == "K":
                codev_label = "K"
            else:
                patent_order = int(label[1:])
                codev_order = 2 * (patent_order - 1)
                codev_label = ASPHERE_ORDER_TO_CODEV.get(codev_order)
                if codev_label is None:
                    if abs(value) > 0.0:
                        raise PatentParseError(
                            "unsupported nonzero SEKONIX asphere term: "
                            f"S{surface_label}:{label}={value:.3g}"
                        )
                    continue
            surface_index = index_by_label.get(surface_label)
            if surface_index is not None:
                coefficients.setdefault(surface_index, {})[codev_label] = value
    return coefficients


def _sekonix_meta_for_span(span: str) -> _SunnyMeta:
    exact_patterns = {
        "efl": (
            rf"(?<![/A-Za-z0-9])f\s*=\s*(?P<value>{NUMBER_PATTERN})\s*mm",
            rf"effective focal (?:length|distance)[^.;=]{{0,80}}(?:=|\bis)\s*(?P<value>{NUMBER_PATTERN})\s*mm",
        ),
        "fno": (
            rf"\bFno\s*=\s*(?P<value>{NUMBER_PATTERN})",
            rf"\bF\s*number\s+Fno[^.;=]{{0,50}}=\s*(?P<value>{NUMBER_PATTERN})",
        ),
        "fov": (rf"\bFOV\s*=\s*(?P<value>{NUMBER_PATTERN})\s*°?",),
    }
    found: dict[str, float | None] = {"efl": None, "fno": None, "fov": None}
    for meta_field, patterns in exact_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, span, flags=re.IGNORECASE)
            if match is not None:
                found[meta_field] = _parse_number(match.group("value"))
                break
    missing = [field for field, value in found.items() if value is None]
    if missing:
        qualifier = (
            " (range-only metadata is not an instance value)"
            if _SEKONIX_RANGE_META_RE.search(span)
            else ""
        )
        raise PatentParseError(
            "SEKONIX embodiment metadata lacks exact instance " + "/".join(missing) + qualifier
        )
    return _SunnyMeta(
        focal_length_mm=found["efl"],
        f_number=found["fno"],
        hfov_deg=found["fov"] / 2.0,
    )


# ---------------------------------------------------------------------------
# Sunny Optics (Zhejiang Sunny Optics / Sunny Optical) fallback family
# (DATA-10b parser expansion). Modern Sunny prescriptions use OBJ/STO/S<n>
# surface tables ("OBJ spherical infinite infinite / STO spherical infinite
# -0.38 / S1 aspheric R T [nd vd] [conic] ..."), column-oriented asphere
# tables headed "Surface number A4 A6 ...", and one of three metadata styles:
# a per-embodiment table (f(mm)/Semi-FOV(deg)/f/EPD rows), one consolidated
# all-embodiments table (rows of per-example values), or narrative sentences
# ("satisfies Semi-FOV=43.7deg", "Fno ... is 2.27").
# ---------------------------------------------------------------------------

_SUNNY_ROW_KEY_RE = re.compile(r"^(?:OBJ|STO|S\d+)$")
_SUNNY_SURFACE_TYPE_RE = re.compile(r"^(?:spherical|aspheric(?:al)?)$", re.IGNORECASE)
_SUNNY_NARRATIVE_CUT_RE = re.compile(r"\s(?:\(\d+\)|\[\d+\])\s")


@dataclass(frozen=True)
class _SunnyMeta:
    focal_length_mm: float | None = None
    f_number: float | None = None
    hfov_deg: float | None = None
    epd_mm: float | None = None

    def merged_with(self, other: _SunnyMeta) -> _SunnyMeta:
        return _SunnyMeta(
            focal_length_mm=(
                self.focal_length_mm if self.focal_length_mm is not None else other.focal_length_mm
            ),
            f_number=self.f_number if self.f_number is not None else other.f_number,
            hfov_deg=self.hfov_deg if self.hfov_deg is not None else other.hfov_deg,
            epd_mm=self.epd_mm if self.epd_mm is not None else other.epd_mm,
        )


def _parse_sunny_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse Sunny Optics OBJ/STO surface tables plus detached metadata."""

    blocks = _patent_table_blocks(text)
    surface_blocks: list[tuple[int, _PatentTableBlock]] = []
    for block_index, block in enumerate(blocks):
        if _sunny_surface_block_signature(block.text):
            surface_blocks.append((block_index, block))
    if not surface_blocks:
        return []

    consolidated = _sunny_consolidated_meta_rows(
        blocks,
        embodiment_count=len(surface_blocks),
        document_text=text,
    )
    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, (_block_index, block) in enumerate(surface_blocks, start=1):
        embodiment = f"Sunny embodiment {embodiment_number}"
        next_surface_start = (
            surface_blocks[embodiment_number][1].start
            if embodiment_number < len(surface_blocks)
            else len(text)
        )
        try:
            surfaces, index_by_row_key = _parse_sunny_surface_table(
                block.text,
                embodiment_number=embodiment_number,
            )
            coefficients = _parse_sunny_asphere_blocks(
                blocks,
                span_start=block.end,
                span_end=next_surface_start,
                index_by_row_key=index_by_row_key,
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.asphere_coefficients.update(coefficients[surface.index])
                    surface.surface_type = "ASP"
            # The span starts at the surface block itself: the "In this
            # example, ... f ... is 3.36 mm" summary sentence lives in the
            # surface block's trailing narrative (before the next TABLE-US
            # marker), and none of the metadata labels can occur inside the
            # OBJ/STO/S-row table body itself.
            meta = _sunny_meta_for_embodiment(
                text,
                embodiment_number=embodiment_number,
                table_span=(block.start, next_surface_start),
                consolidated=consolidated,
            )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=meta[0],
                f_number=meta[1],
                hfov_deg=meta[2],
                surfaces=surfaces,
            )
        except Exception as exc:  # noqa: BLE001 - kept as a per-embodiment failure
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


def _sunny_surface_block_signature(block_text: str) -> bool:
    body = _cut_sunny_table_narrative(block_text)
    tokens = body.split()
    has_obj = "OBJ" in tokens
    s_rows = sum(1 for token in tokens if re.fullmatch(r"S\d+", token))
    has_type = any(_SUNNY_SURFACE_TYPE_RE.fullmatch(token) for token in tokens)
    return has_obj and has_type and s_rows >= 3


def _cut_sunny_table_narrative(text: str) -> str:
    return _SUNNY_NARRATIVE_CUT_RE.split(text, maxsplit=1)[0]


def _cut_sunny_conditional_tail(text: str) -> str:
    """Drop conditional-expression summary tables from a metadata span.

    Those tables ("TABLE 13 Conditional/Example 1 2 3 ..." with rows like
    "f/EPD 1.37 1.42 ...") list per-EXAMPLE values, so a naive first-match in
    the last embodiment's span (which runs to the end of the document) would
    silently assign example 1's value to example N.
    """

    match = re.search(
        r"\bConditional\s*/\s*(?:Example|Embodiment)|\bTABLE\s+\d+\s+Conditional|"
        r"\bconditional\s+expressions?\b",
        text,
        flags=re.IGNORECASE,
    )
    return text[: match.start()] if match is not None else text


def _sunny_distance(token: str, *, field_name: str) -> float:
    if token.lower() in {"infinite", "infinity", "inf"}:
        return math.inf
    try:
        return _parse_number(token)
    except PatentParseError as exc:
        raise PatentParseError(f"Sunny {field_name} is not numeric: {token}") from exc


def _parse_sunny_surface_table(
    block_text: str,
    *,
    embodiment_number: int,
) -> tuple[list[PatentSurface], dict[str, int]]:
    body = _cut_sunny_table_narrative(block_text)
    tokens = [token for token in body.split() if token]
    row_starts = [
        (pos, token) for pos, token in enumerate(tokens) if _SUNNY_ROW_KEY_RE.fullmatch(token)
    ]
    if not row_starts:
        raise PatentParseError(
            f"Sunny embodiment {embodiment_number} surface table had no OBJ/STO/S rows"
        )

    surfaces: list[PatentSurface] = []
    index_by_row_key: dict[str, int] = {}
    for row_pos, (pos, row_key) in enumerate(row_starts):
        row_end = row_starts[row_pos + 1][0] if row_pos + 1 < len(row_starts) else len(tokens)
        row = tokens[pos + 1 : row_end]
        if row and _SUNNY_SURFACE_TYPE_RE.fullmatch(row[0]):
            surface_type_token = row[0].lower()
            row = row[1:]
            # Two-token variant: "Aspheric surface" / "Spherical surface".
            if row and row[0].lower() == "surface":
                row = row[1:]
        else:
            surface_type_token = ""
        if row_key == "OBJ":
            continue

        values = [
            _sunny_distance(token, field_name=f"{row_key} value")
            for token in row
            if not _is_empty_value(token)
        ]
        if not values:
            raise PatentParseError(f"Sunny {row_key} row had no numeric values")
        radius = values[0]
        thickness = values[1] if len(values) >= 2 else 0.0
        rest = values[2:]
        nd = vd = None
        if len(rest) >= 2 and _is_physical_nd(rest[0]) and _is_physical_vd(rest[1]):
            nd, vd = rest[0], rest[1]
            rest = rest[2:]
        # Some Sunny tables add a per-element Focal-length column between the
        # Abbe number and the Conic coefficient (header "... Abbe Focal Conic
        # number length coefficient"). Column order is fixed, so with two
        # trailing values the last one is the conic and the first (the element
        # focal length) is redundant derived data we do not need.
        conic = rest[-1] if rest else None
        if len(rest) > 2:
            raise PatentParseError(
                f"Sunny {row_key} row has unexpected extra values: {rest[:-1]!r}"
            )
        _validate_material_indices(surface_index=len(surfaces) + 1, nd=nd, vd=vd)

        surface_index = len(surfaces) + 1
        surface = PatentSurface(
            index=surface_index,
            label="Stop" if row_key == "STO" else f"Surface {row_key}",
            radius_mm=radius,
            thickness_mm=thickness,
            material="Glass" if nd is not None else None,
            nd=nd,
            vd=vd,
            surface_type="ASP" if surface_type_token == "aspheric" else None,
        )
        if conic is not None and abs(conic) > 0.0:
            surface.asphere_coefficients["K"] = conic
        surfaces.append(surface)
        index_by_row_key[row_key] = surface_index

    if len(surfaces) < 4:
        raise PatentParseError(
            f"Sunny embodiment {embodiment_number} surface table too short: {len(surfaces)} rows"
        )
    return surfaces, index_by_row_key


def _parse_sunny_asphere_blocks(
    blocks: list[_PatentTableBlock],
    *,
    span_start: int,
    span_end: int,
    index_by_row_key: dict[str, int],
) -> dict[int, dict[str, float]]:
    coefficients: dict[int, dict[str, float]] = {}
    for block in blocks:
        if block.start < span_start or block.start >= span_end:
            continue
        _parse_sunny_asphere_block_into(
            block.text,
            index_by_row_key=index_by_row_key,
            coefficients=coefficients,
        )
    return coefficients


def _parse_sunny_asphere_block_into(
    block_text: str,
    *,
    index_by_row_key: dict[str, int],
    coefficients: dict[int, dict[str, float]],
) -> None:
    body = _cut_sunny_table_narrative(block_text)
    tokens = [token for token in body.split() if token]
    pos = 0
    labels: list[str] = []
    while pos < len(tokens):
        token = tokens[pos]
        if token == "Surface" and pos + 1 < len(tokens) and tokens[pos + 1] == "number":
            pos += 2
            labels = []
            while pos < len(tokens) and re.fullmatch(r"[AK]\d*", tokens[pos], re.IGNORECASE):
                labels.append(tokens[pos].upper())
                pos += 1
            continue
        row_match = re.fullmatch(r"S\d+", token)
        if row_match is None or not labels:
            pos += 1
            continue
        row_key = token
        pos += 1
        values: list[float] = []
        for label in labels:
            if pos >= len(tokens):
                raise PatentParseError(f"Sunny asphere row {row_key} is incomplete at {label}")
            raw = tokens[pos]
            if _CORRUPT_EXPONENT_RE.fullmatch(raw):
                raise PatentParseError(
                    f"OCR-corrupted exponent token in Sunny asphere table: {raw!r}"
                )
            if _is_empty_value(raw):
                values.append(0.0)
            else:
                values.append(_parse_number(raw))
            pos += 1
        if pos < len(tokens) and re.fullmatch(NUMBER_PATTERN, tokens[pos], re.IGNORECASE):
            raise PatentParseError(
                f"Sunny asphere row {row_key} has more values than headers: {tokens[pos]!r}"
            )
        surface_index = index_by_row_key.get(row_key)
        if surface_index is None:
            continue
        for label, value in zip(labels, values, strict=True):
            if label == "K":
                coefficients.setdefault(surface_index, {})["K"] = value
                continue
            order = int(label[1:])
            if order not in SUPPORTED_ASPHERE_ORDERS:
                if abs(value) > 0.0:
                    raise PatentParseError(
                        f"unsupported nonzero Sunny asphere term: {row_key}:{label}={value:.3g}"
                    )
                continue
            coefficients.setdefault(surface_index, {})[ASPHERE_ORDER_TO_CODEV[order]] = value


_SUNNY_DEG_PAREN = r"\(\s*(?:°|˚|deg\.?)\s*\)"
# Table-style labels: only valid inside the embodiment's own table span
# (surface-block end .. next surface-block start). Narrative-style sentences
# ("satisfies Semi-FOV=43.7", "Fno ... is 2.27") describe the embodiment they
# INTRODUCE, i.e. the one whose tables follow, so they may only be searched in
# the span BEFORE the surface block -- mixing the two would let embodiment
# i+1's narrative leak into embodiment i's metadata.
_SUNNY_TABLE_META_PATTERNS: dict[str, tuple[str, ...]] = {
    "efl": (rf"(?<![A-Za-z0-9/])f\s*\(mm\)\s*(?P<value>{NUMBER_PATTERN})",),
    "fno": (rf"f\s*/\s*EPD\s*=?\s*(?P<value>{NUMBER_PATTERN})",),
    "hfov": (
        rf"Semi-FOV\s*{_SUNNY_DEG_PAREN}\s*(?P<value>{NUMBER_PATTERN})",
        rf"HFOV\s*{_SUNNY_DEG_PAREN}\s*(?P<value>{NUMBER_PATTERN})",
    ),
    "epd": (rf"EPD\s*\(mm\)\s*(?P<value>{NUMBER_PATTERN})",),
}
_SUNNY_NARRATIVE_META_PATTERNS: dict[str, tuple[str, ...]] = {
    "efl": (
        r"total effective focal length[^.;=]{0,90}?(?:=|\bis\b)\s*(?:about\s+)?"
        rf"(?P<value>{NUMBER_PATTERN})\s*mm",
        # "satisfies f=4.26 mm" -- the lookbehind rejects ratio forms like
        # "R2/f=0.85" and per-element "f1=", and the mm suffix is mandatory.
        rf"(?<![A-Za-z0-9/])f\s*=\s*(?P<value>{NUMBER_PATTERN})\s*mm",
    ),
    "fno": (
        rf"f\s*/\s*EPD\s*=\s*(?P<value>{NUMBER_PATTERN})",
        rf"\bFno\s*=\s*(?P<value>{NUMBER_PATTERN})",
        rf"\bFno\b[^.;=]{{0,90}}?\bis:?\s+(?:about\s+)?(?P<value>{NUMBER_PATTERN})",
    ),
    "hfov": (
        rf"Semi-FOV\s*=\s*(?P<value>{NUMBER_PATTERN})",
        rf"HFOV\s*=\s*(?P<value>{NUMBER_PATTERN})",
        rf"Semi-FOV\b[^.;=]{{0,90}}?\bis\s+(?:about\s+)?(?P<value>{NUMBER_PATTERN})",
    ),
    "epd": (),
}
# Columnar per-embodiment variant: "parameter f f1 ... ImgH HFOV (mm) ... (°)
# numerical value 1.38 -2.47 ... 80.1" -- header labels map positionally onto
# the value row (unit tokens are skipped).
_SUNNY_COLUMNAR_META_RE = re.compile(
    rf"\bparameter\s+(?P<header>(?:\S+\s+)+?)numerical\s+value\s+"
    rf"(?P<values>(?:{NUMBER_PATTERN}\s*)+)",
    flags=re.IGNORECASE,
)


def _sunny_columnar_meta(span_text: str) -> _SunnyMeta:
    match = _SUNNY_COLUMNAR_META_RE.search(span_text)
    if match is None:
        return _SunnyMeta()
    labels = [
        token
        for token in match.group("header").split()
        if not token.startswith("(") and not token.endswith(")")
    ]
    values = [
        _parse_number(token)
        for token in match.group("values").split()
        if re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE)
    ]
    if len(labels) != len(values):
        return _SunnyMeta()
    by_label = {label.upper(): value for label, value in zip(labels, values, strict=True)}
    return _SunnyMeta(
        focal_length_mm=by_label.get("F"),
        f_number=by_label.get("FNO") or by_label.get("F/EPD"),
        hfov_deg=by_label.get("HFOV") or by_label.get("SEMI-FOV"),
        epd_mm=by_label.get("EPD"),
    )


def _sunny_meta_from_span(text: str, patterns: dict[str, tuple[str, ...]]) -> _SunnyMeta:
    found: dict[str, float | None] = {"efl": None, "fno": None, "hfov": None, "epd": None}
    for meta_field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match is not None:
                found[meta_field] = _parse_number(match.group("value"))
                break
    return _SunnyMeta(
        focal_length_mm=found["efl"],
        f_number=found["fno"],
        hfov_deg=found["hfov"],
        epd_mm=found["epd"],
    )


_SUNNY_CONSOLIDATED_LABELS: dict[str, tuple[str, ...]] = {
    "efl": (r"(?<![A-Za-z0-9/])f\s*\(mm\)",),
    "fno": (r"f\s*/\s*EPD", r"\bFno\b"),
    "hfov": (
        rf"Semi-FOV\s*{_SUNNY_DEG_PAREN}",
        rf"HFOV\s*{_SUNNY_DEG_PAREN}",
    ),
    "epd": (r"\bEPD\s*\(mm\)",),
}


_SUNNY_GROUP_FNO_LABELS = (r"(?<![A-Za-z0-9/])f\s*/\s*EPD(?!\s*\()",)
_SUNNY_GROUP_FULL_FOV_LABELS = (r"(?<![-A-Za-z])FOV\s*(?:\([^)]*\))?",)


def _sunny_group_row_values(
    blocks: list[_PatentTableBlock],
    *,
    label_patterns: tuple[str, ...],
    embodiment_count: int,
    reject_compound_fno: bool = False,
    reject_operator_prefix: bool = False,
) -> list[float] | None:
    """Return one unambiguous, complete per-embodiment row.

    Sunny changes the order of words such as ``Example``, ``Embodiment``,
    ``Condition``, and ``Expression`` across related filings.  The stable
    structure is the exact row label followed by one published value per
    disclosed surface table.  Requiring exact cardinality avoids treating a
    bound, a per-example scalar, or an unrelated conditional row as metadata.
    """

    candidates: set[tuple[float, ...]] = set()
    for block in blocks:
        body = _cut_sunny_table_narrative(block.text)
        for label_pattern in label_patterns:
            for match in re.finditer(
                rf"{label_pattern}\s+((?:{NUMBER_PATTERN}\s*)+)",
                body,
                flags=re.IGNORECASE,
            ):
                prefix = body[max(0, match.start() - 32) : match.start()]
                if reject_operator_prefix and re.search(r"[×*]\s*$", prefix) is not None:
                    # A row such as ``tan(FOV/2) × f(mm)`` publishes a
                    # compound condition, not the effective focal length.
                    continue
                if (
                    reject_compound_fno
                    and re.search(
                        r"(?:ImgH|TTL|TL|DT\w*)\s*[×*]\s*$",
                        prefix,
                        flags=re.IGNORECASE,
                    )
                    is not None
                ):
                    # ``ImgH × f/EPD (mm)`` is a dimensional condition,
                    # not the working F-number row.
                    continue
                values = tuple(
                    _parse_number(token)
                    for token in match.group(1).split()
                    if re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE)
                )
                if len(values) == embodiment_count:
                    candidates.add(values)
                elif len(values) == embodiment_count * 2 and all(
                    values[index] == values[index + 1] for index in range(0, len(values), 2)
                ):
                    # Some multi-state Sunny tables publish two adjacent
                    # state columns for each surface prescription.  Collapse
                    # only when every published pair is exactly identical;
                    # differing states require a dedicated parser family.
                    candidates.add(values[::2])
    if len(candidates) != 1:
        return None
    return list(next(iter(candidates)))


def _sunny_fov_is_full_angle(document_text: str) -> bool:
    full_field = r"(?:maximum|maximal|full)\s+(?:diagonal\s+)?field[- ]of[- ]view"
    patterns = (
        rf"{full_field}\s+FOV\b",
        rf"\bFOV\b\s+(?:is|represents|denotes)\s+(?:a\s+|the\s+)?{full_field}",
    )
    return any(re.search(pattern, document_text, flags=re.IGNORECASE) for pattern in patterns)


def _sunny_consolidated_meta_rows(
    blocks: list[_PatentTableBlock],
    *,
    embodiment_count: int,
    document_text: str,
) -> dict[str, list[float]]:
    """Collect exact, cardinality-bound per-embodiment Sunny metadata rows."""

    rows: dict[str, list[float]] = {}
    for meta_field, label_patterns in _SUNNY_CONSOLIDATED_LABELS.items():
        values = _sunny_group_row_values(
            blocks,
            label_patterns=label_patterns,
            embodiment_count=embodiment_count,
            reject_operator_prefix=meta_field == "efl",
        )
        if values is not None:
            rows[meta_field] = values

    f_numbers = _sunny_group_row_values(
        blocks,
        label_patterns=_SUNNY_GROUP_FNO_LABELS,
        embodiment_count=embodiment_count,
        reject_compound_fno=True,
    )
    if f_numbers is not None:
        rows["fno"] = f_numbers

    if "hfov" not in rows and _sunny_fov_is_full_angle(document_text):
        full_fovs = _sunny_group_row_values(
            blocks,
            label_patterns=_SUNNY_GROUP_FULL_FOV_LABELS,
            embodiment_count=embodiment_count,
        )
        if full_fovs is not None and all(0.0 < value < 180.0 for value in full_fovs):
            # PatentPrescription stores half field angle.  The document must
            # explicitly define FOV as the maximum/full field before this
            # deterministic unit transform is allowed.
            rows["hfov"] = [value / 2.0 for value in full_fovs]
    return rows


_SUNNY_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
)


_SUNNY_ANY_TAGGED_ANCHOR_RE = re.compile(
    r"\bIn\s+(?:the\s+)?(?:example|embodiment)\s+(?P<num>\d+)\s*,"
    r"|\bIn\s+the\s+(?P<numth>\d+)(?:st|nd|rd|th)\s+(?:embodiment|example)\s*,"
    r"|\bIn\s+(?:the\s+)?(?P<word>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth"
    r"|tenth|eleventh|twelfth)\s+(?:embodiment|example)\s*,",
    flags=re.IGNORECASE,
)


def _sunny_tagged_anchor_number(match: re.Match[str]) -> int | None:
    if match.group("num") is not None:
        return int(match.group("num"))
    if match.group("numth") is not None:
        return int(match.group("numth"))
    word = match.group("word")
    if word is not None:
        return _SUNNY_ORDINALS.index(word.lower()) + 1
    return None


def _sunny_anchored_narrative_windows(
    text: str,
    span: tuple[int, int],
    embodiment_number: int,
) -> list[str]:
    """Bounded windows after 'In Example N,' / 'In the Nth embodiment,' anchors.

    Sunny summary sentences ("In Example 1, a total effective focal length f
    ... is 6.52 mm, ... Fno ... is 2.27") can sit AFTER the embodiment's
    surface table or BEFORE it as a section intro, so tagged anchors are
    searched over the whole document -- the embodiment tag itself guarantees
    correct binding (an untagged span search produced an off-by-one value
    assignment during the DATA-10b backtest). The trailing comma excludes
    cross-references like "as in example 1.". The untagged self-referential
    form ("In this example, ...") is only trusted inside this embodiment's own
    table span, clamped at the first tagged anchor so a following embodiment's
    intro can never leak in.
    """

    ordinal = (
        _SUNNY_ORDINALS[embodiment_number - 1]
        if embodiment_number <= len(_SUNNY_ORDINALS)
        else None
    )
    tagged_patterns = [
        rf"\bIn\s+(?:the\s+)?example\s+{embodiment_number}\s*,",
        rf"\bIn\s+(?:the\s+)?embodiment\s+{embodiment_number}\s*,",
        rf"\bIn\s+the\s+{embodiment_number}(?:st|nd|rd|th)\s+(?:embodiment|example)\s*,",
    ]
    if ordinal is not None:
        tagged_patterns.append(rf"\bIn\s+(?:the\s+)?{ordinal}\s+(?:embodiment|example)\s*,")
    windows: list[str] = []
    for pattern in tagged_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            windows.append(text[match.end() : match.end() + 1200])

    span_text = text[span[0] : span[1]]
    # Clamp the self-referential search at the first tagged anchor belonging
    # to a DIFFERENT embodiment (same-numbered tagged sentences, e.g. the
    # "In example 2, the ... surfaces are aspheric" geometry note, are fine).
    self_ref_region = span_text
    for match in _SUNNY_ANY_TAGGED_ANCHOR_RE.finditer(span_text):
        number = _sunny_tagged_anchor_number(match)
        if number is not None and number != embodiment_number:
            self_ref_region = span_text[: match.start()]
            break
    for match in re.finditer(
        r"\bIn\s+this\s+(?:example|embodiment)\s*,", self_ref_region, flags=re.IGNORECASE
    ):
        windows.append(self_ref_region[match.end() : match.end() + 1200])
    # Lowest-priority fallback: the whole clamped span. Some Sunny sections
    # end with an unanchored summary ("... and f=6.06 mm; HFOV=20.5deg; TTL=
    # 5.68 mm; Fno is: 2.63.") before the next example's tagged intro; the
    # different-embodiment clamp above already guarantees the span contains
    # only THIS embodiment's tables and trailing narrative.
    windows.append(self_ref_region)
    return windows


def _sunny_meta_for_embodiment(
    text: str,
    *,
    embodiment_number: int,
    table_span: tuple[int, int],
    consolidated: dict[str, list[float]],
) -> tuple[float, float, float]:
    table_text = _cut_sunny_conditional_tail(text[table_span[0] : table_span[1]])
    meta = _sunny_meta_from_span(table_text, _SUNNY_TABLE_META_PATTERNS)
    meta = meta.merged_with(_sunny_columnar_meta(table_text))
    for window in _sunny_anchored_narrative_windows(text, table_span, embodiment_number):
        meta = meta.merged_with(
            _sunny_meta_from_span(
                _cut_sunny_conditional_tail(window), _SUNNY_NARRATIVE_META_PATTERNS
            )
        )

    def _consolidated_value(field: str) -> float | None:
        values = consolidated.get(field)
        if values is not None and len(values) >= embodiment_number:
            return values[embodiment_number - 1]
        return None

    efl = meta.focal_length_mm if meta.focal_length_mm is not None else _consolidated_value("efl")
    fno = meta.f_number if meta.f_number is not None else _consolidated_value("fno")
    hfov = meta.hfov_deg if meta.hfov_deg is not None else _consolidated_value("hfov")
    epd = meta.epd_mm if meta.epd_mm is not None else _consolidated_value("epd")
    if fno is None and efl is not None and epd is not None and epd > 0.0:
        # f/EPD is the definition of the working F-number; both operands are
        # published numbers, so this is a deterministic transform, not a fill.
        fno = efl / epd
    missing = [
        name for name, value in (("f", efl), ("Fno", fno), ("Semi-FOV", hfov)) if value is None
    ]
    if missing:
        raise PatentParseError(
            f"Sunny embodiment {embodiment_number} metadata missing: {', '.join(missing)}"
        )
    return efl, fno, hfov


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


def load_patent_pool(
    pool_dir: Path,
    pattern: str = DEFAULT_POOL_GLOB,
    *,
    only_patents: frozenset[str] | set[str] | None = None,
) -> list[PatentCandidate]:
    """Load de-duplicated USPTO patent candidates from local JSONL pool files."""

    candidates: list[PatentCandidate] = []
    seen: set[str] = set()
    normalized_only = (
        {_normalized_patent_id(patent_id) for patent_id in only_patents}
        if only_patents is not None
        else None
    )
    for path in sorted(pool_dir.glob(pattern)):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                patent_id = str(record.get("id") or "").strip()
                normalized = _normalized_patent_id(patent_id)
                if (
                    not patent_id
                    or normalized in seen
                    or (normalized_only is not None and normalized not in normalized_only)
                ):
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
    only_patents: frozenset[str] | set[str] | None = None,
    raw_document_dir: Path = DEFAULT_RAW_DOCUMENT_DIR,
    attempts_dir: Path = DEFAULT_ATTEMPTS_DIR,
    conversion_timeout_seconds: float = DEFAULT_CONVERSION_TIMEOUT_SECONDS,
) -> list[ConversionAttempt]:
    """Fetch USPTO HTML, parse prescriptions, write ZMX files, and report attempts."""

    candidates = load_patent_pool(pool_dir, only_patents=only_patents)
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
                raw_document_dir=raw_document_dir,
                attempts_dir=attempts_dir,
                conversion_timeout_seconds=conversion_timeout_seconds,
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
    raw_document_dir: Path | None = None,
    attempts_dir: Path | None = None,
    conversion_timeout_seconds: float = DEFAULT_CONVERSION_TIMEOUT_SECONDS,
    patent_budget_seconds: float | None = None,
) -> list[ConversionAttempt]:
    started_at = time.monotonic()
    if patent_budget_seconds is not None and patent_budget_seconds <= 0:
        raise ValueError("patent_budget_seconds must be positive")
    raw_document_dir = raw_document_dir or output_dir / ".raw-html"
    attempts_dir = attempts_dir or output_dir / ".attempts"
    source_document: SourceDocumentEvidence | None = None
    fetched: FetchedPatentHtml | None = None
    try:
        fetched = await _fetch_patent_html(client, token, candidate.patent_id)
        if isinstance(fetched, str):
            fetched = FetchedPatentHtml(
                html=fetched,
                source_bucket="injected-fixture",
                attempts=(
                    SourceFetchAttempt(
                        publication_id=candidate.patent_id,
                        source_bucket="injected-fixture",
                        state=SourceFetchState.RETAINED,
                        http_status=200,
                    ),
                ),
            )
        source_document = _retain_fetched_patent_html(
            raw_document_dir,
            patent_id=candidate.patent_id,
            fetched=fetched,
        )
        parse_attempts = _parse_prescription_attempts(
            fetched.html,
            patent_id=candidate.patent_id,
        )
    except Exception as exc:  # noqa: BLE001 - report per-patent failure reason
        source_attempts = (
            exc.attempts
            if isinstance(exc, PatentFulltextFetchError)
            else (fetched.attempts if fetched is not None else ())
        )
        return [
            ConversionAttempt(
                patent_id=candidate.patent_id,
                title=candidate.title,
                status="failed",
                reason=f"{type(exc).__name__}: {exc}",
                raw_document_path=(
                    source_document.retained_path if source_document is not None else ""
                ),
                raw_document_sha256=(source_document.sha256 if source_document is not None else ""),
                source_attempts=source_attempts,
            )
        ]

    assert source_document is not None
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
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
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
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
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
                            f"duplicate_prescription: {DUPLICATE_PRESCRIPTION_DETAIL} {fingerprint}"
                        ),
                        raw_document_path=source_document.retained_path,
                        raw_document_sha256=source_document.sha256,
                        source_bucket=fetched.source_bucket,
                        source_attempts=fetched.attempts,
                        embodiment_number=parse_attempt.embodiment_number,
                        prescription_fingerprint=fingerprint,
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
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
                    prescription_fingerprint=fingerprint,
                    embodiment=prescription.embodiment,
                )
            )
            continue
        output_path = output_dir / (
            f"{_safe_stem(candidate.patent_id)}-e{parse_attempt.embodiment_number}.zmx"
        )
        worker_timeout_seconds = conversion_timeout_seconds
        if patent_budget_seconds is not None:
            remaining_seconds = patent_budget_seconds - (time.monotonic() - started_at)
            if remaining_seconds <= 0:
                attempts.append(
                    ConversionAttempt(
                        patent_id=candidate.patent_id,
                        title=candidate.title,
                        status="conversion_retry_required",
                        reason="patent conversion budget exhausted before worker launch",
                        reason_code="conversion_retry_required.patent_budget_exhausted",
                        raw_document_path=source_document.retained_path,
                        raw_document_sha256=source_document.sha256,
                        source_bucket=fetched.source_bucket,
                        source_attempts=fetched.attempts,
                        embodiment_number=parse_attempt.embodiment_number,
                        prescription_fingerprint=fingerprint,
                        embodiment=prescription.embodiment,
                        coverage=_coverage(prescription),
                    )
                )
                continue
            worker_timeout_seconds = min(worker_timeout_seconds, remaining_seconds)
        try:
            request = _conversion_request(prescription, source_document)
        except Exception as exc:  # noqa: BLE001 - preserve and continue later embodiments.
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="failed",
                    reason=f"ConversionInputError: {type(exc).__name__}: {exc}",
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
                    prescription_fingerprint=fingerprint,
                    embodiment=prescription.embodiment,
                    coverage=_coverage(prescription),
                )
            )
            continue
        try:
            receipt = await asyncio.to_thread(
                run_patent_conversion_attempt,
                request,
                published_zmx_path=output_path,
                attempts_root=attempts_dir,
                repo_root=ROOT,
                timeout_seconds=worker_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - keep processing later embodiments.
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="trace_failed",
                    reason=f"trace_failed.executor_exception: {type(exc).__name__}: {exc}",
                    reason_code="trace_failed.executor_exception",
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
                    prescription_fingerprint=fingerprint,
                    embodiment=prescription.embodiment,
                    coverage=_coverage(prescription),
                )
            )
            continue
        if receipt.status == "success":
            response = receipt.worker_response
            if response is None or response.efl_mm is None or response.trace_audit is None:
                attempts.append(
                    ConversionAttempt(
                        patent_id=candidate.patent_id,
                        title=candidate.title,
                        status="trace_failed",
                        reason="trace_failed.receipt_invalid: success omitted worker measurements",
                        reason_code="trace_failed.receipt_invalid",
                        attempt_id=receipt.attempt_id,
                        request_sha256=receipt.request_sha256,
                        receipt_path=receipt.receipt_path,
                        raw_document_path=source_document.retained_path,
                        raw_document_sha256=source_document.sha256,
                        source_bucket=fetched.source_bucket,
                        source_attempts=fetched.attempts,
                        embodiment_number=parse_attempt.embodiment_number,
                        prescription_fingerprint=fingerprint,
                        embodiment=prescription.embodiment,
                        coverage=_coverage(prescription),
                    )
                )
                continue
            trace_audit = _trace_audit_from_worker(response.trace_audit)
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status="success",
                    reason="parsed and process-isolated ingestion succeeded",
                    reason_code=receipt.reason_code,
                    attempt_id=receipt.attempt_id,
                    request_sha256=receipt.request_sha256,
                    receipt_path=receipt.receipt_path,
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
                    prescription_fingerprint=fingerprint,
                    embodiment=prescription.embodiment,
                    zmx_path=_display_path(output_path),
                    efl_mm=response.efl_mm,
                    real_image_height_mm=trace_audit.real_image_height_mm,
                    sanity_image_height_mm=trace_audit.sanity_image_height_mm,
                    coverage=_coverage(prescription, trace_audit=trace_audit),
                )
            )
        else:
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status=receipt.status,
                    reason=f"{receipt.reason_code}: {receipt.detail}",
                    reason_code=receipt.reason_code,
                    attempt_id=receipt.attempt_id,
                    request_sha256=receipt.request_sha256,
                    receipt_path=receipt.receipt_path,
                    raw_document_path=source_document.retained_path,
                    raw_document_sha256=source_document.sha256,
                    source_bucket=fetched.source_bucket,
                    source_attempts=fetched.attempts,
                    embodiment_number=parse_attempt.embodiment_number,
                    prescription_fingerprint=fingerprint,
                    embodiment=prescription.embodiment,
                    coverage=_coverage(prescription),
                )
            )
    return attempts


async def _fetch_patent_html(
    client: httpx.AsyncClient,
    token: str,
    patent_id: str,
) -> FetchedPatentHtml:
    sources = [_source_for_patent_id(patent_id), "USPAT", "US-PGPUB", "USOCR"]
    seen: set[str] = set()
    attempts: list[SourceFetchAttempt] = []
    for source in sources:
        if source in seen:
            continue
        seen.add(source)
        try:
            page_html = await _ppubs_patent_html(client, token, patent_id, source)
            attempts.append(
                SourceFetchAttempt(
                    publication_id=patent_id,
                    source_bucket=source,
                    state=SourceFetchState.RETAINED,
                    http_status=200,
                )
            )
            return FetchedPatentHtml(
                html=page_html,
                source_bucket=source,
                attempts=tuple(attempts),
            )
        except httpx.HTTPStatusError as exc:
            attempts.append(
                SourceFetchAttempt(
                    publication_id=patent_id,
                    source_bucket=source,
                    state=SourceFetchState.HTTP_ERROR,
                    http_status=exc.response.status_code,
                    exception_type=type(exc).__name__,
                )
            )
        except httpx.RequestError as exc:
            attempts.append(
                SourceFetchAttempt(
                    publication_id=patent_id,
                    source_bucket=source,
                    state=SourceFetchState.TRANSPORT_ERROR,
                    exception_type=type(exc).__name__,
                )
            )
        except Exception as exc:  # noqa: BLE001 - try alternate PPUBS source buckets
            attempts.append(
                SourceFetchAttempt(
                    publication_id=patent_id,
                    source_bucket=source,
                    state=SourceFetchState.TRANSPORT_ERROR,
                    exception_type=type(exc).__name__,
                )
            )
    raise PatentFulltextFetchError(tuple(attempts))


def _retain_fetched_patent_html(
    raw_document_dir: Path,
    *,
    patent_id: str,
    fetched: FetchedPatentHtml,
) -> SourceDocumentEvidence:
    """Retain exactly the decoded HTML text supplied to the deterministic parser."""

    content = fetched.html.encode("utf-8")
    digest = sha256_bytes(content)
    source_stem = _safe_stem(fetched.source_bucket)
    path = raw_document_dir / source_stem / digest[:16] / f"{_safe_stem(patent_id)}.html"
    if path.exists():
        if path.read_bytes() != content:
            raise PatentParseError(f"raw document hash-path collision: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_bytes(content)
        temp_path.replace(path)
    return SourceDocumentEvidence(
        source_bucket=fetched.source_bucket,
        retained_path=Path(_display_path(path)).as_posix(),
        sha256=digest,
    )


def _conversion_request(
    prescription: PatentPrescription,
    source_document: SourceDocumentEvidence,
) -> PatentConversionRequest:
    return PatentConversionRequest(
        prescription=PatentPrescriptionInput(
            patent_id=prescription.patent_id,
            embodiment=prescription.embodiment,
            focal_length_mm=prescription.focal_length_mm,
            f_number=prescription.f_number,
            hfov_deg=prescription.hfov_deg,
            surfaces=tuple(
                PatentSurfaceInput(
                    index=surface.index,
                    label=surface.label,
                    radius_mm=_request_radius_mm(surface.radius_mm),
                    thickness_mm=surface.thickness_mm,
                    material=surface.material,
                    nd=surface.nd,
                    vd=surface.vd,
                    surface_type=surface.surface_type,
                    asphere_coefficients=dict(surface.asphere_coefficients),
                )
                for surface in prescription.surfaces
            ),
            unsupported_asphere_terms=tuple(prescription.unsupported_asphere_terms),
        ),
        source_document=source_document,
    )


def _request_radius_mm(value: float | None) -> float | None:
    """Encode an explicitly infinite/plano radius in the finite JSON DTO."""

    if value is not None and math.isinf(value):
        return 0.0
    return value


def _trace_audit_from_worker(result: TraceAuditResult) -> TraceApertureAudit:
    return TraceApertureAudit(
        semi_diameters_mm=dict(result.semi_diameters_mm),
        real_image_height_mm=result.real_image_height_mm,
        sanity_image_height_mm=result.sanity_image_height_mm,
        measured_surfaces=result.measured_surfaces,
        interpolated_surfaces=result.interpolated_surfaces,
        finite_final_rays=result.finite_final_rays,
        total_rays=result.total_rays,
    )


_PRIMARY_SURFACE_ZERO_RE = re.compile(
    r"\b0\s+(?:Object\b|Outer-Side\b|m-side\b)",
    flags=re.IGNORECASE,
)


def _find_embodiment_metas(text: str) -> list[_EmbodimentMeta]:
    label_pattern = re.compile(
        r"(?P<embodiment>"
        r"\d+(?:st|nd|rd|th)\s+Embodiment|"
        r"Embodiment\s+\d+|"
        r"(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\s+"
        r"Embodiment|"
        r"(?:Working\s+)?Example(?:\s+No\.?)?\s+\d+|"
        r"Optical\s+data\s+of\s+this\s+preferred\s+embodiment"
        r")",
        flags=re.IGNORECASE,
    )
    label_matches = list(label_pattern.finditer(text))
    metas: list[_EmbodimentMeta] = []
    for index, match in enumerate(label_matches):
        next_start = (
            label_matches[index + 1].start() if index + 1 < len(label_matches) else len(text)
        )
        window = text[match.start() : min(next_start, match.start() + 900)]
        surface_start = _PRIMARY_SURFACE_ZERO_RE.search(window)
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
                # f/HEP (Ability Opto: focal length over entrance pupil) must
                # precede the generic F/ alternative so the specific label wins.
                r"F\s*/\s*HEP|F\s*no\.?|FNO|F-number|F\s*number|F\s*/\s*#?|F/#|F\s*#",
                "F number",
            )
            hfov, hfov_end = _extract_meta_number(
                meta_window,
                r"HFOV|Half\s+FOV|Half\s+Field\s+of\s+View|"
                r"Half\s+Angle\s+of\s+View|Half\s+View\s+Angle|Semi\s+Field\s+Angle|"
                r"HAF",
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
    start_match = _PRIMARY_SURFACE_ZERO_RE.search(table_region)
    if start_match is None:
        raise PatentParseError("surface table did not contain a supported surface 0 row")
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
    # Ability Opto rows label lenses with PPUBS ordinal markup ("1.sup.st lens",
    # "3 .sup.rd lens"). Rewrite to the primary parser's "Lens N" convention.
    table_region = re.sub(
        r"\b(\d+)\s*\.\s*sup\s*\.\s*(?:st|nd|rd|th)\s+lens\b",
        r"Lens \1",
        table_region,
        flags=re.IGNORECASE,
    )
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
            if surfaces and "IMAGE" in surfaces[-1].label.upper():
                # Ability Opto image rows carry trailing residue ("Image plane
                # 1E+18 0") whose final token would otherwise read as a bogus
                # surface index. Once the image surface is parsed the
                # prescription is complete; stop instead of failing.
                break
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
        if pos < len(tokens) and (
            _material_token(tokens[pos]) or _named_glass_with_indices(tokens, pos)
        ):
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
    # Primary tables head each block "Surface # 1 2 3"; Ability Opto omits the
    # "#" ("Surface 1 2 4 5 6"). Capital-S with a following digit keeps the
    # narrative "surface 0 - 10 indicates ..." from splitting a junk block.
    blocks = re.split(r"\bSurface\s+#\s+|\bSurface\s+(?=\d)", coeff_text)[1:]
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
                    value, pos = _consume_coefficient_number(tokens, pos)
                    coefficients.setdefault(surface_id, {})["K"] = value or 0.0
                _reject_row_value_overflow(tokens, pos, label="K")
                continue
            order_match = re.fullmatch(r"A(\d+)", label.rstrip("="))
            if order_match is None:
                continue
            order = int(order_match.group(1))
            values: list[float] = []
            for _surface_id in surface_ids:
                value, pos = _consume_coefficient_number(tokens, pos)
                values.append(value or 0.0)
            _reject_row_value_overflow(tokens, pos, label=f"A{order}")
            if order in SUPPORTED_ASPHERE_ORDERS:
                codev_label = ASPHERE_ORDER_TO_CODEV[order]
                for surface_id, value in zip(surface_ids, values, strict=True):
                    coefficients.setdefault(surface_id, {})[codev_label] = value
            else:
                for surface_id, value in zip(surface_ids, values, strict=True):
                    if abs(value) > 0.0:
                        unsupported.append(f"S{surface_id}:A{order}={value:.3g}")
    return coefficients, unsupported


_CORRUPT_EXPONENT_RE = re.compile(r"^[A-Za-z]*E[-+]\d+$")


def _consume_coefficient_number(tokens: list[str], pos: int) -> tuple[float | None, int]:
    """Consume one coefficient value, failing loud on OCR-corrupted exponents.

    PPUBS OCR occasionally splits "1.88094E-05" into "1.88094 IE-05". The old
    permissive consume would keep the mantissa as the coefficient (a ~1e5x
    error) and silently zero-fill the rest of the row. Any bare exponent
    fragment is proof the row is corrupt, so the embodiment must fail rather
    than ingest invented numbers.
    """

    value, new_pos = _consume_optional_number(tokens, pos)
    if new_pos < len(tokens) and _CORRUPT_EXPONENT_RE.fullmatch(tokens[new_pos]):
        raise PatentParseError(
            f"OCR-corrupted exponent token in aspheric table: {tokens[new_pos]!r}"
        )
    return value, new_pos


def _reject_row_value_overflow(tokens: list[str], pos: int, *, label: str) -> None:
    """Fail loud when a coefficient row has more numeric values than surfaces.

    Overflow means a value was split ("−1.5703 51E+00") or a column slipped,
    so every assignment in the row is suspect -- misalignment must never be
    ingested silently.
    """

    if pos >= len(tokens):
        return
    token = tokens[pos]
    if re.fullmatch(r"A\d+=?|K=?", token, flags=re.IGNORECASE):
        return
    # Raw-token match only: paren/bracket-wrapped paragraph markers like
    # "(65)" must not count as row values (paren-stripping _parse_number
    # would accept them).
    if not re.fullmatch(NUMBER_PATTERN, token, flags=re.IGNORECASE):
        return
    raise PatentParseError(
        f"aspheric row {label} has more numeric values than surfaces: extra {token!r}"
    )


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
    if upper == "OUTER-SIDE":
        return "Object", pos + 1
    if upper == "M-SIDE":
        next_pos = pos + 1
        if next_pos < len(tokens) and tokens[next_pos].upper() == "SURFACE":
            next_pos += 1
        return "Object", next_pos
    if upper == "INNER-SIDE":
        return "Image", pos + 1
    if upper == "RCS":
        return "Image", pos + 1
    if upper == "IR-FILTER":
        return "IR-filter", pos + 1
    if upper == "LENS" and pos + 1 < len(tokens):
        return f"Lens {tokens[pos + 1]}", pos + 2
    if upper in {"APE.", "APE"} and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "STOP":
        return "Ape. Stop", pos + 2
    if upper in {"APE.", "APE"}:
        return "Ape.", pos + 1
    if upper == "APERTURE":
        # Ability Opto: "Aperture plane -0.412" -- the stop row with a plano
        # radius column ("plane") and its thickness.
        return "Ape. Stop", pos + 1
    if upper == "INFRARED" and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "RAYS":
        return "IR-cut filter", pos + 2
    if upper == "INFRARED":
        return "IR-cut filter", pos + 1
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
    if upper in {"PLANO", "PIANO", "PLANE"}:
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
    glass_rows = [
        surface for surface in surfaces if surface.nd is not None and surface.vd is not None
    ]
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
        "| patent | embodiment | status | reason_code | attempt_id | raw_document | raw_sha256 | receipt | zmx | efl_mm | real_imh_mm | f_tan_sanity_mm | field coverage | reason |",
        "|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|",
    ]
    for attempt in attempts:
        coverage = _format_coverage(attempt.coverage)
        efl = "" if attempt.efl_mm is None else f"{attempt.efl_mm:.6g}"
        real_imh = (
            "" if attempt.real_image_height_mm is None else f"{attempt.real_image_height_mm:.6g}"
        )
        sanity_imh = (
            ""
            if attempt.sanity_image_height_mm is None
            else f"{attempt.sanity_image_height_mm:.6g}"
        )
        lines.append(
            "| "
            + " | ".join(
                (
                    _md_cell(attempt.patent_id),
                    _md_cell(attempt.embodiment),
                    attempt.status,
                    _md_cell(attempt.reason_code),
                    _md_cell(attempt.attempt_id),
                    _md_cell(attempt.raw_document_path),
                    _md_cell(attempt.raw_document_sha256),
                    _md_cell(attempt.receipt_path),
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
        if attempt.reason_code:
            counts[attempt.reason_code] += 1
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
        try:
            trace_audit = _trace_surface_apertures(temp_path, prescription)
        except Exception as exc:
            raise PatentTraceError(f"{type(exc).__name__}: {exc}") from exc
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
        if any(
            abs(surface.asphere_coefficients.get(label, 0.0)) > 0.0 for label in XASPHERE_HIGH_TERMS
        ):
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
        rewritten.extend(_xasphere_surface_block(block, xasphere_coefficients[surface_index]))
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
        '  XDAT 1 10 0 0 1 0 0 ""',
        '  XDAT 2 1 0 0 1 0 0 ""',
        '  XDAT 3 0 0 0 1 0 0 ""',
    ]
    for xdat_index, label in enumerate(XASPHERE_WRITABLE_TERMS, start=4):
        value = coefficients.get(label, 0.0)
        lines.append(f'  XDAT {xdat_index} {_fmt_zmx_number(value)} 0 0 1 0 0 ""')
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
        index for index, sample in enumerate(samples) if math.isclose(sample[1], 1.0, abs_tol=1e-12)
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
        lower = max(
            (candidate for candidate in measured_indices if candidate < index), default=None
        )
        upper = min(
            (candidate for candidate in measured_indices if candidate > index), default=None
        )
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


def _find_required_before_any(
    text: str,
    needles: tuple[str, ...],
    start: int,
    end: int,
) -> int:
    """Return the earliest occurrence of any needle in [start, end)."""

    hits = [
        index for needle in needles if (index := text.lower().find(needle.lower(), start, end)) >= 0
    ]
    if not hits:
        raise PatentParseError(f"{needles[0]!r} section not found in embodiment")
    return min(hits)


def _material_token(token: str) -> bool:
    return _strip_parens(token).upper() in MATERIAL_TOKENS


def _named_glass_with_indices(tokens: list[str], pos: int) -> bool:
    """True when a named-glass token (e.g. Ability Opto "BK7_SCH") is directly
    followed by a physically plausible nd/vd pair.

    Deterministic: requires BOTH follower tokens to parse and land inside the
    nd [1.3, 2.2] / vd [10, 100] physical windows, so an arbitrary word is
    never mistaken for a material without real refractive data behind it.
    """

    token = _strip_parens(tokens[pos])
    if not token or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", token):
        return False
    if pos + 2 >= len(tokens):
        return False
    try:
        nd = _parse_number(tokens[pos + 1])
        vd = _parse_number(tokens[pos + 2])
    except PatentParseError:
        return False
    return _is_physical_nd(nd) and _is_physical_vd(vd)


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
        "--conversion-timeout-seconds",
        type=float,
        default=DEFAULT_CONVERSION_TIMEOUT_SECONDS,
        help="Hard wall-clock timeout for each isolated embodiment conversion.",
    )
    parser.add_argument(
        "--raw-document-dir",
        type=Path,
        default=DEFAULT_RAW_DOCUMENT_DIR,
        help="Content-addressed store for the exact HTML text supplied to parsers.",
    )
    parser.add_argument(
        "--attempts-dir",
        type=Path,
        default=DEFAULT_ATTEMPTS_DIR,
        help="Append-only process request/response/log/receipt evidence root.",
    )
    parser.add_argument(
        "--only-patents",
        type=Path,
        help="Text file containing one patent number per line; restrict mining to this set.",
    )
    parser.add_argument(
        "--case-index",
        type=Path,
        default=DEFAULT_CASE_INDEX_PATH,
        help="Formal case index used to skip already ingested patent embodiments.",
    )
    args = parser.parse_args()
    only_patents = None
    if args.only_patents is not None:
        only_patents = frozenset(
            line.strip()
            for line in args.only_patents.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    attempts = asyncio.run(
        run_conversion(
            pool_dir=args.pool_dir,
            output_dir=args.out_dir,
            report_path=args.report,
            target_successes=args.target_successes,
            max_attempts=args.max_attempts,
            case_index_path=args.case_index,
            only_patents=only_patents,
            raw_document_dir=args.raw_document_dir,
            attempts_dir=args.attempts_dir,
            conversion_timeout_seconds=args.conversion_timeout_seconds,
        )
    )
    successes = sum(attempt.status == "success" for attempt in attempts)
    return 0 if successes >= args.target_successes else 1


if __name__ == "__main__":
    sys.exit(main())
