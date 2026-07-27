"""Build a strict census for the generic patent-summary metadata failure bucket."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.patent_replay import (  # noqa: E402
    ReplayItemState,
    canonical_json_bytes,
    latest_result_path,
    load_replay_cohort,
    load_root_replay_result,
    parser_failure_signature,
    sha256_bytes,
    summarize_replay_results,
)
from app.core.patent_saturation import EvidenceRef, StrictModel  # noqa: E402
from scripts.patent_to_zmx import (  # noqa: E402
    NUMBER_PATTERN,
    _cut_sunny_table_narrative,
    normalize_patent_text,
)

DEFAULT_REPLAY_ROOT = ROOT / "data" / "patent-ledger" / "replay" / "local-uncovered"
DEFAULT_COHORT_PATH = DEFAULT_REPLAY_ROOT / "cohort.json"
DEFAULT_RESULTS_DIR = DEFAULT_REPLAY_ROOT / "results"
DEFAULT_OUTPUT_PATH = DEFAULT_REPLAY_ROOT / "census" / "generic-summary-before.json"
TARGET_SIGNATURE = "generic_summary_metadata_missing"
TARGET_DETAIL = "PatentParseError: embodiment f/Fno/HFOV line not found"

_MARKER_PATTERNS: dict[str, re.Pattern[str]] = {
    "effective_focal_length": re.compile(
        r"(?i)effective focal length|(?<![A-Za-z0-9/])EFL\b|(?<![A-Za-z0-9/])f\s*[=(]"
    ),
    "f_number": re.compile(r"(?i)\bFno\.?\b|\bF-number\b|\bF number\b|F/#|f\s*/\s*EPD"),
    "half_field": re.compile(
        r"(?i)\bHFOV\b|Semi[- ]?FOV|half (?:diagonal )?(?:field|angle)"
    ),
    "full_field": re.compile(r"(?i)(?<![-A-Za-z])FOV\b|field[- ]of[- ]view"),
    "example_anchor": re.compile(r"(?i)\bExample\s+\d+\b"),
    "embodiment_anchor": re.compile(
        r"(?i)\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
        r"\d+(?:st|nd|rd|th))\s+embodiment\b|\bEmbodiment\s+\d+\b"
    ),
}
_TABLE_BLOCK_RE = re.compile(
    r"\bTABLE-US-\d+\s+TABLE\s+\d+[A-Za-z]?\s+",
    flags=re.IGNORECASE,
)


class GenericSummaryCensusItem(StrictModel):
    root_id: str = Field(min_length=1)
    publication_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    raw_document: EvidenceRef
    layout_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    table_count: int = Field(ge=0)
    marker_counts: dict[str, int]


class GenericSummaryCensus(StrictModel):
    schema_version: Literal[1] = 1
    target_parser_signature: Literal["generic_summary_metadata_missing"] = TARGET_SIGNATURE
    cohort_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    affected_roots: int = Field(ge=0)
    affected_items: int = Field(ge=0)
    layout_signature_counts: dict[str, int]
    items: tuple[GenericSummaryCensusItem, ...]

    @model_validator(mode="after")
    def validate_recomputed_counts(self) -> GenericSummaryCensus:
        if self.affected_items != len(self.items):
            raise ValueError("affected_items does not match item count")
        if self.affected_roots != len({item.root_id for item in self.items}):
            raise ValueError("affected_roots does not match item roots")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("census item IDs must be unique")
        layouts = Counter(item.layout_signature for item in self.items)
        if dict(sorted(layouts.items())) != self.layout_signature_counts:
            raise ValueError("layout_signature_counts does not match items")
        return self


def _normalized_table_prefix(block_text: str) -> str:
    body = _cut_sunny_table_narrative(block_text)
    body = re.sub(r"TABLE-US-\d+\s+TABLE\s+\d+[A-Za-z]?\s*", "", body, flags=re.I)
    body = re.sub(NUMBER_PATTERN, "N", body, flags=re.I)
    return re.sub(r"\s+", " ", body).strip()[:600]


def _layout_evidence(raw_text: str) -> tuple[str, int, dict[str, int]]:
    text = normalize_patent_text(raw_text)
    matches = list(_TABLE_BLOCK_RE.finditer(text))
    blocks = [
        text[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        for index, match in enumerate(matches)
    ]
    marker_counts = {
        name: len(tuple(pattern.finditer(text))) for name, pattern in _MARKER_PATTERNS.items()
    }
    payload = {
        "table_prefixes": [_normalized_table_prefix(block) for block in blocks],
        "marker_presence": {
            name: count > 0 for name, count in sorted(marker_counts.items())
        },
    }
    return sha256_bytes(canonical_json_bytes(payload)), len(blocks), marker_counts


def build_census(*, cohort_path: Path, results_dir: Path) -> GenericSummaryCensus:
    cohort = load_replay_cohort(cohort_path)
    summary = summarize_replay_results(cohort, results_dir=results_dir, evidence_root=ROOT)
    if not summary.cohort_replay_complete:
        raise RuntimeError("strict replay audit must pass before building parser census")

    items: list[GenericSummaryCensusItem] = []
    for member in cohort.members:
        result_path = latest_result_path(results_dir, member.root_id)
        if result_path is None:
            raise RuntimeError(f"missing replay result after strict audit: {member.root_id}")
        result = load_root_replay_result(result_path)
        matching = [
            item
            for item in result.items
            if item.state is ReplayItemState.PARSER_REVIEW_REQUIRED
            and parser_failure_signature(item.detail) == TARGET_SIGNATURE
        ]
        if not matching:
            continue
        if len(matching) != 1 or matching[0].detail != TARGET_DETAIL:
            raise RuntimeError(f"unexpected generic-summary result shape: {member.root_id}")
        item = matching[0]
        if item.item_id != f"{result.publication_id}:document":
            raise RuntimeError(f"generic-summary item is not document-scoped: {item.item_id}")
        if result.raw_document is None:
            raise RuntimeError(f"generic-summary result lacks raw document: {member.root_id}")
        raw_path = ROOT / result.raw_document.path
        layout, table_count, marker_counts = _layout_evidence(
            raw_path.read_text(encoding="utf-8")
        )
        items.append(
            GenericSummaryCensusItem(
                root_id=result.root_id,
                publication_id=result.publication_id,
                item_id=item.item_id,
                raw_document=result.raw_document,
                layout_signature=layout,
                table_count=table_count,
                marker_counts=marker_counts,
            )
        )
    items.sort(key=lambda item: (item.root_id, item.publication_id))
    layouts = Counter(item.layout_signature for item in items)
    return GenericSummaryCensus(
        cohort_sha256=summary.cohort_sha256,
        result_set_sha256=summary.result_set_sha256,
        affected_roots=len({item.root_id for item in items}),
        affected_items=len(items),
        layout_signature_counts=dict(sorted(layouts.items())),
        items=tuple(items),
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    census = build_census(cohort_path=args.cohort, results_dir=args.results_dir)
    _atomic_write(args.output, canonical_json_bytes(census))
    print(
        f"affected_items={census.affected_items} affected_roots={census.affected_roots} "
        f"result_set_sha256={census.result_set_sha256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
