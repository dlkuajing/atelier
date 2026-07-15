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
from scripts.patent_crawler import (  # noqa: E402
    _ppubs_access_token,
    _ppubs_patent_html,
    _ppubs_search_docs,
)
from scripts.patent_pdf_recovery import (  # noqa: E402
    PatentPdfCachedSources,
    PatentPdfOcrRecovery,
    PatentPdfRecoveryError,
    recover_ability_official_pdf_ocr,
)

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


class PatentTerminalParseError(PatentParseError):
    """A source-proven parse outcome that is terminal without ray tracing.

    This is deliberately narrower than a generic parser rejection.  Callers may
    use it only when the retained official source itself proves one of the
    saturation contract's terminal outcomes.
    """

    _ALLOWED_STATUSES = frozenset({"confirmed_no_prescription", "metadata_unpublished"})

    def __init__(self, *, status: str, reason_code: str, detail: str) -> None:
        if status not in self._ALLOWED_STATUSES:
            raise ValueError(f"unsupported source-proven terminal parse status: {status}")
        if not reason_code.startswith(f"{status}."):
            raise ValueError("terminal parse reason code must be namespaced by status")
        self.status = status
        self.reason_code = reason_code
        super().__init__(detail)


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


@dataclass(frozen=True)
class RecoveredPatentHtml:
    """Official same-application grant selected as a text parser input."""

    publication_id: str
    application_number: str
    fetched: FetchedPatentHtml
    primary_embedded_tiff_count: int
    primary_text_table_count: int
    recovered_text_table_count: int


@dataclass(frozen=True)
class RecoveredPriorPublicationPdf:
    """Official A-publication PDF linked from one same-application grant."""

    primary_publication_id: str
    source_publication_id: str
    application_number: str
    source_fetched: FetchedPatentHtml
    recovered: PatentPdfOcrRecovery


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
    parser_input_document_path: str = ""
    parser_input_document_sha256: str = ""
    parser_input_publication_id: str = ""
    parser_input_source_bucket: str = ""
    fulltext_recovery_manifest_path: str = ""
    fulltext_recovery_manifest_sha256: str = ""
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
    embodiment_number: int | None
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

    pdf_attempts = _parse_ability_pdf_ocr_attempts(raw_text, patent_id=patent_id)
    if pdf_attempts:
        return pdf_attempts
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
        attempts = _parse_kantatsu_five_lens_ih_first_table_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _parse_kantatsu_ih_first_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_kantatsu_missing_half_field_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_kantatsu_damaged_metadata_attempts(text, patent_id=patent_id)
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
        attempts = _parse_samsung_even_order_table_attempts(text, patent_id=patent_id)
        if attempts:
            return attempts
        attempts = _parse_samsung_eight_lens_missing_stop_attempts(
            text,
            patent_id=patent_id,
        )
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
        attempts = _classify_surface_texture_acquisition_only_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_lens_driving_mechanical_only_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_non_optical_zone_stray_light_only_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_ir_filter_coating_only_attempts(text, patent_id=patent_id)
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
_KANTATSU_FIVE_LENS_IH_FIRST_HEADER_PATTERN = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Example\s*(?P<example>\d+)\s+"
    rf"Unit\s+mm\s+f\s*=\s*(?P<f>{NUMBER_PATTERN})\s+"
    rf"i\s*h\s*=\s*(?P<ih>{NUMBER_PATTERN})\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"TTL\s*=\s*(?P<ttl>{NUMBER_PATTERN})\s+"
    rf"[^\s(=]+\s*\(\s*[^)]*\s*\)\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s+"
    r"Surface\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_FIVE_LENS_IH_FIRST_BINDING_PATTERN = re.compile(
    r"\bExample\s+(?P<example>\d+)\s+\(\d+\)\s+The\s+basic\s+lens\s+data\s+"
    r"is\s+shown\s+below\s+in\s+Table\s+(?P<table>\d+)\.\s+\(\d+\)\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<header_table>\d+)\s+"
    r"Example\s*(?P<header_example>\d+)\s+Unit\s+mm\b",
    flags=re.IGNORECASE,
)
_KANTATSU_FIVE_LENS_IH_FIRST_HALF_FIELD_DEFINITION = re.compile(
    r"\bIn\s+each\s+example,\s+f\s+denotes\s+the\s+focal\s+length\s+of\s+the\s+"
    r"overall\s+optical\s+system\s+of\s+the\s+imaging\s+lens,\s+Fno\s+denotes\s+"
    r"an\s+F-number,\s+\S+\s+denotes\s+a\s+half\s+field\s+of\s+view,\s+ih\s+"
    r"denotes\s+a\s+maximum\s+image\s+height,\s+and\s+TTL\s+denotes\s+a\s+"
    r"total\s+track\s+length\b",
    flags=re.IGNORECASE,
)
_KANTATSU_FIVE_LENS_IH_FIRST_ASPHERE_DEFINITION = re.compile(
    r"\bA4,\s+A6,\s+A8,\s+A10,\s+A12,\s+A14,\s+A16,\s+A18\s+and\s+A20\s+"
    r"denote\s+aspheric\s+surface\s+coefficients\b",
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
_KANTATSU_MISSING_HALF_FIELD_HEADER_PATTERN = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Example\s*(?P<example>\d+)\s+"
    rf"Unit\s+mm\s+f\s*=\s*(?P<f>{NUMBER_PATTERN})\s+"
    rf"Fno\s*=\s*(?P<fno>{NUMBER_PATTERN})\s+"
    rf"ih\s*=\s*(?P<ih>{NUMBER_PATTERN})\s+"
    rf"TTL\s*=\s*(?P<ttl>{NUMBER_PATTERN})\s+Surface\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_MISSING_HALF_FIELD_BINDING_PATTERN = re.compile(
    r"\bExample\s+(?P<example>\d+)\s+\[\d+\]\s+The\s+basic\s+lens\s+data\s+"
    r"is\s+shown\s+below\s+in\s+Table\s+(?P<table>\d+)\.\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<header_table>\d+)\s+"
    r"Example\s*(?P<header_example>\d+)\s+Unit\s+mm\b",
    flags=re.IGNORECASE,
)
_KANTATSU_MISSING_HALF_FIELD_DEFINITION = re.compile(
    r"\bIn\s+each\s+example,\s+f\s+denotes\s+the\s+focal\s+length\s+of\s+the\s+"
    r"overall\s+optical\s+system\s+of\s+the\s+imaging\s+lens,\s+Fno\s+denotes\s+"
    r"an\s+F-number,\s+\S+\s+denotes\s+a\s+half\s+field\s+of\s+view,\s+ih\s+"
    r"denotes\s+a\s+maximum\s+image\s+height,\s+and\s+TTL\s+denotes\s+a\s+"
    r"total\s+track\s+length\b",
    flags=re.IGNORECASE,
)
_KANTATSU_MISSING_HALF_FIELD_ASPHERE_DEFINITION = re.compile(
    r"\bA4,\s+A6,\s+A8,\s+A10,\s+A12,\s+A14,\s+A16,\s+A18\s+and\s+A20\s+"
    r"denote\s+aspheric\s+surface\s+coefficients\b",
    flags=re.IGNORECASE,
)
_KANTATSU_DAMAGED_METADATA_HEADER_PATTERN = re.compile(
    rf"\bTABLE\s+(?P<table>\d+)\s+Example\s+(?P<example>\d+)\s+"
    rf"Unit\s+mm\s+f\s*=\s*{NUMBER_PATTERN}\s+"
    rf"=\s*{NUMBER_PATTERN}\s+F\s*=\s*{NUMBER_PATTERN}\s+"
    rf"TTL\s*=\s*{NUMBER_PATTERN}\s+=\s*{NUMBER_PATTERN}\s+Surface\s+Data\b",
    flags=re.IGNORECASE,
)
_KANTATSU_DAMAGED_METADATA_BINDING_PATTERN = re.compile(
    r"\bExample\s+(?P<example>\d+)\s+\[\d+\]\s+The\s+basic\s+lens\s+data\s+"
    r"is\s+shown\s+below\s+in\s+Table\s+(?P<table>\d+)\.\s+"
    r"TABLE-US-\d+\s+TABLE\s+(?P<header_table>\d+)\s+"
    r"Example\s+(?P<header_example>\d+)\s+Unit\s+mm\b",
    flags=re.IGNORECASE,
)
_KANTATSU_DAMAGED_METADATA_HALF_FIELD_DEFINITION = re.compile(
    r"\bIn\s+each\s+example,\s+f\s+denotes\s+the\s+focal\s+length\s+of\s+the\s+"
    r"overall\s+optical\s+system\s+of\s+the\s+imaging\s+lens,\s+Fno\s+denotes\s+"
    r"an\s+F-number,\s+\S+\s+denotes\s+a\s+half\s+field\s+of\s+view,\s+and\s+"
    r"ih\s+denotes\s+a\s+maximum\s+image\s+height\b",
    flags=re.IGNORECASE,
)
_KANTATSU_DAMAGED_METADATA_ASPHERE_DEFINITION = re.compile(
    r"\bA4,\s+A6,\s+A8,\s+A10,\s+A12,\s+A14,\s+A16,\s+A18\s+and\s+A20\s+"
    r"denote\s+aspheric\s+surface\s+coefficients\b",
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
_SAMSUNG_EVEN_ORDER_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+SYSTEM\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_EVEN_ORDER_BINDING_PATTERN = re.compile(
    r"\bTables\s+(?P<surface_table>\d+)\s+and\s+(?P<asphere_table>\d+)\s+list\s+"
    r"(?:the\s+)?lens\s+characteristics\s+and\s+(?:the\s+)?aspheric\s+values?\s+of\s+"
    r"the\s+imaging\s+lens\s+system\s+according\s+to\s+the\s+present\s+embodiment\.",
    flags=re.IGNORECASE,
)
_SAMSUNG_EVEN_ORDER_HALF_FIELD_DEFINITION = re.compile(
    r"\bHFOV\s+is\s+the\s+half\s+field\s+of\s+view\s+of\s+the\s+imaging\s+lens\s+system\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_EVEN_ORDER_ASPHERE_DEFINITION = re.compile(
    r"\bc\s+is\s+the\s+reciprocal\s+of\s+the\s+radius\s+of\s+curvature\s+of\s+the\s+"
    r"corresponding\s+lens\s*,\s*k\s+is\s+the\s+conic\s+constant\s*,.*?"
    r"\bA\s+to\s+H\s+and\s+J\s+are\s+aspherical\s+constants\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_EVEN_ORDER_SURFACE_HEADERS = frozenset(
    {
        "Surface Radius of Thickness/ Refractive Abbe Effective No. Components "
        "curvature Distance index number Radius",
        # The fifth official HTML table drops the two wrapping column labels,
        # while retaining the same exact 5/3-value row arity as all nine peers.
        "Sur- face Radius of Refractive Abbe Effective No. Components curvature "
        "index number Radius",
        # PPUBS interleaves line-wrapped header cells in TABLE 11.
        "Sur- Thick- Re- face Com- Radius of ness/ fractive Abbe Effective No. "
        "ponents curvature Distance index number Radius",
        "Radius of Thickness/ Refractive Abbe Effective Surface No. Components "
        "curvature Distance index number Radius",
        "Surface Radius of Refractive Abbe Effective No. Components curvature "
        "Thickness/Distance index number Radius",
    }
)
_SAMSUNG_EIGHT_LENS_BINDING_PATTERN = re.compile(
    r"\bTables\s+(?P<surface_table>\d+)\s+and\s+(?P<asphere_table>\d+)\s+list\s+"
    r"lens\s+characteristics\s+and\s+aspherical\s+values\s+of\s+the\s+imaging\s+"
    r"lens\s+system\s+(?P<system>[1-5]00)\s*\.",
    flags=re.IGNORECASE,
)
_SAMSUNG_EIGHT_LENS_STOP_PATTERN = re.compile(
    r"\bThe\s+stop\s+ST\s+may\s+be\s+disposed\s+between\s+the\s+second\s+lens\s+"
    r"(?P<second>[1-5]20)\s+and\s+the\s+third\s+lens\s+(?P<third>[1-5]30)\s*\.",
    flags=re.IGNORECASE,
)
_SAMSUNG_EIGHT_LENS_SURFACE_HEADER_PATTERN = re.compile(
    r"\bSurface\s+Radius\s+of\s+Thickness/\s+Refractive\s+Abbe\s+No\.\s+Note\s+"
    r"Curvature\s+Distance\s+Index\s+Number\s+",
    flags=re.IGNORECASE,
)
_SAMSUNG_EIGHT_LENS_ASPHERE_HEADER_PATTERN = re.compile(
    r"\bSurface\s+No\.\s+K\s+A\s+B\s+C\s+D\s+E\s+",
    flags=re.IGNORECASE,
)
_SAMSUNG_EIGHT_LENS_ASPHERE_CONTINUATION_PATTERN = re.compile(
    r"\bSurface\s+No\.\s+F\s+G\s+H\s+J\s+",
    flags=re.IGNORECASE,
)
_IR_FILTER_COATING_ONLY_TITLE_PATTERN = re.compile(
    r"\bOPTICAL\s+LENS\s+ASSEMBLY\s+AND\s+IMAGING\s+LENS\s+WITH\s+"
    r"INFRARED\s+RAY\s+FILTERING\b",
    flags=re.IGNORECASE,
)
_SURFACE_TEXTURE_ACQUISITION_ONLY_TITLE_PATTERN = re.compile(
    r"\bSYSTEM\s+AND\s+METHOD\s+FOR\s+ACQUIRING\s+IMAGES\s+OF\s+"
    r"SURFACE\s+TEXTURE\b",
    flags=re.IGNORECASE,
)
_LENS_DRIVING_MECHANICAL_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+DRIVING\s+MODULE\s*,?\s+IMAGE\s+CAPTURING\s+"
    r"APPARATUS\s+AND\s+ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_LENS_DRIVING_MECHANICAL_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12607821-B2": {
        "normalized_text_sha256": (
            "59c846813747313f1fc30305ce5632807a11dcfc5cf2ee0ff7eb09e018495969"
        ),
        "mechanical_phrase_counts": {
            "imaging lens driving module": 79,
            "image capturing apparatus": 32,
            "electronic device": 20,
            "driving mechanism": 24,
            "carrier": 175,
            "magnet": 118,
            "coil": 21,
        },
    },
    "US-20220113492-A1": {
        "normalized_text_sha256": (
            "4738f683f3f26fd4ecaeaba9a7cc56bf03d690b409dd1be8010219b82890222c"
        ),
        "mechanical_phrase_counts": {
            "imaging lens driving module": 83,
            "image capturing apparatus": 32,
            "electronic device": 20,
            "driving mechanism": 24,
            "carrier": 175,
            "magnet": 116,
            "coil": 21,
        },
    },
}
_NON_OPTICAL_ZONE_STRAY_LIGHT_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY\s+AND\s+OPTICAL\s+VERIFICATION\s+SYSTEM\b",
    flags=re.IGNORECASE,
)
_NON_OPTICAL_ZONE_STRAY_LIGHT_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-11892707-B2": {
        "normalized_text_sha256": (
            "101ff4360f85edbb552f718c9ac4ec9a1343c65026491ca21f37f5b38d5e2757"
        ),
        "architecture_phrase_counts": {
            "Family ID: 79907355": 1,
            "field of view (FOV) greater than 120 degrees": 2,
            "first connection portion": 32,
            "non-optical zone": 54,
            "stray light": 16,
            "three-piece optical lens assembly": 1,
            "curvature radius": 11,
        },
    },
    "US-20220229269-A1": {
        "normalized_text_sha256": (
            "8c8066f68343d3ec391ace2c7daedc810c0e37b44d46de34406c8327e2a4a0a3"
        ),
        "architecture_phrase_counts": {
            "Family ID: 79907355": 1,
            "field of view (FOV) greater than 120 degrees": 2,
            "first connection portion": 32,
            "non-optical zone": 54,
            "stray light": 16,
            "three-piece optical lens assembly": 1,
            "curvature radius": 11,
        },
    },
}
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


# ---------------------------------------------------------------------------
# Ability Enterprise drawing-table PDF fallback.  PPUBS HTML declares these
# figures but omits their image-only prescriptions.  The retained parser input
# is canonical JSON produced only after the OCR PDF's embedded page images are
# pixel-identical to the official USPTO decoded page rasters.
# ---------------------------------------------------------------------------

_ABILITY_PDF_PARSER_FAMILY = "ability_official_pdf_ocr_v1"
_ABILITY_EIGHT_LENS_PROFILE = "ability_eight_lens_metadata_unpublished_v1"
_ABILITY_THREE_LENS_PROFILE = "ability_three_lens_prescriptions_v1"
_ABILITY_TWO_FIVE_LENS_PROFILE = "ability_two_five_lens_prescriptions_v1"
_ABILITY_TWO_NINE_LENS_PROFILE = "ability_two_nine_lens_f_number_unpublished_v1"
_ABILITY_FOUR_EIGHT_LENS_PROFILE = "ability_four_eight_lens_f_number_unpublished_v1"
_LARGAN_THREE_FIVE_LENS_PROFILE = "largan_three_five_lens_prescriptions_v1"
_ABILITY_ZOOM_TWO_STATE_PROFILE = "ability_zoom_two_state_census_v1"
_GENIUS_FOUR_LENS_ELEVEN_PROFILE = "genius_four_lens_eleven_embodiment_census_v1"
_GENIUS_NINE_LENS_ELEVEN_PROFILE = "genius_nine_lens_eleven_embodiment_census_v1"
_GENIUS_EIGHT_LENS_FOURTEEN_PROFILE = (
    "genius_eight_lens_fourteen_embodiment_census_v1"
)
_GENIUS_FOUR_LENS_NINE_PROFILE = "genius_four_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_FIVE_PROFILE = "genius_six_lens_five_embodiment_census_v1"
_GENIUS_SIX_LENS_NINE_PROFILE = "genius_six_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE = (
    "genius_six_lens_nine_three_comparison_census_v1"
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE = (
    "genius_six_lens_nine_four_comparison_census_v1"
)
_ABILITY_OCR_LABEL_CONFIDENCE = 0.95
_ABILITY_OCR_NUMBER_CONFIDENCE = 0.99
_ABILITY_ROW_Y_TOLERANCE = 18.0
_ABILITY_COLUMN_X_TOLERANCE = 85.0
_ABILITY_OL2_ROW_LABELS = (
    "S1",
    "S2",
    "S3",
    "S4",
    "S15",
    "S16",
    "S5",
    "S6",
    "St",
    "S10",
    "S11",
    "S12",
    "S7",
    "S8",
    "Sf1",
    "Sf2",
    "Sc1",
    "Sc2",
    "Image",
)
_ABILITY_THREE_OL12_SURFACE_LABELS = (
    *(f"S{i}" for i in range(1, 7)),
    "St",
    *(f"S{i}" for i in range(7, 17)),
)
_ABILITY_THREE_OL3_SURFACE_LABELS = (
    *(f"S{i}" for i in range(1, 7)),
    "St",
    *(f"S{i}" for i in range(7, 19)),
)
_ABILITY_THREE_OL12_ASPHERE_LABELS = (
    "S3",
    "S4",
    "S7",
    "S8",
    "S9",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
)
_ABILITY_THREE_OL3_ASPHERE_LABELS = (
    "S5",
    "S6",
    "S7",
    "S8",
    "S9",
    "S11",
    "S12",
    "S13",
    "S14",
)
_ABILITY_TWO_FIVE_SURFACE_LABELS = (
    *(f"S{i}" for i in range(1, 5)),
    "St",
    *(f"S{i}" for i in range(5, 15)),
)
_ABILITY_TWO_FIVE_ASPHERE_LABELS = ("S3", "S4", "S7", "S8", "S9", "S10")


def _ability_token_center(token: dict[str, Any]) -> tuple[float, float]:
    box = token.get("box")
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(not isinstance(point, list) or len(point) != 2 for point in box)
    ):
        raise PatentParseError("Ability PDF OCR token has an invalid box")
    try:
        x = sum(float(point[0]) for point in box) / 4.0
        y = sum(float(point[1]) for point in box) / 4.0
    except (TypeError, ValueError) as exc:
        raise PatentParseError("Ability PDF OCR token box is not numeric") from exc
    return x, y


def _ability_token_text(token: dict[str, Any]) -> str:
    text = token.get("text")
    if not isinstance(text, str) or not text.strip():
        raise PatentParseError("Ability PDF OCR token text is empty")
    return text.strip()


