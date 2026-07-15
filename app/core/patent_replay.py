"""Deterministic frozen-cohort and result models for local patent replay."""

from __future__ import annotations

import json
import re
from collections import Counter
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.core.patent_saturation import (
    EvidenceRef,
    InputManifest,
    StrictModel,
    TerminalStatus,
    canonical_json_bytes,
    load_saturation_snapshot,
    sha256_bytes,
)

REPLAY_SCHEMA_VERSION = 1
REASON_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
ATTEMPT_DIRECTORY_PATTERN = re.compile(r"^attempt-(?P<number>\d{4,})$")


class PatentReplayError(RuntimeError):
    """Raised when frozen replay inputs or result evidence are inconsistent."""


class SourceFetchState(StrEnum):
    RETAINED = "retained"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"


class ReplayItemState(StrEnum):
    CONVERTED_PENDING_INTAKE = "converted_pending_intake"
    TERMINAL = "terminal"
    PARSER_REVIEW_REQUIRED = "parser_review_required"
    CONVERSION_RETRY_REQUIRED = "conversion_retry_required"


class RootReplayState(StrEnum):
    CONVERTED_PENDING_INTAKE = "converted_pending_intake"
    TERMINAL = "terminal"
    PARSER_REVIEW_REQUIRED = "parser_review_required"
    SOURCE_RETRY_REQUIRED = "source_retry_required"
    SOURCE_EXHAUSTED_PENDING_ALTERNATES = "source_exhausted_pending_alternates"
    CONVERSION_RETRY_REQUIRED = "conversion_retry_required"
    MIXED_NONTERMINAL = "mixed_nonterminal"


class SourceFetchAttempt(StrictModel):
    publication_id: str = Field(min_length=1)
    source_bucket: str = Field(min_length=1)
    state: SourceFetchState
    http_status: int | None = Field(default=None, ge=100, le=599)
    exception_type: str | None = None

    @model_validator(mode="after")
    def validate_state_evidence(self) -> SourceFetchAttempt:
        if self.state is SourceFetchState.RETAINED:
            if self.http_status != 200 or self.exception_type is not None:
                raise ValueError("retained source attempt requires HTTP 200 and no exception")
        elif self.state is SourceFetchState.HTTP_ERROR:
            if self.http_status is None or not self.exception_type:
                raise ValueError("HTTP error requires status and exception type")
        elif self.http_status is not None or not self.exception_type:
            raise ValueError("transport error requires exception type and no HTTP status")
        return self


