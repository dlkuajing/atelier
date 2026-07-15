"""Deterministic control-plane models and builders for patent-pool saturation.

This module deliberately separates discovered/raw patent evidence from formal seed
artifacts.  A formal ZMX already present in the runtime library is evidence that an
artifact exists; it is not, by itself, enough evidence to assign the stricter
``intaken`` terminal status required by the saturation program.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.patent_crawl_schema import validate_patent_record

SCHEMA_VERSION = 1
DEFAULT_POOL_GLOB = "uspto-smartphone-batch*.jsonl"
RAW_DOCUMENT_EXTENSIONS = frozenset({".htm", ".html", ".pdf", ".tif", ".tiff", ".txt", ".xml"})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REASON_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
PUBLICATION_PATTERN = re.compile(
    r"^US[-_]?(?P<number>\d+)[-_]?(?P<kind>[A-Z]\d?)(?:[-_]?E(?P<embodiment>\d+))?$",
    re.IGNORECASE,
)


class PatentSaturationError(ValueError):
    """Raised when saturation inputs or identities are ambiguous or inconsistent."""


class TerminalStatus(StrEnum):
    """The closed set of terminal outcomes authorized by the saturation contract."""

    INTAKEN = "intaken"
    DUPLICATE = "duplicate"
    QUALITY_REJECTED = "quality_rejected"
    CONFIRMED_NO_PRESCRIPTION = "confirmed_no_prescription"
    FULLTEXT_UNAVAILABLE = "fulltext_unavailable"
    PARSER_FAMILY_MISSING = "parser_family_missing"
    METADATA_UNPUBLISHED = "metadata_unpublished"
    TRACE_FAILED = "trace_failed"
    TRACE_TIMEOUT = "trace_timeout"
    EXTERNALLY_BLOCKED = "externally_blocked"


class StrictModel(BaseModel):
    """Frozen, extra-forbidden base model for canonical ledger objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PublicationIdentity(StrictModel):
    publication_id: str
    root_id: str
    kind_code: str
    embodiment_number: int | None = None