def _ability_token_confidence(token: dict[str, Any]) -> float:
    try:
        confidence = float(token.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise PatentParseError("Ability PDF OCR token confidence is invalid") from exc
    if not 0.0 <= confidence <= 1.0:
        raise PatentParseError("Ability PDF OCR token confidence is outside [0, 1]")
    return confidence


def _ability_page(payload: dict[str, Any], role: str) -> dict[str, Any]:
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise PatentParseError("Ability PDF OCR pages must be a list")
    matches = [page for page in pages if isinstance(page, dict) and page.get("role") == role]
    if len(matches) != 1:
        raise PatentParseError(f"Ability PDF OCR role {role} occurs {len(matches)} times")
    page = matches[0]
    digest = page.get("official_image_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise PatentParseError(f"Ability PDF OCR role {role} lacks an official image hash")
    tokens = page.get("rapidocr_tokens")
    if not isinstance(tokens, list) or not tokens or any(not isinstance(t, dict) for t in tokens):
        raise PatentParseError(f"Ability PDF OCR role {role} lacks structured OCR tokens")
    return page


def _ability_unique_token(
    tokens: list[dict[str, Any]],
    text: str,
    *,
    min_confidence: float,
) -> dict[str, Any]:
    matches = [
        token
        for token in tokens
        if _ability_token_text(token).casefold() == text.casefold()
        and _ability_token_confidence(token) >= min_confidence
    ]
    if len(matches) != 1:
        raise PatentParseError(
            f"Ability PDF OCR token {text!r} occurs {len(matches)} times above confidence gate"
        )
    return matches[0]


def _ability_number_token(
    tokens: list[dict[str, Any]],
    *,
    x: float,
    y: float,
    required: bool,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for token in tokens:
        token_text = _ability_token_text(token)
        if re.fullmatch(NUMBER_PATTERN, token_text, re.IGNORECASE) is None:
            continue
        token_x, token_y = _ability_token_center(token)
        if (
            abs(token_x - x) <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(token_y - y) <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
        ):
            candidates.append(token)
    if len(candidates) > 1 or (required and len(candidates) != 1):
        raise PatentParseError(
            f"Ability PDF OCR numeric cell at ({x:.1f}, {y:.1f}) has {len(candidates)} values"
        )
    return candidates[0] if candidates else None


def _ability_infinity_token(
    tokens: list[dict[str, Any]],
    *,
    x: float,
    y: float,
) -> None:
    candidates = []
    for token in tokens:
        token_x, token_y = _ability_token_center(token)
        if (
            abs(token_x - x) <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(token_y - y) <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_confidence(token) >= 0.97
        ):
            candidates.append(_ability_token_text(token))
    # RapidOCR deterministically renders the printed infinity glyph as "8"
    # in this retained layout.  This alias is accepted only in the radius
    # column of rows which the source labels as stop/filter/cover/image.
    if candidates != ["8"]:
        raise PatentParseError(
            f"Ability PDF flat-surface radius cell is not the retained infinity alias: {candidates}"
        )


def _ability_surface_table(page: dict[str, Any]) -> list[PatentSurface]:
    tokens = list(page["rapidocr_tokens"])
    surface_header = _ability_unique_token(
        tokens,
        "Surface",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    curvature_header = _ability_unique_token(
        tokens,
        "Curvature",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    thickness_header = _ability_unique_token(
        tokens,
        "Thickness",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    abbe_header = _ability_unique_token(
        tokens,
        "Abbe",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    refractive_matches = [
        token
        for token in tokens
        if "refractive" in _ability_token_text(token).casefold()
        and _ability_token_confidence(token) >= 0.94
    ]
    if len(refractive_matches) != 1:
        raise PatentParseError("Ability PDF refractive-index header is ambiguous")
    surface_x, header_y = _ability_token_center(surface_header)
    radius_x, _ = _ability_token_center(curvature_header)
    thickness_x, _ = _ability_token_center(thickness_header)
    nd_x, _ = _ability_token_center(refractive_matches[0])
    vd_x, _ = _ability_token_center(abbe_header)
    figure_tokens = [
        token for token in tokens if _ability_token_text(token).upper().startswith("FIG.")
    ]
    if len(figure_tokens) != 1:
        raise PatentParseError("Ability PDF surface figure boundary is ambiguous")
    _, figure_y = _ability_token_center(figure_tokens[0])

    labeled_rows: list[tuple[float, str]] = []
    for token in tokens:
        text = _ability_token_text(token)
        x, y = _ability_token_center(token)
        if not header_y < y < figure_y or abs(x - surface_x) > _ABILITY_COLUMN_X_TOLERANCE:
            continue
        if re.fullmatch(r"S\d+|St|Sf\d+|Sc\d+", text, re.IGNORECASE) is None:
            continue
        if _ability_token_confidence(token) < _ABILITY_OCR_LABEL_CONFIDENCE:
            raise PatentParseError(f"Ability PDF surface label {text} is below confidence gate")
        labeled_rows.append((y, text))
    labeled_rows.sort()
    if not labeled_rows:
        raise PatentParseError("Ability PDF surface table has no labeled rows")

    surfaces: list[PatentSurface] = []
    observed_labels: list[str] = []
    for row_y, source_label in labeled_rows:
        canonical = source_label[0].upper() + source_label[1:]
        is_flat_auxiliary = canonical.casefold() in {
            "st",
            "sf1",
            "sf2",
            "sc1",
            "sc2",
        }
        if is_flat_auxiliary:
            _ability_infinity_token(tokens, x=radius_x, y=row_y)
            radius = None
        else:
            radius_token = _ability_number_token(
                tokens,
                x=radius_x,
                y=row_y,
                required=True,
            )
            assert radius_token is not None
            radius = _parse_number(_ability_token_text(radius_token))
        thickness_token = _ability_number_token(
            tokens,
            x=thickness_x,
            y=row_y,
            required=True,
        )
        assert thickness_token is not None
        thickness = _parse_number(_ability_token_text(thickness_token))
        nd_token = _ability_number_token(tokens, x=nd_x, y=row_y, required=False)
        vd_token = _ability_number_token(tokens, x=vd_x, y=row_y, required=False)
        if (nd_token is None) != (vd_token is None):
            raise PatentParseError(f"Ability PDF row {canonical} has incomplete material metadata")
        nd = _parse_number(_ability_token_text(nd_token)) if nd_token is not None else None
        vd = _parse_number(_ability_token_text(vd_token)) if vd_token is not None else None
        _validate_material_indices(surface_index=len(surfaces) + 1, nd=nd, vd=vd)
        if canonical.casefold() == "st":
            label = "Stop"
        elif canonical.casefold().startswith("sf"):
            label = "Filter"
        elif canonical.casefold().startswith("sc"):
            label = "Cover"
        else:
            label = canonical
        observed_labels.append(canonical)
        surfaces.append(
            PatentSurface(
                index=len(surfaces) + 1,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=None,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )

    last_row_y = labeled_rows[-1][0]
    trailing_radius = [
        token
        for token in tokens
        if last_row_y + _ABILITY_ROW_Y_TOLERANCE < _ability_token_center(token)[1] < figure_y
        and abs(_ability_token_center(token)[0] - radius_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and _ability_token_confidence(token) >= 0.97
    ]
    trailing_thickness = [
        token
        for token in tokens
        if last_row_y + _ABILITY_ROW_Y_TOLERANCE < _ability_token_center(token)[1] < figure_y
        and abs(_ability_token_center(token)[0] - thickness_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
    ]
    if [_ability_token_text(token) for token in trailing_radius] != ["8"]:
        raise PatentParseError("Ability PDF image-plane infinity cell is not uniquely retained")
    if [_ability_token_text(token) for token in trailing_thickness] != ["0.00"]:
        raise PatentParseError("Ability PDF image-plane thickness cell is not uniquely retained")
    observed_labels.append("Image")
    surfaces.append(
        PatentSurface(
            index=len(surfaces) + 1,
            label="Image",
            radius_mm=None,
            thickness_mm=0.0,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    if tuple(observed_labels) != _ABILITY_OL2_ROW_LABELS:
        raise PatentParseError(
            "Ability OL2 surface row sequence mismatch: " + ",".join(observed_labels)
        )
    return surfaces


def _ability_meta_row(page: dict[str, Any], label: str) -> tuple[float, float]:
    tokens = list(page["rapidocr_tokens"])
    label_token = _ability_unique_token(
        tokens,
        label,
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    label_x, label_y = _ability_token_center(label_token)
    values: list[tuple[float, float]] = []
    for token in tokens:
        text = _ability_token_text(token)
        if re.fullmatch(NUMBER_PATTERN, text, re.IGNORECASE) is None:
            continue
        x, y = _ability_token_center(token)
        if (
            x > label_x + _ABILITY_COLUMN_X_TOLERANCE
            and abs(y - label_y) <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
        ):
            values.append((x, _parse_number(text)))
    values.sort()
    if len(values) != 2:
        raise PatentParseError(f"Ability PDF metadata row {label} has {len(values)} values")
    return values[0][1], values[1][1]


def _ability_profile_number_token(
    tokens: list[dict[str, Any]],
    *,
    x: float,
    y: float,
    min_confidence: float = _ABILITY_OCR_NUMBER_CONFIDENCE,
) -> dict[str, Any]:
    candidates = []
    for token in tokens:
        if re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE) is None:
            continue
        token_x, token_y = _ability_token_center(token)
        if (
            abs(token_x - x) <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(token_y - y) <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_confidence(token) >= min_confidence
        ):
            candidates.append(token)
    if len(candidates) != 1:
        raise PatentParseError(
            f"Ability PDF numeric cell at ({x:.1f}, {y:.1f}) has "
            f"{len(candidates)} values above confidence gate"
        )
    return candidates[0]


def _ability_three_lens_surface_table(
    page: dict[str, Any],
    *,
    expected_labels: tuple[str, ...],
    surface_figure: str,
) -> tuple[list[PatentSurface], dict[str, float]]:
    tokens = list(page["rapidocr_tokens"])
    surface_header = _ability_unique_token(tokens, "surface", min_confidence=0.98)
    curvature_header = _ability_unique_token(tokens, "curvature", min_confidence=0.98)
    index_header = _ability_unique_token(tokens, "index", min_confidence=0.98)
    abbe_header = _ability_unique_token(tokens, "number", min_confidence=0.98)
    conic_header = _ability_unique_token(tokens, "constant", min_confidence=0.98)
    surface_x, header_y = _ability_token_center(surface_header)
    radius_x, _ = _ability_token_center(curvature_header)
    nd_x, _ = _ability_token_center(index_header)
    vd_x, _ = _ability_token_center(abbe_header)
    conic_x, _ = _ability_token_center(conic_header)
    millimeter_headers = [
        token
        for token in tokens
        if _ability_token_text(token).casefold() == "(mm)"
        and _ability_token_confidence(token) >= 0.98
    ]
    thickness_headers = [
        token
        for token in millimeter_headers
        if radius_x < _ability_token_center(token)[0] < nd_x
    ]
    if len(thickness_headers) != 1:
        raise PatentParseError("Ability three-lens thickness column is ambiguous")
    thickness_x, _ = _ability_token_center(thickness_headers[0])
    figure_token = _ability_unique_token(tokens, surface_figure, min_confidence=0.90)
    _, figure_y = _ability_token_center(figure_token)

    row_tokens = [
        token
        for token in tokens
        if header_y < _ability_token_center(token)[1] < figure_y
        and abs(_ability_token_center(token)[0] - surface_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and re.fullmatch(r"S\d+|St", _ability_token_text(token), re.IGNORECASE)
        and _ability_token_confidence(token) >= 0.90
    ]
    row_tokens.sort(key=lambda token: _ability_token_center(token)[1])
    observed_labels = tuple(_ability_token_text(token) for token in row_tokens)
    if tuple(label.casefold() for label in observed_labels) != tuple(
        label.casefold() for label in expected_labels
    ):
        raise PatentParseError(
            "Ability three-lens surface row sequence mismatch: " + ",".join(observed_labels)
        )

    surfaces: list[PatentSurface] = []
    conics: dict[str, float] = {}
    for label, row_token in zip(expected_labels, row_tokens, strict=True):
        _, row_y = _ability_token_center(row_token)
        radius_token = _ability_profile_number_token(tokens, x=radius_x, y=row_y)
        radius_text = _ability_token_text(radius_token)
        if radius_text == "8":
            _ability_infinity_token(tokens, x=radius_x, y=row_y)
            radius = None
        else:
            radius = _parse_number(radius_text)
        thickness = _parse_number(
            _ability_token_text(
                _ability_profile_number_token(tokens, x=thickness_x, y=row_y)
            )
        )
        material_tokens = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[1] - row_y) <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
            and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
        ]
        nd_matches = [
            token
            for token in material_tokens
            if abs(_ability_token_center(token)[0] - nd_x) <= _ABILITY_COLUMN_X_TOLERANCE
        ]
        vd_matches = [
            token
            for token in material_tokens
            if abs(_ability_token_center(token)[0] - vd_x) <= _ABILITY_COLUMN_X_TOLERANCE
        ]
        if len(nd_matches) != len(vd_matches) or len(nd_matches) > 1:
            raise PatentParseError(f"Ability three-lens row {label} has incomplete material data")
        nd = _parse_number(_ability_token_text(nd_matches[0])) if nd_matches else None
        vd = _parse_number(_ability_token_text(vd_matches[0])) if vd_matches else None
        _validate_material_indices(surface_index=len(surfaces) + 1, nd=nd, vd=vd)
        conic = _parse_number(
            _ability_token_text(_ability_profile_number_token(tokens, x=conic_x, y=row_y))
        )
        conics[label] = conic
        surfaces.append(
            PatentSurface(
                index=len(surfaces) + 1,
                label="Stop" if label.casefold() == "st" else label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=None,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )

    image_tokens = [
        token
        for token in tokens
        if header_y < _ability_token_center(token)[1] < figure_y
        and abs(_ability_token_center(token)[0] - surface_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and _ability_token_text(token).casefold() == "i"
        and _ability_token_confidence(token) >= 0.65
    ]
    if len(image_tokens) != 1:
        raise PatentParseError("Ability three-lens image row is not independently located")
    _, image_y = _ability_token_center(image_tokens[0])
    _ability_infinity_token(tokens, x=radius_x, y=image_y)
    surfaces.append(
        PatentSurface(
            index=len(surfaces) + 1,
            label="Image",
            radius_mm=None,
            thickness_mm=0.0,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces, conics


def _ability_overlay_asphere_rows(
    page: dict[str, Any],
    *,
    expected_labels: tuple[str, ...],
    surface_figure: str,
    asphere_figure: str,
) -> dict[str, str]:
    mirror_text = page.get("mirror_text")
    if not isinstance(mirror_text, str):
        raise PatentParseError("Ability three-lens page lacks OCR-overlay text")
    start_match = re.search(
        rf"\bFig\s*\.\s*{re.escape(surface_figure.removeprefix('Fig. '))}\b",
        mirror_text,
        flags=re.IGNORECASE,
    )
    end_match = re.search(
        rf"\bFig\s*\.\s*{re.escape(asphere_figure.removeprefix('Fig. '))}\b",
        mirror_text,
        flags=re.IGNORECASE,
    )
    if start_match is None or end_match is None or start_match.end() >= end_match.start():
        raise PatentParseError("Ability three-lens asphere overlay boundaries are ambiguous")
    text = mirror_text[start_match.end() : end_match.start()]
    text = re.sub(r"([Ee])\s*([+-])\s*(\d+)", r"\1\2\3", text)
    starts: list[tuple[str, int, int]] = []
    cursor = 0
    for label in expected_labels:
        match = re.search(
            rf"(?<![A-Z0-9]){re.escape(label)}(?=\s|[-+0-9])",
            text[cursor:],
            flags=re.IGNORECASE,
        )
        if match is None:
            raise PatentParseError(f"Ability three-lens overlay row {label} is not located")
        start = cursor + match.start()
        end = cursor + match.end()
        starts.append((label, start, end))
        cursor = end
    return {
        label: text[row_end : (starts[index + 1][1] if index + 1 < len(starts) else len(text))]
        for index, (label, _row_start, row_end) in enumerate(starts)
    }


def _ability_three_lens_aspheres(
    page: dict[str, Any],
    *,
    expected_labels: tuple[str, ...],
    surface_figure: str,
    asphere_figure: str,
) -> dict[str, dict[str, float]]:
    tokens = list(page["rapidocr_tokens"])
    header_labels = ("A2", "A4", "A6", "A8", "A10", "A12", "A14", "A16")
    header_tokens = {
        label: _ability_unique_token(tokens, label, min_confidence=0.95)
        for label in header_labels
    }
    header_y = sum(_ability_token_center(token)[1] for token in header_tokens.values()) / len(
        header_tokens
    )
    end_token = _ability_unique_token(tokens, asphere_figure, min_confidence=0.90)
    _, end_y = _ability_token_center(end_token)
    overlay_rows = _ability_overlay_asphere_rows(
        page,
        expected_labels=expected_labels,
        surface_figure=surface_figure,
        asphere_figure=asphere_figure,
    )
    coefficients: dict[str, dict[str, float]] = {}
    for label in expected_labels:
        label_matches = [
            token
            for token in tokens
            if _ability_token_text(token).casefold() == label.casefold()
            and header_y < _ability_token_center(token)[1] < end_y
            and _ability_token_confidence(token) >= 0.90
        ]
        if len(label_matches) != 1:
            raise PatentParseError(
                f"Ability three-lens asphere row {label} occurs {len(label_matches)} times"
            )
        _, row_y = _ability_token_center(label_matches[0])
        texts: list[str] = []
        values: list[float] = []
        for header_label in header_labels:
            column_x, _ = _ability_token_center(header_tokens[header_label])
            token = _ability_profile_number_token(tokens, x=column_x, y=row_y)
            texts.append(_ability_token_text(token))
            values.append(_parse_number(texts[-1]))
        overlay_row = overlay_rows[label]
        overlay_cursor = 0
        for token_text in texts:
            match = re.search(
                rf"(?<![-+0-9.]){re.escape(token_text)}(?![0-9.])",
                overlay_row[overlay_cursor:],
                flags=re.IGNORECASE,
            )
            if match is None:
                raise PatentParseError(
                    f"Ability three-lens {label} OCR views disagree at value {token_text}"
                )
            overlay_cursor += match.end()
        if values[0] != 0.0:
            raise PatentParseError(f"Ability three-lens {label} has unsupported nonzero A2")
        coefficients[label] = dict(zip(header_labels[1:], values[1:], strict=True))
    return coefficients


def _ability_three_lens_system_meta(page: dict[str, Any]) -> list[tuple[float, float, float]]:
    tokens = list(page["rapidocr_tokens"])
    column_tokens = [
        _ability_unique_token(tokens, label, min_confidence=0.97)
        for label in ("OL1", "OL2", "OL3")
    ]
    column_xs = [_ability_token_center(token)[0] for token in column_tokens]
    rows: dict[str, list[float]] = {}
    for label, minimum_confidence in (("F (mm)", 0.94), ("FNO (mm)", 0.97), ("FOV (degree)", 0.97)):
        label_token = _ability_unique_token(tokens, label, min_confidence=minimum_confidence)
        _, row_y = _ability_token_center(label_token)
        rows[label] = [
            _parse_number(
                _ability_token_text(_ability_profile_number_token(tokens, x=x, y=row_y))
            )
            for x in column_xs
        ]
    metadata = list(zip(rows["F (mm)"], rows["FNO (mm)"], rows["FOV (degree)"], strict=True))
    if any(f <= 0.0 or fno <= 0.0 or not 0.0 < fov < 180.0 for f, fno, fov in metadata):
        raise PatentParseError("Ability three-lens system metadata is outside physical bounds")
    return metadata


def _parse_ability_three_lens_attempts(payload: dict[str, Any]) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 15:
        raise PatentParseError("Ability three-lens PDF page count is not the retained layout")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 4:
        raise PatentParseError("Ability three-lens PDF must retain exactly four key pages")
    role_pages = (
        (
            "prescription_ol1",
            6,
            "Fig. 4A",
            "Fig. 4B",
            _ABILITY_THREE_OL12_SURFACE_LABELS,
            _ABILITY_THREE_OL12_ASPHERE_LABELS,
        ),
        (
            "prescription_ol2",
            7,
            "Fig. 5A",
            "Fig. 5B",
            _ABILITY_THREE_OL12_SURFACE_LABELS,
            _ABILITY_THREE_OL12_ASPHERE_LABELS,
        ),
        (
            "prescription_ol3",
            8,
            "Fig. 6A",
            "Fig. 6B",
            _ABILITY_THREE_OL3_SURFACE_LABELS,
            _ABILITY_THREE_OL3_ASPHERE_LABELS,
        ),
    )
    prescription_pages: list[dict[str, Any]] = []
    for role, page_number, surface_figure, asphere_figure, _surface_labels, _asphere_labels in role_pages:
        page = _ability_page(payload, role)
        if page.get("page_number") != page_number:
            raise PatentParseError(f"Ability three-lens role {role} is on the wrong page")
        mirror_text = page.get("mirror_text")
        figure_numbers = (
            surface_figure.removeprefix("Fig. "),
            asphere_figure.removeprefix("Fig. "),
        )
        if (
            not isinstance(mirror_text, str)
            or any(
                re.search(
                    rf"\bFig\s*\.\s*{re.escape(figure)}\b",
                    mirror_text,
                    flags=re.IGNORECASE,
                )
                is None
                for figure in figure_numbers
            )
            or any(
                marker.casefold() not in mirror_text.casefold()
                for marker in ("surface", "curvature", "A16")
            )
        ):
            raise PatentParseError(f"Ability three-lens role {role} lacks figure/table markers")
        prescription_pages.append(page)
    meta_page = _ability_page(payload, "system_meta_three")
    if meta_page.get("page_number") != 9:
        raise PatentParseError("Ability three-lens system metadata is not on page 9")
    metadata = _ability_three_lens_system_meta(meta_page)

    facts = payload.get("source_facts")
    expected_figure_counts = {
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 5A": 1,
        "FIG. 5B": 1,
        "FIG. 6A": 1,
        "FIG. 6B": 2,
        "FIG. 7": 2,
    }
    if not isinstance(facts, dict) or facts.get("figure_binding_counts") != expected_figure_counts:
        raise PatentParseError("Ability three-lens official figure bindings changed")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Ability three-lens official HTML hash is invalid")

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, (profile, page, meta) in enumerate(
        zip(role_pages, prescription_pages, metadata, strict=True),
        start=1,
    ):
        _role, _page_number, surface_figure, asphere_figure, surface_labels, asphere_labels = profile
        embodiment = f"Ability optical lens OL{embodiment_number}"
        try:
            surfaces, conics = _ability_three_lens_surface_table(
                page,
                expected_labels=surface_labels,
                surface_figure=surface_figure,
            )
            coefficient_rows = _ability_three_lens_aspheres(
                page,
                expected_labels=asphere_labels,
                surface_figure=surface_figure,
                asphere_figure=asphere_figure,
            )
            surface_by_label = {surface.label: surface for surface in surfaces}
            if any(value != 0.0 and label not in coefficient_rows for label, value in conics.items()):
                raise PatentParseError(
                    f"Ability OL{embodiment_number} has a conic outside its asphere table"
                )
            for label, coefficients in coefficient_rows.items():
                surface = surface_by_label[label]
                surface.surface_type = "ASP"
                if conics[label] != 0.0:
                    surface.asphere_coefficients["K"] = conics[label]
                surface.asphere_coefficients.update(coefficients)
            focal_length, f_number, full_fov = meta
            prescription = PatentPrescription(
                patent_id=str(payload["publication_id"]),
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=full_fov / 2.0,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retain each disclosed optical lens
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
        else:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    prescription=prescription,
                )
            )
    return attempts


def _ability_two_five_surface_table(
    page: dict[str, Any],
    *,
    surface_figure: str,
) -> list[PatentSurface]:
    """Parse one source-bound five-lens surface table without repairing OCR."""

    tokens = list(page["rapidocr_tokens"])
    figure_token = _ability_unique_token(tokens, surface_figure, min_confidence=0.90)
    _, figure_y = _ability_token_center(figure_token)

    def table_header(text: str) -> dict[str, Any]:
        matches = [
            token
            for token in tokens
            if _ability_token_text(token).casefold() == text.casefold()
            and _ability_token_center(token)[1] < figure_y
            and _ability_token_confidence(token) >= 0.98
        ]
        if len(matches) != 1:
            raise PatentParseError(
                f"Ability two-five-lens header {text!r} occurs {len(matches)} times"
            )
        return matches[0]

    surface_header = table_header("Surface")
    radius_header = table_header("curvature")
    thickness_header = table_header("Thickness")
    refractive_header = table_header("Refractive")
    abbe_header = table_header("Abbe")
    surface_x, header_y = _ability_token_center(surface_header)
    radius_x, _ = _ability_token_center(radius_header)
    thickness_x, _ = _ability_token_center(thickness_header)
    nd_x, _ = _ability_token_center(refractive_header)
    vd_x, _ = _ability_token_center(abbe_header)

    row_tokens = [
        token
        for token in tokens
        if header_y < _ability_token_center(token)[1] < figure_y
        and abs(_ability_token_center(token)[0] - surface_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and re.fullmatch(r"S\d+|St", _ability_token_text(token), re.IGNORECASE)
        and _ability_token_confidence(token) >= _ABILITY_OCR_LABEL_CONFIDENCE
    ]
    row_tokens.sort(key=lambda token: _ability_token_center(token)[1])
    observed_labels = tuple(_ability_token_text(token) for token in row_tokens)
    if tuple(label.casefold() for label in observed_labels) != tuple(
        label.casefold() for label in _ABILITY_TWO_FIVE_SURFACE_LABELS
    ):
        raise PatentParseError(
            "Ability two-five-lens surface row sequence mismatch: "
            + ",".join(observed_labels)
        )

    surfaces: list[PatentSurface] = []
    for label, row_token in zip(
        _ABILITY_TWO_FIVE_SURFACE_LABELS,
        row_tokens,
        strict=True,
    ):
        _, row_y = _ability_token_center(row_token)
        radius_candidates = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[0] - radius_x) <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(_ability_token_center(token)[1] - row_y) <= _ABILITY_ROW_Y_TOLERANCE
            and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
            and _ability_token_confidence(token) >= 0.97
        ]
        if [_ability_token_text(token) for token in radius_candidates] == ["8"]:
            _ability_infinity_token(tokens, x=radius_x, y=row_y)
            radius = None
        else:
            radius = _parse_number(
                _ability_token_text(
                    _ability_profile_number_token(tokens, x=radius_x, y=row_y)
                )
            )
        thickness = _parse_number(
            _ability_token_text(
                _ability_profile_number_token(tokens, x=thickness_x, y=row_y)
            )
        )
        material_tokens = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[1] - row_y) <= _ABILITY_ROW_Y_TOLERANCE
            and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
            and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
        ]
        nd_matches = [
            token
            for token in material_tokens
            if abs(_ability_token_center(token)[0] - nd_x) <= _ABILITY_COLUMN_X_TOLERANCE
        ]
        vd_matches = [
            token
            for token in material_tokens
            if abs(_ability_token_center(token)[0] - vd_x) <= _ABILITY_COLUMN_X_TOLERANCE
        ]
        if len(nd_matches) != len(vd_matches) or len(nd_matches) > 1:
            raise PatentParseError(
                f"Ability two-five-lens row {label} has incomplete material data"
            )
        nd = _parse_number(_ability_token_text(nd_matches[0])) if nd_matches else None
        vd = _parse_number(_ability_token_text(vd_matches[0])) if vd_matches else None
        _validate_material_indices(surface_index=len(surfaces) + 1, nd=nd, vd=vd)
        surfaces.append(
            PatentSurface(
                index=len(surfaces) + 1,
                label="Stop" if label.casefold() == "st" else label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=None,
                nd=nd,
                vd=vd,
                surface_type=None,
            )
        )

    last_row_y = _ability_token_center(row_tokens[-1])[1]
    image_radius_tokens = [
        token
        for token in tokens
        if last_row_y + _ABILITY_ROW_Y_TOLERANCE < _ability_token_center(token)[1] < figure_y
        and abs(_ability_token_center(token)[0] - radius_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
    ]
    if len(image_radius_tokens) != 1:
        raise PatentParseError("Ability two-five-lens image row is not independently located")
    _, image_y = _ability_token_center(image_radius_tokens[0])
    _ability_infinity_token(tokens, x=radius_x, y=image_y)
    surfaces.append(
        PatentSurface(
            index=len(surfaces) + 1,
            label="Image",
            radius_mm=None,
            thickness_mm=0.0,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces


def _ability_two_five_aspheres(
    page: dict[str, Any],
    *,
    surface_figure: str,
    asphere_figure: str,
) -> dict[str, dict[str, float]]:
    """Parse the transposed six-surface asphere table with two-view agreement."""

    tokens = list(page["rapidocr_tokens"])
    surface_end = _ability_unique_token(tokens, surface_figure, min_confidence=0.90)
    asphere_end = _ability_unique_token(tokens, asphere_figure, min_confidence=0.90)
    _, surface_end_y = _ability_token_center(surface_end)
    _, asphere_end_y = _ability_token_center(asphere_end)
    k_token = _ability_unique_token(tokens, "K", min_confidence=0.95)
    _, k_y = _ability_token_center(k_token)
    column_tokens: list[dict[str, Any]] = []
    for label in _ABILITY_TWO_FIVE_ASPHERE_LABELS:
        matches = [
            token
            for token in tokens
            if _ability_token_text(token).casefold() == label.casefold()
            and surface_end_y < _ability_token_center(token)[1] < k_y
            and _ability_token_confidence(token) >= _ABILITY_OCR_LABEL_CONFIDENCE
        ]
        if len(matches) != 1:
            raise PatentParseError(
                f"Ability two-five-lens asphere column {label} occurs {len(matches)} times"
            )
        column_tokens.append(matches[0])
    column_xs = [_ability_token_center(token)[0] for token in column_tokens]

    row_labels = ("K", "A2", "A4", "A6", "A8", "A10", "A12")
    row_tokens: list[dict[str, Any]] = []
    for label in row_labels:
        matches = [
            token
            for token in tokens
            if _ability_token_text(token).casefold() == label.casefold()
            and surface_end_y < _ability_token_center(token)[1] < asphere_end_y
            and _ability_token_confidence(token) >= _ABILITY_OCR_LABEL_CONFIDENCE
        ]
        if len(matches) != 1:
            raise PatentParseError(
                f"Ability two-five-lens asphere row {label} occurs {len(matches)} times"
            )
        row_tokens.append(matches[0])
    if [
        _ability_token_center(token)[1] for token in row_tokens
    ] != sorted(_ability_token_center(token)[1] for token in row_tokens):
        raise PatentParseError("Ability two-five-lens asphere rows are out of order")

    mirror_text = page.get("mirror_text")
    if not isinstance(mirror_text, str):
        raise PatentParseError("Ability two-five-lens page lacks OCR-overlay text")
    start_match = re.search(
        rf"\bFig\s*\.\s*{re.escape(surface_figure.removeprefix('FIG. '))}\b",
        mirror_text,
        flags=re.IGNORECASE,
    )
    end_match = re.search(
        rf"\bFig\s*\.\s*{re.escape(asphere_figure.removeprefix('FIG. '))}\b",
        mirror_text,
        flags=re.IGNORECASE,
    )
    if start_match is None or end_match is None or start_match.end() >= end_match.start():
        raise PatentParseError("Ability two-five-lens asphere overlay boundaries are ambiguous")
    overlay = re.sub(
        r"([Ee])\s*([+-])\s*(\d+)",
        r"\1\2\3",
        mirror_text[start_match.end() : end_match.start()],
    )
    overlay_cursor = 0
    rows: dict[str, list[float]] = {}
    for label, row_token in zip(row_labels, row_tokens, strict=True):
        _, row_y = _ability_token_center(row_token)
        texts = [
            _ability_token_text(_ability_profile_number_token(tokens, x=x, y=row_y))
            for x in column_xs
        ]
        for token_text in texts:
            match = re.search(
                rf"(?<![A-Z0-9.+-]){re.escape(token_text)}(?![A-Z0-9.])",
                overlay[overlay_cursor:],
                flags=re.IGNORECASE,
            )
            if match is None:
                raise PatentParseError(
                    "Ability two-five-lens OCR views disagree at "
                    f"{label} value {token_text}"
                )
            overlay_cursor += match.end()
        rows[label] = [_parse_number(text) for text in texts]
    if any(value != 0.0 for value in rows["A2"]):
        raise PatentParseError("Ability two-five-lens table has unsupported nonzero A2")
    return {
        surface_label: {
            coefficient: rows[coefficient][column_index]
            for coefficient in ("K", "A4", "A6", "A8", "A10", "A12")
        }
        for column_index, surface_label in enumerate(_ABILITY_TWO_FIVE_ASPHERE_LABELS)
    }


def _ability_two_five_system_meta(page: dict[str, Any]) -> list[tuple[float, float, float]]:
    tokens = list(page["rapidocr_tokens"])
    column_tokens = [
        _ability_unique_token(tokens, label, min_confidence=0.97)
        for label in ("OL1", "OL2")
    ]
    column_xs = [_ability_token_center(token)[0] for token in column_tokens]
    rows: dict[str, list[float]] = {}
    for label in ("f (mm)", "Fno", "FOV (°)"):
        label_token = _ability_unique_token(tokens, label, min_confidence=0.95)
        _, row_y = _ability_token_center(label_token)
        rows[label] = [
            _parse_number(
                _ability_token_text(_ability_profile_number_token(tokens, x=x, y=row_y))
            )
            for x in column_xs
        ]
    metadata = list(zip(rows["f (mm)"], rows["Fno"], rows["FOV (°)"], strict=True))
    if any(f <= 0.0 or fno <= 0.0 or not 0.0 < fov < 180.0 for f, fno, fov in metadata):
        raise PatentParseError("Ability two-five-lens system metadata is outside physical bounds")
    return metadata


def _parse_ability_two_five_lens_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 12:
        raise PatentParseError("Ability two-five-lens PDF page count is not the retained layout")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 3:
        raise PatentParseError("Ability two-five-lens PDF must retain exactly three key pages")
    role_pages = (
        ("prescription_five_ol1", 4, "FIG. 3A", "FIG. 3B"),
        ("prescription_five_ol2", 5, "FIG. 4A", "FIG. 4B"),
    )
    prescription_pages: list[dict[str, Any]] = []
    for role, page_number, surface_figure, asphere_figure in role_pages:
        page = _ability_page(payload, role)
        if page.get("page_number") != page_number:
            raise PatentParseError(f"Ability two-five-lens role {role} is on the wrong page")
        mirror_text = page.get("mirror_text")
        if (
            not isinstance(mirror_text, str)
            or any(
                re.search(
                    rf"\bFig\s*\.\s*{re.escape(figure.removeprefix('FIG. '))}\b",
                    mirror_text,
                    flags=re.IGNORECASE,
                )
                is None
                for figure in (surface_figure, asphere_figure)
            )
            or any(
                marker.casefold() not in mirror_text.casefold()
                for marker in ("Surface", "Radius", "A12")
            )
        ):
            raise PatentParseError(
                f"Ability two-five-lens role {role} lacks figure/table markers"
            )
        prescription_pages.append(page)
    meta_page = _ability_page(payload, "system_meta_five")
    if meta_page.get("page_number") != 6:
        raise PatentParseError("Ability two-five-lens system metadata is not on page 6")
    mirror_meta = meta_page.get("mirror_text")
    if not isinstance(mirror_meta, str) or any(
        marker.casefold() not in mirror_meta.casefold()
        for marker in ("FIG . 5", "OL1", "OL2", "Fno", "FOV")
    ):
        raise PatentParseError("Ability two-five-lens metadata page lacks table markers")

    facts = payload.get("source_facts")
    expected_figure_counts = {
        "FIG. 3A": 1,
        "FIG. 3B": 1,
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 5": 2,
    }
    if not isinstance(facts, dict) or facts.get("figure_binding_counts") != expected_figure_counts:
        raise PatentParseError("Ability two-five-lens official figure bindings changed")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Ability two-five-lens official HTML hash is invalid")
    metadata = _ability_two_five_system_meta(meta_page)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, (profile, page, meta) in enumerate(
        zip(role_pages, prescription_pages, metadata, strict=True),
        start=1,
    ):
        _role, _page_number, surface_figure, asphere_figure = profile
        embodiment = f"Ability optical lens OL{embodiment_number}"
        try:
            surfaces = _ability_two_five_surface_table(
                page,
                surface_figure=surface_figure,
            )
            aspheres = _ability_two_five_aspheres(
                page,
                surface_figure=surface_figure,
                asphere_figure=asphere_figure,
            )
            surface_by_label = {surface.label: surface for surface in surfaces}
            for label, coefficients in aspheres.items():
                surface = surface_by_label[label]
                surface.surface_type = "ASP"
                if coefficients["K"] != 0.0:
                    surface.asphere_coefficients["K"] = coefficients["K"]
                surface.asphere_coefficients.update(
                    {key: value for key, value in coefficients.items() if key != "K"}
                )
            focal_length, f_number, full_fov = meta
            prescription = PatentPrescription(
                patent_id=str(payload["publication_id"]),
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=full_fov / 2.0,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retain each disclosed optical lens
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
        else:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    prescription=prescription,
                )
            )
    return attempts


def _largan_required_number_token(
    tokens: list[dict[str, Any]],
    *,
    x: float,
    y: float,
    context: str,
) -> dict[str, Any]:
    candidates = [
        token
        for token in tokens
        if abs(_ability_token_center(token)[0] - x) <= _ABILITY_COLUMN_X_TOLERANCE
        and abs(_ability_token_center(token)[1] - y) <= _ABILITY_ROW_Y_TOLERANCE
        and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
    ]
    if len(candidates) != 1:
        raise PatentParseError(
            f"Largan {context} has {len(candidates)} numeric OCR tokens"
        )
    token = candidates[0]
    confidence = _ability_token_confidence(token)
    if confidence < _ABILITY_OCR_NUMBER_CONFIDENCE:
        raise PatentParseError(
            f"Largan {context} token {_ability_token_text(token)!r} confidence "
            f"{confidence:.6f} is below {_ABILITY_OCR_NUMBER_CONFIDENCE:.6f}"
        )
    return token


def _largan_five_lens_surface_table(page: dict[str, Any]) -> list[PatentSurface]:
    """Parse one Largan five-lens table from coordinate OCR without repair."""

    tokens = list(page["rapidocr_tokens"])
    headers = {
        label: _ability_unique_token(tokens, label, min_confidence=0.95)
        for label in ("Surface #", "Curvature Radius", "Thickness", "Material", "Index", "Abbe #")
    }
    surface_x, header_y = _ability_token_center(headers["Surface #"])
    radius_x, _ = _ability_token_center(headers["Curvature Radius"])
    thickness_x, _ = _ability_token_center(headers["Thickness"])
    material_x, _ = _ability_token_center(headers["Material"])
    nd_x, _ = _ability_token_center(headers["Index"])
    vd_x, _ = _ability_token_center(headers["Abbe #"])

    row_tokens = [
        token
        for token in tokens
        if _ability_token_center(token)[1] > header_y
        and abs(_ability_token_center(token)[0] - surface_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and re.fullmatch(r"\d+", _ability_token_text(token))
    ]
    row_tokens.sort(key=lambda token: _ability_token_center(token)[1])
    if [_ability_token_text(token) for token in row_tokens] != [
        str(index) for index in range(15)
    ]:
        raise PatentParseError("Largan five-lens surface row sequence is not 0 through 14")
    for token in row_tokens:
        confidence = _ability_token_confidence(token)
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            raise PatentParseError(
                f"Largan surface label {_ability_token_text(token)!r} confidence "
                f"{confidence:.6f} is below {_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )

    surfaces: list[PatentSurface] = []
    radius_pattern = re.compile(
        rf"(?P<value>{NUMBER_PATTERN})(?P<asphere>\s*\(ASP\))?",
        flags=re.IGNORECASE,
    )
    for surface_number, row_token in enumerate(row_tokens[1:], start=1):
        _, row_y = _ability_token_center(row_token)
        radius_candidates = []
        for token in tokens:
            token_x, token_y = _ability_token_center(token)
            if (
                abs(token_x - radius_x) > _ABILITY_COLUMN_X_TOLERANCE
                or abs(token_y - row_y) > _ABILITY_ROW_Y_TOLERANCE
            ):
                continue
            token_text = _ability_token_text(token)
            if token_text.casefold() == "plano":
                if _ability_token_confidence(token) >= 0.97:
                    radius_candidates.append((token, None, False))
                continue
            match = radius_pattern.fullmatch(token_text)
            if match is not None:
                confidence = _ability_token_confidence(token)
                if confidence < _ABILITY_OCR_NUMBER_CONFIDENCE:
                    raise PatentParseError(
                        f"Largan surface {surface_number} radius token {token_text!r} "
                        f"confidence {confidence:.6f} is below "
                        f"{_ABILITY_OCR_NUMBER_CONFIDENCE:.6f}"
                    )
                radius_candidates.append(
                    (
                        token,
                        _parse_number(match.group("value")),
                        match.group("asphere") is not None,
                    )
                )
        if len(radius_candidates) != 1:
            raise PatentParseError(
                f"Largan five-lens surface {surface_number} radius has "
                f"{len(radius_candidates)} values above confidence gate"
            )
        _radius_token, radius, is_asphere = radius_candidates[0]

        if surface_number == 14:
            thickness = 0.0
        else:
            thickness = _parse_number(
                _ability_token_text(
                    _largan_required_number_token(
                        tokens,
                        x=thickness_x,
                        y=row_y,
                        context=f"surface {surface_number} thickness",
                    )
                )
            )

        material_tokens = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[0] - material_x)
            <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(_ability_token_center(token)[1] - row_y) <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_text(token).casefold() in {"plastic", "glass"}
            and _ability_token_confidence(token) >= _ABILITY_OCR_LABEL_CONFIDENCE
        ]
        if len(material_tokens) > 1:
            raise PatentParseError(
                f"Largan five-lens surface {surface_number} material label is ambiguous"
            )
        nd_token = _ability_number_token(tokens, x=nd_x, y=row_y, required=False)
        vd_token = _ability_number_token(tokens, x=vd_x, y=row_y, required=False)
        if bool(material_tokens) != bool(nd_token) or bool(nd_token) != bool(vd_token):
            raise PatentParseError(
                f"Largan five-lens surface {surface_number} material data is incomplete"
            )
        nd = _parse_number(_ability_token_text(nd_token)) if nd_token else None
        vd = _parse_number(_ability_token_text(vd_token)) if vd_token else None
        _validate_material_indices(
            surface_index=surface_number,
            nd=nd,
            vd=vd,
        )
        label = (
            "Stop"
            if surface_number == 1
            else "Image"
            if surface_number == 14
            else f"S{surface_number}"
        )
        surfaces.append(
            PatentSurface(
                index=len(surfaces) + 1,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material=None,
                nd=nd,
                vd=vd,
                surface_type="ASP" if is_asphere else None,
            )
        )
    return surfaces


_LARGAN_SCIENTIFIC_CELL_PATTERN = re.compile(
    r"[-+]?\d[.,]\d{5}E[-+]\d{2}",
    flags=re.IGNORECASE,
)


def _largan_normalized_scientific_values(text: str) -> list[str]:
    normalized = re.sub(
        r"([Ee])\s*([+-])\s*(\d{2})",
        r"\1\2\3",
        text.replace(",", "."),
    )
    return [match.group(0).upper() for match in _LARGAN_SCIENTIFIC_CELL_PATTERN.finditer(normalized)]


def _largan_five_lens_aspheres(
    page: dict[str, Any],
) -> dict[int, dict[str, float]]:
    """Parse two five-column coefficient grids only when both OCR views agree."""

    tokens = list(page["rapidocr_tokens"])
    mirror_text = page.get("mirror_text")
    if not isinstance(mirror_text, str):
        raise PatentParseError("Largan five-lens asphere page lacks OCR-overlay text")
    coordinate_values = [
        _ability_token_text(token).replace(",", ".").upper()
        for token in tokens
        if _LARGAN_SCIENTIFIC_CELL_PATTERN.fullmatch(
            _ability_token_text(token).replace(",", ".")
        )
        and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
    ]
    overlay_values = _largan_normalized_scientific_values(mirror_text)
    if sorted(coordinate_values) != sorted(overlay_values):
        raise PatentParseError(
            "Largan five-lens coefficient OCR views disagree or contain joined cells"
        )

    header_tokens = [
        token
        for token in tokens
        if _ability_token_text(token).casefold() == "surface #"
        and _ability_token_confidence(token) >= _ABILITY_OCR_LABEL_CONFIDENCE
    ]
    header_tokens.sort(key=lambda token: _ability_token_center(token)[1])
    if len(header_tokens) != 2:
        raise PatentParseError("Largan five-lens asphere table does not have two grids")
    coefficients = {
        surface_number: dict.fromkeys(
            ("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16"),
            0.0,
        )
        for surface_number in range(2, 12)
    }
    expected_groups = ((2, 3, 4, 5, 6), (7, 8, 9, 10, 11))
    row_labels = ("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16")
    for group_index, (header, expected_surfaces) in enumerate(
        zip(header_tokens, expected_groups, strict=True)
    ):
        header_x, header_y = _ability_token_center(header)
        next_y = (
            _ability_token_center(header_tokens[group_index + 1])[1]
            if group_index + 1 < len(header_tokens)
            else float("inf")
        )
        surface_headers = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[1] - header_y)
            <= _ABILITY_ROW_Y_TOLERANCE
            and _ability_token_center(token)[0] > header_x
            and re.fullmatch(r"\d+", _ability_token_text(token))
            and _ability_token_confidence(token) >= 0.90
        ]
        surface_headers.sort(key=lambda token: _ability_token_center(token)[0])
        if tuple(int(_ability_token_text(token)) for token in surface_headers) != (
            expected_surfaces
        ):
            raise PatentParseError("Largan five-lens asphere surface headers changed")
        column_xs = [_ability_token_center(token)[0] for token in surface_headers]

        normalized_row_tokens: dict[str, dict[str, Any]] = {}
        for token in tokens:
            token_x, token_y = _ability_token_center(token)
            if token_x >= min(column_xs) or not header_y < token_y < next_y:
                continue
            normalized = re.sub(r"[\s=]", "", _ability_token_text(token)).upper()
            if normalized in row_labels:
                if normalized in normalized_row_tokens:
                    raise PatentParseError(
                        f"Largan five-lens asphere row {normalized} is ambiguous"
                    )
                normalized_row_tokens[normalized] = token
        if tuple(label for label in row_labels if label in normalized_row_tokens) != row_labels:
            raise PatentParseError("Largan five-lens asphere coefficient rows are incomplete")
        for label in row_labels:
            _, row_y = _ability_token_center(normalized_row_tokens[label])
            for surface_number, column_x in zip(
                expected_surfaces,
                column_xs,
                strict=True,
            ):
                value_token = _ability_number_token(
                    tokens,
                    x=column_x,
                    y=row_y,
                    required=False,
                )
                if value_token is not None:
                    coefficients[surface_number][label] = _parse_number(
                        _ability_token_text(value_token)
                    )
    return coefficients


def _largan_three_five_lens_system_meta(
    page: dict[str, Any],
    surface_pages: list[dict[str, Any]],
) -> list[tuple[float, float, float]]:
    """Parse TABLE 7 metadata and cross-check each prescription page header."""

    tokens = list(page["rapidocr_tokens"])
    embodiment_header = _ability_unique_token(
        tokens,
        "Embodiment Embodiment Embodiment",
        min_confidence=0.95,
    )
    f_token = _ability_unique_token(tokens, "f", min_confidence=0.95)
    _, embodiment_y = _ability_token_center(embodiment_header)
    _, f_y = _ability_token_center(f_token)
    column_tokens = [
        token
        for token in tokens
        if embodiment_y < _ability_token_center(token)[1] < f_y
        and _ability_token_text(token) in {"1", "2", "3"}
        and _ability_token_confidence(token) >= 0.99
    ]
    column_tokens.sort(key=lambda token: _ability_token_center(token)[0])
    if [_ability_token_text(token) for token in column_tokens] != ["1", "2", "3"]:
        raise PatentParseError("Largan TABLE 7 embodiment columns changed")
    column_xs = [_ability_token_center(token)[0] for token in column_tokens]
    rows: dict[str, list[float]] = {}
    for label in ("f", "Fno", "HFOV"):
        label_token = _ability_unique_token(tokens, label, min_confidence=0.95)
        _, row_y = _ability_token_center(label_token)
        rows[label] = [
            _parse_number(
                _ability_token_text(
                    _largan_required_number_token(
                        tokens,
                        x=column_x,
                        y=row_y,
                        context=f"TABLE 7 {label} embodiment value",
                    )
                )
            )
            for column_x in column_xs
        ]
    metadata = list(zip(rows["f"], rows["Fno"], rows["HFOV"], strict=True))
    if any(
        focal <= 0.0 or f_number <= 0.0 or not 0.0 < hfov < 90.0
        for focal, f_number, hfov in metadata
    ):
        raise PatentParseError("Largan five-lens system metadata is outside physical bounds")
    for embodiment_number, (surface_page, expected) in enumerate(
        zip(surface_pages, metadata, strict=True),
        start=1,
    ):
        mirror_text = surface_page.get("mirror_text")
        if not isinstance(mirror_text, str):
            raise PatentParseError("Largan surface page lacks OCR-overlay text")
        match = re.search(
            rf"TABLE\s*{2 * embodiment_number - 1}\s*\(\s*Embodiment\s*"
            rf"{embodiment_number}\s*\).*?\bf\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm"
            rf".*?\bFno\s*=\s*(?P<fno>{NUMBER_PATTERN}).*?\bHFOV\s*=\s*"
            rf"(?P<hfov>{NUMBER_PATTERN})\s*deg",
            mirror_text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if match is None:
            raise PatentParseError(
                f"Largan embodiment {embodiment_number} overlay metadata is absent"
            )
        observed = tuple(
            _parse_number(match.group(label)) for label in ("f", "fno", "hfov")
        )
        if observed != expected:
            raise PatentParseError(
                f"Largan embodiment {embodiment_number} metadata OCR views disagree"
            )
    return metadata


def _parse_largan_three_five_lens_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 21:
        raise PatentParseError("Largan three-five-lens PDF page count is not retained")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 7:
        raise PatentParseError("Largan three-five-lens PDF must retain seven key pages")
    page_profiles = (
        ("largan_surface_1", 8, "largan_asphere_1", 9, "FIG . 7", "FIG . 8"),
        ("largan_surface_2", 10, "largan_asphere_2", 11, "FIG . 9", "FIG . 10"),
        ("largan_surface_3", 12, "largan_asphere_3", 13, "FIG . 11", "FIG . 12"),
    )
    surface_pages: list[dict[str, Any]] = []
    asphere_pages: list[dict[str, Any]] = []
    for surface_role, surface_number, asphere_role, asphere_number, surface_figure, asphere_figure in (
        page_profiles
    ):
        surface_page = _ability_page(payload, surface_role)
        asphere_page = _ability_page(payload, asphere_role)
        if (surface_page.get("page_number"), asphere_page.get("page_number")) != (
            surface_number,
            asphere_number,
        ):
            raise PatentParseError("Largan prescription role is on the wrong page")
        surface_text = surface_page.get("mirror_text")
        asphere_text = asphere_page.get("mirror_text")
        if not isinstance(surface_text, str) or any(
            marker.casefold() not in surface_text.casefold()
            for marker in (surface_figure, "Surface #", "Fno", "HFOV")
        ):
            raise PatentParseError("Largan surface page lacks required markers")
        if not isinstance(asphere_text, str) or any(
            marker.casefold() not in asphere_text.casefold()
            for marker in (asphere_figure, "Aspheric Coefficients", "Surface #")
        ):
            raise PatentParseError("Largan asphere page lacks required markers")
        surface_pages.append(surface_page)
        asphere_pages.append(asphere_page)
    meta_page = _ability_page(payload, "largan_system_meta")
    if meta_page.get("page_number") != 14:
        raise PatentParseError("Largan TABLE 7 metadata is not on page 14")
    mirror_meta = meta_page.get("mirror_text")
    if not isinstance(mirror_meta, str) or any(
        marker.casefold() not in mirror_meta.casefold()
        for marker in ("FIG . 13", "TABLE 7", "Embodiment", "Fno", "HFOV")
    ):
        raise PatentParseError("Largan TABLE 7 metadata page lacks required markers")

    facts = payload.get("source_facts")
    expected_figure_counts = {f"FIG. {number}": 1 for number in range(7, 14)}
    if not isinstance(facts, dict) or facts.get("figure_binding_counts") != expected_figure_counts:
        raise PatentParseError("Largan official figure bindings changed")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Largan official HTML hash is invalid")
    metadata = _largan_three_five_lens_system_meta(meta_page, surface_pages)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, (surface_page, asphere_page, meta) in enumerate(
        zip(surface_pages, asphere_pages, metadata, strict=True),
        start=1,
    ):
        embodiment = f"Largan five-lens embodiment {embodiment_number}"
        try:
            surfaces = _largan_five_lens_surface_table(surface_page)
            coefficients = _largan_five_lens_aspheres(asphere_page)
            surface_by_label = {surface.label: surface for surface in surfaces}
            for surface_number, values in coefficients.items():
                surface = surface_by_label[f"S{surface_number}"]
                surface.surface_type = "ASP"
                surface.asphere_coefficients.update(
                    {label: value for label, value in values.items() if value != 0.0}
                )
            focal_length, f_number, hfov = meta
            prescription = PatentPrescription(
                patent_id=str(payload["publication_id"]),
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=hfov,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
        except Exception as exc:  # noqa: BLE001 - retain each disclosed embodiment
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
        else:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    prescription=prescription,
                )
            )
    return attempts


def _ability_zoom_required_number_token(
    tokens: list[dict[str, Any]],
    *,
    x: float,
    y: float,
    context: str,
) -> dict[str, Any]:
    candidates = [
        token
        for token in tokens
        if abs(_ability_token_center(token)[0] - x) <= _ABILITY_COLUMN_X_TOLERANCE
        and abs(_ability_token_center(token)[1] - y) <= _ABILITY_ROW_Y_TOLERANCE
        and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
    ]
    if len(candidates) != 1:
        raise PatentParseError(
            f"Ability zoom {context} has {len(candidates)} numeric OCR tokens"
        )
    token = candidates[0]
    confidence = _ability_token_confidence(token)
    if confidence < _ABILITY_OCR_NUMBER_CONFIDENCE:
        raise PatentParseError(
            f"Ability zoom {context} token {_ability_token_text(token)!r} confidence "
            f"{confidence:.6f} is below {_ABILITY_OCR_NUMBER_CONFIDENCE:.6f}"
        )
    return token


def _ability_zoom_surface_census(page: dict[str, Any]) -> None:
    """Validate one variable-length zoom-state surface grid at unchanged gates."""

    tokens = list(page["rapidocr_tokens"])
    surface_header = _ability_unique_token(tokens, "Surface", min_confidence=0.95)
    curvature_header = _ability_unique_token(tokens, "Curvature", min_confidence=0.95)
    index_header = _ability_unique_token(tokens, "index", min_confidence=0.95)
    abbe_header = _ability_unique_token(tokens, "Abbe", min_confidence=0.95)
    surface_x, header_y = _ability_token_center(surface_header)
    radius_x, _ = _ability_token_center(curvature_header)
    nd_x, _ = _ability_token_center(index_header)
    vd_x, _ = _ability_token_center(abbe_header)
    thickness_x = (radius_x + nd_x) / 2.0

    row_tokens = [
        token
        for token in tokens
        if _ability_token_center(token)[1] > header_y
        and abs(_ability_token_center(token)[0] - surface_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and re.fullmatch(r"S\d+|STO|IMA", _ability_token_text(token), re.IGNORECASE)
    ]
    row_tokens.sort(key=lambda token: _ability_token_center(token)[1])
    observed = [_ability_token_text(token).upper() for token in row_tokens]
    surface_numbers = [
        int(label[1:]) for label in observed if re.fullmatch(r"S\d+", label)
    ]
    if (
        not surface_numbers
        or surface_numbers != list(range(1, max(surface_numbers) + 1))
        or observed.count("STO") != 1
        or observed.count("IMA") != 1
        or observed[-1] != "IMA"
    ):
        raise PatentParseError(
            "Ability zoom surface sequence is not S1..Sn with one STO and final IMA"
        )
    for token in row_tokens:
        confidence = _ability_token_confidence(token)
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            raise PatentParseError(
                f"Ability zoom surface label {_ability_token_text(token)!r} confidence "
                f"{confidence:.6f} is below {_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )

    for token in row_tokens:
        label = _ability_token_text(token).upper()
        _, row_y = _ability_token_center(token)
        if label != "IMA":
            _ability_zoom_required_number_token(
                tokens,
                x=thickness_x,
                y=row_y,
                context=f"{label} thickness",
            )
        if label == "STO":
            _ability_infinity_token(tokens, x=radius_x, y=row_y)
            continue
        if label == "IMA":
            continue
        _ability_zoom_required_number_token(
            tokens,
            x=radius_x,
            y=row_y,
            context=f"{label} radius",
        )
        nd_candidates = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[0] - nd_x) <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(_ability_token_center(token)[1] - row_y) <= _ABILITY_ROW_Y_TOLERANCE
            and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
        ]
        vd_candidates = [
            token
            for token in tokens
            if abs(_ability_token_center(token)[0] - vd_x) <= _ABILITY_COLUMN_X_TOLERANCE
            and abs(_ability_token_center(token)[1] - row_y) <= _ABILITY_ROW_Y_TOLERANCE
            and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
        ]
        if bool(nd_candidates) != bool(vd_candidates) or len(nd_candidates) > 1 or len(
            vd_candidates
        ) > 1:
            raise PatentParseError(f"Ability zoom {label} material columns are incomplete")
        if nd_candidates:
            _ability_zoom_required_number_token(
                tokens,
                x=nd_x,
                y=row_y,
                context=f"{label} refractive index",
            )
            _ability_zoom_required_number_token(
                tokens,
                x=vd_x,
                y=row_y,
                context=f"{label} Abbe number",
            )


def _parse_ability_zoom_two_state_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") not in {14, 15}:
        raise PatentParseError("Ability zoom PDF page count is not a retained layout")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 4:
        raise PatentParseError("Ability zoom PDF must retain exactly four key pages")
    state_profiles = (
        (1, "telescopic", "ability_zoom_telescopic", 4, "FIG . 3"),
        (2, "wide-angle", "ability_zoom_wide", 5, "FIG . 4"),
    )
    state_pages: list[dict[str, Any]] = []
    for _number, _state, role, page_number, figure in state_profiles:
        page = _ability_page(payload, role)
        mirror_text = page.get("mirror_text")
        if page.get("page_number") != page_number or not isinstance(mirror_text, str):
            raise PatentParseError(f"Ability zoom role {role} is not on its retained page")
        if any(
            marker.casefold() not in mirror_text.casefold()
            for marker in (figure, "Surface", "Curvature", "Thickness", "Abbe")
        ):
            raise PatentParseError(f"Ability zoom role {role} lacks table markers")
        state_pages.append(page)
    asphere_page = _ability_page(payload, "ability_zoom_asphere")
    meta_page = _ability_page(payload, "ability_zoom_meta")
    if (asphere_page.get("page_number"), meta_page.get("page_number")) != (6, 7):
        raise PatentParseError("Ability zoom FIG. 5/FIG. 6 pages are not retained")
    for page, required in (
        (asphere_page, ("FIG . 5", "K", "A4")),
        (meta_page, ("FIG . 6", "Fw", "Ft", "TTL", "Fno", "FOV")),
    ):
        mirror_text = page.get("mirror_text")
        if not isinstance(mirror_text, str) or any(
            marker.casefold() not in mirror_text.casefold() for marker in required
        ):
            raise PatentParseError("Ability zoom supporting page lacks required markers")

    facts = payload.get("source_facts")
    valid_counts = (
        {"FIG. 3": 1, "FIG. 4": 1, "FIG. 5": 1, "FIG. 6": 1},
        {"FIG. 3": 1, "FIG. 4": 1, "FIG. 5": 1, "FIG. 6": 2},
    )
    if not isinstance(facts, dict) or facts.get("figure_binding_counts") not in valid_counts:
        raise PatentParseError("Ability zoom official figure bindings changed")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Ability zoom official HTML hash is invalid")

    attempts: list[_PrescriptionParseAttempt] = []
    for (number, state, _role, _page_number, _figure), page in zip(
        state_profiles,
        state_pages,
        strict=True,
    ):
        embodiment = f"Ability zoom {state} state"
        try:
            _ability_zoom_surface_census(page)
            raise PatentParseError(
                "Ability zoom surface grid passed; asphere grid still requires cell splitting"
            )
        except Exception as exc:  # noqa: BLE001 - retain each disclosed zoom state
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=number,
                    embodiment=embodiment,
                    error=exc,
                )
            )
    return attempts


def _genius_four_lens_surface_labels(embodiment_number: int) -> tuple[str, ...]:
    prefix = str(embodiment_number)
    return (
        f"{prefix}00",
        f"{prefix}11",
        f"{prefix}12",
        f"{prefix}21",
        f"{prefix}22",
        f"{prefix}31",
        f"{prefix}32",
        f"{prefix}41",
        f"{prefix}42",
        f"{prefix}51",
        f"{prefix}52",
        f"{prefix}60",
    )


def _genius_page_binding_error(
    page: dict[str, Any],
    *,
    page_number: int,
    sheet_number: int,
    role: str,
) -> str | None:
    if page.get("page_number") != page_number:
        return f"{role} is not retained on page {page_number}"
    tokens = list(page.get("rapidocr_tokens") or [])
    sheet_matches = [
        token
        for token in tokens
        if f"Sheet {sheet_number} of 48" in _ability_token_text(token)
    ]
    if len(sheet_matches) != 1:
        return f"{role} has {len(sheet_matches)} drawing-sheet header tokens"
    confidence = _ability_token_confidence(sheet_matches[0])
    if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
        return (
            f"{role} drawing-sheet header confidence {confidence:.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return None


def _genius_optical_census_error(
    page: dict[str, Any],
    *,
    embodiment_number: int,
) -> str | None:
    tokens = list(page["rapidocr_tokens"])
    expected_labels = _genius_four_lens_surface_labels(embodiment_number)
    label_tokens: list[dict[str, Any]] = []
    for label in expected_labels:
        matches = [token for token in tokens if _ability_token_text(token) == label]
        if len(matches) != 1:
            return (
                f"optical table surface {label} has {len(matches)} exact OCR label tokens"
            )
        confidence = _ability_token_confidence(matches[0])
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            return (
                f"optical table surface {label} confidence {confidence:.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
        label_tokens.append(matches[0])

    radius_matches = [
        token
        for token in tokens
        if _ability_token_text(token).casefold() == "radius"
        and _ability_token_confidence(token) >= _ABILITY_OCR_LABEL_CONFIDENCE
    ]
    if len(radius_matches) != 1:
        return f"optical table has {len(radius_matches)} accepted Radius headers"
    radius_y = _ability_token_center(radius_matches[0])[1]
    surface_x = sum(_ability_token_center(token)[0] for token in label_tokens) / len(label_tokens)
    surface_header_candidates = [
        token
        for token in tokens
        if abs(_ability_token_center(token)[0] - surface_x) <= _ABILITY_COLUMN_X_TOLERANCE
        and abs(_ability_token_center(token)[1] - radius_y) <= _ABILITY_ROW_Y_TOLERANCE * 2
        and token not in label_tokens
    ]
    if len(surface_header_candidates) != 1:
        return (
            "optical table surface header has "
            f"{len(surface_header_candidates)} coordinate OCR candidates"
        )
    surface_header = surface_header_candidates[0]
    header_text = re.sub(r"\s+", "", _ability_token_text(surface_header)).casefold()
    header_confidence = _ability_token_confidence(surface_header)
    if header_text != "surface#":
        return (
            f"optical table surface header token {_ability_token_text(surface_header)!r} "
            f"does not equal 'Surface#' (confidence {header_confidence:.6f})"
        )
    if header_confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
        return (
            f"optical table Surface# confidence {header_confidence:.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return None


def _genius_asphere_census_error(
    page: dict[str, Any],
    *,
    embodiment_number: int,
) -> str | None:
    tokens = list(page["rapidocr_tokens"])
    prefix = str(embodiment_number)
    expected_surface_labels = tuple(
        f"{prefix}{suffix}" for suffix in ("11", "12", "21", "22", "31", "32", "41", "42")
    )
    for label in expected_surface_labels:
        matches = [token for token in tokens if _ability_token_text(token) == label]
        if len(matches) != 1:
            return f"asphere table surface {label} has {len(matches)} exact OCR label tokens"
        confidence = _ability_token_confidence(matches[0])
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            return (
                f"asphere table surface {label} confidence {confidence:.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )

    surface_headers = [
        token
        for token in tokens
        if re.sub(r"\s+", "", _ability_token_text(token)).casefold() == "surface#"
    ]
    if len(surface_headers) != 2:
        return f"asphere table has {len(surface_headers)} exact Surface# headers"
    for token in surface_headers:
        confidence = _ability_token_confidence(token)
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            return (
                f"asphere table Surface# confidence {confidence:.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )

    for label in ("K", "a4", "a6", "a8", "a10", "a12", "a14", "a16"):
        matches = [
            token
            for token in tokens
            if _ability_token_text(token).casefold() == label.casefold()
        ]
        if len(matches) != 2:
            return f"asphere coefficient label {label} has {len(matches)} exact OCR tokens"
        below_gate = [
            _ability_token_confidence(token)
            for token in matches
            if _ability_token_confidence(token) < _ABILITY_OCR_LABEL_CONFIDENCE
        ]
        if below_gate:
            return (
                f"asphere coefficient label {label} confidence {min(below_gate):.6f} "
                f"is below {_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
    return None


def _genius_comparison_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page["rapidocr_tokens"])
    fno_tokens = [
        token
        for token in tokens
        if _ability_token_text(token).casefold() == "fno"
    ]
    if len(fno_tokens) != 3:
        return f"FIG. 46 has {len(fno_tokens)} exact Fno row labels"
    expected_value_counts = (4, 4, 3)
    for panel, (label_token, expected_count) in enumerate(
        zip(
            sorted(fno_tokens, key=lambda token: _ability_token_center(token)[1]),
            expected_value_counts,
            strict=True,
        ),
        start=1,
    ):
        confidence = _ability_token_confidence(label_token)
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            return (
                f"FIG. 46 panel {panel} Fno label confidence {confidence:.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
        label_x, label_y = _ability_token_center(label_token)
        values = [
            token
            for token in tokens
            if _ability_token_center(token)[0] > label_x + _ABILITY_COLUMN_X_TOLERANCE
            and abs(_ability_token_center(token)[1] - label_y) <= _ABILITY_ROW_Y_TOLERANCE
            and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
        ]
        if len(values) != expected_count:
            return (
                f"FIG. 46 panel {panel} Fno row has {len(values)} numeric tokens; "
                f"expected {expected_count}"
            )
        below_gate = [
            token
            for token in values
            if _ability_token_confidence(token) < _ABILITY_OCR_NUMBER_CONFIDENCE
        ]
        if below_gate:
            token = min(below_gate, key=_ability_token_confidence)
            return (
                f"FIG. 46 panel {panel} Fno token {_ability_token_text(token)!r} confidence "
                f"{_ability_token_confidence(token):.6f} is below "
                f"{_ABILITY_OCR_NUMBER_CONFIDENCE:.6f}"
            )
    return None


def _parse_genius_four_lens_eleven_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 66:
        raise PatentParseError("Genius eleven-embodiment PDF page count is not 66")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 23:
        raise PatentParseError("Genius eleven-embodiment PDF must retain 23 key pages")
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius parser input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    comparison_counts = facts.get("comparison_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 22
        or set(figure_counts.values()) != {1}
        or not isinstance(comparison_counts, dict)
        or len(comparison_counts) != 2
        or set(comparison_counts.values()) != {1}
        or facts.get("fno_label_count") != 1
    ):
        raise PatentParseError("Genius official figure/Fno bindings changed")

    comparison_page = _ability_page(payload, "genius_comparison")
    comparison_binding_error = _genius_page_binding_error(
        comparison_page,
        page_number=47,
        sheet_number=46,
        role="genius_comparison",
    )
    comparison_census_error = _genius_comparison_census_error(comparison_page)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 12):
        optical_figure = 2 if embodiment_number == 1 else 4 * embodiment_number - 1
        asphere_figure = 4 * embodiment_number
        optical_page_number = optical_figure + 1
        asphere_page_number = asphere_figure + 1
        optical_page = _ability_page(payload, f"genius_optical_{embodiment_number}")
        asphere_page = _ability_page(payload, f"genius_asphere_{embodiment_number}")
        errors = [
            error
            for error in (
                _genius_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_figure,
                    role=f"genius_optical_{embodiment_number}",
                ),
                _genius_optical_census_error(
                    optical_page,
                    embodiment_number=embodiment_number,
                ),
                _genius_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_figure,
                    role=f"genius_asphere_{embodiment_number}",
                ),
                _genius_asphere_census_error(
                    asphere_page,
                    embodiment_number=embodiment_number,
                ),
                comparison_binding_error,
                comparison_census_error,
            )
            if error is not None
        ]
        if not errors:
            errors.append(
                "Genius optical/asphere/Fno census passed; numeric cell parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius four-lens embodiment {embodiment_number}",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


def _genius_six_page_binding_error(
    page: dict[str, Any],
    *,
    page_number: int,
    sheet_number: int,
    sheet_count: int,
    role: str,
) -> str | None:
    if page.get("page_number") != page_number:
        return f"{role} is not retained on page {page_number}"
    tokens = list(page.get("rapidocr_tokens") or [])
    sheet_matches = [
        token
        for token in tokens
        if f"Sheet {sheet_number} of {sheet_count}" in _ability_token_text(token)
    ]
    if len(sheet_matches) != 1:
        return f"{role} has {len(sheet_matches)} drawing-sheet header tokens"
    confidence = _ability_token_confidence(sheet_matches[0])
    if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
        return (
            f"{role} drawing-sheet header confidence {confidence:.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return None


def _genius_six_exact_label_error(
    tokens: list[dict[str, Any]],
    label: str,
    *,
    context: str,
    expected_count: int = 1,
) -> str | None:
    matches = [
        token
        for token in tokens
        if _ability_token_text(token).strip(" .:").casefold() == label.casefold()
    ]
    if len(matches) != expected_count:
        return (
            f"{context} label {label!r} has {len(matches)} exact OCR tokens; "
            f"expected {expected_count}"
        )
    below_gate = [
        _ability_token_confidence(token)
        for token in matches
        if _ability_token_confidence(token) < _ABILITY_OCR_LABEL_CONFIDENCE
    ]
    if below_gate:
        return (
            f"{context} label {label!r} confidence {min(below_gate):.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return None


def _genius_six_metadata_label_error(
    tokens: list[dict[str, Any]],
    label: str,
) -> str | None:
    pattern = re.compile(rf"(?:^|[\s(]){re.escape(label)}\)?\s*=", flags=re.IGNORECASE)
    matches = [token for token in tokens if pattern.search(_ability_token_text(token))]
    if len(matches) != 1:
        return f"optical metadata label {label} has {len(matches)} exact OCR prefixes"
    confidence = _ability_token_confidence(matches[0])
    if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
        return (
            f"optical metadata label {label} confidence {confidence:.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return None


def _genius_six_optical_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("EFL", "HFOV", "TTL", "Fno", "LCR"):
        error = _genius_six_metadata_label_error(tokens, label)
        if error is not None:
            return error
    for label in ("surface", "radius", "thickness", "Abbe"):
        error = _genius_six_exact_label_error(tokens, label, context="optical table")
        if error is not None:
            return error
    return None


def _genius_six_asphere_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("surface", "K", "a2", "a4", "a6", "a8", "a10", "a12", "a14", "a16"):
        error = _genius_six_exact_label_error(
            tokens,
            label,
            context="asphere table",
            expected_count=2 if label == "surface" else 1,
        )
        if error is not None:
            return error
    return None


def _genius_nine_lens_eleven_optical_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("EFL", "HFOV", "TTL", "Fno", "Image Height"):
        error = _genius_six_metadata_label_error(tokens, label)
        if error is not None:
            return error
    for label in ("Surface #", "curvature", "Thickness", "Material", "index", "number"):
        error = _genius_six_exact_label_error(tokens, label, context="optical table")
        if error is not None:
            return error
    return None


def _genius_nine_lens_eleven_asphere_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("Surface", "K", "a4", "a6", "a8", "a10", "a12", "a14", "a16"):
        error = _genius_six_exact_label_error(tokens, label, context="asphere table")
        if error is not None:
            return error
    return None


def _genius_eight_lens_fourteen_optical_census_error(
    page: dict[str, Any],
) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("EFL", "HFOV", "TTL", "Fno", "Image height"):
        error = _genius_six_metadata_label_error(tokens, label)
        if error is not None:
            return error
    for label in ("Surface", "Radius", "Thickness", "Material", "index", "number"):
        error = _genius_six_exact_label_error(tokens, label, context="optical table")
        if error is not None:
            return error
    return None


def _genius_six_lens_census_attempts(
    payload: dict[str, Any],
    *,
    embodiment_count: int,
    sheet_count: int | None = None,
    comparison_count: int = 2,
) -> list[_PrescriptionParseAttempt]:
    if sheet_count is None:
        sheet_count = 20 if embodiment_count == 5 else 32
    ordinals = (
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
        "sixth",
        "seventh",
        "eighth",
        "ninth",
    )[:embodiment_count]
    last_asphere_page = 7 + (embodiment_count - 1) * 3
    comparison_errors = []
    for index in range(1, comparison_count + 1):
        page_number = last_asphere_page + index
        page = _ability_page(payload, f"genius_six_comparison_{index}")
        error = _genius_six_page_binding_error(
            page,
            page_number=page_number,
            sheet_number=page_number - 1,
            sheet_count=sheet_count,
            role=f"genius_six_comparison_{index}",
        )
        if error is not None:
            comparison_errors.append(error)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, ordinal in enumerate(ordinals, start=1):
        optical_page_number = 6 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        optical_page = _ability_page(payload, f"genius_six_optical_{embodiment_number}")
        asphere_page = _ability_page(payload, f"genius_six_asphere_{embodiment_number}")
        errors = [
            error
            for error in (
                _genius_six_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_page_number - 1,
                    sheet_count=sheet_count,
                    role=f"genius_six_optical_{embodiment_number}",
                ),
                _genius_six_optical_census_error(optical_page),
                _genius_six_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_page_number - 1,
                    sheet_count=sheet_count,
                    role=f"genius_six_asphere_{embodiment_number}",
                ),
                _genius_six_asphere_census_error(asphere_page),
                *comparison_errors,
            )
            if error is not None
        ]
        if not errors:
            errors.append(
                "Genius six-lens optical/asphere census passed; numeric cell parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius six-lens {ordinal} embodiment",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


def _parse_genius_nine_lens_eleven_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 65:
        raise PatentParseError("Genius nine-lens eleven-embodiment PDF page count is not 65")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 24:
        raise PatentParseError(
            "Genius nine-lens eleven-embodiment PDF must retain 24 key pages"
        )
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError(
            "Genius nine-lens eleven-embodiment input lacks official source facts"
        )
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius nine-lens official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    comparison_counts = facts.get("comparison_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 22
        or set(figure_counts.values()) != {1}
        or not isinstance(comparison_counts, dict)
        or len(comparison_counts) != 2
        or set(comparison_counts.values()) != {1}
        or facts.get("genius_applicant_assignee_count") != 2
    ):
        raise PatentParseError("Genius nine-lens official figure/source bindings changed")

    comparison_errors = []
    for comparison, (page_number, sheet_number) in enumerate(((49, 47), (50, 48)), start=1):
        page = _ability_page(payload, f"genius_nine_eleven_comparison_{comparison}")
        error = _genius_six_page_binding_error(
            page,
            page_number=page_number,
            sheet_number=sheet_number,
            sheet_count=48,
            role=f"genius_nine_eleven_comparison_{comparison}",
        )
        if error is not None:
            comparison_errors.append(error)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 12):
        optical_page_number = 7 + (embodiment_number - 1) * 4
        asphere_page_number = optical_page_number + 1
        optical_page = _ability_page(
            payload,
            f"genius_nine_eleven_optical_{embodiment_number}",
        )
        asphere_page = _ability_page(
            payload,
            f"genius_nine_eleven_asphere_{embodiment_number}",
        )
        errors = [
            error
            for error in (
                _genius_six_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_page_number - 2,
                    sheet_count=48,
                    role=f"genius_nine_eleven_optical_{embodiment_number}",
                ),
                _genius_nine_lens_eleven_optical_census_error(optical_page),
                _genius_six_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_page_number - 2,
                    sheet_count=48,
                    role=f"genius_nine_eleven_asphere_{embodiment_number}",
                ),
                _genius_nine_lens_eleven_asphere_census_error(asphere_page),
                *comparison_errors,
            )
            if error is not None
        ]
        if not errors:
            errors.append(
                "Genius nine-lens eleven-embodiment census passed; numeric parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius nine-lens embodiment {embodiment_number}",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


def _parse_genius_eight_lens_fourteen_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 64:
        raise PatentParseError(
            "Genius eight-lens fourteen-embodiment PDF page count is not 64"
        )
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 30:
        raise PatentParseError(
            "Genius eight-lens fourteen-embodiment PDF must retain 30 key pages"
        )
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError(
            "Genius eight-lens fourteen-embodiment input lacks official source facts"
        )
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius eight-lens official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    comparison_counts = facts.get("comparison_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 28
        or set(figure_counts.values()) != {1}
        or not isinstance(comparison_counts, dict)
        or len(comparison_counts) != 3
        or set(comparison_counts.values()) != {1}
        or facts.get("genius_applicant_assignee_count") != 2
    ):
        raise PatentParseError("Genius eight-lens official figure/source bindings changed")

    comparison_errors = []
    for comparison, (page_number, sheet_number) in enumerate(((46, 45), (47, 46)), start=1):
        page = _ability_page(payload, f"genius_eight_fourteen_comparison_{comparison}")
        error = _genius_six_page_binding_error(
            page,
            page_number=page_number,
            sheet_number=sheet_number,
            sheet_count=46,
            role=f"genius_eight_fourteen_comparison_{comparison}",
        )
        if error is not None:
            comparison_errors.append(error)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 15):
        optical_page_number = 5 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        optical_page = _ability_page(
            payload,
            f"genius_eight_fourteen_optical_{embodiment_number}",
        )
        asphere_page = _ability_page(
            payload,
            f"genius_eight_fourteen_asphere_{embodiment_number}",
        )
        errors = [
            error
            for error in (
                _genius_six_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_page_number - 1,
                    sheet_count=46,
                    role=f"genius_eight_fourteen_optical_{embodiment_number}",
                ),
                _genius_eight_lens_fourteen_optical_census_error(optical_page),
                _genius_six_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_page_number - 1,
                    sheet_count=46,
                    role=f"genius_eight_fourteen_asphere_{embodiment_number}",
                ),
                _genius_six_asphere_census_error(asphere_page),
                *comparison_errors,
            )
            if error is not None
        ]
        if not errors:
            errors.append(
                "Genius eight-lens fourteen-embodiment census passed; numeric parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius eight-lens embodiment {embodiment_number}",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


def _parse_genius_six_lens_five_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 34:
        raise PatentParseError("Genius five-embodiment PDF page count is not 34")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 12:
        raise PatentParseError("Genius five-embodiment PDF must retain 12 key pages")
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius five-embodiment input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius five-embodiment official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 10
        or set(figure_counts.values()) != {1}
        or facts.get("comparison_binding_count") != 1
    ):
        raise PatentParseError("Genius five-embodiment official figure bindings changed")

    return _genius_six_lens_census_attempts(payload, embodiment_count=5)


def _parse_genius_six_lens_nine_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") not in {50, 51}:
        raise PatentParseError(
            "Genius nine-embodiment PDF page count is not retained 50/51 layout"
        )
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 20:
        raise PatentParseError("Genius nine-embodiment PDF must retain 20 key pages")
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius nine-embodiment input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius nine-embodiment official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    comparison_counts = facts.get("comparison_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 18
        or set(figure_counts.values()) != {1}
        or not isinstance(comparison_counts, dict)
        or len(comparison_counts) != 2
        or set(comparison_counts.values()) != {1}
    ):
        raise PatentParseError("Genius nine-embodiment official figure bindings changed")
    return _genius_six_lens_census_attempts(payload, embodiment_count=9)


def _parse_genius_six_lens_nine_comparison_variant_attempts(
    payload: dict[str, Any],
    *,
    page_count: int,
    sheet_count: int,
    comparison_count: int,
    expected_comparison_counts: dict[str, int],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != page_count:
        raise PatentParseError(
            f"Genius nine-embodiment PDF page count is not retained {page_count} layout"
        )
    pages = payload.get("pages")
    expected_key_pages = 18 + comparison_count
    if not isinstance(pages, list) or len(pages) != expected_key_pages:
        raise PatentParseError(
            f"Genius nine-embodiment PDF must retain {expected_key_pages} key pages"
        )
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius nine-embodiment input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius nine-embodiment official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 18
        or set(figure_counts.values()) != {1}
        or facts.get("comparison_binding_counts") != expected_comparison_counts
    ):
        raise PatentParseError("Genius nine-embodiment official figure bindings changed")
    return _genius_six_lens_census_attempts(
        payload,
        embodiment_count=9,
        sheet_count=sheet_count,
        comparison_count=comparison_count,
    )


def _genius_four_lens_nine_optical_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("EFL", "HFOV", "Fno"):
        error = _genius_six_metadata_label_error(tokens, label)
        if error is not None:
            return error
    system_length_matches = [
        token
        for token in tokens
        if re.search(r"(?:^|\s)System\s+length\s*=", _ability_token_text(token), re.IGNORECASE)
    ]
    if len(system_length_matches) != 1:
        return f"optical metadata label System length has {len(system_length_matches)} exact prefixes"
    confidence = _ability_token_confidence(system_length_matches[0])
    if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
        return (
            f"optical metadata label System length confidence {confidence:.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    for label in ("Surface", "curvature", "Material", "index", "number"):
        error = _genius_six_exact_label_error(tokens, label, context="optical table")
        if error is not None:
            return error
    return None


def _genius_four_lens_nine_asphere_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("Surface", "K", "a4", "a6", "a8", "a10", "a12", "a14", "a16"):
        error = _genius_six_exact_label_error(
            tokens,
            label,
            context="asphere table",
            expected_count=2 if label == "Surface" else 1,
        )
        if error is not None:
            return error
    return None


def _parse_genius_four_lens_nine_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 47:
        raise PatentParseError("Genius four-lens nine-embodiment PDF page count is not 47")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 22:
        raise PatentParseError("Genius four-lens nine-embodiment PDF must retain 22 key pages")
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius four-lens nine-embodiment input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius four-lens nine-embodiment official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    comparison_counts = facts.get("comparison_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 18
        or set(figure_counts.values()) != {1}
        or not isinstance(comparison_counts, dict)
        or len(comparison_counts) != 2
        or set(comparison_counts.values()) != {1}
    ):
        raise PatentParseError("Genius four-lens nine-embodiment figure bindings changed")

    comparison_errors = []
    for comparison in range(1, 5):
        page_number = 30 + comparison
        page = _ability_page(payload, f"genius_four_nine_comparison_{comparison}")
        error = _genius_six_page_binding_error(
            page,
            page_number=page_number,
            sheet_number=page_number - 1,
            sheet_count=33,
            role=f"genius_four_nine_comparison_{comparison}",
        )
        if error is not None:
            comparison_errors.append(error)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 10):
        optical_page_number = 5 + (embodiment_number - 1) * 3
        asphere_page_number = optical_page_number + 1
        optical_page = _ability_page(payload, f"genius_four_nine_optical_{embodiment_number}")
        asphere_page = _ability_page(payload, f"genius_four_nine_asphere_{embodiment_number}")
        errors = [
            error
            for error in (
                _genius_six_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_page_number - 1,
                    sheet_count=33,
                    role=f"genius_four_nine_optical_{embodiment_number}",
                ),
                _genius_four_lens_nine_optical_census_error(optical_page),
                _genius_six_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_page_number - 1,
                    sheet_count=33,
                    role=f"genius_four_nine_asphere_{embodiment_number}",
                ),
                _genius_four_lens_nine_asphere_census_error(asphere_page),
                *comparison_errors,
            )
            if error is not None
        ]
        if not errors:
            errors.append("Genius four-lens nine-embodiment census passed; numeric parser remains")
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius four-lens embodiment {embodiment_number}",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


def _ability_eight_lens_terminal_attempt(
    payload: dict[str, Any],
) -> _PrescriptionParseAttempt:
    """Classify one source-bound prescription whose system metadata is absent."""

    if payload.get("page_count") != 11:
        raise PatentParseError("Ability eight-lens PDF page count is not the retained layout")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 2:
        raise PatentParseError("Ability eight-lens PDF must retain exactly two key pages")
    surface_page = _ability_page(payload, "surface_single")
    asphere_page = _ability_page(payload, "asphere_single")
    if (surface_page.get("page_number"), asphere_page.get("page_number")) != (4, 5):
        raise PatentParseError("Ability eight-lens key pages are not FIG. 2/FIG. 3 pages 4/5")

    page_requirements = (
        (
            surface_page,
            ("Sheet 2 of 4", "FIG . 2", "Surface", "Curvature", "Thickness", "Abbe", "Conic"),
        ),
        (
            asphere_page,
            ("Sheet 3 of 4", "FIG . 3", "Aspheric", "coefficient", "A4", "A16"),
        ),
    )
    system_label_pattern = re.compile(r"\b(?:FNO|FOV|F)\b", flags=re.IGNORECASE)
    for page, required in page_requirements:
        mirror_text = page.get("mirror_text")
        if not isinstance(mirror_text, str) or any(
            marker.casefold() not in mirror_text.casefold() for marker in required
        ):
            raise PatentParseError("Ability eight-lens OCR overlay lacks a required figure marker")
        if system_label_pattern.search(mirror_text) is not None:
            raise PatentParseError(
                "Ability eight-lens OCR overlay contains possible F/FNO/FOV metadata"
            )
        rapidocr_text = " ".join(
            _ability_token_text(token) for token in page["rapidocr_tokens"]
        )
        if system_label_pattern.search(rapidocr_text) is not None:
            raise PatentParseError(
                "Ability eight-lens independent OCR contains possible F/FNO/FOV metadata"
            )

    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Ability eight-lens parser input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Ability eight-lens official HTML hash is invalid")
    expected_counts = {
        "surface_figure_binding_count": 2,
        "asphere_figure_binding_count": 2,
        "fno_definition_count": 1,
        "fov_definition_count": 4,
    }
    if any(facts.get(key) != expected for key, expected in expected_counts.items()):
        raise PatentParseError("Ability eight-lens official figure/definition counts changed")
    if facts.get("numeric_system_value_assignment_counts") != {
        "F": 0,
        "FNO": 0,
        "FOV": 0,
    }:
        raise PatentParseError("Ability eight-lens official HTML may publish system values")

    return _PrescriptionParseAttempt(
        embodiment_number=1,
        embodiment="Ability eight-lens FIG. 1 embodiment",
        error=PatentTerminalParseError(
            status="metadata_unpublished",
            reason_code="metadata_unpublished.system_f_fno_fov_values_absent",
            detail=(
                "official HTML and both exact-image OCR views publish no numeric "
                "F/FNO/FOV values for the sole FIG. 2/FIG. 3 prescription"
            ),
        ),
    )


def _ability_two_nine_lens_terminal_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    """Classify two prescriptions whose source publishes no F-number."""

    if payload.get("page_count") != 13:
        raise PatentParseError("Ability two-nine-lens PDF page count is not retained")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 3:
        raise PatentParseError("Ability two-nine-lens PDF must retain exactly three key pages")
    page_requirements = (
        (
            "prescription_nine_ol1",
            5,
            ("FIG . 4A", "FIG . 4B", "Surface", "Curvature", "A12"),
        ),
        (
            "prescription_nine_ol2",
            6,
            ("FIG . 5A", "FIG . 5B", "Surface", "Curvature", "A12"),
        ),
        (
            "system_meta_nine",
            7,
            ("FIG . 6", "Optical lens OL1", "Optical lens OL2", "TTL", "FOV"),
        ),
    )
    retained_pages: list[dict[str, Any]] = []
    for role, page_number, required in page_requirements:
        page = _ability_page(payload, role)
        if page.get("page_number") != page_number:
            raise PatentParseError(f"Ability two-nine-lens role {role} is on the wrong page")
        mirror_text = page.get("mirror_text")
        if not isinstance(mirror_text, str) or any(
            marker.casefold() not in mirror_text.casefold() for marker in required
        ):
            raise PatentParseError(
                f"Ability two-nine-lens role {role} lacks figure/table markers"
            )
        retained_pages.append(page)

    f_number_pattern = re.compile(
        r"\b(?:FNO|F\s*[- ]?number|F\s*/\s*#)\b",
        flags=re.IGNORECASE,
    )
    for page in retained_pages:
        mirror_text = str(page["mirror_text"])
        coordinate_text = " ".join(
            _ability_token_text(token) for token in page["rapidocr_tokens"]
        )
        if f_number_pattern.search(mirror_text) or f_number_pattern.search(coordinate_text):
            raise PatentParseError("Ability two-nine-lens OCR may publish an F-number")

    facts = payload.get("source_facts")
    expected_figure_counts = {
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 5A": 1,
        "FIG. 5B": 1,
        "FIG. 6": 2,
    }
    if not isinstance(facts, dict) or facts.get("figure_binding_counts") != expected_figure_counts:
        raise PatentParseError("Ability two-nine-lens official figure bindings changed")
    if facts.get("f_number_label_counts") != {"FNO": 0, "F-number": 0, "F/#": 0}:
        raise PatentParseError("Ability two-nine-lens official text may publish an F-number")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Ability two-nine-lens official HTML hash is invalid")

    return [
        _PrescriptionParseAttempt(
            embodiment_number=embodiment_number,
            embodiment=f"Ability optical lens OL{embodiment_number}",
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code="metadata_unpublished.system_f_number_absent",
                detail=(
                    "official HTML and both exact-raster OCR views publish no F-number "
                    f"for optical lens OL{embodiment_number}"
                ),
            ),
        )
        for embodiment_number in (1, 2)
    ]


def _ability_four_eight_lens_terminal_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    """Classify four eight-lens prescriptions whose source omits F-number."""

    if payload.get("page_count") != 14:
        raise PatentParseError("Ability four-eight-lens PDF page count is not retained")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 5:
        raise PatentParseError("Ability four-eight-lens PDF must retain exactly five key pages")
    page_requirements = (
        (
            "prescription_eight_ol1",
            3,
            ("FIG . 2A", "FIG . 2B", "Surface", "Curvature", "A12"),
        ),
        (
            "prescription_eight_ol2",
            4,
            ("FIG . 4A", "FIG . 4B", "Surface", "Curvature", "A12"),
        ),
        (
            "prescription_eight_ol3",
            6,
            ("FIG . 6A", "FIG . 6B", "Surface", "Curvature", "A12"),
        ),
        (
            "prescription_eight_ol4",
            7,
            ("FIG . 8", "Surface", "Curvature", "Thickness", "Abbe"),
        ),
        (
            "system_meta_four_eight",
            8,
            ("FIG . 9", "Optical lens OL1", "Optical lens OL4", "F1", "R1"),
        ),
    )
    retained_pages: list[dict[str, Any]] = []
    for role, page_number, required in page_requirements:
        page = _ability_page(payload, role)
        if page.get("page_number") != page_number:
            raise PatentParseError(
                f"Ability four-eight-lens role {role} is on the wrong page"
            )
        mirror_text = page.get("mirror_text")
        if not isinstance(mirror_text, str) or any(
            marker.casefold() not in mirror_text.casefold() for marker in required
        ):
            raise PatentParseError(
                f"Ability four-eight-lens role {role} lacks figure/table markers"
            )
        retained_pages.append(page)

    f_number_pattern = re.compile(
        r"\b(?:FNO|F\s*[- ]?number|F\s*/\s*#)\b",
        flags=re.IGNORECASE,
    )
    for page in retained_pages:
        mirror_text = str(page["mirror_text"])
        coordinate_text = " ".join(
            _ability_token_text(token) for token in page["rapidocr_tokens"]
        )
        if f_number_pattern.search(mirror_text) or f_number_pattern.search(coordinate_text):
            raise PatentParseError("Ability four-eight-lens OCR may publish an F-number")

    facts = payload.get("source_facts")
    expected_figure_counts = {
        "FIG. 2A": 1,
        "FIG. 2B": 1,
        "FIG. 4A": 1,
        "FIG. 4B": 1,
        "FIG. 6A": 1,
        "FIG. 6B": 1,
        "FIG. 8": 1,
        "FIG. 9": 2,
    }
    if not isinstance(facts, dict) or facts.get("figure_binding_counts") != expected_figure_counts:
        raise PatentParseError("Ability four-eight-lens official figure bindings changed")
    if facts.get("f_number_label_counts") != {"FNO": 0, "F-number": 0, "F/#": 0}:
        raise PatentParseError("Ability four-eight-lens official text may publish an F-number")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Ability four-eight-lens official HTML hash is invalid")

    return [
        _PrescriptionParseAttempt(
            embodiment_number=embodiment_number,
            embodiment=f"Ability optical lens OL{embodiment_number}",
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code="metadata_unpublished.system_f_number_absent",
                detail=(
                    "official HTML and both exact-raster OCR views publish no F-number "
                    f"for optical lens OL{embodiment_number}"
                ),
            ),
        )
        for embodiment_number in (1, 2, 3, 4)
    ]


def _validate_ability_pdf_source_linkage(payload: dict[str, Any]) -> None:
    """Validate the optional grant-to-prior-publication parser binding."""

    source_publication_id = payload.get("source_publication_id")
    if source_publication_id is None:
        return
    if (
        not isinstance(source_publication_id, str)
        or re.fullmatch(r"US-\d+-A\d+", source_publication_id) is None
        or source_publication_id == payload.get("publication_id")
    ):
        raise PatentParseError("Ability PDF OCR source publication id is invalid")
    linkage = payload.get("source_linkage")
    if not isinstance(linkage, dict) or linkage.get("kind") != (
        "uspto_prior_publication_data_same_application_v1"
    ):
        raise PatentParseError("Ability PDF OCR source linkage is missing")
    if linkage.get("grant_prior_publication_binding") is not True:
        raise PatentParseError("Ability PDF OCR grant prior-publication binding is absent")
    if linkage.get("exact_application_number_match") is not True:
        raise PatentParseError("Ability PDF OCR application-number linkage is absent")
    application_number = linkage.get("application_number")
    if not isinstance(application_number, str) or re.fullmatch(
        r"\d{2}/\d{6}", application_number
    ) is None:
        raise PatentParseError("Ability PDF OCR linkage application number is invalid")
    primary_digest = linkage.get("primary_html_sha256")
    source_digest = linkage.get("source_html_sha256")
    if any(
        not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        for digest in (primary_digest, source_digest)
    ):
        raise PatentParseError("Ability PDF OCR linkage HTML hash is invalid")
    source_facts = payload.get("source_facts")
    if not isinstance(source_facts, dict) or source_facts.get(
        "primary_html_sha256"
    ) != source_digest:
        raise PatentParseError("Ability PDF OCR source facts do not match linked HTML")


def _parse_ability_pdf_ocr_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    if not raw_text.lstrip().startswith("{") or _ABILITY_PDF_PARSER_FAMILY not in raw_text:
        return []
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PatentParseError("Ability PDF OCR parser input is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("parser_family") != _ABILITY_PDF_PARSER_FAMILY:
        return []
    if payload.get("schema_version") != 1:
        raise PatentParseError("unsupported Ability PDF OCR parser schema")
    if payload.get("publication_id") != patent_id:
        raise PatentParseError("Ability PDF OCR publication id does not match the candidate")
    _validate_ability_pdf_source_linkage(payload)
    profile = payload.get("profile")
    if profile == _ABILITY_EIGHT_LENS_PROFILE:
        return [_ability_eight_lens_terminal_attempt(payload)]
    if profile == _ABILITY_THREE_LENS_PROFILE:
        return _parse_ability_three_lens_attempts(payload)
    if profile == _ABILITY_TWO_FIVE_LENS_PROFILE:
        return _parse_ability_two_five_lens_attempts(payload)
    if profile == _ABILITY_TWO_NINE_LENS_PROFILE:
        return _ability_two_nine_lens_terminal_attempts(payload)
    if profile == _ABILITY_FOUR_EIGHT_LENS_PROFILE:
        return _ability_four_eight_lens_terminal_attempts(payload)
    if profile == _LARGAN_THREE_FIVE_LENS_PROFILE:
        return _parse_largan_three_five_lens_attempts(payload)
    if profile == _ABILITY_ZOOM_TWO_STATE_PROFILE:
        return _parse_ability_zoom_two_state_attempts(payload)
    if profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        return _parse_genius_four_lens_eleven_attempts(payload)
    if profile == _GENIUS_NINE_LENS_ELEVEN_PROFILE:
        return _parse_genius_nine_lens_eleven_attempts(payload)
    if profile == _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE:
        return _parse_genius_eight_lens_fourteen_attempts(payload)
    if profile == _GENIUS_FOUR_LENS_NINE_PROFILE:
        return _parse_genius_four_lens_nine_attempts(payload)
    if profile == _GENIUS_SIX_LENS_FIVE_PROFILE:
        return _parse_genius_six_lens_five_attempts(payload)
    if profile == _GENIUS_SIX_LENS_NINE_PROFILE:
        return _parse_genius_six_lens_nine_attempts(payload)
    if profile == _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE:
        return _parse_genius_six_lens_nine_comparison_variant_attempts(
            payload,
            page_count=48,
            sheet_count=33,
            comparison_count=3,
            expected_comparison_counts={"FIG. 43": 1, "FIG. 44": 1, "FIG. 45": 1},
        )
    if profile == _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE:
        return _parse_genius_six_lens_nine_comparison_variant_attempts(
            payload,
            page_count=50,
            sheet_count=34,
            comparison_count=4,
            expected_comparison_counts={
                "FIG. 43 to FIG. 46 illustrate all important parameters and numerical values "
                "of relational expressions for the optical lens element assemblies according "
                "to the first to ninth embodiments of the invention": 1,
                "FIG. 43 and FIG. 45": 5,
                "FIG. 44 and FIG. 46": 4,
            },
        )
    if profile is not None:
        raise PatentParseError(f"unsupported Ability PDF OCR profile: {profile}")
    surface_page = _ability_page(payload, "surface_ol2")
    meta_page = _ability_page(payload, "system_meta")
    # OL1 has a published asphere table, but its retained OCR views leave
    # cells unclassified.  Keep a per-embodiment failure instead of filling
    # those optical values.  OL2 is explicitly spherical in this layout and
    # can be recovered independently from FIG. 5 and FIG. 7.
    _ability_page(payload, "surface_ol1")
    _ability_page(payload, "asphere_ol1")
    attempts = [
        _PrescriptionParseAttempt(
            embodiment_number=1,
            embodiment="Optical lens OL1",
            error=PatentParseError(
                "Ability OL1 asphere cells are not independently classified; fail closed"
            ),
        )
    ]
    try:
        surfaces = _ability_surface_table(surface_page)
        focal_lengths = _ability_meta_row(meta_page, "F")
        full_fovs = _ability_meta_row(meta_page, "FOV")
        f_numbers = _ability_meta_row(meta_page, "FNO")
        focal_length = focal_lengths[1]
        full_fov = full_fovs[1]
        f_number = f_numbers[1]
        if focal_length <= 0.0 or f_number <= 0.0 or not 0.0 < full_fov < 180.0:
            raise PatentParseError("Ability OL2 has invalid published F/FNO/FOV values")
        prescription = PatentPrescription(
            patent_id=patent_id,
            embodiment="Optical lens OL2",
            focal_length_mm=focal_length,
            f_number=f_number,
            hfov_deg=full_fov / 2.0,
            surfaces=surfaces,
        )
        _validate_prescription_materials(prescription)
    except Exception as exc:  # noqa: BLE001 - per-embodiment fail-closed result
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=2,
                embodiment="Optical lens OL2",
                error=exc,
            )
        )
    else:
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=2,
                embodiment="Optical lens OL2",
                prescription=prescription,
            )
        )
    return attempts


def _parse_kantatsu_five_lens_ih_first_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse exact four-example five-lens tables recovered from a USPTO grant."""

    blocks = _patent_table_blocks(text)
    matched_headers = [
        _KANTATSU_FIVE_LENS_IH_FIRST_HEADER_PATTERN.search(block.text) for block in blocks
    ]
    bindings = list(_KANTATSU_FIVE_LENS_IH_FIRST_BINDING_PATTERN.finditer(text))
    # Family ownership is deliberately narrower than the shared metadata header.
    # Other Kantatsu A-publications use bracket paragraph numbers and/or publish
    # more than five tables; they must continue to their established parsers.
    if (
        not any(matched_headers)
        or [block.number for block in blocks] != list(range(1, 6))
        or len(bindings) != 4
    ):
        return []

    try:
        if _KANTATSU_FIVE_LENS_IH_FIRST_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu five-lens ih-first published half-field definition not found"
            )
        if _KANTATSU_FIVE_LENS_IH_FIRST_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu five-lens ih-first published A4-A20 asphere definition not found"
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
                    "Kantatsu five-lens ih-first narrative/header binding is not "
                    f"consecutive at example {example_number}"
                )
    except Exception as exc:  # noqa: BLE001 - retain all four disclosed examples
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu five-lens ih-first example {example_number}",
                error=exc,
            )
            for example_number in range(1, 5)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, block in enumerate(blocks[:4], start=1):
        embodiment = f"Kantatsu five-lens ih-first example {example_number}"
        try:
            header = _KANTATSU_FIVE_LENS_IH_FIRST_HEADER_PATTERN.search(block.text)
            if header is None:
                raise PatentParseError(
                    f"Kantatsu five-lens ih-first example {example_number} "
                    "header is source-damaged"
                )
            if (
                int(header.group("table")) != example_number
                or int(header.group("example")) != example_number
            ):
                raise PatentParseError(
                    f"Kantatsu five-lens ih-first example {example_number} "
                    "header is cross-bound"
                )

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
                family_label="Kantatsu five-lens ih-first",
            )
            if lens_surface_end != 11:
                raise PatentParseError(
                    f"Kantatsu five-lens ih-first example {example_number} lens surface "
                    f"coverage must end at 11, found {lens_surface_end}"
                )
            asphere_table_text = re.split(
                r"\s+\(\d+\)\s+The\s+imaging\s+lens\b",
                table_text,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            coefficients = _parse_kantatsu_inline_asphere_table(
                asphere_table_text,
                example_number=example_number,
                expected_source_surfaces=tuple(range(2, 12)),
                labels=("K", "A4", "A6", "A8", "A10", "A12", "A14", "A16", "A18", "A20"),
                family_label="Kantatsu five-lens ih-first",
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
                    f"Kantatsu five-lens ih-first example {example_number} has invalid "
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
        except Exception as exc:  # noqa: BLE001 - retain per published example
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


def _parse_kantatsu_missing_half_field_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain tables that define half field but publish no per-example value."""

    del patent_id  # Classification is source-bound and cannot produce a prescription.
    blocks = _patent_table_blocks(text)
    headers = [_KANTATSU_MISSING_HALF_FIELD_HEADER_PATTERN.search(block.text) for block in blocks]
    if not any(headers):
        return []

    bindings = list(_KANTATSU_MISSING_HALF_FIELD_BINDING_PATTERN.finditer(text))
    try:
        if [block.number for block in blocks] != list(range(1, 8)):
            raise PatentParseError(
                "Kantatsu missing-half-field family tables are not consecutive through the "
                "conditional-expression summary"
            )
        if len(bindings) != 6:
            raise PatentParseError(
                f"Kantatsu missing-half-field family must bind six examples, found {len(bindings)}"
            )
        if _KANTATSU_MISSING_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu missing-half-field published half-field definition not found"
            )
        if _KANTATSU_MISSING_HALF_FIELD_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu missing-half-field published A4-A20 asphere definition not found"
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
                    "Kantatsu missing-half-field narrative/header binding is not consecutive at "
                    f"example {example_number}"
                )
        if any(header is None for header in headers[:6]):
            raise PatentParseError("Kantatsu missing-half-field example headers are incomplete")
    except Exception as exc:  # noqa: BLE001 - retain all six disclosed examples
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu missing-half-field example {example_number}",
                error=exc,
            )
            for example_number in range(1, 7)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, header in enumerate(headers[:6], start=1):
        if header is None:  # pragma: no cover - guarded above
            raise AssertionError("missing header after family validation")
        if (
            int(header.group("table")) != example_number
            or int(header.group("example")) != example_number
        ):
            error = PatentParseError(
                f"Kantatsu missing-half-field example {example_number} header is cross-bound"
            )
        else:
            error = PatentParseError(
                f"Kantatsu missing-half-field example {example_number} published "
                "half-field value is absent from the table header"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu missing-half-field example {example_number}",
                error=error,
            )
        )
    return attempts


