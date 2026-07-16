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
    DEFAULT_PATENT_REFERENCE_WAVELENGTH_UM,
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
    genius_four_lens_eleven_source_layout_for_sha256,
    genius_four_lens_six_source_layout_for_sha256,
    genius_seven_lens_seven_source_layout_for_sha256,
    recover_ability_official_pdf_ocr,
)

DEFAULT_POOL_GLOB = "uspto-smartphone-batch*.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "zmx-staging"
DEFAULT_RAW_DOCUMENT_DIR = ROOT / "data" / "patent-lake" / "uspto-ppubs-html"
DEFAULT_ATTEMPTS_DIR = ROOT / "data" / "patent-conversion-attempts"
DEFAULT_REPORT_PATH = ROOT / ".planning" / "loop" / "patent2zmx-spike-report.md"
DEFAULT_CASE_INDEX_PATH = ROOT / "app" / "data" / "optical_cases" / "index.json"
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
    reference_wavelength_um: float = DEFAULT_PATENT_REFERENCE_WAVELENGTH_UM
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
    source_locked_attempts = _parse_folded_adaptive_zoom_terminal_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _parse_sunny_long_focus_folded_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _parse_sunny_fingerprint_wide_angle_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_aac_telecentric_nine_lens_metadata_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = (
        _classify_aac_near_eye_folded_three_lens_missing_metadata_attempts(
            raw_text,
            patent_id=patent_id,
        )
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = (
        _classify_sunny_automotive_nineteen_lens_missing_f_number_attempts(
            raw_text,
            patent_id=patent_id,
        )
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_endoscopic_three_lens_missing_f_number_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _parse_samsung_iris_moving_group_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_meta_optical_layer_architecture_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_edof_microscope_examples_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_deformable_lens_actuator_architecture_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_catadioptric_module_architecture_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_compact_barcode_telephoto_architecture_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_shiftable_image_sensor_wire_geometry_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = (
        _classify_low_reflection_light_blocking_architecture_only_attempts(
            raw_text,
            patent_id=patent_id,
        )
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_lens_barrel_absorbing_geometry_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_folded_lens_barrel_driving_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _classify_circle_optics_mechanical_only_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
    source_locked_attempts = _parse_large_aperture_scanning_tele_attempts(
        raw_text,
        patent_id=patent_id,
    )
    if source_locked_attempts:
        return source_locked_attempts
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
        attempts = _classify_samsung_ten_lens_undefined_high_order_attempts(
            text,
            patent_id=patent_id,
        )
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
        attempts = _classify_folded_tele_missing_f_number_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_barrel_spacer_geometry_only_attempts(
            text,
            patent_id=patent_id,
        )
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
        attempts = _classify_barcode_scanner_architecture_only_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_imaging_lens_system_architecture_only_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_extended_depth_of_focus_architecture_only_attempts(
            text,
            patent_id=patent_id,
        )
        if attempts:
            return attempts
        attempts = _classify_light_blocking_geometry_only_attempts(
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
_LARGE_APERTURE_SCANNING_TELE_TITLE_PATTERN = re.compile(
    r"\bLARGE-APERTURE\s+COMPACT\s+SCANNING\s+TELE\s+CAMERAS\b",
    flags=re.IGNORECASE,
)
_LARGE_APERTURE_SCANNING_TELE_SOURCE_ANCHOR_PATTERN = re.compile(
    r"\bTABLE-US-(?P<number>\d{5})\s+",
    flags=re.IGNORECASE,
)
_LARGE_APERTURE_SCANNING_TELE_SURFACE_HEADER_PATTERN = re.compile(
    rf"\bExample\s+(?P<example>800|900|1000|1100)\s+"
    rf"EFL\s*=\s*(?P<f>{NUMBER_PATTERN})\s*mm\s*,\s*"
    rf"(?:Eff\.\s+)?f\s+number\s*=\s*(?P<fno>{NUMBER_PATTERN})\s*"
    rf"\(\s*Eff\.\s+DA/2\s*=\s*(?P<aperture>{NUMBER_PATTERN})\s*mm\s*\)\s*,\s*"
    rf"HFOV\s*=\s*(?P<hfov>{NUMBER_PATTERN})\s*deg\.?\s+"
    r"Aperture\s+Curvature\s+Radius\s+Focal\s+Surface\s+#\s+Comment\s+Type\s+"
    r"Radius\s+Thickness\s+\(D/2\)\s+Material\s+Index\s+Abbe\s+#\s+Length\s+",
    flags=re.IGNORECASE,
)
_LARGE_APERTURE_SCANNING_TELE_COEFFICIENT_HEADER_PATTERN = re.compile(
    r"\bAspheric\s+Coefficients(?:\s+\(Continued\))?\s+Surface\s+#\s+",
    flags=re.IGNORECASE,
)
_LARGE_APERTURE_SCANNING_TELE_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12216259-B2": {
        "raw_document_sha256": (
            "86d554b9602ba6d6d25a7e378a05f8477f5ca4bd71d5c7564489cafd41891744"
        ),
        "normalized_text_sha256": (
            "dd190c44fb05db84a44000de42cf2b85c228f421f4a4f964f22706b8e74d489d"
        ),
    },
    "US-12411321-B1": {
        "raw_document_sha256": (
            "9084f2c33d964572e78a73f2696ee16ee887c4b467ff7f3bc025d54a52b96a67"
        ),
        "normalized_text_sha256": (
            "7f30e9e4ff73b370c79020d119fb2663d1f67ce04f3dd290923d93ec1afeb272"
        ),
    },
    "US-20250271645-A1": {
        "raw_document_sha256": (
            "6cee6f58f05c7c78829f5f872c08b88a2879ead05a796a367fe2d714322af22b"
        ),
        "normalized_text_sha256": (
            "c4790a2b8cc367304729712bf7b2019ab4823993a59b177121fd6438d767acb6"
        ),
    },
}
_LARGE_APERTURE_SCANNING_TELE_EXAMPLES = (800, 900, 1000, 1100)
_LARGE_APERTURE_SCANNING_TELE_FIELD_BINDINGS = {
    "EFL": (17.37, 14.10, 14.10, 14.10),
    "f number": (2.35, 2.45, 2.45, 2.43),
    "HFOV": (12.8, 11.5, 15.7, 13.7),
    "n-FOV.sub.T": (25.6, 22.8, 31.0, 27.4),
    "SD": (8.0, 5.6, 8.0, 7.0),
}
_FOLDED_ADAPTIVE_ZOOM_TITLE_PATTERN = re.compile(
    r"\bFOLDED\s+CAMERA\s+WITH\s+CONTINUOUSLY\s+ADAPTIVE\s+ZOOM\s+FACTOR\b",
    flags=re.IGNORECASE,
)
_FOLDED_ADAPTIVE_ZOOM_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-11947247-B2": {
        "raw_document_sha256": (
            "738f12facf7092f2f417aa19eedefc5ff1e6167b2893599c0357d457d60f1f35"
        ),
        "normalized_text_sha256": (
            "99941829b0ed8bd15d6ee519d409616c3b15672766ba6d23d28e6362f08dec31"
        ),
        "qcon_formula_count": 10,
        "qcon_last_definition_id": "MATH-US-00001-10",
    },
    "US-12572060-B2": {
        "raw_document_sha256": (
            "3a888161b1902f85510fac473e35d4b00cdde17b27477e0477512ba5f1cea2e5"
        ),
        "normalized_text_sha256": (
            "c5342d6fef3c8158fe32fe9964ea39fc077381217147397bd519bacaba32f1bc"
        ),
        "qcon_formula_count": 7,
        "qcon_last_definition_id": "MATH-US-00001-7",
    },
    "US-20230288783-A1": {
        "raw_document_sha256": (
            "a0b7015cb421fac8678d58a8d9d71c67fc5d0f7c631dccf0b240be98d18d42fa"
        ),
        "normalized_text_sha256": (
            "4426d79e2dfe6e63183aec40b1c544de937f6642c0b3346abb5de9c931818fc0"
        ),
        "qcon_formula_count": 10,
        "qcon_last_definition_id": "MATH-US-00001-10",
    },
}
_FOLDED_ADAPTIVE_ZOOM_EFLS = (15.0, 22.5, 30.0)
_FOLDED_ADAPTIVE_ZOOM_F_NUMBERS = (2.34, 3.52, 4.69)
_FOLDED_ADAPTIVE_ZOOM_MOVING_THICKNESSES = {
    7: (1.4118, 5.1246, 7.8118),
    13: (6.5013, 2.7885, 0.1013),
    17: (0.9176, 4.6456, 7.3176),
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
_SAMSUNG_TEN_LENS_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+SYSTEM\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_TEN_LENS_BINDING_PATTERN = re.compile(
    r"\bTables\s+(?P<surface_table>\d+)\s+and\s+(?P<asphere_table>\d+)\s+"
    r"illustrate\s+lens\s+characteristics\s+and\s+aspherical\s+surface\s+values\s+"
    r"of\s+the\s+imaging\s+lens\s+system\s+according\s+to\s+the\s+present\s+"
    r"embodiment\.",
    flags=re.IGNORECASE,
)
_SAMSUNG_TEN_LENS_SURFACE_HEADER_PATTERN = re.compile(
    r"\bSurface\s+Radius\s+of\s+Thickness/\s+Refractive\s+Abbe\s+No\.\s+"
    r"Components\s+curvature\s+distance\s+index\s+number\s+",
    flags=re.IGNORECASE,
)
_SAMSUNG_TEN_LENS_COEFFICIENT_HEADER_PATTERN = re.compile(
    r"\bSurface\s+No\.\s+(?P<surfaces>(?:S\d+\s+)+)",
    flags=re.IGNORECASE,
)
_SAMSUNG_TEN_LENS_FOV_DEFINITION = re.compile(
    r"\bFOV\s+is\s+a\s+field\s+of\s+view\s+of\s+the\s+imaging\s+lens\s+system\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_TEN_LENS_PUBLISHED_ASPHERE_DEFINITION = re.compile(
    r"\bc\s+is\s+a\s+reciprocal\s+of\s+a\s+radius\s+of\s+curvature\s+of\s+the\s+"
    r"corresponding\s+lens\s*,\s*k\s+is\s+a\s+conic\s+constant\s*,\s*r\s+is\s+a\s+"
    r"distance\s+from\s+a\s+certain\s+point\s+on\s+an\s+aspherical\s+surface\s+to\s+"
    r"an\s+optical\s+axis\s*,\s*A\s+to\s+H\s+and\s+J\s+are\s+aspherical\s+surface\s+"
    r"constants\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_TEN_LENS_UNDEFINED_HIGH_ORDER_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12578550-B2": {
        "normalized_text_sha256": (
            "02aa5d51987a6fb37393d816e7e2c20193b3f4d7e01efc2f2aaad34522f0b695"
        ),
    },
    "US-20240184082-A1": {
        "normalized_text_sha256": (
            "e4b3d02b47d3435e9517a3f79d03329dfb183dd99a723b87cfe510fbe6ab66a6"
        ),
    },
    "US-20260169262-A1": {
        "normalized_text_sha256": (
            "fea78314657aa574cfcb20d9b6ed1d0d227d34acb28a1bf6860562549a72450e"
        ),
    },
}
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
_BARCODE_SCANNER_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bSYSTEMS\s+AND\s+METHODS\s+TO\s+IDENTIFY\s+BARCODES\s+OF\s+INTEREST\s+"
    r"USING\s+A\s+NON-INTERNET\s+CONNECTED\s+BARCODE\s+SCANNER\b",
    flags=re.IGNORECASE,
)
_BARCODE_SCANNER_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12547862-B1": {
        "normalized_text_sha256": (
            "59517f74eaf91b27eea059da2aad8b43780e06d7c9be50de917a12c527ec1538"
        ),
        "architecture_phrase_counts": {
            "Family ID: 98700212": 1,
            "barcode": 245,
            "non-internet-connected barcode": 2,
            "imaging lens assembly": 2,
            "image sensor": 3,
            "field of view": 2,
            "return light": 5,
            "illumination assembly": 1,
            "aiming light": 3,
        },
    },
    "US-20260170283-A1": {
        "normalized_text_sha256": (
            "6c83c9a608eb6784ad7a5f749e7d190ac86acbd8aa586d1ec1ef8258dd380cf4"
        ),
        "architecture_phrase_counts": {
            "Family ID: 98700212": 1,
            "barcode": 245,
            "non-internet-connected barcode": 2,
            "imaging lens assembly": 2,
            "image sensor": 3,
            "field of view": 2,
            "return light": 5,
            "illumination assembly": 1,
            "aiming light": 3,
        },
    },
}
_COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bTELEPHOTO\s+LENS\s+FOR\s+COMPACT\s+LONG\s+RANGE\s+BARCODE\s+READER\b",
    flags=re.IGNORECASE,
)
_COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_PHRASE_COUNTS = {
    "Family ID: 84363056": 1,
    "telephoto lens assembly": 51,
    "Crown type glass": 5,
    "Flint type glass": 5,
    "Flint type plastic": 5,
    "Crown type plastic": 5,
    "index of refraction": 4,
    "Abbe value": 4,
    "plastic aspheric lens": 3,
    "effective focal length": 8,
    "field of view": 6,
    "total length from the first lens to the imager": 4,
    "central thickness": 4,
}
_COMPACT_BARCODE_TELEPHOTO_MATERIAL_ANCHORS = (
    "first lens 122 is further made from a Crown type glass with an index of "
    "refraction in the range of approximately 1.51-1.62, for example 1.52",
    "first lens 122 has an Abbe value of approximately 59",
    "third lens is made from a Flint type glass with an index of refraction in "
    "the range of approximately 1.57-1.75, for example 1.66",
    "third lens 126 has an Abbe value of approximately 24",
    "second lens 124 has an index of refraction of approximately 1.65 and an "
    "Abbe value of approximately 22",
    "fourth lens 128 has an index of refraction of approximately 1.53 and an "
    "Abbe value of approximately 56",
)
_COMPACT_BARCODE_TELEPHOTO_SYSTEM_VALUE_ANCHORS = (
    "the total length is 10.34 millimeters",
    "the EFL is 11.8 millimeters",
    "making the telephoto ratio 0.876",
    "the lens has a 19-degree FOV when used with a 1⁄4 inch imaging sensor",
    "has a 2 millimeters aperture",
)
_COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-12235418-B2": {
        "raw_document_sha256": (
            "90b705c9b510a7885abdc379a345e6765fbfbb85f3bdcfa63c41e1abbb18f59c"
        ),
        "normalized_text_sha256": (
            "4e4ead6863537320d55b5b21cda40bbc7a62f1d6008c2d4d9b69ebddd21e857e"
        ),
        "application_number": "17/873058",
        "relationship_markers": (
            "US 20230067508 A1 Mar. 02, 2023",
            "us-provisional-application US 63239348 20210831",
        ),
        "architecture_phrase_counts": (
            _COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_PHRASE_COUNTS
        ),
    },
    "US-20230067508-A1": {
        "raw_document_sha256": (
            "c13c69020e466001c3a6bb09584a7b5e09385c31b301fcb0ed9accc7d85d6bdd"
        ),
        "normalized_text_sha256": (
            "41f761a66657fa8d6c040dc3fdcaf74a3326c5c973995e7eb1634ca099a79589"
        ),
        "application_number": "17/873058",
        "relationship_markers": (
            "us-provisional-application US 63239348 20210831",
        ),
        "architecture_phrase_counts": (
            _COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_PHRASE_COUNTS
        ),
    },
}
_IMAGING_LENS_SYSTEM_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+SYSTEM\s*,\s*IMAGE\s+CAPTURING\s+MODULE\s+AND\s+"
    r"ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_IMAGING_LENS_SYSTEM_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12007589-B2": {
        "normalized_text_sha256": (
            "c37a76765f01a9da6722ec03f8f824e976ca14e41618ed782216760d7a188a5c"
        ),
        "architecture_phrase_counts": {
            "Family ID: 79321029": 1,
            "imaging lens system": 217,
            "image capturing module": 139,
            "electronic device": 42,
            "optical path": 175,
            "lens element": 305,
            "aperture element": 257,
            "field of view": 7,
            "focal length": 16,
            "equivalent focal length": 13,
            "thermal expansion coefficients": 1,
        },
    },
    "US-12449571-B2": {
        "normalized_text_sha256": (
            "4dcc41158dec0b204a18f680b991de5ca1b4f7ced46298c44a27392308f1f88e"
        ),
        "architecture_phrase_counts": {
            "Family ID: 79321029": 1,
            "imaging lens system": 187,
            "image capturing module": 135,
            "electronic device": 40,
            "optical path": 148,
            "lens element": 281,
            "aperture element": 237,
            "field of view": 7,
            "focal length": 16,
            "equivalent focal length": 13,
            "thermal expansion coefficients": 1,
        },
    },
}
_EXTENDED_DEPTH_OF_FOCUS_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bOPTICAL\s+METHOD\s+AND\s+SYSTEM\s+FOR\s+EXTENDED\s+DEPTH\s+OF\s+FOCUS\b",
    flags=re.IGNORECASE,
)
_EXTENDED_DEPTH_OF_FOCUS_DRAWING_ANCHOR_COUNTS = {
    "FIG. 1A is a schematic illustration": 1,
    "FIG. 1B schematically illustrates another example": 1,
    "FIG. 1C schematically illustrates yet another example": 1,
    "1D and 1E show two examples, respectively": 1,
    "2A to 2C show three examples, respectively": 1,
    "3A to 3D illustrate the effect": 2,
    "4A to 4I exemplify face images": 1,
    "5A to 5I exemplify face images": 1,
    "FIG. 6 shows the results of examining": 2,
    "7A to 7D show experimental results": 1,
    "8A to 8D and FIGS. 9A to 9H show experimental verification": 1,
    "FIG. 10A illustrates the performance": 1,
    "FIG. 10B illustrates the performance": 1,
    "11A and 11B present two images": 2,
    "12A-12B and 13 show the ophthalmic experimental results": 1,
    "14A and 14B present the ophthalmic experimental results": 1,
    "15A and 15B present the ophthalmic experimental results": 1,
}
_EXTENDED_DEPTH_OF_FOCUS_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-20080198482-A1": {
        "normalized_text_sha256": (
            "db87ee2b05d34aa6f91336bdcae2ebfe0c6fa987abac1fab5b24ca7d6bc0986f"
        ),
        "architecture_phrase_counts": {
            "Family ID: 46327306": 1,
            "extended depth of focus": 32,
            "phase mask": 7,
            "phase-affecting": 20,
            "non-diffractive": 23,
            "focal length": 8,
            "field of view": 8,
        },
        "drawing_anchor_counts": _EXTENDED_DEPTH_OF_FOCUS_DRAWING_ANCHOR_COUNTS,
    },
    "US-7365917-B2": {
        "normalized_text_sha256": (
            "27b605d0ac827ead0cd9259b79f360db16d04fb474103d6f6d55dc6ff0ca35a8"
        ),
        "architecture_phrase_counts": {
            "Family ID: 46327306": 1,
            "extended depth of focus": 33,
            "phase mask": 7,
            "phase-affecting": 22,
            "non-diffractive": 25,
            "focal length": 8,
            "field of view": 8,
        },
        "drawing_anchor_counts": _EXTENDED_DEPTH_OF_FOCUS_DRAWING_ANCHOR_COUNTS,
    },
    "US-7859769-B2": {
        "normalized_text_sha256": (
            "04a44f2e0b41ccadac7b3d52f214e924e40d9d84c5fa06e36e5262f80d6f38e5"
        ),
        "architecture_phrase_counts": {
            "Family ID: 46327306": 1,
            "extended depth of focus": 40,
            "phase mask": 48,
            "phase-affecting": 19,
            "non-diffractive": 22,
            "focal length": 8,
            "field of view": 8,
        },
        "drawing_anchor_counts": _EXTENDED_DEPTH_OF_FOCUS_DRAWING_ANCHOR_COUNTS,
    },
}
_LENS_BARREL_ABSORBING_GEOMETRY_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY(?:\s+MODULE)?\s*,\s*CAMERA\s+MODULE\s+AND\s+"
    r"ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_LENS_BARREL_ABSORBING_GEOMETRY_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12298595-B2": {
        "raw_document_sha256": (
            "7026f1e465f6aece0d38ae3b479c657a96313b0948099d1ad2c7a41776eb9972"
        ),
        "normalized_text_sha256": (
            "75c468b41831ed49ace3aad85a9983e6ee64b685cce33cb484527837936dbb57"
        ),
        "application_number": "16/924496",
        "table7_prefix": "7th example EPD (mm) 1.77 ψY (mm) 2.32 ψb (mm) 1.82",
        "geometry_phrase_counts": {
            "minimum opening": 33,
            "optical lens element set": 65,
            "smart phone": 1,
            "image sensor": 8,
        },
    },
    "US-20210088752-A1": {
        "raw_document_sha256": (
            "09bf70b6835f49bf072aca9cc017cd890afb45eebd29a4a86ce470dd07187af7"
        ),
        "normalized_text_sha256": (
            "7299d778c9cc10a3642bc3eed79297ea344255c99e48af18c89cfe6ff562b889"
        ),
        "application_number": "16/924496",
        "table7_prefix": "7th example EPD (mm) 1.77 ψY (mm) 2.32 ψb (mm) 1.82",
        "geometry_phrase_counts": {
            "minimum opening": 33,
            "optical lens element set": 65,
            "smart phone": 1,
            "image sensor": 8,
        },
    },
    "US-20260147182-A1": {
        "raw_document_sha256": (
            "3905fa6a1c284a9a375192d1f40db0720fa7620cace856b93674c54f0e2e6bfd"
        ),
        "normalized_text_sha256": (
            "73ddb6e57102209d443fef28c29f6644a840a8474e271ae5e8d8cee1aa784409"
        ),
        "application_number": "19/177743",
        "table7_prefix": "7th example EPD (mm) 1.77 ψL (mm) 2.32 ψb (mm) 1.82",
        "geometry_phrase_counts": {
            "minimum opening": 29,
            "optical lens element set": 57,
            "smart phone": 1,
            "image sensor": 8,
        },
    },
}
_LOW_REFLECTION_LIGHT_BLOCKING_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY\s*,\s*CAMERA\s+MODULE\s+AND\s+"
    r"ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_LOW_REFLECTION_LIGHT_BLOCKING_DRAWINGS = (
    *(("1", panel) for panel in "ABCDEFG"),
    *((str(index), panel) for index in range(2, 6) for panel in "ABCD"),
)
_LOW_REFLECTION_LIGHT_BLOCKING_ITEM_LABELS = (
    "Low-reflection coating and light-blocking example 1",
    "Low-reflection coating and light-blocking example 2",
    "Low-reflection coating and light-blocking example 3",
    "Low-reflection coating and light-blocking example 4",
    "Smartphone camera-module architecture example 5",
)
_LOW_REFLECTION_LIGHT_BLOCKING_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-12429633-B2": {
        "raw_document_sha256": (
            "e6faadbdb770bfd33e48dc5224b7fafa2e87bc59f9a89724f19a82e7567982c7"
        ),
        "normalized_text_sha256": (
            "afd8189dd1194c2f10013a2df2ea2041cfe1074bf42828045c093a5291207699"
        ),
        "application_number": "18/507179",
        "owner_count": 2,
        "relationship_markers": (
            "US 20240077657 A1 Mar. 07, 2024",
            "continuation parent-doc US 16935378 20200722 US 11852848 "
            "child-doc US 18507179",
            "us-provisional-application US 62941937 20191129",
        ),
    },
    "US-20240077657-A1": {
        "raw_document_sha256": (
            "d3fc6eaa25685839674e13d232e13e1ef52676d97cf209ca43bb0adccf3d1f53"
        ),
        "normalized_text_sha256": (
            "7103db39751dc2da158f2c2e0065bc86db66f2388d629e5efb2bbd6d5279c342"
        ),
        "application_number": "18/507179",
        "owner_count": 1,
        "relationship_markers": (
            "parent US continuation 16935378 20200722",
            "us-provisional-application US 62941937 20191129",
        ),
    },
}
_LOW_REFLECTION_LIGHT_BLOCKING_TABLE_SHA256 = (
    "65f34f5a8fdaa637adc41437b234611c80ade9c6864537449e73e95695fd5d0f"
)
_LOW_REFLECTION_LIGHT_BLOCKING_PHRASE_COUNTS = {
    "low-reflection layer": 119,
    "nano-microstructure": 117,
    "carbon black layer": 78,
    "coating layer": 74,
    "light blocking element": 12,
    "light blocking sheet": 6,
    "optical lens elements": 11,
    "such as the numbers, the structures, the surface shapes": 4,
    "non-imaging stray light": 2,
    "reflectivity result": 2,
    "smart phone": 1,
    "image signal processor": 1,
    "optical image stabilization": 1,
}
_FOLDED_LENS_BARREL_DRIVING_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY\s+MODULE\s*,\s*IMAGING\s+LENS\s+"
    r"ASSEMBLY\s+DRIVING\s+MODULE\s+AND\s+ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_FOLDED_LENS_BARREL_DRIVING_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-11722760-B2": {
        "raw_document_sha256": (
            "414e34d63d4331fa4caee23b523035adc9aa4805c7db23c10deb0ef0f6b96bcc"
        ),
        "normalized_text_sha256": (
            "2e4280dbd1fbc1ece18329fa544e46f4feb53c639e141f1c4dd7a7a62d952712"
        ),
        "application_number": "17/391171",
        "heading_markers": ("1st Embodiment (35)", "2nd Embodiment (61)"),
        "table_prefix": "TABLE-US-00001 TABLE 1 d1 (mm) 1.4 d2 (mm) 1.4",
        "ppubs_table_count": 1,
        "architecture_phrase_counts": {
            "Family ID: 77725725": 1,
            "imaging lens assembly module": 43,
            "imaging lens assembly driving module": 6,
            "light path folding element": 16,
            "first lens barrel": 80,
            "second lens barrel": 77,
            "rolling bearings": 20,
            "first sensing element": 34,
            "fourth sensing element": 17,
            "plastic lens elements": 33,
            "smartphone": 1,
            "image sensor": 12,
            "FIG. 1 E is an optical surface schematic view": 2,
            "TABLE-US-00001": 1,
        },
    },
    "US-12088905-B2": {
        "raw_document_sha256": (
            "7242c9295f2f5c6ba76ac26061e7c59dec855b3c92466b0c1406222256bd3055"
        ),
        "normalized_text_sha256": (
            "ab9fcb48acc448ca03dccc35ebc0e10e302f9c87bba4766c208546a616d2131a"
        ),
        "application_number": "18/337147",
        "heading_markers": ("1st Embodiment (35)", "2nd Embodiment (61)"),
        "table_prefix": "TABLE-US-00001 TABLE 1 d1 (mm) 1.4 d2 (mm) 1.4",
        "ppubs_table_count": 1,
        "architecture_phrase_counts": {
            "Family ID: 77725725": 1,
            "imaging lens assembly module": 43,
            "imaging lens assembly driving module": 31,
            "light path folding element": 16,
            "first lens barrel": 80,
            "second lens barrel": 77,
            "rolling bearings": 20,
            "first sensing element": 34,
            "fourth sensing element": 17,
            "plastic lens elements": 33,
            "smartphone": 1,
            "image sensor": 12,
            "FIG. 1 E is an optical surface schematic view": 2,
            "TABLE-US-00001": 1,
        },
    },
    "US-20230353852-A1": {
        "raw_document_sha256": (
            "3eca590960e69369b5474ffac654dc0b8597ff9563387efcd027feef3f0a3a24"
        ),
        "normalized_text_sha256": (
            "ba8b3dc979f32ce054fc9fdd130eed90fc4a19a2049024287b8e98a10ac47b33"
        ),
        "application_number": "18/337147",
        "heading_markers": ("1st Embodiment [0041]", "2nd Embodiment [0066]"),
        "table_prefix": "TABLE-US-00001 d1 (mm) 1.4 d2 (mm) 1.4",
        "ppubs_table_count": 0,
        "architecture_phrase_counts": {
            "Family ID: 77725725": 1,
            "imaging lens assembly module": 43,
            "imaging lens assembly driving module": 31,
            "light path folding element": 16,
            "first lens barrel": 80,
            "second lens barrel": 77,
            "rolling bearings": 20,
            "first sensing element": 34,
            "fourth sensing element": 17,
            "plastic lens elements": 33,
            "smartphone": 1,
            "image sensor": 12,
            "FIG. 1 E is an optical surface schematic view": 2,
            "TABLE-US-00001": 1,
        },
    },
}
_ENDOSCOPIC_THREE_LENS_MISSING_F_NUMBER_TITLE_PATTERN = re.compile(
    r"\bOPTICAL\s+IMAGING\s+LENS\s+ASSEMBLY\s+AND\s+ENDOSCOPIC\s+OPTICAL\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_ENDOSCOPIC_THREE_LENS_FIGURES = tuple(range(1, 12))
_ENDOSCOPIC_THREE_LENS_SYSTEM_ROWS = (
    "EFL 0.43 f1 -0.35 f2 0.60 f3 0.59 HFOV 60.00",
    "EFL 0.43 f1 -0.34 f2 0.60 f3 0.60 HFOV 60.00",
    "EFL 0.42 f1 -0.33 f2 0.60 f3 0.59 HFOV 60.00",
)
_ENDOSCOPIC_THREE_LENS_TABLE_BINDINGS = (
    (1, 2, 3),
    (4, 5, 6),
    (7, 8, 9),
)
_ENDOSCOPIC_THREE_LENS_MISSING_F_NUMBER_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-11832791-B2": {
        "raw_document_sha256": (
            "2ef9a1fbb3aad09317228a9db6d30d1b9fad67059b7fae25e21655d96301451f"
        ),
        "normalized_text_sha256": (
            "8d5d3edad4daa9845193bdd0e7d0e4d6a530c04a0ee9f334011c319fd7d3c699"
        ),
        "application_number": "17/477544",
        "relationship_markers": ("US 20230091208 A1 Mar. 23, 2023",),
        "table_block_sha256": (
            "bfe01c7f69920951d339edf88608ee8bc1d2d0c603fbabf9985f4a7cf072497c",
            "38644945b7692314a86cc1af5ca78dfa9368571c83fcb45db00c10d206be6ec0",
            "f3514b31c4eaeb5fa85e239484de26853ec2c9518d09d1447db1cabe70381143",
            "15c8628eb6dd710e67335fe076517f12882756cc8ba793736c426b51de5dc6cc",
            "42473c9878f8392b9a12e0bdf7ee861f37af471f953151f760d268f60208160d",
            "e5b1f6779b7bca3b926ef16831dffaa21f73221b6d9ff07ecfa6bfe87444a8b0",
            "3f7ec1ca0e069bceae57e4b7df8e2a8b0dd34ee46bd3cbb4df4fad202a73e80e",
            "425b6fe580e25de4e005da7ce0852a64e4a16dc75613c5f22f490d53acb2bf93",
            "c8d51023005e1190005dd3b5123273fab826602fd8f96f9084abfb0508f67812",
        ),
    },
    "US-20230091208-A1": {
        "raw_document_sha256": (
            "0ba2fa9864b8a3fc1b2b60af0dfc241eb55b0dcb953ea4f6cafeb3a0a34e475a"
        ),
        "normalized_text_sha256": (
            "78b1cb4de4dc2a7a82e7e19e7c34e0c40725b05d9a17c32ea2ef7fed6c3a47eb"
        ),
        "application_number": "17/477544",
        "relationship_markers": (),
        "table_block_sha256": (
            "90d02fced3e70c9e4f0d74421084fba5ede763e852930bba75219b939a7a575a",
            "d0abdae31aea138557b8b3459ce3b22d10848b0d04217aa8c8eb15a095ce110a",
            "2a8690cb248c52b172ee10e7fc68e2358fca6aef9da36650315f1a1bc7bc8497",
            "d85217f4b07a639ae5ae1cd9945cdf2096baf3470627a3bb02d72c7bb3748a2b",
            "7a1c6252792e85e275370163fd8bd64803194e028f3a3ae775a04aab69836a42",
            "ab44d66af7b265f017174edaf0cf995b84b4a9e3a78c79573c21c3ff24b4e741",
            "b02909799206e6cb96aa6b264556a5ca84d7869c67c09ce9818f770a91f069a9",
            "5a27a1648e7b01f5f62604fad096a6489d2896e2fa378c08d4eb412d10de6eba",
            "3b09b3b9cc93b8c9eac2a600877be07f09e683e3df1a47807cea463aa8493394",
        ),
    },
}
_SUNNY_AUTOMOTIVE_NINETEEN_LENS_TITLE_PATTERN = re.compile(
    r"<h2[^>]*>\s*Optical\s+lens\s+assembly\s+and\s+electronic\s+device\s*</h2>",
    flags=re.IGNORECASE,
)
_SUNNY_AUTOMOTIVE_NINETEEN_LENS_FIGURES = tuple(range(1, 21))
_SUNNY_AUTOMOTIVE_NINETEEN_LENS_TABLE_TITLES = (
    *(str(index) for index in range(1, 40)),
    "40-1",
    "40-2",
    "40-3",
)
_SUNNY_AUTOMOTIVE_NINETEEN_LENS_SYSTEM_TABLE_SHA256 = (
    "0a4a2426030db823644f8c8426ed6602f6959e9850856f7fd3fbd2b84175db39",
    "34019ae05b7c098b2552afad386da06962985ce1abef86ae95188e8241de90e0",
    "ebc4f85c9d6ef85bc6505b0a7da34f026bdfa5986ea1cfbe571b3c103e76f716",
    "627a6a809e0a95331dab0321399019d3410b5118cb5501d4c7550c82bb83c0af",
)
_SUNNY_AUTOMOTIVE_NINETEEN_LENS_SYSTEM_ROWS = (
    (
        "F 15.23 14.26 15.87 16.06 15.33 14.16 15.36 H",
        "FOV 30 30 30 30 30 30 30 ENPD",
        "F/ENPD 1.66 1.68 1.68 1.68 1.68 1.68 1.75 arctan",
    ),
    (
        "F 14.460 14.517 14.277 14.331 FOV",
        "FOV 31.000 31.000 31.000 31.000 F1",
        "F/EPD 1.645 1.645 1.645 1.645 (d4 + d5 + d6)/TTL",
    ),
    (
        "F 14.435 14.887 13.819 13.818 FOV",
        "FOV 31.000 31.000 31.000 31.000 F1",
        "F/EPD 1.645 1.645 1.645 1.645 (d4 + d5 + d6)/TTL",
        "|F6/F] 3.6635 3.8090 7.6029 7.4628 d7/TTL",
    ),
    (
        "F 14.464 14.317 14.871 13.803 FOV",
        "FOV 35.600 35.600 35.600 35.600 F1",
        "F/EPD 1.645 1.645 1.645 1.645 (d4 + d5 + d6)/TTL",
    ),
)
_SUNNY_AUTOMOTIVE_NINETEEN_LENS_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-12591114-B2": {
        "raw_document_sha256": (
            "7128071564aad7e014695521977dcf5aeeaedb2aea3c546364066bdec1fbff8c"
        ),
        "normalized_text_sha256": (
            "621c097f338cc411098b6d403e04a2b5c26cd6744925436ae188e55f82c41c1d"
        ),
        "application_number": "18/326553",
        "family_id": "82157375",
        "table_aggregate_sha256": (
            "3034143515fc6d814a6b604e004be2e78c9f139c4676513343d91c0447e15135"
        ),
        "identity_markers": (
            "Applicant: NINGBO SUNNY AUTOMOTIVE OPTECH CO., LTD (Ningbo, CN)",
            "US 20230367104 A1 Nov. 16, 2023",
            "CN 202011560293.0 Dec. 25, 2020",
            "CN 202110744979.3 Jul. 01, 2021",
            "WO PCT/CN2021/135070 20211202 PENDING",
        ),
    },
}
_AAC_NEAR_EYE_FOLDED_THREE_LENS_TITLE_PATTERN = re.compile(
    r"<h2[^>]*>\s*OPTICAL\s+SYSTEM\s*</h2>",
    flags=re.IGNORECASE,
)
_AAC_NEAR_EYE_FOLDED_THREE_LENS_FIGURES = tuple(range(1, 11))
_AAC_NEAR_EYE_FOLDED_THREE_LENS_TABLE_SHA256 = (
    "2c140f7f09f7682a8af8222c16de017e947e28f7e59ac0a63eee93701b633ca5",
    "59a67c7de41f031e7a222765812e2bc0aaae6ad19bf6c60f819299153f4390ec",
    "3bcbcd7bfbdab7ffa7c6eadcff3e84bc918fe6211c7d9806b0c8897d0ece1ba2",
    "8aed7f63acf17d7709f125eaceca961ca4e92bcac16424cb97ef49cbf9d02ac9",
    "594c0f8f23883467efe88f08f5451e399a442841c1aa6afcd9a5cc1105b3b71f",
)
_AAC_NEAR_EYE_FOLDED_THREE_LENS_SYSTEM_ROWS = (
    "In this embodiment, an entrance pupil diameter ENPD of the optical system "
    "100 is 4.00 mm, an image height IH of 1.0H is 11.500 mm, and a field of "
    "view FOV in a diagonal direction is 89.94°.",
    "In this embodiment, an entrance pupil diameter ENPD of the optical system "
    "100 is 4.00 mm, an image height IH of 1.0H is 11.200 mm, and a field of "
    "view FOV in a diagonal direction is 94.95°.",
)
_AAC_NEAR_EYE_FOLDED_THREE_LENS_PHRASE_COUNTS = {
    "optical path folding structure": 2,
    "reflective polarizing coating": 24,
    "semi-transparent and semi-reflective film": 12,
    "entrance pupil diameter ENPD": 3,
    "image height IH of 1.0H": 2,
    "field of view FOV in a diagonal direction": 2,
    "focal length of the optical system is defined as f": 2,
    "focal length of the second lens": 5,
    "Tables 1 and 2 show the design data": 1,
    "Table 3 and table 4 show the design data": 1,
    "d line is green light with a wavelength of 540 nm": 1,
}
_AAC_NEAR_EYE_FOLDED_THREE_LENS_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-20250271635-A1": {
        "raw_document_sha256": (
            "36dafd2330f060721180c55b169135401815d1dc73e39af434b2912e2037957b"
        ),
        "normalized_text_sha256": (
            "f0f9d8e1b241c27ff4508d009b9eb09b76e0bb320ce28f3e34b8de59e9730d9d"
        ),
        "application_number": "18/731404",
        "owner_count": 1,
        "priority_marker": "CN 202410202541.6 Feb. 23, 2024",
    },
}
_AAC_TELECENTRIC_NINE_LENS_TITLE_PATTERN = re.compile(
    r"\bInventor\(s\)\s+Teranishi;\s*Takaaki\s+CAMERA\s+TELECENTRIC\s+"
    r"LENS\s+Abstract\b",
    flags=re.IGNORECASE,
)
_AAC_TELECENTRIC_NINE_LENS_FIGURES = tuple(range(1, 29))
_AAC_TELECENTRIC_NINE_LENS_EFL_ROW = (
    "f 140.015 228.181 192.943 139.411 167.106 92.494 143.161"
)
_AAC_TELECENTRIC_NINE_LENS_ENTRANCE_PUPIL_DIAMETERS = (
    "4633.628",
    "5000.248",
    "3592.504",
    "3820.700",
    "25971.381",
    "2624.704",
    "4516.334",
)
_AAC_TELECENTRIC_NINE_LENS_DIAGONAL_FIELDS = (
    "0.01",
    "0.03",
    "0.02",
    "0.00",
    "0.03",
    "0.02",
)
_AAC_TELECENTRIC_NINE_LENS_TABLE7_UNDEFINED_SPACING = (
    "R6 32.940 d6= 0.000 d.sub.6-BS= 4.550 d.sub.BS= 35.000 "
    "d.sub.BS-s1= 7.220 d.sub.s1-7= 5.600 G4"
)
_AAC_TELECENTRIC_NINE_LENS_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12585096-B2": {
        "raw_document_sha256": (
            "5bd759cb65d3d9815f6218a79994b91201eb58bb399bea6891abb5673f453987"
        ),
        "normalized_text_sha256": (
            "50209f643a66dde1859ee71576e3558b832b9c47b12ff901ecb6db8acd11080c"
        ),
        "application_number": "18/402737",
        "relationship_markers": ("US 20250102782 A1 Mar. 27, 2025",),
        "table_block_sha256": (
            "306ac2a003d6c899f1af8b1e5e36ab904d206f7728436dd02283354ee398814a",
            "3b137d240c1109be142ad07fa20a9f8a44d946cac7b7724bdc1d96078811eb8e",
            "5c2b5de92f194de2682276db18ad95e41750eae33a5005fd813b3de82235fa39",
            "7e4aa7c6ba50443229b52b5125c432ac2202c2d706df3610b5419c06dba2613a",
            "7dd9d610face823b542c774d07f1a037e10364f1425ff0e632118aed77f5958e",
            "1891ea05d2dc0f86146f23d07a3d1529dfbf652242e47c652cfa8a2013281dee",
            "c22d01feff15031f2b32b9dc9efd58d316cea6a71d03468e3f9377237a282a9c",
            "b4ab1dcefdaef19c09e7eef199e4f8fbff3226576ff5ad4bbcb957a43a12109d",
        ),
    },
    "US-20250102782-A1": {
        "raw_document_sha256": (
            "0d6559cf2668051684f43dc51245307286441d21d0c558ee66728d0d2f1c7625"
        ),
        "normalized_text_sha256": (
            "3b9bfd136910fe58e15feeb9dc1b35c750eb3ac3aafd1ba21888faae42840fae"
        ),
        "application_number": "18/402737",
        "relationship_markers": (),
        "table_block_sha256": (
            "b87e47bd6c8d5f4489e16543a95e96b99ab41f5e5068344d927367dcef946f2e",
            "53c557ff64b95940ee122ce13ba71316e542737651a67a1bafa9b4d3d9d67746",
            "8b1eb7a1114ddf5d771e93c859dff9ca583978c6cbaeaf910c88a607f3ed5cfb",
            "f63364ebd339e8aefb7203245b2f7339ab4a97b3456b89654f2d666a89727961",
            "9a13f5b1005584e322232be3fd3d5f945925da9355d427beab9e23aab9969544",
            "cb5e18281bcd95a9f88321ed52d3ac73bb70142d03f66d314a470a902c83468c",
            "ad1283c9ee8085d5afa8e7928c2177d6942ff8b6a05caa46af193ed8f86c75ef",
            "507c0a28cf5c700e2dcf3ab78bba63c7ded99ba496d6ada8e5a81429e70e392b",
        ),
    },
}
_SAMSUNG_IRIS_MOVING_GROUP_TITLE_PATTERN = re.compile(
    r"\bOPTICAL\s+LENS\s+ASSEMBLY\s+AND\s+ELECTRONIC\s+DEVICE\s+"
    r"COMPRISING\s+SAME\b",
    flags=re.IGNORECASE,
)
_SAMSUNG_IRIS_MOVING_GROUP_FIGURES = tuple(range(1, 19))
_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS = (
    "Samsung iris numerical embodiment 1 visible state",
    "Samsung iris numerical embodiment 1 IR state",
    "Samsung iris numerical embodiment 2 visible state",
    "Samsung iris numerical embodiment 2 IR state",
    "Samsung iris numerical embodiment 3 visible state",
    "Samsung iris numerical embodiment 3 IR state",
)
_SAMSUNG_IRIS_MOVING_GROUP_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-11435552-B2": {
        "raw_document_sha256": (
            "fc7ffce9d6d1ba6245b1cee259c8e63a022c92314840324273e1022f96b73089"
        ),
        "normalized_text_sha256": (
            "be2f3764ff09939c08c1f23718d4b4aa1855ea70384b6c71ac742dc98121edd0"
        ),
        "application_number": "16/485921",
        "relationship_markers": ("US 20200041761 A1 Feb. 06, 2020",),
        "table_block_sha256": (
            "0b3ac9d62fa62d70b258ea142dde60abac804a772db170b0c5bdda04e40d026d",
            "f0078b3f62c29f075de6c2488cbbefce0982e19f4ac0e82a9879fbd5edd1489b",
            "5b92e95c4a868ec6cd00c75cb8b9124521bc14c68f01ec66f1ab6ec980b52474",
            "bb23045ab19b6b0808d67d9db34bed6d506bfbfc3e74ba09aa6ecc9136f19bbb",
            "46fc906c92a60d66c49ab540709d7ac446b864d1c62e2923f76ab9ac4efada4b",
            "c3be6d3c1797c857a46d31c5eea70970919296494f77de0758b85c0466c20584",
            "10d97bbe1daafa60e8d5db3898b0149b74a28bd62ed707a3e28544f3a60410bb",
            "0d684c6ffc7ae7718da9b13e3000fd14016acdcdee06c5886c02db39ca3cd37e",
            "ba00001020ce6977212c64169c8f415657df43cd8f50fef5319a16a2cfc74a08",
            "9a0edf174bcc2ee8fb69797cd91bde24abb54a4445802173e981777cc26d1072",
            "87e15e13c2bc9239447188467dfd84732419d942f743ecc8b7deb8ee3de43101",
        ),
    },
    "US-20200041761-A1": {
        "raw_document_sha256": (
            "41a8a3a3a2183a9129cdde921874fc090aa2471a6af657a2f29195e47ceb2d38"
        ),
        "normalized_text_sha256": (
            "182146469a92e0140562a94e9d85025d8036ca44d40a0918affc4d1a69c10e05"
        ),
        "application_number": "16/485921",
        "relationship_markers": (),
        "table_block_sha256": (
            "6cf459faf11625bcf36dc0bd5b4b8cc5ea1b1dc6db132dbd08c83ab08b2cf494",
            "53d266ca745434e9b3d2cbb551618102a210f8003ca7958dc18f494e7bf7f55e",
            "7ff85931f9a0a64157f2ac7fdc28842423101e6778acada28e56fbef862f2484",
            "00a4411af790acfeaef5c82c3a477b1004dab7dcd888a855e722be9d604b99eb",
            "39ea1b5dfc5605d8752b1e1bc5f34e68efbffd9163159a7da61fcd2623172bde",
            "7c057ce3c83bad154c67bb61cabdc265289c8beecefef75fd8ff7b65e756a3bd",
            "bd135899388721c2ca05b8a059cc6eee172a4ebf40e9ee1a8daf1743b271cd95",
            "0eb93268b525911ccfbda1a7d65a6391f8c3b7de156936d3a2335a1499ce514b",
            "e8e42dce87472d8aeb5d978f887c375c0b68c74d2bea15c0174a9b9ba877a4b5",
            "af9a1da31d2df9302f000ba165ae2ea551448e7c580f27ba5eab775280d12f65",
            "14d512d8aca88610f6e379a5586a84d33ad20c0db7c3ee722143d761718d0a95",
        ),
    },
}
_SAMSUNG_IRIS_FIRST_VISIBLE_LAYOUT = (
    (("obj",), False),
    (("1*",), True),
    (("2*",), False),
    (("3*",), True),
    (("4*",), False),
    (("ST",), False),
    (("6*",), True),
    (("7*",), False),
    (("8*",), True),
    (("9*",), False),
    (("10*",), True),
    (("11*",), False),
    (("12",), True),
    (("13",), False),
    (("IMG",), False),
)
_SAMSUNG_IRIS_FIRST_IR_LAYOUT = (
    (("obj",), False),
    (("1*",), True),
    (("2*",), False),
    (("3*",), True),
    (("4*",), False),
    (("ST",), False),
    (("6*",), True),
    (("7", "(7*-1)"), False),
    (("7-2",), True),
    (("7-3",), True),
    (("7-4",), False),
    (("8*",), True),
    (("9*",), False),
    (("10*",), True),
    (("11*",), False),
    (("12",), True),
    (("13",), False),
    (("IMG",), False),
)
_META_OPTICAL_LAYER_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bMETA-OPTICAL\s+DEVICE\s+AND\s+ELECTRONIC\s+DEVICE\s+"
    r"INCLUDING\s+THE\s+SAME\b",
    flags=re.IGNORECASE,
)
_META_OPTICAL_LAYER_ARCHITECTURE_ONLY_DRAWINGS = (
    *((str(index), "") for index in range(1, 12)),
    *((str(index), panel) for index in range(12, 17) for panel in ("A", "B")),
    *((str(index), "") for index in range(17, 20)),
)
_META_OPTICAL_LAYER_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-12517281-B2": {
        "raw_document_sha256": (
            "8d33014a60dc3d2cc9d9a02e39831bf45852c1984f46bda6c4f70ce218345068"
        ),
        "normalized_text_sha256": (
            "ab059245b4672308e713c2df51b45d37485236c8b35e869aa9bc4fcf6ab7a9c1"
        ),
        "application_number": "18/097820",
        "relationship_markers": ("US 20230236339 A1 Jul. 27, 2023",),
        "architecture_phrase_counts": {
            "meta-optical device": 156,
            "meta-structure layer": 169,
            "nanostructure": 95,
            "antireflective layer": 51,
            "computational simulation": 18,
            "transmittance": 22,
            "focal length": 3,
            "F number": 1,
        },
    },
    "US-20260093056-A1": {
        "raw_document_sha256": (
            "925f82e175ec31eb5d9b20eef019db1715d7b01030701edce7453f1cdbc20854"
        ),
        "normalized_text_sha256": (
            "af16fee0a73427814535b21023812fc614949042a09f5504122e69b037853f14"
        ),
        "application_number": "19/413947",
        "relationship_markers": (
            "parent US continuation 18097820 20230117",
            "This present application is a continuation of U.S. application Ser. No. "
            "18/097,820, filed on Jan. 17, 2023",
        ),
        "architecture_phrase_counts": {
            "meta-optical device": 156,
            "meta-structure layer": 159,
            "nanostructure": 91,
            "antireflective layer": 50,
            "computational simulation": 18,
            "transmittance": 22,
            "focal length": 3,
            "F number": 1,
        },
    },
}
_EDOF_MICROSCOPE_SOURCE_TITLE_PATTERN = re.compile(
    r"\bSYSTEMS\s+AND\s+METHODS\s+FOR\s+EXTENDED\s+DEPTH-OF-FIELD\s+MICROSCOPY\b",
    flags=re.IGNORECASE,
)
_EDOF_MICROSCOPE_EXAMPLE_HEADINGS = (
    "Example I: Theoretical Analysis of Deconvolution-Free EDOF Microscopy",
    "Example II: Infinity-Corrected EDOF Microscope",
    "Example III: Infinity-Corrected Object-Space Telecentric Varifocal "
    "Microscope Objective with Electrically Tunable Liquid-Filled Lens",
    "Example IV: EDOF Microdeflectometry Results",
    "Example V: Experimental Demonstration of EDOF SIM",
)
_EDOF_MICROSCOPE_FIGURE_EXPRESSIONS = (
    *((str(index)) for index in range(1, 15)),
    "15A and 15B",
    *((str(index)) for index in range(16, 22)),
    "22A and 22B",
    "23",
    "24",
    "25A-C",
    "26",
    "27A and 27B",
    "28",
    "29",
    "30",
    "31A and 31B",
    "32",
    "33A and 33B",
    "34A-C",
    "35",
    "36A and 36B",
    "37A-E",
    "38A-F",
    "39A and 39B",
    "40A-F",
    "41A and 41B",
    "42A-E",
)
_EDOF_MICROSCOPE_ITEM_LABELS = (
    "Example I: theoretical analysis of deconvolution-free EDOF microscopy",
    "Example II: infinity-corrected EDOF microscope architecture",
    "Example III: telecentric varifocal microscope objective prescription",
    "Example IV: EDOF microdeflectometry results",
    "Example V: experimental EDOF structured-illumination microscopy results",
)
_EDOF_MICROSCOPE_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-10725279-B2": {
        "raw_document_sha256": (
            "df938fc2c5990798bf030f1da721c9fa4896aa031470b01c576ccba18299f91b"
        ),
        "normalized_text_sha256": (
            "4f33518c76f6b68854991c1d9b474f45d448b68c726b57f132071414915fa35c"
        ),
        "application_number": "16/092071",
        "owner_count": 2,
        "relationship_markers": (
            "US 20190162945 A1 May. 30, 2019",
            "us-provisional-application US 62320275 20160408",
        ),
        "table_sha256": (
            "d7b844bdf21ef1792cb616673cd828e2a56a9800f15b8ab464aa46260149b1fc"
        ),
        "phrase_counts": {
            "Table 1 (below) lists a design specification": 1,
            "2 mm and the numerical aperture is 0.24 NA": 1,
            "constant 2-mm diameter field of view with 0.25 NA": 2,
            "working wavelength centered at 530 nm": 2,
            "working wavelength at 550 nm": 1,
            "focus scanning range is 2 mm, which is 125 times of the diffraction "
            "limited DOF": 1,
            "effective focal length": 2,
        },
    },
    "US-20190162945-A1": {
        "raw_document_sha256": (
            "eb7cb67e831cc1c63467fbd8c93e1d2583395048fc8e78bbb764ffcd88095bbc"
        ),
        "normalized_text_sha256": (
            "ec772f1c1b8a1ce6f1664c0c782d8466d5b9f9ccf5108593d54cea7d2660484f"
        ),
        "application_number": "16/092071",
        "owner_count": 1,
        "relationship_markers": (
            "us-provisional-application US 62320275 20160408",
        ),
        "table_sha256": (
            "d7b844bdf21ef1792cb616673cd828e2a56a9800f15b8ab464aa46260149b1fc"
        ),
        "phrase_counts": {
            "Table 1 (below) lists a design specification": 1,
            "2 mm and the numerical aperture is 0.24 NA": 1,
            "constant 2-mm diameter field of view with 0.25 NA": 2,
            "working wavelength centered at 530 nm": 2,
            "working wavelength at 550 nm": 1,
            "focus scanning range is 2 mm, which is 125 times of the diffraction "
            "limited DOF": 1,
            "effective focal length": 2,
        },
    },
}
_DEFORMABLE_LENS_ACTUATOR_TITLE_PATTERN = re.compile(
    r"<h2[^>]*>\s*APPARATUS\s+AND\s+METHOD\s+COMPRISING\s+DEFORMABLE\s+"
    r"LENS\s+ELEMENT\s*</h2>",
    flags=re.IGNORECASE,
)
_DEFORMABLE_LENS_ACTUATOR_DRAWINGS = (
    *((f"FIG. {index}") for index in range(1, 20)),
    "FIG. 20 and FIG. 21",
    "FIGS. 22-24",
    "FIG. 25",
    "FIG. 26",
    "FIG. 27",
    "FIG. 28",
)
_DEFORMABLE_LENS_ACTUATOR_ITEM_LABEL = (
    "Example 1 and deformable-lens actuator/imaging-terminal architecture"
)
_DEFORMABLE_LENS_ACTUATOR_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-20160088216-A1": {
        "raw_document_sha256": (
            "041e2e327a607a20c6f625fa2ae0564e01ba97eb619c0a1dc58ca74a3e97c38f"
        ),
        "normalized_text_sha256": (
            "1c68002ba8e35f10315564a2800c913f8175704ecf28d18988bf878c529aa3f1"
        ),
        "application_number": "14/958173",
        "owner_count": 2,
        "relationship_markers": (
            "parent US continuation 13964801 20130812",
            "parent US division 12901242 20101008",
            "parent US division 11897924 20070831",
            "us-provisional-application US 60961036 20070718",
            "us-provisional-application US 60875245 20061215",
        ),
        "table_block_sha256": (
            "f9098ad5d4e6f926191d8826f24cb04434aa138461b6a091983700c9d75159cc",
            "3aafdbc43e7344646701f0eeef63e0be2f836b34515df9b06671ea437400eac9",
            "298c7208ed2077f62f7ec40481e6cfe5c5627cc28f8ecdb65d12a6c8d880fe85",
            "3d9f239b2926c84f8e066144894dff87dda8eeeb09e6a9494348fec386586188",
        ),
        "phrase_counts": {
            "lens triplet imaging lens assembly of an IT5000 Image Engine": 1,
            "focal length of 5.88 mm": 1,
            "an F# of 6.6": 1,
            "nominal fixed best focus distance of 36 inches": 1,
            "half FOV": 2,
            "lens element surface curvature": 1,
            "The results are summarized in Table C below": 1,
            "Various operator selectable configurations are summarized in Table D below": 1,
        },
    },
    "US-9699370-B2": {
        "raw_document_sha256": (
            "88d9daf89b28d35136db8a275cfa6928e7d7ed2f80e1eae72635ded465457d96"
        ),
        "normalized_text_sha256": (
            "3d8a5f8e677dc57ee70f3a8090ed6e2fee8f6ead1f42460f3d0c2f247e070189"
        ),
        "application_number": "14/958173",
        "owner_count": 3,
        "relationship_markers": (
            "US 20160088216 A1 Mar. 24, 2016",
            "continuation parent-doc US 13964801 20130812 US 9207367 child-doc US 14958173",
            "division parent-doc US 12901242 20101008 US 8505822 child-doc US 13964801",
            "division parent-doc US 11897924 20070831 US 7813047 child-doc US 12901242",
            "us-provisional-application US 60961036 20070718",
            "us-provisional-application US 60875245 20061215",
        ),
        "table_block_sha256": (
            "ba57630b4d0d286d47030638201421994536399f4c096bf0150f42818b05f4e3",
            "a5314a30588e0ed8f789b4f378c1915506640aae601cdb9bc08f29adff8ab7b5",
            "298c7208ed2077f62f7ec40481e6cfe5c5627cc28f8ecdb65d12a6c8d880fe85",
            "3d9f239b2926c84f8e066144894dff87dda8eeeb09e6a9494348fec386586188",
        ),
        "phrase_counts": {
            "lens triplet imaging lens assembly of an IT5000 Image Engine": 1,
            "focal length of 5.88 mm": 1,
            "an F# of 6.6": 1,
            "nominal fixed best focus distance of 36 inches": 1,
            "half FOV": 2,
            "lens element surface curvature": 1,
            "The results are summarized in Table C below": 1,
            "Various operator selectable configurations are summarized in Table D below": 1,
        },
    },
}
_CATADIOPTRIC_MODULE_ARCHITECTURE_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY\s+MODULE\s*,\s*CAMERA\s+MODULE\s+AND\s+"
    r"ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_CATADIOPTRIC_MODULE_DRAWINGS = (
    ("1", "A"),
    ("1", "B"),
    ("1", "C"),
    ("1", "D"),
    ("1", "E"),
    ("2", ""),
    ("3", ""),
    ("4", "A"),
    ("4", "B"),
    ("5", "A"),
    ("5", "B"),
    ("5", "C"),
    ("5", "D"),
    ("5", "E"),
    ("6", ""),
    ("7", "A"),
    ("7", "B"),
    ("7", "C"),
)
_CATADIOPTRIC_MODULE_TABLE_KEYS = (
    (1, "A"),
    (1, "B"),
    (2, "A"),
    (2, "B"),
    (3, "A"),
    (3, "B"),
    (3, "C"),
    (3, "D"),
    (4, "A"),
    (4, "B"),
)
_CATADIOPTRIC_MODULE_EXAMPLES = (
    (1, 1, "1A", "1B"),
    (1, 2, "2A", "2B"),
    (1, 3, "3A", "3D"),
    (2, 3, "3B", "3D"),
    (3, 3, "3C", "3D"),
    (1, 4, "4A", "4B"),
)
_CATADIOPTRIC_MODULE_SYSTEM_ROWS = {
    "D (mm) 3.05 FNO 1.82 FOV (degrees) 19.1": 2,
    "D (mm) 2.49 FNO 2.2 FOV (degrees) 16.5": 2,
}
_CATADIOPTRIC_MODULE_ARCHITECTURE_ONLY_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-12631860-B2": {
        "raw_document_sha256": (
            "053e22371b8427c36702a98d7d4992c0ff86771fb8fa5391c04103982d8ee9f5"
        ),
        "normalized_text_sha256": (
            "f5340d3edabdf94df8663b8b12514b77abe50380786603baef9b1f7401e6a16a"
        ),
        "application_number": "18/474353",
        "heading_markers": (
            "1st Embodiment (39)",
            "2nd Embodiment (53)",
            "3rd Embodiment (65)",
            "4th Embodiment (78)",
            "5th Embodiment (89)",
            "6th Embodiment (98)",
            "7th Embodiment (101)",
        ),
        "relationship_markers": (
            "US 20240111139 A1 Apr. 04, 2024",
            "us-provisional-application US 63377730 20220930",
        ),
        "table_block_sha256": (
            "ff78a2555e5d8dac5b8b11e5a9c2fa21cfee9f5b5088c97dbcc4971542798ba1",
            "713372b4007aa6577862e54dd0d8e5b3f85d216f5b68b68a5207a97be6561d86",
            "54eb349fefd46805db4b725d13ca42574d0b22df44d058e8abdb204548d0d3a4",
            "4192393f098d9a717e307be6af9f0bc0a402639299433a12845c52c1629b9b91",
            "4cd295d8129cf358fd35d1fa637d96770cc81eef84d198b107655031227cdff6",
            "a92a3563fceb52cc338c9efdef738bc3600fb7fdc9ad929e8c61ba004988f4ee",
            "5b29dbf941ef16abef7b762caf161f1c2790975acfca7ec9bfdd728843412d1b",
            "854e06d91b9e8d884c261802aeda805e666099681ab2f2248963e6de9dc48a85",
            "12d8a09996586c3f33034596c5b93c11cf515e4eaf2cc73b08de649f7667d176",
            "3d54804752b53c6ba0cfb4e46f345b48f4414d6c877329a908ec8a59e200a99d",
        ),
    },
    "US-20260153717-A1": {
        "raw_document_sha256": (
            "0c6ae9d0c0d4606ebc29235e993f71ce459bf04a875f586c00eda9869c356990"
        ),
        "normalized_text_sha256": (
            "57f16c924738b6790604ef5cdc3a08f9e1a70b3c6e3e93cac0c8ccfb721a062a"
        ),
        "application_number": "19/460417",
        "heading_markers": (
            "1st Embodiment [0045]",
            "2nd Embodiment [0057]",
            "3rd Embodiment [0067]",
            "4th Embodiment [0076]",
            "5th Embodiment [0085]",
            "6th Embodiment [0094]",
            "7th Embodiment [0097]",
        ),
        "relationship_markers": (
            "parent US continuation 18474353 20230926 PENDING child US 19460417",
            "us-provisional-application US 63377730 20220930",
            "This application is a continuation of U.S. application Ser. No. 18/474,353, "
            "filed Sep. 26, 2023",
        ),
        "table_block_sha256": (
            "f4e8a8b604eb7ded2334acd2d0ef9dd586d3c30dc20d4379577da86726e5180c",
            "3523e4c65f688f787dc4e3a340d8e2e7a4e129dae6c9e091656eec0a3a989be5",
            "4783525745e6a4c3702fa4e0513b09f66f4d41cb245829141994a1786f107917",
            "9cb55ca5416e169488a0c3ef803e4c2c680c6bae92cde3194129e00a16599026",
            "5877e166374371539af904103e00971c7f94cc8d4c220c0089414bf6e774f651",
            "0dca36e21261677ad10019d509317b1358ae5b243f2ea2efec30cbc3c0c4e7b8",
            "f637d636e916fb6515ad4ac7d06829ba266eb1b551d5509e343211942eec9c29",
            "3aec30c99949d8ad9d9e90d8ac20450f041c9361508fd65d6ff3fcc9c99d0d91",
            "f6f0ba64f53a08d12be4dcc730e7eb78ba12b78f6e7ae91382426ca2cf05e254",
            "abf6f2b5d14b7516d930bf3ac163ec938ddad382ae7bce992bafb849851db09f",
        ),
    },
}
_SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_ONLY_TITLE_PATTERN = re.compile(
    r"\bSHIFTABLE\s+CIRCUIT\s+ELEMENT\s*,\s*SHIFTABLE\s+IMAGE\s+SENSOR\s+"
    r"MODULE\s*,\s*CAMERA\s+MODULE\s+AND\s+ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_TABLE_ROWS = (
    "TABLE-US-00001 TABLE 1A the 1st example of the 1st embodiment "
    "Dc (mm) 0.14 We (mm) 0.07 Wc (mm) 0.04 He (mm) 0.25 "
    "Dc/Wc 3.5 We/He 0.28 N 28",
    "TABLE-US-00002 TABLE 1B the 2nd example of the 1st embodiment "
    "Dc (mm) 0.18 We (mm) 0.05 Wc (mm) 0.03 He (mm) 0.30 "
    "Dc/Wc 6.0 We/He 0.167 N 36",
    "TABLE-US-00003 TABLE 1C the 3rd example of the 1st embodiment "
    "Dc (mm) 0.10 We (mm) 0.08 Wc (mm) 0.04 He (mm) 0.20 "
    "Dc/Wc 2.5 We/He 0.40 N 32",
)
_SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_DRAWINGS = (
    ("1", "A"),
    ("1", "B"),
    ("1", "C"),
    ("1", "D"),
    ("1", "E"),
    ("1", "F"),
    ("2", "A"),
    ("2", "B"),
    ("2", "C"),
    ("2", "D"),
    ("2", "E"),
    ("3", ""),
    ("4", "A"),
    ("4", "B"),
    ("4", "C"),
)
_SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_ONLY_SOURCE_PROFILES: dict[
    str, dict[str, Any]
] = {
    "US-12470822-B2": {
        "raw_document_sha256": (
            "3086bf4acc39aeeae39659b5bebc51c39b46b1eed93c89bce69f572c087d0b30"
        ),
        "normalized_text_sha256": (
            "2c1bc5322a375ec0c247ac1c595e78063ed76ffe8c1fb6ddd262dd4a30d85313"
        ),
        "application_number": "18/337472",
        "heading_markers": (
            "1st Embodiment (46)",
            "2nd Embodiment (65)",
            "3rd Embodiment (74)",
            "4th Embodiment (78)",
        ),
        "relationship_markers": (
            "US 20240007748 A1 Jan. 04, 2024",
            "TW 112106819 Feb. 23, 2023",
            "us-provisional-application US 63357070 20220630",
        ),
        "architecture_phrase_counts": {
            "Family ID: 86764397": 1,
            "shiftable image sensor module": 34,
            "conductive wire units": 119,
            "imaging lens assembly module": 16,
            "ultra-wide angle camera module": 5,
            "high resolution camera module": 4,
            "telephoto camera module": 6,
            "Time-Of-Flight (TOF) module": 1,
            "fold the light": 1,
            "different focal lengths": 1,
        },
    },
    "US-20260039960-A1": {
        "raw_document_sha256": (
            "ae90751842fc7ce931d7f1302fe801b5f709fa7702ce52473cc129997e546044"
        ),
        "normalized_text_sha256": (
            "d9976c5a5c704c92fe98d703c232357dd1632aedbca1d029e6af1bd5469dcfc8"
        ),
        "application_number": "19/353732",
        "heading_markers": (
            "1st Embodiment [0052]",
            "2nd Embodiment [0068]",
            "3rd Embodiment [0077]",
            "4th Embodiment [0081]",
        ),
        "relationship_markers": (
            "TW 112106819 Feb. 23, 2023",
            "parent US continuation 18337472 20230620",
            "parent-grant-document US 12470822 child US 19353732",
            "us-provisional-application US 63357070 20220630",
        ),
        "architecture_phrase_counts": {
            "Family ID: 86764397": 1,
            "shiftable image sensor module": 36,
            "conductive wire units": 102,
            "imaging lens assembly module": 16,
            "ultra-wide angle camera module": 5,
            "high resolution camera module": 4,
            "telephoto camera module": 6,
            "Time-Of-Flight (TOF) module": 1,
            "fold the light": 1,
            "different focal lengths": 1,
        },
    },
}
_CIRCLE_OPTICS_MECHANICAL_ONLY_TITLE_PATTERN = re.compile(
    r"\bOPTO-MECHANICS\s+OF\s+PANORAMIC\s+CAPTURE\s+DEVICES\s+WITH\s+"
    r"ABUTTING\s+CAMERAS\b",
    flags=re.IGNORECASE,
)
_CIRCLE_OPTICS_MECHANICAL_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12092800-B2": {
        "raw_document_sha256": (
            "162be98ab26d3e96a81dddd8350a4c2ec1588133fd4751719ca8b31fbb1a3335"
        ),
        "normalized_text_sha256": (
            "e7ee0f720a571939785c685b5b2cc517d66e43da25edcbc5c3088abd52ac45e5"
        ),
        "application_number": "17/622393",
        "drawing_description_count": 28,
        "architecture_phrase_counts": {
            "Family ID: 74060373": 1,
            "outer compressor": 11,
            "aperture stop": 19,
            "image plane": 34,
            "aspheric surfaces": 1,
            "lens element thicknesses and curvatures": 1,
            "FIG. 8 depicts an image sensor with a sensor mount having adjustors": 1,
            "FIG. 21 depicts an alternate configuration for an improved multi-camera "
            "projection device": 1,
        },
    },
}
_LIGHT_BLOCKING_GEOMETRY_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY\s+MODULE\s*,\s*CAMERA\s+MODULE\s+AND\s+"
    r"ELECTRONIC\s+DEVICE\b",
    flags=re.IGNORECASE,
)
_LIGHT_BLOCKING_GEOMETRY_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-12001077-B2": {
        "normalized_text_sha256": (
            "83bced2427a357d878458607be067736e62e64548bc20f19a3ed2540218a458c"
        ),
        "table_count": 14,
        "geometry_phrase_counts": {
            "Family ID: 78608859": 1,
            "imaging lens assembly module": 213,
            "light blocking structure": 212,
            "light blocking opening": 282,
            "first curvature radius": 52,
            "second curvature radius": 45,
            "lens element": 269,
            "field of view": 18,
            "FOV (degree)": 14,
        },
    },
    "US-12405441-B2": {
        "normalized_text_sha256": (
            "8d724d5cc2442fb2637318615b76fb1c6ce312b5171376edb1b7561c93c21622"
        ),
        "table_count": 14,
        "geometry_phrase_counts": {
            "Family ID: 78608859": 1,
            "imaging lens assembly module": 196,
            "light blocking structure": 208,
            "light blocking opening": 270,
            "first curvature radius": 48,
            "second curvature radius": 41,
            "lens element": 256,
            "field of view": 17,
            "FOV (degree)": 14,
        },
    },
    "US-20210364725-A1": {
        "normalized_text_sha256": (
            "b1ef346be3187db3c6bf9bde364ac4267c91cd652ec4a0172172101ed6617eb4"
        ),
        "table_count": 14,
        "geometry_phrase_counts": {
            "Family ID: 78608859": 1,
            "imaging lens assembly module": 213,
            "light blocking structure": 212,
            "light blocking opening": 282,
            "first curvature radius": 52,
            "second curvature radius": 45,
            "lens element": 269,
            "field of view": 18,
            "FOV (degree)": 14,
        },
    },
    "US-20240280784-A1": {
        "normalized_text_sha256": (
            "3f7c2d12e5dfe7ebfc5a8e21dcde9baaf64fef29c678bb8c3797e5e16a9f7ac4"
        ),
        "table_count": 14,
        "geometry_phrase_counts": {
            "Family ID: 78608859": 1,
            "imaging lens assembly module": 196,
            "light blocking structure": 208,
            "light blocking opening": 270,
            "first curvature radius": 48,
            "second curvature radius": 41,
            "lens element": 256,
            "field of view": 17,
            "FOV (degree)": 14,
        },
    },
}
_FOLDED_TELE_MISSING_F_NUMBER_TITLE_PATTERN = re.compile(
    r"\bZOOM\s+DUAL\s*[- ]?APERTURE\s+CAMERA\s+WITH\s+FOLDED\s+LENS\b",
    flags=re.IGNORECASE,
)
_FOLDED_TELE_MISSING_F_NUMBER_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-10571665-B2": {
        "normalized_text_sha256": (
            "a7214ec208151fe0eb684e41b035adf7712573b4ea682f76da3d086997b88b2d"
        ),
        "lens_module_220_c_count": 2,
    },
    "US-11042011-B2": {
        "normalized_text_sha256": (
            "8a6b73cca2bbe21467a6d068ba1a6ad3b22de77adf44ba1ae2932b8f060c52dc"
        ),
        "lens_module_220_c_count": 2,
    },
    "US-11703668-B2": {
        "normalized_text_sha256": (
            "230470eef9ba561e9fbc99a3f75b2693d70647625735b8177a85007471194bab"
        ),
        "lens_module_220_c_count": 2,
    },
    "US-11982796-B2": {
        "normalized_text_sha256": (
            "a805a3cee37ea20ea6d9b198a03c30d2f7afbccb4d212e3f3beedcea46019300"
        ),
        "lens_module_220_c_count": 2,
    },
    "US-12663618-B2": {
        "normalized_text_sha256": (
            "c05a97a8b839514495a6f5ece2d4eb2724c6fc50dacec141daadf3f34e95b1bf"
        ),
        "lens_module_220_c_count": 2,
    },
    "US-20160044250-A1": {
        "normalized_text_sha256": (
            "8bec326bf0ecc72d7a3965b01465c05a5efe6484ceabc79b023bc29644d33642"
        ),
        "lens_module_220_c_count": 1,
    },
    "US-20200057282-A1": {
        "normalized_text_sha256": (
            "49345928fbad7d934b116bb97eb1b98ae3249d4eb3bef74277edb1fea405555f"
        ),
        "lens_module_220_c_count": 2,
    },
    "US-20220382024-A1": {
        "normalized_text_sha256": (
            "68480e54aa353e67767a85176ef96db1542751d8466080a1192894baaee7692e"
        ),
        "lens_module_220_c_count": 2,
    },
}
_BARREL_SPACER_GEOMETRY_ONLY_TITLE_PATTERN = re.compile(
    r"\bIMAGING\s+LENS\s+ASSEMBLY(?:\s*,\s*CAMERA\s+MODULE\s+AND\s+"
    r"ELECTRONIC\s+DEVICE)?\b",
    flags=re.IGNORECASE,
)
_BARREL_SPACER_GEOMETRY_ONLY_SOURCE_PROFILES: dict[str, dict[str, Any]] = {
    "US-11372191-B2": {
        "normalized_text_sha256": (
            "79e834444da228951da14657ad4854b086fcb22baa18baa0d9b62ceacd927eab"
        ),
        "geometry_phrase_counts": {
            "Family ID: 63640526": 1,
            "imaging lens assembly": 128,
            "plastic barrel": 93,
            "spacer": 68,
            "lens element": 206,
            "stray light": 41,
            "d (mm)": 3,
        },
    },
    "US-12228785-B2": {
        "normalized_text_sha256": (
            "49f397a92f850d7a1140f286f6cf93cb442bd41091f6e7df2c6dec4863e1dede"
        ),
        "geometry_phrase_counts": {
            "Family ID: 63640526": 1,
            "imaging lens assembly": 128,
            "plastic barrel": 92,
            "spacer": 67,
            "lens element": 208,
            "stray light": 41,
            "d (mm)": 3,
        },
    },
    "US-20220276460-A1": {
        "normalized_text_sha256": (
            "511956f91d4563f333c65d5ffd4496dfadaa8eacba56b043dce6efd6e331bfba"
        ),
        "geometry_phrase_counts": {
            "Family ID: 63640526": 1,
            "imaging lens assembly": 128,
            "plastic barrel": 93,
            "spacer": 68,
            "lens element": 206,
            "stray light": 41,
            "d (mm)": 3,
        },
    },
    "US-20230341649-A1": {
        "normalized_text_sha256": (
            "d9e4f6c055e64b6f14bf5c4b607a9a9ff829b66cd919acc5a71805c937e0f802"
        ),
        "geometry_phrase_counts": {
            "Family ID: 63640526": 1,
            "imaging lens assembly": 130,
            "plastic barrel": 96,
            "spacer": 70,
            "lens element": 210,
            "stray light": 41,
            "d (mm)": 3,
        },
    },
    "US-20250147264-A1": {
        "normalized_text_sha256": (
            "38e02b10a61edf345b113dd889d601a44d3badecddaa146fd8b7c595fefb7a36"
        ),
        "geometry_phrase_counts": {
            "Family ID: 63640526": 1,
            "imaging lens assembly": 112,
            "plastic barrel": 81,
            "spacer": 64,
            "lens element": 189,
            "stray light": 41,
            "d (mm)": 3,
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
_ABILITY_THREE_FIVE_LENS_PROFILE = (
    "ability_three_five_lens_angular_field_unpublished_v1"
)
_ABILITY_THREE_FIVE_LENS_ROLE_PAGE_NUMBERS = {
    "ability_three_five_prescription_ol1": 5,
    "ability_three_five_prescription_ol2": 6,
    "ability_three_five_prescription_ol3": 7,
    "ability_three_five_system_meta": 8,
}
_ABILITY_THREE_FIVE_LENS_PUBLICATION_SOURCES = {
    "US-11719909-B2": {
        "primary_html_sha256": (
            "f43a4a419a082df67f60af279a3053069903b81eac017ba14d55359904840987"
        ),
        "normalized_text_sha256": (
            "9a41a01aeb9a626685aa3a7939d2c34c3dd442573accf78a2de062fb73b72910"
        ),
        "application_number": "16/883126",
        "page_count": 13,
        "blank_key_pages": frozenset({5, 6, 7, 8}),
        "key_page_image_sha256": {
            "ability_three_five_prescription_ol1": (
                "d228c17cc75a9ee07221c983939fe84a2c52227b946d4973a8b4b9a76c7f1fbc"
            ),
            "ability_three_five_prescription_ol2": (
                "07969a02deff4c2b837b465d7218e1ef992b4f0e4b34578efbb1a90b0070ea28"
            ),
            "ability_three_five_prescription_ol3": (
                "71d564b5a924d610faf1434749a7798fb097923815b32960fb94cf5f6874354d"
            ),
            "ability_three_five_system_meta": (
                "f9d78791e50b3bb8f6aeb5b913f8e7727f6c58d566d3b334fe8dcf33fc4f7206"
            ),
        },
    },
    "US-20210026108-A1": {
        "primary_html_sha256": (
            "a94cba4e581ebdb5b65798212ca6211170174ac43d60e539cce2152cf9d6c8de"
        ),
        "normalized_text_sha256": (
            "49c30c4ae4049648ef33fd99bc6a5eb0f00c4da7f6e9c97949f5f1dc041e68d1"
        ),
        "application_number": "16/883126",
        "page_count": 13,
        "blank_key_pages": frozenset(),
        "key_page_image_sha256": {
            "ability_three_five_prescription_ol1": (
                "95742709b43e371b5f6c8bae4765cf46bea3609c5046d15de40742113c189c9b"
            ),
            "ability_three_five_prescription_ol2": (
                "d4e2eb07042851f8025ea6037d2b654a1f2941c248ad64dfba28683b4448abda"
            ),
            "ability_three_five_prescription_ol3": (
                "bd904a31f239fb583b2183d901dbeb37a9a30769938a548b728a4f11d9da51d9"
            ),
            "ability_three_five_system_meta": (
                "c2cf657990d7773f275578e988a59797a43803bcb086ac335eb0ee1fc805b23c"
            ),
        },
    },
}
_ABILITY_TWO_FIVE_LENS_PROFILE = "ability_two_five_lens_prescriptions_v1"
_ABILITY_TWO_NINE_LENS_PROFILE = "ability_two_nine_lens_f_number_unpublished_v1"
_ABILITY_FOUR_EIGHT_LENS_PROFILE = "ability_four_eight_lens_f_number_unpublished_v1"
_ABILITY_FIVE_THREE_LENS_PROFILE = (
    "ability_five_three_lens_f_number_unpublished_v1"
)
_AAC_TWO_THREE_LENS_PROFILE = "aac_two_three_lens_field_unpublished_v1"
_AAC_TWO_THREE_LENS_PUBLICATION_SOURCES = {
    "US-20160161712-A1": {
        "primary_html_sha256": (
            "d442fce31a21057546974505b5aa3e5361304ad8525afe7455a4cb438bfb5600"
        ),
        "normalized_text_sha256": (
            "99c5ebf699ef689f6769d12e6a755c33eda8e3fac4021eccdf3f36abf693213d"
        ),
        "application_number": "14/832442",
        "page_count": 7,
        "table_block_sha256": [
            "e2ec3a72c80cf18601e0ee782c9550d9feffd600aea8d06081b122c0955586f5",
            "5c1f1c74edb0ba1ffd97f8b5d86808d4cae516047cf9059cd533d1d3facdb386",
            "efb81b625b9f8f04857d955c7beee11576014688f8103baf4b312950bcc836e5",
            "01ff5df296ef054c678b06fa3a1db72a3c96446e724e0fc6a60a8fec22afe39a",
            "c006d1ce1ef4a7827d844fa46e812622007675de3b8473228d817430dc0812c5",
        ],
    },
    "US-9810879-B2": {
        "primary_html_sha256": (
            "cd5bc9f6cab04ac685e4dca612a9b974767d03f6021fd7527230bdbafc7d3047"
        ),
        "normalized_text_sha256": (
            "f4b1e6f46bcf5d0bb7ab11e94de42ab706d8a488f58df6cd6a572e54e0bf086f"
        ),
        "application_number": "14/832442",
        "page_count": 7,
        "table_block_sha256": [
            "d69322ee49d979453728e3c539d7d3183aa3e2194696493b2e067d64bdad983f",
            "7284512e5e41cef0396f8ed743fdad0db2f51b61ecc1d4c2ca50430c7686d49a",
            "fe5eac295bf9b7dc5a45ad7cc26919d80f1e1ce507053800862a2009e0e0dfc0",
            "c76b393f657e9556021def9b4de7cb2df010736be818ecb60797f490748e9700",
            "a1263ba358ad89aec023c81b6cee8073f8fdf2968987eb7f3f5af4b99a2ce94b",
        ],
    },
}
_ABILITY_FIVE_THREE_LENS_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
)
_ABILITY_FIVE_THREE_LENS_ROLE_PAGE_NUMBERS = {
    **{
        f"ability_five_three_surface_{embodiment}": page_number
        for embodiment, page_number in enumerate((4, 8, 12, 16, 20), start=1)
    },
    **{
        f"ability_five_three_asphere_{embodiment}": page_number
        for embodiment, page_number in enumerate((5, 9, 13, 17, 21), start=1)
    },
    "ability_five_three_meta": 22,
}
_ABILITY_FIVE_THREE_LENS_PUBLICATION_SOURCES = {
    "US-20160085051-A1": {
        "primary_html_sha256": (
            "a389c98016a9f5af18165a30a2041fe29a761d3d37958ffce100e8bfb81ea50d"
        ),
        "normalized_text_sha256": (
            "a7a4d8d7489ef8db8b76b64868fdcf31cfc32b37934a5c17f39484893f212b1f"
        ),
        "application_number": "14/858521",
        "page_count": 27,
    },
    "US-9541733-B2": {
        "primary_html_sha256": (
            "e9fee581375c0ca2c0946fe8b27032c078f14aa82e90aa6365889cd4667319f0"
        ),
        "normalized_text_sha256": (
            "5089537a9bb04df736b4cef2a4146e377b92aced134d7432870fddde145b205c"
        ),
        "application_number": "14/858521",
        "page_count": 26,
    },
}
_LARGAN_THREE_FIVE_LENS_PROFILE = "largan_three_five_lens_prescriptions_v1"
_ABILITY_ZOOM_TWO_STATE_PROFILE = "ability_zoom_two_state_census_v1"
_CIRCLE_OPTICS_SEVEN_LENS_PROFILE = "circle_optics_seven_lens_ocr_review_v1"
_CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT = (
    "provide lens prescription data for the lens",
    "A prescription for this camera lens is given",
    "with glass or material types, axial thicknesses, and surface radii identified",
    "The lens has 7 lens elements",
    "Aspherical surface coefficients are also provided",
    "focused image at F/2.0",
    "nominal focal length of 2.57 mm",
    "aperture stop diameter of 1.42 mm",
)
_CIRCLE_OPTICS_SEVEN_LENS_PUBLICATION_SOURCES = {
    "US-12313825-B2": {
        "primary_html_sha256": (
            "f39a32f7a1eb5004447f43fc12e3bd60c06a55f4f4c50d26e4375e61b17bd154"
        ),
        "application_number": "17/622463",
        "role_page_numbers": {
            "circle_optics_surface_table": 17,
            "circle_optics_asphere_table": 18,
        },
    },
    "US-20250284103-A1": {
        "primary_html_sha256": (
            "449f9a8e066cb4625dd38d76d737a711f216fb45195668f98c25f9c32cebabf4"
        ),
        "application_number": "19/217645",
        "role_page_numbers": {
            "circle_optics_surface_table": 16,
            "circle_optics_asphere_table": 17,
        },
    },
}
_KODAK_LOW_STRESS_TWO_LENS_PROFILE = (
    "kodak_low_stress_two_lens_metadata_unpublished_v1"
)
_KODAK_LOW_STRESS_REQUIRED_TEXT = (
    "FIG. 14A is a table specifying the lens design parameters for the third "
    "exemplary projection lens of FIG. 12A",
    "FIG. 14B is a table specifying the lens design parameters for the third "
    "exemplary relay lens of FIG. 12C",
    "The prescription for the third exemplary projection lens 270, shown in FIG. "
    "12A, is provided in the table of FIG. 14A, with the data for radii (lens shape "
    "or curvature), thicknesses, and materials included.",
    "All the lens surfaces have spherical, rather than aspheric, toric, or "
    "cylindrical profiles.",
    "The prescription for the third exemplary relay lens 250, shown in FIG. 12C, "
    "is provided in the table of FIG. 14B, with the data for radii, thicknesses, "
    "and materials included.",
    "The lens designs prescribed in FIGS. 14A and 14B, and shown in FIGS. 12A and "
    "12C, were fabricated, assembled, and tested",
)
_KODAK_LOW_STRESS_F_NUMBER_CONTEXTS = (
    "relay lens 250 is designed to collect and image F/6 light",
    "projection lens 270 is preferably a faster lens (.about.F/3) than the relay "
    "lens 250",
    "projection lens 270 operates at F/2.5 or faster",
)
_KODAK_LOW_STRESS_PUBLICATION_SOURCES: dict[str, dict[str, Any]] = {
    "US-20140036377-A1": {
        "primary_html_sha256": (
            "2efe34e5641c40bcb2c93d330d9288271b19f2d851f1bba26e03aef85d269819"
        ),
        "normalized_text_sha256": (
            "8affd3aaf0079a69bd7d4a8e68fb31a653b857f6bcbd352b9666d696cd2be572"
        ),
        "application_number": "14/042755",
        "page_count": 61,
        "role_page_numbers": {
            "kodak_projection_prescription": 36,
            "kodak_relay_prescription": 37,
        },
    },
    "US-8649094-B2": {
        "primary_html_sha256": (
            "ddb70ad8434854ab534ae7fb26e1c015147b0ea1518c9ef792f5d112ede1c3e5"
        ),
        "normalized_text_sha256": (
            "1c2a2c4c9be26ae4aa04bcbb80595ea827d5252f89a37c7210e2dc68595c0c98"
        ),
        "application_number": "12/784520",
        "page_count": 60,
        "role_page_numbers": {
            "kodak_projection_prescription": 37,
            "kodak_relay_prescription": 38,
        },
    },
    "US-9069105-B2": {
        "primary_html_sha256": (
            "2e5c75ff60cb61628fb6c256aa18b23a43adbfc04a60fac0974f8a60027173e8"
        ),
        "normalized_text_sha256": (
            "e0196b6186bec0b637bfee3cfc5bdcad39fb273a9275e7894199cb5eff9f857e"
        ),
        "application_number": "14/042755",
        "page_count": 61,
        "role_page_numbers": {
            "kodak_projection_prescription": 37,
            "kodak_relay_prescription": 38,
        },
    },
}
_GENIUS_FOUR_LENS_ELEVEN_PROFILE = "genius_four_lens_eleven_embodiment_census_v1"
_GENIUS_FOUR_LENS_SIX_PROFILE = "genius_four_lens_six_embodiment_census_v1"
_GENIUS_NINE_LENS_ELEVEN_PROFILE = "genius_nine_lens_eleven_embodiment_census_v1"
_GENIUS_EIGHT_LENS_FOURTEEN_PROFILE = (
    "genius_eight_lens_fourteen_embodiment_census_v1"
)
_GENIUS_SEVEN_LENS_SEVEN_PROFILE = "genius_seven_lens_seven_example_census_v1"
_GENIUS_FOUR_LENS_NINE_PROFILE = "genius_four_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_FIVE_PROFILE = "genius_six_lens_five_embodiment_census_v1"
_GENIUS_SIX_LENS_NINE_PROFILE = "genius_six_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE = (
    "genius_six_lens_ten_dual_focus_census_v1"
)
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


def _genius_four_six_page_errors(
    page: dict[str, Any],
    *,
    source_layout: dict[str, Any],
    role: str,
    figure_number: int,
) -> list[str]:
    errors: list[str] = []
    page_index = source_layout["role_pages"][role]
    page_number = page_index + 1
    if page.get("page_number") != page_number:
        errors.append(f"{role} is not retained on page {page_number}")
    expected_image_hash = source_layout["page_image_sha256"][page_index]
    if page.get("official_image_sha256") != expected_image_hash:
        errors.append(f"{role} official raster hash changed")
    mirror_text = page.get("mirror_text")
    if not isinstance(mirror_text, str):
        errors.append(f"{role} mirror text is not a string")
    elif (not mirror_text.strip()) != (
        page_number in source_layout["blank_mirror_pages"]
    ):
        errors.append(f"{role} mirror-text state changed")
    binding_error = _genius_six_page_binding_error(
        page,
        page_number=page_number,
        sheet_number=source_layout["role_sheets"][role],
        sheet_count=source_layout["sheet_count"],
        role=role,
    )
    if binding_error is not None:
        errors.append(binding_error)
    tokens = list(page.get("rapidocr_tokens") or [])
    figure_pattern = re.compile(
        rf"\bFIG\s*\.\s*{figure_number}\b",
        flags=re.IGNORECASE,
    )
    figure_matches = [
        token
        for token in tokens
        if figure_pattern.search(_ability_token_text(token))
    ]
    if len(figure_matches) != 1:
        errors.append(f"{role} has {len(figure_matches)} FIG. {figure_number} OCR tokens")
    elif _ability_token_confidence(figure_matches[0]) < _ABILITY_OCR_LABEL_CONFIDENCE:
        errors.append(
            f"{role} FIG. {figure_number} confidence "
            f"{_ability_token_confidence(figure_matches[0]):.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return errors


def _genius_four_six_optical_census_errors(page: dict[str, Any]) -> list[str]:
    tokens = list(page.get("rapidocr_tokens") or [])
    errors: list[str] = []
    metadata_patterns = {
        "focus": re.compile(r"\bf\s*\(\s*Focus\s*\)\s*=", flags=re.IGNORECASE),
        "half angular field": re.compile(
            r"\bHFO[VW]\s*\([^)]*angular\s+field\s+of\s+view[^)]*\)\s*=",
            flags=re.IGNORECASE,
        ),
    }
    for label, pattern in metadata_patterns.items():
        matches = [
            token
            for token in tokens
            if pattern.search(_ability_token_text(token))
        ]
        if len(matches) != 1:
            errors.append(
                f"four-lens optical metadata {label} has {len(matches)} exact OCR prefixes"
            )
        elif _ability_token_confidence(matches[0]) < _ABILITY_OCR_LABEL_CONFIDENCE:
            errors.append(
                f"four-lens optical metadata {label} confidence "
                f"{_ability_token_confidence(matches[0]):.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
    for label in (
        "Surface",
        "Radius",
        "Thickness",
        "Refractive",
        "index",
        "Abbe",
        "number",
        "Material",
        "Focus",
    ):
        error = _genius_six_exact_label_error(
            tokens,
            label,
            context="four-lens optical table",
        )
        if error is not None:
            errors.append(error)
    return errors


def _genius_four_six_asphere_census_errors(page: dict[str, Any]) -> list[str]:
    tokens = list(page.get("rapidocr_tokens") or [])
    errors: list[str] = []
    heading_matches = [
        token
        for token in tokens
        if "aspherical parameters" in _ability_token_text(token).casefold()
    ]
    if len(heading_matches) != 1:
        errors.append(
            "four-lens asphere heading has "
            f"{len(heading_matches)} OCR tokens; expected 1"
        )
    elif _ability_token_confidence(heading_matches[0]) < _ABILITY_OCR_LABEL_CONFIDENCE:
        errors.append(
            "four-lens asphere heading confidence "
            f"{_ability_token_confidence(heading_matches[0]):.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    for label in ("Surface #", "K", "a4", "a6", "a8", "a10", "a12"):
        error = _genius_six_exact_label_error(
            tokens,
            label,
            context="four-lens asphere table",
            expected_count=2,
        )
        if error is not None:
            errors.append(error)
    return errors


def _genius_four_six_comparison_census_errors(page: dict[str, Any]) -> list[str]:
    tokens = list(page.get("rapidocr_tokens") or [])
    errors: list[str] = []
    for label in ("EFL (mm)", "Fno"):
        matches = [
            token
            for token in tokens
            if _ability_token_text(token).casefold() == label.casefold()
        ]
        if len(matches) != 1:
            errors.append(
                f"four-lens comparison label {label!r} has {len(matches)} OCR tokens"
            )
            continue
        label_token = matches[0]
        confidence = _ability_token_confidence(label_token)
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            errors.append(
                f"four-lens comparison label {label!r} confidence {confidence:.6f} "
                f"is below {_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
        label_x, label_y = _ability_token_center(label_token)
        row_numbers = [
            token
            for token in tokens
            if re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
            and _ability_token_center(token)[0] > label_x + _ABILITY_COLUMN_X_TOLERANCE
            and abs(_ability_token_center(token)[1] - label_y)
            <= _ABILITY_ROW_Y_TOLERANCE
        ]
        if len(row_numbers) != 6:
            errors.append(
                f"four-lens comparison {label} row has {len(row_numbers)} numeric values; "
                "expected 6"
            )
            continue
        below_gate = [
            _ability_token_confidence(token)
            for token in row_numbers
            if _ability_token_confidence(token) < _ABILITY_OCR_NUMBER_CONFIDENCE
        ]
        if below_gate:
            errors.append(
                f"four-lens comparison {label} numeric confidence "
                f"{min(below_gate):.6f} is below {_ABILITY_OCR_NUMBER_CONFIDENCE:.6f}"
            )
    return errors


def _parse_genius_four_lens_six_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError(
            "Genius four-lens six-embodiment input lacks official source facts"
        )
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(
        r"[0-9a-f]{64}", primary_digest
    ) is None:
        raise PatentParseError("Genius four-lens six-embodiment HTML hash is invalid")
    try:
        source_layout = genius_four_lens_six_source_layout_for_sha256(primary_digest)
    except PatentPdfRecoveryError as exc:
        raise PatentParseError(str(exc)) from exc
    if payload.get("page_count") != source_layout["page_count"]:
        raise PatentParseError("Genius four-lens six-embodiment PDF page count changed")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 13:
        raise PatentParseError(
            "Genius four-lens six-embodiment PDF must retain 13 key pages"
        )
    expected_source_facts = {
        "normalized_text_sha256": source_layout["normalized_text_sha256"],
        "family_id": source_layout["family_id"],
        "application_number": source_layout["application_number"],
        "title_count": 1,
        "owner_count": source_layout["owner_count"],
        "priority_binding_counts": {
            "CN201210328571.9": 2,
            "CN201210437198.0": 2,
        },
        "relationship_binding_counts": source_layout["relationship_binding_counts"],
        "prescription_count": 6,
        "lens_element_count": 4,
        "comparison_binding_count": 1,
        "declared_figure_numbers": list(range(1, 29)),
        "html_table_count": 0,
        "html_system_label_counts": {
            "FNO": 0,
            "F-number": 0,
            "F/#": 0,
            "HFOV": 0,
            "field of view": 0,
        },
    }
    for key, expected in expected_source_facts.items():
        if facts.get(key) != expected:
            raise PatentParseError(
                f"Genius four-lens six-embodiment source fact {key!r} changed"
            )
    figure_counts = facts.get("figure_binding_counts")
    device_counts = facts.get("device_figure_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 12
        or set(figure_counts.values()) != {1}
        or not isinstance(device_counts, dict)
        or len(device_counts) != 2
        or set(device_counts.values()) != {1}
    ):
        raise PatentParseError(
            "Genius four-lens six-embodiment source bindings changed"
        )

    comparison_role = "genius_four_six_comparison"
    comparison_page = _ability_page(payload, comparison_role)
    comparison_errors = [
        *_genius_four_six_page_errors(
            comparison_page,
            source_layout=source_layout,
            role=comparison_role,
            figure_number=26,
        ),
        *_genius_four_six_comparison_census_errors(comparison_page),
    ]
    attempts: list[_PrescriptionParseAttempt] = []
    ordinals = ("first", "second", "third", "fourth", "fifth", "sixth")
    for embodiment_number, ordinal in enumerate(ordinals, start=1):
        optical_role = f"genius_four_six_optical_{embodiment_number}"
        asphere_role = f"genius_four_six_asphere_{embodiment_number}"
        optical_page = _ability_page(payload, optical_role)
        asphere_page = _ability_page(payload, asphere_role)
        optical_figure = 4 + (embodiment_number - 1) * 4
        asphere_figure = optical_figure + 1
        errors = [
            *_genius_four_six_page_errors(
                optical_page,
                source_layout=source_layout,
                role=optical_role,
                figure_number=optical_figure,
            ),
            *_genius_four_six_optical_census_errors(optical_page),
            *_genius_four_six_page_errors(
                asphere_page,
                source_layout=source_layout,
                role=asphere_role,
                figure_number=asphere_figure,
            ),
            *_genius_four_six_asphere_census_errors(asphere_page),
            *comparison_errors,
        ]
        if not errors:
            errors.append(
                "Genius four-lens six-embodiment census passed; numeric cell parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius four-lens {ordinal} embodiment",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


def _parse_genius_four_lens_eleven_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius parser input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None:
        raise PatentParseError("Genius official HTML hash is invalid")
    try:
        source_layout = genius_four_lens_eleven_source_layout_for_sha256(primary_digest)
    except PatentPdfRecoveryError as exc:
        raise PatentParseError(str(exc)) from exc
    expected_page_count = source_layout["page_count"]
    if payload.get("page_count") != expected_page_count:
        raise PatentParseError(
            "Genius eleven-embodiment PDF page count changed: "
            f"actual={payload.get('page_count')} expected={expected_page_count}"
        )
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 23:
        raise PatentParseError("Genius eleven-embodiment PDF must retain 23 key pages")
    drawing_page_offset = source_layout["drawing_page_offset"]
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
        page_number=46 + drawing_page_offset,
        sheet_number=46,
        role="genius_comparison",
    )
    comparison_census_error = _genius_comparison_census_error(comparison_page)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 12):
        optical_figure = 2 if embodiment_number == 1 else 4 * embodiment_number - 1
        asphere_figure = 4 * embodiment_number
        optical_page_number = optical_figure + drawing_page_offset
        asphere_page_number = asphere_figure + drawing_page_offset
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


def _genius_six_ten_dual_metadata_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    patterns = {
        "EFL": r"(?:^|[\s,])EFL\s*=",
        "EFLA": r"(?:^|[\s,])EFLA\s*=",
        "first-focus Fno": r"(?:^|[\s,])Fno\s+at\s+first\s+focusing\s+state\s*=",
        "second-focus Fno": r"(?:^|[\s,])Fno\s+at\s+second\s+focusing\s+state\s*=",
        "first-focus HFOV": r"(?:^|[\s,])HFOV\s+at\s+first\s+focusing\s+state\s*=",
        "second-focus HFOV": r"(?:^|[\s,])HFOV\s+at\s+second\s+focusing\s+state\s*=",
        "TTL": r"(?:^|[\s,])TTL\s*=",
        "ImgH": r"(?:^|[\s,])ImgH\s*=",
    }
    for label, pattern in patterns.items():
        matches = [
            token
            for token in tokens
            if re.search(pattern, _ability_token_text(token), flags=re.IGNORECASE)
        ]
        if len(matches) != 1:
            return f"dual-focus optical metadata {label} has {len(matches)} exact prefixes"
        confidence = _ability_token_confidence(matches[0])
        if confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            return (
                f"dual-focus optical metadata {label} confidence {confidence:.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
    return None


def _genius_six_ten_dual_asphere_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("K", "a4", "a6", "a8", "a10", "a12", "a14", "a16", "a18", "a20"):
        error = _genius_six_exact_label_error(
            tokens,
            label,
            context="dual-focus asphere table",
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


def _genius_seven_page_binding_error(
    page: dict[str, Any],
    *,
    page_number: int,
    sheet_number: int,
    figure_number: int,
    role: str,
    rotation: str | None,
) -> str | None:
    if page.get("page_number") != page_number:
        return f"{role} is not retained on page {page_number}"
    if page.get("rapidocr_scale") != 0.5:
        return f"{role} lacks its source-locked 0.5 OCR scale"
    if page.get("rapidocr_rotation") != rotation:
        return f"{role} OCR rotation changed"
    tokens = list(page.get("rapidocr_tokens") or [])
    figure_pattern = re.compile(
        rf"\bFIG\s*\.\s*{figure_number}\b",
        flags=re.IGNORECASE,
    )
    figure_matches = [
        token
        for token in tokens
        if figure_pattern.search(_ability_token_text(token))
    ]
    if len(figure_matches) != 1:
        return f"{role} has {len(figure_matches)} FIG. {figure_number} OCR tokens"
    figure_confidence = _ability_token_confidence(figure_matches[0])
    if figure_confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
        return (
            f"{role} FIG. {figure_number} confidence {figure_confidence:.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    if rotation is None:
        sheet_matches = [
            token
            for token in tokens
            if f"Sheet {sheet_number} of 25" in _ability_token_text(token)
        ]
        if len(sheet_matches) != 1:
            return f"{role} has {len(sheet_matches)} drawing-sheet header tokens"
        sheet_confidence = _ability_token_confidence(sheet_matches[0])
        if sheet_confidence < _ABILITY_OCR_LABEL_CONFIDENCE:
            return (
                f"{role} drawing-sheet header confidence {sheet_confidence:.6f} is below "
                f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
    return None


def _genius_seven_token_fragment_error(
    tokens: list[dict[str, Any]],
    fragment: str,
    *,
    context: str,
    expected_count: int = 1,
) -> str | None:
    matches = [
        token
        for token in tokens
        if fragment.casefold() in _ability_token_text(token).casefold()
    ]
    if len(matches) != expected_count:
        return (
            f"{context} fragment {fragment!r} has {len(matches)} OCR tokens; "
            f"expected {expected_count}"
        )
    below_gate = [
        _ability_token_confidence(token)
        for token in matches
        if _ability_token_confidence(token) < _ABILITY_OCR_LABEL_CONFIDENCE
    ]
    if below_gate:
        return (
            f"{context} fragment {fragment!r} confidence {min(below_gate):.6f} is below "
            f"{_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
        )
    return None


def _genius_seven_optical_census_error(
    page: dict[str, Any],
    *,
    ordinal: str,
) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("EFL", "HFOV", "TTL", "Fno"):
        error = _genius_six_metadata_label_error(tokens, label)
        if error is not None:
            return error
    for fragment in (
        f"{ordinal} Example",
        "Curvature",
        "Thickness",
        "Refractive",
        "Abbe",
        "Focal Length",
        "First Lens",
        "Second Lens",
        "Third Lens",
        "Fourth Lens",
        "Fifth Lens",
        "Sixth Lens",
        "Seventh Lens",
    ):
        error = _genius_seven_token_fragment_error(
            tokens,
            fragment,
            context="seven-lens optical table",
        )
        if error is not None:
            return error
    return None


def _genius_seven_asphere_census_error(page: dict[str, Any]) -> str | None:
    tokens = list(page.get("rapidocr_tokens") or [])
    for label in ("No", "K", "a2", "a4", "a6", "a8", "a10", "a12", "a14", "a16"):
        matches = [
            token
            for token in tokens
            if _ability_token_text(token).strip(" .:").casefold() == label.casefold()
        ]
        if len(matches) != 2:
            return f"seven-lens asphere label {label!r} has {len(matches)} tokens; expected 2"
        below_gate = [
            _ability_token_confidence(token)
            for token in matches
            if _ability_token_confidence(token) < _ABILITY_OCR_LABEL_CONFIDENCE
        ]
        if below_gate:
            return (
                f"seven-lens asphere label {label!r} confidence {min(below_gate):.6f} "
                f"is below {_ABILITY_OCR_LABEL_CONFIDENCE:.6f}"
            )
    return None


def _parse_genius_seven_lens_seven_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Genius seven-lens input lacks official source facts")
    primary_digest = facts.get("primary_html_sha256")
    if not isinstance(primary_digest, str) or re.fullmatch(
        r"[0-9a-f]{64}", primary_digest
    ) is None:
        raise PatentParseError("Genius seven-lens official HTML hash is invalid")
    try:
        source_layout = genius_seven_lens_seven_source_layout_for_sha256(
            primary_digest
        )
    except PatentPdfRecoveryError as exc:
        raise PatentParseError(str(exc)) from exc
    if payload.get("page_count") != source_layout["page_count"]:
        raise PatentParseError("Genius seven-lens seven-example PDF page count changed")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 16:
        raise PatentParseError(
            "Genius seven-lens seven-example PDF must retain 16 key pages"
        )
    expected_source_facts = {
        "normalized_text_sha256": source_layout["normalized_text_sha256"],
        "family_id": source_layout["family_id"],
        "application_number": source_layout["application_number"],
        "system_values": list(source_layout["system_values"]),
        "genius_applicant_assignee_count": 2,
    }
    for key, expected in expected_source_facts.items():
        if facts.get(key) != expected:
            raise PatentParseError(f"Genius seven-lens source fact {key!r} changed")
    figure_counts = facts.get("figure_binding_counts")
    comparison_counts = facts.get("comparison_binding_counts")
    heading_counts = facts.get("example_heading_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 14
        or set(figure_counts.values()) != {1}
        or not isinstance(comparison_counts, dict)
        or len(comparison_counts) != 2
        or set(comparison_counts.values()) != {1}
        or not isinstance(heading_counts, dict)
        or list(heading_counts.values()) != [1] * 7
    ):
        raise PatentParseError("Genius seven-lens source bindings changed")

    comparison_errors = []
    for comparison, (page_number, figure_number, rotation) in enumerate(
        ((25, 34, None), (26, 35, "clockwise_90")),
        start=1,
    ):
        error = _genius_seven_page_binding_error(
            _ability_page(payload, f"genius_seven_comparison_{comparison}"),
            page_number=page_number,
            sheet_number=page_number - 1,
            figure_number=figure_number,
            role=f"genius_seven_comparison_{comparison}",
            rotation=rotation,
        )
        if error is not None:
            comparison_errors.append(error)

    ordinals = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh")
    attempts: list[_PrescriptionParseAttempt] = []
    for example_number, ordinal in enumerate(ordinals, start=1):
        optical_page_number = 11 + (example_number - 1) * 2
        asphere_page_number = optical_page_number + 1
        optical_role = f"genius_seven_optical_{example_number}"
        asphere_role = f"genius_seven_asphere_{example_number}"
        optical_page = _ability_page(payload, optical_role)
        asphere_page = _ability_page(payload, asphere_role)
        errors = [
            error
            for error in (
                _genius_seven_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_page_number - 1,
                    figure_number=20 + (example_number - 1) * 2,
                    role=optical_role,
                    rotation=None,
                ),
                _genius_seven_optical_census_error(
                    optical_page,
                    ordinal=ordinal,
                ),
                _genius_seven_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_page_number - 1,
                    figure_number=21 + (example_number - 1) * 2,
                    role=asphere_role,
                    rotation="clockwise_90",
                ),
                _genius_seven_asphere_census_error(asphere_page),
                *comparison_errors,
            )
            if error is not None
        ]
        if not errors:
            errors.append(
                "Genius seven-lens seven-example census passed; numeric cell parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=example_number,
                embodiment=f"Genius seven-lens {ordinal} example",
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


def _parse_genius_six_lens_ten_dual_focus_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    if payload.get("page_count") != 64:
        raise PatentParseError(
            "Genius ten-embodiment dual-focus PDF page count is not 64"
        )
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 24:
        raise PatentParseError(
            "Genius ten-embodiment dual-focus PDF must retain 24 key pages"
        )
    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError(
            "Genius ten-embodiment dual-focus input lacks official source facts"
        )
    primary_digest = facts.get("primary_html_sha256")
    if (
        not isinstance(primary_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", primary_digest) is None
    ):
        raise PatentParseError("Genius dual-focus official HTML hash is invalid")
    figure_counts = facts.get("figure_binding_counts")
    if (
        not isinstance(figure_counts, dict)
        or len(figure_counts) != 10
        or set(figure_counts.values()) != {1}
        or facts.get("comparison_binding_count") != 1
        or facts.get("first_focusing_state_count") != 201
        or facts.get("second_focusing_state_count") != 207
        or facts.get("six_lens_element_claim_count") != 2
    ):
        raise PatentParseError("Genius dual-focus official figure/source bindings changed")

    comparison_errors = []
    for comparison in range(1, 5):
        page_number = 43 + comparison
        page = _ability_page(
            payload,
            f"genius_six_ten_dual_comparison_{comparison}",
        )
        error = _genius_six_page_binding_error(
            page,
            page_number=page_number,
            sheet_number=page_number - 1,
            sheet_count=46,
            role=f"genius_six_ten_dual_comparison_{comparison}",
        )
        if error is not None:
            comparison_errors.append(error)

    attempts: list[_PrescriptionParseAttempt] = []
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
        "tenth",
    )
    for embodiment_number, ordinal in enumerate(ordinals, start=1):
        optical_page_number = 24 + (embodiment_number - 1) * 2
        asphere_page_number = optical_page_number + 1
        optical_page = _ability_page(
            payload,
            f"genius_six_ten_dual_optical_{embodiment_number}",
        )
        asphere_page = _ability_page(
            payload,
            f"genius_six_ten_dual_asphere_{embodiment_number}",
        )
        errors = [
            error
            for error in (
                _genius_six_page_binding_error(
                    optical_page,
                    page_number=optical_page_number,
                    sheet_number=optical_page_number - 1,
                    sheet_count=46,
                    role=f"genius_six_ten_dual_optical_{embodiment_number}",
                ),
                _genius_six_ten_dual_metadata_error(optical_page),
                _genius_six_page_binding_error(
                    asphere_page,
                    page_number=asphere_page_number,
                    sheet_number=asphere_page_number - 1,
                    sheet_count=46,
                    role=f"genius_six_ten_dual_asphere_{embodiment_number}",
                ),
                _genius_six_ten_dual_asphere_census_error(asphere_page),
                *comparison_errors,
            )
            if error is not None
        ]
        if not errors:
            errors.append(
                "Genius ten-embodiment dual-focus census passed; numeric parser remains"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Genius six-lens dual-focus {ordinal} embodiment",
                error=PatentParseError(" | ".join(errors)),
            )
        )
    return attempts


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


def _ability_three_five_lens_terminal_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    """Classify three source-locked five-lens prescriptions without angular field."""

    publication_id = str(payload.get("publication_id"))
    source_profile = _ABILITY_THREE_FIVE_LENS_PUBLICATION_SOURCES.get(publication_id)
    if source_profile is None:
        raise PatentParseError(
            "Ability three-five-lens publication is not source-locked"
        )
    if payload.get("page_count") != source_profile["page_count"]:
        raise PatentParseError("Ability three-five-lens PDF page count changed")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 4:
        raise PatentParseError(
            "Ability three-five-lens parser input must retain four key pages"
        )

    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Ability three-five-lens source facts are absent")
    expected_facts = {
        "primary_html_sha256": source_profile["primary_html_sha256"],
        "normalized_text_sha256": source_profile["normalized_text_sha256"],
        "family_id": "74187659",
        "application_number": source_profile["application_number"],
        "prescription_count": 3,
        "lens_element_count": 5,
        "figure_binding_counts": dict.fromkeys(
            (
                "surface_ol1",
                "asphere_ol1",
                "surface_ol2",
                "asphere_ol2",
                "surface_ol3",
                "asphere_ol3",
                "system_meta",
            ),
            2,
        ),
        "angular_field_label_counts": {
            "FOV": 0,
            "HFOV": 0,
            "field of view": 0,
            "viewing angle": 0,
            "angle of view": 0,
            "image height": 0,
        },
        "shape_coordinate_definition_counts": {"h": 1, "H": 1},
    }
    for key, expected in expected_facts.items():
        if facts.get(key) != expected:
            raise PatentParseError(
                f"Ability three-five-lens source fact {key!r} changed"
            )

    common_prescription_labels = frozenset(
        {
            "SURFACE",
            "CURVATURE",
            "THICKNESS",
            "REFRACTIVE",
            "ABBE",
            "S1",
            "S2",
            "S3",
            "S4",
            "ST",
            "S5",
            "S6",
            "S7",
            "S8",
            "S9",
            "S10",
            "S11",
            "S12",
            "K",
            "A2",
            "A4",
            "A6",
            "A8",
            "A10",
            "A12",
            "A14",
            "A16",
        }
    )
    prescription_required_labels = {
        embodiment_number: common_prescription_labels
        | {f"FIG{embodiment_number + 3}A", f"FIG{embodiment_number + 3}B"}
        for embodiment_number in (1, 2, 3)
    }
    angular_field_pattern = re.compile(
        r"\b(?:FOV|HFOV)\b|\bfield\s+of\s+view\b|\bviewing\s+angle\b|"
        r"\bangle\s+of\s+view\b|\bhalf\s*[- ]?field\b|"
        r"\bfull\s*[- ]?field\b|\bfield\s+angle\b|\bimage\s+height\b",
        flags=re.IGNORECASE,
    )
    prescription_pages: dict[int, dict[str, Any]] = {}
    for embodiment_number in (1, 2, 3):
        role = f"ability_three_five_prescription_ol{embodiment_number}"
        page = _ability_page(payload, role)
        expected_page_number = _ABILITY_THREE_FIVE_LENS_ROLE_PAGE_NUMBERS[role]
        if page.get("page_number") != expected_page_number:
            raise PatentParseError(
                f"Ability three-five-lens role {role} is on the wrong page"
            )
        if page.get("official_image_sha256") != source_profile[
            "key_page_image_sha256"
        ][role]:
            raise PatentParseError(
                f"Ability three-five-lens role {role} raster hash changed"
            )
        mirror_text = page.get("mirror_text")
        if not isinstance(mirror_text, str) or (
            not mirror_text.strip()
        ) != (expected_page_number in source_profile["blank_key_pages"]):
            raise PatentParseError(
                f"Ability three-five-lens role {role} mirror-text state changed"
            )
        tokens = list(page["rapidocr_tokens"])
        normalized_labels = {
            re.sub(r"[^A-Z0-9]", "", _ability_token_text(token).upper())
            for token in tokens
            if _ability_token_confidence(token) >= 0.90
        }
        missing_labels = sorted(
            prescription_required_labels[embodiment_number] - normalized_labels
        )
        if missing_labels:
            raise PatentParseError(
                f"Ability three-five-lens role {role} lacks labels: "
                + ",".join(missing_labels)
            )
        coordinate_text = " ".join(_ability_token_text(token) for token in tokens)
        if angular_field_pattern.search(mirror_text) or angular_field_pattern.search(
            coordinate_text
        ):
            raise PatentParseError(
                f"Ability three-five-lens role {role} may publish angular field"
            )
        prescription_pages[embodiment_number] = page

    meta_role = "ability_three_five_system_meta"
    meta_page = _ability_page(payload, meta_role)
    meta_page_number = _ABILITY_THREE_FIVE_LENS_ROLE_PAGE_NUMBERS[meta_role]
    if meta_page.get("page_number") != meta_page_number:
        raise PatentParseError("Ability three-five-lens metadata is on the wrong page")
    if meta_page.get("official_image_sha256") != source_profile[
        "key_page_image_sha256"
    ][meta_role]:
        raise PatentParseError("Ability three-five-lens metadata raster hash changed")
    meta_mirror_text = meta_page.get("mirror_text")
    if not isinstance(meta_mirror_text, str) or (
        not meta_mirror_text.strip()
    ) != (meta_page_number in source_profile["blank_key_pages"]):
        raise PatentParseError(
            "Ability three-five-lens metadata mirror-text state changed"
        )
    meta_tokens = list(meta_page["rapidocr_tokens"])
    meta_labels = {
        re.sub(r"[^A-Z0-9]", "", _ability_token_text(token).upper())
        for token in meta_tokens
        if _ability_token_confidence(token) >= 0.90
    }
    required_meta_labels = {
        "FIG7",
        "OL1",
        "OL2",
        "OL3",
        "EFLMM",
        "FNO",
        "TTLMM",
        "F1MM",
        "F2MM",
        "F3MM",
        "F4MM",
        "F5MM",
        "F345MM",
        "F2F345",
        "TTLEFL",
        "R1MM",
        "R2MM",
        "R3MM",
        "R4MM",
    }
    missing_meta_labels = sorted(required_meta_labels - meta_labels)
    if missing_meta_labels:
        raise PatentParseError(
            "Ability three-five-lens metadata lacks labels: "
            + ",".join(missing_meta_labels)
        )
    meta_coordinate_text = " ".join(
        _ability_token_text(token) for token in meta_tokens
    )
    if angular_field_pattern.search(meta_mirror_text) or angular_field_pattern.search(
        meta_coordinate_text
    ):
        raise PatentParseError(
            "Ability three-five-lens metadata may publish angular field"
        )

    ol2_tokens = list(prescription_pages[2]["rapidocr_tokens"])
    ol2_s1 = _ability_unique_token(
        ol2_tokens,
        "S1",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    ol2_surface_r1 = _ability_unique_token(
        ol2_tokens,
        "-17.90",
        min_confidence=0.99,
    )
    if abs(_ability_token_center(ol2_s1)[1] - _ability_token_center(ol2_surface_r1)[1]) > (
        _ABILITY_ROW_Y_TOLERANCE
    ):
        raise PatentParseError(
            "Ability OL2 FIG. 5A S1/R1 row association changed"
        )
    meta_ol2 = _ability_unique_token(
        meta_tokens,
        "OL2",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    meta_r1 = _ability_unique_token(
        meta_tokens,
        "R1 (mm)",
        min_confidence=_ABILITY_OCR_LABEL_CONFIDENCE,
    )
    meta_ol2_r1 = _ability_unique_token(
        meta_tokens,
        "17.90",
        min_confidence=0.99,
    )
    meta_ol2_r1_x, meta_ol2_r1_y = _ability_token_center(meta_ol2_r1)
    if (
        abs(_ability_token_center(meta_ol2)[0] - meta_ol2_r1_x)
        > _ABILITY_COLUMN_X_TOLERANCE
        or abs(_ability_token_center(meta_r1)[1] - meta_ol2_r1_y)
        > _ABILITY_ROW_Y_TOLERANCE
    ):
        raise PatentParseError(
            "Ability OL2 FIG. 7 R1 column/row association changed"
        )

    return [
        _PrescriptionParseAttempt(
            embodiment_number=embodiment_number,
            embodiment=f"Ability optical lens OL{embodiment_number}",
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code=(
                    "metadata_unpublished.prescription_specific_angular_field_absent"
                    if embodiment_number != 2
                    else "metadata_unpublished.prescription_specific_angular_field_"
                    "absent_and_r1_sign_conflicted"
                ),
                detail=(
                    f"official HTML and all 13 exact-raster PDF pages publish the complete "
                    f"OL{embodiment_number} five-lens prescription, EFL, and Fno, but no "
                    "angular field"
                    + (
                        "; FIG. 5A publishes S1/R1=-17.90 mm while FIG. 7 publishes "
                        "OL2 R1=+17.90 mm"
                        if embodiment_number == 2
                        else ""
                    )
                ),
            ),
        )
        for embodiment_number in (1, 2, 3)
    ]


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


def _ability_five_three_lens_terminal_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    """Classify five complete prescriptions whose source omits F-number."""

    publication_id = str(payload.get("publication_id"))
    source_profile = _ABILITY_FIVE_THREE_LENS_PUBLICATION_SOURCES.get(publication_id)
    if source_profile is None:
        raise PatentParseError("Ability five-three-lens publication is not source-locked")
    if payload.get("page_count") != source_profile["page_count"]:
        raise PatentParseError("Ability five-three-lens PDF page count changed")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 11:
        raise PatentParseError(
            "Ability five-three-lens PDF must retain exactly eleven key pages"
        )

    f_number_pattern = re.compile(
        r"(?:\bFNO\b|\bF\s*[- ]?number\b|\bF\s*/\s*#)",
        flags=re.IGNORECASE,
    )
    for embodiment, (surface_figure, asphere_figure) in enumerate(
        zip((3, 7, 11, 15, 19), (4, 8, 12, 16, 20), strict=True),
        start=1,
    ):
        for kind, figure, minimum_numeric_count in (
            ("surface", surface_figure, 25),
            ("asphere", asphere_figure, 55),
        ):
            role = f"ability_five_three_{kind}_{embodiment}"
            page = _ability_page(payload, role)
            expected_page = _ABILITY_FIVE_THREE_LENS_ROLE_PAGE_NUMBERS[role]
            if page.get("page_number") != expected_page:
                raise PatentParseError(
                    f"Ability five-three-lens role {role} is on the wrong page"
                )
            if page.get("rapidocr_rotation") is not None:
                raise PatentParseError(
                    f"Ability five-three-lens role {role} has an unexpected OCR rotation"
                )
            mirror_text = page.get("mirror_text")
            if not isinstance(mirror_text, str):
                raise PatentParseError(
                    f"Ability five-three-lens role {role} mirror text is invalid"
                )
            sheet_number = expected_page - 1
            if mirror_text and re.search(
                rf"\bSheet\s+{sheet_number}\s+of\s*21\b",
                mirror_text,
                flags=re.IGNORECASE,
            ) is None:
                raise PatentParseError(
                    f"Ability five-three-lens role {role} lacks its sheet header"
                )

            tokens = list(page["rapidocr_tokens"])
            token_text = " ".join(_ability_token_text(token) for token in tokens)
            if f_number_pattern.search(mirror_text) or f_number_pattern.search(token_text):
                raise PatentParseError(
                    f"Ability five-three-lens role {role} may publish an F-number"
                )
            normalized_labels = {
                re.sub(r"[^A-Z0-9]", "", _ability_token_text(token).upper())
                for token in tokens
            }
            numeric_count = sum(
                _ability_token_confidence(token) >= 0.90
                and re.fullmatch(
                    NUMBER_PATTERN,
                    _ability_token_text(token),
                    flags=re.IGNORECASE,
                )
                is not None
                for token in tokens
            )
            if kind == "surface":
                required_labels = {
                    f"FIG{figure}",
                    "RADIUSOF",
                    "CURVATURE",
                    "THICKNESS",
                    "REFRACTIVE",
                    "ABBE",
                    "DISTANCEFN",
                }
                has_effective_focal = "EFFECTIVEFOCAL" in normalized_labels or {
                    "EFFECTIVE",
                    "FOCAL",
                }.issubset(normalized_labels)
            else:
                required_labels = {f"FIG{figure}", "SURFACE", "B", "E", "F", "H"}
                has_effective_focal = True
            missing_labels = sorted(required_labels - normalized_labels)
            if (
                missing_labels
                or not has_effective_focal
                or numeric_count < minimum_numeric_count
            ):
                if not has_effective_focal:
                    missing_labels.append("EFFECTIVE_FOCAL")
                raise PatentParseError(
                    f"Ability five-three-lens role {role} lacks complete table evidence: "
                    f"missing={','.join(missing_labels)} numeric={numeric_count}"
                )

    meta_role = "ability_five_three_meta"
    meta_page = _ability_page(payload, meta_role)
    if meta_page.get("page_number") != _ABILITY_FIVE_THREE_LENS_ROLE_PAGE_NUMBERS[
        meta_role
    ]:
        raise PatentParseError("Ability five-three-lens FIG. 21 is on the wrong page")
    if meta_page.get("rapidocr_rotation") is not None:
        raise PatentParseError("Ability five-three-lens FIG. 21 has an OCR rotation")
    meta_mirror_text = meta_page.get("mirror_text")
    if not isinstance(meta_mirror_text, str):
        raise PatentParseError("Ability five-three-lens FIG. 21 mirror text is invalid")
    if meta_mirror_text and re.search(
        r"\bSheet\s+21\s+of\s*21\b",
        meta_mirror_text,
        flags=re.IGNORECASE,
    ) is None:
        raise PatentParseError("Ability five-three-lens FIG. 21 lacks its sheet header")
    meta_tokens = list(meta_page["rapidocr_tokens"])
    meta_token_text = " ".join(_ability_token_text(token) for token in meta_tokens)
    if f_number_pattern.search(meta_mirror_text) or f_number_pattern.search(meta_token_text):
        raise PatentParseError("Ability five-three-lens FIG. 21 may publish an F-number")
    meta_labels = {
        re.sub(r"[^A-Z0-9]", "", _ability_token_text(token).upper())
        for token in meta_tokens
    }
    required_meta_labels = {
        "FIG21",
        "FIRST",
        "SECOND",
        "THIRD",
        "FOURTH",
        "FIFTH",
        "FOV",
    }
    meta_numeric_count = sum(
        _ability_token_confidence(token) >= 0.90
        and re.fullmatch(
            NUMBER_PATTERN,
            _ability_token_text(token),
            flags=re.IGNORECASE,
        )
        is not None
        for token in meta_tokens
    )
    if required_meta_labels - meta_labels or meta_numeric_count < 55:
        raise PatentParseError(
            "Ability five-three-lens FIG. 21 lacks five-embodiment comparison evidence"
        )

    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("Ability five-three-lens source facts are absent")
    expected_values = {
        ordinal: {
            "entrance_pupil_diameter_mm": epd,
            "focal_length_mm": focal_length,
            "full_field_of_view_deg": fov,
        }
        for ordinal, epd, focal_length, fov in zip(
            _ABILITY_FIVE_THREE_LENS_ORDINALS,
            (0.666, 1.075, 1.178, 1.097, 1.124),
            (1.619, 2.408, 2.393, 2.227, 2.716),
            (84.0, 84.0, 84.0, 87.0, 77.4),
            strict=True,
        )
    }
    expected_facts = {
        "primary_html_sha256": source_profile["primary_html_sha256"],
        "normalized_text_sha256": source_profile["normalized_text_sha256"],
        "family_id": "55525612",
        "application_number": source_profile["application_number"],
        "figure_binding_counts": {
            f"FIG. {figure}": 1
            for figure in (3, 4, 7, 8, 11, 12, 15, 16, 19, 20, 21)
        },
        "embodiment_detail_counts": dict.fromkeys(
            _ABILITY_FIVE_THREE_LENS_ORDINALS,
            1,
        ),
        "embodiment_system_values": expected_values,
        "f_number_label_counts": {"FNO": 0, "F-number": 0, "F/#": 0},
    }
    for key, expected in expected_facts.items():
        if facts.get(key) != expected:
            raise PatentParseError(
                f"Ability five-three-lens source fact {key!r} changed"
            )

    return [
        _PrescriptionParseAttempt(
            embodiment_number=embodiment_number,
            embodiment=(
                f"Ability three-lens {ordinal} embodiment "
                f"(FIGS. {surface_figure}/{asphere_figure})"
            ),
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code="metadata_unpublished.system_f_number_absent",
                detail=(
                    "official HTML and both exact-raster OCR views publish the complete "
                    f"{ordinal} prescription but no system F-number"
                ),
            ),
        )
        for embodiment_number, (ordinal, surface_figure, asphere_figure) in enumerate(
            zip(
                _ABILITY_FIVE_THREE_LENS_ORDINALS,
                (3, 7, 11, 15, 19),
                (4, 8, 12, 16, 20),
                strict=True,
            ),
            start=1,
        )
    ]


def _aac_two_three_lens_terminal_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    """Classify two complete prescriptions whose system field is unpublished."""

    publication_id = str(payload.get("publication_id"))
    source_profile = _AAC_TWO_THREE_LENS_PUBLICATION_SOURCES.get(publication_id)
    if source_profile is None:
        raise PatentParseError("AAC two-three-lens publication is not source-locked")
    if payload.get("page_count") != source_profile["page_count"]:
        raise PatentParseError("AAC two-three-lens PDF page count changed")
    pages = payload.get("pages")
    if not isinstance(pages, list) or len(pages) != 2:
        raise PatentParseError(
            "AAC two-three-lens PDF must retain exactly two drawing sheets"
        )

    forbidden_field_pattern = re.compile(
        r"(?:\bFOV\b|\bHFOV\b|\bfield\s+of\s+view\b|"
        r"\bangle\s+of\s+view\b)",
        flags=re.IGNORECASE,
    )
    for sheet_number, expected_figures in ((1, (1, 2)), (2, (3, 4))):
        role = f"aac_two_three_drawing_sheet_{sheet_number}"
        page = _ability_page(payload, role)
        if page.get("page_number") != sheet_number + 1:
            raise PatentParseError(
                f"AAC two-three-lens drawing sheet {sheet_number} is on the wrong page"
            )
        mirror_text = page.get("mirror_text")
        if not isinstance(mirror_text, str) or re.search(
            rf"\bSheet\s+{sheet_number}\s+of\s*2\b",
            mirror_text,
            flags=re.IGNORECASE,
        ) is None:
            raise PatentParseError(
                f"AAC two-three-lens drawing sheet {sheet_number} header changed"
            )
        token_texts = [
            _ability_token_text(token)
            for token in page["rapidocr_tokens"]
            if _ability_token_confidence(token) >= 0.90
        ]
        normalized_tokens = {
            re.sub(r"[^A-Z0-9]", "", token.upper()) for token in token_texts
        }
        expected_labels = {f"FIG{figure}" for figure in expected_figures}
        if not expected_labels.issubset(normalized_tokens):
            raise PatentParseError(
                f"AAC two-three-lens drawing sheet {sheet_number} figure labels changed"
            )
        coordinate_text = " ".join(token_texts)
        if forbidden_field_pattern.search(mirror_text) or forbidden_field_pattern.search(
            coordinate_text
        ):
            raise PatentParseError(
                f"AAC two-three-lens drawing sheet {sheet_number} may publish system field"
            )

    facts = payload.get("source_facts")
    if not isinstance(facts, dict):
        raise PatentParseError("AAC two-three-lens source facts are absent")
    expected_facts = {
        "primary_html_sha256": source_profile["primary_html_sha256"],
        "normalized_text_sha256": source_profile["normalized_text_sha256"],
        "family_id": "53345880",
        "application_number": source_profile["application_number"],
        "figure_binding_counts": {
            "FIG. 1": 1,
            "FIG. 2": 1,
            "FIG. 3": 1,
            "FIG. 4": 1,
        },
        "table_numbers": [1, 2, 3, 4, 5],
        "table_block_sha256": source_profile["table_block_sha256"],
        "embodiment_table_bindings": {
            "1": {"surface_table": 1, "asphere_table": 2},
            "2": {"surface_table": 3, "asphere_table": 4},
        },
        "embodiment_system_values": {
            "1": {
                "focal_length_mm": 3.5246,
                "f_number": 2.8,
                "published_dof_deg": 33.41,
            },
            "2": {
                "focal_length_mm": 2.3412,
                "f_number": 2.6,
                "published_dof_deg": 37.72,
            },
        },
        "dof_label_count": 2,
        "dof_expansion_count": 1,
        "system_field_label_counts": {
            "FOV": 0,
            "HFOV": 0,
            "field of view": 0,
            "angle of view": 0,
        },
    }
    for key, expected in expected_facts.items():
        if facts.get(key) != expected:
            raise PatentParseError(f"AAC two-three-lens source fact {key!r} changed")

    return [
        _PrescriptionParseAttempt(
            embodiment_number=embodiment_number,
            embodiment=f"AAC three-lens embodiment {embodiment_number}",
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code="metadata_unpublished.system_field_of_view_absent",
                detail=(
                    "official HTML publishes the complete surface/asphere prescription, "
                    "focal length, F-number, and a value explicitly labeled DOF, while "
                    "the full text and both exact-raster drawing sheets publish no FOV, "
                    "HFOV, field-of-view, or angle-of-view field for embodiment "
                    f"{embodiment_number}"
                ),
            ),
        )
        for embodiment_number in (1, 2)
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


def _circle_optics_seven_lens_review_attempt(
    payload: dict[str, Any],
) -> _PrescriptionParseAttempt:
    """Retain the published prescription without accepting unreliable numeric OCR."""

    embodiment = "Circle Optics seven-lens FIG. 8C prescription"
    try:
        if payload.get("page_count") != 66:
            raise PatentParseError("Circle Optics seven-lens PDF page count is not 66")
        publication_id = payload.get("publication_id")
        source_profile = _CIRCLE_OPTICS_SEVEN_LENS_PUBLICATION_SOURCES.get(
            str(publication_id)
        )
        if source_profile is None:
            raise PatentParseError("Circle Optics publication is not source-locked")
        facts = payload.get("source_facts")
        if not isinstance(facts, dict):
            raise PatentParseError("Circle Optics source facts are absent")
        expected_facts = {
            "primary_html_sha256": source_profile["primary_html_sha256"],
            "family_id": "74060373",
            "application_number": source_profile["application_number"],
            "lens_element_count": 7,
            "aspheric_lens_element_count": 3,
            "f_number": 2.0,
            "nominal_focal_length_mm": 2.57,
            "aperture_stop_diameter_mm": 1.42,
            "track_length_mm": 50.0,
            "image_width_mm": 3.9,
            "design_wavelengths_nm": [450, 587, 656],
        }
        for key, expected in expected_facts.items():
            if facts.get(key) != expected:
                raise PatentParseError(f"Circle Optics source fact {key!r} changed")
        required_counts = facts.get("required_text_counts")
        if required_counts != dict.fromkeys(
            _CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT,
            1,
        ):
            raise PatentParseError("Circle Optics required source-text bindings changed")

        pages: list[dict[str, Any]] = []
        figure_markers = {
            "circle_optics_surface_table": "FIG8C-1",
            "circle_optics_asphere_table": "FIG8C-2",
        }
        for role, page_number in source_profile["role_page_numbers"].items():
            page = _ability_page(payload, role)
            if page.get("page_number") != page_number:
                raise PatentParseError(f"Circle Optics role {role} is on the wrong page")
            if page.get("rapidocr_rotation") != "clockwise_90":
                raise PatentParseError(f"Circle Optics role {role} lacks its OCR rotation")
            if page.get("mirror_text") != "":
                raise PatentParseError(f"Circle Optics role {role} unexpectedly uses mirror text")
            tokens = list(page["rapidocr_tokens"])
            normalized_labels = [
                (
                    re.sub(r"[^A-Z0-9-]", "", _ability_token_text(token).upper()),
                    _ability_token_confidence(token),
                )
                for token in tokens
            ]
            figure_matches = [
                confidence
                for label, confidence in normalized_labels
                if label == figure_markers[role] and confidence >= _ABILITY_OCR_LABEL_CONFIDENCE
            ]
            prescription_matches = [
                confidence
                for label, confidence in normalized_labels
                if label == "LENSPRESCRIPTION"
                and confidence >= _ABILITY_OCR_LABEL_CONFIDENCE
            ]
            expected_prescription_labels = (
                1 if role == "circle_optics_surface_table" else 0
            )
            if (
                len(figure_matches) != 1
                or len(prescription_matches) != expected_prescription_labels
            ):
                raise PatentParseError(
                    f"Circle Optics role {role} lacks unique high-confidence table labels"
                )
            pages.append(page)

        numeric_tokens = []
        for page in pages:
            for token in page["rapidocr_tokens"]:
                x, y = _ability_token_center(token)
                if (
                    430.0 <= x <= 2900.0
                    and 700.0 <= y <= 2200.0
                    and _ability_token_confidence(token) >= _ABILITY_OCR_NUMBER_CONFIDENCE
                    and re.fullmatch(NUMBER_PATTERN, _ability_token_text(token), re.IGNORECASE)
                ):
                    numeric_tokens.append(token)
        if len(numeric_tokens) >= 20:
            raise PatentParseError(
                "Circle Optics OCR now exposes enough high-confidence numeric cells; "
                "a reviewed complete seven-lens parser is required"
            )
        error = PatentParseError(
            "Circle Optics publishes a seven-lens prescription in FIGS. 8C-1 and 8C-2, "
            f"but only {len(numeric_tokens)} table-region numeric OCR tokens meet the "
            f"{_ABILITY_OCR_NUMBER_CONFIDENCE:.2f} confidence gate; retained for parser review"
        )
    except Exception as exc:  # noqa: BLE001 - retain the source-specific embodiment
        error = exc
    return _PrescriptionParseAttempt(
        embodiment_number=1,
        embodiment=embodiment,
        error=error,
    )


def _kodak_low_stress_terminal_attempts(
    payload: dict[str, Any],
) -> list[_PrescriptionParseAttempt]:
    """Classify both spherical prescriptions only when their metadata gap is proven."""

    embodiments = (
        "Kodak third exemplary projection lens 270 (FIG. 14A)",
        "Kodak third exemplary relay lens 250 (FIG. 14B)",
    )
    try:
        publication_id = str(payload.get("publication_id"))
        source_profile = _KODAK_LOW_STRESS_PUBLICATION_SOURCES.get(publication_id)
        if source_profile is None:
            raise PatentParseError("Kodak low-stress publication is not source-locked")
        if payload.get("page_count") != source_profile["page_count"]:
            raise PatentParseError("Kodak low-stress PDF page count changed")
        pages = payload.get("pages")
        if not isinstance(pages, list) or len(pages) != 2:
            raise PatentParseError("Kodak low-stress parser input must retain two pages")

        facts = payload.get("source_facts")
        if not isinstance(facts, dict):
            raise PatentParseError("Kodak low-stress source facts are absent")
        expected_facts = {
            "primary_html_sha256": source_profile["primary_html_sha256"],
            "normalized_text_sha256": source_profile["normalized_text_sha256"],
            "family_id": "44121309",
            "application_number": source_profile["application_number"],
            "required_text_counts": dict.fromkeys(
                _KODAK_LOW_STRESS_REQUIRED_TEXT,
                1,
            ),
            "f_number_context_counts": dict.fromkeys(
                _KODAK_LOW_STRESS_F_NUMBER_CONTEXTS,
                1,
            ),
            "numeric_system_value_assignment_counts": {
                "F": 0,
                "FNO": 0,
                "FOV": 0,
                "HFOV": 0,
                "EFL": 0,
            },
            "effective_focal_length_count": 0,
            "focal_length_count": 3,
            "field_of_view_count": 1,
            "prescription_count": 2,
        }
        for key, expected in expected_facts.items():
            if facts.get(key) != expected:
                raise PatentParseError(f"Kodak low-stress source fact {key!r} changed")

        required_labels = {
            "kodak_projection_prescription": (
                "FIG14A",
                "SURFACE",
                "RADIUS",
                "THICKNESS",
                "APERTURE",
                "GLASS",
                "OBJECTSCREEN",
                "STOP",
                "IMAGEINTIMG",
            ),
            "kodak_relay_prescription": (
                "FIG14B",
                "SURFACE",
                "RADIUS",
                "THICKNESS",
                "APERTURE",
                "GLASS",
                "OBJECTDLP",
                "APERTURESTOP",
                "INTIMAGE",
            ),
        }
        forbidden_system_labels = frozenset({"EFL", "FNO", "FOV", "HFOV", "F"})
        for role, page_number in source_profile["role_page_numbers"].items():
            page = _ability_page(payload, role)
            if page.get("page_number") != page_number:
                raise PatentParseError(f"Kodak low-stress role {role} is on the wrong page")
            if page.get("rapidocr_rotation") != "counterclockwise_90":
                raise PatentParseError(f"Kodak low-stress role {role} lacks its OCR rotation")
            if not isinstance(page.get("mirror_text"), str):
                raise PatentParseError(f"Kodak low-stress role {role} mirror text is invalid")
            normalized_labels = [
                (
                    re.sub(r"[^A-Z0-9]", "", _ability_token_text(token).upper()),
                    _ability_token_confidence(token),
                )
                for token in page["rapidocr_tokens"]
            ]
            for label in required_labels[role]:
                matches = [
                    confidence
                    for candidate, confidence in normalized_labels
                    if candidate == label
                    and confidence >= _ABILITY_OCR_LABEL_CONFIDENCE
                ]
                if len(matches) != 1:
                    raise PatentParseError(
                        f"Kodak low-stress role {role} label {label!r} occurs "
                        f"{len(matches)} times above confidence gate"
                    )
            exposed_system_labels = sorted(
                {
                    candidate
                    for candidate, confidence in normalized_labels
                    if candidate in forbidden_system_labels
                    and confidence >= _ABILITY_OCR_LABEL_CONFIDENCE
                }
            )
            if exposed_system_labels:
                raise PatentParseError(
                    f"Kodak low-stress role {role} OCR may publish system metadata: "
                    + ",".join(exposed_system_labels)
                )
    except Exception as exc:  # noqa: BLE001 - retain both source embodiments
        return [
            _PrescriptionParseAttempt(
                embodiment_number=number,
                embodiment=embodiment,
                error=exc,
            )
            for number, embodiment in enumerate(embodiments, start=1)
        ]

    return [
        _PrescriptionParseAttempt(
            embodiment_number=number,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code=(
                    "metadata_unpublished.prescription_specific_efl_and_field_absent"
                ),
                detail=(
                    f"official HTML and exact-raster OCR publish the {figure} spherical "
                    "prescription, but no prescription-specific effective focal length "
                    "or field value"
                ),
            ),
        )
        for number, (embodiment, figure) in enumerate(
            zip(embodiments, ("FIG. 14A", "FIG. 14B"), strict=True),
            start=1,
        )
    ]


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
    if profile == _ABILITY_THREE_FIVE_LENS_PROFILE:
        return _ability_three_five_lens_terminal_attempts(payload)
    if profile == _ABILITY_TWO_FIVE_LENS_PROFILE:
        return _parse_ability_two_five_lens_attempts(payload)
    if profile == _ABILITY_TWO_NINE_LENS_PROFILE:
        return _ability_two_nine_lens_terminal_attempts(payload)
    if profile == _ABILITY_FOUR_EIGHT_LENS_PROFILE:
        return _ability_four_eight_lens_terminal_attempts(payload)
    if profile == _ABILITY_FIVE_THREE_LENS_PROFILE:
        return _ability_five_three_lens_terminal_attempts(payload)
    if profile == _AAC_TWO_THREE_LENS_PROFILE:
        return _aac_two_three_lens_terminal_attempts(payload)
    if profile == _LARGAN_THREE_FIVE_LENS_PROFILE:
        return _parse_largan_three_five_lens_attempts(payload)
    if profile == _ABILITY_ZOOM_TWO_STATE_PROFILE:
        return _parse_ability_zoom_two_state_attempts(payload)
    if profile == _CIRCLE_OPTICS_SEVEN_LENS_PROFILE:
        return [_circle_optics_seven_lens_review_attempt(payload)]
    if profile == _KODAK_LOW_STRESS_TWO_LENS_PROFILE:
        return _kodak_low_stress_terminal_attempts(payload)
    if profile == _GENIUS_FOUR_LENS_SIX_PROFILE:
        return _parse_genius_four_lens_six_attempts(payload)
    if profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        return _parse_genius_four_lens_eleven_attempts(payload)
    if profile == _GENIUS_NINE_LENS_ELEVEN_PROFILE:
        return _parse_genius_nine_lens_eleven_attempts(payload)
    if profile == _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE:
        return _parse_genius_eight_lens_fourteen_attempts(payload)
    if profile == _GENIUS_SEVEN_LENS_SEVEN_PROFILE:
        return _parse_genius_seven_lens_seven_attempts(payload)
    if profile == _GENIUS_FOUR_LENS_NINE_PROFILE:
        return _parse_genius_four_lens_nine_attempts(payload)
    if profile == _GENIUS_SIX_LENS_FIVE_PROFILE:
        return _parse_genius_six_lens_five_attempts(payload)
    if profile == _GENIUS_SIX_LENS_NINE_PROFILE:
        return _parse_genius_six_lens_nine_attempts(payload)
    if profile == _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE:
        return _parse_genius_six_lens_ten_dual_focus_attempts(payload)
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


def _parse_large_aperture_scanning_tele_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Parse the exact Family 85477866 four-prescription disclosure.

    The source profile pins both the retained official HTML bytes and normalized
    text.  TABLE 14 publishes a diagonal native FOV beside each system and binds
    it to the per-prescription HFOV at approximately twice the angle (maximum
    published difference 0.4 degrees).  That cross-table evidence is required
    before the published HFOV value is used as the pipeline half field; no field
    value is derived from EFL or sensor diagonal.
    """

    profile = _LARGE_APERTURE_SCANNING_TELE_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=f"Large-aperture scanning tele example {example}",
                error=exc,
            )
            for index, example in enumerate(
                _LARGE_APERTURE_SCANNING_TELE_EXAMPLES,
                start=1,
            )
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"large-aperture scanning tele official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                "large-aperture scanning tele official normalized text hash changed "
                f"for {patent_id}"
            )
        if _LARGE_APERTURE_SCANNING_TELE_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("large-aperture scanning tele title binding changed")
        if len(re.findall(r"Family\s+ID:\s*85477866", text, flags=re.IGNORECASE)) != 1:
            raise PatentParseError("large-aperture scanning tele Family ID binding changed")
        if len(
            re.findall(
                r"Even\s+Asphere\s+\(ASP\)\s+surface\s+sag\s+formula",
                text,
                flags=re.IGNORECASE,
            )
        ) != 1 or len(
            re.findall(
                r"A\.sub\.n\s+are\s+the\s+polynomial\s+coefficients\s+shown\s+"
                r"in\s+lens\s+data\s+tables",
                text,
                flags=re.IGNORECASE,
            )
        ) != 1 or len(
            re.findall(
                r"c\s+is\s+the\s+paraxial\s+curvature\s+of\s+the\s+surface",
                text,
                flags=re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("large-aperture scanning tele ASP definition changed")
        if len(
            re.findall(
                r"The\s+reference\s+wavelength\s+is\s+555\.0\s+nm",
                text,
                flags=re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "large-aperture scanning tele reference wavelength binding changed"
            )

        blocks = _large_aperture_scanning_tele_source_blocks(text)
        if set(blocks) != set(range(1, 15)):
            raise PatentParseError(
                "large-aperture scanning tele family must contain source anchors 1-14"
            )
        table_bindings = _parse_large_aperture_scanning_tele_field_bindings(blocks[14])
        if table_bindings != {
            key: tuple(values)
            for key, values in _LARGE_APERTURE_SCANNING_TELE_FIELD_BINDINGS.items()
            if key != "HFOV"
        }:
            raise PatentParseError(
                "large-aperture scanning tele TABLE 14 field bindings changed"
            )

        prescriptions: list[PatentPrescription] = []
        for index, example in enumerate(
            _LARGE_APERTURE_SCANNING_TELE_EXAMPLES,
            start=1,
        ):
            pair = (index * 2 + 2, index * 2 + 3)
            surface_candidates = [
                table_number
                for table_number in pair
                if (
                    header := _LARGE_APERTURE_SCANNING_TELE_SURFACE_HEADER_PATTERN.search(
                        blocks[table_number]
                    )
                )
                is not None
                and int(header.group("example")) == example
            ]
            if len(surface_candidates) != 1:
                raise PatentParseError(
                    f"large-aperture scanning tele example {example} surface table binding changed"
                )
            surface_table = surface_candidates[0]
            coefficient_table = next(
                table_number for table_number in pair if table_number != surface_table
            )
            if _LARGE_APERTURE_SCANNING_TELE_COEFFICIENT_HEADER_PATTERN.search(
                blocks[coefficient_table]
            ) is None:
                raise PatentParseError(
                    f"large-aperture scanning tele example {example} coefficient table missing"
                )
            header = _LARGE_APERTURE_SCANNING_TELE_SURFACE_HEADER_PATTERN.search(
                blocks[surface_table]
            )
            if header is None:  # pragma: no cover - guarded by surface_candidates
                raise PatentParseError(
                    f"large-aperture scanning tele example {example} header missing"
                )
            focal_length = _parse_number(header.group("f"))
            f_number = _parse_number(header.group("fno"))
            half_field = _parse_number(header.group("hfov"))
            expected_column = index - 1
            if (
                focal_length != table_bindings["EFL"][expected_column]
                or f_number != table_bindings["f number"][expected_column]
                or half_field
                != _LARGE_APERTURE_SCANNING_TELE_FIELD_BINDINGS["HFOV"][
                    expected_column
                ]
            ):
                raise PatentParseError(
                    f"large-aperture scanning tele example {example} header/TABLE 14 mismatch"
                )
            if (
                abs(
                    table_bindings["n-FOV.sub.T"][expected_column]
                    - 2.0 * half_field
                )
                > 0.5
            ):
                raise PatentParseError(
                    "large-aperture scanning tele HFOV/native-FOV cross-table "
                    f"binding changed for example {example}"
                )
            surfaces, trailing_text = _parse_large_aperture_scanning_tele_surfaces(
                blocks[surface_table],
                header=header,
                example=example,
            )
            coefficients = _parse_large_aperture_scanning_tele_coefficients(
                blocks[coefficient_table] + " " + trailing_text,
                example=example,
            )
            for surface in surfaces:
                if surface.index in coefficients:
                    surface.surface_type = "ASP"
                    surface.asphere_coefficients.update(coefficients[surface.index])
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=f"Large-aperture scanning tele example {example}",
                focal_length_mm=focal_length,
                f_number=f_number,
                hfov_deg=half_field,
                surfaces=surfaces,
                reference_wavelength_um=0.555,
            )
            _validate_prescription_materials(prescription)
            prescriptions.append(prescription)
    except Exception as exc:  # noqa: BLE001 - retain all four disclosed examples
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=prescription.embodiment,
            prescription=prescription,
        )
        for index, prescription in enumerate(prescriptions, start=1)
    ]


def _parse_folded_adaptive_zoom_terminal_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify Family 81853013 configurations with two source-proven gaps."""

    profile = _FOLDED_ADAPTIVE_ZOOM_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=f"Folded adaptive zoom configuration {index}",
                error=exc,
            )
            for index in range(1, 4)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"folded adaptive zoom official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"folded adaptive zoom normalized text hash changed for {patent_id}"
            )
        if _FOLDED_ADAPTIVE_ZOOM_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("folded adaptive zoom title binding changed")
        if len(re.findall(r"Family\s+ID:\s*81853013", text, flags=re.IGNORECASE)) != 1:
            raise PatentParseError("folded adaptive zoom Family ID binding changed")
        if len(
            re.findall(
                r"The\s+reference\s+wavelength\s+is\s+555\.0\s+nm",
                text,
                flags=re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("folded adaptive zoom reference wavelength changed")

        blocks = _folded_adaptive_zoom_source_blocks(text)
        if set(blocks) != set(range(1, 6)):
            raise PatentParseError("folded adaptive zoom must contain source tables 1-5")
        if len(
            re.findall(
                r"S\.sub\.(?:[2-9]|1[0-7])\s+QTYP\b",
                blocks[1],
                flags=re.IGNORECASE,
            )
        ) != 16:
            raise PatentParseError("folded adaptive zoom QTYP surface binding changed")

        qcon_rows = _folded_adaptive_zoom_qcon_rows(blocks[2])
        if [index for index, _values in qcon_rows] != list(range(2, 18)):
            raise PatentParseError("folded adaptive zoom Q-conic row sequence changed")
        if any(values[-1] == 0.0 for _index, values in qcon_rows):
            raise PatentParseError("folded adaptive zoom published A6 evidence changed")

        if raw_text.count('<maths id="MATH-US-00001') != profile["qcon_formula_count"]:
            raise PatentParseError("folded adaptive zoom Q-conic formula count changed")
        if f'<maths id="{profile["qcon_last_definition_id"]}"' not in raw_text:
            raise PatentParseError("folded adaptive zoom final Q-conic definition changed")
        if '<maths id="MATH-US-00001-11"' in raw_text:
            raise PatentParseError("folded adaptive zoom now publishes a Q6 definition")

        table4_efls, moving_thicknesses = _folded_adaptive_zoom_configuration_table(
            blocks[4]
        )
        if table4_efls != _FOLDED_ADAPTIVE_ZOOM_EFLS:
            raise PatentParseError("folded adaptive zoom TABLE 4 EFL binding changed")
        if moving_thicknesses != _FOLDED_ADAPTIVE_ZOOM_MOVING_THICKNESSES:
            raise PatentParseError("folded adaptive zoom moving-thickness binding changed")
        table5_efls, f_numbers = _folded_adaptive_zoom_f_number_table(blocks[5])
        if table5_efls != _FOLDED_ADAPTIVE_ZOOM_EFLS:
            raise PatentParseError("folded adaptive zoom TABLE 5 EFL binding changed")
        if f_numbers != _FOLDED_ADAPTIVE_ZOOM_F_NUMBERS:
            raise PatentParseError("folded adaptive zoom TABLE 5 f-number binding changed")

        if re.search(
            rf"\bHFOV\s*(?:=|\[\s*deg\s*\])\s*{NUMBER_PATTERN}",
            text,
            flags=re.IGNORECASE,
        ) is not None:
            raise PatentParseError("folded adaptive zoom now publishes numeric HFOV")
        if len(re.findall(r"\bHFOV\b", text, flags=re.IGNORECASE)) != 2:
            raise PatentParseError("folded adaptive zoom HFOV definition count changed")
    except Exception as exc:  # noqa: BLE001 - retain all three configurations
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=f"Folded adaptive zoom configuration {index}",
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code=(
                    "metadata_unpublished.configuration_hfov_and_qcon_q6_definition_absent"
                ),
                detail=(
                    f"configuration {index} publishes EFL/f-number and moving thicknesses, "
                    "but no numeric HFOV; TABLE 2 has non-zero A6 while the official "
                    "Q-conic formula does not define Q6"
                ),
            ),
        )
        for index in range(1, 4)
    ]


def _folded_adaptive_zoom_source_blocks(text: str) -> dict[int, str]:
    matches = list(_LARGE_APERTURE_SCANNING_TELE_SOURCE_ANCHOR_PATTERN.finditer(text))
    blocks: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group("number"))
        if number in blocks:
            raise PatentParseError(f"duplicate folded adaptive zoom table: {number}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[number] = text[match.start() : end]
    return blocks


def _folded_adaptive_zoom_qcon_rows(
    table_text: str,
) -> list[tuple[int, tuple[float, ...]]]:
    header = re.search(
        r"\bConic\s+Surface\s+\(k\)\s+NR\s+"
        r"A\.sub\.0\s+A\.sub\.1\s+A\.sub\.2\s+A\.sub\.3\s+"
        r"A\.sub\.4\s+A\.sub\.5\s+A\.sub\.6\s+",
        table_text,
        flags=re.IGNORECASE,
    )
    if header is None:
        raise PatentParseError("folded adaptive zoom Q-conic header changed")
    row_pattern = re.compile(
        r"S\.sub\.(?P<surface>\d+)\s+"
        + r"\s+".join(rf"(?P<v{index}>{NUMBER_PATTERN})" for index in range(9)),
        flags=re.IGNORECASE,
    )
    return [
        (
            int(match.group("surface")),
            tuple(_parse_number(match.group(f"v{index}")) for index in range(9)),
        )
        for match in row_pattern.finditer(table_text, header.end())
    ]


def _folded_adaptive_zoom_configuration_table(
    table_text: str,
) -> tuple[tuple[float, ...], dict[int, tuple[float, ...]]]:
    efls = _folded_adaptive_zoom_efl_header(table_text)
    rows: dict[int, tuple[float, ...]] = {}
    for surface in (7, 13, 17):
        match = re.search(
            rf"S\.sub\.{surface}\s+"
            + r"\s+".join(
                rf"(?P<v{index}>{NUMBER_PATTERN})" for index in range(3)
            ),
            table_text,
            flags=re.IGNORECASE,
        )
        if match is None:
            raise PatentParseError(
                f"folded adaptive zoom TABLE 4 surface {surface} row missing"
            )
        rows[surface] = tuple(
            _parse_number(match.group(f"v{index}")) for index in range(3)
        )
    return efls, rows


def _folded_adaptive_zoom_f_number_table(
    table_text: str,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    efls = _folded_adaptive_zoom_efl_header(table_text)
    match = re.search(
        r"f/#\s+"
        + r"\s+".join(rf"(?P<v{index}>{NUMBER_PATTERN})" for index in range(3)),
        table_text,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise PatentParseError("folded adaptive zoom TABLE 5 f-number row missing")
    return efls, tuple(
        _parse_number(match.group(f"v{index}")) for index in range(3)
    )


def _folded_adaptive_zoom_efl_header(table_text: str) -> tuple[float, ...]:
    match = re.search(
        r"Configuration\s+1\s+Configuration\s+2\s+Configuration\s*3\s+"
        + r"\s+".join(
            rf"EFL\s*=\s*(?P<v{index}>{NUMBER_PATTERN})\s*mm"
            for index in range(3)
        ),
        table_text,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise PatentParseError("folded adaptive zoom configuration header missing")
    return tuple(_parse_number(match.group(f"v{index}")) for index in range(3))


def _large_aperture_scanning_tele_source_blocks(text: str) -> dict[int, str]:
    matches = list(_LARGE_APERTURE_SCANNING_TELE_SOURCE_ANCHOR_PATTERN.finditer(text))
    blocks: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group("number"))
        if number in blocks:
            raise PatentParseError(
                f"duplicate large-aperture scanning tele source anchor: {number}"
            )
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[number] = text[match.start() : end]
    return blocks


def _parse_large_aperture_scanning_tele_field_bindings(
    table_text: str,
) -> dict[str, tuple[float, ...]]:
    if re.search(
        r"\bn-FOV\.sub\.T\s+.*?Diagonal\s+n-FOV\.sub\.T\b",
        table_text,
        flags=re.IGNORECASE,
    ) is None:
        raise PatentParseError(
            "large-aperture scanning tele diagonal native-FOV label missing"
        )

    def four_values(label: str, *, degrees: bool = False) -> tuple[float, ...]:
        suffix = r"\s*°?" if degrees else ""
        value = rf"(?P<v{{index}}>{NUMBER_PATTERN}){suffix}"
        pattern = re.escape(label) + r"\s+" + r"\s+".join(
            value.format(index=index) for index in range(4)
        )
        match = re.search(pattern, table_text, flags=re.IGNORECASE)
        if match is None:
            raise PatentParseError(
                f"large-aperture scanning tele TABLE 14 row {label} missing"
            )
        return tuple(_parse_number(match.group(f"v{index}")) for index in range(4))

    return {
        "EFL": four_values("EFL"),
        "f number": four_values("f number"),
        "n-FOV.sub.T": four_values("n-FOV.sub.T", degrees=True),
        "SD": four_values("SD"),
    }


def _parse_large_aperture_scanning_tele_surfaces(
    table_text: str,
    *,
    header: re.Match[str],
    example: int,
) -> tuple[list[PatentSurface], str]:
    tokens = table_text[header.end() :].split()
    pos = 0

    def take(expected: str | None = None) -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise PatentParseError(
                f"large-aperture scanning tele example {example} surface table is incomplete"
            )
        token = tokens[pos]
        pos += 1
        if expected is not None and token.lower() != expected.lower():
            raise PatentParseError(
                f"large-aperture scanning tele example {example} expected {expected}, "
                f"found {token}"
            )
        return token

    surfaces: list[PatentSurface] = []
    take("1")
    take("A.S.")
    take("Plano")
    stop_radius = _distance_value(take(), field_name=f"example {example} stop radius")
    stop_thickness = _distance_value(
        take(), field_name=f"example {example} stop thickness"
    )
    _parse_number(take())
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

    for lens_number in range(1, 7):
        first_index = lens_number * 2
        take(str(first_index))
        take("Lens")
        take(str(lens_number))
        take("ASP")
        first_radius = _distance_value(
            take(), field_name=f"example {example} surface {first_index} radius"
        )
        first_thickness = _distance_value(
            take(), field_name=f"example {example} surface {first_index} thickness"
        )
        _parse_number(take())
        material = take()
        expected_material = "Glass" if lens_number == 1 else "Plastic"
        if material.lower() != expected_material.lower():
            raise PatentParseError(
                f"large-aperture scanning tele example {example} lens {lens_number} "
                f"material changed: {material}"
            )
        nd = _parse_number(take())
        vd = _parse_number(take())
        _parse_number(take())
        surfaces.append(
            PatentSurface(
                index=first_index,
                label=f"Lens {lens_number}",
                radius_mm=first_radius,
                thickness_mm=first_thickness,
                material=expected_material,
                nd=nd,
                vd=vd,
                surface_type="ASP",
            )
        )

        second_index = first_index + 1
        take(str(second_index))
        second_radius = _distance_value(
            take(), field_name=f"example {example} surface {second_index} radius"
        )
        second_thickness = _distance_value(
            take(), field_name=f"example {example} surface {second_index} thickness"
        )
        _parse_number(take())
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

    take("14")
    filter_first_token = take()
    deferred_filter_token = False
    if filter_first_token.lower() == "filter":
        filter_label = "Filter"
    elif filter_first_token.lower() == "ir":
        filter_label = "IR Filter"
        if pos < len(tokens) and tokens[pos].lower() == "filter":
            pos += 1
        else:
            deferred_filter_token = True
    else:
        raise PatentParseError(
            f"large-aperture scanning tele example {example} filter label changed"
        )
    take("Plano")
    filter_radius = _distance_value(
        take(), field_name=f"example {example} filter radius"
    )
    filter_thickness = _distance_value(
        take(), field_name=f"example {example} filter thickness"
    )
    filter_aperture = take()
    if not _is_empty_value(filter_aperture):
        _parse_number(filter_aperture)
    take("Glass")
    filter_nd = _parse_number(take())
    filter_vd = _parse_number(take())
    if deferred_filter_token:
        take("Filter")
    surfaces.append(
        PatentSurface(
            index=14,
            label=filter_label,
            radius_mm=filter_radius,
            thickness_mm=filter_thickness,
            material="Glass",
            nd=filter_nd,
            vd=filter_vd,
            surface_type=None,
        )
    )

    take("15")
    filter_back_radius = _distance_value(
        take(), field_name=f"example {example} filter back radius"
    )
    filter_back_thickness = _distance_value(
        take(), field_name=f"example {example} filter back thickness"
    )
    take("--")
    surfaces.append(
        PatentSurface(
            index=15,
            label=filter_label,
            radius_mm=filter_back_radius,
            thickness_mm=filter_back_thickness,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )

    take("16")
    take("Image")
    take("Plano")
    image_radius = _distance_value(
        take(), field_name=f"example {example} image radius"
    )
    image_thickness = _distance_value(
        take(), field_name=f"example {example} image thickness"
    )
    take("--")
    surfaces.append(
        PatentSurface(
            index=16,
            label="Image",
            radius_mm=image_radius,
            thickness_mm=image_thickness,
            material=None,
            nd=None,
            vd=None,
            surface_type=None,
        )
    )
    return surfaces, " ".join(tokens[pos:])


def _parse_large_aperture_scanning_tele_coefficients(
    table_text: str,
    *,
    example: int,
) -> dict[int, dict[str, float]]:
    headers = list(
        _LARGE_APERTURE_SCANNING_TELE_COEFFICIENT_HEADER_PATTERN.finditer(table_text)
    )
    if len(headers) not in {1, 2}:
        raise PatentParseError(
            f"large-aperture scanning tele example {example} coefficient section count changed"
        )

    coefficients: dict[int, dict[str, float]] = {}
    observed_labels: set[str] = set()
    for header_index, header in enumerate(headers):
        end = headers[header_index + 1].start() if header_index + 1 < len(headers) else len(
            table_text
        )
        tokens = table_text[header.end() : end].split()
        pos = 0
        labels: list[str] = []
        while pos < len(tokens) and re.fullmatch(
            r"Conic|\d+\.sup\.th",
            tokens[pos],
            flags=re.IGNORECASE,
        ):
            labels.append(tokens[pos])
            pos += 1
        if not labels:
            raise PatentParseError(
                f"large-aperture scanning tele example {example} coefficient labels missing"
            )
        codev_labels: list[str] = []
        for label in labels:
            if label.lower() == "conic":
                codev_label = "K"
            else:
                order = int(label.split(".", 1)[0])
                if order not in {4, 6, 8, 10, 12, 14, 16}:
                    raise PatentParseError(
                        f"large-aperture scanning tele example {example} unsupported "
                        f"coefficient order {order}"
                    )
                codev_label = ASPHERE_ORDER_TO_CODEV[order]
            if codev_label in observed_labels:
                raise PatentParseError(
                    f"large-aperture scanning tele example {example} duplicate "
                    f"coefficient label {codev_label}"
                )
            observed_labels.add(codev_label)
            codev_labels.append(codev_label)

        for surface_index in range(2, 14):
            if pos >= len(tokens) or tokens[pos] != str(surface_index):
                actual = tokens[pos] if pos < len(tokens) else "<end>"
                raise PatentParseError(
                    f"large-aperture scanning tele example {example} coefficient sequence "
                    f"expected {surface_index}, found {actual}"
                )
            pos += 1
            row = coefficients.setdefault(surface_index, {})
            for codev_label in codev_labels:
                if pos >= len(tokens):
                    raise PatentParseError(
                        f"large-aperture scanning tele example {example} surface "
                        f"{surface_index} coefficient row is incomplete"
                    )
                row[codev_label] = _parse_number(tokens[pos])
                pos += 1

    expected_labels = {"K", "A", "B", "C", "D", "E", "F", "G"}
    if observed_labels != expected_labels or any(
        set(coefficients.get(surface_index, {})) != expected_labels
        for surface_index in range(2, 14)
    ):
        raise PatentParseError(
            f"large-aperture scanning tele example {example} coefficient coverage changed"
        )
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


def _classify_samsung_ten_lens_undefined_high_order_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Fail closed when exact Samsung tables publish undefined L-P terms.

    The retained official family publishes ten complete surface tables. Its
    asphere equation defines A-H and J through the 20th-order term, while every
    paired coefficient table also contains non-zero L-P rows without defining
    their polynomial powers. Mapping those rows by convention would invent
    optical semantics, so each disclosed embodiment receives a terminal source
    metadata outcome instead of a partial prescription.
    """

    if _SAMSUNG_TEN_LENS_TITLE_PATTERN.search(text) is None:
        return []
    profile = _SAMSUNG_TEN_LENS_UNDEFINED_HIGH_ORDER_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiment_numbers = range(1, 11)

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Samsung ten-lens embodiment {embodiment_number}",
                error=exc,
            )
            for embodiment_number in embodiment_numbers
        ]

    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"Samsung ten-lens official text hash changed for {patent_id}"
            )
        if len(re.findall(r"Family\s+ID:\s*91269360", text, flags=re.IGNORECASE)) != 1:
            raise PatentParseError("Samsung ten-lens Family ID binding changed")
        if len(_SAMSUNG_TEN_LENS_FOV_DEFINITION.findall(text)) != 1:
            raise PatentParseError("Samsung ten-lens full-field FOV definition changed")
        if len(_SAMSUNG_TEN_LENS_PUBLISHED_ASPHERE_DEFINITION.findall(text)) != 1:
            raise PatentParseError("Samsung ten-lens A-H/J asphere definition changed")
        if re.search(
            r"\b(?:L\s+to\s+P|L\s*,\s*M\s*,\s*N\s*,\s*O\s*,\s*(?:and\s+)?P)\s+"
            r"are\s+aspherical\s+(?:surface\s+)?constants\b",
            text,
            flags=re.IGNORECASE,
        ) is not None:
            raise PatentParseError("Samsung ten-lens L-P terms now have a published definition")

        bindings = list(_SAMSUNG_TEN_LENS_BINDING_PATTERN.finditer(text))
        if len(bindings) != 10:
            raise PatentParseError(
                f"Samsung ten-lens family must bind 10 embodiments, found {len(bindings)}"
            )
        for embodiment_number, binding in enumerate(bindings, start=1):
            expected_pair = (embodiment_number * 2 - 1, embodiment_number * 2)
            observed_pair = (
                int(binding.group("surface_table")),
                int(binding.group("asphere_table")),
            )
            if observed_pair != expected_pair:
                raise PatentParseError(
                    "Samsung ten-lens table binding is not consecutive at embodiment "
                    f"{embodiment_number}: {observed_pair}"
                )

        blocks = _numbered_patent_table_blocks(text)
        if set(blocks) != set(range(1, 25)):
            raise PatentParseError("Samsung ten-lens family must contain TABLE 1 through 24")
        _validate_samsung_ten_lens_metadata(blocks)
        for embodiment_number in embodiment_numbers:
            _validate_samsung_ten_lens_surface_table(
                blocks[embodiment_number * 2 - 1],
                embodiment_number=embodiment_number,
            )
            _validate_samsung_ten_lens_undefined_high_order_table(
                blocks[embodiment_number * 2],
                embodiment_number=embodiment_number,
            )
    except Exception as exc:  # noqa: BLE001 - retain all disclosed embodiments
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=embodiment_number,
            embodiment=f"Samsung ten-lens embodiment {embodiment_number}",
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code=(
                    "metadata_unpublished.high_order_asphere_term_definition_absent"
                ),
                detail=(
                    f"TABLE {embodiment_number * 2 - 1}/{embodiment_number * 2} "
                    "publishes a complete surface/asphere pair, but the official "
                    "equation defines only A-H/J while the coefficient table contains "
                    "non-zero L-P rows with no published polynomial-power mapping; "
                    "conventional mapping is not substituted"
                ),
            ),
        )
        for embodiment_number in embodiment_numbers
    ]


def _validate_samsung_ten_lens_metadata(blocks: dict[int, str]) -> None:
    sections = (
        (21, "First Second Third Fourth Fifth Reference embodiment"),
        (22, "Sixth Seventh Eighth Ninth Tenth Reference embodiment"),
    )
    for table_number, header in sections:
        table = blocks[table_number]
        if header not in table:
            raise PatentParseError(
                f"Samsung ten-lens TABLE {table_number} metadata header changed"
            )
        _parse_exact_five_value_row(table, label="f")
        _parse_exact_five_value_row(table, label="f number")
        _parse_exact_five_value_row(table, label="FOV")


def _validate_samsung_ten_lens_surface_table(
    table: str,
    *,
    embodiment_number: int,
) -> None:
    header = _SAMSUNG_TEN_LENS_SURFACE_HEADER_PATTERN.search(table)
    if header is None:
        raise PatentParseError(
            f"Samsung ten-lens embodiment {embodiment_number} surface header changed"
        )
    indices = [
        int(match.group("index"))
        for match in re.finditer(
            r"(?<!\S)S(?P<index>\d+)\s+",
            table[header.end() :],
            flags=re.IGNORECASE,
        )
    ]
    if indices != list(range(1, 24)):
        raise PatentParseError(
            f"Samsung ten-lens embodiment {embodiment_number} surface sequence "
            f"is {indices}; expected S1-S23"
        )


def _validate_samsung_ten_lens_undefined_high_order_table(
    table: str,
    *,
    embodiment_number: int,
) -> None:
    headers = list(_SAMSUNG_TEN_LENS_COEFFICIENT_HEADER_PATTERN.finditer(table))
    expected_groups = (
        tuple(range(1, 8)),
        tuple(range(8, 15)),
        tuple(range(15, 21)),
    )
    observed_groups = tuple(
        tuple(int(token[1:]) for token in header.group("surfaces").split())
        for header in headers
    )
    if observed_groups != expected_groups:
        raise PatentParseError(
            f"Samsung ten-lens embodiment {embodiment_number} coefficient headers "
            f"are {observed_groups}; expected S1-S7, S8-S14, and S15-S20"
        )

    labels = ("K", "A", "B", "C", "D", "E", "F", "G", "H", "J", "L", "M", "N", "O", "P")
    high_order_nonzero = False
    for section_number, (header, surface_indices) in enumerate(
        zip(headers, expected_groups, strict=True),
        start=1,
    ):
        section_end = (
            headers[section_number].start() if section_number < len(headers) else len(table)
        )
        tokens = table[header.end() : section_end].split()
        position = 0
        for label in labels:
            if position >= len(tokens) or tokens[position].upper() != label:
                raise PatentParseError(
                    f"Samsung ten-lens embodiment {embodiment_number} section "
                    f"{section_number} coefficient row {label} changed"
                )
            position += 1
            value_tokens = tokens[position : position + len(surface_indices)]
            if len(value_tokens) != len(surface_indices) or any(
                re.fullmatch(NUMBER_PATTERN, token, flags=re.IGNORECASE) is None
                for token in value_tokens
            ):
                raise PatentParseError(
                    f"Samsung ten-lens embodiment {embodiment_number} section "
                    f"{section_number} coefficient row {label} is incomplete"
                )
            values = tuple(_parse_number(token) for token in value_tokens)
            if label in {"L", "M", "N", "O", "P"} and any(value != 0.0 for value in values):
                high_order_nonzero = True
            position += len(surface_indices)
    if not high_order_nonzero:
        raise PatentParseError(
            f"Samsung ten-lens embodiment {embodiment_number} has no non-zero L-P evidence"
        )


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


def _classify_barcode_scanner_architecture_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify one exact Zebra barcode-reader architecture family."""

    if _BARCODE_SCANNER_ARCHITECTURE_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _BARCODE_SCANNER_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    embodiment = "non-internet-connected barcode-reader architecture"
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"barcode-reader official text hash changed for {patent_id}"
            )
        if _patent_table_blocks(text):
            raise PatentParseError(
                "barcode-reader disclosure unexpectedly contains PPUBS tables"
            )
        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"barcode-reader phrase {phrase!r} occurs {observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bcurvature\s+radius\b|\bradius\s+of\s+curvature\b|"
            r"\baspher(?:e|ic|ical)\s+(?:surface\s+)?"
            r"(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)\b|\bSurface\s+(?:No\.|#)\s*|"
            r"\bFno\b|\bF\s*[- ]?number\b|\bEFL\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|TABLE-US-)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "barcode-reader disclosure contains a prescription marker"
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
                    "confirmed_no_prescription.barcode_scanner_architecture_only"
                ),
                detail=(
                    "the exact retained official PPUBS disclosure publishes barcode-reader "
                    "illumination, aiming, image-sensor, and decoding architecture but no "
                    "optical surface prescription or prescription table"
                ),
            ),
        )
    ]


