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
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
import structlog


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.patent_crawl_config import (  # noqa: E402
    SMARTPHONE_LENS_PROFILE,
    has_three_to_seven_p_keyword,
)
from app.core.patent_crawl_schema import validate_patent_record  # noqa: E402


logger = structlog.get_logger(__name__)


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


async def _ppubs_search_docs(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    page_size: int,
) -> list[dict]:
    payload = {
        "cursorMarker": "*",
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
    return response.json().get("docs", [])


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


async def _records_for_uspto_query(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    page_size: int,
    max_records: int | None = None,
) -> list[PatentRecord]:
    docs = await _ppubs_search_docs(client, token, query, page_size)
    records: list[PatentRecord] = []
    for doc in docs:
        if max_records is not None and len(records) >= max_records:
            break
        document_id = str(doc.get("documentId") or "")
        source_type = str(doc.get("type") or "")
        if not document_id or not source_type:
            continue
        try:
            page_html = await _ppubs_patent_html(client, token, document_id, source_type)
            record = _ppubs_record_from_doc(doc, page_html)
            validate_patent_record(asdict(record))
        except Exception as exc:
            logger.warning("uspto_record_skipped", document_id=document_id, error=str(exc))
            continue
        records.append(record)
        await asyncio.sleep(0.8)
    return records


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


async def _async_main(args: argparse.Namespace) -> int:
    if args.dry_run:
        _write_jsonl(dry_run_records(), Path(args.out))
        return 0

    if args.source == "uspto":
        if args.profile == "smartphone" and not args.query:
            records = await search_uspto_smartphone(args.limit)
        else:
            query = args.query or SMARTPHONE_LENS_PROFILE.uspto_queries[0]
            records = await search_uspto(query, args.limit)
    elif args.source == "espacenet":
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

    _write_jsonl(records, Path(args.out))
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
        "--dry-run",
        action="store_true",
        help="No network — produce sample records for schema validation",
    )
    args = parser.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
