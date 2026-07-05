"""Convert USPTO embodiment prescription tables into staging Zemax files."""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

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
SUPPORTED_ASPHERE_ORDERS = {4, 6, 8, 10, 12, 14, 16}
ASPHERE_ORDER_TO_CODEV = {
    4: "A",
    6: "B",
    8: "C",
    10: "D",
    12: "E",
    14: "F",
    16: "G",
}
MATERIAL_TOKENS = {
    "PLASTIC",
    "GLASS",
    "CEMENTED",
    "RESIN",
    "FILTER",
    "CG",
    "IR",
    "IR-CUT",
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


@dataclass
class ConversionAttempt:
    patent_id: str
    title: str
    status: str
    reason: str
    zmx_path: str = ""
    efl_mm: float | None = None
    coverage: dict[str, Any] = field(default_factory=dict)


def normalize_patent_text(value: str) -> str:
    """Return PPUBS HTML/plain text normalized for deterministic regex parsing."""

    text = re.sub(r"<maths.*?</maths>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
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

    text = normalize_patent_text(raw_text)
    meta = _find_first_embodiment_meta(text)
    coeff_start = _find_required(text, "Aspheric Coefficients", meta.end())
    surface_table = _surface_table_text(text, meta.end(), coeff_start)
    surfaces = _parse_surface_table(surface_table)
    coefficients, unsupported = _parse_asphere_coefficients(text, coeff_start)
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
        embodiment=meta.group("embodiment"),
        focal_length_mm=_parse_number(meta.group("f")),
        f_number=_parse_number(meta.group("fno")),
        hfov_deg=_parse_number(meta.group("hfov")),
        surfaces=optical_surfaces,
        unsupported_asphere_terms=unsupported,
    )


def build_readout_from_prescription(prescription: PatentPrescription) -> CodeVReadout:
    """Build the existing CODE V readout DTO consumed by ``zmx_writer``."""

    semi_diameter = _derived_clear_aperture_mm(prescription)
    stop_surface = _stop_surface_index(prescription.surfaces)
    surfaces = tuple(
        CodeVSurfaceReadout(
            index=surface.index,
            radius_y_mm=_finite_or_zero(surface.radius_mm),
            thickness_mm=_finite_or_zero(surface.thickness_mm),
            semi_diameter_mm=semi_diameter,
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
        image_height_y_mm=prescription.image_height_mm,
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


async def run_conversion(
    *,
    pool_dir: Path,
    output_dir: Path,
    report_path: Path,
    target_successes: int,
    max_attempts: int,
) -> list[ConversionAttempt]:
    """Fetch USPTO HTML, parse prescriptions, write ZMX files, and report attempts."""

    candidates = load_patent_pool(pool_dir)
    attempts: list[ConversionAttempt] = []
    successes = 0
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=60) as client:
        token = await _ppubs_access_token(client)
        for candidate in candidates:
            if len(attempts) >= max_attempts or successes >= target_successes:
                break
            attempt = await _convert_candidate(client, token, candidate, output_dir)
            attempts.append(attempt)
            if attempt.status == "success":
                successes += 1
            await asyncio.sleep(0.25)

    _write_report(report_path, attempts, target_successes=target_successes)
    return attempts


async def _convert_candidate(
    client: httpx.AsyncClient,
    token: str,
    candidate: PatentCandidate,
    output_dir: Path,
) -> ConversionAttempt:
    try:
        page_html = await _fetch_patent_html(client, token, candidate.patent_id)
        prescription = parse_patent_prescription(page_html, patent_id=candidate.patent_id)
        readout = build_readout_from_prescription(prescription)
        output_path = output_dir / f"{_safe_stem(candidate.patent_id)}.zmx"
        write_zmx_from_codev_readout(
            readout,
            output_path,
            name=_safe_stem(candidate.patent_id),
        )
        optic = load_normalized_zmx(output_path)
        efl = float(optic.paraxial.f2())
        if not math.isfinite(efl):
            raise PatentParseError("generated ZMX loaded but EFL was not finite")
        return ConversionAttempt(
            patent_id=candidate.patent_id,
            title=candidate.title,
            status="success",
            reason="parsed and ingested",
            zmx_path=str(output_path.relative_to(ROOT)),
            efl_mm=efl,
            coverage=_coverage(prescription),
        )
    except Exception as exc:  # noqa: BLE001 - report per-patent failure reason
        return ConversionAttempt(
            patent_id=candidate.patent_id,
            title=candidate.title,
            status="failed",
            reason=f"{type(exc).__name__}: {exc}",
        )


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


def _find_first_embodiment_meta(text: str) -> re.Match[str]:
    number = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[-+]?\d+)?"
    pattern = re.compile(
        rf"(?P<embodiment>\d+(?:st|nd|rd|th)\s+Embodiment)\s+"
        rf"f\s*=\s*(?P<f>{number})\s*mm,?\s+"
        rf"Fno\s*=\s*(?P<fno>{number}),?\s+"
        rf"HFOV\s*=\s*(?P<hfov>{number})\s*deg",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if match is None:
        raise PatentParseError("first embodiment f/Fno/HFOV line not found")
    return match


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
            nd, pos = _consume_optional_number(tokens, pos)
            vd, pos = _consume_optional_number(tokens, pos)
            if pos < len(tokens) and not _is_next_surface_index(tokens[pos], index + 1):
                _, pos = _consume_optional_number(tokens, pos)
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
) -> tuple[dict[int, dict[str, float]], list[str]]:
    end = _find_coefficients_end(text, coeff_start)
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
    )
    ends = [
        match.start()
        for pattern in patterns
        if (match := re.search(pattern, tail, flags=re.IGNORECASE))
    ]
    return coeff_start + min(ends) if ends else len(text)