def _classify_imaging_lens_system_architecture_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify one exact multi-camera imaging-lens architecture family."""

    if _IMAGING_LENS_SYSTEM_ARCHITECTURE_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _IMAGING_LENS_SYSTEM_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []
    embodiment = "multi-camera imaging-lens system architecture"
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"imaging-lens-system official text hash changed for {patent_id}"
            )
        if _patent_table_blocks(text):
            raise PatentParseError(
                "imaging-lens-system disclosure unexpectedly contains PPUBS tables"
            )
        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"imaging-lens-system phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bradius\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)\b|\bSurface\s+(?:No\.|#)\s*|"
            r"\bFno\b|\bF\s*[- ]?number\b|\bEFL\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\bprescription\b|TABLE-US-)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "imaging-lens-system disclosure contains a prescription marker"
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
                    "confirmed_no_prescription.imaging_lens_system_architecture_only"
                ),
                detail=(
                    "the exact retained official PPUBS disclosure publishes multi-camera "
                    "lens-element arrangement and system-level equivalent focal ranges but "
                    "no optical surface prescription or prescription table"
                ),
            ),
        )
    ]


def _classify_extended_depth_of_focus_architecture_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify three exact EDOF phase-element architecture disclosures."""

    if _EXTENDED_DEPTH_OF_FOCUS_ARCHITECTURE_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _EXTENDED_DEPTH_OF_FOCUS_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []
    embodiment = "extended-depth-of-focus phase-element architecture"
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"extended-depth-of-focus official text hash changed for {patent_id}"
            )
        blocks = _patent_table_blocks(text)
        if [block.number for block in blocks] != [1, 2]:
            raise PatentParseError(
                "extended-depth-of-focus clinical table denominator changed"
            )
        required_table_headers = (
            "Summary of the reading test.",
            "Summary of the effect of the invented element on far vision.",
        )
        for block, header in zip(blocks, required_table_headers, strict=True):
            if len(re.findall(re.escape(header), block.text, flags=re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"extended-depth-of-focus clinical table {block.number} header changed"
                )
        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"extended-depth-of-focus phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        for phrase, expected in profile["drawing_anchor_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"extended-depth-of-focus drawing anchor {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bcurvature\s+radius\b|\bradius\s+of\s+curvature\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)\b|\bSurface\s+(?:No\.?|#|Number)\b|"
            r"\bFno\b|\bF\s*[- ]?number\b|\bEFL\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\blens\s+parameters?\b|\bprescription\b|"
            r"\b(?:Surface|Surf)\s+(?:No\.?|#).{0,200}\bRadius\b"
            r".{0,200}\b(?:Thickness|Distance)\b)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "extended-depth-of-focus disclosure contains a prescription marker"
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
                    "extended_depth_of_focus_phase_element_architecture_only"
                ),
                detail=(
                    "the exact retained official PPUBS disclosure publishes EDOF "
                    "phase-element architecture, simulations, experiments, and two "
                    "clinical-result tables but no optical surface prescription"
                ),
            ),
        )
    ]