def _parse_kantatsu_damaged_metadata_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain four tables whose PPUBS metadata labels are source-damaged."""

    del patent_id  # Classification is source-bound and cannot produce a prescription.
    blocks = _patent_table_blocks(text)
    headers = [_KANTATSU_DAMAGED_METADATA_HEADER_PATTERN.search(block.text) for block in blocks]
    if not any(headers):
        return []

    bindings = list(_KANTATSU_DAMAGED_METADATA_BINDING_PATTERN.finditer(text))
    try:
        if [block.number for block in blocks] != list(range(1, 6)):
            raise PatentParseError(
                "Kantatsu damaged-metadata family tables are not consecutive through the "
                "conditional-expression summary"
            )
        if len(bindings) != 4:
            raise PatentParseError(
                f"Kantatsu damaged-metadata family must bind four examples, found {len(bindings)}"
            )
        if _KANTATSU_DAMAGED_METADATA_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu damaged-metadata published half-field definition not found"
            )
        if _KANTATSU_DAMAGED_METADATA_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError(
                "Kantatsu damaged-metadata published A4-A20 asphere definition not found"
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
                    "Kantatsu damaged-metadata narrative/header binding is not consecutive at "
                    f"example {example_number}"
                )
        if any(header is None for header in headers[:4]):
            raise PatentParseError("Kantatsu damaged-metadata example headers are incomplete")
    except Exception as exc:  # noqa: BLE001 - retain all four disclosed examples
        return [
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu damaged-metadata example {example_number}",
                error=exc,
            )
            for example_number in range(1, 5)
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, header in enumerate(headers[:4], start=1):
        if header is None:  # pragma: no cover - guarded above
            raise AssertionError("missing header after family validation")
        if (
            int(header.group("table")) != example_number
            or int(header.group("example")) != example_number
        ):
            error = PatentParseError(
                f"Kantatsu damaged-metadata example {example_number} header is cross-bound"
            )
        else:
            error = PatentParseError(
                f"Kantatsu damaged-metadata example {example_number} published "
                "ih/Fno/half-field labels are absent from the table header"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Kantatsu damaged-metadata example {example_number}",
                error=error,
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
    elif source_indices == [*range(1, 12), 18, 19]:
        # This five-lens family numbers the two published filter rows 18/19
        # after lens surface 11. Output indices follow physical row order.
        lens_surface_end, filter_front, filter_rear = 11, 18, 19
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


def _parse_samsung_even_order_table_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse Samsung S1-S16 even-order asphere table pairs independently.

    This family publishes ten TABLE pairs and explicitly defines ``HFOV`` as
    half field. Each coefficient table names polynomial orders through 30th
    order, so high-order mappings come from source row labels rather than from
    an inferred symbolic coefficient.
    """

    bindings = list(_SAMSUNG_EVEN_ORDER_BINDING_PATTERN.finditer(text))
    if _SAMSUNG_EVEN_ORDER_TITLE_PATTERN.search(text) is None or not bindings:
        return []

    embodiment_numbers = range(1, 11)

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Samsung even-order embodiment {embodiment_number}",
                error=exc,
            )
            for embodiment_number in embodiment_numbers
        ]

    try:
        if len(bindings) != 10:
            raise PatentParseError(
                f"Samsung even-order family must bind 10 embodiments, found {len(bindings)}"
            )
        if _SAMSUNG_EVEN_ORDER_HALF_FIELD_DEFINITION.search(text) is None:
            raise PatentParseError("Samsung even-order half-field HFOV definition not found")
        if _SAMSUNG_EVEN_ORDER_ASPHERE_DEFINITION.search(text) is None:
            raise PatentParseError("Samsung even-order asphere equation definition not found")
        blocks = _numbered_patent_table_blocks(text)
        if set(blocks) != set(range(1, 24)):
            raise PatentParseError(
                "Samsung even-order family must contain exactly TABLE 1 through 23"
            )
        for embodiment_number, binding in enumerate(bindings, start=1):
            if (
                int(binding.group("surface_table")) != embodiment_number * 2 - 1
                or int(binding.group("asphere_table")) != embodiment_number * 2
            ):
                raise PatentParseError(
                    "Samsung even-order table binding is not consecutive at "
                    f"embodiment {embodiment_number}"
                )
        metadata = _parse_samsung_even_order_metadata(blocks)
        if set(metadata) != set(embodiment_numbers):
            raise PatentParseError("Samsung even-order metadata does not cover embodiments 1-10")
    except Exception as exc:  # noqa: BLE001 - retain the disclosed embodiment set
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in embodiment_numbers:
        embodiment = f"Samsung even-order embodiment {embodiment_number}"
        try:
            surface_table = embodiment_number * 2 - 1
            asphere_table = embodiment_number * 2
            surfaces = _parse_samsung_even_order_surface_table(
                blocks[surface_table],
                embodiment_number=embodiment_number,
            )
            coefficients = _parse_samsung_even_order_asphere_table(
                blocks[asphere_table],
                embodiment_number=embodiment_number,
            )
            if set(coefficients) != set(range(1, 17)):
                raise PatentParseError(
                    f"Samsung even-order embodiment {embodiment_number} asphere coverage "
                    "must be S1-S16"
                )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
            focal_length, f_number, half_field = metadata[embodiment_number]
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=embodiment,
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
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


