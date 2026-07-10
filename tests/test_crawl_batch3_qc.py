from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from app.core.patent_crawl_config import three_to_seven_p_hit_rate
from app.core.patent_crawl_schema import load_validated_jsonl, validate_patent_record

ROOT = Path(__file__).resolve().parents[1]
BATCH_PATHS = (
    ROOT / "data/patents/uspto-smartphone-batch1.jsonl",
    ROOT / "data/patents/uspto-smartphone-batch2.jsonl",
    ROOT / "data/patents/uspto-smartphone-batch3.jsonl",
)
BATCH3_PATH = BATCH_PATHS[-1]

TARGET_NON_LARGAN_ASSIGNEE_PATTERNS = {
    "sunny": ("SUNNY OPTIC", "SUNNY OPTICAL", "ZHEJIANG SUNNY", "SUNNY OPTICS"),
    "genius": ("GENIUS ELECTRONIC OPTICAL", "GENIUS ELECTRONIC OPTICS", "GSEO"),
    "aac": ("AAC OPTICS", "AAC ACOUSTIC", "CHANGZHOU AAC", "AAC RAYTECH"),
    "kantatsu": ("KANTATSU",),
    "sekonix": ("SEKONIX",),
}


def _patent_number(record: dict[str, object]) -> str:
    value = record.get("id")
    assert isinstance(value, str)
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _assignee(record: dict[str, object]) -> str:
    value = record.get("assignee")
    assert isinstance(value, str)
    return value.upper()


def _is_non_largan(record: dict[str, object]) -> bool:
    return "LARGAN" not in _assignee(record)


def _target_non_largan_family(record: dict[str, object]) -> str | None:
    assignee = _assignee(record)
    if "LARGAN" in assignee:
        return None
    for family, patterns in TARGET_NON_LARGAN_ASSIGNEE_PATTERNS.items():
        if any(pattern in assignee for pattern in patterns):
            return family
    return None


def _share(
    rows: Iterable[dict[str, object]], predicate: Callable[[dict[str, object]], bool]
) -> float:
    records = list(rows)
    return sum(1 for record in records if predicate(record)) / len(records)


def test_uspto_smartphone_batch3_quality_gate() -> None:
    records = load_validated_jsonl(BATCH3_PATH)

    assert len(records) >= 30

    for record in records:
        validate_patent_record(record)

    for field in ("id", "title", "assignee"):
        assert all(record[field].strip() for record in records)

    assert len({_patent_number(record) for record in records}) == len(records)
    assert three_to_seven_p_hit_rate(records) >= 0.8


def test_uspto_smartphone_batch3_dedupes_across_all_batches() -> None:
    batches = [load_validated_jsonl(path) for path in BATCH_PATHS]
    patent_numbers = [_patent_number(record) for batch in batches for record in batch]

    assert len(patent_numbers) == sum(len(batch) for batch in batches)
    assert len(set(patent_numbers)) == len(patent_numbers)


def test_uspto_smartphone_batch3_non_largan_diversity() -> None:
    records = load_validated_jsonl(BATCH3_PATH)
    families = {
        family for record in records if (family := _target_non_largan_family(record)) is not None
    }

    assert _share(records, _is_non_largan) >= 0.70
    assert len(families) >= 4