def _classify_lens_barrel_absorbing_geometry_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify exact Family 72082560 barrel/absorbing-layer examples.

    Examples 1-7 publish only entrance/minimum-opening, barrel, effective
    optical-surface, element-diameter, center-thickness, and axial-length
    geometry.  Example 8 is the smartphone/camera-module wrapper.  The exact
    retained sources publish no curvature, glass, asphere, EFL, F-number, or
    field prescription and their drawing descriptions contain no hidden table
    or prescription reference.
    """

    profile = _LENS_BARREL_ABSORBING_GEOMETRY_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=f"Lens-barrel absorbing geometry example {index}",
                error=exc,
            )
            for index in range(1, 9)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"lens-barrel absorbing official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"lens-barrel absorbing normalized text hash changed for {patent_id}"
            )
        if _LENS_BARREL_ABSORBING_GEOMETRY_ONLY_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("lens-barrel absorbing title binding changed")
        if len(re.findall(r"Family\s+ID:\s*72082560", text, re.IGNORECASE)) != 1:
            raise PatentParseError("lens-barrel absorbing Family ID binding changed")
        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("lens-barrel absorbing application binding changed")

        blocks = _patent_table_blocks(text)
        if [block.number for block in blocks] != list(range(1, 8)):
            raise PatentParseError("lens-barrel absorbing source tables must be 1-7")
        for index, block in enumerate(blocks, start=1):
            body = _cut_sunny_table_narrative(block.text)
            suffix = "st" if index == 1 else "nd" if index == 2 else "rd" if index == 3 else "th"
            if re.search(rf"\b{index}{suffix}\s+example\b", body, re.IGNORECASE) is None:
                raise PatentParseError(
                    f"lens-barrel absorbing TABLE {index} example binding changed"
                )
            required_labels = (
                r"\bEPD\s*\(mm\)",
                r"ψb\s*\(mm\)",
                r"\bCT\s*\(mm\)",
                r"(?<!ψ)\bL\s*\(mm\)",
                r"ψY\s*/\s*CT",
            )
            if any(re.search(label, body, re.IGNORECASE) is None for label in required_labels):
                raise PatentParseError(
                    f"lens-barrel absorbing TABLE {index} geometry header changed"
                )
            if index <= 6 and re.search(r"ψL\s*\(mm\)", body) is None:
                raise PatentParseError(
                    f"lens-barrel absorbing TABLE {index} element-diameter header changed"
                )
            if index == 7 and re.search(
                re.escape(str(profile["table7_prefix"])),
                body,
                re.IGNORECASE,
            ) is None:
                raise PatentParseError(
                    "lens-barrel absorbing TABLE 7 source-prefix binding changed"
                )
            has_effective_diameter = re.search(r"ψA\s*\(mm\)", body) is not None
            if has_effective_diameter != (index <= 6):
                raise PatentParseError(
                    f"lens-barrel absorbing TABLE {index} effective-diameter binding changed"
                )

        for index in range(1, 9):
            suffix = "st" if index == 1 else "nd" if index == 2 else "rd" if index == 3 else "th"
            heading = rf"\b{index}{suffix}\s+Example\s+(?:\(\d+\)|\[\d+\])\s+FIG\."
            if len(re.findall(heading, text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"lens-barrel absorbing example {index} section binding changed"
                )

        for phrase, expected in profile["geometry_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"lens-barrel absorbing phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        drawings = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+THE\s+DRAWINGS(?P<body>.*?)"
            r"DETAILED\s+DESCRIPTION",
            text,
            re.IGNORECASE,
        )
        if drawings is None:
            raise PatentParseError("lens-barrel absorbing drawing description is missing")
        if re.search(
            r"\b(?:table|prescription|optical\s+data|lens\s+data)\b",
            drawings.group("body"),
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "lens-barrel absorbing drawings now reference prescription data"
            )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)?\b|\brefractive\s+index\b|"
            r"\bSurface\s+(?:No\.|#)\s*|\bFno\b|\bF\s*[- ]?number\b|"
            r"\bEFL\b|\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\blens\s+data\b|\bprescription\b)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "lens-barrel absorbing disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain all eight explicit examples
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for index in range(1, 9):
        device_wrapper = index == 8
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=(
                    "Smartphone camera-module example 8"
                    if device_wrapper
                    else f"Lens-barrel absorbing geometry example {index}"
                ),
                error=PatentTerminalParseError(
                    status="confirmed_no_prescription",
                    reason_code=(
                        "confirmed_no_prescription.camera_module_device_architecture_only"
                        if device_wrapper
                        else (
                            "confirmed_no_prescription."
                            "lens_barrel_absorbing_geometry_only"
                        )
                    ),
                    detail=(
                        "example 8 publishes only the smartphone, camera-module, image-sensor, "
                        "and user-interface wrapper; it has no optical prescription"
                        if device_wrapper
                        else (
                            f"TABLE {index} publishes only opening, barrel, effective-surface, "
                            "element-diameter, center-thickness, length, and ratio geometry; "
                            "it has no optical surface prescription"
                        )
                    ),
                ),
            )
        )
    return attempts


def _classify_low_reflection_light_blocking_architecture_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify all five exact Family 73978649 source-declared examples.

    Examples 1-4 publish low-reflection carbon-black/nano/coating stacks on
    barrel, spacer, retainer, or light-blocking components.  Example 5 is the
    smartphone/camera-module wrapper.  The sole table is a 380-1050 nm
    reflectivity experiment, not an ordered optical surface prescription.
    """

    profile = _LOW_REFLECTION_LIGHT_BLOCKING_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=label,
                error=exc,
            )
            for index, label in enumerate(
                _LOW_REFLECTION_LIGHT_BLOCKING_ITEM_LABELS,
                start=1,
            )
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"low-reflection light-blocking official raw text hash changed for "
                f"{patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"low-reflection light-blocking normalized text hash changed for "
                f"{patent_id}"
            )
        if (
            _LOW_REFLECTION_LIGHT_BLOCKING_ARCHITECTURE_ONLY_TITLE_PATTERN.search(
                text
            )
            is None
        ):
            raise PatentParseError("low-reflection light-blocking title binding changed")
        if len(re.findall(r"Family\s+ID:\s*73978649", text, re.IGNORECASE)) != 1:
            raise PatentParseError(
                "low-reflection light-blocking Family ID binding changed"
            )
        owner = "Largan Precision Co., Ltd."
        if len(re.findall(re.escape(owner), text, re.IGNORECASE)) != profile[
            "owner_count"
        ]:
            raise PatentParseError(
                "low-reflection light-blocking owner binding changed"
            )
        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "low-reflection light-blocking application binding changed"
            )
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"low-reflection light-blocking relationship marker {marker!r} "
                    f"occurs {observed}; expected 1"
                )

        headings = tuple(
            index
            for index, suffix in ((1, "ST"), (2, "ND"), (3, "RD"), (4, "TH"), (5, "TH"))
            if len(
                re.findall(
                    rf"<br\s*/?>\s*{index}{suffix}\s+EXAMPLE\s*<br\s*/?>",
                    raw_text,
                    re.IGNORECASE,
                )
            )
            == 1
        )
        if headings != (1, 2, 3, 4, 5):
            raise PatentParseError(
                "low-reflection light-blocking five-example denominator changed"
            )

        table_ids = tuple(re.findall(r"TABLE-US-(\d+)", raw_text, re.IGNORECASE))
        if table_ids != ("00001",):
            raise PatentParseError(
                "low-reflection light-blocking one-table denominator changed"
            )
        table_match = re.search(
            r"TABLE-US-00001(?P<body>.*?)<br\s*/?>",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if table_match is None:
            raise PatentParseError(
                "low-reflection light-blocking TABLE 1 body is missing"
            )
        table_text = normalize_patent_text(
            "TABLE-US-00001" + table_match.group("body")
        )
        if (
            hashlib.sha256(table_text.encode("utf-8")).hexdigest()
            != _LOW_REFLECTION_LIGHT_BLOCKING_TABLE_SHA256
        ):
            raise PatentParseError(
                "low-reflection light-blocking TABLE 1 digest changed"
            )
        if not table_text.startswith(
            "TABLE-US-00001 TABLE 1 wavelength 0 degrees 90 degrees "
            "180 degrees 270 degrees (nm) (%) (%) (%) (%)"
        ):
            raise PatentParseError(
                "low-reflection light-blocking TABLE 1 column binding changed"
            )
        wavelengths = tuple(
            int(value)
            for value in re.findall(
                r"(?<![\d.])(\d{3,4})\s+[-+]?\d+\.\d+\s+[-+]?\d+\.\d+\s+"
                r"[-+]?\d+\.\d+\s+[-+]?\d+\.\d+",
                table_text,
            )
        )
        if wavelengths != tuple(range(380, 1051)):
            raise PatentParseError(
                "low-reflection light-blocking TABLE 1 wavelength denominator changed"
            )

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)DETAILED DESCRIPTION",
            text,
            re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError(
                "low-reflection light-blocking drawing description is missing"
            )
        drawings = tuple(
            re.findall(
                r"FIG\.\s*(\d+)\s*([A-Z]?)\s+(?:is|shows|illustrates)",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if drawings != _LOW_REFLECTION_LIGHT_BLOCKING_DRAWINGS:
            raise PatentParseError(
                "low-reflection light-blocking 23-panel drawing denominator changed"
            )
        if re.search(
            r"\b(?:prescription|optical\s+data|lens\s+data)\b",
            brief_match.group("body"),
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "low-reflection light-blocking drawings now reference prescription data"
            )

        for phrase, expected in _LOW_REFLECTION_LIGHT_BLOCKING_PHRASE_COUNTS.items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"low-reflection light-blocking phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe(?:\s+(?:number|#))?\b|"
            r"\bSurface\s+(?:No\.?|#|Number)\s*\d+\b|"
            r"\bFno\b|\bF\s*[- ]?number\b|\bEFL\b|"
            r"\beffective\s+focal\s+length\b|\bfield\s+of\s+view\b|\bHFOV\b|"
            r"\boptical\s+(?:surface\s+)?(?:prescription|data)\b|"
            r"\blens\s+(?:prescription|data)\b|\bprescription\b|"
            r"\b(?:Surface|Surf)\s+(?:No\.?|#).{0,200}\bRadius\b"
            r".{0,200}\b(?:Thickness|Distance)\b)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "low-reflection light-blocking disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain all five explicit examples
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for index, label in enumerate(_LOW_REFLECTION_LIGHT_BLOCKING_ITEM_LABELS, start=1):
        device_wrapper = index == 5
        if index == 1:
            detail = (
                "example 1 publishes the carbon-black/nano/coating stack, component "
                "geometry, and TABLE 1's 671 wavelength/azimuth reflectivity rows; "
                "it has no ordered optical surface prescription"
            )
        elif device_wrapper:
            detail = (
                "example 5 publishes only the smartphone, camera-module, image-sensor, "
                "ISP, OIS, user-interface, and capture-mode wrapper; it has no optical "
                "surface prescription"
            )
        else:
            detail = (
                f"example {index} publishes only low-reflection coating stacks and "
                "barrel, spacer, retainer, or light-blocking component arrangements; "
                "it has no ordered optical surface prescription"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=label,
                error=PatentTerminalParseError(
                    status="confirmed_no_prescription",
                    reason_code=(
                        "confirmed_no_prescription."
                        "camera_module_device_architecture_only"
                        if device_wrapper
                        else (
                            "confirmed_no_prescription."
                            "low_reflection_coating_and_light_blocking_architecture_only"
                        )
                    ),
                    detail=detail,
                ),
            )
        )
    return attempts


def _classify_folded_lens_barrel_driving_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify exact Family 77725725 mechanical and device embodiments."""

    profile = _FOLDED_LENS_BARREL_DRIVING_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiments = (
        "Folded lens-barrel driving and sensing architecture example 1",
        "Multi-camera electronic-device architecture example 2",
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"folded lens-barrel driving official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                "folded lens-barrel driving normalized text hash changed "
                f"for {patent_id}"
            )
        if _FOLDED_LENS_BARREL_DRIVING_ONLY_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("folded lens-barrel driving title binding changed")
        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "folded lens-barrel driving application binding changed"
            )
        for marker in profile["heading_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"folded lens-barrel driving heading {marker!r} changed"
                )
        if re.search(r"\b3rd\s+Embodiment\b", text, re.IGNORECASE) is not None:
            raise PatentParseError(
                "folded lens-barrel driving source gained a third embodiment"
            )
        table_prefix = str(profile["table_prefix"])
        if len(re.findall(re.escape(table_prefix), text, re.IGNORECASE)) != 1:
            raise PatentParseError(
                "folded lens-barrel driving sensing-distance table changed"
            )
        if len(_patent_table_blocks(text)) != profile["ppubs_table_count"]:
            raise PatentParseError(
                "folded lens-barrel driving PPUBS table-label layout changed"
            )
        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"folded lens-barrel driving phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        if len(re.findall(r"\bfocal\s+length\b", text, re.IGNORECASE)) != 1:
            raise PatentParseError(
                "folded lens-barrel driving nonnumeric focal-length architecture changed"
            )
        drawings = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+THE\s+DRAWINGS(?P<body>.*?)"
            r"DETAILED\s+DESCRIPTION",
            text,
            re.IGNORECASE,
        )
        if drawings is None:
            raise PatentParseError(
                "folded lens-barrel driving drawing description is missing"
            )
        if re.search(
            r"\b(?:table|prescription|optical\s+data|lens\s+data)\b",
            drawings.group("body"),
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "folded lens-barrel driving drawings now reference prescription data"
            )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)?\b|\brefractive\s+index\b|"
            r"\bSurface\s+(?:No\.|#)\s*|\bFno\b|\bF\s*[- ]?number\b|"
            r"\bEFL\b|\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\blens\s+data\b|\bprescription\b)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "folded lens-barrel driving disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain both explicit embodiments
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=1,
            embodiment=embodiments[0],
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code=(
                    "confirmed_no_prescription."
                    "lens_driving_mechanical_architecture_only"
                ),
                detail=(
                    "example 1 publishes folded lens barrels, rolling bearings, magnets, "
                    "coils, sensing elements, and sensing-element axial distances only; "
                    "it has no optical surface prescription"
                ),
            ),
        ),
        _PrescriptionParseAttempt(
            embodiment_number=2,
            embodiment=embodiments[1],
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code=(
                    "confirmed_no_prescription."
                    "camera_module_device_architecture_only"
                ),
                detail=(
                    "example 2 publishes only smartphone, image-sensor, and multiple "
                    "image-capturing-device architecture; it has no optical surface "
                    "prescription"
                ),
            ),
        ),
    ]


def _classify_endoscopic_three_lens_missing_f_number_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain three exact endoscopic prescriptions whose F-number is unpublished."""

    profile = _ENDOSCOPIC_THREE_LENS_MISSING_F_NUMBER_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiments = tuple(
        f"Endoscopic optical imaging lens assembly embodiment {index}"
        for index in range(1, 4)
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"endoscopic three-lens official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"endoscopic three-lens normalized text hash changed for {patent_id}"
            )
        if (
            len(_ENDOSCOPIC_THREE_LENS_MISSING_F_NUMBER_TITLE_PATTERN.findall(text))
            != 1
        ):
            raise PatentParseError("endoscopic three-lens title binding changed")
        if len(re.findall(r"Family\s+ID:\s*78592599", text, re.IGNORECASE)) != 1:
            raise PatentParseError("endoscopic three-lens Family ID binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("endoscopic three-lens application binding changed")
        for marker in profile["relationship_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"endoscopic three-lens relationship marker {marker!r} changed"
                )

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)DETAILED DESCRIPTION",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError(
                "endoscopic three-lens drawing description is missing"
            )
        declared_figures = tuple(
            int(figure)
            for figure in re.findall(
                r"FIG\.\s*<b>(\d+)</b></figref>\s+is\s+",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if declared_figures != _ENDOSCOPIC_THREE_LENS_FIGURES:
            raise PatentParseError(
                "endoscopic three-lens 11-figure denominator changed"
            )
        drawing_text = normalize_patent_text(brief_match.group("body"))
        drawing_roles = (
            len(re.findall(r"functional\s+block\s+diagram", drawing_text, re.IGNORECASE)),
            len(
                re.findall(
                    r"diagram\s+of\s+(?:an?\s+)?(?:the\s+)?optical\s+imaging\s+"
                    r"lens\s+assembly",
                    drawing_text,
                    re.IGNORECASE,
                )
            ),
            len(re.findall(r"diagram\s+of\s+distortion", drawing_text, re.IGNORECASE)),
            len(
                re.findall(
                    r"diagram\s+of\s+relative\s+illumination",
                    drawing_text,
                    re.IGNORECASE,
                )
            ),
        )
        if drawing_roles != (2, 3, 3, 3):
            raise PatentParseError("endoscopic three-lens drawing roles changed")

        table_binding_patterns = (
            r"illustrated\s+in\s+Table\s+1\s*,\s*and\s+further\s+have\s+optical\s+"
            r"data\s+and\s+aspheric\s+surface\s+data\s+respectively\s+illustrated\s+"
            r"in\s+Table\s+2\s+and\s+Table\s+3",
            r"illustrated\s+in\s+Table\s+4\s*,\s*and\s+further\s+have\s+optical\s+"
            r"data\s+and\s+aspheric\s+surface\s+data\s+respectively\s+illustrated\s+"
            r"in\s+Table\s+5\s+and\s+Table\s+6",
            r"illustrated\s+in\s+Table\s+7\s*,\s*and\s+further\s+have\s+optical\s+"
            r"data\s+and\s+aspheric\s+surface\s+data\s+respectively\s+illustrated\s+"
            r"in\s+Table\s+8\s+and\s+Table\s+9",
        )
        for embodiment_number, pattern in enumerate(table_binding_patterns, start=1):
            if len(re.findall(pattern, text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    "endoscopic three-lens embodiment "
                    f"{embodiment_number} table binding changed"
                )
        if re.search(r"\bfourth\s+embodiment\b", text, re.IGNORECASE) is not None:
            raise PatentParseError(
                "endoscopic three-lens source gained a fourth optical embodiment"
            )

        blocks = _patent_table_blocks(text)
        table_numbers = tuple(block.number for block in blocks)
        if table_numbers != tuple(range(1, 10)):
            raise PatentParseError(
                f"endoscopic three-lens table sequence is {table_numbers}; expected 1..9"
            )
        table_digests = tuple(
            hashlib.sha256(block.text.encode("utf-8")).hexdigest() for block in blocks
        )
        if table_digests != profile["table_block_sha256"]:
            raise PatentParseError("endoscopic three-lens table digest changed")

        for embodiment_number, (system_number, surface_number, asphere_number) in enumerate(
            _ENDOSCOPIC_THREE_LENS_TABLE_BINDINGS,
            start=1,
        ):
            system_text = blocks[system_number - 1].text
            surface_text = blocks[surface_number - 1].text
            asphere_text = blocks[asphere_number - 1].text
            if len(
                re.findall(
                    re.escape(_ENDOSCOPIC_THREE_LENS_SYSTEM_ROWS[embodiment_number - 1]),
                    system_text,
                    re.IGNORECASE,
                )
            ) != 1:
                raise PatentParseError(
                    "endoscopic three-lens embodiment "
                    f"{embodiment_number} system row changed"
                )
            surface_markers = (
                "Thickness Air gap Curvature Ape. stop radius distance",
                "Refractive No. (mm) (mm) index Abbe No.",
                "261(26) First lens",
                "281(28) Second",
                "30 Aperture",
                "321(32) Third lens",
                "34 Filter",
                "36 Image",
            )
            if any(
                len(re.findall(re.escape(marker), surface_text, re.IGNORECASE)) != 1
                for marker in surface_markers
            ):
                raise PatentParseError(
                    "endoscopic three-lens embodiment "
                    f"{embodiment_number} surface-table structure changed"
                )
            if re.search(
                r"No\.\s+261\(26\)\s+262\(26\)\s+281\(28\)\s+282\(28\)\s+"
                r"321\(32\)\s+322\(32\)\s+K\s+.*?\s+A4\s+.*?\s+A6\s+.*?\s+"
                r"A8\s+.*?\s+A10\s+.*?\s+A12\s+",
                asphere_text,
                re.IGNORECASE,
            ) is None:
                raise PatentParseError(
                    "endoscopic three-lens embodiment "
                    f"{embodiment_number} asphere-table structure changed"
                )

        forbidden_f_number_patterns = (
            r"\bF\s*[- ]?number\b",
            r"\bFNO\b",
            r"\bF\s*/\s*(?:#|No\.?|Number|\d)",
            r"\baperture\s+number\b",
            r"\bnumerical\s+aperture\b",
        )
        for pattern in forbidden_f_number_patterns:
            observed = len(re.findall(pattern, text, re.IGNORECASE))
            if observed != 0:
                raise PatentParseError(
                    f"endoscopic three-lens F-number marker {pattern!r} occurs "
                    f"{observed}; expected 0"
                )
    except Exception as exc:  # noqa: BLE001 - retain all three optical embodiments
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code="metadata_unpublished.system_f_number_absent",
                detail=(
                    f"Tables {3 * index - 2}-{3 * index} publish direct EFL/HFOV, "
                    "the complete surface prescription, and asphere coefficients, but "
                    "the official HTML and all-page official raster audit publish no "
                    "exact system F-number; aperture-stop position and curvature are "
                    "not substituted or used to derive it"
                ),
            ),
        )
        for index, embodiment in enumerate(embodiments, start=1)
    ]