def _tokenize_table(text: str) -> list[str]:
    text = text.replace("(", " ").replace(")", " ").replace(",", " ")
    text = text.replace("=", " = ")
    return [token.strip() for token in text.split() if token.strip()]


def _tokenize_coefficients(text: str) -> list[str]:
    text = text.replace("=", " = ")
    text = text.replace(",", " ")
    return [token.strip() for token in text.split() if token.strip()]


def _consume_surface_label(tokens: list[str], pos: int) -> tuple[str, int]:
    if pos >= len(tokens):
        raise PatentParseError("unexpected end of surface row")
    token = tokens[pos]
    upper = token.upper()
    if upper == "LENS" and pos + 1 < len(tokens):
        return f"Lens {tokens[pos + 1]}", pos + 2
    if upper in {"APE.", "APE"} and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "STOP":
        return "Ape. Stop", pos + 2
    if upper == "IR-CUT" and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "FILTER":
        return "IR-cut filter", pos + 2
    if upper == "COVER" and pos + 1 < len(tokens) and tokens[pos + 1].upper() == "GLASS":
        return "Cover glass", pos + 2
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


def _distance_value(token: str, *, field_name: str) -> float | None:
    stripped = _strip_parens(token)
    upper = stripped.upper()
    if upper == "PLANO":
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
    cleaned = _strip_parens(token).replace(",", "").replace("−", "-")
    cleaned = cleaned.rstrip(".;")
    if not re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[-+]?\d+)?", cleaned, re.I):
        raise PatentParseError(f"not a number: {token}")
    value = float(cleaned)
    if not math.isfinite(value):
        raise PatentParseError(f"non-finite number: {token}")
    return value


def _coverage(prescription: PatentPrescription) -> dict[str, Any]:
    surfaces = prescription.surfaces
    asphere_surfaces = [surface for surface in surfaces if surface.asphere_coefficients]
    glass_rows = [surface for surface in surfaces if surface.nd is not None and surface.vd is not None]
    return {
        "surfaces": len(surfaces),
        "r": f"{sum(surface.radius_mm is not None for surface in surfaces)}/{len(surfaces)}",
        "d": f"{sum(surface.thickness_mm is not None for surface in surfaces)}/{len(surfaces)}",
        "nd_vd": f"{len(glass_rows)}/{len(surfaces)}",
        "asphere_surfaces": len(asphere_surfaces),
        "f_mm": prescription.focal_length_mm,
        "f_number": prescription.f_number,
        "hfov_deg": prescription.hfov_deg,
        "image_height_mm": prescription.image_height_mm,
        "semi_diameter_policy": "derived clear aperture from f/Fno/HFOV",
    }


def _write_report(
    report_path: Path,
    attempts: list[ConversionAttempt],
    *,
    target_successes: int,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    successes = [attempt for attempt in attempts if attempt.status == "success"]
    lines = [
        "# DATA-06a patent-to-ZMX spike report",
        "",
        f"- target_successes: {target_successes}",
        f"- attempts: {len(attempts)}",
        f"- successes: {len(successes)}",
        "- source: local data/patents/uspto-smartphone-batch*.jsonl + USPTO PPUBS HTML",
        "- parser: deterministic first-embodiment table parse; no numeric LLM fill",
        "- clear_aperture: derived from parsed f/Fno/HFOV only for ZMX DIAM/MEMA metadata",
        "",
        "## Per-patent attempts",
        "",
        "| patent | status | zmx | efl_mm | field coverage | reason |",
        "|---|---|---|---:|---|---|",
    ]
    for attempt in attempts:
        coverage = _format_coverage(attempt.coverage)
        efl = "" if attempt.efl_mm is None else f"{attempt.efl_mm:.6g}"
        lines.append(
            "| "
            + " | ".join(
                (
                    _md_cell(attempt.patent_id),
                    attempt.status,
                    _md_cell(attempt.zmx_path),
                    efl,
                    _md_cell(coverage),
                    _md_cell(attempt.reason),
                )
            )
            + " |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    )
    return "; ".join(f"{key}={coverage[key]}" for key in keys if key in coverage)


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _find_required(text: str, needle: str, start: int) -> int:
    index = text.lower().find(needle.lower(), start)
    if index < 0:
        raise PatentParseError(f"{needle!r} section not found")
    return index


def _material_token(token: str) -> bool:
    return _strip_parens(token).upper() in MATERIAL_TOKENS


def _strip_parens(token: str) -> str:
    return token.strip().strip("()")


def _is_empty_value(token: str) -> bool:
    return _strip_parens(token).upper() in {"-", "--", "---", "—", "N/A", "NA"}


def _is_next_surface_index(token: str, expected: int) -> bool:
    return token.isdigit() and int(token) == expected


def _stop_surface_index(surfaces: list[PatentSurface]) -> int:
    for surface in surfaces:
        if "APE" in surface.label.upper() and "STOP" in surface.label.upper():
            return surface.index
    for surface in surfaces:
        if surface.label.upper() == "STOP":
            return surface.index
    return surfaces[0].index


def _derived_clear_aperture_mm(prescription: PatentPrescription) -> float:
    image_height = abs(prescription.image_height_mm)
    entrance_radius = prescription.focal_length_mm / (2.0 * prescription.f_number)
    return max(1.0, image_height * 1.1, entrance_radius * 1.2)


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
    args = parser.parse_args()

    attempts = asyncio.run(
        run_conversion(
            pool_dir=args.pool_dir,
            output_dir=args.out_dir,
            report_path=args.report,
            target_successes=args.target_successes,
            max_attempts=args.max_attempts,
        )
    )
    successes = sum(attempt.status == "success" for attempt in attempts)
    return 0 if successes >= args.target_successes else 1


if __name__ == "__main__":
    sys.exit(main())