def _parse_samsung_even_order_metadata(
    blocks: dict[int, str],
) -> dict[int, tuple[float, float, float]]:
    table = blocks.get(21)
    if table is None:
        raise PatentParseError("Samsung even-order TABLE 21 metadata not found")
    first_header = re.search(
        r"\bFirst\s+Second\s+Third\s+Fourth\s+Fifth\s+Elements\s+"
        r"(?:embodiment\s+){4}embodiment\s+",
        table,
        flags=re.IGNORECASE,
    )
    second_header = re.search(
        r"\bSixth\s+Seventh\s+Eighth\s+Ninth\s+Tenth\s+Elements\s+"
        r"(?:embodiment\s+){4}embodiment\s+",
        table,
        flags=re.IGNORECASE,
    )
    if first_header is None or second_header is None or second_header.start() <= first_header.end():
        raise PatentParseError("Samsung even-order TABLE 21 metadata headers are incomplete")

    metadata: dict[int, tuple[float, float, float]] = {}
    sections = (
        (range(1, 6), table[first_header.end() : second_header.start()]),
        (range(6, 11), table[second_header.end() :]),
    )
    for embodiment_numbers, section in sections:
        focal_lengths = _parse_samsung_even_order_five_value_row(
            section,
            label_pattern=r"f",
            label="f",
        )
        f_numbers = _parse_samsung_even_order_five_value_row(
            section,
            label_pattern=r"f-number",
            label="f-number",
        )
        half_fields = _parse_samsung_even_order_five_value_row(
            section,
            label_pattern=r"HFOV(?:\(°\))?",
            label="HFOV",
        )
        for embodiment_number, focal_length, f_number, half_field in zip(
            embodiment_numbers,
            focal_lengths,
            f_numbers,
            half_fields,
            strict=True,
        ):
            metadata[embodiment_number] = (focal_length, f_number, half_field)
    return metadata