def _classify_sunny_automotive_nineteen_lens_missing_f_number_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain 19 exact seven-lens prescriptions whose F-number is unpublished."""

    profile = _SUNNY_AUTOMOTIVE_NINETEEN_LENS_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiments = tuple(
        f"Sunny automotive seven-lens embodiment {index}"
        for index in range(1, 20)
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"Sunny automotive official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"Sunny automotive normalized text hash changed for {patent_id}"
            )
        if len(_SUNNY_AUTOMOTIVE_NINETEEN_LENS_TITLE_PATTERN.findall(raw_text)) != 1:
            raise PatentParseError("Sunny automotive title binding changed")
        if len(
            re.findall(
                rf"Family\s+ID:\s*{re.escape(str(profile['family_id']))}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("Sunny automotive Family ID binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("Sunny automotive application binding changed")
        for marker in profile["identity_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"Sunny automotive identity marker {marker!r} changed"
                )

        heading_numbers = tuple(
            int(number)
            for number in re.findall(
                r"<br\s*/?>\s*Embodiment\s+(\d+)\s*<br\s*/?>",
                raw_text,
                re.IGNORECASE,
            )
        )
        if heading_numbers != tuple(range(1, 20)):
            raise PatentParseError(
                "Sunny automotive nineteen-embodiment heading denominator changed"
            )

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)"
            r"DETAILED DESCRIPTION OF EMBODIMENTS",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError("Sunny automotive drawing description is missing")
        declared_figures = tuple(
            int(figure)
            for figure in re.findall(
                r"FIG\.\s*<b>(\d+)</b></figref>\s+is\s+",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if declared_figures != _SUNNY_AUTOMOTIVE_NINETEEN_LENS_FIGURES:
            raise PatentParseError("Sunny automotive 20-figure denominator changed")
        drawing_text = normalize_patent_text(brief_match.group("body"))
        for embodiment_number in range(1, 20):
            figure_binding = (
                rf"FIG\.\s*{embodiment_number}\s+is\s+a\s+schematic\s+structural\s+"
                rf"diagram\s+of\s+an\s+optical\s+lens\s+assembly\s+according\s+to\s+"
                rf"Embodiment\s+{embodiment_number}\b"
            )
            if len(re.findall(figure_binding, drawing_text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    "Sunny automotive embodiment "
                    f"{embodiment_number} figure binding changed"
                )
        if len(re.findall(r"FIG\.\s*20\s+is\s+a\s+schematic\s+diagram", drawing_text)) != 1:
            raise PatentParseError("Sunny automotive FIG. 20 ray-angle role changed")

        for embodiment_number in range(1, 20):
            surface_number = 2 * embodiment_number - 1
            asphere_number = 2 * embodiment_number
            surface_binding = (
                rf"Table\s+{surface_number}\s+shows\s+.*?\s+in\s+"
                rf"Embodiment\s+{embodiment_number}\."
            )
            asphere_binding = (
                rf"Table\s+{asphere_number}(?:\s+below)?\s+(?:shows|gives)\s+.*?"
                rf"\s+in\s+Embodiment\s+{embodiment_number}\."
            )
            if len(re.findall(surface_binding, text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    "Sunny automotive embodiment "
                    f"{embodiment_number} surface-table binding changed"
                )
            if len(re.findall(asphere_binding, text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    "Sunny automotive embodiment "
                    f"{embodiment_number} asphere-table binding changed"
                )

        table_pattern = re.compile(
            r"(?P<full>TABLE-US-(?P<id>\d+)\s+TABLE\s+"
            r"(?P<title>\d+(?:-\d+)?)(?P<body>.*?)<br\s*/?>)",
            re.DOTALL | re.IGNORECASE,
        )
        table_records: list[dict[str, Any]] = []
        table_bodies: list[str] = []
        table_digests: list[str] = []
        for match in table_pattern.finditer(raw_text):
            full_text = normalize_patent_text(match.group("full"))
            body = normalize_patent_text(match.group("body"))
            digest = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
            table_records.append(
                {
                    "ppubs_id": int(match.group("id")),
                    "title": match.group("title"),
                    "sha256": digest,
                }
            )
            table_bodies.append(body)
            table_digests.append(digest)
        if tuple(record["ppubs_id"] for record in table_records) != tuple(
            range(1, 43)
        ):
            raise PatentParseError("Sunny automotive PPUBS table ID sequence changed")
        if tuple(record["title"] for record in table_records) != (
            _SUNNY_AUTOMOTIVE_NINETEEN_LENS_TABLE_TITLES
        ):
            raise PatentParseError("Sunny automotive PPUBS table title sequence changed")
        aggregate_payload = json.dumps(
            table_records,
            sort_keys=True,
            separators=(",", ":"),
        )
        aggregate_digest = hashlib.sha256(
            aggregate_payload.encode("utf-8")
        ).hexdigest()
        if aggregate_digest != profile["table_aggregate_sha256"]:
            raise PatentParseError("Sunny automotive PPUBS table aggregate changed")
        if tuple(table_digests[38:42]) != (
            _SUNNY_AUTOMOTIVE_NINETEEN_LENS_SYSTEM_TABLE_SHA256
        ):
            raise PatentParseError("Sunny automotive system table digest changed")

        first_surface_header = (
            "surface radius of curvature thickness/distance refractive abbe number"
        )
        later_surface_header = (
            "radius of thickness/ surface curvature R distance d refractive abbe number"
        )
        asphere_header = "surface number k A4 A6 A8 A10 A12 A14 A16"
        for embodiment_number in range(1, 20):
            surface_body = table_bodies[2 * embodiment_number - 2]
            asphere_body = table_bodies[2 * embodiment_number - 1]
            expected_surface_header = (
                first_surface_header
                if embodiment_number <= 7
                else later_surface_header
            )
            if not surface_body.startswith(expected_surface_header):
                raise PatentParseError(
                    "Sunny automotive embodiment "
                    f"{embodiment_number} surface-table structure changed"
                )
            if not asphere_body.startswith(asphere_header):
                raise PatentParseError(
                    "Sunny automotive embodiment "
                    f"{embodiment_number} asphere-table structure changed"
                )

        for system_index, expected_rows in enumerate(
            _SUNNY_AUTOMOTIVE_NINETEEN_LENS_SYSTEM_ROWS,
            start=39,
        ):
            body = table_bodies[system_index - 1]
            for expected_row in expected_rows:
                if len(re.findall(re.escape(expected_row), body)) != 1:
                    raise PatentParseError(
                        f"Sunny automotive system TABLE {system_index} row changed"
                    )

        direct_f_values = re.findall(
            r"\bF\s+((?:\d+(?:\.\d+)?\s+){6}\d+(?:\.\d+)?)\s+H\b",
            table_bodies[38],
        )
        direct_f_values.extend(
            re.findall(
                r"\bF\s+((?:\d+(?:\.\d+)?\s+){3}\d+(?:\.\d+)?)\s+FOV\b",
                body,
            )[0]
            for body in table_bodies[39:42]
        )
        if sum(len(values.split()) for values in direct_f_values) != 19:
            raise PatentParseError("Sunny automotive direct EFL denominator changed")
        direct_fov_values = re.findall(
            r"\bFOV\s+((?:\d+(?:\.\d+)?\s+){6}\d+(?:\.\d+)?)\s+ENPD\b",
            table_bodies[38],
        )
        direct_fov_values.extend(
            re.findall(
                r"\bFOV\s+((?:\d+(?:\.\d+)?\s+){3}\d+(?:\.\d+)?)\s+F1\b",
                body,
            )[0]
            for body in table_bodies[39:42]
        )
        if sum(len(values.split()) for values in direct_fov_values) != 19:
            raise PatentParseError("Sunny automotive direct FOV denominator changed")

        forbidden_f_number_patterns = (
            r"\bF\s*[- ]?number\b",
            r"\bFNO\b",
            r"\bF\s*/\s*(?:#|No\.?|Number|\d)",
            r"\baperture\s+number\b",
            r"\bnumerical\s+aperture\b",
        )
        for pattern in forbidden_f_number_patterns:
            observed = len(re.findall(pattern, text, re.IGNORECASE))
            if observed != 0:
                raise PatentParseError(
                    f"Sunny automotive nineteen-embodiment F-number marker "
                    f"{pattern!r} occurs {observed}; expected 0"
                )
    except Exception as exc:  # noqa: BLE001 - retain all 19 optical embodiments
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code="metadata_unpublished.system_f_number_absent",
                detail=(
                    f"Tables {2 * index - 1}-{2 * index} publish the complete "
                    "seven-lens surface/asphere prescription, and TABLE 39 or "
                    "TABLES 40-1/40-2/40-3 publish direct EFL and FOV; the "
                    "official HTML and all-page official raster audits publish no "
                    "exact system F-number, so F/ENPD and F/EPD are retained as "
                    "source ratios and are not substituted or derived"
                ),
            ),
        )
        for index, embodiment in enumerate(embodiments, start=1)
    ]


def _classify_aac_near_eye_folded_three_lens_missing_metadata_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain exact Family 90845725 folded prescriptions with EFL/FNO absent.

    Both embodiments publish repeated reflective-path surface rows, R1-R6
    aspheres, entrance pupil, image height, and diagonal FOV.  Their symbolic
    focal-length ratios and track lengths do not directly publish numeric
    system EFL or F-number, so neither value is derived for conversion.
    """

    profile = _AAC_NEAR_EYE_FOLDED_THREE_LENS_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiments = (
        "AAC near-eye folded three-lens embodiment 1",
        "AAC near-eye folded three-lens embodiment 2",
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"AAC near-eye folded official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"AAC near-eye folded normalized text hash changed for {patent_id}"
            )
        if len(_AAC_NEAR_EYE_FOLDED_THREE_LENS_TITLE_PATTERN.findall(raw_text)) != 1:
            raise PatentParseError("AAC near-eye folded title binding changed")
        if len(re.findall(r"Family\s+ID:\s*90845725", text, re.IGNORECASE)) != 1:
            raise PatentParseError("AAC near-eye folded Family ID binding changed")
        owner = "Changzhou AAC Raytech Optronics Co., Ltd."
        if len(re.findall(re.escape(owner), text, re.IGNORECASE)) != profile[
            "owner_count"
        ]:
            raise PatentParseError("AAC near-eye folded owner binding changed")
        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("AAC near-eye folded application binding changed")
        if len(
            re.findall(
                re.escape(str(profile["priority_marker"])),
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("AAC near-eye folded priority binding changed")

        for heading, paragraph in (("First", "0052"), ("Second", "0093")):
            if len(
                re.findall(
                    rf"<br\s*/?>\s*{heading}\s+Embodiment\s*<br\s*/?>"
                    rf"\s*\[{paragraph}\]",
                    raw_text,
                    re.IGNORECASE,
                )
            ) != 1:
                raise PatentParseError(
                    f"AAC near-eye folded {heading.lower()} embodiment heading changed"
                )
        if re.search(
            r"<br\s*/?>\s*Third\s+Embodiment\s*<br\s*/?>",
            raw_text,
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError("AAC near-eye folded source gained a third embodiment")

        table_ids = tuple(re.findall(r"TABLE-US-(\d+)", raw_text, re.IGNORECASE))
        if table_ids != tuple(f"{index:05d}" for index in range(1, 6)):
            raise PatentParseError("AAC near-eye folded table sequence changed")
        table_texts: list[str] = []
        for index in range(1, 6):
            table_match = re.search(
                rf"TABLE-US-{index:05d}(?P<body>.*?)<br\s*/?>",
                raw_text,
                re.DOTALL | re.IGNORECASE,
            )
            if table_match is None:
                raise PatentParseError(
                    f"AAC near-eye folded TABLE {index} body is missing"
                )
            table_texts.append(
                normalize_patent_text(
                    f"TABLE-US-{index:05d}" + table_match.group("body")
                )
            )
        table_digests = tuple(
            hashlib.sha256(table_text.encode("utf-8")).hexdigest()
            for table_text in table_texts
        )
        if table_digests != _AAC_NEAR_EYE_FOLDED_THREE_LENS_TABLE_SHA256:
            raise PatentParseError("AAC near-eye folded table digest changed")
        table_prefixes = (
            "TABLE-US-00001 TABLE 1 R d nd νd OBJECT Infinity -1437.5",
            "TABLE-US-00002 TABLE 2 Conic coefficient Aspheric surface coefficients",
            "TABLE-US-00003 TABLE 3 R d nd νd OBJECT Infinity -1342.8",
            "TABLE-US-00004 TABLE 4 Conic coefficient Aspheric surface coefficient",
            "TABLE-US-00005 TABLE 5 Parameters and First Second Conditional Equations",
        )
        if any(
            not table_text.startswith(prefix)
            for table_text, prefix in zip(table_texts, table_prefixes, strict=True)
        ):
            raise PatentParseError("AAC near-eye folded table-role binding changed")
        folded_path_markers = (
            ("d6 -6.098", "d7 -0.289", "d8 -0.122"),
            ("d6 -5.647", "d8 -0.127"),
        )
        for index, markers in enumerate(folded_path_markers):
            surface_table = table_texts[index * 2]
            if any(marker not in surface_table for marker in markers):
                raise PatentParseError(
                    f"AAC near-eye folded embodiment {index + 1} reflected path changed"
                )
        if table_texts[4] != (
            "TABLE-US-00005 TABLE 5 Parameters and First Second Conditional Equations "
            "Embodiment Embodiment f2/f 5.19 8.93 (R1 + R2)/(R1 - R2) 1.38 4.72 "
            "R5/R6 0.94 2.73 SDmax 23.00 22.00 eyebox 12.00 12.00 TL 18.307 "
            "17.977 TTL 34.707 31.777 IH 11.500 11.200 FOV 89.94 94.95"
        ):
            raise PatentParseError("AAC near-eye folded TABLE 5 system rows changed")

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)"
            r"DETAILED DESCRIPTION OF THE EMBODIMENTS",
            text,
            re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError("AAC near-eye folded drawing description is missing")
        figures = tuple(
            int(value)
            for value in re.findall(
                r"FIG\.\s*(\d+)\s+(?:is|are)",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if figures != _AAC_NEAR_EYE_FOLDED_THREE_LENS_FIGURES:
            raise PatentParseError("AAC near-eye folded ten-figure denominator changed")

        for phrase, expected in _AAC_NEAR_EYE_FOLDED_THREE_LENS_PHRASE_COUNTS.items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"AAC near-eye folded phrase {phrase!r} occurs {observed}; "
                    f"expected {expected}"
                )
        for row in _AAC_NEAR_EYE_FOLDED_THREE_LENS_SYSTEM_ROWS:
            if len(re.findall(re.escape(row), text, re.IGNORECASE)) != 1:
                raise PatentParseError("AAC near-eye folded direct system row changed")

        numeric_required_metadata_patterns = (
            r"(?:\beffective\s+focal\s+length\b|\bEFL\b|"
            r"\bfocal\s+length\s+of\s+the\s+optical\s+system\b)\s*"
            r"(?:is|=|:)\s*[-+]?\d",
            r"\b(?:F\s*[- ]?number|FNO|F/#|aperture\s+number)\b\s*"
            r"(?:is|=|:)\s*[-+]?\d",
        )
        if any(
            re.search(pattern, text, re.IGNORECASE) is not None
            for pattern in numeric_required_metadata_patterns
        ):
            raise PatentParseError(
                "AAC near-eye folded required system metadata unexpectedly became numeric"
            )
    except Exception as exc:  # noqa: BLE001 - retain both source-declared embodiments
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="metadata_unpublished",
                reason_code=(
                    "metadata_unpublished."
                    "prescription_specific_efl_and_f_number_absent"
                ),
                detail=(
                    f"Tables {2 * index - 1}-{2 * index} publish the exact folded "
                    "surface/path prescription and R1-R6 conic/A4-A16 coefficients; "
                    "the embodiment and TABLE 5 publish direct ENPD, image height, "
                    "diagonal FOV, ratios, and track lengths, but no direct numeric "
                    "system EFL or F-number, and neither is derived from f2/f, pupil, "
                    "track length, or the repeated reflective path"
                ),
            ),
        )
        for index, embodiment in enumerate(embodiments, start=1)
    ]


