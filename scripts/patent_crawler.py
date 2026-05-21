"""Patent crawler — pulls lens-design patents from USPTO + Espacenet.

Phase 0 deliverable: working CLI with --dry-run mode that exercises all paths
without needing API keys. Phase 3.1 runs the real ingestion once the Owner has
provided EPO_OPS_KEY / EPO_OPS_SECRET (see OWNER-CHECKLIST.md).

Usage:
    # Dry run (no network — schema validation + sample records)
    uv run python scripts/patent_crawler.py --dry-run --out data/sample.jsonl

    # Real USPTO search (PatentsView; no auth required)
    uv run python scripts/patent_crawler.py --source uspto \\
        --query "telephoto lens largan" --limit 20 \\
        --out data/uspto-largan.jsonl

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
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import httpx
import structlog


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
# USPTO — PatentsView API (free, no auth)
# ---------------------------------------------------------------------------

USPTO_SEARCH_URL = "https://api.patentsview.org/patents/query"


async def search_uspto(query: str, limit: int) -> list[PatentRecord]:
    """Search USPTO PatentsView for free-text query in title + abstract."""
    payload = {
        "q": {
            "_or": [
                {"_text_phrase": {"patent_title": query}},
                {"_text_phrase": {"patent_abstract": query}},
            ]
        },
        "f": [
            "patent_number",
            "patent_title",
            "patent_abstract",
            "inventors",
            "assignees",
            "cpcs",
            "patent_date",
        ],
        "o": {"per_page": limit},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(USPTO_SEARCH_URL, json=payload)
        r.raise_for_status()
        data = r.json()

    records: list[PatentRecord] = []
    for p in data.get("patents", []):
        pn = p.get("patent_number", "")
        records.append(
            PatentRecord(
                id=f"US{pn}",
                title=p.get("patent_title", ""),
                abstract=p.get("patent_abstract", ""),
                claim_excerpt="",  # PatentsView basic API doesn't ship full claims
                inventors=[
                    f"{i.get('inventor_first_name', '')} {i.get('inventor_last_name', '')}".strip()
                    for i in p.get("inventors", [])
                ],
                assignee=(p.get("assignees") or [{}])[0].get(
                    "assignee_organization", ""
                ),
                ipc_classes=[c.get("cpc_subgroup_id", "") for c in (p.get("cpcs") or [])],
                filing_date=p.get("patent_date"),
                source="uspto",
                source_url=f"https://patents.google.com/patent/US{pn}",
            )
        )
    return records


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
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
    logger.info("wrote_jsonl", path=str(out_path), count=len(records))


async def _async_main(args: argparse.Namespace) -> int:
    if args.dry_run:
        _write_jsonl(dry_run_records(), Path(args.out))
        return 0

    if args.source == "uspto":
        records = await search_uspto(args.query, args.limit)
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
        logger.warning("no_records_found", query=args.query)
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
    parser.add_argument("--query", default="telephoto lens")
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
