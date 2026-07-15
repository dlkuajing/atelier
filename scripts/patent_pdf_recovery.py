"""Fail-closed recovery of patent drawing tables from public PDF images.

USPTO Patent Public Search serves some drawing tables only as page images.  A
Google Patents PDF may add an OCR text layer to the same page image.  This
module accepts that text layer only when every decoded page raster is pixel-
identical to the official USPTO PDF, then retains a second deterministic OCR
view of the key pages for missing-cell detection and parser provenance.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import re
from dataclasses import dataclass
from typing import Any

import cv2
import httpx
import numpy as np
import pypdf
from rapidocr_onnxruntime import RapidOCR

USPTO_IMAGE_PDF_URL = (
    "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{patent_number}"
)
GOOGLE_PATENT_URL = "https://patents.google.com/patent/{compact_publication_id}/en"
GOOGLE_PDF_HOST = "patentimages.storage.googleapis.com"
_GOOGLE_PDF_META_RE = re.compile(
    r'<meta\s+name="citation_pdf_url"\s+content="(?P<url>[^"]+)"',
    flags=re.IGNORECASE,
)
_ABILITY_REQUIRED_FIGURE_TEXT = (
    "FIG. 2A lists one embodiment",
    "FIG. 2B lists another embodiment",
    "FIG. 5 lists one embodiment",
    "FIG. 7 lists information",
)
_ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 2 shows each lens parameter of the optical lens",
    "FIG. 3 lists aspheric coefficients of the mathematic equation "
    "of the aspheric lenses of the optical lens",
    "FNO is F-number of the stop STO",
    "FOV is a field of view of the optical lens",
)
_ABILITY_EIGHT_LENS_PROFILE = "ability_eight_lens_metadata_unpublished_v1"
_ABILITY_THREE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 4A lists parameters of each lens of the optical lens shown in FIG. 1",
    "FIG. 4B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 1",
    "FIG. 5A lists parameters of each lens of the optical lens shown in FIG. 2",
    "FIG. 5B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 2",
    "FIG. 6A lists parameters of each lens of the optical lens shown in FIG. 3",
    "FIG. 6B lists aspherical coefficients of the aspherical surface formula",
    "FIG. 7 lists optical data of the optical lenses OL 1 , OL 2 , OL 3",
)
_ABILITY_THREE_LENS_PROFILE = "ability_three_lens_prescriptions_v1"
_ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 3A shows each lens parameter of the optical lens of FIG. 1",
    "FIG. 3B shows each coefficient of a mathematical formula of aspheric surface "
    "for the aspheric lens of the optical lens of FIG. 1",
    "FIG. 4A shows each lens parameter of the optical lens of FIG. 2",
    "FIG. 4B shows each coefficient of a mathematical formula of aspheric surface "
    "for the aspheric lens of the optical lens of FIG. 2",
    "FIG. 5 shows parameter performance of the optical lens",
)
_ABILITY_TWO_FIVE_LENS_PROFILE = "ability_two_five_lens_prescriptions_v1"
_ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 4A lists each lens parameter of the optical lens of FIG. 1",
    "FIG. 4B lists coefficients of the mathematic equation of the aspheric surfaces "
    "of the optical lens of FIG. 1",
    "FIG. 5A lists each lens parameter of the optical lens of FIG. 2",
    "FIG. 5B lists coefficients of the mathematic equation of the aspheric surfaces "
    "of the optical lens of FIG. 2",
    "FIG. 6 lists optical information of the optical lenses OL 1 and OL 2",
)
_ABILITY_TWO_NINE_LENS_PROFILE = "ability_two_nine_lens_f_number_unpublished_v1"
_ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 2A lists parameters of each lens of the optical lens in FIG. 1",
    "FIG. 2B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 1 and FIG. 2A",
    "FIG. 4A lists parameters of each lens of the optical lens in FIG. 3",
    "FIG. 4B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 3 and FIG. 4A",
    "FIG. 6A lists parameters of each lens of the optical lens in FIG. 5",
    "FIG. 6B lists aspherical coefficients of the aspherical surface formula "
    "of the lenses in optical lens shown in FIG. 5 and FIG. 6A",
    "FIG. 8 lists parameters of each lens of the optical lens in FIG. 7",
    "FIG. 9 lists optical properties of the optical lenses",
)
_ABILITY_FOUR_EIGHT_LENS_PROFILE = "ability_four_eight_lens_f_number_unpublished_v1"
_SYSTEM_VALUE_PATTERN_TEMPLATE = (
    r"\b{label}\s*(?:=|:|is(?:\s+set\s+to)?)\s*"
    r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[-+]?\d+)?"
)
_PDF_HEADER = b"%PDF-"


class PatentPdfRecoveryError(RuntimeError):
    """Raised when a PDF/OCR linkage or extraction invariant is not proven."""


@dataclass(frozen=True)
class PatentPdfOcrRecovery:
    publication_id: str
    official_pdf: bytes
    official_pdf_url: str
    mirror_pdf: bytes
    mirror_pdf_url: str
    parser_input: bytes
    page_count: int
    page_image_sha256: tuple[str, ...]
    key_page_numbers: tuple[int, ...]
    pypdf_version: str
    rapidocr_version: str


@dataclass(frozen=True)
class PatentPdfCachedSources:
    """Immutable PDF bytes selected by the patent-lake source pin."""

    official_pdf: bytes
    official_pdf_url: str
    mirror_pdf: bytes
    mirror_pdf_url: str


def _normalized_html_text(raw_html: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw_html))
    return re.sub(r"\s+", " ", text).strip()


def _ability_layout_profile(raw_html: str) -> str | None:
    """Return the exact source-proven Ability drawing-table profile."""

    text = _normalized_html_text(raw_html)
    if all(marker in text for marker in _ABILITY_REQUIRED_FIGURE_TEXT):
        return "ability_two_lens_prescriptions_v1"
    if all(marker in text for marker in _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_EIGHT_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_THREE_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_THREE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_TWO_FIVE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_TWO_NINE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT):
        return _ABILITY_FOUR_EIGHT_LENS_PROFILE
    return None


def ability_drawing_tables_declared(raw_html: str) -> bool:
    """Return whether official text declares a supported image-table layout."""

    return _ability_layout_profile(raw_html) is not None


def _ability_eight_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure the exact official-text facts needed for a terminal outcome."""

    text = _normalized_html_text(raw_html)
    assignments = {
        label: len(
            re.findall(
                _SYSTEM_VALUE_PATTERN_TEMPLATE.format(label=re.escape(label)),
                text,
                flags=re.IGNORECASE,
            )
        )
        for label in ("F", "FNO", "FOV")
    }
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "surface_figure_binding_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[0]
        ),
        "asphere_figure_binding_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[1]
        ),
        "fno_definition_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[2]
        ),
        "fov_definition_count": text.count(
            _ABILITY_EIGHT_LENS_REQUIRED_FIGURE_TEXT[3]
        ),
        "numeric_system_value_assignment_counts": assignments,
    }