def _classify_aac_telecentric_nine_lens_metadata_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain exact Family 89001540 prescriptions with source-proven gaps."""

    profile = _AAC_TELECENTRIC_NINE_LENS_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    embodiments = tuple(
        f"AAC object-space telecentric nine-lens embodiment {index}"
        for index in range(1, 8)
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"AAC telecentric nine-lens official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"AAC telecentric nine-lens normalized text hash changed for {patent_id}"
            )
        if len(_AAC_TELECENTRIC_NINE_LENS_TITLE_PATTERN.findall(text)) != 1:
            raise PatentParseError("AAC telecentric nine-lens title binding changed")
        if len(re.findall(r"Family\s+ID:\s*89001540", text, re.IGNORECASE)) != 1:
            raise PatentParseError("AAC telecentric nine-lens Family ID binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "AAC telecentric nine-lens application binding changed"
            )
        for marker in profile["relationship_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"AAC telecentric nine-lens relationship marker {marker!r} changed"
                )

        brief_match = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+DRAWINGS(?P<body>.*?)"
            r"DESCRIPTION\s+OF\s+EMBODIMENTS",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError(
                "AAC telecentric nine-lens drawing description is missing"
            )
        declared_figures = tuple(
            int(figure)
            for figure in re.findall(
                r"FIG\.\s*<b>(\d+)</b></figref>\s+is\s+",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if declared_figures != _AAC_TELECENTRIC_NINE_LENS_FIGURES:
            raise PatentParseError(
                "AAC telecentric nine-lens 28-figure denominator changed"
            )
        drawing_text = normalize_patent_text(brief_match.group("body"))
        drawing_roles = (
            len(
                re.findall(
                    r"structural\s+schematic\s+diagram",
                    drawing_text,
                    re.IGNORECASE,
                )
            ),
            len(
                re.findall(
                    r"(?:structural\s+)?schematic\s+diagram\s+of\s+(?:the\s+)?"
                    r"longitudinal\s+aberration",
                    drawing_text,
                    re.IGNORECASE,
                )
            ),
            len(
                re.findall(
                    r"schematic\s+diagram\s+of\s+lateral\s+color",
                    drawing_text,
                    re.IGNORECASE,
                )
            ),
            len(
                re.findall(
                    r"schematic\s+diagram\s+of\s+field\s+curvature\s+and\s+"
                    r"distortion",
                    drawing_text,
                    re.IGNORECASE,
                )
            ),
        )
        if drawing_roles != (8, 7, 7, 7):
            raise PatentParseError(
                f"AAC telecentric nine-lens drawing roles changed: {drawing_roles}"
            )

        for embodiment_number in range(1, 8):
            heading_pattern = (
                rf"<br\s*/>\s*Embodiment\s+{embodiment_number}\s*<br\s*/>"
            )
            if len(re.findall(heading_pattern, raw_text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    "AAC telecentric nine-lens embodiment "
                    f"{embodiment_number} heading changed"
                )
            table_binding = (
                rf"Table\s+{embodiment_number}\s+shows\s+design\s+data\s+of\s+"
                rf"(?:a|the)\s+"
                rf"camera\s+telecentric\s+lens\s+{10 * embodiment_number}\s+as\s+"
                rf"described\s+in\s+Embodiment\s+{embodiment_number}"
            )
            if len(re.findall(table_binding, text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    "AAC telecentric nine-lens embodiment "
                    f"{embodiment_number} table binding changed"
                )
        if re.search(r"<br\s*/>\s*Embodiment\s+8\s*<br\s*/>", raw_text, re.IGNORECASE):
            raise PatentParseError(
                "AAC telecentric nine-lens source gained an eighth embodiment"
            )

        blocks = _patent_table_blocks(text)
        table_numbers = tuple(block.number for block in blocks)
        if table_numbers != tuple(range(1, 9)):
            raise PatentParseError(
                "AAC telecentric nine-lens table sequence is "
                f"{table_numbers}; expected 1..8"
            )
        table_digests = tuple(
            hashlib.sha256(block.text.encode("utf-8")).hexdigest() for block in blocks
        )
        if table_digests != profile["table_block_sha256"]:
            raise PatentParseError("AAC telecentric nine-lens table digest changed")

        for table_number, block in enumerate(blocks[:7], start=1):
            expected_row_count = 2 if table_number == 1 else 1
            for lens_number in range(1, 10):
                if len(re.findall(rf"\bG{lens_number}\b", block.text)) != 1:
                    raise PatentParseError(
                        f"AAC telecentric TABLE {table_number} G{lens_number} row changed"
                    )
                for marker in (f"nd{lens_number}", f"v{lens_number}"):
                    if (
                        len(re.findall(rf"\b{marker}\b", block.text, re.IGNORECASE))
                        != expected_row_count
                    ):
                        raise PatentParseError(
                            f"AAC telecentric TABLE {table_number} {marker} row changed"
                        )
            for surface_number in range(1, 19):
                if (
                    len(re.findall(rf"\bR{surface_number}\b", block.text))
                    != expected_row_count
                ):
                    raise PatentParseError(
                        f"AAC telecentric TABLE {table_number} R{surface_number} row changed"
                    )
        if len(
            re.findall(
                re.escape(_AAC_TELECENTRIC_NINE_LENS_EFL_ROW),
                blocks[7].text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("AAC telecentric nine-lens TABLE 8 EFL row changed")

        for diameter in _AAC_TELECENTRIC_NINE_LENS_ENTRANCE_PUPIL_DIAMETERS:
            if len(re.findall(rf"entrance\s+pupil\s+diameter.*?{diameter}\s+mm", text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"AAC telecentric nine-lens entrance-pupil value {diameter} changed"
                )
        if len(
            re.findall(
                r"full\s+field\s+of\s+view\s+image\s+height\s+is\s+18\.5\s+mm",
                text,
                re.IGNORECASE,
            )
        ) != 7:
            raise PatentParseError(
                "AAC telecentric nine-lens full-field image-height denominator changed"
            )
        if len(
            re.findall(
                r"(?:the\s+)?numerical\s+aperture\s+is\s+0\.13",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "AAC telecentric nine-lens embodiment 1 numerical aperture changed"
            )
        for field in dict.fromkeys(_AAC_TELECENTRIC_NINE_LENS_DIAGONAL_FIELDS):
            observed = len(
                re.findall(
                    rf"field\s+of\s+view\s+in\s+a\s+diagonal\s+direction\s+is\s+"
                    rf"{re.escape(field)}°",
                    text,
                    re.IGNORECASE,
                )
            )
            expected = _AAC_TELECENTRIC_NINE_LENS_DIAGONAL_FIELDS.count(field)
            if observed != expected:
                raise PatentParseError(
                    f"AAC telecentric nine-lens diagonal field {field}° changed"
                )
        for phrase, expected in {
            "object-space telecentric design": 1,
            "entrance pupil is located at infinity": 1,
            "d11-BS: on-axis distance": 1,
            "dBS: on-axis thickness of the beam splitting prism BS": 1,
        }.items():
            if len(re.findall(re.escape(phrase), text, re.IGNORECASE)) != expected:
                raise PatentParseError(
                    f"AAC telecentric nine-lens phrase {phrase!r} changed"
                )

        if len(
            re.findall(
                re.escape(_AAC_TELECENTRIC_NINE_LENS_TABLE7_UNDEFINED_SPACING),
                blocks[6].text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "AAC telecentric TABLE 7 undefined d6-BS spacing chain changed"
            )
        for pattern in (
            r"\bF\s*[- ]?number\b",
            r"\bFNO\b",
            r"\bF\s*/\s*(?:#|No\.?|Number|\d)",
            r"\baperture\s+number\b",
        ):
            observed = len(re.findall(pattern, text, re.IGNORECASE))
            if observed != 0:
                raise PatentParseError(
                    f"AAC telecentric nine-lens F-number marker {pattern!r} occurs "
                    f"{observed}; expected 0"
                )
        for pattern in (
            r"\bndBS\b",
            r"\brefractive\s+index\b[^.]{0,120}\bbeam\s+splitting\s+prism\b",
            r"\bAbbe\b[^.]{0,120}\bbeam\s+splitting\s+prism\b",
        ):
            observed = len(re.findall(pattern, text, re.IGNORECASE))
            if observed != 0:
                raise PatentParseError(
                    f"AAC telecentric nine-lens prism-material marker {pattern!r} "
                    f"occurs {observed}; expected 0"
                )
    except Exception as exc:  # noqa: BLE001 - retain all seven disclosed examples
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for index, embodiment in enumerate(embodiments, start=1):
        if index == 1:
            reason_code = (
                "metadata_unpublished.beam_splitter_material_f_number_and_"
                "angular_field_absent"
            )
            detail = (
                "TABLE 1 publishes the nine-lens finite-object prescription, direct EFL, "
                "NA 0.13, and full-field image height 18.5 mm, but no beam-splitter "
                "refractive index/dispersion, exact system F-number, or angular field; "
                "NA and entrance-pupil diameter are not converted to an F-number"
            )
        elif index == 7:
            reason_code = (
                "metadata_unpublished.beam_splitter_material_f_number_and_"
                "table7_spacing_identity_absent"
            )
            detail = (
                "TABLE 7 publishes direct EFL and diagonal field, but no beam-splitter "
                "refractive index/dispersion or exact system F-number; both official HTML "
                "versions and the official A1/B2 raster pages also publish an undefined "
                "d6-BS/dBS/dBS-S1/dS1-7 chain before G4 in addition to the defined "
                "d11-BS beam-splitter chain after G6, so no row is repaired or discarded"
            )
        else:
            reason_code = (
                "metadata_unpublished.beam_splitter_material_and_f_number_absent"
            )
            detail = (
                f"TABLE {index} publishes the nine-lens finite-object prescription, "
                "direct EFL, and diagonal field, but no beam-splitter refractive "
                "index/dispersion or exact system F-number; numerical aperture and "
                "entrance-pupil diameter are not substituted or used to derive it"
            )
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=PatentTerminalParseError(
                    status="metadata_unpublished",
                    reason_code=reason_code,
                    detail=detail,
                ),
            )
        )
    return attempts


def _parse_samsung_iris_surface_table(
    table: _PatentTableBlock,
    *,
    layout: tuple[tuple[tuple[str, ...], bool], ...],
) -> tuple[list[PatentSurface], dict[str, int], set[str]]:
    """Parse one exact Family 63585563 state without renumbering source labels."""

    prefix = f"TABLE-US-{table.number:05d} TABLE {table.number} LENS SURFACE R Dn nd vd "
    if not table.text.startswith(prefix):
        raise PatentParseError(
            f"Samsung iris TABLE {table.number} surface header changed"
        )
    body = re.split(r"\s+(?:\(\d+\)|\[\d+\])\s+", table.text[len(prefix) :], maxsplit=1)[
        0
    ].strip()
    tokens = body.split()
    pos = 0
    surfaces: list[PatentSurface] = []
    index_by_source_label: dict[str, int] = {}
    aspheric_source_labels: set[str] = set()
    for label_tokens, has_material in layout:
        actual_labels = tuple(tokens[pos : pos + len(label_tokens)])
        if tuple(item.casefold() for item in actual_labels) != tuple(
            item.casefold() for item in label_tokens
        ):
            raise PatentParseError(
                f"Samsung iris TABLE {table.number} row label changed at "
                f"{' '.join(label_tokens)}"
            )
        pos += len(label_tokens)
        value_count = 4 if has_material else 2
        value_tokens = tokens[pos : pos + value_count]
        if len(value_tokens) != value_count:
            raise PatentParseError(
                f"Samsung iris TABLE {table.number} row {' '.join(label_tokens)} is incomplete"
            )
        pos += value_count
        radius = _distance_value(
            value_tokens[0],
            field_name=(
                f"Samsung iris TABLE {table.number} {' '.join(label_tokens)} radius"
            ),
        )
        thickness = _distance_value(
            value_tokens[1],
            field_name=(
                f"Samsung iris TABLE {table.number} {' '.join(label_tokens)} thickness"
            ),
        )
        if thickness is None or not math.isfinite(thickness):
            raise PatentParseError(
                f"Samsung iris TABLE {table.number} {' '.join(label_tokens)} "
                "thickness must be finite"
            )
        nd = vd = None
        if has_material:
            nd = _parse_number(value_tokens[2])
            vd = _parse_number(value_tokens[3])
            _validate_material_indices(surface_index=len(surfaces) + 1, nd=nd, vd=vd)

        raw_label = label_tokens[0].replace("*", "")
        if raw_label.casefold() == "obj":
            if radius != math.inf or thickness != 500.0 or has_material:
                raise PatentParseError(
                    f"Samsung iris TABLE {table.number} object row changed"
                )
            continue
        surface_index = len(surfaces) + 1
        if raw_label.upper() == "ST":
            label = "Stop"
        elif raw_label.upper() == "IMG":
            label = "Image"
        else:
            label = f"Surface {raw_label}"
            index_by_source_label[raw_label] = surface_index
        if any("*" in token for token in label_tokens):
            aspheric_source_labels.add(raw_label)
        surfaces.append(
            PatentSurface(
                index=surface_index,
                label=label,
                radius_mm=radius,
                thickness_mm=thickness,
                material="Glass" if nd is not None else None,
                nd=nd,
                vd=vd,
                surface_type=(
                    "ASP" if raw_label in aspheric_source_labels else None
                ),
            )
        )
    if pos != len(tokens):
        raise PatentParseError(
            f"Samsung iris TABLE {table.number} has unbound trailing surface tokens"
        )
    if sum(surface.label == "Stop" for surface in surfaces) != 1:
        raise PatentParseError(
            f"Samsung iris TABLE {table.number} must contain exactly one stop"
        )
    if not surfaces or surfaces[-1].label != "Image":
        raise PatentParseError(
            f"Samsung iris TABLE {table.number} must terminate at IMG"
        )
    return surfaces, index_by_source_label, aspheric_source_labels


def _parse_samsung_iris_first_asphere_table(
    table: _PatentTableBlock,
    *,
    index_by_source_label: dict[str, int],
) -> tuple[dict[int, dict[str, float]], tuple[str, ...]]:
    source_labels = ("1", "2", "3", "4", "6", "7", "8", "9", "10", "11")
    prefix = f"TABLE-US-{table.number:05d} TABLE {table.number} "
    if not table.text.startswith(prefix):
        raise PatentParseError("Samsung iris TABLE 3 asphere header changed")
    body = re.split(r"\s+(?:\(\d+\)|\[\d+\])\s+", table.text[len(prefix) :], maxsplit=1)[
        0
    ].strip()
    tokens = body.split()
    if tuple(tokens[: len(source_labels)]) != source_labels:
        raise PatentParseError("Samsung iris TABLE 3 surface labels changed")
    pos = len(source_labels)
    coefficients: dict[int, dict[str, float]] = {}
    for row_label in ("K", "A", "B", "C", "D", "E", "F", "G", "H"):
        if pos >= len(tokens) or tokens[pos] != row_label:
            raise PatentParseError(
                f"Samsung iris TABLE 3 coefficient row {row_label} changed"
            )
        pos += 1
        row_tokens = tokens[pos : pos + len(source_labels)]
        if len(row_tokens) != len(source_labels) or any(
            re.fullmatch(NUMBER_PATTERN, token, re.IGNORECASE) is None
            for token in row_tokens
        ):
            raise PatentParseError(
                f"Samsung iris TABLE 3 coefficient row {row_label} is incomplete"
            )
        pos += len(source_labels)
        for source_label, token in zip(source_labels, row_tokens, strict=True):
            surface_index = index_by_source_label.get(source_label)
            if surface_index is None:
                raise PatentParseError(
                    f"Samsung iris TABLE 3 references absent surface {source_label}"
                )
            coefficients.setdefault(surface_index, {})[row_label] = _parse_number(token)
    if pos != len(tokens):
        raise PatentParseError("Samsung iris TABLE 3 has unbound coefficient tokens")
    return coefficients, source_labels


def _samsung_iris_narrative_metadata(text: str) -> dict[int, tuple[float, float, float]]:
    ordinal_numbers = {"first": 1, "second": 2, "third": 3}
    pattern = re.compile(
        rf"\bIn\s+the\s+(?P<ordinal>first|second|third)\s+numerical\s+embodiment\s*,\s*"
        rf"F-number\s+is\s+(?P<fno>{NUMBER_PATTERN})\s*,\s*a\s+half\s+field\s+of\s+"
        rf"view\s+is\s+(?P<hfov>{NUMBER_PATTERN})\s*°\s*,\s*and\s+an?\s+"
        rf"(?:overall\s+)?focal\s+length\s*\(\s*f\s*\)\s+is\s+"
        rf"(?P<f>{NUMBER_PATTERN})\s*mm\s*\.",
        flags=re.IGNORECASE,
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 3:
        raise PatentParseError("Samsung iris three narrative metadata rows changed")
    metadata = {
        ordinal_numbers[match.group("ordinal").lower()]: (
            _parse_number(match.group("f")),
            _parse_number(match.group("fno")),
            _parse_number(match.group("hfov")),
        )
        for match in matches
    }
    if set(metadata) != {1, 2, 3}:
        raise PatentParseError("Samsung iris narrative embodiment mapping changed")
    return metadata


def _samsung_iris_system_rows(table: _PatentTableBlock) -> dict[int, tuple[float, ...]]:
    header = (
        "TABLE-US-00011 TABLE 11 HALF FILED OF V3 - T34/ F f1 f2 f3 f4 f5 VIEW "
        "OAL Fnumber T34 V2 f2/f OAL f.sub.IR "
    )
    if not table.text.startswith(header):
        raise PatentParseError("Samsung iris TABLE 11 flattened header changed")
    rows: dict[int, tuple[float, ...]] = {}
    row_pattern = re.compile(
        rf"\bEMBODIMENT\s+(?P<number>[1-3])\s+"
        rf"(?P<values>(?:{NUMBER_PATTERN}\s+){{13}}{NUMBER_PATTERN})(?=\s)",
        flags=re.IGNORECASE,
    )
    for match in row_pattern.finditer(table.text):
        number = int(match.group("number"))
        values = tuple(_parse_number(token) for token in match.group("values").split())
        if number in rows or len(values) != 14:
            raise PatentParseError("Samsung iris TABLE 11 row cardinality changed")
        rows[number] = values
    if set(rows) != {1, 2, 3}:
        raise PatentParseError("Samsung iris TABLE 11 embodiment rows changed")
    return rows


def _parse_samsung_iris_moving_group_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Recover only unambiguous states from exact Family 63585563 sources.

    The source declares three numerical embodiments with visible/IR lens-group
    positions, so the denominator is six state items.  TABLES 6/10 conflict
    with the surface numbering, TABLE 7 repeats the conic row label, TABLE 8
    prints a nonnumeric radius, and embodiment 3's narrative/TABLE 11 system
    values disagree.  Those source defects remain parser failures.
    """

    profile = _SAMSUNG_IRIS_MOVING_GROUP_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=label,
                error=exc,
            )
            for index, label in enumerate(_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"Samsung iris official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"Samsung iris normalized text hash changed for {patent_id}"
            )
        if len(_SAMSUNG_IRIS_MOVING_GROUP_TITLE_PATTERN.findall(text)) != 1:
            raise PatentParseError("Samsung iris title binding changed")
        if len(re.findall(r"Family\s+ID:\s*63585563", text, re.IGNORECASE)) != 1:
            raise PatentParseError("Samsung iris Family ID binding changed")
        if len(
            re.findall(
                r"Samsung\s+Electronics\s+Co\.\s*,\s*Ltd\.",
                text,
                re.IGNORECASE,
            )
        ) < 1:
            raise PatentParseError("Samsung iris owner binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("Samsung iris application binding changed")
        for marker in profile["relationship_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"Samsung iris relationship marker {marker!r} changed"
                )

        drawings = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+DRAWINGS(?P<body>.*?)MODE\s+OF\s+DISCLOSURE",
            text,
            re.IGNORECASE,
        )
        if drawings is None:
            raise PatentParseError("Samsung iris drawing description is missing")
        declared_figures = tuple(
            int(number)
            for number in re.findall(
                r"\bFIG\.\s*([1-9]\d*)\s+(?:illustrates|is)\b",
                drawings.group("body"),
                re.IGNORECASE,
            )
        )
        if declared_figures != _SAMSUNG_IRIS_MOVING_GROUP_FIGURES:
            raise PatentParseError("Samsung iris 18-figure denominator changed")
        headings = tuple(
            ordinal.lower()
            for ordinal in re.findall(
                r"\b(First|Second|Third)\s+Numerical\s+Embodiment\s+"
                r"(?=\(\d+\)|\[\d+\])",
                text,
                re.IGNORECASE,
            )
        )
        if headings != ("first", "second", "third"):
            raise PatentParseError("Samsung iris numerical-embodiment denominator changed")

        blocks = _patent_table_blocks(text)
        table_numbers = tuple(block.number for block in blocks)
        if table_numbers != tuple(range(1, 12)):
            raise PatentParseError(
                f"Samsung iris table sequence is {table_numbers}; expected 1..11"
            )
        table_digests = tuple(
            hashlib.sha256(block.text.encode("utf-8")).hexdigest() for block in blocks
        )
        if table_digests != profile["table_block_sha256"]:
            raise PatentParseError("Samsung iris table digest changed")
        if len(
            re.findall(
                r"K\s+denotes\s+a\s+conic\s+constant\s*,\s*A\s*,\s*B\s*,\s*C\s*,\s*"
                r"and\s+D\s+denote\s+aspherical\s+coefficients",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("Samsung iris asphere convention changed")

        narrative_metadata = _samsung_iris_narrative_metadata(text)
        system_rows = _samsung_iris_system_rows(blocks[10])
        first_f, first_fno, first_hfov = narrative_metadata[1]
        first_system = system_rows[1]
        rounded_hfov = math.floor(first_hfov + 0.5)
        if (
            first_f != first_system[0]
            or first_fno != first_system[8]
            or rounded_hfov != first_system[6]
        ):
            raise PatentParseError(
                "Samsung iris embodiment 1 narrative and TABLE 11 metadata disagree"
            )

        visible_surfaces, visible_indices, visible_aspheres = (
            _parse_samsung_iris_surface_table(
                blocks[0],
                layout=_SAMSUNG_IRIS_FIRST_VISIBLE_LAYOUT,
            )
        )
        visible_coefficients, table3_labels = _parse_samsung_iris_first_asphere_table(
            blocks[2],
            index_by_source_label=visible_indices,
        )
        if visible_aspheres != set(table3_labels):
            raise PatentParseError(
                "Samsung iris TABLE 1 stars and TABLE 3 surface labels disagree"
            )
        ir_surfaces, ir_indices, ir_aspheres = _parse_samsung_iris_surface_table(
            blocks[1],
            layout=_SAMSUNG_IRIS_FIRST_IR_LAYOUT,
        )
        ir_coefficients, ir_table3_labels = _parse_samsung_iris_first_asphere_table(
            blocks[2],
            index_by_source_label=ir_indices,
        )
        if ir_aspheres != set(ir_table3_labels):
            raise PatentParseError(
                "Samsung iris TABLE 2 stars and TABLE 3 surface labels disagree"
            )
        for surfaces, coefficients in (
            (visible_surfaces, visible_coefficients),
            (ir_surfaces, ir_coefficients),
        ):
            for surface in surfaces:
                values = coefficients.get(surface.index)
                if values is not None:
                    surface.asphere_coefficients.update(values)
                    surface.surface_type = "ASP"

        # These exact defects are source facts, not inferred repairs.  Keeping
        # the assertions makes any future corrected publication reopen parsing.
        if re.search(
            r"\ATABLE-US-00006\s+TABLE\s+6\s+1\s+2\s+3\s+4\s+5\s+6\s+7\s+8\s+9\s+10\s+K\s+",
            blocks[5].text,
        ) is None:
            raise PatentParseError("Samsung iris TABLE 6 conflict signature changed")
        table7_labels = tuple(
            re.findall(r"(?<!\S)(K|A|B|C|D|E|F|G|H)(?=\s)", blocks[6].text)
        )
        if table7_labels != ("K", "A", "B", "C", "D", "E", "F", "G", "H", "K"):
            raise PatentParseError("Samsung iris TABLE 7 duplicate-K signature changed")
        if len(re.findall(r"(?<!\S)1\.530f377(?=\s)", blocks[7].text)) != 1:
            raise PatentParseError("Samsung iris TABLE 8 damaged-radius signature changed")
        if re.search(
            r"\ATABLE-US-00010\s+TABLE\s+10\s+1\s+2\s+3\s+4\s+5\s+6\s+7\s+8\s+9\s+10\s+K\s+",
            blocks[9].text,
        ) is None:
            raise PatentParseError("Samsung iris TABLE 10 conflict signature changed")
        third_f, third_fno, third_hfov = narrative_metadata[3]
        third_system = system_rows[3]
        if (third_f, third_fno, third_hfov) == (
            third_system[0],
            third_system[8],
            third_system[6],
        ):
            raise PatentParseError(
                "Samsung iris embodiment 3 metadata conflict unexpectedly disappeared"
            )

        visible = PatentPrescription(
            patent_id=patent_id,
            embodiment=_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS[0],
            focal_length_mm=first_f,
            f_number=first_fno,
            hfov_deg=first_hfov,
            surfaces=visible_surfaces,
        )
        ir = PatentPrescription(
            patent_id=patent_id,
            embodiment=_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS[1],
            focal_length_mm=first_f,
            f_number=first_fno,
            hfov_deg=first_hfov,
            surfaces=ir_surfaces,
            reference_wavelength_um=0.82,
        )
        _validate_prescription_materials(visible)
        _validate_prescription_materials(ir)
    except Exception as exc:  # noqa: BLE001 - retain all six disclosed state items
        return attempts_for_error(exc)

    source_errors = (
        PatentParseError(
            "Samsung iris embodiment 2 visible state source conflict: TABLE 6 labels "
            "asphere columns 1-10 although TABLE 4 uses ST between surfaces 4 and 6"
        ),
        PatentParseError(
            "Samsung iris embodiment 2 IR state source conflict: TABLE 6 surface labels "
            "are inconsistent and TABLE 7 publishes duplicate K rows for surfaces 7-2/7-3"
        ),
        PatentParseError(
            "Samsung iris embodiment 3 visible state source conflict: TABLE 8 radius "
            "1.530f377 is nonnumeric, TABLE 10 surface labels are inconsistent, and "
            "narrative/TABLE 11 system metadata disagree"
        ),
        PatentParseError(
            "Samsung iris embodiment 3 IR state source conflict: TABLE 10 labels "
            "asphere columns 1-10 although TABLE 9 uses ST between surfaces 4 and 6, "
            "and narrative/TABLE 11 system metadata disagree"
        ),
    )
    return [
        _PrescriptionParseAttempt(
            embodiment_number=1,
            embodiment=_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS[0],
            prescription=visible,
        ),
        _PrescriptionParseAttempt(
            embodiment_number=2,
            embodiment=_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS[1],
            prescription=ir,
        ),
        *[
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=_SAMSUNG_IRIS_MOVING_GROUP_ITEM_LABELS[index - 1],
                error=error,
            )
            for index, error in enumerate(source_errors, start=3)
        ],
    ]


def _classify_meta_optical_layer_architecture_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify exact Family 85199256 meta-layer/device disclosures.

    The retained HTML and image-only official PDFs disclose meta-structure layer
    stacks, simulated transmittance, a meta-lens phase profile, and electronic
    device blocks.  They publish no ordered refractive-surface prescription.
    """

    profile = _META_OPTICAL_LAYER_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []
    embodiment = "meta-optical layer and electronic-device architecture"
    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"meta-optical architecture official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"meta-optical architecture normalized text hash changed for {patent_id}"
            )
        if len(_META_OPTICAL_LAYER_ARCHITECTURE_ONLY_TITLE_PATTERN.findall(text)) != 1:
            raise PatentParseError("meta-optical architecture title binding changed")
        if len(re.findall(r"Family\s+ID:\s*85199256", text, re.IGNORECASE)) != 1:
            raise PatentParseError("meta-optical architecture Family ID binding changed")
        if (
            len(
                re.findall(
                    r"Samsung\s+Electronics\s+Co\.,?\s*Ltd\.",
                    text,
                    re.IGNORECASE,
                )
            )
            != 2
        ):
            raise PatentParseError("meta-optical architecture owner binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if (
            len(
                re.findall(
                    rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                    text,
                    re.IGNORECASE,
                )
            )
            != 1
        ):
            raise PatentParseError("meta-optical architecture application binding changed")
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"meta-optical architecture relationship marker {marker!r} occurs "
                    f"{observed}; expected 1"
                )

        if _patent_table_blocks(text) or re.search(r"TABLE-US-", raw_text):
            raise PatentParseError(
                "meta-optical architecture unexpectedly contains a PPUBS table"
            )
        numbered_headings = re.findall(
            r"\b(?:EXAMPLE|NUMERICAL\s+EMBODIMENT)\s+(?:No\.\s*)?\d+\b",
            text,
            re.IGNORECASE,
        )
        if numbered_headings:
            raise PatentParseError(
                "meta-optical architecture numbered example denominator changed"
            )

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)DETAILED DESCRIPTION",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError("meta-optical architecture drawing description is missing")
        drawing_refs = tuple(
            (figure, panel.upper())
            for figure, panel in re.findall(
                r"FIG\.\s*<b>(\d+)</b>([A-B]?)</figref>\s+"
                r"(?:is\s+|exemplarily\s+illustrates\s+)",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if drawing_refs != _META_OPTICAL_LAYER_ARCHITECTURE_ONLY_DRAWINGS:
            raise PatentParseError(
                "meta-optical architecture 24-panel drawing denominator changed"
            )
        drawing_text = normalize_patent_text(brief_match.group("body"))
        if re.search(
            r"\b(?:prescription|optical\s+data|lens\s+data|"
            r"radius\s+of\s+curvature|curvature\s+radius|Abbe|"
            r"Surface\s+(?:No\.?|#|Number))\b",
            drawing_text,
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "meta-optical architecture drawing descriptions reference prescription data"
            )

        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"meta-optical architecture phrase {phrase!r} occurs {observed}; "
                    f"expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\bAbbe\s+(?:number|#)?\b|\bSurface\s+(?:No\.?|#|Number)\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\blens\s+data\b|\bprescription\b|"
            rf"\bfocal\s+lengths?\s*(?:=|:)\s*{NUMBER_PATTERN})",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "meta-optical architecture disclosure contains a prescription marker"
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
                    "meta_optical_layer_and_device_architecture_only"
                ),
                detail=(
                    "the exact retained official disclosure and its 24-panel raster "
                    "drawing set publish meta-structure layers, simulated transmittance, "
                    "a meta-lens phase profile, and electronic-device blocks but no "
                    "ordered optical surface prescription or prescription table"
                ),
            ),
        )
    ]


def _classify_edof_microscope_examples_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify all five source-declared examples in exact Family 60001556.

    Example III publishes an ordered, spherical surface prescription in TABLE 1,
    but no direct numeric EFL, F-number, or angular field for that prescription.
    The other examples disclose analysis, architecture, or experimental results
    without an independent ordered surface prescription.
    """

    profile = _EDOF_MICROSCOPE_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(_EDOF_MICROSCOPE_ITEM_LABELS, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"EDOF microscope official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"EDOF microscope normalized text hash changed for {patent_id}"
            )
        if len(_EDOF_MICROSCOPE_SOURCE_TITLE_PATTERN.findall(text)) != 1:
            raise PatentParseError("EDOF microscope title binding changed")
        if len(re.findall(r"Family\s+ID:\s*60001556", text, re.IGNORECASE)) != 1:
            raise PatentParseError("EDOF microscope Family ID binding changed")
        owner = "Arizona Board of Regents on Behalf of the University of Arizona"
        if len(re.findall(re.escape(owner), text, re.IGNORECASE)) != profile["owner_count"]:
            raise PatentParseError("EDOF microscope owner binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("EDOF microscope application binding changed")
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"EDOF microscope relationship marker {marker!r} occurs "
                    f"{observed}; expected 1"
                )

        headings = tuple(
            normalize_patent_text(match)
            for match in re.findall(
                r"Example\s+[IVX]+:\s+[^<\r\n]+",
                raw_text,
                re.IGNORECASE,
            )
        )
        if headings != _EDOF_MICROSCOPE_EXAMPLE_HEADINGS:
            raise PatentParseError("EDOF microscope five-example denominator changed")

        table_ids = tuple(re.findall(r"TABLE-US-(\d+)", raw_text, re.IGNORECASE))
        if table_ids != ("00001",):
            raise PatentParseError("EDOF microscope one-table denominator changed")
        table_match = re.search(
            r"TABLE-US-00001(?P<body>.*?)<br\s*/?>",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if table_match is None:
            raise PatentParseError("EDOF microscope TABLE 1 body is missing")
        table_text = normalize_patent_text(
            "TABLE-US-00001" + table_match.group("body")
        )
        table_digest = hashlib.sha256(table_text.encode("utf-8")).hexdigest()
        if table_digest != profile["table_sha256"]:
            raise PatentParseError("EDOF microscope TABLE 1 digest changed")
        if not table_text.startswith(
            "TABLE-US-00001 TABLE 1 Semi- Radius Thickness Diameter Surface Comment "
            "[mm] [mm] Material [mm]"
        ):
            raise PatentParseError("EDOF microscope TABLE 1 column binding changed")
        for row in (
            "Focusing plane Infinity 2.5000 1.0000",
            "Adaptive surface (EL- Infinity 1.9818 OL1024_UV_VIS_NIR 5.0000",
            "Imaging plane Infinity 0.0000 2.0769",
        ):
            if len(re.findall(re.escape(row), table_text, re.IGNORECASE)) != 1:
                raise PatentParseError(f"EDOF microscope TABLE 1 row {row!r} changed")

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)DETAILED DESCRIPTION",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError("EDOF microscope drawing description is missing")
        figure_expressions = tuple(
            re.findall(
                r"(?:\(\d+\)|\[\d+\])\s+FIGS?\.\s+"
                r"([0-9A-F]+(?:\s*(?:,|and|through|-)\s*[0-9A-F]+)*)\s+"
                r"(?:(?:schematically|exemplarily)\s+)?"
                r"(?:is|are|show|shows|illustrate|illustrates|demonstrate)",
                normalize_patent_text(brief_match.group("body")),
                re.IGNORECASE,
            )
        )
        if figure_expressions != _EDOF_MICROSCOPE_FIGURE_EXPRESSIONS:
            raise PatentParseError(
                "EDOF microscope 42-number/72-panel drawing denominator changed"
            )

        for phrase, expected in profile["phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"EDOF microscope phrase {phrase!r} occurs {observed}; "
                    f"expected {expected}"
                )

        numeric_required_metadata_patterns = (
            r"\beffective\s+focal\s+length\s*(?:=|:)\s*[-+]?\d",
            r"\b(?:F\s*[- ]?number|FNO|F/#|aperture\s+number)\s*"
            r"(?:=|:)\s*[-+]?\d",
            r"\b(?:HFOV|half\s+field\s+of\s+view|angular\s+field\s+of\s+view)\s*"
            r"(?:=|:)\s*[-+]?\d",
        )
        if any(
            re.search(pattern, text, re.IGNORECASE) is not None
            for pattern in numeric_required_metadata_patterns
        ):
            raise PatentParseError(
                "EDOF microscope required system metadata unexpectedly became numeric"
            )
    except Exception as exc:  # noqa: BLE001 - retain all five source-declared items
        return attempts_for_error(exc)

    outcomes = (
        (
            "confirmed_no_prescription",
            "confirmed_no_prescription.theoretical_imaging_analysis_only",
            "Example I publishes theoretical EDOF imaging analysis without an ordered "
            "optical surface prescription",
        ),
        (
            "confirmed_no_prescription",
            "confirmed_no_prescription.edof_microscope_architecture_only",
            "Example II publishes an infinity-corrected EDOF microscope implementation "
            "and performance targets but no ordered optical surface prescription",
        ),
        (
            "metadata_unpublished",
            "metadata_unpublished."
            "prescription_specific_efl_f_number_and_angular_field_absent",
            "Example III TABLE 1 publishes the ordered spherical surface prescription, "
            "materials, clear diameters, stop, and wavelength context, but no direct "
            "numeric EFL, F-number, or angular field bound to that prescription",
        ),
        (
            "confirmed_no_prescription",
            "confirmed_no_prescription.metrology_results_only",
            "Example IV publishes EDOF microdeflectometry results without an independent "
            "ordered optical surface prescription",
        ),
        (
            "confirmed_no_prescription",
            "confirmed_no_prescription.microscopy_experimental_results_only",
            "Example V publishes structured-illumination microscopy results without an "
            "independent ordered optical surface prescription",
        ),
    )
    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status=status,
                reason_code=reason_code,
                detail=detail,
            ),
        )
        for index, (embodiment, (status, reason_code, detail)) in enumerate(
            zip(_EDOF_MICROSCOPE_ITEM_LABELS, outcomes, strict=True),
            start=1,
        )
    ]


