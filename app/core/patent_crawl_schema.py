"""Schema checks for patent crawler JSONL output."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "id": str,
    "title": str,
    "abstract": str,
    "claim_excerpt": str,
    "inventors": list,
    "assignee": str,
    "ipc_classes": list,
    "filing_date": (str, type(None)),
    "source": str,
    "source_url": str,
}

NONEMPTY_STRING_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "abstract",
    "claim_excerpt",
    "assignee",
    "source",
    "source_url",
)


class PatentRecordSchemaError(ValueError):
    """Raised when a crawler record does not match the JSONL contract."""


def patent_record_errors(record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []

    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in record:
            errors.append(f"missing field: {field}")
            continue
        if not isinstance(record[field], expected_type):
            errors.append(f"{field} has invalid type: {type(record[field]).__name__}")

    for field in NONEMPTY_STRING_FIELDS:
        value = record.get(field)
        if isinstance(value, str) and not value.strip():
            errors.append(f"{field} must be non-empty")

    for field in ("inventors", "ipc_classes"):
        value = record.get(field)
        if isinstance(value, list) and not all(isinstance(item, str) for item in value):
            errors.append(f"{field} must contain strings only")

    source = record.get("source")
    if isinstance(source, str) and source not in {"uspto", "espacenet", "sample"}:
        errors.append(f"source is unsupported: {source}")

    return errors


def validate_patent_record(record: Mapping[str, Any]) -> None:
    errors = patent_record_errors(record)
    if errors:
        raise PatentRecordSchemaError("; ".join(errors))


def load_validated_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            try:
                validate_patent_record(record)
            except PatentRecordSchemaError as exc:
                raise PatentRecordSchemaError(f"{path}:{line_number}: {exc}") from exc
            records.append(record)
    return records
