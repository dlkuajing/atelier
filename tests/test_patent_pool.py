from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import httpx
import pytest

import scripts.patent_crawler as patent_crawler
from scripts.patent_crawler import (
    PatentRecord,
    family_fingerprint,
    filter_patent_records_by_pool,
)

ROOT = Path(__file__).resolve().parents[1]
PATENT_DIR = ROOT / "data/patents"
REPORT_PATH = ROOT / ".planning/loop/uspto-b7-report.md"


def _fixture_record(
    patent_id: str,
    *,
    assignee: str,
    title: str = "Optical Imaging Lens Assembly",
    optical_text: str = "f/Fno = 6.27/1.71",
) -> PatentRecord:
    return PatentRecord(
        id=patent_id,
        title=title,
        abstract=f"A compact imaging lens for an electronic device; {optical_text}.",
        claim_excerpt="A first lens through a sixth lens element define the optical path.",
        inventors=["Jane Doe"],
        assignee=assignee,
        ipc_classes=["G02B13/0045"],
        filing_date="2024-01-31",
        source="uspto",
        source_url=f"https://ppubs.uspto.gov/{patent_id}",
    )


def _patent_number(record: dict[str, object]) -> str:
    value = record.get("id")
    assert isinstance(value, str) and value.strip()
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _load_patent_pool() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in sorted(PATENT_DIR.glob("uspto-smartphone-batch*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                for field in ("id", "title", "source_url"):
                    assert isinstance(record.get(field), str), f"{path}:{line_number}: {field}"
                    assert record[field].strip(), f"{path}:{line_number}: {field}"
                records.append(record)
    return records


def test_uspto_smartphone_patent_pool_is_large_and_globally_unique() -> None:
    records = _load_patent_pool()
    patent_numbers = [_patent_number(record) for record in records]

    assert len(records) >= 714
    assert len(set(patent_numbers)) == len(patent_numbers)


def test_family_fingerprint_normalizes_assignee_title_and_f_fno_values() -> None:
    base = _fixture_record("US1000001A1", assignee="Largan Precision Co., Ltd.")
    near_duplicate = _fixture_record(
        "US1000002A1",
        assignee="LARGAN PRECISION COMPANY LIMITED",
        title="Optical-imaging lens assembly",
        optical_text="f = 6.29 mm; F-number = 1.70",
    )
    different_f_number = _fixture_record(
        "US1000003A1",
        assignee="Largan Precision Co., Ltd.",
        optical_text="f/Fno/HFOV = 6.27/1.95/41.6",
    )

    assert family_fingerprint(base) == family_fingerprint(near_duplicate)
    assert family_fingerprint(base) != family_fingerprint(different_f_number)


def test_pool_filter_marks_family_fingerprint_duplicates_without_skipping() -> None:
    existing = [_fixture_record("US1000010A1", assignee="Sunny Optical Technology Group")]
    duplicate = _fixture_record(
        "US1000011A1",
        assignee="Zhejiang Sunny Optics Co., Ltd.",
        title="Optical-imaging lens assembly",
        optical_text="f = 6.29 mm; Fno = 1.70",
    )
    fresh = _fixture_record(
        "US1000012A1",
        assignee="Genius Electronic Optical Co., Ltd.",
        title="Camera Optical Lens",
        optical_text="f/Fno/HFOV = 5.10/2.20/55.0",
    )

    accepted, stats = filter_patent_records_by_pool([duplicate, fresh], existing)

    assert [record.id for record in accepted] == ["US1000011A1", "US1000012A1"]
    assert duplicate.family_hint is not None
    assert "near_duplicate_of=US1000010A1" in duplicate.family_hint
    assert fresh.family_hint is None
    assert stats.id_duplicate_skipped == 0
    assert stats.family_hint_tagged == 1
    assert stats.family_duplicate_skipped == 0
    assert stats.assignee_quota_skipped == 0


def test_pool_filter_skips_exact_patent_id_duplicates() -> None:
    existing = [
        _fixture_record(
            "US-1000010-A1",
            assignee="Independent Optics",
            title="Compact Lens Module",
            optical_text="f/Fno/HFOV = 4.10/2.10/50.0",
        )
    ]
    duplicate_id = _fixture_record(
        "US1000010A1",
        assignee="Different Assignee",
        title="Different Lens Title",
        optical_text="f/Fno/HFOV = 8.20/1.80/32.0",
    )
    fresh = _fixture_record(
        "US1000011A1",
        assignee="Another Optics",
        title="Seven Piece Camera Lens",
        optical_text="f/Fno/HFOV = 5.10/2.20/55.0",
    )

    accepted, stats = filter_patent_records_by_pool([duplicate_id, fresh], existing)

    assert [record.id for record in accepted] == ["US1000011A1"]
    assert stats.id_duplicate_skipped == 1
    assert stats.family_hint_tagged == 0


def test_pool_filter_skips_assignee_when_quota_would_exceed_thirty_percent() -> None:
    existing = [
        _fixture_record(f"US200000{i}A1", assignee="Largan Precision Co., Ltd.")
        for i in range(3)
    ]
    existing.extend(
        _fixture_record(
            f"US200001{i}A1",
            assignee=f"Independent Optics {i}",
            title=f"Imaging Lens Assembly {i}",
            optical_text=f"f/Fno/HFOV = {4.0 + i:.2f}/2.20/55.0",
        )
        for i in range(7)
    )
    over_quota = _fixture_record(
        "US2000100A1",
        assignee="LARGAN PRECISION COMPANY LIMITED",
        title="Compact Wide Imaging Lens",
        optical_text="f/Fno/HFOV = 8.20/2.10/32.0",
    )
    allowed = _fixture_record(
        "US2000101A1",
        assignee="AAC Optics Solutions",
        title="Seven Piece Camera Optical Lens",
        optical_text="f/Fno/HFOV = 9.30/2.40/28.0",
    )

    accepted, stats = filter_patent_records_by_pool([over_quota, allowed], existing)

    assert [record.id for record in accepted] == ["US2000101A1"]
    assert stats.assignee_quota_skipped == 1
    assert stats.family_duplicate_skipped == 0


async def test_uspto_record_skipped_logs_exception_status_and_skips_failure_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []
    sleep_calls: list[float] = []

    class FakeLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            events.append((event, kwargs))

    async def fail_fetch(
        _client: object,
        _token: str,
        _document_id: str,
        _source_type: str,
    ) -> str:
        request = httpx.Request("GET", "https://ppubs.example.test/html")
        response = httpx.Response(503, request=request)
        raise httpx.HTTPStatusError("", request=request, response=response)

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(patent_crawler, "logger", FakeLogger())
    monkeypatch.setattr(patent_crawler, "_ppubs_patent_html", fail_fetch)
    monkeypatch.setattr(patent_crawler.asyncio, "sleep", fake_sleep)

    reason_counts: Counter[str] = Counter()
    record = await patent_crawler._record_for_ppubs_doc(
        object(),
        "token",
        {"documentId": "US-FAIL-A1", "type": "US-PGPUB"},
        skip_reason_counts=reason_counts,
    )

    assert record is None
    assert sleep_calls == []
    assert reason_counts == Counter({"http_503": 1})
    assert len(events) == 1
    event, payload = events[0]
    assert event == "uspto_record_skipped"
    assert payload["document_id"] == "US-FAIL-A1"
    assert payload["stage"] == "fetch"
    assert payload["error"]
    assert payload["error_type"] == "HTTPStatusError"
    assert payload["http_status"] == 503
    assert payload["failure_reason"] == "http_503"


def test_uspto_batch7_report_records_query_stats() -> None:
    if not REPORT_PATH.is_file():
        pytest.skip("DATA-05d collection report is optional outside the collection worktree")

    text = REPORT_PATH.read_text(encoding="utf-8")

    assert "DATA-05d" in text
    assert "uspto-smartphone-batch7.jsonl" in text
    assert "查询词" in text
    assert "命中率" in text
    assert "去重数" in text