def _classify_deformable_lens_actuator_architecture_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify the exact Family 39526858 actuator/terminal disclosure.

    The one formal Example 1 benchmarks a deformable focus apparatus fitted to
    a third-party IT5000 lens triplet.  Its focal length and F-number describe
    that external assembly; neither the example nor the remaining architecture,
    material, force-response, and control tables publish an ordered surface
    prescription.
    """

    profile = _DEFORMABLE_LENS_ACTUATOR_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    embodiment = _DEFORMABLE_LENS_ACTUATOR_ITEM_LABEL
    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"deformable-lens actuator official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"deformable-lens actuator normalized text hash changed for {patent_id}"
            )
        if len(_DEFORMABLE_LENS_ACTUATOR_TITLE_PATTERN.findall(raw_text)) != 1:
            raise PatentParseError("deformable-lens actuator title binding changed")
        if len(re.findall(r"Family\s+ID:\s*39526858", text, re.IGNORECASE)) != 1:
            raise PatentParseError("deformable-lens actuator Family ID binding changed")

        owner = "Hand Held Products, Inc."
        if len(re.findall(re.escape(owner), text, re.IGNORECASE)) != profile[
            "owner_count"
        ]:
            raise PatentParseError("deformable-lens actuator owner binding changed")
        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("deformable-lens actuator application binding changed")
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"deformable-lens actuator relationship marker {marker!r} occurs "
                    f"{observed}; expected 1"
                )

        formal_examples = tuple(
            re.findall(r"(?<!End of )\bEXAMPLE\s+(\d+)\b", text, re.IGNORECASE)
        )
        if formal_examples != ("1",):
            raise PatentParseError(
                "deformable-lens actuator one-formal-example denominator changed"
            )
        if len(re.findall(r"\bEnd of Example 1\b", text, re.IGNORECASE)) != 1:
            raise PatentParseError("deformable-lens actuator Example 1 boundary changed")
        if len(re.findall(r"\bexamples?\b", text, re.IGNORECASE)) != 24:
            raise PatentParseError(
                "deformable-lens actuator example-word accounting changed"
            )

        table_ids = tuple(re.findall(r"TABLE-US-(\d+)", raw_text, re.IGNORECASE))
        if table_ids != ("00001", "00002", "00003", "00004"):
            raise PatentParseError(
                "deformable-lens actuator four-table denominator changed"
            )
        table_texts: list[str] = []
        for table_id in table_ids:
            match = re.search(
                rf"TABLE-US-{table_id}(?P<body>.*?)<br\s*/?>",
                raw_text,
                re.DOTALL | re.IGNORECASE,
            )
            if match is None:
                raise PatentParseError(
                    f"deformable-lens actuator TABLE-US-{table_id} body is missing"
                )
            table_texts.append(
                normalize_patent_text(f"TABLE-US-{table_id}" + match.group("body"))
            )
        table_digests = tuple(
            hashlib.sha256(table_text.encode("utf-8")).hexdigest()
            for table_text in table_texts
        )
        if table_digests != profile["table_block_sha256"]:
            raise PatentParseError("deformable-lens actuator table digest changed")
        table_prefixes = (
            "TABLE-US-00001 TABLE A Example Material and Sample Characteristics",
            "TABLE-US-00002 TABLE B",
            "TABLE-US-00003 TABLE C VOLTAGE DISTANCE MOVEMENT OF ACTUATOR BEST FOCUS",
            "TABLE-US-00004 TABLE D Configuration Exposure Period and Lens Setting Coordination",
        )
        if any(
            not table_text.startswith(prefix)
            for table_text, prefix in zip(table_texts, table_prefixes, strict=True)
        ):
            raise PatentParseError("deformable-lens actuator table-role binding changed")

        brief_match = re.search(
            r"DETAILED DESCRIPTION OF THE DRAWINGS(?P<body>.*?)"
            r"DETAILED DESCRIPTION(?:<|\s)",
            raw_text,
            re.DOTALL | re.IGNORECASE,
        )
        if brief_match is None:
            raise PatentParseError("deformable-lens actuator drawing description is missing")
        drawing_text = normalize_patent_text(brief_match.group("body"))
        drawing_rows = tuple(
            re.findall(
                r"(?:\[\d+\]|\(\d+\))\s+(FIGS?\..*?)"
                r"(?=(?:\[\d+\]|\(\d+\))\s+FIG|$)",
                drawing_text,
                re.IGNORECASE,
            )
        )
        drawing_declarations: list[str] = []
        for row in drawing_rows:
            declaration_match = re.match(
                r"(FIGS?\.\s+\d+(?:\s+and\s+FIG\.\s+\d+|-\d+)?)\s+"
                r"(?:is|are)",
                row,
                re.IGNORECASE,
            )
            if declaration_match is None:
                raise PatentParseError(
                    "deformable-lens actuator drawing declaration syntax changed"
                )
            drawing_declarations.append(declaration_match.group(1))
        if tuple(drawing_declarations) != _DEFORMABLE_LENS_ACTUATOR_DRAWINGS:
            raise PatentParseError(
                "deformable-lens actuator 28-figure denominator changed"
            )

        for phrase, expected in profile["phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"deformable-lens actuator phrase {phrase!r} occurs {observed}; "
                    f"expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\bAbbe(?:\s+(?:number|#))?\b|"
            r"\bSurface\s+(?:No\.?|#|Number)\s*\d+\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\boptical\s+(?:surface\s+)?(?:prescription|data)\b|"
            r"\blens\s+(?:prescription|data)\b)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "deformable-lens actuator disclosure contains a surface-prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain exact-source structural drift
        return [
            _PrescriptionParseAttempt(
                embodiment_number=1,
                embodiment=embodiment,
                error=exc,
            )
        ]

    return [
        _PrescriptionParseAttempt(
            embodiment_number=1,
            embodiment=embodiment,
            error=PatentTerminalParseError(
                status="confirmed_no_prescription",
                reason_code=(
                    "confirmed_no_prescription."
                    "deformable_lens_actuator_and_imaging_terminal_architecture_only"
                ),
                detail=(
                    "the exact retained disclosure has one formal Example 1 and four "
                    "lettered tables covering materials, force profiles, fitted-actuator "
                    "focus response, and lens-setting control; the published 5.88 mm "
                    "focal length and F# 6.6 belong to the external IT5000 lens triplet, "
                    "and neither it nor the 28 component/control figures supplies an "
                    "ordered optical surface prescription"
                ),
            ),
        )
    ]


def _classify_catadioptric_module_architecture_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify the nine source-declared items in exact Family 88236580 records.

    Embodiments 1-4 publish six thin-film stack examples plus module-level D/FNO/FOV
    values, but no optical surface prescription. Embodiments 5-7 publish only
    smartphone, multi-camera/TOF/folded-light, and vehicle camera architecture.
    """

    profile = _CATADIOPTRIC_MODULE_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiments = tuple(
        f"Catadioptric thin-film example {example} of embodiment {embodiment}"
        for example, embodiment, _table, _system_table in _CATADIOPTRIC_MODULE_EXAMPLES
    ) + (
        "Multi-camera smartphone architecture embodiment 5",
        "Multi-camera TOF and folded-light architecture embodiment 6",
        "Vehicle camera-module architecture embodiment 7",
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"catadioptric module official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"catadioptric module normalized text hash changed for {patent_id}"
            )
        if _CATADIOPTRIC_MODULE_ARCHITECTURE_ONLY_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("catadioptric module title binding changed")
        if len(re.findall(r"Family\s+ID:\s*88236580", text, re.IGNORECASE)) != 1:
            raise PatentParseError("catadioptric module Family ID binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("catadioptric module application binding changed")
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"catadioptric module relationship marker {marker!r} occurs "
                    f"{observed}; expected 1"
                )

        for marker in profile["heading_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"catadioptric module heading {marker!r} changed"
                )
        example_pairs = {
            (int(example), int(embodiment))
            for example, embodiment in re.findall(
                r"\b(\d+)(?:st|nd|rd|th)\s+example\s+of\s+the\s+"
                r"(\d+)(?:st|nd|rd|th)\s+embodiment\b",
                text,
                re.IGNORECASE,
            )
        }
        expected_examples = {
            (example, embodiment)
            for example, embodiment, _table, _system_table in _CATADIOPTRIC_MODULE_EXAMPLES
        }
        if example_pairs != expected_examples:
            raise PatentParseError("catadioptric module example denominator changed")

        blocks = _suffixed_patent_table_blocks(text)
        if tuple(blocks) != _CATADIOPTRIC_MODULE_TABLE_KEYS:
            raise PatentParseError("catadioptric module table denominator changed")
        table_digests = tuple(
            hashlib.sha256(blocks[key].encode("utf-8")).hexdigest() for key in blocks
        )
        if table_digests != profile["table_block_sha256"]:
            raise PatentParseError("catadioptric module table digest changed")
        for example, embodiment, table, _system_table in _CATADIOPTRIC_MODULE_EXAMPLES:
            example_ordinal = {1: "1st", 2: "2nd", 3: "3rd"}[example]
            embodiment_ordinal = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}[
                embodiment
            ]
            marker = (
                f"TABLE {table} the {example_ordinal} example of the "
                f"{embodiment_ordinal} embodiment thin film material "
                "refractive index"
            )
            if len(re.findall(re.escape(marker), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"catadioptric module thin-film TABLE {table} binding changed"
                )
        for row, expected in _CATADIOPTRIC_MODULE_SYSTEM_ROWS.items():
            observed = len(re.findall(re.escape(row), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"catadioptric module system row {row!r} occurs {observed}; "
                    f"expected {expected}"
                )

        brief_match = re.search(
            r"BRIEF DESCRIPTION OF THE DRAWINGS(?P<body>.*?)"
            r"DETAILED DESCRIPTION<br\s*/?>",
            raw_text,
            re.DOTALL,
        )
        if brief_match is None:
            raise PatentParseError("catadioptric module drawing description is missing")
        drawing_refs = tuple(
            (figure, panel.upper())
            for figure, panel in re.findall(
                r"FIG\.\s*<b>([1-7])</b>([A-E]?)</figref>\s+is\s+",
                brief_match.group("body"),
                re.IGNORECASE,
            )
        )
        if drawing_refs != _CATADIOPTRIC_MODULE_DRAWINGS:
            raise PatentParseError("catadioptric module 18-drawing denominator changed")
        drawing_text = normalize_patent_text(brief_match.group("body"))
        if re.search(
            r"\b(?:table|prescription|optical\s+data|lens\s+data|radius|Abbe|FNO|FOV)\b",
            drawing_text,
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "catadioptric module drawing descriptions reference prescription data"
            )

        exact_count_markers = {
            r"\baspheric(?:al)?\b": 3,
            r"\brefractive\s+index\b": 10,
            r"\bfocal\s+lengths\b": 1,
            r"40\s+degrees\s*<\s*θ\s*<\s*90\s+degrees": 1,
        }
        for pattern, expected in exact_count_markers.items():
            observed = len(re.findall(pattern, text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"catadioptric module marker {pattern!r} occurs {observed}; "
                    f"expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\bAbbe\s+(?:number|#)?\b|\bSurface\s+(?:No\.?|#|Number)\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\blens\s+data\b|\bprescription\b|"
            rf"\bfocal\s+lengths?\s*(?:=|:)\s*{NUMBER_PATTERN})",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "catadioptric module disclosure contains a surface-prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain all nine source-declared items
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for index, embodiment in enumerate(embodiments, start=1):
        thin_film_example = index <= len(_CATADIOPTRIC_MODULE_EXAMPLES)
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=PatentTerminalParseError(
                    status="confirmed_no_prescription",
                    reason_code=(
                        "confirmed_no_prescription."
                        "catadioptric_thin_film_and_module_architecture_only"
                        if thin_film_example
                        else (
                            "confirmed_no_prescription."
                            "camera_module_device_architecture_only"
                        )
                    ),
                    detail=(
                        "the source publishes a light-eliminating thin-film stack and "
                        "module-level D/FNO/FOV values, but no ordered optical surface "
                        "prescription"
                        if thin_film_example
                        else (
                            f"{embodiment} publishes only camera-module placement, sensor, "
                            "device, capture, TOF, folded-light, or vehicle architecture; "
                            "it has no optical surface prescription"
                        )
                    ),
                ),
            )
        )
    return attempts


def _classify_compact_barcode_telephoto_architecture_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify the exact Family 84363056 four-lens architecture disclosure.

    Both same-application publications disclose one document-scoped telephoto
    architecture with material classes, refractive indices, Abbe values, EFL,
    field, aperture, and total length.  They publish no radii, axial surface
    spacing, conic constants, or asphere coefficients, so no prescription can
    be built.  Any source or denominator drift remains a parser failure.
    """

    profile = _COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []
    embodiment = "Compact long-range barcode telephoto architecture"
    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"compact barcode telephoto official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                "compact barcode telephoto normalized text hash changed "
                f"for {patent_id}"
            )
        if (
            _COMPACT_BARCODE_TELEPHOTO_ARCHITECTURE_ONLY_TITLE_PATTERN.search(text)
            is None
        ):
            raise PatentParseError("compact barcode telephoto title binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("compact barcode telephoto application binding changed")
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    "compact barcode telephoto relationship marker "
                    f"{marker!r} occurs {observed}; expected 1"
                )

        if _patent_table_blocks(text) or re.search(
            r"TABLE-US-\d+", text, re.IGNORECASE
        ):
            raise PatentParseError("compact barcode telephoto source gained a PPUBS table")

        drawings = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+THE\s+DRAWINGS\s+"
            r"(?:\(\d+\)|\[\d+\])(?P<body>.*?)"
            r"DETAILED\s+DESCRIPTION\s+(?:\(\d+\)|\[\d+\])",
            text,
            re.IGNORECASE,
        )
        if drawings is None:
            raise PatentParseError(
                "compact barcode telephoto drawing denominator is missing"
            )
        drawing_numbers = re.findall(
            r"\bFIG\.\s*([1-5])\s+illustrates\s+",
            drawings.group("body"),
            re.IGNORECASE,
        )
        if drawing_numbers != ["1", "2", "3", "4", "5"]:
            raise PatentParseError(
                "compact barcode telephoto five-drawing denominator changed"
            )
        if re.search(
            r"\b(?:table|prescription|optical\s+data|lens\s+data)\b",
            drawings.group("body"),
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "compact barcode telephoto drawings now reference prescription data"
            )

        if len(
            re.findall(
                r"DETAILED\s+DESCRIPTION\s+(?:\(\d+\)|\[\d+\])",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "compact barcode telephoto detailed-section denominator changed"
            )
        if re.search(
            r"(?:\(\d+\)|\[\d+\])\s+(?:EXAMPLE|EMBODIMENT)\s+"
            r"(?:[1-9]\d*|[IVX]+)\b|"
            r"\b[1-9]\d*(?:st|nd|rd|th)\s+(?:example|embodiment)\b",
            text,
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "compact barcode telephoto formal item denominator changed"
            )
        independent_claims = re.findall(
            r"\b(\d+)\s*\.\s+An\s+imaging\s+engine\s+for\s+decoding\s+barcodes",
            text,
            re.IGNORECASE,
        )
        if independent_claims != ["1", "11"]:
            raise PatentParseError(
                "compact barcode telephoto independent-claim denominator changed"
            )

        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"compact barcode telephoto phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        for phrase in _COMPACT_BARCODE_TELEPHOTO_MATERIAL_ANCHORS:
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"compact barcode telephoto material anchor {phrase!r} occurs "
                    f"{observed}; expected 1"
                )
        for phrase in _COMPACT_BARCODE_TELEPHOTO_SYSTEM_VALUE_ANCHORS:
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    f"compact barcode telephoto system anchor {phrase!r} occurs "
                    f"{observed}; expected 1"
                )

        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\bsurface\s+radii\b|"
            r"\baspher(?:e|ic|ical)\s+(?:surface\s+)?"
            r"(?:data|coefficients?|parameters?)\b|"
            r"\bconic\s+(?:constant|coefficient)\b|"
            r"\b(?:axial|surface)\s+(?:air\s+)?spacings?\b|"
            r"\bSurface\s+(?:No\.|#)\s*|\bFno\b|\bF\s*[- ]?number\b|"
            r"\boptical\s+data\b|\blens\s+data\b|\bprescription\b)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "compact barcode telephoto disclosure contains a prescription marker"
            )
        error: Exception = PatentTerminalParseError(
            status="confirmed_no_prescription",
            reason_code=(
                "confirmed_no_prescription."
                "compact_barcode_telephoto_architecture_only"
            ),
            detail=(
                "the source publishes a four-lens material/index/Abbe architecture and "
                "system EFL, field, aperture, and total-length values, but no surface "
                "radii, axial spacings, conic constants, or asphere coefficients"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - retain the exact document-scoped item
        error = exc
    return [
        _PrescriptionParseAttempt(
            embodiment_number=1,
            embodiment=embodiment,
            error=error,
        )
    ]


def _classify_shiftable_image_sensor_wire_geometry_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify the six exact Family 86764397 source-declared items.

    The first embodiment publishes three conductive-wire/elastic-connector
    geometry examples.  Embodiments 2-4 publish smartphone, multi-camera/TOF,
    folded-light, and vehicle camera placement architecture only.  The exact
    official PPUBS sources and their 15-sheet official rasters publish no
    optical surface prescription.  Source drift remains a parser failure.
    """

    profile = _SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_ONLY_SOURCE_PROFILES.get(
        patent_id.upper()
    )
    if profile is None:
        return []

    embodiments = (
        "Shiftable image-sensor wire geometry example 1",
        "Shiftable image-sensor wire geometry example 2",
        "Shiftable image-sensor wire geometry example 3",
        "Multi-camera smartphone architecture embodiment 2",
        "Multi-camera TOF and folded-light architecture embodiment 3",
        "Vehicle camera-module architecture embodiment 4",
    )

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=exc,
            )
            for index, embodiment in enumerate(embodiments, start=1)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                "shiftable image-sensor wire official raw text hash changed "
                f"for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                "shiftable image-sensor wire normalized text hash changed "
                f"for {patent_id}"
            )
        if _SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_ONLY_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("shiftable image-sensor wire title binding changed")

        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "shiftable image-sensor wire application binding changed"
            )
        for marker in profile["relationship_markers"]:
            observed = len(re.findall(re.escape(str(marker)), text, re.IGNORECASE))
            if observed != 1:
                raise PatentParseError(
                    "shiftable image-sensor wire relationship marker "
                    f"{marker!r} occurs {observed}; expected 1"
                )

        heading_matches = re.findall(
            r"\b([1-9]\d*)(?:st|nd|rd|th)\s+Embodiment\s+"
            r"(?:\(\d+\)|\[\d+\])",
            text,
            re.IGNORECASE,
        )
        if heading_matches != ["1", "2", "3", "4"]:
            raise PatentParseError(
                "shiftable image-sensor wire embodiment denominator changed"
            )
        for marker in profile["heading_markers"]:
            if len(re.findall(re.escape(str(marker)), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"shiftable image-sensor wire heading {marker!r} changed"
                )

        example_pairs = {
            (int(example), int(embodiment))
            for example, embodiment in re.findall(
                r"\b(\d+)(?:st|nd|rd|th)\s+example\s+of\s+the\s+"
                r"(\d+)(?:st|nd|rd|th)\s+embodiment\b",
                text,
                re.IGNORECASE,
            )
        }
        if example_pairs != {(1, 1), (2, 1), (3, 1)}:
            raise PatentParseError(
                "shiftable image-sensor wire example denominator changed"
            )
        for index, row in enumerate(
            _SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_TABLE_ROWS,
            start=1,
        ):
            if len(re.findall(re.escape(row), text, re.IGNORECASE)) != 1:
                raise PatentParseError(
                    f"shiftable image-sensor wire TABLE 1{'ABC'[index - 1]} binding changed"
                )
        if len(re.findall(r"TABLE-US-\d{5}", text, re.IGNORECASE)) != 3:
            raise PatentParseError(
                "shiftable image-sensor wire table denominator changed"
            )

        drawings = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+THE\s+DRAWINGS(?P<body>.*?)"
            r"DETAILED\s+DESCRIPTION",
            text,
            re.IGNORECASE,
        )
        if drawings is None:
            raise PatentParseError(
                "shiftable image-sensor wire drawing description is missing"
            )
        drawing_refs = tuple(
            (figure, panel.upper())
            for figure, panel in re.findall(
                r"\bFIG\.\s*([1-4])\s*([A-F]?)\s+is\s+",
                drawings.group("body"),
                re.IGNORECASE,
            )
        )
        if drawing_refs != _SHIFTABLE_IMAGE_SENSOR_WIRE_GEOMETRY_DRAWINGS:
            raise PatentParseError(
                "shiftable image-sensor wire 15-drawing denominator changed"
            )
        if re.search(
            r"\b(?:table|prescription|optical\s+data|lens\s+data)\b",
            drawings.group("body"),
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "shiftable image-sensor wire drawings now reference prescription data"
            )

        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"shiftable image-sensor wire phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        if len(re.findall(r"\bfocal\s+lengths?\b", text, re.IGNORECASE)) != 1:
            raise PatentParseError(
                "shiftable image-sensor wire nonnumeric focal-length narrative changed"
            )
        if len(
            re.findall(
                r"40\s+degrees\s*<\s*θ\s*<\s*90\s+degrees",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError(
                "shiftable image-sensor wire vehicle visual-angle range changed"
            )
        prescription_marker = re.compile(
            r"(?:\bradius\s+of\s+curvature\b|\bcurvature\s+radius\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)?\b|\brefractive\s+index\b|"
            r"\bSurface\s+(?:No\.|#)\s*|\bFno\b|\bF\s*[- ]?number\b|"
            r"\bEFL\b|\beffective\s+focal\s+length\b|\bfield\s+of\s+view\b|"
            r"\boptical\s+data\b|\blens\s+data\b|\bprescription\b|"
            rf"\bfocal\s+lengths?\s*(?:=|:)\s*{NUMBER_PATTERN})",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "shiftable image-sensor wire disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain all six source-declared items
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for index, embodiment in enumerate(embodiments, start=1):
        wire_geometry = index <= 3
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=embodiment,
                error=PatentTerminalParseError(
                    status="confirmed_no_prescription",
                    reason_code=(
                        "confirmed_no_prescription."
                        "shiftable_image_sensor_wire_geometry_only"
                        if wire_geometry
                        else (
                            "confirmed_no_prescription."
                            "camera_module_device_architecture_only"
                        )
                    ),
                    detail=(
                        f"TABLE 1{'ABC'[index - 1]} publishes only conductive-wire spacing, "
                        "width, elastic-connector cross-section, ratios, and wire count; "
                        "it has no optical surface prescription"
                        if wire_geometry
                        else (
                            f"{embodiment} publishes only camera-module placement, sensor, "
                            "device, capture, or light-folding architecture; it has no "
                            "optical surface prescription"
                        )
                    ),
                ),
            )
        )
    return attempts


def _classify_circle_optics_mechanical_only_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify the exact panoramic opto-mechanical member of Family 74060373."""

    profile = _CIRCLE_OPTICS_MECHANICAL_ONLY_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    embodiment = "Circle Optics panoramic capture opto-mechanical architecture"
    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"Circle Optics mechanical official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"Circle Optics mechanical normalized text hash changed for {patent_id}"
            )
        if _CIRCLE_OPTICS_MECHANICAL_ONLY_TITLE_PATTERN.search(text) is None:
            raise PatentParseError("Circle Optics mechanical title binding changed")
        application_number = str(profile["application_number"])
        series, serial = application_number.split("/", maxsplit=1)
        if len(
            re.findall(
                rf"Appl\.\s*No\.:\s*{re.escape(series)}\s*/\s*{re.escape(serial)}",
                text,
                re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("Circle Optics mechanical application binding changed")
        if _patent_table_blocks(text):
            raise PatentParseError("Circle Optics mechanical source gained a PPUBS table")
        for phrase, expected in profile["architecture_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"Circle Optics mechanical phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        drawings = re.search(
            r"BRIEF\s+DESCRIPTION\s+OF\s+(?:THE\s+)?DRAWINGS(?P<body>.*?)"
            r"DETAILED\s+DESCRIPTION",
            text,
            re.IGNORECASE,
        )
        if drawings is None:
            raise PatentParseError("Circle Optics mechanical drawing description is missing")
        drawing_body = drawings.group("body")
        drawing_numbers = [
            int(number) for number in re.findall(r"\((\d+)\)", drawing_body)
        ]
        expected_drawing_numbers = list(
            range(1, int(profile["drawing_description_count"]) + 1)
        )
        if drawing_numbers != expected_drawing_numbers:
            raise PatentParseError(
                "Circle Optics mechanical drawing sequence changed: "
                f"actual={drawing_numbers} expected={expected_drawing_numbers}"
            )
        if re.search(
            r"\b(?:table|prescription|optical\s+data|lens\s+data)\b",
            drawing_body,
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "Circle Optics mechanical drawings now reference prescription data"
            )
        if re.search(
            r"(?:\blens\s+prescription\b|\boptical\s+data\b|\blens\s+data\b|"
            r"\bsurface\s+radii\b|\baspherical\s+surface\s+coefficients\b)",
            text,
            re.IGNORECASE,
        ) is not None:
            raise PatentParseError(
                "Circle Optics mechanical disclosure contains a prescription marker"
            )
        error: Exception = PatentTerminalParseError(
            status="confirmed_no_prescription",
            reason_code=(
                "confirmed_no_prescription."
                "panoramic_opto_mechanical_architecture_only"
            ),
            detail=(
                "the source publishes panoramic camera housings, compressors, stops, "
                "sensors, projection architecture, and generic lens-design guidance only; "
                "it has no optical surface prescription"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - retain the exact source member
        error = exc
    return [
        _PrescriptionParseAttempt(
            embodiment_number=1,
            embodiment=embodiment,
            error=error,
        )
    ]


def _classify_light_blocking_geometry_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify one exact Largan light-blocking-opening geometry family."""

    if _LIGHT_BLOCKING_GEOMETRY_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _LIGHT_BLOCKING_GEOMETRY_ONLY_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    embodiment = "light-blocking-opening geometry disclosure"
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"light-blocking-geometry official text hash changed for {patent_id}"
            )
        table_count = len(_patent_table_blocks(text))
        if table_count != profile["table_count"]:
            raise PatentParseError(
                f"light-blocking-geometry table count is {table_count}; "
                f"expected {profile['table_count']}"
            )
        for phrase, expected in profile["geometry_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"light-blocking-geometry phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        prescription_marker = re.compile(
            r"(?:\bSurface\s+(?:No\.|#)\s*|"
            r"\b(?:Radius|Curvature)\s+Thickness\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)\b|\brefractive\s+index\b|"
            r"\bFno\b|\bF\s*[- ]?number\b|\bEFL\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\bprescription\b)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "light-blocking-geometry disclosure contains a prescription marker"
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
                reason_code="confirmed_no_prescription.light_blocking_geometry_only",
                detail=(
                    "the exact retained official PPUBS disclosure publishes only "
                    "light-blocking-opening D/A/R/dmin/FOV/N geometry tables and no "
                    "optical surface prescription"
                ),
            ),
        )
    ]


