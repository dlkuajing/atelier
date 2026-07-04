from __future__ import annotations

import re

import pytest

from app.core.patent_crawl_config import (
    SMARTPHONE_LENS_ASSIGNEES,
    SMARTPHONE_LENS_PROFILE,
    SMARTPHONE_USPTO_QUERIES,
    THREE_TO_SEVEN_P_PATTERNS,
    has_three_to_seven_p_keyword,
    three_to_seven_p_hit_rate,
)
from app.core.patent_crawl_schema import (
    PatentRecordSchemaError,
    patent_record_errors,
    validate_patent_record,
)


VALID_PATENT_RECORD = {
    "id": "US1234567B2",
    "title": "Optical imaging lens assembly",
    "abstract": "A compact camera module for an electronic device.",
    "claim_excerpt": "The assembly includes first through sixth lens elements.",
    "inventors": ["Jane Doe", "John Doe"],
    "assignee": "Largan Precision Co., Ltd.",
    "ipc_classes": ["G02B13/00", "G02B9/64"],
    "filing_date": "2024-01-31",
    "source": "uspto",
    "source_url": "https://ppubs.uspto.gov/pubwebapp/",
}


def test_smartphone_crawl_profile_wires_tuple_config() -> None:
    assert SMARTPHONE_LENS_PROFILE.name == "smartphone-lens"
    assert SMARTPHONE_LENS_PROFILE.uspto_queries is SMARTPHONE_USPTO_QUERIES
    assert SMARTPHONE_LENS_PROFILE.assignees is SMARTPHONE_LENS_ASSIGNEES
    assert SMARTPHONE_LENS_PROFILE.lens_count_patterns is THREE_TO_SEVEN_P_PATTERNS

    assert len(SMARTPHONE_USPTO_QUERIES) >= 4
    assert all(isinstance(query, str) and query.strip() for query in SMARTPHONE_USPTO_QUERIES)
    assert all("lens" in query.lower() for query in SMARTPHONE_USPTO_QUERIES)

    assert len(SMARTPHONE_LENS_ASSIGNEES) >= 10
    assert len(set(SMARTPHONE_LENS_ASSIGNEES)) == len(SMARTPHONE_LENS_ASSIGNEES)
    assert all(isinstance(assignee, str) and assignee.strip() for assignee in SMARTPHONE_LENS_ASSIGNEES)
    assert {"Largan Precision", "Sunny Optical", "Kantatsu"}.issubset(
        SMARTPHONE_LENS_ASSIGNEES
    )


def test_three_to_seven_p_patterns_compile_and_classify_examples() -> None:
    assert len(THREE_TO_SEVEN_P_PATTERNS) >= 8
    for pattern in THREE_TO_SEVEN_P_PATTERNS:
        re.compile(pattern)

    positive_texts = (
        "An optical imaging lens assembly has a six lens system.",
        "The electronic device includes a compact 6P camera optical lens.",
        "The first lens element through a fifth lens element define the imaging path.",
        "A total of seven lenses are arranged from object side to image side.",
    )
    assert all(has_three_to_seven_p_keyword(text) for text in positive_texts)

    negative_texts = (
        "A single objective lens is used in the module.",
        "The design uses eight lenses for a folded telephoto camera.",
    )
    assert not any(has_three_to_seven_p_keyword(text) for text in negative_texts)


def test_three_to_seven_p_hit_rate_uses_record_text_fields() -> None:
    records = [
        {**VALID_PATENT_RECORD, "claim_excerpt": "A first lens to a fourth lens are used."},
        {**VALID_PATENT_RECORD, "claim_excerpt": "A single objective lens is used."},
    ]

    assert three_to_seven_p_hit_rate(records) == 0.5
    assert three_to_seven_p_hit_rate([]) == 0.0


def test_patent_record_schema_accepts_valid_sample() -> None:
    validate_patent_record(VALID_PATENT_RECORD)

    assert patent_record_errors(VALID_PATENT_RECORD) == []
    validate_patent_record({**VALID_PATENT_RECORD, "filing_date": None, "source": "espacenet"})
    validate_patent_record({**VALID_PATENT_RECORD, "source": "sample"})


def test_patent_record_schema_rejects_invalid_samples() -> None:
    missing_claim = dict(VALID_PATENT_RECORD)
    missing_claim.pop("claim_excerpt")
    assert "missing field: claim_excerpt" in patent_record_errors(missing_claim)
    with pytest.raises(PatentRecordSchemaError, match="missing field: claim_excerpt"):
        validate_patent_record(missing_claim)

    wrong_types = {
        **VALID_PATENT_RECORD,
        "inventors": "Jane Doe",
        "filing_date": 20240131,
    }
    wrong_type_errors = patent_record_errors(wrong_types)
    assert "inventors has invalid type: str" in wrong_type_errors
    assert "filing_date has invalid type: int" in wrong_type_errors

    bad_values = {
        **VALID_PATENT_RECORD,
        "source": "wipo",
        "source_url": " ",
        "ipc_classes": ["G02B13/00", 42],
    }
    bad_value_errors = patent_record_errors(bad_values)
    assert "source is unsupported: wipo" in bad_value_errors
    assert "source_url must be non-empty" in bad_value_errors
    assert "ipc_classes must contain strings only" in bad_value_errors