def _parse_samsung_even_order_five_value_row(
    text: str,
    *,
    label_pattern: str,
    label: str,
) -> tuple[float, ...]:
    value_sequence = rf"(?P<values>(?:{NUMBER_PATTERN}\s+){{4}}{NUMBER_PATTERN})"
    matches = list(
        re.finditer(
            rf"(?<!\S)(?:{label_pattern})(?!\S)\s+{value_sequence}",
            text,
            flags=re.IGNORECASE,
        )
    )
    if len(matches) != 1:
        raise PatentParseError(
            f"Samsung even-order metadata row {label} must occur exactly once per half"
        )
    return tuple(_parse_number(token) for token in matches[0].group("values").split())


def _parse_samsung_even_order_surface_table(
    table_text: str,
    *,
    embodiment_number: int,
) -> list[PatentSurface]:
    starts = list(re.finditer(r"(?<!\S)S(?P<index>\d+)\s+", table_text, re.IGNORECASE))
    indices = [int(match.group("index")) for match in starts]
    if indices != list(range(1, 20)):
        raise PatentParseError(
            f"Samsung even-order embodiment {embodiment_number} surface sequence must be S1-S19"
        )
    header = re.sub(
        r"\ATABLE-US-\d+\s+TABLE\s+\d+\s+",
        "",
        table_text[: starts[0].start()],
        flags=re.IGNORECASE,
    ).strip()
    if header not in _SAMSUNG_EVEN_ORDER_SURFACE_HEADERS:
        raise PatentParseError(
            f"Samsung even-order embodiment {embodiment_number} surface header is unsupported"
        )

    label_tokens: dict[int, tuple[str, ...]] = {
        1: ("First", "lens"),
        3: ("Second", "lens"),
        4: ("Stop",),
        5: ("Third", "lens"),
        7: ("Fourth", "lens"),
        9: ("Fifth", "lens"),
        11: ("Sixth", "lens"),
        13: ("Seventh", "lens"),
        15: ("Eighth", "lens"),
        17: ("Filter",),
        19: ("Imaging", "plane"),
    }
    material_surfaces = {1, 3, 5, 7, 9, 11, 13, 15, 17}
    surfaces: list[PatentSurface] = []
    for row_index, match in enumerate(starts):
        surface_index = int(match.group("index"))
        end = starts[row_index + 1].start() if row_index + 1 < len(starts) else len(table_text)
        tokens = table_text[match.end() : end].split()
        values = [
            token
            for token in tokens
            if token.upper() == "INFINITY" or re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE)
        ]
        residue = [
            token.lower()
            for token in tokens
            if token.upper() != "INFINITY"
            and re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE) is None
        ]
        expected_label = [token.lower() for token in label_tokens.get(surface_index, ())]
        if residue != expected_label:
            raise PatentParseError(
                f"Samsung even-order embodiment {embodiment_number} surface "
                f"S{surface_index} label mismatch"
            )
        expected_values = 5 if surface_index in material_surfaces else 3
        if len(values) != expected_values:
            raise PatentParseError(
                f"Samsung even-order embodiment {embodiment_number} surface S{surface_index} "
                f"has {len(values)} values, expected {expected_values}"
            )
        radius = _distance_value(
            values[0],
            field_name=f"Samsung even-order S{surface_index} radius",
        )
        thickness = _distance_value(
            values[1],
            field_name=f"Samsung even-order S{surface_index} thickness",
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
                f"Samsung even-order embodiment {embodiment_number} surface "
                f"S{surface_index} effective radius must be positive"
            )
        label = " ".join(label_tokens.get(surface_index, ())) or f"Surface {surface_index}"
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