class ReplayPublication(StrictModel):
    publication_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_url: str
    title: str
    pool_file: str = Field(min_length=1)
    line_number: int = Field(ge=1)
    raw_line_sha256: str

    @field_validator("raw_line_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("raw_line_sha256 must be lowercase SHA-256")
        return value


class ReplayCohortMember(StrictModel):
    root_id: str = Field(min_length=1)
    publications: tuple[ReplayPublication, ...] = Field(min_length=1)


class ReplayCohortManifest(StrictModel):
    schema_version: Literal[1] = REPLAY_SCHEMA_VERSION
    saturation_snapshot: EvidenceRef
    inputs: InputManifest
    selection_rule: Literal["raw_root_without_formal_case"] = "raw_root_without_formal_case"
    members: tuple[ReplayCohortMember, ...]

    @model_validator(mode="after")
    def validate_unique_membership(self) -> ReplayCohortManifest:
        root_ids = [member.root_id for member in self.members]
        if root_ids != sorted(root_ids):
            raise ValueError("cohort members must be sorted by root_id")
        if len(root_ids) != len(set(root_ids)):
            raise ValueError("cohort root IDs must be unique")
        publications = [
            publication.publication_id
            for member in self.members
            for publication in member.publications
        ]
        if len(publications) != len(set(publications)):
            raise ValueError("cohort publication IDs must be unique")
        return self


class ReplayItemResult(StrictModel):
    item_id: str = Field(min_length=1)
    embodiment_number: int | None = Field(default=None, ge=1)
    embodiment_label: str = ""
    state: ReplayItemState
    reason_code: str
    detail: str = ""
    terminal_status: TerminalStatus | None = None
    prescription_fingerprint: str | None = None
    conversion_attempt_id: str | None = None
    conversion_request_sha256: str | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    coverage: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_outcome(self) -> ReplayItemResult:
        if REASON_CODE_PATTERN.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must be structured lowercase dotted text")
        if not self.reason_code.startswith(f"{self.state.value}."):
            raise ValueError("reason_code must be namespaced by item state")
        if self.state is ReplayItemState.TERMINAL:
            if self.terminal_status is None or not self.evidence:
                raise ValueError("terminal item requires terminal status and evidence")
        elif self.terminal_status is not None:
            raise ValueError("non-terminal item cannot carry terminal status")
        if self.conversion_attempt_id is None and self.conversion_request_sha256 is not None:
            raise ValueError("conversion request hash requires conversion attempt ID")
        evidence_keys = [(item.evidence_type, item.path, item.sha256) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("replay item evidence must be unique")
        return self


class RootReplayResult(StrictModel):
    schema_version: Literal[1] = REPLAY_SCHEMA_VERSION
    cohort_sha256: str
    root_id: str = Field(min_length=1)
    result_attempt: int = Field(ge=1)
    publication_id: str = Field(min_length=1)
    root_state: RootReplayState
    reason_code: str
    source_attempts: tuple[SourceFetchAttempt, ...] = Field(min_length=1)
    raw_document: EvidenceRef | None = None
    items: tuple[ReplayItemResult, ...]

    @field_validator("cohort_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("cohort_sha256 must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_result(self) -> RootReplayResult:
        if REASON_CODE_PATTERN.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must be structured lowercase dotted text")
        if not self.reason_code.startswith(f"{self.root_state.value}."):
            raise ValueError("reason_code must be namespaced by root state")
        retained = [
            attempt
            for attempt in self.source_attempts
            if attempt.state is SourceFetchState.RETAINED
        ]
        if retained and self.raw_document is None:
            raise ValueError("retained source requires raw document evidence")
        if not retained and self.raw_document is not None:
            raise ValueError("raw document evidence requires retained source")
        if len(retained) > 1:
            raise ValueError("one root replay result may retain only one source response")
        if retained:
            if retained[0].publication_id != self.publication_id:
                raise ValueError("retained source publication must match replay publication")
            item_states = {item.state for item in self.items}
            if not item_states or item_states == {ReplayItemState.PARSER_REVIEW_REQUIRED}:
                expected_root_state = RootReplayState.PARSER_REVIEW_REQUIRED
            elif item_states == {ReplayItemState.CONVERTED_PENDING_INTAKE}:
                expected_root_state = RootReplayState.CONVERTED_PENDING_INTAKE
            elif item_states == {ReplayItemState.TERMINAL}:
                expected_root_state = RootReplayState.TERMINAL
            elif item_states == {ReplayItemState.CONVERSION_RETRY_REQUIRED}:
                expected_root_state = RootReplayState.CONVERSION_RETRY_REQUIRED
            else:
                expected_root_state = RootReplayState.MIXED_NONTERMINAL
            if self.root_state is not expected_root_state:
                raise ValueError("root state is inconsistent with replay item states")
        else:
            if self.items:
                raise ValueError("source-fetch failure cannot carry replay items")
            if self.root_state not in {
                RootReplayState.SOURCE_RETRY_REQUIRED,
                RootReplayState.SOURCE_EXHAUSTED_PENDING_ALTERNATES,
            }:
                raise ValueError("missing retained source requires a source root state")
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("replay item IDs must be unique")
        return self


class ReplaySummary(StrictModel):
    schema_version: Literal[1] = REPLAY_SCHEMA_VERSION
    cohort_sha256: str
    cohort_roots: int = Field(ge=0)
    roots_with_results: int = Field(ge=0)
    missing_root_ids: tuple[str, ...]
    corrupt_result_paths: tuple[str, ...]
    cohort_replay_complete: bool
    saturation_complete: Literal[False] = False
    next_missing_index: int | None = Field(default=None, ge=0)
    root_state_counts: dict[RootReplayState, int]
    item_state_counts: dict[ReplayItemState, int]
    terminal_status_counts: dict[TerminalStatus, int]
    root_reason_counts: dict[str, int]
    item_reason_counts: dict[str, int]
    source_attempt_state_counts: dict[SourceFetchState, int]
    parser_failure_signature_counts: dict[str, int]


def build_replay_cohort(
    *,
    repo_root: Path,
    saturation_snapshot_path: Path,
) -> ReplayCohortManifest:
    """Freeze every raw root with no formal case, bound to exact input bytes."""

    repo_root = repo_root.resolve()
    snapshot_path = saturation_snapshot_path.resolve()
    snapshot = load_saturation_snapshot(snapshot_path)
    _verify_snapshot_inputs(repo_root, snapshot.inputs)
    records_by_location = _load_pool_records(repo_root, snapshot.inputs)
    members: list[ReplayCohortMember] = []
    for root in snapshot.roots:
        if not root.raw_records or root.formal_case_ids:
            continue
        publications: list[ReplayPublication] = []
        for raw_ref in root.raw_records:
            location = (raw_ref.pool_file, raw_ref.line_number)
            record, raw_line = records_by_location[location]
            if sha256_bytes(raw_line) != raw_ref.raw_line_sha256:
                raise PatentReplayError(
                    f"raw line hash drift: {raw_ref.pool_file}:{raw_ref.line_number}"
                )
            publications.append(
                ReplayPublication(
                    publication_id=raw_ref.publication_id,
                    source=raw_ref.source,
                    source_url=raw_ref.source_url,
                    title=str(record.get("title") or ""),
                    pool_file=raw_ref.pool_file,
                    line_number=raw_ref.line_number,
                    raw_line_sha256=raw_ref.raw_line_sha256,
                )
            )
        members.append(
            ReplayCohortMember(
                root_id=root.root_id,
                publications=tuple(sorted(publications, key=lambda item: item.publication_id)),
            )
        )
    try:
        snapshot_relative = snapshot_path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise PatentReplayError("saturation snapshot must be inside repository root") from exc
    return ReplayCohortManifest(
        saturation_snapshot=EvidenceRef(
            evidence_type="saturation_snapshot",
            path=snapshot_relative,
            sha256=sha256_bytes(snapshot_path.read_bytes()),
        ),
        inputs=snapshot.inputs,
        members=tuple(sorted(members, key=lambda item: item.root_id)),
    )


def verify_replay_cohort_inputs(
    cohort: ReplayCohortManifest,
    *,
    repo_root: Path,
) -> None:
    repo_root = repo_root.resolve()
    snapshot_path = repo_root / cohort.saturation_snapshot.path
    if not snapshot_path.is_file():
        raise PatentReplayError(f"frozen saturation snapshot is missing: {snapshot_path}")
    if sha256_bytes(snapshot_path.read_bytes()) != cohort.saturation_snapshot.sha256:
        raise PatentReplayError("frozen saturation snapshot hash drift")
    snapshot = load_saturation_snapshot(snapshot_path)
    if snapshot.inputs != cohort.inputs:
        raise PatentReplayError("cohort input manifest differs from saturation snapshot")
    _verify_snapshot_inputs(repo_root, cohort.inputs)


def cohort_sha256(cohort: ReplayCohortManifest) -> str:
    return sha256_bytes(canonical_json_bytes(cohort))


def load_replay_cohort(path: Path) -> ReplayCohortManifest:
    try:
        return ReplayCohortManifest.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise PatentReplayError(f"invalid replay cohort: {path}: {exc}") from exc


def load_root_replay_result(path: Path) -> RootReplayResult:
    try:
        return RootReplayResult.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise PatentReplayError(f"invalid root replay result: {path}: {exc}") from exc


def next_result_attempt(results_dir: Path, root_id: str) -> tuple[Path, int]:
    root_dir = results_dir / root_id
    root_dir.mkdir(parents=True, exist_ok=True)
    for attempt_number in range(1, 1_000_000):
        attempt_dir = root_dir / f"attempt-{attempt_number:04d}"
        try:
            attempt_dir.mkdir()
        except FileExistsError:
            continue
        return attempt_dir / "result.json", attempt_number
    raise PatentReplayError(f"result attempt sequence exhausted: {root_id}")


def latest_result_path(results_dir: Path, root_id: str) -> Path | None:
    root_dir = results_dir / root_id
    if not root_dir.is_dir():
        return None
    attempts: list[tuple[int, Path]] = []
    for path in root_dir.iterdir():
        if not path.is_dir():
            continue
        match = ATTEMPT_DIRECTORY_PATTERN.fullmatch(path.name)
        if match is not None:
            attempts.append((int(match.group("number")), path / "result.json"))
    if not attempts:
        return None
    return max(attempts, key=lambda item: item[0])[1]


def summarize_replay_results(
    cohort: ReplayCohortManifest,
    *,
    results_dir: Path,
) -> ReplaySummary:
    digest = cohort_sha256(cohort)
    missing: list[str] = []
    corrupt: list[str] = []
    root_counts: Counter[RootReplayState] = Counter()
    item_counts: Counter[ReplayItemState] = Counter()
    terminal_counts: Counter[TerminalStatus] = Counter()
    root_reason_counts: Counter[str] = Counter()
    item_reason_counts: Counter[str] = Counter()
    source_attempt_counts: Counter[SourceFetchState] = Counter()
    parser_failure_counts: Counter[str] = Counter()
    roots_with_results = 0
    for member in cohort.members:
        result_path = latest_result_path(results_dir, member.root_id)
        if result_path is None or not result_path.is_file():
            missing.append(member.root_id)
            continue
        try:
            result = load_root_replay_result(result_path)
        except PatentReplayError:
            corrupt.append(result_path.as_posix())
            continue
        if result.cohort_sha256 != digest or result.root_id != member.root_id:
            corrupt.append(result_path.as_posix())
            continue
        roots_with_results += 1
        root_counts[result.root_state] += 1
        root_reason_counts[result.reason_code] += 1
        for source_attempt in result.source_attempts:
            source_attempt_counts[source_attempt.state] += 1
        for item in result.items:
            item_counts[item.state] += 1
            item_reason_counts[item.reason_code] += 1
            if item.state is ReplayItemState.PARSER_REVIEW_REQUIRED:
                parser_failure_counts[parser_failure_signature(item.detail)] += 1
            if item.terminal_status is not None:
                terminal_counts[item.terminal_status] += 1
    next_index = None
    if missing:
        first_missing = missing[0]
        next_index = next(
            index for index, member in enumerate(cohort.members) if member.root_id == first_missing
        )
    root_state_counts = {state: root_counts[state] for state in RootReplayState}
    item_state_counts = {state: item_counts[state] for state in ReplayItemState}
    terminal_status_counts = {status: terminal_counts[status] for status in TerminalStatus}
    return ReplaySummary(
        cohort_sha256=digest,
        cohort_roots=len(cohort.members),
        roots_with_results=roots_with_results,
        missing_root_ids=tuple(missing),
        corrupt_result_paths=tuple(sorted(corrupt)),
        cohort_replay_complete=not missing and not corrupt,
        next_missing_index=next_index,
        root_state_counts=root_state_counts,
        item_state_counts=item_state_counts,
        terminal_status_counts=terminal_status_counts,
        root_reason_counts=dict(sorted(root_reason_counts.items())),
        item_reason_counts=dict(sorted(item_reason_counts.items())),
        source_attempt_state_counts={
            state: source_attempt_counts[state] for state in SourceFetchState
        },
        parser_failure_signature_counts=dict(sorted(parser_failure_counts.items())),
    )


def replay_report_markdown(cohort: ReplayCohortManifest, summary: ReplaySummary) -> str:
    root_counts = "\n".join(
        f"- `{state.value}`: {summary.root_state_counts[state]}" for state in RootReplayState
    )
    item_counts = "\n".join(
        f"- `{state.value}`: {summary.item_state_counts[state]}" for state in ReplayItemState
    )
    terminal_counts = "\n".join(
        f"- `{status.value}`: {summary.terminal_status_counts[status]}"
        for status in TerminalStatus
    )
    root_reason_counts = _markdown_counts(summary.root_reason_counts)
    item_reason_counts = _markdown_counts(summary.item_reason_counts)
    source_attempt_counts = "\n".join(
        f"- `{state.value}`: {summary.source_attempt_state_counts[state]}"
        for state in SourceFetchState
    )
    parser_failure_counts = _markdown_counts(summary.parser_failure_signature_counts)
    return f"""# Frozen local patent-pool replay

## Result

- cohort_sha256: `{summary.cohort_sha256}`
- frozen_roots: {summary.cohort_roots}
- roots_with_results: {summary.roots_with_results}
- missing_roots: {len(summary.missing_root_ids)}
- corrupt_results: {len(summary.corrupt_result_paths)}
- cohort_replay_complete: `{str(summary.cohort_replay_complete).lower()}`
- saturation_complete: `false`
- next_missing_index: {summary.next_missing_index}

The replay-complete flag means every frozen local root has one strict current replay result. It
does not mean source saturation, formal intake, production usability, or an expert verdict.

## Root states

{root_counts}

## Item states

{item_counts}

## Terminal statuses proven by replay receipts

{terminal_counts}

## Root reason codes

{root_reason_counts}

## Item reason codes

{item_reason_counts}

## Source attempts

{source_attempt_counts}

## Parser failure signatures

{parser_failure_counts}
"""


def _markdown_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "- none"
    return "\n".join(
        f"- `{reason}`: {count}"
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )


def parser_failure_signature(detail: str) -> str:
    """Collapse deterministic parser messages into stable, actionable buckets."""

    message = re.sub(r"^[A-Za-z][A-Za-z0-9_]*Error:\s*", "", detail.strip())
    patterns = (
        (r"^AAC Raytech summary metadata did not contain ", "aac_raytech_summary_metadata_missing"),
        (r"^Sunny embodiment \d+ metadata missing:", "sunny_embodiment_metadata_missing"),
        (r"^Sunny S\d+ value is not numeric:", "sunny_surface_value_not_numeric"),
        (r"^SEKONIX .* row is incomplete$", "sekonix_surface_row_incomplete"),
        (r"^SEKONIX .* radius is not numeric:", "sekonix_radius_not_numeric"),
        (r"^surface table index break:", "generic_surface_table_index_break"),
        (r"^surface \d+ radius is not numeric:", "generic_surface_radius_not_numeric"),
        (r"^not a number:", "generic_numeric_token_rejected"),
        (
            r"^'Aspheric Coefficients' section not found in embodiment$",
            "asphere_section_missing",
        ),
        (
            r"^aspheric coefficient table had no Surface # block$",
            "asphere_surface_header_missing",
        ),
        (r"^OCR-corrupted exponent token", "ocr_corrupted_exponent"),
        (
            r"^embodiment f/Fno/HFOV line not found$",
            "generic_summary_metadata_missing",
        ),
        (r"^ConversionInputError:", "conversion_input_validation"),
        (
            r"^embodiment did not produce a prescription$",
            "embodiment_without_prescription_object",
        ),
    )
    for pattern, signature in patterns:
        if re.search(pattern, message, flags=re.IGNORECASE):
            return signature
    if not message:
        return "empty_parser_failure_detail"
    normalized = re.sub(r"(['\"]).*?\1", " token ", message)
    normalized = re.sub(r"\b\d+(?:\.\d+)?(?:e[-+]?\d+)?\b", " n ", normalized, flags=re.I)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    if not normalized:
        normalized = "non_alphanumeric_parser_failure"
    if len(normalized) > 120:
        digest = sha256_bytes(message.encode("utf-8"))[:12]
        normalized = f"{normalized[:107].rstrip('_')}_{digest}"
    return f"other_{normalized}"


def _verify_snapshot_inputs(repo_root: Path, inputs: InputManifest) -> None:
    concatenated = bytearray()
    for input_file in inputs.pool_files:
        path = repo_root / input_file.path
        if not path.is_file():
            raise PatentReplayError(f"frozen pool input is missing: {path}")
        data = path.read_bytes()
        if len(data) != input_file.byte_size or sha256_bytes(data) != input_file.sha256:
            raise PatentReplayError(f"frozen pool input drift: {input_file.path}")
        concatenated.extend(data)
    if sha256_bytes(bytes(concatenated)) != inputs.pool_concat_sha256:
        raise PatentReplayError("frozen pool concatenation hash drift")
    case_index_path = repo_root / inputs.case_index.path
    if not case_index_path.is_file():
        raise PatentReplayError(f"frozen case index is missing: {case_index_path}")
    if sha256_bytes(case_index_path.read_bytes()) != inputs.case_index.sha256:
        raise PatentReplayError("frozen case index hash drift")


def _load_pool_records(
    repo_root: Path,
    inputs: InputManifest,
) -> dict[tuple[str, int], tuple[dict[str, Any], bytes]]:
    records: dict[tuple[str, int], tuple[dict[str, Any], bytes]] = {}
    for input_file in inputs.pool_files:
        data = (repo_root / input_file.path).read_bytes()
        for line_number, raw_line in enumerate(data.splitlines(), start=1):
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PatentReplayError(
                    f"invalid frozen pool JSON: {input_file.path}:{line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise PatentReplayError(
                    f"frozen pool record is not an object: {input_file.path}:{line_number}"
                )
            records[(input_file.path, line_number)] = (record, raw_line)
    return records