class EvidenceRef(StrictModel):
    evidence_type: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class TerminalOutcome(StrictModel):
    status: TerminalStatus
    reason_code: str
    attempt_id: str = Field(min_length=1)
    evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    detail: str = ""

    @model_validator(mode="after")
    def validate_reason_namespace(self) -> TerminalOutcome:
        if not REASON_CODE_PATTERN.fullmatch(self.reason_code):
            raise ValueError("reason_code must be a structured lowercase dotted identifier")
        if not self.reason_code.startswith(f"{self.status.value}."):
            raise ValueError("reason_code must be namespaced by terminal status")
        evidence_keys = [(item.evidence_type, item.path, item.sha256) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("terminal outcome evidence must be unique")
        return self


class InputFile(StrictModel):
    path: str
    byte_size: int = Field(ge=0)
    sha256: str
    record_count: int = Field(ge=0)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class InputManifest(StrictModel):
    pool_files: tuple[InputFile, ...]
    pool_concat_sha256: str
    case_index: EvidenceRef

    @field_validator("pool_concat_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("pool_concat_sha256 must be 64 lowercase hexadecimal characters")
        return value


class RawPatentRecordRef(StrictModel):
    publication_id: str
    root_id: str
    source: str
    source_url: str
    pool_file: str
    line_number: int = Field(ge=1)
    raw_line_sha256: str
    family_hint: str | None = None

    @field_validator("raw_line_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("raw_line_sha256 must be 64 lowercase hexadecimal characters")
        return value


class RawDocumentArtifact(StrictModel):
    publication_id: str
    root_id: str
    media_type: str
    path: str
    sha256: str

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return value


class FormalPatentArtifact(StrictModel):
    publication_id: str
    root_id: str
    embodiment_key: str
    source_embodiment_published: bool
    case_id: str
    source_zmx: str
    index_record_sha256: str
    case_json: EvidenceRef
    zmx: EvidenceRef

    @field_validator("index_record_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("index_record_sha256 must be 64 lowercase hexadecimal characters")
        return value


class EmbodimentRecord(StrictModel):
    embodiment_id: str
    publication_id: str
    root_id: str
    source_embodiment: str | None = None
    formal_case_id: str
    terminal_outcome: TerminalOutcome | None = None


class PatentRootRecord(StrictModel):
    root_id: str
    publication_ids: tuple[str, ...]
    raw_records: tuple[RawPatentRecordRef, ...]
    reported_family_hints: tuple[str, ...]
    family_id: str | None = None
    formal_case_ids: tuple[str, ...]
    terminal_outcome: TerminalOutcome | None = None


class PatentFamilyRecord(StrictModel):
    family_id: str
    member_root_ids: tuple[str, ...] = Field(min_length=1)
    authority_evidence: tuple[EvidenceRef, ...] = Field(min_length=1)
    terminal_outcome: TerminalOutcome | None = None


class SnapshotCounts(StrictModel):
    pool_records: int = Field(ge=0)
    raw_unique_publications: int = Field(ge=0)
    raw_unique_roots: int = Field(ge=0)
    formal_designs_total: int = Field(ge=0)
    formal_patent_artifacts: int = Field(ge=0)
    formal_unique_roots: int = Field(ge=0)
    raw_formal_overlap_roots: int = Field(ge=0)
    raw_roots_without_formal_artifact: int = Field(ge=0)
    formal_roots_outside_raw_pool: int = Field(ge=0)
    discovered_unique_roots: int = Field(ge=0)
    known_embodiments: int = Field(ge=0)
    legacy_unspecified_embodiments: int = Field(ge=0)
    retained_raw_documents: int = Field(ge=0)
    resolved_families: int = Field(ge=0)
    terminal_root_outcomes: int = Field(ge=0)
    terminal_embodiment_outcomes: int = Field(ge=0)
    staging_patent_candidates: int = Field(ge=0)


class SaturationSnapshot(StrictModel):
    schema_version: int = SCHEMA_VERSION
    inputs: InputManifest
    raw_documents: tuple[RawDocumentArtifact, ...]
    formal_artifacts: tuple[FormalPatentArtifact, ...]
    families: tuple[PatentFamilyRecord, ...]
    roots: tuple[PatentRootRecord, ...]
    embodiments: tuple[EmbodimentRecord, ...]
    staging_patent_candidates: tuple[str, ...]
    counts: SnapshotCounts

    @model_validator(mode="after")
    def validate_unique_identities(self) -> SaturationSnapshot:
        _require_unique((item.root_id for item in self.roots), "root_id")
        _require_unique((item.family_id for item in self.families), "family_id")
        _require_unique((item.case_id for item in self.formal_artifacts), "formal case_id")
        _require_unique((item.embodiment_id for item in self.embodiments), "embodiment_id")
        _require_unique(
            (
                (item.pool_file, item.line_number, item.publication_id)
                for root in self.roots
                for item in root.raw_records
            ),
            "raw record identity",
        )
        return self


class SaturationAudit(StrictModel):
    schema_version: int = SCHEMA_VERSION
    snapshot_sha256: str
    saturation_complete: bool
    errors: tuple[str, ...]
    unresolved_family_root_ids: tuple[str, ...]
    unresolved_family_ids: tuple[str, ...]
    unresolved_root_ids: tuple[str, ...]
    unresolved_embodiment_ids: tuple[str, ...]
    legacy_unspecified_embodiment_ids: tuple[str, ...]
    roots_without_retained_fulltext: tuple[str, ...]
    staging_patent_candidates: tuple[str, ...]
    terminal_status_counts: dict[TerminalStatus, int]

    @field_validator("snapshot_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("snapshot_sha256 must be 64 lowercase hexadecimal characters")
        return value


def parse_us_publication(value: str) -> PublicationIdentity | None:
    """Parse one US publication/case stem without inventing a missing kind code."""

    stem = Path(value.strip()).stem.upper()
    match = PUBLICATION_PATTERN.fullmatch(stem)
    if match is None:
        return None
    number = match.group("number")
    kind = match.group("kind").upper()
    embodiment = match.group("embodiment")
    return PublicationIdentity(
        publication_id=f"US-{number}-{kind}",
        root_id=f"US-{number}",
        kind_code=kind,
        embodiment_number=int(embodiment) if embodiment is not None else None,
    )


def canonical_json_bytes(value: BaseModel | dict[str, Any]) -> bytes:
    """Return stable UTF-8 JSON bytes with a single trailing newline."""

    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def build_saturation_snapshot(
    *,
    repo_root: Path,
    pool_dir: Path,
    case_index_path: Path,
    case_data_dir: Path,
    zmx_dir: Path,
    raw_document_dir: Path,
    staging_dirs: tuple[Path, ...],
    pool_glob: str = DEFAULT_POOL_GLOB,
) -> SaturationSnapshot:
    """Build a deterministic snapshot from repository bytes.

    The builder records unresolved state explicitly as ``terminal_outcome=None``.  The
    separate auditor treats every such value as an error; it is never serialized as an
    authorized terminal status.
    """

    repo_root = repo_root.resolve()
    pool_files = sorted(pool_dir.glob(pool_glob), key=lambda path: _relative(repo_root, path))
    if not pool_files:
        raise PatentSaturationError(f"no patent pool files matched {pool_dir / pool_glob}")

    input_files: list[InputFile] = []
    raw_refs_by_root: dict[str, list[RawPatentRecordRef]] = defaultdict(list)
    publications_seen: dict[str, tuple[str, int]] = {}
    concatenated_pool_bytes = bytearray()

    for pool_path in pool_files:
        file_bytes = pool_path.read_bytes()
        concatenated_pool_bytes.extend(file_bytes)
        record_count = 0
        for line_number, raw_line in enumerate(file_bytes.splitlines(), start=1):
            if not raw_line.strip():
                continue
            record_count += 1
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PatentSaturationError(f"{pool_path}:{line_number}: invalid UTF-8 JSON") from exc
            validate_patent_record(record)
            identity = parse_us_publication(str(record["id"]))
            if identity is None:
                raise PatentSaturationError(
                    f"{pool_path}:{line_number}: unsupported publication identity {record['id']!r}"
                )
            previous = publications_seen.get(identity.publication_id)
            location = (_relative(repo_root, pool_path), line_number)
            if previous is not None:
                raise PatentSaturationError(
                    f"duplicate publication {identity.publication_id}: {previous} and {location}"
                )
            publications_seen[identity.publication_id] = location
            family_hint = record.get("family_hint")
            raw_refs_by_root[identity.root_id].append(
                RawPatentRecordRef(
                    publication_id=identity.publication_id,
                    root_id=identity.root_id,
                    source=str(record["source"]),
                    source_url=str(record["source_url"]),
                    pool_file=_relative(repo_root, pool_path),
                    line_number=line_number,
                    raw_line_sha256=sha256_bytes(raw_line),
                    family_hint=str(family_hint) if family_hint else None,
                )
            )
        input_files.append(
            InputFile(
                path=_relative(repo_root, pool_path),
                byte_size=len(file_bytes),
                sha256=sha256_bytes(file_bytes),
                record_count=record_count,
            )
        )

    if not case_index_path.is_file():
        raise PatentSaturationError(f"case index is missing: {case_index_path}")
    case_index_bytes = case_index_path.read_bytes()
    try:
        case_index = json.loads(case_index_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PatentSaturationError(f"case index is not valid UTF-8 JSON: {case_index_path}") from exc
    if not isinstance(case_index, list):
        raise PatentSaturationError("case index must contain a JSON list")

    formal_artifacts: list[FormalPatentArtifact] = []
    embodiments: list[EmbodimentRecord] = []
    formal_case_ids_by_root: dict[str, list[str]] = defaultdict(list)
    formal_root_ids: set[str] = set()
    formal_case_ids_seen: set[str] = set()

    for record in case_index:
        if not isinstance(record, dict):
            raise PatentSaturationError("case index records must be JSON objects")
        case_id = str(record.get("case_id") or "")
        if not case_id:
            raise PatentSaturationError("case index record is missing case_id")
        if case_id in formal_case_ids_seen:
            raise PatentSaturationError(f"duplicate formal case_id: {case_id}")
        formal_case_ids_seen.add(case_id)
        identity = parse_us_publication(case_id)
        if identity is None:
            continue
        source_zmx = str(record.get("source_zmx") or "")
        if not source_zmx:
            raise PatentSaturationError(f"patent case {case_id} is missing source_zmx")
        case_json_path = case_data_dir / f"{case_id}.json"
        zmx_path = zmx_dir / source_zmx
        if not case_json_path.is_file():
            raise PatentSaturationError(f"formal case JSON is missing: {case_json_path}")
        if not zmx_path.is_file():
            raise PatentSaturationError(f"formal ZMX is missing: {zmx_path}")

        source_embodiment = (
            f"e{identity.embodiment_number}" if identity.embodiment_number is not None else None
        )
        embodiment_key = source_embodiment or f"legacy-case:{case_id}"
        artifact = FormalPatentArtifact(
            publication_id=identity.publication_id,
            root_id=identity.root_id,
            embodiment_key=embodiment_key,
            source_embodiment_published=source_embodiment is not None,
            case_id=case_id,
            source_zmx=source_zmx,
            index_record_sha256=sha256_bytes(canonical_json_bytes(record)),
            case_json=_evidence(repo_root, case_json_path, "formal_case_json"),
            zmx=_evidence(repo_root, zmx_path, "formal_zmx"),
        )
        formal_artifacts.append(artifact)
        formal_case_ids_by_root[identity.root_id].append(case_id)
        formal_root_ids.add(identity.root_id)
        embodiments.append(
            EmbodimentRecord(
                embodiment_id=f"{identity.publication_id}:{embodiment_key}",
                publication_id=identity.publication_id,
                root_id=identity.root_id,
                source_embodiment=source_embodiment,
                formal_case_id=case_id,
                terminal_outcome=None,
            )
        )

    raw_documents = _scan_raw_documents(repo_root, raw_document_dir)
    all_root_ids = sorted(set(raw_refs_by_root) | formal_root_ids)
    roots: list[PatentRootRecord] = []
    for root_id in all_root_ids:
        raw_records = sorted(
            raw_refs_by_root.get(root_id, []),
            key=lambda item: (item.publication_id, item.pool_file, item.line_number),
        )
        formal_case_ids = tuple(sorted(formal_case_ids_by_root.get(root_id, [])))
        publications = sorted(
            {item.publication_id for item in raw_records}
            | {
                item.publication_id
                for item in formal_artifacts
                if item.root_id == root_id
            }
        )
        hints = tuple(sorted({item.family_hint for item in raw_records if item.family_hint}))
        roots.append(
            PatentRootRecord(
                root_id=root_id,
                publication_ids=tuple(publications),
                raw_records=tuple(raw_records),
                reported_family_hints=hints,
                family_id=None,
                formal_case_ids=formal_case_ids,
                terminal_outcome=None,
            )
        )

    staging_candidates = _scan_staging_patent_candidates(
        repo_root,
        staging_dirs,
        formal_case_ids_seen,
    )
    raw_root_ids = set(raw_refs_by_root)
    overlap = raw_root_ids & formal_root_ids
    counts = SnapshotCounts(
        pool_records=sum(item.record_count for item in input_files),
        raw_unique_publications=len(publications_seen),
        raw_unique_roots=len(raw_root_ids),
        formal_designs_total=len(case_index),
        formal_patent_artifacts=len(formal_artifacts),
        formal_unique_roots=len(formal_root_ids),
        raw_formal_overlap_roots=len(overlap),
        raw_roots_without_formal_artifact=len(raw_root_ids - formal_root_ids),
        formal_roots_outside_raw_pool=len(formal_root_ids - raw_root_ids),
        discovered_unique_roots=len(all_root_ids),
        known_embodiments=len(embodiments),
        legacy_unspecified_embodiments=sum(
            item.source_embodiment is None for item in embodiments
        ),
        retained_raw_documents=len(raw_documents),
        resolved_families=0,
        terminal_root_outcomes=0,
        terminal_embodiment_outcomes=0,
        staging_patent_candidates=len(staging_candidates),
    )
    return SaturationSnapshot(
        inputs=InputManifest(
            pool_files=tuple(input_files),
            pool_concat_sha256=sha256_bytes(bytes(concatenated_pool_bytes)),
            case_index=EvidenceRef(
                evidence_type="formal_case_index",
                path=_relative(repo_root, case_index_path),
                sha256=sha256_bytes(case_index_bytes),
            ),
        ),
        raw_documents=tuple(raw_documents),
        formal_artifacts=tuple(sorted(formal_artifacts, key=lambda item: item.case_id)),
        families=(),
        roots=tuple(roots),
        embodiments=tuple(sorted(embodiments, key=lambda item: item.embodiment_id)),
        staging_patent_candidates=tuple(staging_candidates),
        counts=counts,
    )


def audit_saturation_snapshot(
    snapshot: SaturationSnapshot,
    *,
    snapshot_sha256: str | None = None,
) -> SaturationAudit:
    """Return a fail-closed completeness audit for one canonical snapshot."""

    snapshot_bytes = canonical_json_bytes(snapshot)
    digest = snapshot_sha256 or sha256_bytes(snapshot_bytes)
    unresolved_family_roots = tuple(
        item.root_id for item in snapshot.roots if item.family_id is None
    )
    unresolved_families = tuple(
        item.family_id for item in snapshot.families if item.terminal_outcome is None
    )
    unresolved_roots = tuple(
        item.root_id for item in snapshot.roots if item.terminal_outcome is None
    )
    unresolved_embodiments = tuple(
        item.embodiment_id for item in snapshot.embodiments if item.terminal_outcome is None
    )
    legacy_unspecified = tuple(
        item.embodiment_id for item in snapshot.embodiments if item.source_embodiment is None
    )
    fulltext_root_ids = {item.root_id for item in snapshot.raw_documents}
    roots_without_fulltext = tuple(
        root.root_id
        for root in snapshot.roots
        if root.root_id not in fulltext_root_ids
        and (
            root.terminal_outcome is None
            or root.terminal_outcome.status
            not in {TerminalStatus.FULLTEXT_UNAVAILABLE, TerminalStatus.EXTERNALLY_BLOCKED}
        )
    )

    status_counts = dict.fromkeys(TerminalStatus, 0)
    for outcome in (
        [item.terminal_outcome for item in snapshot.families]
        + [item.terminal_outcome for item in snapshot.roots]
        + [item.terminal_outcome for item in snapshot.embodiments]
    ):
        if outcome is not None:
            status_counts[outcome.status] += 1

    errors: list[str] = []
    _append_count_error(errors, "unresolved_family_roots", unresolved_family_roots)
    _append_count_error(errors, "unresolved_families", unresolved_families)
    _append_count_error(errors, "unresolved_root_outcomes", unresolved_roots)
    _append_count_error(errors, "unresolved_embodiment_outcomes", unresolved_embodiments)
    _append_count_error(errors, "legacy_unspecified_embodiments", legacy_unspecified)
    _append_count_error(errors, "roots_without_retained_fulltext", roots_without_fulltext)
    _append_count_error(
        errors,
        "staging_patent_candidates",
        snapshot.staging_patent_candidates,
    )

    family_by_id = {item.family_id: item for item in snapshot.families}
    root_by_id = {item.root_id: item for item in snapshot.roots}
    artifact_by_case = {item.case_id: item for item in snapshot.formal_artifacts}
    for root in snapshot.roots:
        if root.family_id is not None:
            family = family_by_id.get(root.family_id)
            if family is None or root.root_id not in family.member_root_ids:
                errors.append(f"family_membership_mismatch:{root.root_id}")
    for family in snapshot.families:
        for root_id in family.member_root_ids:
            root = root_by_id.get(root_id)
            if root is None or root.family_id != family.family_id:
                errors.append(f"family_member_reverse_mismatch:{family.family_id}:{root_id}")
    for embodiment in snapshot.embodiments:
        artifact = artifact_by_case.get(embodiment.formal_case_id)
        if artifact is None:
            errors.append(f"formal_artifact_missing:{embodiment.embodiment_id}")
            continue
        if embodiment.terminal_outcome is not None:
            if embodiment.terminal_outcome.status is not TerminalStatus.INTAKEN:
                errors.append(f"formal_artifact_non_intaken:{embodiment.embodiment_id}")
            if artifact.root_id != embodiment.root_id:
                errors.append(f"formal_artifact_root_mismatch:{embodiment.embodiment_id}")
    errors = sorted(set(errors))
    return SaturationAudit(
        snapshot_sha256=digest,
        saturation_complete=not errors,
        errors=tuple(errors),
        unresolved_family_root_ids=unresolved_family_roots,
        unresolved_family_ids=unresolved_families,
        unresolved_root_ids=unresolved_roots,
        unresolved_embodiment_ids=unresolved_embodiments,
        legacy_unspecified_embodiment_ids=legacy_unspecified,
        roots_without_retained_fulltext=roots_without_fulltext,
        staging_patent_candidates=snapshot.staging_patent_candidates,
        terminal_status_counts=status_counts,
    )


def saturation_report_markdown(snapshot: SaturationSnapshot, audit: SaturationAudit) -> str:
    """Render a compact deterministic baseline report."""

    counts = snapshot.counts
    status_lines = "\n".join(
        f"- `{status.value}`: {audit.terminal_status_counts[status]}"
        for status in TerminalStatus
    )
    errors = "\n".join(f"- `{item}`" for item in audit.errors) or "- none"
    return f"""# Patent saturation baseline

## Result

- saturation_complete: `{str(audit.saturation_complete).lower()}`
- snapshot_sha256: `{audit.snapshot_sha256}`
- pool_concat_sha256: `{snapshot.inputs.pool_concat_sha256}`
- case_index_sha256: `{snapshot.inputs.case_index.sha256}`

The snapshot is intentionally fail-closed. Existing formal patent ZMX/case files are recorded
as artifacts, but are not promoted to `intaken` until retained source/full-text and exact
embodiment provenance satisfy the stricter saturation contract.

## Recomputed inventory

- pool records / unique publications / unique roots: {counts.pool_records} /
  {counts.raw_unique_publications} / {counts.raw_unique_roots}
- formal designs / patent artifacts / patent roots: {counts.formal_designs_total} /
  {counts.formal_patent_artifacts} / {counts.formal_unique_roots}
- raw/formal overlap roots: {counts.raw_formal_overlap_roots}
- raw roots without formal artifact: {counts.raw_roots_without_formal_artifact}
- formal roots outside raw pool: {counts.formal_roots_outside_raw_pool}
- discovered union roots: {counts.discovered_unique_roots}
- known formal embodiments / legacy-unspecified: {counts.known_embodiments} /
  {counts.legacy_unspecified_embodiments}
- retained raw documents: {counts.retained_raw_documents}
- staging-only patent candidates: {counts.staging_patent_candidates}

## Terminal status counts

{status_lines}

## Failing completeness checks

{errors}

This report is a baseline control-plane artifact, not saturation completion, an expert verdict,
or evidence of production usability.
"""


def load_saturation_snapshot(path: Path) -> SaturationSnapshot:
    try:
        return SaturationSnapshot.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise PatentSaturationError(f"invalid saturation snapshot: {path}: {exc}") from exc


def _scan_raw_documents(repo_root: Path, raw_document_dir: Path) -> list[RawDocumentArtifact]:
    if not raw_document_dir.is_dir():
        return []
    artifacts: list[RawDocumentArtifact] = []
    for path in sorted(
        (item for item in raw_document_dir.rglob("*") if item.is_file()),
        key=lambda item: _relative(repo_root, item),
    ):
        if path.suffix.lower() not in RAW_DOCUMENT_EXTENSIONS:
            continue
        identity = parse_us_publication(path.stem)
        if identity is None:
            raise PatentSaturationError(f"raw document filename has no publication identity: {path}")
        artifacts.append(
            RawDocumentArtifact(
                publication_id=identity.publication_id,
                root_id=identity.root_id,
                media_type=path.suffix.lower().lstrip("."),
                path=_relative(repo_root, path),
                sha256=sha256_bytes(path.read_bytes()),
            )
        )
    _require_unique(
        ((item.publication_id, item.media_type, item.path) for item in artifacts),
        "raw document artifact",
    )
    return artifacts


def _scan_staging_patent_candidates(
    repo_root: Path,
    staging_dirs: tuple[Path, ...],
    formal_case_ids: set[str],
) -> list[str]:
    candidates: list[str] = []
    for staging_dir in staging_dirs:
        if not staging_dir.is_dir():
            continue
        for path in sorted(
            (item for item in staging_dir.rglob("*") if item.is_file()),
            key=lambda item: _relative(repo_root, item),
        ):
            if path.suffix.lower() != ".zmx" or parse_us_publication(path.stem) is None:
                continue
            if path.stem not in formal_case_ids:
                candidates.append(_relative(repo_root, path))
    return sorted(set(candidates))


def _evidence(repo_root: Path, path: Path, evidence_type: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_type=evidence_type,
        path=_relative(repo_root, path),
        sha256=sha256_bytes(path.read_bytes()),
    )


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise PatentSaturationError(f"path escapes repository root: {path}") from exc


def _require_unique(values: Any, label: str) -> None:
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {label}: {value}")
        seen.add(value)


def _append_count_error(errors: list[str], label: str, values: tuple[Any, ...]) -> None:
    if values:
        errors.append(f"{label}:{len(values)}")