def _classify_folded_tele_missing_f_number_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Retain three exact folded-Tele prescriptions whose F-number is unpublished."""

    if _FOLDED_TELE_MISSING_F_NUMBER_TITLE_PATTERN.search(text) is None:
        return []
    profile = _FOLDED_TELE_MISSING_F_NUMBER_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"folded-Tele official text hash changed for {patent_id}"
            )
        blocks = _patent_table_blocks(text)
        table_numbers = [block.number for block in blocks]
        if table_numbers != list(range(1, 8)):
            raise PatentParseError(
                f"folded-Tele table sequence is {table_numbers}; expected 1..7"
            )
        expected_phrase_counts = {
            "Family ID: 55268405": 1,
            (
                "Detailed optical data and aspheric surface data is given in Tables 2 "
                "and 3 for lens module 220 a"
            ): 1,
            "lens module 220 a": 2,
            "lens module 220 b": 2,
            "lens module 220 c": profile["lens_module_220_c_count"],
            "EFL.sub.T of 12 mm": 1,
            "F-number": 2,
            "HFOV": 0,
        }
        for phrase, expected in expected_phrase_counts.items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"folded-Tele phrase {phrase!r} occurs {observed}; expected {expected}"
                )
        table_pairs = ((2, 3, "220a"), (4, 5, "220b"), (6, 7, "220c"))
        for surface_number, asphere_number, module in table_pairs:
            surface_text = blocks[surface_number - 1].text
            asphere_text = blocks[asphere_number - 1].text
            if (
                re.search(
                    r"(?:\bRadius(?:\s+\(R\))?\s+Distance\b|"
                    r"\bRadius\s+Conic\s+#\s+\(R\)\s+Distance\b)",
                    surface_text,
                )
                is None
            ):
                raise PatentParseError(
                    f"folded-Tele module {module} surface-table header changed"
                )
            if re.search(r"\bN\.sub\.d\s*/\s*V\.sub\.d\b", surface_text) is None:
                raise PatentParseError(
                    f"folded-Tele module {module} material header changed"
                )
            if re.search(r"#\s+α\.sub\.1\s+α\.sub\.2", asphere_text) is None:
                raise PatentParseError(
                    f"folded-Tele module {module} asphere-table header changed"
                )
    except Exception as exc:  # noqa: BLE001 - retain exact-source structural drift
        return [
            _PrescriptionParseAttempt(
                embodiment_number=None,
                embodiment="folded Tele prescription family",
                error=exc,
            )
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number, module in enumerate(("220a", "220b", "220c"), start=1):
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Folded Tele lens module {module}",
                error=PatentTerminalParseError(
                    status="metadata_unpublished",
                    reason_code="metadata_unpublished.system_f_number_absent",
                    detail=(
                        f"Tables {2 * embodiment_number}/{2 * embodiment_number + 1} "
                        f"publish the complete module {module} surface/asphere prescription, "
                        "but the official text publishes no exact system F-number for that "
                        "prescription; range and inequality statements are not substituted"
                    ),
                ),
            )
        )
    return attempts


def _classify_barrel_spacer_geometry_only_attempts(
    text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Classify one exact barrel/spacer geometry family without prescriptions."""

    if _BARREL_SPACER_GEOMETRY_ONLY_TITLE_PATTERN.search(text) is None:
        return []
    profile = _BARREL_SPACER_GEOMETRY_ONLY_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []
    try:
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"barrel-spacer-geometry official text hash changed for {patent_id}"
            )
        blocks = _patent_table_blocks(text)
        table_numbers = [block.number for block in blocks]
        if table_numbers != [1, 2, 3]:
            raise PatentParseError(
                f"barrel-spacer-geometry table sequence is {table_numbers}; expected 1..3"
            )
        for phrase, expected in profile["geometry_phrase_counts"].items():
            observed = len(re.findall(re.escape(phrase), text, flags=re.IGNORECASE))
            if observed != expected:
                raise PatentParseError(
                    f"barrel-spacer-geometry phrase {phrase!r} occurs "
                    f"{observed}; expected {expected}"
                )
        for block in blocks:
            if re.search(r"\bd\s+\(mm\)", block.text) is None:
                raise PatentParseError(
                    f"barrel-spacer-geometry TABLE {block.number} d header changed"
                )
            if re.search(r"N1i\s+\(mm\)", block.text) is None:
                raise PatentParseError(
                    f"barrel-spacer-geometry TABLE {block.number} N1i header changed"
                )
            if re.search(r"\bw2\s*/\s*w1\b", block.text) is None:
                raise PatentParseError(
                    f"barrel-spacer-geometry TABLE {block.number} width-ratio header changed"
                )
        prescription_marker = re.compile(
            r"(?:\bSurface\s+(?:No\.|#)\s*|"
            r"\b(?:Radius|Curvature)\s+Thickness\b|"
            r"\baspheric?\s+(?:surface\s+)?(?:data|coefficients?|parameters?)\b|"
            r"\bAbbe\s+(?:number|#)\b|\brefractive\s+index\b|"
            r"\bFno\b|\bF\s*[- ]?number\b|\bEFL\b|"
            r"\beffective\s+focal\s+length\b|\boptical\s+data\b|"
            r"\bprescription\b)",
            flags=re.IGNORECASE,
        )
        if prescription_marker.search(text) is not None:
            raise PatentParseError(
                "barrel-spacer-geometry disclosure contains a prescription marker"
            )
    except Exception as exc:  # noqa: BLE001 - retain exact-source structural drift
        return [
            _PrescriptionParseAttempt(
                embodiment_number=None,
                embodiment="barrel/spacer geometry family",
                error=exc,
            )
        ]

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 4):
        attempts.append(
            _PrescriptionParseAttempt(
                embodiment_number=embodiment_number,
                embodiment=f"Barrel/spacer geometry embodiment {embodiment_number}",
                error=PatentTerminalParseError(
                    status="confirmed_no_prescription",
                    reason_code="confirmed_no_prescription.barrel_spacer_geometry_only",
                    detail=(
                        f"TABLE {embodiment_number} publishes only barrel, spacer, opening, "
                        "and width-ratio geometry and no optical surface prescription"
                    ),
                ),
            )
        )
    return attempts


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
_SUNNY_LONG_FOCUS_FOLDED_SOURCE_PROFILES: dict[str, dict[str, str]] = {
    "US-12078782-B2": {
        "raw_document_sha256": (
            "2ceeeedb0c95b9958a372642aa47b06b0be0093d4f740bdabcacc8e6aab7a08e"
        ),
        "normalized_text_sha256": (
            "33b7f4f716197047a5a2f53227d90a274a0c3af57f94dd839b4b3f855fdcb997"
        ),
        "table_one_label": "1",
    },
    "US-20220137337-A1": {
        "raw_document_sha256": (
            "c40d066678be0f6fe2a8f592488381f13f611ee8cad7a25b481dee336763ce55"
        ),
        "normalized_text_sha256": (
            "42e843b251d6b8caf8bec222638338249583e171a77ab3e4809924e717b614bc"
        ),
        "table_one_label": "I",
    },
}
_SUNNY_FINGERPRINT_WIDE_ANGLE_SOURCE_PROFILES: dict[str, dict[str, str]] = {
    "US-12216247-B2": {
        "raw_document_sha256": (
            "52c751834233443040bbd188c77c584a5e9a38a3ac5e99cc30a8ec7ecf8dee2b"
        ),
        "normalized_text_sha256": (
            "491a61d9331cb197685dd764a095c0ab3a5b6049352cc3e073373a6aeeae1039"
        ),
    },
    "US-20220244497-A1": {
        "raw_document_sha256": (
            "f19c4e1fdb2e65940f9c998688aab0aa50cadddd2d5370973045788dba408cd0"
        ),
        "normalized_text_sha256": (
            "e1e1bdcf7c26956d4fd3dda9088ff3f0576b039185b680f028ac05ff0b98d40b"
        ),
    },
}
_SUNNY_FINGERPRINT_WIDE_ANGLE_METADATA = (
    (0.26, 2.62, 1.01, 149.9),
    (0.30, 2.58, 0.96, 145.7),
    (0.27, 2.75, 0.96, 142.9),
    (0.29, 2.82, 1.04, 141.4),
    (0.29, 2.81, 1.03, 144.0),
)
_SUNNY_FINGERPRINT_WIDE_ANGLE_F_NUMBERS = (1.40, 1.36, 1.38, 1.48, 1.49)
_SUNNY_FINGERPRINT_WIDE_ANGLE_SURFACE_DIGESTS = (
    "b19c6137166bb6de08b3890d56a858e4536cb3b5323b5e213cbd372f5f449917",
    "ef8f3e7e8beb5468bf9b321d122ff9cf36d642c029386ceb73d407fec6cd7f0e",
    "ba9f4a8a044d99cd4874a88f5f7136643c113cb90cd2ccebe508321601529e47",
    "58241f6a7754971f27ed27c67c2b8a4916a1db06ecb81397ffbb8eeb67e01363",
    "4dc41a30e934a00f5f23f741018c234b4ee6ff1f4b5b6819842e4cfc3f6901c7",
)
_SUNNY_LONG_FOCUS_FOLDED_SOURCE_ANCHOR_PATTERN = re.compile(
    r"\bTABLE-US-(?P<anchor>\d+)\s+TABLE\s+(?P<label>\d+|I)\s+",
    flags=re.IGNORECASE,
)
_SUNNY_LONG_FOCUS_FOLDED_EFLS: tuple[float | None, ...] = (
    40.0,
    40.0,
    40.0,
    45.0,
    None,
    40.0,
    48.0,
    40.0,
)
_SUNNY_LONG_FOCUS_FOLDED_PRODUCTS = (5.12, 5.12, 5.12, 5.76, 5.12, 5.12, 6.15, 5.12)
_SUNNY_LONG_FOCUS_FOLDED_PRODUCT_TOKENS = (
    "5.12",
    "←",
    "5.12",
    "5.76",
    "5.12",
    "5.12",
    "6.15",
    "5.12",
)
_SUNNY_LONG_FOCUS_FOLDED_STANDARD_TABLES = {
    1: (1, 2),
    3: (4, 5),
    4: (6, 7),
    5: (8, 9),
    6: (10, 11),
    7: (12, 13),
    8: (14, 15),
}
_SUNNY_LONG_FOCUS_FOLDED_COEFFICIENT_COUNTS = {
    1: 8,
    3: 8,
    4: 8,
    5: 9,
    6: 8,
    7: 9,
    8: 9,
}


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
        if (
            token == "Surface"
            and pos + 1 < len(tokens)
            and tokens[pos + 1].lower() in {"number", "no."}
        ):
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
    wavelengths, reference_wavelength_index = _patent_wavelength_table(
        prescription.reference_wavelength_um
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
        reference_wavelength_index=reference_wavelength_index,
        image_height_y_mm=(
            image_height_y_mm if image_height_y_mm is not None else prescription.image_height_mm
        ),
        surfaces=surfaces,
        fields=fields,
        wavelengths=wavelengths,
    )


