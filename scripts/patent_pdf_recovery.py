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
_LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT = (
    "FIG. 7 is TABLE 1 which lists the optical data of the first embodiment",
    "FIG. 8 is TABLE 2 which lists the aspheric surface data of the first embodiment",
    "FIG. 9 is TABLE 3 which lists the optical data of the second embodiment",
    "FIG. 10 is TABLE 4 which lists the aspheric surface data of the second embodiment",
    "FIG. 11 is TABLE 5 which lists the optical data of the third embodiment",
    "FIG. 12 is TABLE 6 which lists the aspheric surface data of the third embodiment",
    "FIG. 13 is TABLE 7 which lists the data of the respective embodiments",
)
_LARGAN_THREE_FIVE_LENS_PROFILE = "largan_three_five_lens_prescriptions_v1"
_ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT = (
    "FIG. 3 lists each lens parameter of the optical lens at the telescopic end "
    "shown in FIG. 1",
    "FIG. 4 lists each lens parameter of the optical lens at the wide-angle end "
    "shown in FIG. 2",
    "FIG. 5 lists aspheric coefficients of the mathematic equation of the aspheric "
    "lenses of the optical lens of FIG. 1",
    "FIG. 6 lists the specific parameters of the optical lens of FIG. 1",
)
_ABILITY_ZOOM_TWO_STATE_PROFILE = "ability_zoom_two_state_census_v1"
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
_CIRCLE_OPTICS_SEVEN_LENS_PROFILE = "circle_optics_seven_lens_ocr_review_v1"
_CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "f39a32f7a1eb5004447f43fc12e3bd60c06a55f4f4c50d26e4375e61b17bd154": {
        "application_number": "17/622463",
        "page_count": 66,
        "role_pages": {
            "circle_optics_surface_table": 16,
            "circle_optics_asphere_table": 17,
        },
    },
    "449f9a8e066cb4625dd38d76d737a711f216fb45195668f98c25f9c32cebabf4": {
        "application_number": "19/217645",
        "page_count": 66,
        "role_pages": {
            "circle_optics_surface_table": 15,
            "circle_optics_asphere_table": 16,
        },
    },
}
_GENIUS_FOUR_LENS_ELEVEN_OPTICAL_FIGURES = (2, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43)
_GENIUS_FOUR_LENS_ELEVEN_ASPHERE_FIGURES = (4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44)
_GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for embodiment, (optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_FOUR_LENS_ELEVEN_OPTICAL_FIGURES,
            _GENIUS_FOUR_LENS_ELEVEN_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
    for marker in (
        f"FIG. {optical_figure} shows a table of optical data of each lens element "
        f"of the optical imaging lens according to embodiment {embodiment} of the invention",
        f"FIG. {asphere_figure} shows a table of aspherical data of the optical imaging lens "
        f"according to embodiment {embodiment} of the invention",
    )
)
_GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS = (
    "FIG. 46 shows a comparison table",
    "all 11 example embodiments shown in FIGS. 1",
)
_GENIUS_FOUR_LENS_ELEVEN_PROFILE = "genius_four_lens_eleven_embodiment_census_v1"
_GENIUS_FOUR_LENS_ELEVEN_SOURCE_LAYOUTS: dict[str, dict[str, Any]] = {
    "0211f3fe1bdd3152ab6c57c25e4991603504980b37398c9ae5cbcb9812c43dea": {
        "page_count": 66,
        "drawing_page_offset": 1,
        "blank_mirror_pages": frozenset({6, 17, 21, 33, 45}),
    },
    "3b6a1046e050f84cd85e6e04efeee1a2ca96ff2450b1b810816733d7a3d03a73": {
        "page_count": 65,
        "drawing_page_offset": 1,
        "blank_mirror_pages": frozenset({48}),
    },
    "bdc8b8babf2e783d5c8bb49be17a1c79ff143aba871d0ac217edc6e63e8def6a": {
        "page_count": 66,
        "drawing_page_offset": 2,
        "blank_mirror_pages": frozenset({6, 7, 11, 19, 23, 27, 32, 50}),
    },
    "8b17a79c47cb8c9b589e62cba4097197485d1827ea7ed7147ba57da9f4ccd873": {
        "page_count": 65,
        "drawing_page_offset": 1,
        "blank_mirror_pages": frozenset({6, 10, 17, 30, 41, 42, 48}),
    },
}
_GENIUS_NINE_LENS_ELEVEN_ORDINALS = (
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
)
_GENIUS_NINE_LENS_ELEVEN_OPTICAL_FIGURES = tuple(8 + 4 * index for index in range(11))
_GENIUS_NINE_LENS_ELEVEN_ASPHERE_FIGURES = tuple(9 + 4 * index for index in range(11))
_GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for embodiment, (ordinal, optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_NINE_LENS_ELEVEN_ORDINALS,
            _GENIUS_NINE_LENS_ELEVEN_OPTICAL_FIGURES,
            _GENIUS_NINE_LENS_ELEVEN_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
    for marker in (
        (
            f"FIG. {optical_figure} depicts a table of optical data for each lens element "
            + (
                f"of {'an' if ordinal in {'eighth', 'eleventh'} else 'a'} {ordinal} "
                "embodiment of an optical imaging lens according to "
                if embodiment == 1 or embodiment >= 7
                else f"of the optical imaging lens of a {ordinal} embodiment of "
            )
            + "the present disclosure"
        ),
        f"FIG. {asphere_figure} depicts a table of aspherical data of "
        f"{'an' if ordinal in {'eighth', 'eleventh'} else 'a'} {ordinal} "
        "embodiment of the optical imaging lens according to the present disclosure",
    )
)
_GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS = (
    "FIGS. 50 A and 50 B depict tables for the values of",
    "of all eleven example embodiments",
)
_GENIUS_NINE_LENS_ELEVEN_PROFILE = "genius_nine_lens_eleven_embodiment_census_v1"
_GENIUS_EIGHT_LENS_FOURTEEN_ORDINALS = (
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
    "thirteenth",
    "fourteenth",
)
_GENIUS_EIGHT_LENS_FOURTEEN_DESIGNATORS = (
    "1 ′",
    "2 ′",
    "3 ′",
    "4 ′",
    "5 ′",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11 ′",
    "12 ′",
    "13 ′",
    "14 ′",
)
_GENIUS_EIGHT_LENS_FOURTEEN_OPTICAL_FIGURES = tuple(8 + 4 * index for index in range(14))
_GENIUS_EIGHT_LENS_FOURTEEN_ASPHERE_FIGURES = tuple(9 + 4 * index for index in range(14))
_GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for embodiment, (ordinal, designator, optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_EIGHT_LENS_FOURTEEN_ORDINALS,
            _GENIUS_EIGHT_LENS_FOURTEEN_DESIGNATORS,
            _GENIUS_EIGHT_LENS_FOURTEEN_OPTICAL_FIGURES,
            _GENIUS_EIGHT_LENS_FOURTEEN_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
    for marker in (
        f"FIG. {optical_figure} {'illustrates' if embodiment == 1 else 'shows'} an example "
        f"table of optical data of each lens element of the optical imaging lens {designator} "
        f"according to the {ordinal} example embodiment",
        f"FIG. {asphere_figure} {'depicts' if embodiment == 1 else 'shows'} an example table "
        f"of aspherical data of the optical imaging lens {designator} according to the "
        f"{ordinal} example embodiment",
    )
)
_GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS = (
    "FIG. 62 A and FIG. 62 B are tables for the values of",
    "of all embodiments",
    "the fourteen embodiments",
)
_GENIUS_EIGHT_LENS_FOURTEEN_PROFILE = (
    "genius_eight_lens_fourteen_embodiment_census_v1"
)
_GENIUS_FOUR_LENS_NINE_OPTICAL_FIGURES = (8, 12, 16, 20, 24, 28, 32, 36, 40)
_GENIUS_FOUR_LENS_NINE_ASPHERE_FIGURES = (9, 13, 17, 21, 25, 29, 33, 37, 41)
_GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"),
        _GENIUS_FOUR_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_FOUR_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows detailed optical data of the optical imaging lens of the "
        f"{ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows aspheric parameters of the optical imaging lens of the "
        f"{ordinal} embodiment of the disclosure",
    )
)
_GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS = (
    "FIG. 42 and FIG. 43 show values of important parameters and their relational expressions "
    "of the optical imaging lenses of the first to fifth embodiments of the disclosure",
    "FIG. 44 and FIG. 45 show values of important parameters and their relational expressions "
    "of the optical imaging lenses of the sixth to ninth embodiments of the disclosure",
)
_GENIUS_FOUR_LENS_NINE_PROFILE = "genius_four_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_FIVE_OPTICAL_FIGURES = (9, 13, 17, 21, 25)
_GENIUS_SIX_LENS_FIVE_ASPHERE_FIGURES = (10, 14, 18, 22, 26)
_GENIUS_SIX_LENS_FIVE_ORDINALS = ("first", "second", "third", "fourth", "fifth")
_GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_FIVE_ORDINALS,
        _GENIUS_SIX_LENS_FIVE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_FIVE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows detailed optical data of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows aspheric parameters of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
    )
)
_GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER = (
    "FIGS. 27 and 28 shows values of important parameters and relational expressions thereof "
    "of the optical lens assemblies according to the first to fifth embodiments of the disclosure"
)
_GENIUS_SIX_LENS_FIVE_PROFILE = "genius_six_lens_five_embodiment_census_v1"
_GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES = (9, 13, 17, 21, 25, 29, 33, 37, 41)
_GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES = (10, 14, 18, 22, 26, 30, 34, 38, 42)
_GENIUS_SIX_LENS_NINE_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
)
_GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_NINE_ORDINALS,
        _GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows the detailed optical data of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows the aspheric parameters of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
    )
)
_GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS = (
    "FIG. 43 shows the values of important parameters of the optical lens assembly and their "
    "relational values according to the first to the fifth embodiments of the disclosure",
    "FIG. 44 shows the values of important parameters of the optical lens assembly and their "
    "relational values according to the sixth to the ninth embodiments of the disclosure",
)
_GENIUS_SIX_LENS_NINE_PROFILE = "genius_six_lens_nine_embodiment_census_v1"
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ORDINALS = (
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
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_OPTICAL_FIGURES = tuple(
    26 + 2 * index for index in range(10)
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ASPHERE_FIGURES = tuple(
    27 + 2 * index for index in range(10)
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT = tuple(
    (
        f"The optical data of the {ordinal} embodiment of the optical imaging lens"
        f"{' 1' if embodiment == 1 else ''} are shown in FIG. {optical_figure} while the "
        f"aspheric surface data are shown in FIG. {asphere_figure} ."
    )
    for embodiment, (ordinal, optical_figure, asphere_figure) in enumerate(
        zip(
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ORDINALS,
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_OPTICAL_FIGURES,
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_ASPHERE_FIGURES,
            strict=True,
        ),
        start=1,
    )
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER = (
    "Some important ratios in each embodiment at the first focusing state or at the second "
    "focusing state are shown in FIG. 46 , in FIG. 47 , in FIG. 48 , and in FIG. 49 ."
)
_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE = (
    "genius_six_lens_ten_dual_focus_census_v1"
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_ORDINALS = (
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "nineth",
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_ORDINALS,
        _GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} shows detailed optical data of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
        f"FIG. {asphere_figure} shows aspheric parameters of the optical lens assembly "
        f"according to the {ordinal} embodiment of the disclosure",
    )
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS = (
    "FIG. 43 shows values of important parameters and relational expressions thereof of the "
    "optical lens assembly according to the first to third embodiments of the disclosure",
    "FIG. 44 shows values of important parameters and relational expressions thereof of the "
    "optical lens assembly according to the fourth to sixth embodiments of the disclosure",
    "FIG. 45 shows values of important parameters and relational expressions thereof of the "
    "optical lens assembly according to the seventh to nineth embodiments of the disclosure",
)
_GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE = (
    "genius_six_lens_nine_three_comparison_census_v1"
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT = tuple(
    marker
    for ordinal, optical_figure, asphere_figure in zip(
        _GENIUS_SIX_LENS_NINE_ORDINALS,
        _GENIUS_SIX_LENS_NINE_OPTICAL_FIGURES,
        _GENIUS_SIX_LENS_NINE_ASPHERE_FIGURES,
        strict=True,
    )
    for marker in (
        f"FIG. {optical_figure} illustrates "
        f"{'the ' if ordinal == 'ninth' else ''}detailed optical data of the optical lens "
        f"assembly according to the {ordinal} embodiment of the invention",
        f"FIG. {asphere_figure} illustrates "
        f"{'the ' if ordinal == 'ninth' else ''}aspheric parameters of the optical lens "
        f"assembly according to the {ordinal} embodiment of the invention",
    )
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS = (
    "FIG. 43 to FIG. 46 illustrate all important parameters and numerical values of relational "
    "expressions for the optical lens element assemblies according to the first to ninth "
    "embodiments of the invention",
    "FIG. 43 and FIG. 45",
    "FIG. 44 and FIG. 46",
)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_EXPECTED_COUNTS = (1, 5, 4)
_GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE = (
    "genius_six_lens_nine_four_comparison_census_v1"
)
_GENIUS_OFFICIAL_ONLY_PROFILES = frozenset(
    {
        _GENIUS_SIX_LENS_FIVE_PROFILE,
        _GENIUS_SIX_LENS_NINE_PROFILE,
        _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE,
        _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE,
        _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE,
        _GENIUS_FOUR_LENS_NINE_PROFILE,
        _GENIUS_NINE_LENS_ELEVEN_PROFILE,
        _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE,
        _CIRCLE_OPTICS_SEVEN_LENS_PROFILE,
    }
)
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
    mirror_pdf: bytes | None
    mirror_pdf_url: str | None
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
    mirror_pdf: bytes | None
    mirror_pdf_url: str | None


def _normalized_html_text(raw_html: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw_html))
    return re.sub(r"\s+", " ", text).strip()


def _ability_layout_profile(raw_html: str) -> str | None:
    """Return the exact source-proven Ability drawing-table profile."""

    text = _normalized_html_text(raw_html)
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    if digest in _CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS and all(
        marker in text for marker in _CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT
    ):
        return _CIRCLE_OPTICS_SEVEN_LENS_PROFILE
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
    if all(marker in text for marker in _LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT):
        return _LARGAN_THREE_FIVE_LENS_PROFILE
    if all(marker in text for marker in _ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT):
        return _ABILITY_ZOOM_TWO_STATE_PROFILE
    if all(marker in text for marker in _GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT) and all(
        marker in text for marker in _GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS
    ):
        return _GENIUS_FOUR_LENS_ELEVEN_PROFILE
    if all(
        marker in text for marker in _GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
    ) and all(marker in text for marker in _GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS):
        return _GENIUS_NINE_LENS_ELEVEN_PROFILE
    if all(
        marker in text for marker in _GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT
    ) and all(
        marker in text for marker in _GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS
    ):
        return _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE
    if all(marker in text for marker in _GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT) and all(
        marker in text for marker in _GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS
    ):
        return _GENIUS_FOUR_LENS_NINE_PROFILE
    if all(marker in text for marker in _GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT) and (
        _GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER in text
    ):
        return _GENIUS_SIX_LENS_FIVE_PROFILE
    if all(marker in text for marker in _GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT) and all(
        marker in text for marker in _GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS
    ):
        return _GENIUS_SIX_LENS_NINE_PROFILE
    if all(
        marker in text for marker in _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT
    ) and text.count(_GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER) == 1:
        return _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE
    if all(
        marker in text
        for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT
    ) and all(marker in text for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS):
        return _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE
    if all(
        marker in text for marker in _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT
    ) and all(
        text.count(marker) == expected
        for marker, expected in zip(
            _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS,
            _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_EXPECTED_COUNTS,
            strict=True,
        )
    ):
        return _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE
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


def _largan_three_five_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure exact official bindings for three Largan five-lens prescriptions."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" is TABLE", maxsplit=1)[0]: text.count(marker)
            for marker in _LARGAN_THREE_FIVE_LENS_REQUIRED_FIGURE_TEXT
        },
    }


def _ability_zoom_two_state_source_facts(raw_html: str) -> dict[str, Any]:
    """Measure exact bindings for one telescopic and one wide-angle prescription."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" lists", maxsplit=1)[0]: text.count(marker)
            for marker in _ABILITY_ZOOM_TWO_STATE_REQUIRED_FIGURE_TEXT
        },
    }


def circle_optics_seven_lens_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked layout for one Circle Optics publication."""

    layout = _CIRCLE_OPTICS_SEVEN_LENS_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Circle Optics seven-lens official HTML is not source-locked"
        )
    return layout


def _circle_optics_seven_lens_source_layout(raw_html: str) -> dict[str, Any]:
    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return circle_optics_seven_lens_source_layout_for_sha256(digest)


def _circle_optics_seven_lens_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind the source text which describes the image-only seven-lens tables."""

    text = _normalized_html_text(raw_html)
    layout = _circle_optics_seven_lens_source_layout(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "family_id": "74060373",
        "application_number": layout["application_number"],
        "required_text_counts": {
            marker: text.count(marker)
            for marker in _CIRCLE_OPTICS_SEVEN_LENS_REQUIRED_TEXT
        },
        "lens_element_count": 7,
        "aspheric_lens_element_count": 3,
        "f_number": 2.0,
        "nominal_focal_length_mm": 2.57,
        "aperture_stop_diameter_mm": 1.42,
        "track_length_mm": 50.0,
        "image_width_mm": 3.9,
        "design_wavelengths_nm": [450, 587, 656],
    }


def _genius_four_lens_eleven_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all eleven optical/asphere figure pairs and their Fno comparison table."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_ELEVEN_COMPARISON_MARKERS
        },
        "fno_label_count": len(re.findall(r"\bFno\b", text, flags=re.IGNORECASE)),
    }


def _genius_four_lens_eleven_source_layout(raw_html: str) -> dict[str, Any]:
    """Return an exact PDF layout pinned to one retained official HTML source."""

    digest = hashlib.sha256(raw_html.encode("utf-8")).hexdigest()
    return genius_four_lens_eleven_source_layout_for_sha256(digest)


def genius_four_lens_eleven_source_layout_for_sha256(
    digest: str,
) -> dict[str, Any]:
    """Return the source-locked PDF layout for an official HTML digest."""

    layout = _GENIUS_FOUR_LENS_ELEVEN_SOURCE_LAYOUTS.get(digest)
    if layout is None:
        raise PatentPdfRecoveryError(
            "Genius four-lens eleven-embodiment official HTML is not source-locked"
        )
    return layout


def _genius_four_lens_nine_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all nine four-lens figure pairs and four comparison figures."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_NINE_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker.split(" show", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_FOUR_LENS_NINE_COMPARISON_MARKERS
        },
    }


def _genius_nine_lens_eleven_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind eleven nine-lens optical/asphere pairs and two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" depicts", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_NINE_LENS_ELEVEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_NINE_LENS_ELEVEN_COMPARISON_MARKERS
        },
        "genius_applicant_assignee_count": text.count(
            "Genius Electronic Optical (Xiamen) Co., Ltd."
        ),
    }


def _genius_eight_lens_fourteen_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind fourteen eight-lens optical/asphere pairs and two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_EIGHT_LENS_FOURTEEN_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_EIGHT_LENS_FOURTEEN_COMPARISON_MARKERS
        },
        "genius_applicant_assignee_count": text.count(
            "Genius Electronic Optical (Xiamen) Co., Ltd."
        ),
    }


def _genius_six_lens_five_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all five optical/asphere pairs and their two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_FIVE_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_count": text.count(_GENIUS_SIX_LENS_FIVE_COMPARISON_MARKER),
    }


def _genius_six_lens_nine_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind all nine optical/asphere pairs and their two comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_COMPARISON_MARKERS
        },
    }


def _genius_six_lens_ten_dual_focus_source_facts(raw_html: str) -> dict[str, Any]:
    """Bind ten dual-focus optical/asphere pairs and four comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_count": text.count(
            _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_COMPARISON_MARKER
        ),
        "first_focusing_state_count": text.count("first focusing state"),
        "second_focusing_state_count": text.count("second focusing state"),
        "six_lens_element_claim_count": text.count(
            "optical imaging lens of six lens elements"
        ),
    }