def _ability_three_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure the official figure bindings for the three-prescription layout."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_THREE_LENS_REQUIRED_FIGURE_TEXT
        },
    }


def _ability_two_five_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure the official bindings for two disclosed five-lens prescriptions."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_TWO_FIVE_LENS_REQUIRED_FIGURE_TEXT
        },
    }


def _ability_two_nine_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure figure bindings and the absence of any F-number label."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_TWO_NINE_LENS_REQUIRED_FIGURE_TEXT
        },
        "f_number_label_counts": {
            "FNO": len(re.findall(r"\bFNO\b", text, flags=re.IGNORECASE)),
            "F-number": len(
                re.findall(r"\bF\s*[- ]?number\b", text, flags=re.IGNORECASE)
            ),
            "F/#": len(re.findall(r"\bF\s*/\s*#\b", text, flags=re.IGNORECASE)),
        },
    }


def _ability_four_eight_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure four prescription bindings and the absence of F-number labels."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_FOUR_EIGHT_LENS_REQUIRED_FIGURE_TEXT
        },
        "f_number_label_counts": {
            "FNO": len(re.findall(r"\bFNO\b", text, flags=re.IGNORECASE)),
            "F-number": len(
                re.findall(r"\bF\s*[- ]?number\b", text, flags=re.IGNORECASE)
            ),
            "F/#": len(re.findall(r"\bF\s*/\s*#\b", text, flags=re.IGNORECASE)),
        },
    }


def _compact_publication_id(publication_id: str) -> tuple[str, str]:
    match = re.fullmatch(r"US-(?P<number>\d+)-(?P<kind>[A-Z]\d+)", publication_id.upper())
    if match is None:
        raise PatentPdfRecoveryError(f"unsupported USPTO publication id: {publication_id}")
    compact = f"US{match.group('number')}{match.group('kind')}"
    return compact, match.group("number")


