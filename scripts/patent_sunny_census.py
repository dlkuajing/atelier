"""Build a strict, reproducible census of the Sunny metadata replay bucket."""

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
    _patent_table_blocks,
    _sunny_fov_is_full_angle,
    _sunny_surface_block_signature,
    normalize_patent_text,
)

DEFAULT_REPLAY_ROOT = ROOT / "data" / "patent-ledger" / "replay" / "local-uncovered"
DEFAULT_COHORT_PATH = DEFAULT_REPLAY_ROOT / "cohort.json"
DEFAULT_RESULTS_DIR = DEFAULT_REPLAY_ROOT / "results"
DEFAULT_OUTPUT_PATH = DEFAULT_REPLAY_ROOT / "census" / "sunny-metadata-before.json"
TARGET_SIGNATURE = "sunny_embodiment_metadata_missing"
_MISSING_RE = re.compile(
    r"^PatentParseError: Sunny embodiment (?P<number>\d+) metadata missing: "
    r"(?P<fields>(?:f|Fno|Semi-FOV)(?:, (?:f|Fno|Semi-FOV))*)$"
)
_META_MARKER_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9/])f\s*\(mm\)|f\s*/\s*EPD|Semi[- ]?FOV|"
    r"\bHFOV\b|(?<![-A-Za-z])FOV\s*\(|\bFno\b"
)


class SunnyMetadataCensusItem(StrictModel):
    root_id: str = Field(min_length=1)
    publication_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    embodiment_number: int = Field(ge=1)
    missing_fields: tuple[Literal["f", "Fno", "Semi-FOV"], ...] = Field(min_length=1)
    raw_document: EvidenceRef
    layout_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    surface_table_count: int = Field(ge=1)
    metadata_block_count: int = Field(ge=0)
    full_fov_definition: bool


class SunnyMetadataCensus(StrictModel):
    schema_version: Literal[1] = 1
    target_parser_signature: Literal["sunny_embodiment_metadata_missing"] = TARGET_SIGNATURE
    cohort_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    affected_roots: int = Field(ge=0)
    affected_items: int = Field(ge=0)
    missing_field_counts: dict[str, int]
    layout_signature_counts: dict[str, int]
    items: tuple[SunnyMetadataCensusItem, ...]

    @model_validator(mode="after")
    def validate_recomputed_counts(self) -> SunnyMetadataCensus:
        if self.affected_items != len(self.items):
            raise ValueError("affected_items does not match item count")
        if self.affected_roots != len({item.root_id for item in self.items}):
            raise ValueError("affected_roots does not match item roots")
        if len({item.item_id for item in self.items}) != len(self.items):
            raise ValueError("census item IDs must be unique")
        missing = Counter(field for item in self.items for field in item.missing_fields)
        if dict(sorted(missing.items())) != self.missing_field_counts:
            raise ValueError("missing_field_counts does not match items")
        layouts = Counter(item.layout_signature for item in self.items)
        if dict(sorted(layouts.items())) != self.layout_signature_counts:
            raise ValueError("layout_signature_counts does not match items")
        return self


def _layout_evidence(raw_text: str) -> tuple[str, int, int, bool]:
    text = normalize_patent_text(raw_text)
    blocks = _patent_table_blocks(text)
    surface_count = sum(_sunny_surface_block_signature(block.text) for block in blocks)
    normalized_blocks: list[str] = []
    for block in blocks:
        body = _cut_sunny_table_narrative(block.text)
        if _META_MARKER_RE.search(body) is None:
            continue
        normalized = re.sub(r"TABLE-US-\d+\s+TABLE\s+\d+\s*", "", body, flags=re.I)
        normalized = re.sub(NUMBER_PATTERN, "N", normalized, flags=re.I)
        normalized_blocks.append(re.sub(r"\s+", " ", normalized).strip())
    payload = {
        "surface_table_count": surface_count,
        "metadata_blocks": normalized_blocks,
        "full_fov_definition": _sunny_fov_is_full_angle(text),
    }
    return (
        sha256_bytes(canonical_json_bytes(payload)),
        surface_count,
        len(normalized_blocks),
        payload["full_fov_definition"],
    )


def build_census(*, cohort_path: Path, results_dir: Path) -> SunnyMetadataCensus:
    cohort = load_replay_cohort(cohort_path)
    summary = summarize_replay_results(cohort, results_dir=results_dir, evidence_root=ROOT)
    if not summary.cohort_replay_complete:
        raise RuntimeError("strict replay audit must pass before building parser census")

    items: list[SunnyMetadataCensusItem] = []
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
        if result.raw_document is None:
            raise RuntimeError(f"Sunny parser result lacks raw document: {member.root_id}")
        raw_path = ROOT / result.raw_document.path
        layout, surface_count, metadata_count, full_fov = _layout_evidence(
            raw_path.read_text(encoding="utf-8")
        )
        for item in matching:
            detail = _MISSING_RE.fullmatch(item.detail)
            if detail is None:
                raise RuntimeError(f"unstructured Sunny metadata detail: {item.item_id}")
            embodiment_number = int(detail.group("number"))
            if not item.item_id.endswith(f":e{embodiment_number}"):
                raise RuntimeError(f"Sunny item/embodiment mismatch: {item.item_id}")
            items.append(
                SunnyMetadataCensusItem(
                    root_id=result.root_id,
                    publication_id=result.publication_id,
                    item_id=item.item_id,
                    embodiment_number=embodiment_number,
                    missing_fields=tuple(detail.group("fields").split(", ")),
                    raw_document=result.raw_document,
                    layout_signature=layout,
                    surface_table_count=surface_count,
                    metadata_block_count=metadata_count,
                    full_fov_definition=full_fov,
                )
            )
    items.sort(key=lambda item: (item.root_id, item.publication_id, item.embodiment_number))
    missing = Counter(field for item in items for field in item.missing_fields)
    layouts = Counter(item.layout_signature for item in items)
    return SunnyMetadataCensus(
        cohort_sha256=summary.cohort_sha256,
        result_set_sha256=summary.result_set_sha256,
        affected_roots=len({item.root_id for item in items}),
        affected_items=len(items),
        missing_field_counts=dict(sorted(missing.items())),
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