def _parse_samsung_even_order_asphere_table(
    table_text: str,
    *,
    embodiment_number: int,
) -> dict[int, dict[str, float]]:
    header_pattern = re.compile(
        r"\bSurface\s+No\.?\s+(?P<labels>(?:S\d+\s+){7}S\d+)\s+",
        flags=re.IGNORECASE,
    )
    headers = list(header_pattern.finditer(table_text))
    if len(headers) != 2:
        raise PatentParseError(
            f"Samsung even-order embodiment {embodiment_number} must have two asphere headers"
        )
    expected_groups = (tuple(range(1, 9)), tuple(range(9, 17)))
    parsed_groups = tuple(
        tuple(int(token[1:]) for token in header.group("labels").split())
        for header in headers
    )
    if parsed_groups != expected_groups:
        raise PatentParseError(
            f"Samsung even-order embodiment {embodiment_number} asphere headers must be "
            "S1-S8 and S9-S16"
        )

    coefficients: dict[int, dict[str, float]] = {}
    sections = (
        (expected_groups[0], table_text[headers[0].end() : headers[1].start()]),
        (expected_groups[1], table_text[headers[1].end() :]),
    )
    row_labels = ("K",) + tuple(
        f"{order}{'nd' if order == 22 else 'th'}" for order in range(4, 31, 2)
    )
    row_pattern = re.compile(
        r"(?<!\S)(?:K|4th|6th|8th|10th|12th|14th|16th|18th|20th|22nd|"
        r"24th|26th|28th|30th)(?!\S)",
        flags=re.IGNORECASE,
    )
    for surface_indices, section in sections:
        section = re.split(
            r"\s+(?:\(\d+\)|\[\d+\])\s+",
            section,
            maxsplit=1,
        )[0]
        row_starts = list(row_pattern.finditer(section))
        if tuple(match.group(0).upper() for match in row_starts) != tuple(
            label.upper() for label in row_labels
        ):
            raise PatentParseError(
                f"Samsung even-order embodiment {embodiment_number} coefficient rows "
                "must be K and even orders 4-30"
            )
        for row_index, match in enumerate(row_starts):
            end = (
                row_starts[row_index + 1].start()
                if row_index + 1 < len(row_starts)
                else len(section)
            )
            row_tokens = section[match.start() : end].split()
            numeric_tokens = [
                token
                for token in row_tokens
                if re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE)
            ]
            residue = [
                token.lower()
                for token in row_tokens
                if re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE) is None
            ]
            expected_residue = (
                [match.group(0).lower()]
                if match.group(0).upper() == "K"
                else [match.group(0).lower(), "order", "term"]
            )
            if residue != expected_residue or len(numeric_tokens) != 8:
                raise PatentParseError(
                    f"Samsung even-order embodiment {embodiment_number} coefficient row "
                    f"{match.group(0)} is incomplete"
                )
            codev_label = "K"
            if match.group(0).upper() != "K":
                order_match = re.match(r"\d+", match.group(0))
                if order_match is None:
                    raise PatentParseError("Samsung even-order coefficient label is invalid")
                codev_label = ASPHERE_ORDER_TO_CODEV[int(order_match.group(0))]
            for surface_index, token in zip(surface_indices, numeric_tokens, strict=True):
                coefficients.setdefault(surface_index, {})[codev_label] = _parse_number(token)
    return coefficients


