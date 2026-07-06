"""Patent crawler — pulls lens-design patents from USPTO + Espacenet.

Phase 0 deliverable: working CLI with --dry-run mode that exercises all paths
without needing API keys. Phase 3.1 runs the real ingestion once the Owner has
provided EPO_OPS_KEY / EPO_OPS_SECRET (see OWNER-CHECKLIST.md).

Usage:
    # Dry run (no network — schema validation + sample records)
    uv run python scripts/patent_crawler.py --dry-run --out data/sample.jsonl

    # Real USPTO search (Patent Public Search anonymous session; no credentials)
    uv run python scripts/patent_crawler.py --source uspto \\
        --profile smartphone --limit 30 \\
        --out data/patents/uspto-smartphone-batch1.jsonl

    # Real Espacenet search (needs EPO_OPS_KEY / EPO_OPS_SECRET in env)
    uv run python scripts/patent_crawler.py --source espacenet \\
        --query "imaging lens assembly" --limit 20 \\
        --out data/espacenet.jsonl

Output JSONL — one patent per line:
    {
      "id": "US20200333565A1",
      "title": "Optical Imaging Lens Assembly",
      "abstract": "...",
      "claim_excerpt": "first ~200 words of claim 1",
      "inventors": ["..."],
      "assignee": "Largan Precision Co., Ltd.",
      "ipc_classes": ["G02B 13/00", ...],
      "filing_date": "2020-04-21",
      "source": "uspto" | "espacenet" | "sample",
      "source_url": "https://patents.google.com/patent/..."
    }
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import structlog


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.patent_crawl_config import (  # noqa: E402
    SMARTPHONE_LENS_PROFILE,
    has_three_to_seven_p_keyword,
)
from app.core.patent_crawl_schema import validate_patent_record  # noqa: E402


logger = structlog.get_logger(__name__)

DEFAULT_PATENT_POOL_DIR = Path("data/patents")
PATENT_POOL_PATTERN = "uspto-smartphone-batch*.jsonl"
DEFAULT_CURSOR_PATH = DEFAULT_PATENT_POOL_DIR / "crawl-cursor.json"
IPC_SWEEP_CLASSES: tuple[str, ...] = (
    "G02B13/0045",
    "G02B9/60",
    "G02B9/62",
    "G02B9/64",
)
ASSIGNEE_QUOTA_FRACTION = 0.30
ASSIGNEE_QUOTA_MIN_POOL_SIZE = 10
F_FINGERPRINT_TOLERANCE_MM = 0.1
FNO_FINGERPRINT_TOLERANCE = 0.05


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass
class PatentRecord:
    id: str
    title: str
    abstract: str
    claim_excerpt: str
    inventors: list[str]
    assignee: str
    ipc_classes: list[str]
    filing_date: str | None
    source: str
    source_url: str
    family_hint: str | None = None


@dataclass
class CrawlFilterStats:
    seen: int = 0
    accepted: int = 0
    family_hint_tagged: int = 0
    family_duplicate_skipped: int = 0
    assignee_quota_skipped: int = 0


# ---------------------------------------------------------------------------
# Pool filters: family fingerprint dedupe + assignee quota
# ---------------------------------------------------------------------------


FamilyFingerprint = tuple[str, str, int | None, int | None]


def _record_mapping(record: PatentRecord | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(record, PatentRecord):
        return asdict(record)
    return record


def _normalize_words(value: str) -> str:
    text = unicodedata.normalize("NFKC", html.unescape(value)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_title(value: str) -> str:
    return _normalize_words(value)


def _normalize_assignee(value: str) -> str:
    text = _normalize_words(value)
    text = re.sub(
        r"\b(?:co|corp|corporation|inc|incorporated|ltd|limited|company|"
        r"technology|technologies|group)\b",
        " ",
        text,
    )
    text = re.sub(r"\s+", " ", text).strip()
    if "largan precision" in text:
        return "largan precision"
    if "zhejiang sunny" in text or "sunny optical" in text or "sunny optics" in text:
        return "sunny optical"
    if "genius electronic" in text or "gseo" in text:
        return "genius electronic optical"
    if "aac" in text:
        return "aac optics"
    if "samsung electro" in text:
        return "samsung electro mechanics"
    return text


def _record_text_for_numbers(record: PatentRecord | Mapping[str, Any]) -> str:
    data = _record_mapping(record)
    parts: list[str] = []
    for key in ("title", "abstract", "claim_excerpt"):
        value = data.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def _parse_float_token(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _first_number(patterns: tuple[str, ...], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = _parse_float_token(match.group("value"))
            if value is not None:
                return value
    return None


def _extract_f_fno(text: str) -> tuple[float | None, float | None]:
    compact = re.sub(r"\s+", " ", text)
    combined = re.search(
        r"\bf\s*/\s*f\s*no\.?(?:\s*/\s*h?fov)?\s*[:=]\s*"
        r"(?P<f>\d+(?:\.\d+)?)\s*/\s*(?P<fno>\d+(?:\.\d+)?)",
        compact,
        flags=re.IGNORECASE,
    )
    if combined:
        return _parse_float_token(combined.group("f")), _parse_float_token(
            combined.group("fno")
        )

    focal_length = _first_number(
        (
            r"\bfocal\s+length\s*(?:of|is|=|:)?\s*(?P<value>\d+(?:\.\d+)?)\s*mm\b",
            r"\befl\s*(?:of|around|is|=|:)?\s*(?P<value>\d+(?:\.\d+)?)\s*mm\b",
            r"\bf\s*(?:=|:)\s*(?P<value>\d+(?:\.\d+)?)\s*mm\b",
        ),
        compact,
    )
    f_number = _first_number(
        (
            r"\bf\s*/\s*#\s*(?:of|is|=|:)?\s*(?P<value>\d+(?:\.\d+)?)\b",
            r"\bf\s*no\.?\s*(?:of|is|=|:)?\s*(?P<value>\d+(?:\.\d+)?)\b",
            r"\bfno\s*(?:of|is|=|:)?\s*(?P<value>\d+(?:\.\d+)?)\b",
            r"\bf[-\s]?number\s*(?:of|is|=|:)?\s*(?P<value>\d+(?:\.\d+)?)\b",
            r"\bf\s*/\s*(?P<value>\d+(?:\.\d+)?)\b",
        ),
        compact,
    )
    return focal_length, f_number


def _quantize(value: float | None, tolerance: float) -> int | None:
    if value is None:
        return None
    return int(math.floor(value / tolerance + 0.5))


def family_fingerprint(record: PatentRecord | Mapping[str, Any]) -> FamilyFingerprint:
    """Build a near-duplicate family fingerprint from assignee, title, f, and Fno."""
    data = _record_mapping(record)
    title = data.get("title")
    assignee = data.get("assignee")
    focal_length, f_number = _extract_f_fno(_record_text_for_numbers(record))
    return (
        _normalize_assignee(assignee if isinstance(assignee, str) else ""),
        _normalize_title(title if isinstance(title, str) else ""),
        _quantize(focal_length, F_FINGERPRINT_TOLERANCE_MM),
        _quantize(f_number, FNO_FINGERPRINT_TOLERANCE),
    )


def _assignee_key(record: PatentRecord | Mapping[str, Any]) -> str:
    value = _record_mapping(record).get("assignee")
    return _normalize_assignee(value) if isinstance(value, str) else ""


def _record_id(record: PatentRecord | Mapping[str, Any]) -> str:
    value = _record_mapping(record).get("id")
    return str(value).strip() if value is not None else ""


def _family_hint_value(fingerprint: FamilyFingerprint, matched_record_id: str) -> str:
    assignee, title, focal_bin, fno_bin = fingerprint
    parts = [f"near_duplicate_of={matched_record_id or 'unknown'}"]
    if assignee:
        parts.append(f"assignee={assignee}")
    if title:
        parts.append(f"title={title[:80]}")
    if focal_bin is not None:
        parts.append(f"f_bin={focal_bin}")
    if fno_bin is not None:
        parts.append(f"fno_bin={fno_bin}")
    return "; ".join(parts)


def _would_exceed_assignee_quota(
    assignee: str,
    assignee_counts: Counter[str],
    total_count: int,
    *,
    max_share: float,
    min_pool_size: int,
) -> bool:
    if not assignee:
        return False
    projected_total = total_count + 1
    if projected_total < min_pool_size:
        return False
    return (assignee_counts[assignee] + 1) / projected_total > max_share


def filter_patent_records_by_pool(
    records: list[PatentRecord],
    existing_records: list[PatentRecord | Mapping[str, Any]],
    *,
    max_assignee_share: float = ASSIGNEE_QUOTA_FRACTION,
    quota_min_pool_size: int = ASSIGNEE_QUOTA_MIN_POOL_SIZE,
) -> tuple[list[PatentRecord], CrawlFilterStats]:
    """Apply all-pool family hints and assignee share quota."""
    stats = CrawlFilterStats()
    fingerprints: dict[FamilyFingerprint, str] = {}
    for record in existing_records:
        fingerprints.setdefault(family_fingerprint(record), _record_id(record))
    assignee_counts = Counter(
        assignee for record in existing_records if (assignee := _assignee_key(record))
    )
    total_count = len(existing_records)
    accepted: list[PatentRecord] = []

    for record in records:
        stats.seen += 1
        fingerprint = family_fingerprint(record)
        duplicate_of = fingerprints.get(fingerprint)
        record.family_hint = (
            _family_hint_value(fingerprint, duplicate_of) if duplicate_of is not None else None
        )

        assignee = _assignee_key(record)
        if _would_exceed_assignee_quota(
            assignee,
            assignee_counts,
            total_count,
            max_share=max_assignee_share,
            min_pool_size=quota_min_pool_size,
        ):
            stats.assignee_quota_skipped += 1
            continue

        accepted.append(record)
        stats.accepted += 1
        if record.family_hint is not None:
            stats.family_hint_tagged += 1
        else:
            fingerprints.setdefault(fingerprint, _record_id(record))
        if assignee:
            assignee_counts[assignee] += 1
        total_count += 1

    return accepted, stats


def load_patent_pool_records(
    pool_dir: Path = DEFAULT_PATENT_POOL_DIR,
    *,
    pattern: str = PATENT_POOL_PATTERN,
    exclude: Path | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    excluded = exclude.resolve() if exclude is not None else None
    for path in sorted(pool_dir.glob(pattern)):
        if excluded is not None and path.resolve() == excluded:
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# USPTO -- Patent Public Search anonymous API
# ---------------------------------------------------------------------------

PPUBS_BASE_URL = "https://ppubs.uspto.gov"
PPUBS_SESSION_URL = f"{PPUBS_BASE_URL}/api/users/me/session"
PPUBS_SEARCH_URL = f"{PPUBS_BASE_URL}/api/searches/generic"
PPUBS_TEXT_URL = f"{PPUBS_BASE_URL}/api/patents/html"
PPUBS_DATABASE_FILTERS = (
    {"databaseName": "USPAT"},
    {"databaseName": "US-PGPUB"},
    {"databaseName": "USOCR"},
)


@dataclass(frozen=True)
class PpubsSearchPage:
    docs: list[dict[str, Any]]
    next_cursor: str | None


async def _ppubs_access_token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        PPUBS_SESSION_URL,
        content="-1",
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    token = response.headers.get("x-access-token")
    if not token:
        raise RuntimeError("USPTO PPUBS did not return an anonymous access token")
    return token


async def _ppubs_search_page(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    page_size: int,
    cursor_marker: str = "*",
) -> PpubsSearchPage:
    payload = {
        "cursorMarker": cursor_marker,
        "databaseFilters": list(PPUBS_DATABASE_FILTERS),
        "fields": [
            "documentId",
            "patentNumber",
            "title",
            "datePublished",
            "inventors",
            "pageCount",
            "type",
        ],
        "op": "OR",
        "pageSize": page_size,
        "q": query,
        "searchType": 0,
        "sort": "date_publ desc",
    }
    response = await client.post(
        PPUBS_SEARCH_URL,
        json=payload,
        headers={"Accept": "application/json", "x-access-token": token},
    )
    response.raise_for_status()
    payload_json = response.json()
    docs = payload_json.get("docs", [])
    next_cursor = (
        payload_json.get("nextCursorMarker")
        or payload_json.get("nextCursorMark")
        or payload_json.get("cursorMark")
    )
    if not isinstance(next_cursor, str) or not next_cursor or next_cursor == cursor_marker:
        next_cursor = None
    return PpubsSearchPage(docs=docs, next_cursor=next_cursor)


async def _ppubs_search_docs(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    page_size: int,
) -> list[dict]:
    return (await _ppubs_search_page(client, token, query, page_size)).docs


async def _ppubs_patent_html(
    client: httpx.AsyncClient,
    token: str,
    document_id: str,
    source_type: str,
) -> str:
    for attempt in range(4):
        response = await client.get(
            f"{PPUBS_TEXT_URL}/{document_id}",
            params={"source": source_type, "requestToken": token},
            headers={"Accept": "text/html", "x-access-token": token},
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response.text
        await asyncio.sleep(5 * (attempt + 1))
    response.raise_for_status()
    return response.text


def _exception_diagnostics(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    http_status = status_code if isinstance(status_code, int) else None
    error = str(exc).strip() or repr(exc)
    if http_status is not None:
        failure_reason = f"http_{http_status}"
    elif isinstance(exc, httpx.TimeoutException):
        failure_reason = "timeout"
    elif isinstance(exc, httpx.RequestError):
        failure_reason = "request_error"
    else:
        failure_reason = type(exc).__name__
    return {
        "error": error,
        "error_type": type(exc).__name__,
        "http_status": http_status,
        "failure_reason": failure_reason,
    }


def _record_skip(
    document_id: str,
    exc: Exception,
    *,
    stage: str,
    skip_reason_counts: Counter[str] | None,
) -> None:
    diagnostics = _exception_diagnostics(exc)
    if skip_reason_counts is not None:
        skip_reason_counts[diagnostics["failure_reason"]] += 1
    logger.warning(
        "uspto_record_skipped",
        document_id=document_id,
        stage=stage,
        **diagnostics,
    )


def _strip_html(value: str) -> str:
    text = re.sub(r"<maths.*?</maths>", " ", value, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _section_text(page_html: str, heading: str) -> str:
    match = re.search(
        rf"<h3[^>]*>\s*{re.escape(heading)}\s*</h3>\s*<p>(.*?)</p>",
        page_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return _strip_html(match.group(1)) if match else ""


def _labeled_text(page_html: str, label: str) -> str:
    match = re.search(
        rf">\s*{re.escape(label)}:\s*</p>\s*<p[^>]*>(.*?)</p>",
        page_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return ""
    text = _strip_html(match.group(1))
    return re.sub(r"\s+\([^)]*\)$", "", text).strip()


def _classification_codes(page_html: str) -> list[str]:
    marker = re.search(
        r"<h3[^>]*>\s*Publication Classification\s*</h3>(.*?)(?:</section>|<h3)",
        page_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    block = marker.group(1) if marker else page_html
    codes = re.findall(r"\b[A-HY]\d{2}[A-Z]\s?\d+/\d+\b", _strip_html(block))
    return sorted(set(code.replace(" ", "") for code in codes))


def _claim_excerpt(page_html: str) -> str:
    text = _section_text(page_html, "Claims")
    return text[:1200].strip()


def _ppubs_record_from_doc(doc: dict, page_html: str) -> PatentRecord:
    document_id = str(doc.get("documentId") or "")
    assignee = _labeled_text(page_html, "Assignee") or _labeled_text(page_html, "Applicant")
    return PatentRecord(
        id=document_id,
        title=str(doc.get("title") or ""),
        abstract=_section_text(page_html, "Abstract"),
        claim_excerpt=_claim_excerpt(page_html),
        inventors=[str(doc.get("inventors") or "").strip()],
        assignee=assignee,
        ipc_classes=_classification_codes(page_html),
        filing_date=_labeled_text(page_html, "Filed") or str(doc.get("datePublished") or ""),
        source="uspto",
        source_url=f"{PPUBS_BASE_URL}/dirsearch-public/print/downloadPdf/{document_id}",
    )


async def _record_for_ppubs_doc(
    client: httpx.AsyncClient,
    token: str,
    doc: dict[str, Any],
    *,
    skip_reason_counts: Counter[str] | None = None,
) -> PatentRecord | None:
    document_id = str(doc.get("documentId") or "")
    source_type = str(doc.get("type") or "")
    if not document_id or not source_type:
        return None
    try:
        page_html = await _ppubs_patent_html(client, token, document_id, source_type)
    except Exception as exc:
        _record_skip(
            document_id,
            exc,
            stage="fetch",
            skip_reason_counts=skip_reason_counts,
        )
        return None

    await asyncio.sleep(0.8)

    try:
        record = _ppubs_record_from_doc(doc, page_html)
        validate_patent_record(asdict(record))
    except Exception as exc:
        _record_skip(
            document_id,
            exc,
            stage="parse",
            skip_reason_counts=skip_reason_counts,
        )
        return None
    return record


async def _records_from_ppubs_docs(
    client: httpx.AsyncClient,
    token: str,
    docs: list[dict[str, Any]],
    max_records: int | None = None,
    *,
    skip_reason_counts: Counter[str] | None = None,
) -> list[PatentRecord]:
    records: list[PatentRecord] = []
    for doc in docs:
        if max_records is not None and len(records) >= max_records:
            break
        record = await _record_for_ppubs_doc(
            client,
            token,
            doc,
            skip_reason_counts=skip_reason_counts,
        )
        if record is not None:
            records.append(record)
    return records


async def _records_for_uspto_query(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    page_size: int,
    max_records: int | None = None,
) -> list[PatentRecord]:
    docs = await _ppubs_search_docs(client, token, query, page_size)
    return await _records_from_ppubs_docs(client, token, docs, max_records=max_records)


async def search_uspto(query: str, limit: int) -> list[PatentRecord]:
    """Search USPTO Patent Public Search for a free-text query."""
    async with httpx.AsyncClient(timeout=60) as client:
        token = await _ppubs_access_token(client)
        page_size = min(max(limit, 50), 100)
        return (
            await _records_for_uspto_query(client, token, query, page_size, max_records=limit)
        )[:limit]


async def search_uspto_smartphone(limit: int) -> list[PatentRecord]:
    """Run the DATA-02a smartphone-lens query profile against USPTO."""
    records_by_id: dict[str, PatentRecord] = {}
    async with httpx.AsyncClient(timeout=60) as client:
        token = await _ppubs_access_token(client)
        for query in SMARTPHONE_LENS_PROFILE.uspto_queries:
            needed = max(limit - len(records_by_id), 0)
            if needed == 0:
                break
            for record in await _records_for_uspto_query(
                client,
                token,
                query,
                page_size=50,
                max_records=max(needed, 5),
            ):
                records_by_id.setdefault(record.id, record)
            hits = [
                record
                for record in records_by_id.values()
                if has_three_to_seven_p_keyword(
                    "\n".join((record.title, record.abstract, record.claim_excerpt))
                )
            ]
            if len(hits) >= limit:
                break

    records = list(records_by_id.values())
    hits = [
        record
        for record in records
        if has_three_to_seven_p_keyword("\n".join((record.title, record.abstract, record.claim_excerpt)))
    ]
    misses = [record for record in records if record not in hits]
    return (hits + misses)[:limit]


def _ipc_sweep_query(ipc_class: str) -> str:
    return (
        f'"{ipc_class}" AND '
        '("optical imaging lens assembly" OR "imaging lens assembly" OR "camera optical lens")'
    )


def _load_ipc_cursor(cursor_path: Path) -> dict[str, Any]:
    if cursor_path.is_file():
        with cursor_path.open(encoding="utf-8") as handle:
            cursor = json.load(handle)
    else:
        cursor = {}

    ipc_classes = list(cursor.get("ipc_classes") or IPC_SWEEP_CLASSES)
    cursor_by_ipc = cursor.get("cursor_by_ipc")
    if not isinstance(cursor_by_ipc, dict):
        cursor_by_ipc = {}
    exhausted = cursor.get("exhausted")
    if not isinstance(exhausted, list):
        exhausted = []
    return {
        "ipc_classes": ipc_classes,
        "class_index": int(cursor.get("class_index") or 0) % len(ipc_classes),
        "cursor_by_ipc": {
            ipc: str(cursor_by_ipc.get(ipc) or "*") for ipc in ipc_classes
        },
        "exhausted": [str(item) for item in exhausted if str(item) in ipc_classes],
    }


def _save_ipc_cursor(cursor_path: Path, cursor: Mapping[str, Any]) -> None:
    cursor_path.parent.mkdir(parents=True, exist_ok=True)
    with cursor_path.open("w", encoding="utf-8") as handle:
        json.dump(dict(cursor), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _next_ipc_cursor_class(cursor: Mapping[str, Any]) -> tuple[int, str] | None:
    ipc_classes = list(cursor["ipc_classes"])
    exhausted = set(cursor["exhausted"])
    start_index = int(cursor["class_index"]) % len(ipc_classes)
    for offset in range(len(ipc_classes)):
        index = (start_index + offset) % len(ipc_classes)
        ipc_class = ipc_classes[index]
        if ipc_class not in exhausted:
            return index, ipc_class
    return None


def _add_stats(total: CrawlFilterStats, current: CrawlFilterStats) -> None:
    total.seen += current.seen
    total.accepted += current.accepted
    total.family_hint_tagged += current.family_hint_tagged
    total.family_duplicate_skipped += current.family_duplicate_skipped
    total.assignee_quota_skipped += current.assignee_quota_skipped


async def search_uspto_ipc_sweep(
    limit: int,
    *,
    cursor_path: Path = DEFAULT_CURSOR_PATH,
    existing_records: list[PatentRecord | Mapping[str, Any]] | None = None,
    page_size: int = 50,
) -> list[PatentRecord]:
    """Sweep configured IPC classes one page at a time, resuming from cursor_path."""
    accepted: list[PatentRecord] = []
    accepted_ids: set[str] = set()
    pool_records: list[PatentRecord | Mapping[str, Any]] = list(existing_records or [])
    total_stats = CrawlFilterStats()
    record_skip_reasons: Counter[str] = Counter()

    cursor = _load_ipc_cursor(cursor_path)
    async with httpx.AsyncClient(timeout=60) as client:
        token = await _ppubs_access_token(client)
        while len(accepted) < limit:
            next_class = _next_ipc_cursor_class(cursor)
            if next_class is None:
                break

            class_index, ipc_class = next_class
            cursor_marker = cursor["cursor_by_ipc"].get(ipc_class, "*")
            page = await _ppubs_search_page(
                client,
                token,
                _ipc_sweep_query(ipc_class),
                page_size,
                cursor_marker=cursor_marker,
            )
            page_records = await _records_from_ppubs_docs(
                client,
                token,
                page.docs,
                skip_reason_counts=record_skip_reasons,
            )
            page_records = [record for record in page_records if record.id not in accepted_ids]
            filtered, stats = filter_patent_records_by_pool(page_records, pool_records)
            _add_stats(total_stats, stats)

            for record in filtered:
                accepted.append(record)
                accepted_ids.add(record.id)
                pool_records.append(record)
                if len(accepted) >= limit:
                    break

            if page.next_cursor is None:
                exhausted = set(cursor["exhausted"])
                exhausted.add(ipc_class)
                cursor["exhausted"] = sorted(exhausted)
            else:
                cursor["cursor_by_ipc"][ipc_class] = page.next_cursor
            cursor["class_index"] = (class_index + 1) % len(cursor["ipc_classes"])
            _save_ipc_cursor(cursor_path, cursor)

            if not page.docs and page.next_cursor is None:
                continue

    logger.info(
        "ipc_sweep_finished",
        accepted=len(accepted),
        seen=total_stats.seen,
        family_hint_tagged=total_stats.family_hint_tagged,
        family_duplicate_skipped=total_stats.family_duplicate_skipped,
        assignee_quota_skipped=total_stats.assignee_quota_skipped,
        record_skip_reasons=dict(sorted(record_skip_reasons.items())),
        cursor_path=str(cursor_path),
    )
    return accepted[:limit]


# ---------------------------------------------------------------------------
# Espacenet OPS (OAuth2 client credentials)
# ---------------------------------------------------------------------------

EPO_OPS_BASE = "https://ops.epo.org/3.2/rest-services"
EPO_OPS_AUTH = "https://ops.epo.org/3.2/auth/accesstoken"


async def _epo_token(key: str, secret: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            EPO_OPS_AUTH,
            auth=(key, secret),
            data={"grant_type": "client_credentials"},
        )
        r.raise_for_status()
        return r.json()["access_token"]


async def search_espacenet(
    query: str, limit: int, key: str, secret: str
) -> list[PatentRecord]:
    """Search Espacenet OPS by title/abstract. Returns minimal biblio records."""
    token = await _epo_token(key, secret)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        r = await client.get(
            f"{EPO_OPS_BASE}/published-data/search",
            params={
                "q": f"ti={query} or ab={query}",
                "Range": f"1-{limit}",
            },
        )
        r.raise_for_status()
        data = r.json()

    # OPS JSON is deeply nested. Minimal parse — biblio detail can be fetched
    # per-record in Phase 3.1 with a follow-up /published-data/publication call.
    biblios = (
        data.get("ops:world-patent-data", {})
        .get("ops:biblio-search", {})
        .get("ops:search-result", {})
        .get("ops:publication-reference", [])
    )
    if isinstance(biblios, dict):
        biblios = [biblios]

    records: list[PatentRecord] = []
    for b in biblios[:limit]:
        doc_id = b.get("document-id", {})
        cc = (doc_id.get("country") or {}).get("$", "")
        num = (doc_id.get("doc-number") or {}).get("$", "")
        kind = (doc_id.get("kind") or {}).get("$", "")
        full_id = f"{cc}{num}{kind}"
        records.append(
            PatentRecord(
                id=full_id,
                title="",
                abstract="",
                claim_excerpt="",
                inventors=[],
                assignee="",
                ipc_classes=[],
                filing_date=None,
                source="espacenet",
                source_url=f"https://worldwide.espacenet.com/patent/search/family/?q={full_id}",
            )
        )
    return records


# ---------------------------------------------------------------------------
# Dry-run sample (smartphone-telephoto lens patents — public knowledge)
# ---------------------------------------------------------------------------

SAMPLE_RECORDS: list[PatentRecord] = [
    PatentRecord(
        id="US20200333565A1",
        title="Optical Imaging Lens Assembly",
        abstract=(
            "An optical imaging lens assembly includes seven lens elements with "
            "refractive power, arranged in order from object side to image side. "
            "The lens assembly satisfies miniaturization for smartphone telephoto "
            "modules with an EFL of around 7mm and F/# of 2.4."
        ),
        claim_excerpt=(
            "An optical imaging lens assembly comprising, in order from an object "
            "side to an image side: a first lens element with positive refractive "
            "power having a convex object-side surface in a paraxial region thereof; "
            "a second lens element with refractive power; a third lens element with "
            "refractive power; a fourth lens element with refractive power; a fifth "
            "lens element with refractive power; a sixth lens element with refractive "
            "power; and a seventh lens element with refractive power having a concave "
            "image-side surface in a paraxial region thereof; wherein the lens "
            "assembly has a total of seven lens elements with refractive power."
        ),
        inventors=["Po-Lun Chen", "Hsin-Hsuan Huang"],
        assignee="Largan Precision Co., Ltd.",
        ipc_classes=["G02B 13/00", "G02B 27/00", "G02B 9/64"],
        filing_date="2020-04-21",
        source="sample",
        source_url="https://patents.google.com/patent/US20200333565A1",
    ),
    PatentRecord(
        id="US20210311293A1",
        title="Imaging Lens Assembly and Electronic Device",
        abstract=(
            "An imaging lens assembly includes six lens elements. The configuration "
            "yields a compact telephoto module suitable for smartphone integration "
            "with EFL around 12mm."
        ),
        claim_excerpt=(
            "An imaging lens assembly comprising six lens elements, in order from "
            "the object side to the image side: a first lens element with positive "
            "refractive power..."
        ),
        inventors=["Wei-Yu Chen"],
        assignee="Largan Precision Co., Ltd.",
        ipc_classes=["G02B 13/00", "G02B 13/18"],
        filing_date="2021-04-08",
        source="sample",
        source_url="https://patents.google.com/patent/US20210311293A1",
    ),
    PatentRecord(
        id="US20220197099A1",
        title="Optical Imaging System",
        abstract=(
            "An optical imaging system suitable for compact electronic devices, "
            "with TTL (total track length) under 5mm and a wide aperture of F/1.7. "
            "Designed for ultra-wide smartphone modules."
        ),
        claim_excerpt="An optical imaging system comprising five lens elements...",
        inventors=["Yu-Chen Lin"],
        assignee="Sunny Optical Technology (Group) Co., Ltd.",
        ipc_classes=["G02B 13/00"],
        filing_date="2022-01-15",
        source="sample",
        source_url="https://patents.google.com/patent/US20220197099A1",
    ),
]


def dry_run_records() -> list[PatentRecord]:
    return SAMPLE_RECORDS


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_jsonl(records: list[PatentRecord], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            data = asdict(r)
            validate_patent_record(data)
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
    logger.info("wrote_jsonl", path=str(out_path), count=len(records))


def _apply_pool_filters_for_output(
    records: list[PatentRecord],
    *,
    out_path: Path,
    pool_dir: Path,
) -> list[PatentRecord]:
    existing_records = load_patent_pool_records(pool_dir, exclude=out_path)
    filtered, stats = filter_patent_records_by_pool(records, existing_records)
    logger.info(
        "crawl_filters_applied",
        seen=stats.seen,
        accepted=stats.accepted,
        family_hint_tagged=stats.family_hint_tagged,
        family_duplicate_skipped=stats.family_duplicate_skipped,
        assignee_quota_skipped=stats.assignee_quota_skipped,
        existing_pool_count=len(existing_records),
    )
    return filtered


async def _async_main(args: argparse.Namespace) -> int:
    if args.dry_run:
        _write_jsonl(dry_run_records(), Path(args.out))
        return 0

    out_path = Path(args.out)
    pool_dir = Path(args.pool_dir)

    if args.source == "uspto":
        if args.ipc_sweep:
            existing_records = load_patent_pool_records(pool_dir, exclude=out_path)
            records = await search_uspto_ipc_sweep(
                args.limit,
                cursor_path=Path(args.cursor_file),
                existing_records=existing_records,
                page_size=args.page_size,
            )
        elif args.profile == "smartphone" and not args.query:
            records = await search_uspto_smartphone(args.limit)
        else:
            query = args.query or SMARTPHONE_LENS_PROFILE.uspto_queries[0]
            records = await search_uspto(query, args.limit)
        if not args.ipc_sweep:
            records = _apply_pool_filters_for_output(records, out_path=out_path, pool_dir=pool_dir)
    elif args.source == "espacenet":
        if args.ipc_sweep:
            logger.error("ipc_sweep_requires_uspto_source")
            return 2
        key = os.environ.get("EPO_OPS_KEY")
        secret = os.environ.get("EPO_OPS_SECRET")
        if not key or not secret:
            logger.error(
                "epo_ops_credentials_missing",
                hint="set EPO_OPS_KEY and EPO_OPS_SECRET in environment",
            )
            return 2
        records = await search_espacenet(args.query, args.limit, key, secret)
    else:
        logger.error("unknown_source", source=args.source)
        return 2

    if not records:
        logger.warning("no_records_found", query=args.query, profile=args.profile)
        return 1

    _write_jsonl(records, out_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patent crawler for Lumira Atelier RAG library"
    )
    parser.add_argument(
        "--source", choices=["uspto", "espacenet"], default="uspto"
    )
    parser.add_argument(
        "--profile",
        choices=["smartphone", "custom"],
        default="smartphone",
        help="Use the DATA-02a smartphone lens query profile unless --query is supplied",
    )
    parser.add_argument("--query", default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--out",
        default=f"data/patents-{datetime.now():%Y%m%d-%H%M%S}.jsonl",
    )
    parser.add_argument(
        "--pool-dir",
        default=str(DEFAULT_PATENT_POOL_DIR),
        help="Existing JSONL pool used for family fingerprint dedupe and assignee quotas",
    )
    parser.add_argument(
        "--ipc-sweep",
        action="store_true",
        help="Sweep configured IPC classes page by page with a persistent cursor",
    )
    parser.add_argument(
        "--cursor-file",
        default=str(DEFAULT_CURSOR_PATH),
        help="JSON cursor file for --ipc-sweep resume state",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=50,
        help="USPTO page size for --ipc-sweep",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No network — produce sample records for schema validation",
    )
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