def _patent_wavelength_table(
    reference_wavelength_um: float,
) -> tuple[tuple[CodeVWavelengthReadout, ...], int]:
    if not math.isfinite(reference_wavelength_um) or reference_wavelength_um <= 0.0:
        raise PatentParseError("reference wavelength must be finite and positive")
    values = [0.4861, 0.5876, 0.6563]
    if not any(
        math.isclose(reference_wavelength_um, value, rel_tol=0.0, abs_tol=1e-12)
        for value in values
    ):
        values.append(reference_wavelength_um)
        values.sort()
    reference_index = next(
        index
        for index, value in enumerate(values, start=1)
        if math.isclose(reference_wavelength_um, value, rel_tol=0.0, abs_tol=1e-12)
    )
    return (
        tuple(
            CodeVWavelengthReadout(index=index, wavelength_um=value, weight=1.0)
            for index, value in enumerate(values, start=1)
        ),
        reference_index,
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


def _parse_sunny_long_focus_folded_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Recover the source-locked Family 77932615 long-focus prescriptions.

    TABLE 16 publishes ``f * tan(Semi-FOV)`` for every embodiment.  Where the
    same official source also publishes the embodiment EFL, the half field is
    the deterministic inverse of that exact relation.  No sensor geometry or
    optical cell is inferred.  Embodiment 5 keeps the EFL cell blank and is
    therefore terminal; embodiment 2 includes two mirrors and coordinate
    reversals that remain fail-closed until a folded-coordinate parser exists.
    """

    profile = _SUNNY_LONG_FOCUS_FOLDED_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=f"Sunny long-focus embodiment {index}",
                error=exc,
            )
            for index in range(1, 9)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"Sunny long-focus official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"Sunny long-focus normalized text hash changed for {patent_id}"
            )
        if re.search(
            rf"^{re.escape(patent_id)}\s+-\s+Patent\s+Public\s+Search\s+\|\s+USPTO\b"
            r".*?\bCAMERA\s+LENS\s+Abstract\b",
            text,
            flags=re.IGNORECASE,
        ) is None:
            raise PatentParseError("Sunny long-focus title binding changed")
        if len(re.findall(r"Family\s+ID:\s*77932615", text, flags=re.IGNORECASE)) != 1:
            raise PatentParseError("Sunny long-focus Family ID binding changed")
        if len(re.findall(r"Appl\.\s*No\.:\s*17\s*/\s*509745", text)) != 1:
            raise PatentParseError("Sunny long-focus application binding changed")

        blocks, labels = _sunny_long_focus_folded_source_blocks(text)
        if set(blocks) != set(range(1, 17)):
            raise PatentParseError("Sunny long-focus source tables 1-16 are not complete")
        if labels[1].upper() != profile["table_one_label"]:
            raise PatentParseError("Sunny long-focus TABLE 1 label changed")
        if any(labels[number] != str(number) for number in range(2, 17)):
            raise PatentParseError("Sunny long-focus numeric table labels changed")

        efls, f_numbers = _sunny_long_focus_folded_metadata(text)
        if efls != _SUNNY_LONG_FOCUS_FOLDED_EFLS:
            raise PatentParseError("Sunny long-focus EFL metadata changed")
        if f_numbers != (4.0,) * 8:
            raise PatentParseError("Sunny long-focus F-number metadata changed")
        products = _sunny_long_focus_folded_products(blocks[16])
        if products != _SUNNY_LONG_FOCUS_FOLDED_PRODUCTS:
            raise PatentParseError("Sunny long-focus field-product row changed")
        if len(
            re.findall(
                r"Semi-FOV\s+is\s+the\s+maximum\s+semi-field\s+of\s+view",
                text,
                flags=re.IGNORECASE,
            )
        ) != 1:
            raise PatentParseError("Sunny long-focus Semi-FOV definition changed")
        if re.search(
            rf"(?:Semi-FOV|HFOV)\s*(?:\([^)]*\))?\s*(?:=|\bis\b)\s*"
            rf"(?:about\s+)?{NUMBER_PATTERN}",
            text,
            flags=re.IGNORECASE,
        ) is not None:
            raise PatentParseError("Sunny long-focus now publishes a standalone numeric half field")
        folded_table = blocks[3]
        folded_bindings = (
            r"\(P1\)\s+Spherical\s+Infinity\s+-10\.0000",
            r"S1\s+Aspherical\s+-7\.4399\s+-3\.7276",
            r"S6\s+Aspherical\s+-15\.8317\s+-13\.7656",
            r"\(P2\)\s+Spherical\s+Infinity\s+-5\.0000\s+"
            r"Spherical\s+Infinity\s+5\.0000\s+"
            r"Spherical\s+Infinity\s+2\.3656",
        )
        if any(
            len(re.findall(pattern, folded_table, flags=re.IGNORECASE)) != 1
            for pattern in folded_bindings
        ):
            raise PatentParseError("Sunny long-focus folded-coordinate bindings changed")

        parsed: dict[int, PatentPrescription] = {}
        for embodiment_number, (surface_table, coefficient_table) in (
            _SUNNY_LONG_FOCUS_FOLDED_STANDARD_TABLES.items()
        ):
            surface_text = blocks[surface_table]
            if embodiment_number == 1:
                if surface_text.count("S7 Sphericai") != 1:
                    raise PatentParseError("Sunny long-focus TABLE 1 S7 type token changed")
                # The official source spells the non-numeric surface type as
                # ``Sphericai`` in both same-application publications.  This
                # source-locked token correction never changes an optical cell.
                surface_text = surface_text.replace("S7 Sphericai", "S7 Spherical", 1)
            surfaces, index_by_row_key = _parse_sunny_surface_table(
                surface_text,
                embodiment_number=embodiment_number,
            )
            if set(index_by_row_key) != {"STO", *(f"S{index}" for index in range(1, 10))}:
                raise PatentParseError(
                    f"Sunny long-focus embodiment {embodiment_number} surface sequence changed"
                )
            coefficients: dict[int, dict[str, float]] = {}
            _parse_sunny_asphere_block_into(
                blocks[coefficient_table],
                index_by_row_key=index_by_row_key,
                coefficients=coefficients,
            )
            expected_count = _SUNNY_LONG_FOCUS_FOLDED_COEFFICIENT_COUNTS[
                embodiment_number
            ]
            coefficient_indices = {index_by_row_key[f"S{index}"] for index in range(1, 7)}
            if set(coefficients) != coefficient_indices or any(
                len(values) != expected_count for values in coefficients.values()
            ):
                raise PatentParseError(
                    f"Sunny long-focus embodiment {embodiment_number} coefficients changed"
                )
            for surface in surfaces:
                values = coefficients.get(surface.index)
                if values is not None:
                    surface.asphere_coefficients.update(values)
                    surface.surface_type = "ASP"

            focal_length = efls[embodiment_number - 1]
            if focal_length is None:
                continue
            half_field = math.degrees(
                math.atan(products[embodiment_number - 1] / focal_length)
            )
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=f"Sunny long-focus embodiment {embodiment_number}",
                focal_length_mm=focal_length,
                f_number=f_numbers[embodiment_number - 1],
                hfov_deg=half_field,
                surfaces=surfaces,
            )
            if not math.isclose(
                prescription.image_height_mm,
                products[embodiment_number - 1],
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise PatentParseError(
                    f"Sunny long-focus embodiment {embodiment_number} field transform changed"
                )
            _validate_prescription_materials(prescription)
            parsed[embodiment_number] = prescription
    except Exception as exc:  # noqa: BLE001 - retain all eight disclosed embodiments
        return attempts_for_error(exc)

    attempts: list[_PrescriptionParseAttempt] = []
    for embodiment_number in range(1, 9):
        embodiment = f"Sunny long-focus embodiment {embodiment_number}"
        if embodiment_number == 2:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    error=PatentParseError(
                        "Sunny long-focus embodiment 2 publishes P1/P2 mirrors, signed "
                        "coordinate reversals, and unlabeled coordinate-break rows; a "
                        "folded-coordinate parser is required"
                    ),
                )
            )
        elif embodiment_number == 5:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    error=PatentTerminalParseError(
                        status="metadata_unpublished",
                        reason_code=(
                            "metadata_unpublished.configuration_effective_focal_length_"
                            "and_numeric_semi_fov_absent"
                        ),
                        detail=(
                            "embodiment 5 leaves the EFL value blank and publishes only "
                            "f*tan(Semi-FOV)=5.12, so the numeric half field cannot be "
                            "deterministically recovered"
                        ),
                    ),
                )
            )
        else:
            attempts.append(
                _PrescriptionParseAttempt(
                    embodiment_number=embodiment_number,
                    embodiment=embodiment,
                    prescription=parsed[embodiment_number],
                )
            )
    return attempts


def _parse_sunny_fingerprint_wide_angle_attempts(
    raw_text: str,
    *,
    patent_id: str,
) -> list[_PrescriptionParseAttempt]:
    """Recover all five source-locked Family 75759822 prescriptions.

    The exact publications define FOV as the maximum/full field and publish a
    numeric FOV for every embodiment.  ``PatentPrescription`` stores half
    field, so division by two is a source-defined unit transform.  Published
    ImgH remains provenance evidence: it is not substituted for paraxial
    ``f*tan(HFOV)`` because the disclosed designs have distortion.
    """

    profile = _SUNNY_FINGERPRINT_WIDE_ANGLE_SOURCE_PROFILES.get(patent_id.upper())
    if profile is None:
        return []

    def attempts_for_error(exc: Exception) -> list[_PrescriptionParseAttempt]:
        return [
            _PrescriptionParseAttempt(
                embodiment_number=index,
                embodiment=f"Sunny fingerprint embodiment {index}",
                error=exc,
            )
            for index in range(1, 6)
        ]

    try:
        raw_digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if raw_digest != profile["raw_document_sha256"]:
            raise PatentParseError(
                f"Sunny fingerprint official raw text hash changed for {patent_id}"
            )
        text = normalize_patent_text(raw_text)
        normalized_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if normalized_digest != profile["normalized_text_sha256"]:
            raise PatentParseError(
                f"Sunny fingerprint normalized text hash changed for {patent_id}"
            )
        if re.search(
            rf"^{re.escape(patent_id)}\s+-\s+Patent\s+Public\s+Search\s+\|\s+USPTO\b"
            r".*?\bOPTICAL\s+IMAGING\s+LENS\s+ASSEMBLY\s+AND\s+FINGERPRINT\s+"
            r"IDENTIFICATION\s+DEVICE\s+Abstract\b",
            text,
            flags=re.IGNORECASE,
        ) is None:
            raise PatentParseError("Sunny fingerprint title binding changed")
        if len(re.findall(r"Family\s+ID:\s*75759822", text, flags=re.IGNORECASE)) != 1:
            raise PatentParseError("Sunny fingerprint Family ID binding changed")
        if len(re.findall(r"Appl\.\s*No\.:\s*17\s*/\s*575671", text)) != 1:
            raise PatentParseError("Sunny fingerprint application binding changed")
        if patent_id.upper() == "US-12216247-B2" and not _grant_binds_prior_publication(
            raw_text,
            "US-20220244497-A1",
        ):
            raise PatentParseError("Sunny fingerprint prior-publication binding changed")
        if not _sunny_fov_is_full_angle(text):
            raise PatentParseError("Sunny fingerprint full-FOV definition changed")

        table_bindings = [
            (int(match.group("anchor")), int(match.group("label")))
            for match in re.finditer(
                r"\bTABLE-US-(?P<anchor>\d+)\s+TABLE\s+(?P<label>\d+)\s+",
                text,
                flags=re.IGNORECASE,
            )
        ]
        expected_table_bindings = [(index, index) for index in range(1, 12)]
        if table_bindings != expected_table_bindings:
            raise PatentParseError("Sunny fingerprint source tables 1-11 changed")
        blocks = _patent_table_blocks(text)
        if len(blocks) != 11 or [block.number for block in blocks] != list(range(1, 12)):
            raise PatentParseError("Sunny fingerprint table-block denominator changed")
        if [
            index for index, block in enumerate(blocks) if _sunny_surface_block_signature(block.text)
        ] != [0, 2, 4, 6, 8]:
            raise PatentParseError("Sunny fingerprint surface-table positions changed")

        metadata = _sunny_fingerprint_wide_angle_metadata(text)
        if metadata != _SUNNY_FINGERPRINT_WIDE_ANGLE_METADATA:
            raise PatentParseError("Sunny fingerprint embodiment metadata changed")
        f_numbers = _sunny_group_row_values(
            blocks,
            label_patterns=_SUNNY_GROUP_FNO_LABELS,
            embodiment_count=5,
            reject_compound_fno=True,
        )
        if tuple(f_numbers or ()) != _SUNNY_FINGERPRINT_WIDE_ANGLE_F_NUMBERS:
            raise PatentParseError("Sunny fingerprint F-number row changed")

        prescriptions: list[PatentPrescription] = []
        expected_rows = {"S01", "S02", "STO", *(f"S{index}" for index in range(1, 10))}
        for embodiment_number in range(1, 6):
            surface_block = blocks[(embodiment_number - 1) * 2]
            coefficient_block = blocks[(embodiment_number - 1) * 2 + 1]
            surfaces, index_by_row_key = _parse_sunny_surface_table(
                surface_block.text,
                embodiment_number=embodiment_number,
            )
            if set(index_by_row_key) != expected_rows:
                raise PatentParseError(
                    f"Sunny fingerprint embodiment {embodiment_number} surface sequence changed"
                )
            coefficients: dict[int, dict[str, float]] = {}
            _parse_sunny_asphere_block_into(
                coefficient_block.text,
                index_by_row_key=index_by_row_key,
                coefficients=coefficients,
            )
            expected_coefficient_indices = {
                index_by_row_key[f"S{index}"] for index in range(1, 7)
            }
            if set(coefficients) != expected_coefficient_indices or any(
                len(values) != 9 for values in coefficients.values()
            ):
                raise PatentParseError(
                    f"Sunny fingerprint embodiment {embodiment_number} coefficients changed"
                )
            for surface in surfaces:
                values = coefficients.get(surface.index)
                if values is not None:
                    surface.asphere_coefficients.update(values)
                    surface.surface_type = "ASP"
            if (
                _sunny_fingerprint_wide_angle_surface_digest(surfaces)
                != _SUNNY_FINGERPRINT_WIDE_ANGLE_SURFACE_DIGESTS[embodiment_number - 1]
            ):
                raise PatentParseError(
                    f"Sunny fingerprint embodiment {embodiment_number} optical cells changed"
                )

            focal_length, _ttl, _published_imgh, full_fov = metadata[
                embodiment_number - 1
            ]
            prescription = PatentPrescription(
                patent_id=patent_id,
                embodiment=f"Sunny fingerprint embodiment {embodiment_number}",
                focal_length_mm=focal_length,
                f_number=_SUNNY_FINGERPRINT_WIDE_ANGLE_F_NUMBERS[embodiment_number - 1],
                hfov_deg=full_fov / 2.0,
                surfaces=surfaces,
            )
            _validate_prescription_materials(prescription)
            prescriptions.append(prescription)
    except Exception as exc:  # noqa: BLE001 - retain all five disclosed embodiments
        return attempts_for_error(exc)

    return [
        _PrescriptionParseAttempt(
            embodiment_number=index,
            embodiment=prescription.embodiment,
            prescription=prescription,
        )
        for index, prescription in enumerate(prescriptions, start=1)
    ]


def _sunny_fingerprint_wide_angle_metadata(
    text: str,
) -> tuple[tuple[float, float, float, float], ...]:
    pattern = re.compile(
        r"\bIn\s+the\s+embodiment,\s+a\s+total\s+effective\s+focal\s+length\s+f\s+of\s+"
        r"the\s+optical\s+imaging\s+lens\s+assembly\s+is\s+"
        rf"(?P<f>{NUMBER_PATTERN})\s+mm\.\s+TTL\s+is\s+a\s+total\s+length\s+of\s+the\s+"
        r"optical\s+imaging\s+lens\s+assembly\s*"
        r"(?:\(i\.e\.,[^)]*\))?,\s+and\s+TTL\s+is\s+"
        rf"(?P<ttl>{NUMBER_PATTERN})\s+mm\.\s+ImgH\s+is\s+a\s+half\s+of\s+a\s+diagonal\s+"
        r"length\s+of\s+an\s+effective\s+pixel\s+region\s+on\s+the\s+imaging\s+surface\s+"
        r"S\s*9\s+of\s+the\s+optical\s+imaging\s+lens\s+assembly,\s+and\s+ImgH\s+is\s+"
        rf"(?P<imgh>{NUMBER_PATTERN})\s+mm\.\s+FOV\s+is\s+a\s+(?:maximum\s+)?field\s+of\s+"
        r"view\s+of\s+the\s+optical\s+imaging\s+lens\s+assembly,\s+and\s+FOV\s+is\s+"
        rf"(?:maximally\s+)?(?P<fov>{NUMBER_PATTERN})°\.",
        flags=re.IGNORECASE,
    )
    return tuple(
        tuple(_parse_number(match.group(field)) for field in ("f", "ttl", "imgh", "fov"))
        for match in pattern.finditer(text)
    )


def _sunny_fingerprint_wide_angle_surface_digest(surfaces: list[PatentSurface]) -> str:
    payload = [
        (
            surface.label,
            surface.radius_mm,
            surface.thickness_mm,
            surface.nd,
            surface.vd,
            surface.surface_type,
            sorted(surface.asphere_coefficients.items()),
        )
        for surface in surfaces
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sunny_long_focus_folded_source_blocks(
    text: str,
) -> tuple[dict[int, str], dict[int, str]]:
    matches = list(_SUNNY_LONG_FOCUS_FOLDED_SOURCE_ANCHOR_PATTERN.finditer(text))
    blocks: dict[int, str] = {}
    labels: dict[int, str] = {}
    for index, match in enumerate(matches):
        label = match.group("label")
        number = 1 if label.upper() == "I" else int(label)
        if int(match.group("anchor")) != number:
            raise PatentParseError("Sunny long-focus table anchor/label mismatch")
        if number in blocks:
            raise PatentParseError(f"duplicate Sunny long-focus source table: {number}")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[number] = text[match.start() : end]
        labels[number] = label
    return blocks, labels


def _sunny_long_focus_folded_metadata(
    text: str,
) -> tuple[tuple[float | None, ...], tuple[float, ...]]:
    efls: list[float | None] = []
    f_numbers: list[float] = []
    for embodiment_number in range(1, 9):
        pattern = re.compile(
            rf"\bIn\s+Embodiment\s+{embodiment_number}\s*,\s+a\s+total\s+effective\s+"
            rf"focal\s+length\s+f\s+of\s+the\s+camera\s+lens\s+has\s+a\s+value\s+of\s*"
            rf"(?P<f>{NUMBER_PATTERN})?\s*mm\s*,\s+and\s+an\s+aperture\s+number\s+Fno\s+"
            rf"of\s+the\s+camera\s+lens\s+has\s+a\s+value\s+of\s*"
            rf"(?P<fno>{NUMBER_PATTERN})\s*\.",
            flags=re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if len(matches) != 1:
            raise PatentParseError(
                f"Sunny long-focus embodiment {embodiment_number} metadata binding changed"
            )
        focal_token = matches[0].group("f")
        efls.append(_parse_number(focal_token) if focal_token is not None else None)
        f_numbers.append(_parse_number(matches[0].group("fno")))
    return tuple(efls), tuple(f_numbers)


def _sunny_long_focus_folded_products(table_text: str) -> tuple[float, ...]:
    body = _cut_sunny_table_narrative(table_text)
    match = re.search(
        r"\bf\s*×\s*tan\s*\(\s*Semi-FOV\s*\)\s+"
        r"(?P<values>.*?)\s+TL\s*/\s*EPD\b",
        body,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise PatentParseError("Sunny long-focus field-product row is missing")
    tokens = tuple(match.group("values").split())
    if tokens != _SUNNY_LONG_FOCUS_FOLDED_PRODUCT_TOKENS:
        raise PatentParseError("Sunny long-focus field-product token sequence changed")
    values: list[float] = []
    for token in tokens:
        if token == "←":
            if not values:
                raise PatentParseError("Sunny long-focus field-product arrow lacks a value")
            values.append(values[-1])
        else:
            values.append(_parse_number(token))
    return tuple(values)


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
            reference_wavelength_um=prescription.reference_wavelength_um,
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
        "reference_wavelength_um": prescription.reference_wavelength_um,
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
        rays = optic.trace_generic(
            h_x,
            h_y,
            p_x,
            p_y,
            prescription.reference_wavelength_um,
        )

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