def _parse_samsung_eight_lens_missing_stop_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify five source-complete tables whose axial stop coordinate is absent.

    The official family publishes S1-S19 surface tables and states only that ST
    may lie somewhere in the S4-S5 air gap.  Selecting an endpoint or splitting
    that gap would invent a number, so these embodiments are terminal source
    outcomes rather than conversion candidates.
    """

    bindings = list(_SAMSUNG_EIGHT_LENS_BINDING_PATTERN.finditer(text))
    if not bindings:
        return []

    embodiment_numbers = range(1, 6)

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Samsung eight-lens example {embodiment_number}",
                error=exc,
            )
            for embodiment_number in embodiment_numbers
        ]

    try:
        if len(bindings) != 5:
            raise PatentParseError(
                f"Samsung eight-lens family must bind five examples, found {len(bindings)}"
            )
        blocks = _numbered_patent_table_blocks(text)
        if set(blocks) != set(range(1, 13)):
            raise PatentParseError("Samsung eight-lens family must contain TABLE 1 through 12")
        stops = list(_SAMSUNG_EIGHT_LENS_STOP_PATTERN.finditer(text))
        if len(stops) != 5 or len(re.findall(r"\bstop\s+ST\b", text, re.IGNORECASE)) != 10:
            raise PatentParseError(
                "Samsung eight-lens stop disclosures are incomplete or contain an extra binding"
            )
        if (
            re.search(
                r"[“\"]A\s+to\s+J[”\"]\s+are\s+aspheric\s+constants\b",
                text,
                flags=re.IGNORECASE,
            )
            is None
        ):
            raise PatentParseError("Samsung eight-lens A-J asphere definition not found")
        for embodiment_number, (binding, stop) in enumerate(zip(bindings, stops, strict=True), 1):
            expected_surface_table = embodiment_number * 2 - 1
            expected_asphere_table = embodiment_number * 2
            expected_system = embodiment_number * 100
            if (
                int(binding.group("surface_table")) != expected_surface_table
                or int(binding.group("asphere_table")) != expected_asphere_table
                or int(binding.group("system")) != expected_system
                or int(stop.group("second")) != expected_system + 20
                or int(stop.group("third")) != expected_system + 30
            ):
                raise PatentParseError(
                    "Samsung eight-lens table/stop binding is not consecutive at "
                    f"example {embodiment_number}"
                )
            _validate_samsung_eight_lens_surface_table(
                blocks[expected_surface_table],
                embodiment_number=embodiment_number,
            )
            _validate_samsung_eight_lens_asphere_table(
                blocks[expected_asphere_table],
                embodiment_number=embodiment_number,
            )
        _validate_samsung_eight_lens_metadata_table(blocks[11])
    except Exception as exc:  # noqa: BLE001 - retain all five disclosed examples
        return attempts_for_error(exc)

    detail = (
        "official S1-S19 tables omit a stop row and disclose ST only as somewhere between "
        "the second and third lenses; the axial stop coordinate is not published"
    )
    return attempts_for_error(
        PatentTerminalParseError(
            status="metadata_unpublished",
            reason_code="metadata_unpublished.stop_axial_coordinate_absent",
            detail=detail,
        )
    )


def _validate_samsung_eight_lens_surface_table(
    table_text: str,
    *,
    embodiment_number: int,
) -> None:
    header = _SAMSUNG_EIGHT_LENS_SURFACE_HEADER_PATTERN.search(table_text)
    if header is None:
        raise PatentParseError(
            f"Samsung eight-lens example {embodiment_number} surface header not found"
        )
    body = re.split(
        r"\s+(?:\(\d+\)|\[\d+\])\s+",
        table_text[header.end() :],
        maxsplit=1,
    )[0]
    indices = [
        int(match.group("index"))
        for match in re.finditer(r"(?<!\S)S(?P<index>\d+)\s+", body, re.IGNORECASE)
    ]
    if indices != list(range(1, 20)):
        raise PatentParseError(
            f"Samsung eight-lens example {embodiment_number} surface sequence must be S1-S19"
        )
    if re.search(r"\b(?:stop|ST)\b", body, re.IGNORECASE) is not None:
        raise PatentParseError(
            f"Samsung eight-lens example {embodiment_number} unexpectedly contains a stop row"
        )


def _validate_samsung_eight_lens_asphere_table(
    table_text: str,
    *,
    embodiment_number: int,
) -> None:
    first_header = _SAMSUNG_EIGHT_LENS_ASPHERE_HEADER_PATTERN.search(table_text)
    continuation = _SAMSUNG_EIGHT_LENS_ASPHERE_CONTINUATION_PATTERN.search(table_text)
    if (
        first_header is None
        or continuation is None
        or continuation.start() <= first_header.end()
    ):
        raise PatentParseError(
            f"Samsung eight-lens example {embodiment_number} asphere headers are incomplete"
        )
    first_indices = [
        int(value)
        for value in re.findall(
            r"(?<!\S)S(\d+)\s+",
            table_text[first_header.end() : continuation.start()],
            flags=re.IGNORECASE,
        )
    ]
    continuation_body = re.split(
        r"\s+(?:\(\d+\)|\[\d+\])\s+",
        table_text[continuation.end() :],
        maxsplit=1,
    )[0]
    second_indices = [
        int(value)
        for value in re.findall(
            r"(?<!\S)S(\d+)\s+",
            continuation_body,
            flags=re.IGNORECASE,
        )
    ]
    expected = list(range(1, 17))
    if first_indices != expected or second_indices != expected:
        raise PatentParseError(
            f"Samsung eight-lens example {embodiment_number} asphere rows must be S1-S16 twice"
        )


def _validate_samsung_eight_lens_metadata_table(table_text: str) -> None:
    if (
        re.search(
            r"\bFirst\s+Second\s+Third\s+Fourth\s+Fifth\s+Note\s+"
            r"Example\s+Example\s+Example\s+Example\s+Example\s+",
            table_text,
            flags=re.IGNORECASE,
        )
        is None
    ):
        raise PatentParseError("Samsung eight-lens TABLE 11 example header not found")
    for label in (r"f\s+number", "FOV", "f"):
        matches = list(
            re.finditer(
                rf"(?<!\S){label}(?!\S)\s+"
                rf"(?P<values>(?:{NUMBER_PATTERN}\s+){{4}}{NUMBER_PATTERN})(?!\S)",
                table_text,
                flags=re.IGNORECASE,
            )
        )
        if len(matches) != 1:
            raise PatentParseError(
                f"Samsung eight-lens TABLE 11 metadata row {label} is missing or ambiguous"
            )


def _classify_surface_texture_acquisition_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify one exact machine-vision camera/illumination architecture family."""

    if _SURFACE_TEXTURE_ACQUISITION_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    embodiment = "surface-texture machine-vision architecture"
    try:
        if _patent_table_blocks(text):
            raise PatentParseError(
                "surface-texture acquisition family unexpectedly contains PPUBS tables"
            )
        expected_phrase_counts = {
            "vision system camera assembly": 7,
            "105-millimeter focal length": 1,
            "spaced apart axially by approximately 1 millimeter": 1,
            "semi-reflecting mirror": 4,
            "structured illumination": 2,
            "FIG. 10 is a schematic diagram of an alternate arrangement": 1,
        }
        for phrase, expected in expected_phrase_counts.items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"surface-texture acquisition phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"\b(?:Curvature\s+Radius|Aspheric\s+Coefficients|Abbe\s+(?:Number|#)|"
            r"Surface\s+#|Fno|F\s*[- ]?number)\b",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "surface-texture acquisition family contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain exact-title structural drift
        return [
            _PrescriptionParseAttempt(
                embodiment_number=None,
                embodiment=embodiment,
                error=exc,
            )
        ]
    return [
        _PrescriptionParseAttempt(
            embodiment_number=None,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code=(
                    "confirmed_no_prescription.surface_texture_acquisition_architecture_only"
                ),
                detail=(
                    "official PPUBS text discloses a machine-vision camera, structured "
                    "illumination, mirror, and spaced catalog-like lenses but publishes "
                    "no optical surface prescription or prescription table"
                ),
            ),
        )
    ]


def _classify_ir_filter_coating_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify the exact 78-table IR-coating document as no prescription."""

    if _IR_FILTER_COATING_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    embodiment = "IR-filter coating document"
    try:
        blocks = _patent_table_blocks(text)
        if [block.number for block in blocks] != list(range(1, 79)):
            raise PatentParseError("IR-filter coating family must contain TABLE 1 through 78")
        allowed_table_marker = re.compile(
            r"(?:\bWavelength\s+\(nm\)|\bLayer\b|\bMaterial\b|"
            r"\bTotal\s+(?:amount|number)\b|\bPhysical\s+total\s+thickness\b)",
            flags=re.IGNORECASE,
        )
        if any(allowed_table_marker.search(block.text) is None for block in blocks):
            raise PatentParseError("IR-filter coating family contains an unclassified table")
        table_text = " ".join(block.text for block in blocks)
        if re.search(
            r"\b(?:curvature|Abbe|surface\s+No\.|FOV|HFOV|f\s+number|focal\s+length)\b",
            table_text,
            flags=re.IGNORECASE,
        ):
            raise PatentParseError(
                "IR-filter coating family unexpectedly contains prescription-table markers"
            )
        if len(re.findall(r"\baperture\s+stop\s+60\b", text, re.IGNORECASE)) != 1:
            raise PatentParseError("IR-filter coating family aperture narrative is incomplete")
    except Exception as exc:  # noqa: BLE001 - retain exact-title structural damage
        return [
            _PrescriptionParseAttempt(
                embodiment_number=None,
                embodiment=embodiment,
                error=exc,
            )
        ]
    return [
        _PrescriptionParseAttempt(
            embodiment_number=None,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code="confirmed_no_prescription.ir_filter_coating_tables_only",
                detail=(
                    "all 78 official PPUBS tables disclose only thin-film material, layer "
                    "thickness, wavelength, or transmittance data; no optical surface "
                    "prescription is published"
                ),
            ),
        )
    ]


def _classify_lens_driving_mechanical_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify two exact official lens-driving mechanical disclosures."""

    if _LENS_DRIVING_MECHANICAL_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _LENS_DRIVING_MECHANICAL_ONLY_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    embodiment = "imaging-lens driving mechanical architecture"
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"lens-driving mechanical official text hash changed for {patent_id}"
            )
        if _patent_table_blocks(text):
            raise PatentParseError(
                "lens-driving mechanical disclosure unexpectedly contains PPUBS tables"
            )
        for phrase, expected in profile["mechanical_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"lens-driving mechanical phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bcurvature\s+radius\b|\baspheric\s+coefficients?\b|"
            r"\bAbbe\s+(?:number|#)\b|\bSurface\s+(?:No\.|#)\s*|"
            r"\bFno\b|\bF\s*[- ]?number\b|\beffective\s+focal\s+length\b|"
            r"\boptical\s+data\b|TABLE-US-)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "lens-driving mechanical disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain exact-source structural drift
        return [
            _PrescriptionParseAttempt(
                embodiment_number=None,
                embodiment=embodiment,
                error=exc,
            )
        ]
    return [
        _PrescriptionParseAttempt(
            embodiment_number=None,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code=(
                    "confirmed_no_prescription.lens_driving_mechanical_architecture_only"
                ),
                detail=(
                    "the exact retained official PPUBS disclosure publishes lens-driving "
                    "carrier, magnet, coil, and mechanism architecture but no optical "
                    "surface prescription or prescription table"
                ),
            ),
        )
    ]


def _classify_non_optical_zone_stray_light_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify one exact NEWMAX non-optical-zone architecture family."""

    if _NON_OPTICAL_ZONE_STRAY_LIGHT_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _NON_OPTICAL_ZONE_STRAY_LIGHT_ONLY_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    embodiment = "non-optical-zone stray-light suppression architecture"
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"non-optical-zone official text hash changed for {patent_id}"
            )
        if _patent_table_blocks(text):
            raise PatentParseError(
                "non-optical-zone disclosure unexpectedly contains PPUBS tables"
            )
        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"non-optical-zone phrase {phrase!r} occurs {observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\baspheric\s+coefficients?\b|\bAbbe\s+(?:number|#)\b|"
            r"\bSurface\s+(?:No\.|#)\s*|\bFno\b|\bF\s*[- ]?number\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|TABLE-US-)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "non-optical-zone disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain exact-source structural drift
        return [
            _PrescriptionParseAttempt(
                embodiment_number=None,
                embodiment=embodiment,
                error=exc,
            )
        ]
    return [
        _PrescriptionParseAttempt(
            embodiment_number=None,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code=(
                    "confirmed_no_prescription."
                    "non_optical_zone_stray_light_architecture_only"
                ),
                detail=(
                    "the exact retained official PPUBS disclosure publishes non-optical-zone "
                    "connection geometry for suppressing stray light but no optical surface "
                    "prescription or prescription table"
                ),
            ),
        )
    ]


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
    parser_source_document: SourceDocumentEvidence | None = None
    recovered_parser_input: RecoveredPatentHtml | None = None
    recovered_pdf_input: PatentPdfOcrRecovery | None = None
    recovered_prior_pdf_input: RecoveredPriorPublicationPdf | None = None
    prior_pdf_html_document: SourceDocumentEvidence | None = None
    official_pdf_document: SourceDocumentEvidence | None = None
    mirror_pdf_document: SourceDocumentEvidence | None = None
    pdf_source_pin: SourceDocumentEvidence | None = None
    recovery_manifest: SourceDocumentEvidence | None = None
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
        parser_source_document = source_document
        try:
            parse_attempts = _parse_prescription_attempts(
                fetched.html,
                patent_id=candidate.patent_id,
            )
        except PatentParseError as primary_parse_error:
            recovered_parser_input = await _recover_same_application_grant_html(
                client,
                token,
                primary_publication_id=candidate.patent_id,
                primary_fetched=fetched,
            )
            if recovered_parser_input is not None:
                parser_source_document = _retain_fetched_patent_html(
                    raw_document_dir,
                    patent_id=recovered_parser_input.publication_id,
                    fetched=recovered_parser_input.fetched,
                )
                recovery_manifest = _retain_fulltext_recovery_manifest(
                    raw_document_dir,
                    primary_publication_id=candidate.patent_id,
                    primary_source=source_document,
                    recovered=recovered_parser_input,
                    parser_source=parser_source_document,
                )
                parse_attempts = _parse_prescription_attempts(
                    recovered_parser_input.fetched.html,
                    patent_id=candidate.patent_id,
                )
            else:
                try:
                    cached_pdf_sources = _load_pdf_ocr_source_pin(
                        raw_document_dir,
                        publication_id=candidate.patent_id,
                    )
                    direct_pdf_error: PatentPdfRecoveryError | None = None
                    try:
                        recovered_pdf_input = await recover_ability_official_pdf_ocr(
                            client,
                            token,
                            publication_id=candidate.patent_id,
                            primary_html=fetched.html,
                            cached_sources=cached_pdf_sources,
                        )
                    except PatentPdfRecoveryError as exc:
                        direct_pdf_error = exc
                        recovered_pdf_input = None
                    if recovered_pdf_input is None:
                        recovered_prior_pdf_input = (
                            await _recover_prior_publication_ability_pdf_ocr(
                                client,
                                token,
                                primary_publication_id=candidate.patent_id,
                                primary_fetched=fetched,
                                cached_sources=cached_pdf_sources,
                            )
                        )
                        if recovered_prior_pdf_input is not None:
                            recovered_pdf_input = recovered_prior_pdf_input.recovered
                    if recovered_pdf_input is None and direct_pdf_error is not None:
                        raise direct_pdf_error
                except PatentPdfRecoveryError as exc:
                    raise PatentParseError(f"official PDF recovery rejected: {exc}") from exc
                if recovered_pdf_input is None:
                    raise primary_parse_error
                pdf_source_publication_id = (
                    recovered_prior_pdf_input.source_publication_id
                    if recovered_prior_pdf_input is not None
                    else candidate.patent_id
                )
                if recovered_prior_pdf_input is not None:
                    prior_pdf_html_document = _retain_fetched_patent_html(
                        raw_document_dir,
                        patent_id=recovered_prior_pdf_input.source_publication_id,
                        fetched=recovered_prior_pdf_input.source_fetched,
                    )
                official_pdf_document = _retain_source_bytes(
                    raw_document_dir,
                    publication_id=pdf_source_publication_id,
                    source_bucket="USPTO-PDF",
                    suffix="pdf",
                    content=recovered_pdf_input.official_pdf,
                )
                if recovered_pdf_input.mirror_pdf is not None:
                    mirror_pdf_document = _retain_source_bytes(
                        raw_document_dir,
                        publication_id=pdf_source_publication_id,
                        source_bucket="GOOGLE-OCR-PDF",
                        suffix="pdf",
                        content=recovered_pdf_input.mirror_pdf,
                    )
                parser_source_document = _retain_source_bytes(
                    raw_document_dir,
                    publication_id=candidate.patent_id,
                    source_bucket="USPTO-PDF-OCR-JSON",
                    suffix="json",
                    content=recovered_pdf_input.parser_input,
                )
                pdf_source_pin = _retain_pdf_ocr_source_pin(
                    raw_document_dir,
                    publication_id=candidate.patent_id,
                    recovered=recovered_pdf_input,
                    official_pdf_source=official_pdf_document,
                    mirror_pdf_source=mirror_pdf_document,
                )
                recovery_manifest = _retain_pdf_ocr_recovery_manifest(
                    raw_document_dir,
                    primary_publication_id=candidate.patent_id,
                    primary_source=source_document,
                    recovered=recovered_pdf_input,
                    official_pdf_source=official_pdf_document,
                    mirror_pdf_source=mirror_pdf_document,
                    parser_source=parser_source_document,
                    source_pin=pdf_source_pin,
                    prior_publication_recovery=recovered_prior_pdf_input,
                    prior_publication_source=prior_pdf_html_document,
                )
                parse_attempts = _parse_prescription_attempts(
                    recovered_pdf_input.parser_input.decode("utf-8"),
                    patent_id=candidate.patent_id,
                )
    except Exception as exc:  # noqa: BLE001 - report per-patent failure reason
        failure_status, failure_reason_code = _parse_failure_outcome(exc)
        source_attempts = (
            exc.attempts
            if isinstance(exc, PatentFulltextFetchError)
            else (fetched.attempts if fetched is not None else ())
        )
        return [
            ConversionAttempt(
                patent_id=candidate.patent_id,
                title=candidate.title,
                status=failure_status,
                reason=f"{type(exc).__name__}: {exc}",
                reason_code=failure_reason_code,
                raw_document_path=(
                    source_document.retained_path if source_document is not None else ""
                ),
                raw_document_sha256=(source_document.sha256 if source_document is not None else ""),
                source_attempts=source_attempts,
                parser_input_document_path=(
                    parser_source_document.retained_path
                    if parser_source_document is not None
                    and parser_source_document != source_document
                    else ""
                ),
                parser_input_document_sha256=(
                    parser_source_document.sha256
                    if parser_source_document is not None
                    and parser_source_document != source_document
                    else ""
                ),
                parser_input_publication_id=(
                    recovered_parser_input.publication_id
                    if recovered_parser_input is not None
                    else (
                        recovered_pdf_input.publication_id
                        if recovered_pdf_input is not None
                        else ""
                    )
                ),
                parser_input_source_bucket=(
                    parser_source_document.source_bucket
                    if parser_source_document is not None
                    and parser_source_document != source_document
                    else ""
                ),
                fulltext_recovery_manifest_path=(
                    recovery_manifest.retained_path if recovery_manifest is not None else ""
                ),
                fulltext_recovery_manifest_sha256=(
                    recovery_manifest.sha256 if recovery_manifest is not None else ""
                ),
            )
        ]

    assert source_document is not None
    assert parser_source_document is not None
    attempts: list[ConversionAttempt] = []
    formal_case_stems = formal_case_stems or frozenset()
    for parse_attempt in parse_attempts:
        if parse_attempt.error is not None:
            failure_status, failure_reason_code = _parse_failure_outcome(parse_attempt.error)
            attempts.append(
                ConversionAttempt(
                    patent_id=candidate.patent_id,
                    title=candidate.title,
                    status=failure_status,
                    reason=f"{type(parse_attempt.error).__name__}: {parse_attempt.error}",
                    reason_code=failure_reason_code,
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
            request = _conversion_request(prescription, parser_source_document)
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
    if recovered_parser_input is not None or recovered_pdf_input is not None:
        assert recovery_manifest is not None
        for attempt in attempts:
            attempt.parser_input_document_path = parser_source_document.retained_path
            attempt.parser_input_document_sha256 = parser_source_document.sha256
            attempt.parser_input_publication_id = (
                recovered_parser_input.publication_id
                if recovered_parser_input is not None
                else recovered_pdf_input.publication_id
            )
            attempt.parser_input_source_bucket = parser_source_document.source_bucket
            attempt.fulltext_recovery_manifest_path = recovery_manifest.retained_path
            attempt.fulltext_recovery_manifest_sha256 = recovery_manifest.sha256
    return attempts


def _parse_failure_outcome(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, PatentTerminalParseError):
        return exc.status, exc.reason_code
    return "failed", ""


_PPUBS_APPLICATION_NUMBER_PATTERN = re.compile(
    r"\bAppl\.\s*No\.:\s*(?P<series>\d{2})\s*/\s*(?P<serial>\d{6})\b",
    flags=re.IGNORECASE,
)
_PPUBS_EMBEDDED_TIFF_PATTERN = re.compile(
    r"<\?img\b[^>]*\bfile\s*=\s*[\"'][^\"']+\.TIF[\"'][^>]*\?>",
    flags=re.IGNORECASE,
)


def _ppubs_application_number(raw_html: str) -> str | None:
    """Return one exact USPTO application number or fail closed on ambiguity."""

    matches = {
        f"{match.group('series')}/{match.group('serial')}"
        for match in _PPUBS_APPLICATION_NUMBER_PATTERN.finditer(
            normalize_patent_text(raw_html)
        )
    }
    return next(iter(matches)) if len(matches) == 1 else None


def _ppubs_application_query(application_number: str) -> str:
    series, serial = application_number.split("/", maxsplit=1)
    if re.fullmatch(r"\d{2}", series) is None or re.fullmatch(r"\d{6}", serial) is None:
        raise PatentParseError(f"invalid USPTO application number: {application_number}")
    return f"{series}/{serial[:3]},{serial[3:]}.app."


def _grant_binds_prior_publication(raw_html: str, publication_id: str) -> bool:
    """Require the grant's official Prior Publication Data to name the A-publication."""

    match = re.fullmatch(r"US-(?P<number>\d+)-(?P<kind>A\d+)", publication_id.upper())
    if match is None:
        return False
    text = normalize_patent_text(raw_html)
    section = re.search(
        r"\bPrior\s+Publication\s+Data\b(?P<body>.*?)"
        r"\b(?:Foreign\s+Application\s+Priority\s+Data|Related\s+U\.S\.\s+Application\s+Data|"
        r"Publication\s+Classification)\b",
        text,
        flags=re.IGNORECASE,
    )
    if section is None:
        return False
    pattern = (
        rf"\bUS\s+{re.escape(match.group('number'))}\s+"
        rf"{re.escape(match.group('kind'))}\b"
    )
    return re.search(pattern, section.group("body"), flags=re.IGNORECASE) is not None


