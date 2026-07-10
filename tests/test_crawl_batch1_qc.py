from __future__ import annotations

from pathlib import Path

from app.core.patent_crawl_config import three_to_seven_p_hit_rate
from app.core.patent_crawl_schema import load_validated_jsonl, validate_patent_record

BATCH1_PATH = Path(__file__).resolve().parents[1] / "data/patents/uspto-smartphone-batch1.jsonl"


def test_uspto_smartphone_batch1_quality_gate() -> None:
    records = load_validated_jsonl(BATCH1_PATH)

    assert len(records) >= 30

    for record in records:
        validate_patent_record(record)

    for field in ("id", "title", "assignee"):
        assert all(record[field].strip() for record in records)

    assert three_to_seven_p_hit_rate(records) >= 0.8
