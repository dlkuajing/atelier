from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PATENT_DIR = ROOT / "data/patents"
REPORT_PATH = ROOT / ".planning/loop/uspto-b5-report.md"


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

    assert len(records) >= 224
    assert len(set(patent_numbers)) == len(patent_numbers)


def test_uspto_batch5_report_records_query_stats() -> None:
    if not REPORT_PATH.is_file():
        pytest.skip("DATA-05b collection report is optional outside the collection worktree")

    text = REPORT_PATH.read_text(encoding="utf-8")

    assert "DATA-05b" in text
    assert "uspto-smartphone-batch5.jsonl" in text
    assert "查询词" in text
    assert "命中率" in text
    assert "去重数" in text
