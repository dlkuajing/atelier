"""Targeting configuration for smartphone lens patent crawls."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class PatentCrawlProfile:
    name: str
    uspto_queries: tuple[str, ...]
    assignees: tuple[str, ...]
    lens_count_patterns: tuple[str, ...]


SMARTPHONE_LENS_ASSIGNEES: tuple[str, ...] = (
    "Largan Precision",
    "Sunny Optical",
    "Zhejiang Sunny Optics",
    "Genius Electronic Optical",
    "Genius Electronic Optics",
    "Sekonix",
    "Kantatsu",
    "Ability Opto-Electronics",
    "AAC Optics",
    "Newmax Technology",
    "Samsung Electro-Mechanics",
)

SMARTPHONE_USPTO_QUERIES: tuple[str, ...] = (
    '"optical imaging lens assembly"',
    '"imaging lens assembly" AND "electronic device"',
    '"image capturing unit" AND "lens assembly"',
    '"camera optical lens" AND "electronic device"',
)

THREE_TO_SEVEN_P_PATTERNS: tuple[str, ...] = (
    r"\b(?:three|four|five|six|seven)\s+lens(?:es)?\b",
    r"\b(?:three|four|five|six|seven)\s+lens\s+elements?\b",
    r"\b(?:3|4|5|6|7)\s*(?:p|piece)\b",
    r"\b(?:3|4|5|6|7)[-\s]?lens(?:es)?\b",
    r"\bfirst\s+lens\s+(?:to|through)\s+(?:a\s+)?(?:third|fourth|fifth|sixth|seventh)\s+lens\b",
    r"\bfirst\s+lens\s+(?:to|through)\s+(?:a\s+)?(?:third|fourth|fifth|sixth|seventh)\s+lens\s+element\b",
    r"\bfirst\s+lens\b.{0,240}\b(?:third|fourth|fifth|sixth|seventh)\s+lens\b",
    r"\bfirst\s+lens\s+element\b.{0,260}\b(?:third|fourth|fifth|sixth|seventh)\s+lens\s+element\b",
    r"\bfirst\s+to\s+(?:third|fourth|fifth|sixth|seventh)\s+lenses\b",
    r"\b(?:third|fourth|fifth|sixth|seventh)\s+lens\s+element\b",
    r"\btotal\s+of\s+(?:three|four|five|six|seven)\s+lens(?:es)?\b",
)

SMARTPHONE_LENS_PROFILE = PatentCrawlProfile(
    name="smartphone-lens",
    uspto_queries=SMARTPHONE_USPTO_QUERIES,
    assignees=SMARTPHONE_LENS_ASSIGNEES,
    lens_count_patterns=THREE_TO_SEVEN_P_PATTERNS,
)


def record_text(record: Mapping[str, object]) -> str:
    parts: list[str] = []
    for key in ("title", "abstract", "claim_excerpt", "assignee"):
        value = record.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts)


def has_three_to_seven_p_keyword(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in THREE_TO_SEVEN_P_PATTERNS)


def three_to_seven_p_hit_rate(records: Iterable[Mapping[str, object]]) -> float:
    rows = list(records)
    if not rows:
        return 0.0
    hits = sum(1 for record in rows if has_three_to_seven_p_keyword(record_text(record)))
    return hits / len(rows)
