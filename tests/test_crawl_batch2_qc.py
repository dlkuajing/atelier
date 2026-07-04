from __future__ import annotations

import re
from pathlib import Path

from app.core.patent_crawl_config import three_to_seven_p_hit_rate
from app.core.patent_crawl_schema import load_validated_jsonl, validate_patent_record


ROOT = Path(__file__).resolve().parents[1]
BATCH1_PATH = ROOT / "data/patents/uspto-smartphone-batch1.jsonl"
BATCH2_PATH = ROOT / "data/patents/uspto-smartphone-batch2.jsonl"


def _patent_number(record: dict[str, object]) -> str:
    value = record.get("id")
    assert isinstance(value, str)
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def test_uspto_smartphone_batch2_quality_gate() -> None:
    records = load_validated_jsonl(BATCH2_PATH)

    assert len(records) >= 30

    for record in records:
        validate_patent_record(record)

    for field in ("id", "title", "assignee"):
        assert all(record[field].strip() for record in records)

    assert len({_patent_number(record) for record in records}) == len(records)
    assert three_to_seven_p_hit_rate(records) >= 0.8


def test_uspto_smartphone_batch2_dedupes_against_batch1() -> None:
    batch1 = load_validated_jsonl(BATCH1_PATH)
    batch2 = load_validated_jsonl(BATCH2_PATH)

    batch1_numbers = {_patent_number(record) for record in batch1}
    batch2_numbers = {_patent_number(record) for record in batch2}
    overlap = batch1_numbers & batch2_numbers

    assert not overlap, sorted(overlap)
    assert len(batch1_numbers | batch2_numbers) >= 60