async def _get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(4):
        response = await client.get(
            url,
            params=params,
            headers=headers,
            follow_redirects=True,
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response
        await asyncio.sleep(5 * (attempt + 1))
    assert response is not None
    response.raise_for_status()
    return response


def _require_pdf(content: bytes, *, source: str) -> None:
    if not content.startswith(_PDF_HEADER):
        raise PatentPdfRecoveryError(f"{source} did not return a PDF")


def _page_image(page: pypdf._page.PageObject, *, source: str, page_number: int) -> bytes:
    images = list(page.images)
    if len(images) != 1:
        raise PatentPdfRecoveryError(
            f"{source} page {page_number} contains {len(images)} images; expected exactly one"
        )
    return images[0].data


def _decoded_raster(image_bytes: bytes, *, source: str) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise PatentPdfRecoveryError(f"{source} page image could not be decoded")
    return np.ascontiguousarray(image)


def _canonical_raster_sha256(image_bytes: bytes) -> str:
    """Hash decoded pixels, excluding nondeterministic TIFF container padding."""

    image = _decoded_raster(image_bytes, source="canonical")
    digest = hashlib.sha256()
    digest.update(b"decoded-page-raster-v1\0")
    digest.update(str(image.shape).encode("ascii"))
    digest.update(b"\0")
    digest.update(str(image.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(image.tobytes(order="C"))
    return digest.hexdigest()


def _figure_page(texts: list[str], figure: str, required: tuple[str, ...]) -> int:
    figure_pattern = re.compile(rf"\bFIG\s*\.\s*{re.escape(figure)}\b", re.IGNORECASE)
    drawing_sheet_pattern = re.compile(r"\bSheet\s+\d+\s+of\s+\d+\b", re.IGNORECASE)
    matches = [
        index
        for index, text in enumerate(texts)
        if drawing_sheet_pattern.search(text)
        and figure_pattern.search(text)
        and all(item.lower() in text.lower() for item in required)
    ]
    if len(matches) != 1:
        raise PatentPdfRecoveryError(
            f"Ability PDF figure {figure} key page count is {len(matches)}; expected one"
        )
    return matches[0]


def _rapidocr_tokens(image_bytes: bytes) -> list[dict[str, Any]]:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise PatentPdfRecoveryError("official page image could not be decoded")
    engine = RapidOCR()
    result, _elapsed = engine(image)
    tokens: list[dict[str, Any]] = []
    for box, text, confidence in result or []:
        tokens.append(
            {
                "box": [[round(float(x), 3), round(float(y), 3)] for x, y in box],
                "text": str(text),
                "confidence": round(float(confidence), 6),
            }
        )
    return tokens


def _canonical_parser_input(
    *,
    publication_id: str,
    page_count: int,
    key_pages: list[tuple[int, str, str, str, list[dict[str, Any]]]],
    profile: str | None = None,
    source_facts: dict[str, Any] | None = None,
) -> bytes:
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "publication_id": publication_id,
        "page_count": page_count,
        "pages": [
            {
                "page_number": page_number,
                "role": role,
                "official_image_sha256": image_sha256,
                "mirror_text": mirror_text,
                "rapidocr_tokens": tokens,
            }
            for page_number, role, image_sha256, mirror_text, tokens in key_pages
        ],
    }
    # Keep the first profile's canonical bytes stable.  New profile metadata is
    # emitted only for layouts which need additional source-level proof.
    if profile is not None:
        payload["profile"] = profile
    if source_facts is not None:
        payload["source_facts"] = source_facts
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


async def recover_ability_official_pdf_ocr(
    client: httpx.AsyncClient,
    token: str,
    *,
    publication_id: str,
    primary_html: str,
    cached_sources: PatentPdfCachedSources | None = None,
) -> PatentPdfOcrRecovery | None:
    """Recover a strict Ability image-table layout or return no match."""

    profile = _ability_layout_profile(primary_html)
    if profile is None:
        return None
    compact_id, patent_number = _compact_publication_id(publication_id)
    official_url = USPTO_IMAGE_PDF_URL.format(patent_number=patent_number)
    if cached_sources is None:
        official_response = await _get_with_retries(
            client,
            official_url,
            params={"requestToken": token},
            headers={
                "Accept": "application/pdf",
                "Referer": "https://ppubs.uspto.gov/",
                "x-access-token": token,
            },
        )
        official_pdf = official_response.content
    else:
        if cached_sources.official_pdf_url != official_url:
            raise PatentPdfRecoveryError("cached USPTO PDF URL does not match publication")
        official_pdf = cached_sources.official_pdf
    _require_pdf(official_pdf, source="USPTO image PDF")

    if cached_sources is None:
        google_page_url = GOOGLE_PATENT_URL.format(compact_publication_id=compact_id)
        google_page = await _get_with_retries(
            client,
            google_page_url,
            headers={"Accept": "text/html"},
        )
        pdf_urls = {
            html.unescape(match.group("url"))
            for match in _GOOGLE_PDF_META_RE.finditer(google_page.text)
        }
        if len(pdf_urls) != 1:
            raise PatentPdfRecoveryError(
                f"Google patent citation PDF count is {len(pdf_urls)}; expected one"
            )
        mirror_url = next(iter(pdf_urls))
    else:
        mirror_url = cached_sources.mirror_pdf_url
    parsed_url = httpx.URL(mirror_url)
    if parsed_url.scheme != "https" or parsed_url.host != GOOGLE_PDF_HOST:
        raise PatentPdfRecoveryError("Google citation PDF URL is outside the allowed host")
    if cached_sources is None:
        mirror_response = await _get_with_retries(
            client,
            mirror_url,
            headers={"Accept": "application/pdf"},
        )
        mirror_pdf = mirror_response.content
    else:
        mirror_pdf = cached_sources.mirror_pdf
    _require_pdf(mirror_pdf, source="Google patent OCR PDF")

    official_reader = pypdf.PdfReader(io.BytesIO(official_pdf))
    mirror_reader = pypdf.PdfReader(io.BytesIO(mirror_pdf))
    if len(official_reader.pages) != len(mirror_reader.pages):
        raise PatentPdfRecoveryError("official and OCR PDFs have different page counts")
    page_count = len(official_reader.pages)
    mirror_texts = [page.extract_text() or "" for page in mirror_reader.pages]
    if not all(text.strip() for text in mirror_texts):
        raise PatentPdfRecoveryError("Google citation PDF lacks an OCR text layer on one or more pages")

    page_hashes: list[str] = []
    official_images: list[bytes] = []
    for page_number, (official_page, mirror_page) in enumerate(
        zip(official_reader.pages, mirror_reader.pages, strict=True),
        start=1,
    ):
        official_image = _page_image(
            official_page,
            source="USPTO",
            page_number=page_number,
        )
        mirror_image = _page_image(
            mirror_page,
            source="Google OCR",
            page_number=page_number,
        )
        official_raster = _decoded_raster(
            official_image,
            source=f"USPTO page {page_number}",
        )
        mirror_raster = _decoded_raster(
            mirror_image,
            source=f"Google OCR page {page_number}",
        )
        if (
            official_raster.shape != mirror_raster.shape
            or official_raster.dtype != mirror_raster.dtype
            or not np.array_equal(official_raster, mirror_raster)
        ):
            raise PatentPdfRecoveryError(
                f"official/OCR decoded page raster mismatch at page {page_number}"
            )
        page_hashes.append(_canonical_raster_sha256(official_image))
        official_images.append(official_image)

    if profile == "ability_two_lens_prescriptions_v1":
        role_pages = {
            "surface_ol1": _figure_page(
                mirror_texts,
                "2A",
                ("Lens", "Surface", "Curvature", "Thickness", "Abbe"),
            ),
            "asphere_ol1": _figure_page(
                mirror_texts,
                "2B",
                ("S7", "S8", "A6", "A16"),
            ),
            "surface_ol2": _figure_page(
                mirror_texts,
                "5",
                ("Lens", "Surface", "Curvature", "Thickness", "Abbe"),
            ),
            "system_meta": _figure_page(
                mirror_texts,
                "7",
                ("OL1", "OL2", "FOV", "FNO"),
            ),
        }
        parser_profile = None
        source_facts = None
    elif profile == _ABILITY_EIGHT_LENS_PROFILE:
        role_pages = {
            "surface_single": _figure_page(
                mirror_texts,
                "2",
                ("Surface", "Curvature", "Thickness", "Abbe", "Conic"),
            ),
            "asphere_single": _figure_page(
                mirror_texts,
                "3",
                ("Aspheric", "coefficient", "A4", "A16"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_eight_lens_source_facts(primary_html)
    elif profile == _ABILITY_THREE_LENS_PROFILE:
        role_pages = {
            "prescription_ol1": _figure_page(
                mirror_texts,
                "4A",
                ("surface", "curvature", "thickness", "abbe", "A16"),
            ),
            "prescription_ol2": _figure_page(
                mirror_texts,
                "5A",
                ("surface", "curvature", "thickness", "abbe", "A16"),
            ),
            "prescription_ol3": _figure_page(
                mirror_texts,
                "6A",
                ("surface", "curvature", "thickness", "abbe", "A16"),
            ),
            "system_meta_three": _figure_page(
                mirror_texts,
                "7",
                ("optical lens", "OL1", "OL3", "FNO", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_three_lens_source_facts(primary_html)
    elif profile == _ABILITY_TWO_FIVE_LENS_PROFILE:
        role_pages = {
            "prescription_five_ol1": _figure_page(
                mirror_texts,
                "3A",
                ("Surface", "Radius", "Thickness", "Abbe", "A12", "K"),
            ),
            "prescription_five_ol2": _figure_page(
                mirror_texts,
                "4A",
                ("Surface", "Radius", "Thickness", "Abbe", "A12", "K"),
            ),
            "system_meta_five": _figure_page(
                mirror_texts,
                "5",
                ("OL1", "OL2", "Fno", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_two_five_lens_source_facts(primary_html)
    elif profile == _ABILITY_TWO_NINE_LENS_PROFILE:
        role_pages = {
            "prescription_nine_ol1": _figure_page(
                mirror_texts,
                "4A",
                ("Surface", "Curvature", "Thickness", "Abbe", "K", "A12"),
            ),
            "prescription_nine_ol2": _figure_page(
                mirror_texts,
                "5A",
                ("Surface", "Curvature", "Thickness", "Abbe", "K", "A12"),
            ),
            "system_meta_nine": _figure_page(
                mirror_texts,
                "6",
                ("Optical lens OL1", "Optical lens OL2", "TTL", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_two_nine_lens_source_facts(primary_html)
    elif profile == _ABILITY_FOUR_EIGHT_LENS_PROFILE:
        role_pages = {
            "prescription_eight_ol1": _figure_page(
                mirror_texts,
                "2A",
                ("Surface", "Curvature", "Thickness", "Abbe", "A12"),
            ),
            "prescription_eight_ol2": _figure_page(
                mirror_texts,
                "4A",
                ("Surface", "Curvature", "Thickness", "Abbe", "A12"),
            ),
            "prescription_eight_ol3": _figure_page(
                mirror_texts,
                "6A",
                ("Surface", "Curvature", "Thickness", "Abbe", "A12"),
            ),
            "prescription_eight_ol4": _figure_page(
                mirror_texts,
                "8",
                ("Surface", "Curvature", "Thickness", "Abbe"),
            ),
            "system_meta_four_eight": _figure_page(
                mirror_texts,
                "9",
                ("Optical lens OL1", "Optical lens OL4", "F1", "R1"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_four_eight_lens_source_facts(primary_html)
    else:
        raise PatentPdfRecoveryError(f"unsupported Ability PDF profile: {profile}")
    if len(set(role_pages.values())) != len(role_pages):
        raise PatentPdfRecoveryError("Ability PDF key roles do not map to distinct pages")

    key_pages: list[tuple[int, str, str, str, list[dict[str, Any]]]] = []
    for role, page_index in sorted(role_pages.items(), key=lambda item: item[1]):
        key_pages.append(
            (
                page_index + 1,
                role,
                page_hashes[page_index],
                mirror_texts[page_index],
                _rapidocr_tokens(official_images[page_index]),
            )
        )
    parser_input = _canonical_parser_input(
        publication_id=publication_id,
        page_count=page_count,
        key_pages=key_pages,
        profile=parser_profile,
        source_facts=source_facts,
    )
    from importlib.metadata import version

    return PatentPdfOcrRecovery(
        publication_id=publication_id,
        official_pdf=official_pdf,
        official_pdf_url=official_url,
        mirror_pdf=mirror_pdf,
        mirror_pdf_url=mirror_url,
        parser_input=parser_input,
        page_count=page_count,
        page_image_sha256=tuple(page_hashes),
        key_page_numbers=tuple(page_index + 1 for page_index in role_pages.values()),
        pypdf_version=pypdf.__version__,
        rapidocr_version=version("rapidocr-onnxruntime"),
    )