def _genius_six_lens_nine_three_comparison_source_facts(
    raw_html: str,
) -> dict[str, Any]:
    """Bind the nine figure pairs and three comparison sheets."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker.split(" shows", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_MARKERS
        },
    }


def _genius_six_lens_nine_four_comparison_source_facts(
    raw_html: str,
) -> dict[str, Any]:
    """Bind the nine figure pairs and the four-sheet comparison references."""

    text = _normalized_html_text(raw_html)
    return {
        "primary_html_sha256": hashlib.sha256(raw_html.encode("utf-8")).hexdigest(),
        "figure_binding_counts": {
            marker.split(" illustrates", maxsplit=1)[0]: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_REQUIRED_FIGURE_TEXT
        },
        "comparison_binding_counts": {
            marker: text.count(marker)
            for marker in _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_MARKERS
        },
    }


async def _google_citation_pdf_urls(
    client: httpx.AsyncClient,
    google_page_url: str,
    *,
    profile: str,
) -> set[str]:
    """Return citation PDFs, allowing proven official-only profiles on Google 404."""

    try:
        google_page = await _get_with_retries(
            client,
            google_page_url,
            headers={"Accept": "text/html"},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and profile in _GENIUS_OFFICIAL_ONLY_PROFILES:
            return set()
        raise
    return {
        html.unescape(match.group("url"))
        for match in _GOOGLE_PDF_META_RE.finditer(google_page.text)
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


def _rapidocr_tokens(
    image_bytes: bytes,
    *,
    rotation: str | None = None,
) -> list[dict[str, Any]]:
    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise PatentPdfRecoveryError("official page image could not be decoded")
    if rotation == "clockwise_90":
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif rotation is not None:
        raise PatentPdfRecoveryError(f"unsupported RapidOCR rotation: {rotation}")
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
    rapidocr_rotation: str | None = None,
) -> bytes:
    pages: list[dict[str, Any]] = []
    for page_number, role, image_sha256, mirror_text, tokens in key_pages:
        page = {
            "page_number": page_number,
            "role": role,
            "official_image_sha256": image_sha256,
            "mirror_text": mirror_text,
            "rapidocr_tokens": tokens,
        }
        if rapidocr_rotation is not None:
            page["rapidocr_rotation"] = rapidocr_rotation
        pages.append(page)
    payload = {
        "schema_version": 1,
        "parser_family": "ability_official_pdf_ocr_v1",
        "publication_id": publication_id,
        "page_count": page_count,
        "pages": pages,
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
        pdf_urls = await _google_citation_pdf_urls(
            client,
            google_page_url,
            profile=profile,
        )
        if not pdf_urls and profile in _GENIUS_OFFICIAL_ONLY_PROFILES:
            mirror_url = None
        elif len(pdf_urls) != 1:
            raise PatentPdfRecoveryError(
                f"Google patent citation PDF count is {len(pdf_urls)}; expected one"
            )
        else:
            mirror_url = next(iter(pdf_urls))
    else:
        mirror_url = cached_sources.mirror_pdf_url
    if mirror_url is not None:
        parsed_url = httpx.URL(mirror_url)
        if parsed_url.scheme != "https" or parsed_url.host != GOOGLE_PDF_HOST:
            raise PatentPdfRecoveryError("Google citation PDF URL is outside the allowed host")
    if cached_sources is None and mirror_url is not None:
        mirror_response = await _get_with_retries(
            client,
            mirror_url,
            headers={"Accept": "application/pdf"},
        )
        mirror_pdf = mirror_response.content
    elif cached_sources is not None:
        mirror_pdf = cached_sources.mirror_pdf
    else:
        mirror_pdf = None
    if mirror_pdf is not None:
        _require_pdf(mirror_pdf, source="Google patent OCR PDF")
    if (mirror_pdf is None) != (mirror_url is None):
        raise PatentPdfRecoveryError("Google OCR PDF URL/content availability differs")

    genius_four_lens_layout: dict[str, Any] | None = None
    if profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        genius_four_lens_layout = _genius_four_lens_eleven_source_layout(primary_html)
        if mirror_pdf is None:
            raise PatentPdfRecoveryError("Genius mirror PDF is unavailable")
    circle_optics_layout: dict[str, Any] | None = None
    if profile == _CIRCLE_OPTICS_SEVEN_LENS_PROFILE:
        circle_optics_layout = _circle_optics_seven_lens_source_layout(primary_html)

    official_reader = pypdf.PdfReader(io.BytesIO(official_pdf))
    mirror_reader = pypdf.PdfReader(io.BytesIO(mirror_pdf)) if mirror_pdf is not None else None
    if mirror_reader is not None and len(official_reader.pages) != len(mirror_reader.pages):
        raise PatentPdfRecoveryError("official and OCR PDFs have different page counts")
    page_count = len(official_reader.pages)
    mirror_texts = (
        [page.extract_text() or "" for page in mirror_reader.pages]
        if mirror_reader is not None
        else [""] * page_count
    )
    blank_mirror_pages = {
        page_number
        for page_number, text in enumerate(mirror_texts, start=1)
        if not text.strip()
    }
    if profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        assert genius_four_lens_layout is not None
        expected_blank_pages = genius_four_lens_layout["blank_mirror_pages"]
        if blank_mirror_pages != expected_blank_pages:
            raise PatentPdfRecoveryError(
                "Genius OCR overlay blank-page set changed: actual="
                + ",".join(str(page) for page in sorted(blank_mirror_pages))
                + " expected="
                + ",".join(str(page) for page in sorted(expected_blank_pages))
            )
    elif profile in _GENIUS_OFFICIAL_ONLY_PROFILES:
        # This exact profile does not use mirror text. When an overlay is
        # published, every decoded raster is checked above; otherwise only the
        # official USPTO rasters are retained. Key pages always use RapidOCR.
        pass
    elif blank_mirror_pages:
        raise PatentPdfRecoveryError(
            "Google citation PDF lacks an OCR text layer on one or more pages"
        )

    page_hashes: list[str] = []
    official_images: list[bytes] = []
    for page_number, official_page in enumerate(official_reader.pages, start=1):
        official_image = _page_image(
            official_page,
            source="USPTO",
            page_number=page_number,
        )
        if mirror_reader is not None:
            mirror_image = _page_image(
                mirror_reader.pages[page_number - 1],
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

    rapidocr_rotation: str | None = None
    if profile == _CIRCLE_OPTICS_SEVEN_LENS_PROFILE:
        assert circle_optics_layout is not None
        if page_count != circle_optics_layout["page_count"]:
            raise PatentPdfRecoveryError(
                "Circle Optics seven-lens PDF page count changed: "
                f"actual={page_count} expected={circle_optics_layout['page_count']}"
            )
        role_pages = dict(circle_optics_layout["role_pages"])
        parser_profile = profile
        source_facts = _circle_optics_seven_lens_source_facts(primary_html)
        rapidocr_rotation = "clockwise_90"
    elif profile == "ability_two_lens_prescriptions_v1":
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
    elif profile == _LARGAN_THREE_FIVE_LENS_PROFILE:
        role_pages = {
            "largan_surface_1": _figure_page(
                mirror_texts,
                "7",
                ("TABLE 1", "Embodiment 1", "Surface #", "Fno", "HFOV"),
            ),
            "largan_asphere_1": _figure_page(
                mirror_texts,
                "8",
                ("TABLE 2", "Aspheric Coefficients", "Surface #", "A16"),
            ),
            "largan_surface_2": _figure_page(
                mirror_texts,
                "9",
                ("TABLE 3", "Embodiment 2", "Surface #", "Fno", "HFOV"),
            ),
            "largan_asphere_2": _figure_page(
                mirror_texts,
                "10",
                ("TABLE4", "Aspheric Coefficients", "Surface #", "A14"),
            ),
            "largan_surface_3": _figure_page(
                mirror_texts,
                "11",
                ("TABLE 5", "Embodiment 3", "Surface #", "Fno", "HFOV"),
            ),
            "largan_asphere_3": _figure_page(
                mirror_texts,
                "12",
                ("TABLE 6", "Aspheric Coefficients", "Surface #", "A14"),
            ),
            "largan_system_meta": _figure_page(
                mirror_texts,
                "13",
                ("TABLE 7", "Embodiment", "Fno", "HFOV", "TTL", "ImgH"),
            ),
        }
        parser_profile = profile
        source_facts = _largan_three_five_lens_source_facts(primary_html)
    elif profile == _ABILITY_ZOOM_TWO_STATE_PROFILE:
        role_pages = {
            "ability_zoom_telescopic": _figure_page(
                mirror_texts,
                "3",
                ("Surface", "Curvature", "Thickness", "Refractive", "Abbe"),
            ),
            "ability_zoom_wide": _figure_page(
                mirror_texts,
                "4",
                ("Surface", "Curvature", "Thickness", "Refractive", "Abbe"),
            ),
            "ability_zoom_asphere": _figure_page(
                mirror_texts,
                "5",
                ("K", "A2", "A4"),
            ),
            "ability_zoom_meta": _figure_page(
                mirror_texts,
                "6",
                ("Fw", "Ft", "TTL", "Fno", "FOV"),
            ),
        }
        parser_profile = profile
        source_facts = _ability_zoom_two_state_source_facts(primary_html)
    elif profile == _GENIUS_FOUR_LENS_ELEVEN_PROFILE:
        assert genius_four_lens_layout is not None
        expected_page_count = genius_four_lens_layout["page_count"]
        if page_count != expected_page_count:
            raise PatentPdfRecoveryError(
                "Genius eleven-embodiment PDF page count changed: "
                f"actual={page_count} expected={expected_page_count}"
            )
        drawing_page_offset = genius_four_lens_layout["drawing_page_offset"]
        role_sheets: dict[str, int] = {}
        for embodiment, (optical_figure, asphere_figure) in enumerate(
            zip(
                _GENIUS_FOUR_LENS_ELEVEN_OPTICAL_FIGURES,
                _GENIUS_FOUR_LENS_ELEVEN_ASPHERE_FIGURES,
                strict=True,
            ),
            start=1,
        ):
            role_sheets[f"genius_optical_{embodiment}"] = (
                2 if embodiment == 1 else optical_figure
            )
            role_sheets[f"genius_asphere_{embodiment}"] = asphere_figure
        role_sheets["genius_comparison"] = 46
        role_pages = {
            role: sheet + drawing_page_offset - 1
            for role, sheet in role_sheets.items()
        }
        for role, page_index in role_pages.items():
            sheet = role_sheets[role]
            mirror_text = mirror_texts[page_index]
            if mirror_text and f"Sheet {sheet} of 48" not in re.sub(
                r"\s+", " ", mirror_text
            ):
                raise PatentPdfRecoveryError(
                    f"Genius role {role} lacks its drawing-sheet header"
                )
        parser_profile = profile
        source_facts = _genius_four_lens_eleven_source_facts(primary_html)
    elif profile == _GENIUS_NINE_LENS_ELEVEN_PROFILE:
        if page_count != 65:
            raise PatentPdfRecoveryError(
                "Genius nine-lens eleven-embodiment PDF page count is not 65"
            )
        role_pages = {}
        for embodiment in range(1, 12):
            optical_page_index = 6 + (embodiment - 1) * 4
            role_pages[f"genius_nine_eleven_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_nine_eleven_asphere_{embodiment}"] = optical_page_index + 1
        role_pages["genius_nine_eleven_comparison_1"] = 48
        role_pages["genius_nine_eleven_comparison_2"] = 49
        parser_profile = profile
        source_facts = _genius_nine_lens_eleven_source_facts(primary_html)
    elif profile == _GENIUS_EIGHT_LENS_FOURTEEN_PROFILE:
        if page_count != 64:
            raise PatentPdfRecoveryError(
                "Genius eight-lens fourteen-embodiment PDF page count is not 64"
            )
        role_pages = {}
        for embodiment in range(1, 15):
            optical_page_index = 4 + (embodiment - 1) * 3
            role_pages[f"genius_eight_fourteen_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_eight_fourteen_asphere_{embodiment}"] = (
                optical_page_index + 1
            )
        role_pages["genius_eight_fourteen_comparison_1"] = 45
        role_pages["genius_eight_fourteen_comparison_2"] = 46
        parser_profile = profile
        source_facts = _genius_eight_lens_fourteen_source_facts(primary_html)
    elif profile == _GENIUS_FOUR_LENS_NINE_PROFILE:
        if page_count != 47:
            raise PatentPdfRecoveryError("Genius four-lens nine-embodiment PDF page count is not 47")
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 4 + (embodiment - 1) * 3
            role_pages[f"genius_four_nine_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_four_nine_asphere_{embodiment}"] = optical_page_index + 1
        for comparison in range(1, 5):
            role_pages[f"genius_four_nine_comparison_{comparison}"] = 29 + comparison
        parser_profile = profile
        source_facts = _genius_four_lens_nine_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_FIVE_PROFILE:
        if page_count != 34:
            raise PatentPdfRecoveryError("Genius five-embodiment PDF page count is not 34")
        role_pages = {}
        for embodiment, (optical_page_index, asphere_page_index) in enumerate(
            zip((5, 8, 11, 14, 17), (6, 9, 12, 15, 18), strict=True),
            start=1,
        ):
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = asphere_page_index
        role_pages["genius_six_comparison_1"] = 19
        role_pages["genius_six_comparison_2"] = 20
        parser_profile = profile
        source_facts = _genius_six_lens_five_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_NINE_PROFILE:
        if page_count not in {50, 51}:
            raise PatentPdfRecoveryError(
                "Genius nine-embodiment PDF page count is not retained 50/51 layout"
            )
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 5 + (embodiment - 1) * 3
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = optical_page_index + 1
        role_pages["genius_six_comparison_1"] = 31
        role_pages["genius_six_comparison_2"] = 32
        parser_profile = profile
        source_facts = _genius_six_lens_nine_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_TEN_DUAL_FOCUS_PROFILE:
        if page_count != 64:
            raise PatentPdfRecoveryError(
                "Genius ten-embodiment dual-focus PDF page count is not 64"
        )
        role_pages = {}
        for embodiment in range(1, 11):
            optical_page_index = 23 + (embodiment - 1) * 2
            role_pages[f"genius_six_ten_dual_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_ten_dual_asphere_{embodiment}"] = (
                optical_page_index + 1
            )
        for comparison in range(1, 5):
            role_pages[f"genius_six_ten_dual_comparison_{comparison}"] = 42 + comparison
        parser_profile = profile
        source_facts = _genius_six_lens_ten_dual_focus_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_NINE_THREE_COMPARISON_PROFILE:
        if page_count != 48:
            raise PatentPdfRecoveryError(
                "Genius three-comparison nine-embodiment PDF page count is not 48"
            )
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 5 + (embodiment - 1) * 3
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = optical_page_index + 1
        for comparison in range(1, 4):
            role_pages[f"genius_six_comparison_{comparison}"] = 30 + comparison
        parser_profile = profile
        source_facts = _genius_six_lens_nine_three_comparison_source_facts(primary_html)
    elif profile == _GENIUS_SIX_LENS_NINE_FOUR_COMPARISON_PROFILE:
        if page_count != 50:
            raise PatentPdfRecoveryError(
                "Genius four-comparison nine-embodiment PDF page count is not 50"
            )
        role_pages = {}
        for embodiment in range(1, 10):
            optical_page_index = 5 + (embodiment - 1) * 3
            role_pages[f"genius_six_optical_{embodiment}"] = optical_page_index
            role_pages[f"genius_six_asphere_{embodiment}"] = optical_page_index + 1
        for comparison in range(1, 5):
            role_pages[f"genius_six_comparison_{comparison}"] = 30 + comparison
        parser_profile = profile
        source_facts = _genius_six_lens_nine_four_comparison_source_facts(primary_html)
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
                _rapidocr_tokens(
                    official_images[page_index],
                    rotation=rapidocr_rotation,
                ),
            )
        )
    parser_input = _canonical_parser_input(
        publication_id=publication_id,
        page_count=page_count,
        key_pages=key_pages,
        profile=parser_profile,
        source_facts=source_facts,
        rapidocr_rotation=rapidocr_rotation,
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