def _grant_prior_publication_ids(raw_html: str) -> tuple[str, ...]:
    """Extract only official US A-publications from Prior Publication Data."""

    text = normalize_patent_text(raw_html)
    section = re.search(
        r"\bPrior\s+Publication\s+Data\b(?P<body>.*?)"
        r"\b(?:Foreign\s+Application\s+Priority\s+Data|Related\s+U\.S\.\s+Application\s+Data|"
        r"Publication\s+Classification)\b",
        text,
        flags=re.IGNORECASE,
    )
    if section is None:
        return ()
    publications = {
        f"US-{match.group('number')}-{match.group('kind').upper()}"
        for match in re.finditer(
            r"\bUS\s+(?P<number>\d{11})\s+(?P<kind>A\d+)\b",
            section.group("body"),
            flags=re.IGNORECASE,
        )
    }
    return tuple(sorted(publications))


async def _recover_prior_publication_ability_pdf_ocr(
    client: httpx.AsyncClient,
    token: str,
    *,
    primary_publication_id: str,
    primary_fetched: FetchedPatentHtml,
    cached_sources: PatentPdfCachedSources | None,
) -> RecoveredPriorPublicationPdf | None:
    """Recover an Ability PDF only through an exact grant/A-publication binding."""

    if _source_for_patent_id(primary_publication_id) != "USPAT":
        return None
    application_number = _ppubs_application_number(primary_fetched.html)
    if application_number is None:
        return None
    prior_publications = _grant_prior_publication_ids(primary_fetched.html)
    if not prior_publications:
        return None
    if len(prior_publications) != 1:
        raise PatentParseError(
            "grant Prior Publication Data is ambiguous: " + ", ".join(prior_publications)
        )
    source_publication_id = prior_publications[0]
    if not _grant_binds_prior_publication(primary_fetched.html, source_publication_id):
        raise PatentParseError("grant does not bind the selected prior publication")
    source_html = await _ppubs_patent_html(
        client,
        token,
        source_publication_id,
        "US-PGPUB",
    )
    if _ppubs_application_number(source_html) != application_number:
        raise PatentParseError("prior publication application number does not match grant")
    recovered = await recover_ability_official_pdf_ocr(
        client,
        token,
        publication_id=source_publication_id,
        primary_html=source_html,
        cached_sources=cached_sources,
    )
    if recovered is None:
        return None
    try:
        parser_payload = json.loads(recovered.parser_input)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatentParseError("prior-publication PDF parser input is invalid") from exc
    if (
        not isinstance(parser_payload, dict)
        or parser_payload.get("publication_id") != source_publication_id
    ):
        raise PatentParseError("prior-publication PDF parser input is not source-bound")
    primary_digest = sha256_bytes(primary_fetched.html.encode("utf-8"))
    source_digest = sha256_bytes(source_html.encode("utf-8"))
    parser_payload["publication_id"] = primary_publication_id
    parser_payload["source_publication_id"] = source_publication_id
    parser_payload["source_linkage"] = {
        "application_number": application_number,
        "exact_application_number_match": True,
        "grant_prior_publication_binding": True,
        "kind": "uspto_prior_publication_data_same_application_v1",
        "primary_html_sha256": primary_digest,
        "source_html_sha256": source_digest,
    }
    parser_input = (
        json.dumps(
            parser_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    linked_recovery = replace(
        recovered,
        publication_id=primary_publication_id,
        parser_input=parser_input,
    )
    return RecoveredPriorPublicationPdf(
        primary_publication_id=primary_publication_id,
        source_publication_id=source_publication_id,
        application_number=application_number,
        source_fetched=FetchedPatentHtml(
            html=source_html,
            source_bucket="US-PGPUB",
        ),
        recovered=linked_recovery,
    )


async def _recover_same_application_grant_html(
    client: httpx.AsyncClient,
    token: str,
    *,
    primary_publication_id: str,
    primary_fetched: FetchedPatentHtml,
) -> RecoveredPatentHtml | None:
    """Find an official text grant only when the A-publication embeds TIFF tables."""

    if _source_for_patent_id(primary_publication_id) != "US-PGPUB":
        return None
    embedded_tiff_count = len(_PPUBS_EMBEDDED_TIFF_PATTERN.findall(primary_fetched.html))
    if embedded_tiff_count == 0:
        return None
    application_number = _ppubs_application_number(primary_fetched.html)
    if application_number is None:
        return None

    primary_text_table_count = len(
        _patent_table_blocks(normalize_patent_text(primary_fetched.html))
    )
    docs = await _ppubs_search_docs(
        client,
        token,
        _ppubs_application_query(application_number),
        20,
    )
    recovered: list[RecoveredPatentHtml] = []
    fetch_failures: list[str] = []
    for doc in sorted(docs, key=lambda item: str(item.get("documentId") or "")):
        publication_id = str(doc.get("documentId") or "").strip().upper()
        source_bucket = str(doc.get("type") or "").strip().upper()
        if (
            source_bucket != "USPAT"
            or re.fullmatch(r"US-\d+-B\d+", publication_id) is None
        ):
            continue
        try:
            html_text = await _ppubs_patent_html(
                client,
                token,
                publication_id,
                source_bucket,
            )
        except Exception as exc:  # noqa: BLE001 - try every exact-app grant
            fetch_failures.append(f"{publication_id}:{type(exc).__name__}")
            continue
        if _ppubs_application_number(html_text) != application_number:
            continue
        if not _grant_binds_prior_publication(html_text, primary_publication_id):
            continue
        recovered_text_table_count = len(
            _patent_table_blocks(normalize_patent_text(html_text))
        )
        if recovered_text_table_count <= primary_text_table_count:
            continue
        recovered.append(
            RecoveredPatentHtml(
                publication_id=publication_id,
                application_number=application_number,
                fetched=FetchedPatentHtml(
                    html=html_text,
                    source_bucket=source_bucket,
                    attempts=(),
                ),
                primary_embedded_tiff_count=embedded_tiff_count,
                primary_text_table_count=primary_text_table_count,
                recovered_text_table_count=recovered_text_table_count,
            )
        )
    if not recovered:
        if fetch_failures:
            raise PatentParseError(
                "same-application grant recovery fetch failed: " + ", ".join(fetch_failures)
            )
        return None
    return max(
        recovered,
        key=lambda item: (item.recovered_text_table_count, item.publication_id),
    )


def _retain_fulltext_recovery_manifest(
    raw_document_dir: Path,
    *,
    primary_publication_id: str,
    primary_source: SourceDocumentEvidence,
    recovered: RecoveredPatentHtml,
    parser_source: SourceDocumentEvidence,
) -> SourceDocumentEvidence:
    """Retain deterministic linkage checks for primary and recovered parser inputs."""

    payload = {
        "schema_version": 1,
        "recovery_type": "uspto_same_application_grant_text",
        "application_number": recovered.application_number,
        "primary": {
            "publication_id": primary_publication_id,
            "source_bucket": primary_source.source_bucket,
            "path": primary_source.retained_path,
            "sha256": primary_source.sha256,
            "embedded_tiff_count": recovered.primary_embedded_tiff_count,
            "text_table_count": recovered.primary_text_table_count,
        },
        "parser_input": {
            "publication_id": recovered.publication_id,
            "source_bucket": parser_source.source_bucket,
            "path": parser_source.retained_path,
            "sha256": parser_source.sha256,
            "text_table_count": recovered.recovered_text_table_count,
        },
        "checks": {
            "exact_application_number_match": True,
            "grant_prior_publication_binding": True,
            "parser_input_has_more_text_tables": True,
        },
    }
    content = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    digest = sha256_bytes(content)
    path = (
        raw_document_dir
        / "fulltext-recovery"
        / digest[:16]
        / (
            f"{_safe_stem(primary_publication_id)}--"
            f"{_safe_stem(recovered.publication_id)}.json"
        )
    )
    if path.exists():
        if path.read_bytes() != content:
            raise PatentParseError(f"fulltext recovery manifest hash-path collision: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_bytes(content)
        temp_path.replace(path)
    return SourceDocumentEvidence(
        source_bucket="fulltext-recovery-manifest",
        retained_path=Path(_display_path(path)).as_posix(),
        sha256=digest,
    )


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


def _retain_source_bytes(
    raw_document_dir: Path,
    *,
    publication_id: str,
    source_bucket: str,
    suffix: str,
    content: bytes,
) -> SourceDocumentEvidence:
    """Retain one immutable binary/derived source artifact by content hash."""

    if re.fullmatch(r"[a-z0-9]+", suffix, flags=re.IGNORECASE) is None:
        raise PatentParseError(f"invalid retained source suffix: {suffix}")
    digest = sha256_bytes(content)
    source_stem = _safe_stem(source_bucket)
    path = (
        raw_document_dir
        / source_stem
        / digest[:16]
        / f"{_safe_stem(publication_id)}.{suffix.lower()}"
    )
    if path.exists():
        if path.read_bytes() != content:
            raise PatentParseError(f"raw source hash-path collision: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_bytes(content)
        temp_path.replace(path)
    return SourceDocumentEvidence(
        source_bucket=source_bucket,
        retained_path=Path(_display_path(path)).as_posix(),
        sha256=digest,
    )


def _pdf_ocr_source_pin_path(raw_document_dir: Path, publication_id: str) -> Path:
    return (
        raw_document_dir
        / "USPTO-PDF-OCR-SOURCE-PIN"
        / f"{_safe_stem(publication_id)}.json"
    )


def _resolve_retained_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def _load_pdf_ocr_source_pin(
    raw_document_dir: Path,
    *,
    publication_id: str,
) -> PatentPdfCachedSources | None:
    """Load and hash-check the immutable raw PDF selection for one publication."""

    pin_path = _pdf_ocr_source_pin_path(raw_document_dir, publication_id)
    if not pin_path.exists():
        return None
    try:
        raw = pin_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatentParseError(f"invalid PDF OCR source pin: {pin_path}") from exc
    canonical = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    if raw != canonical:
        raise PatentParseError(f"PDF OCR source pin is not canonical JSON: {pin_path}")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise PatentParseError(f"unsupported PDF OCR source pin schema: {pin_path}")
    if payload.get("publication_id") != publication_id:
        raise PatentParseError(f"PDF OCR source pin publication mismatch: {pin_path}")

    def checked_source(field: str, source_bucket: str) -> tuple[bytes, str]:
        record = payload.get(field)
        if not isinstance(record, dict) or record.get("source_bucket") != source_bucket:
            raise PatentParseError(f"invalid {field} record in PDF OCR source pin")
        path_text = record.get("path")
        expected_sha256 = record.get("sha256")
        source_url = record.get("source_url")
        if not all(isinstance(value, str) and value for value in (path_text, expected_sha256, source_url)):
            raise PatentParseError(f"incomplete {field} record in PDF OCR source pin")
        if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise PatentParseError(f"invalid {field} hash in PDF OCR source pin")
        source_path = _resolve_retained_path(path_text)
        try:
            source_path.resolve().relative_to(raw_document_dir.resolve())
        except ValueError as exc:
            raise PatentParseError(
                f"retained PDF source is outside the raw document lake: {source_path}"
            ) from exc
        try:
            content = source_path.read_bytes()
        except OSError as exc:
            raise PatentParseError(f"retained PDF source is unavailable: {source_path}") from exc
        if sha256_bytes(content) != expected_sha256:
            raise PatentParseError(f"retained PDF source hash mismatch: {source_path}")
        return content, source_url

    official_pdf, official_pdf_url = checked_source("official_pdf", "USPTO-PDF")
    if payload.get("ocr_overlay_pdf") is None:
        mirror_pdf = None
        mirror_pdf_url = None
    else:
        mirror_pdf, mirror_pdf_url = checked_source("ocr_overlay_pdf", "GOOGLE-OCR-PDF")
    return PatentPdfCachedSources(
        official_pdf=official_pdf,
        official_pdf_url=official_pdf_url,
        mirror_pdf=mirror_pdf,
        mirror_pdf_url=mirror_pdf_url,
    )


def _retain_pdf_ocr_source_pin(
    raw_document_dir: Path,
    *,
    publication_id: str,
    recovered: PatentPdfOcrRecovery,
    official_pdf_source: SourceDocumentEvidence,
    mirror_pdf_source: SourceDocumentEvidence | None,
) -> SourceDocumentEvidence:
    """Pin immutable official bytes and the verified overlay when one is published."""

    payload = {
        "schema_version": 1,
        "publication_id": publication_id,
        "official_pdf": {
            "source_url": recovered.official_pdf_url,
            "source_bucket": official_pdf_source.source_bucket,
            "path": official_pdf_source.retained_path,
            "sha256": official_pdf_source.sha256,
        },
    }
    if mirror_pdf_source is not None:
        if recovered.mirror_pdf_url is None or recovered.mirror_pdf is None:
            raise PatentParseError("retained OCR overlay lacks recovered URL/content")
        payload["ocr_overlay_pdf"] = {
            "source_url": recovered.mirror_pdf_url,
            "source_bucket": mirror_pdf_source.source_bucket,
            "path": mirror_pdf_source.retained_path,
            "sha256": mirror_pdf_source.sha256,
        }
    elif recovered.mirror_pdf_url is not None or recovered.mirror_pdf is not None:
        raise PatentParseError("recovered OCR overlay lacks retained source evidence")
    content = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    path = _pdf_ocr_source_pin_path(raw_document_dir, publication_id)
    if path.exists():
        if path.read_bytes() != content:
            raise PatentParseError(f"PDF OCR source pin is immutable: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_bytes(content)
        temp_path.replace(path)
    return SourceDocumentEvidence(
        source_bucket="USPTO-PDF-OCR-SOURCE-PIN",
        retained_path=Path(_display_path(path)).as_posix(),
        sha256=sha256_bytes(content),
    )


def _retain_pdf_ocr_recovery_manifest(
    raw_document_dir: Path,
    *,
    primary_publication_id: str,
    primary_source: SourceDocumentEvidence,
    recovered: PatentPdfOcrRecovery,
    official_pdf_source: SourceDocumentEvidence,
    mirror_pdf_source: SourceDocumentEvidence | None,
    parser_source: SourceDocumentEvidence,
    source_pin: SourceDocumentEvidence,
    prior_publication_recovery: RecoveredPriorPublicationPdf | None = None,
    prior_publication_source: SourceDocumentEvidence | None = None,
) -> SourceDocumentEvidence:
    """Retain official-PDF/OCR-overlay linkage and deterministic tool versions."""

    if (prior_publication_recovery is None) != (prior_publication_source is None):
        raise PatentParseError("prior-publication PDF manifest linkage is incomplete")

    payload = {
        "schema_version": 1,
        "recovery_type": (
            "uspto_official_pdf_exact_image_ocr_overlay"
            if mirror_pdf_source is not None
            else "uspto_official_pdf_coordinate_rapidocr"
        ),
        "publication_id": primary_publication_id,
        "primary": {
            "source_bucket": primary_source.source_bucket,
            "path": primary_source.retained_path,
            "sha256": primary_source.sha256,
        },
        "official_pdf": {
            "source_url": recovered.official_pdf_url,
            "source_bucket": official_pdf_source.source_bucket,
            "path": official_pdf_source.retained_path,
            "sha256": official_pdf_source.sha256,
            "access": "USPTO anonymous PPUBS request token",
        },
        "source_pin": {
            "source_bucket": source_pin.source_bucket,
            "path": source_pin.retained_path,
            "sha256": source_pin.sha256,
        },
        "parser_input": {
            "publication_id": recovered.publication_id,
            "source_bucket": parser_source.source_bucket,
            "path": parser_source.retained_path,
            "sha256": parser_source.sha256,
            "key_page_numbers": list(recovered.key_page_numbers),
        },
        "page_count": recovered.page_count,
        "page_identity": (
            "decoded_page_raster_pixels_v1"
            if mirror_pdf_source is not None
            else "official_decoded_page_raster_pixels_v1"
        ),
        "official_page_image_sha256": list(recovered.page_image_sha256),
        "tool_versions": {
            "pypdf": recovered.pypdf_version,
            "rapidocr_onnxruntime": recovered.rapidocr_version,
        },
        "checks": {
            "same_publication_id": recovered.publication_id == primary_publication_id,
            "key_pages_have_official_image_hashes": True,
            "parser_input_is_canonical_json": True,
        },
    }
    if mirror_pdf_source is not None:
        if recovered.mirror_pdf_url is None or recovered.mirror_pdf is None:
            raise PatentParseError("manifest OCR overlay lacks recovered URL/content")
        payload["ocr_overlay_pdf"] = {
            "source_url": recovered.mirror_pdf_url,
            "source_bucket": mirror_pdf_source.source_bucket,
            "path": mirror_pdf_source.retained_path,
            "sha256": mirror_pdf_source.sha256,
        }
        payload["checks"]["all_decoded_page_rasters_pixel_identical"] = True
    elif recovered.mirror_pdf_url is not None or recovered.mirror_pdf is not None:
        raise PatentParseError("manifest recovered overlay lacks retained evidence")
    if prior_publication_recovery is not None and prior_publication_source is not None:
        try:
            parser_payload = json.loads(recovered.parser_input)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PatentParseError("linked PDF parser input is invalid") from exc
        linkage = parser_payload.get("source_linkage") if isinstance(parser_payload, dict) else None
        linkage_matches = (
            isinstance(linkage, dict)
            and linkage.get("application_number")
            == prior_publication_recovery.application_number
            and linkage.get("primary_html_sha256") == primary_source.sha256
            and linkage.get("source_html_sha256") == prior_publication_source.sha256
            and parser_payload.get("source_publication_id")
            == prior_publication_recovery.source_publication_id
        )
        payload["pdf_source_publication"] = {
            "application_number": prior_publication_recovery.application_number,
            "official_html": {
                "path": prior_publication_source.retained_path,
                "sha256": prior_publication_source.sha256,
                "source_bucket": prior_publication_source.source_bucket,
            },
            "publication_id": prior_publication_recovery.source_publication_id,
            "relationship": "grant_prior_publication_data_same_application",
        }
        payload["checks"]["prior_publication_linkage_matches_parser_input"] = linkage_matches
    if not all(payload["checks"].values()):
        raise PatentParseError("PDF OCR recovery manifest contains a failed linkage check")
    content = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    digest = sha256_bytes(content)
    path = (
        raw_document_dir
        / "fulltext-recovery"
        / digest[:16]
        / f"{_safe_stem(primary_publication_id)}--official-pdf-ocr.json"
    )
    if path.exists():
        if path.read_bytes() != content:
            raise PatentParseError(f"PDF OCR recovery manifest hash-path collision: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.tmp")
        temp_path.write_bytes(content)
        temp_path.replace(path)
    return SourceDocumentEvidence(
        source_bucket="fulltext-recovery-manifest",
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
