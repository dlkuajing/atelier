from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.patent_saturation import (
    EvidenceRef,
    PatentSaturationError,
    SaturationSnapshot,
    TerminalOutcome,
    TerminalStatus,
    audit_saturation_snapshot,
    build_saturation_snapshot,
    canonical_json_bytes,
    parse_us_publication,
    sha256_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
ZERO_SHA = "0" * 64


def _record(patent_id: str) -> dict:
    return {
        "id": patent_id,
        "title": "Lens system",
        "abstract": "A deterministic optical lens system.",
        "claim_excerpt": "An optical lens system comprising lens elements.",
        "inventors": ["Example; Inventor"],
        "assignee": "Example Optics Co., Ltd.",
        "ipc_classes": ["G02B13/00"],
        "filing_date": "January 1, 2025",
        "source": "uspto",
        "source_url": f"https://ppubs.uspto.gov/{patent_id}",
    }


def _fixture_repo(tmp_path: Path) -> dict[str, Path]:
    pool_dir = tmp_path / "data" / "patents"
    case_dir = tmp_path / "app" / "data" / "optical_cases"
    zmx_dir = tmp_path / "data" / "zmx"
    raw_dir = tmp_path / "data" / "patent-lake" / "raw"
    staging_dir = tmp_path / "data" / "zmx-staging"
    for path in (pool_dir, case_dir, zmx_dir, raw_dir, staging_dir):
        path.mkdir(parents=True)
    records = [_record("US-20250000001-A1"), _record("US-10000001-B2")]
    (pool_dir / "uspto-smartphone-batch1.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    case_index = [
        {
            "case_id": "US-20250000001-A1-e2",
            "source_zmx": "US-20250000001-A1-e2.zmx",
            "scenario": "smartphone-wide",
        },
        {
            "case_id": "3P_example",
            "source_zmx": "3P_example.zmx",
            "scenario": "smartphone-wide",
        },
    ]
    (case_dir / "index.json").write_text(json.dumps(case_index), encoding="utf-8")
    for record in case_index:
        (case_dir / f"{record['case_id']}.json").write_text("{}\n", encoding="utf-8")
        (zmx_dir / record["source_zmx"]).write_text("VERS 160829\n", encoding="utf-8")
    return {
        "repo_root": tmp_path,
        "pool_dir": pool_dir,
        "case_index_path": case_dir / "index.json",
        "case_data_dir": case_dir,
        "zmx_dir": zmx_dir,
        "raw_document_dir": raw_dir,
        "staging_dir": staging_dir,
    }


def _build(paths: dict[str, Path]) -> SaturationSnapshot:
    return build_saturation_snapshot(
        repo_root=paths["repo_root"],
        pool_dir=paths["pool_dir"],
        case_index_path=paths["case_index_path"],
        case_data_dir=paths["case_data_dir"],
        zmx_dir=paths["zmx_dir"],
        raw_document_dir=paths["raw_document_dir"],
        staging_dirs=(paths["staging_dir"],),
    )


@pytest.mark.parametrize(
    ("value", "publication", "root", "embodiment"),
    [
        ("US-20250000001-A1", "US-20250000001-A1", "US-20250000001", None),
        ("US20250000001A1", "US-20250000001-A1", "US-20250000001", None),
        ("US-20250000001-A1-e7.zmx", "US-20250000001-A1", "US-20250000001", 7),
    ],
)
def test_parse_us_publication_is_canonical(
    value: str,
    publication: str,
    root: str,
    embodiment: int | None,
) -> None:
    parsed = parse_us_publication(value)
    assert parsed is not None
    assert parsed.publication_id == publication
    assert parsed.root_id == root
    assert parsed.embodiment_number == embodiment


def test_parse_us_publication_refuses_missing_kind() -> None:
    assert parse_us_publication("US-20250000001") is None


def test_terminal_status_set_is_closed_and_exact() -> None:
    assert {item.value for item in TerminalStatus} == {
        "intaken",
        "duplicate",
        "quality_rejected",
        "confirmed_no_prescription",
        "fulltext_unavailable",
        "parser_family_missing",
        "metadata_unpublished",
        "trace_failed",
        "trace_timeout",
        "externally_blocked",
    }


def test_terminal_outcome_requires_namespaced_reason_and_evidence() -> None:
    evidence = EvidenceRef(evidence_type="raw_xml", path="raw/patent.xml", sha256=ZERO_SHA)
    outcome = TerminalOutcome(
        status=TerminalStatus.TRACE_TIMEOUT,
        reason_code="trace_timeout.hard_deadline_exceeded",
        attempt_id="attempt-0001",
        evidence=(evidence,),
    )
    assert outcome.status is TerminalStatus.TRACE_TIMEOUT
    with pytest.raises(ValidationError, match="namespaced by terminal status"):
        TerminalOutcome(
            status=TerminalStatus.TRACE_TIMEOUT,
            reason_code="trace_failed.nonfinite_image",
            attempt_id="attempt-0001",
            evidence=(evidence,),
        )


def test_builder_is_byte_deterministic_and_audit_fails_closed(tmp_path: Path) -> None:
    paths = _fixture_repo(tmp_path)
    first = _build(paths)
    second = _build(paths)
    first_bytes = canonical_json_bytes(first)
    assert first_bytes == canonical_json_bytes(second)
    assert first.counts.pool_records == 2
    assert first.counts.raw_unique_roots == 2
    assert first.counts.formal_designs_total == 2
    assert first.counts.formal_patent_artifacts == 1
    assert first.counts.raw_formal_overlap_roots == 1
    assert first.counts.raw_roots_without_formal_artifact == 1
    assert first.counts.discovered_unique_roots == 2
    assert first.counts.known_embodiments == 1
    audit = audit_saturation_snapshot(first, snapshot_sha256=sha256_bytes(first_bytes))
    assert audit.saturation_complete is False
    assert audit.errors == (
        "roots_without_retained_fulltext:2",
        "unresolved_embodiment_outcomes:1",
        "unresolved_family_roots:2",
        "unresolved_root_outcomes:2",
    )
    assert SaturationSnapshot.model_validate_json(first_bytes) == first


def test_builder_rejects_duplicate_publication_identity(tmp_path: Path) -> None:
    paths = _fixture_repo(tmp_path)
    duplicate = paths["pool_dir"] / "uspto-smartphone-batch2.jsonl"
    duplicate.write_text(json.dumps(_record("US20250000001A1")) + "\n", encoding="utf-8")
    with pytest.raises(PatentSaturationError, match="duplicate publication"):
        _build(paths)


def test_builder_records_staging_only_patent_candidate(tmp_path: Path) -> None:
    paths = _fixture_repo(tmp_path)
    staging = paths["staging_dir"] / "US-10000001-B2-e1.zmx"
    staging.write_text("VERS 160829\n", encoding="utf-8")
    snapshot = _build(paths)
    assert snapshot.staging_patent_candidates == (
        "data/zmx-staging/US-10000001-B2-e1.zmx",
    )
    audit = audit_saturation_snapshot(snapshot)
    assert "staging_patent_candidates:1" in audit.errors


def test_repository_snapshot_recomputes_current_inputs() -> None:
    snapshot = build_saturation_snapshot(
        repo_root=ROOT,
        pool_dir=ROOT / "data" / "patents",
        case_index_path=ROOT / "app" / "data" / "optical_cases" / "index.json",
        case_data_dir=ROOT / "app" / "data" / "optical_cases",
        zmx_dir=ROOT / "data" / "zmx",
        raw_document_dir=ROOT / "data" / "patent-lake" / "raw",
        staging_dirs=(ROOT / "data" / "zmx-staging", ROOT / "data" / "zmx_staging"),
    )
    pool_record_count = 0
    for path in sorted((ROOT / "data" / "patents").glob("uspto-smartphone-batch*.jsonl")):
        pool_record_count += sum(bool(line.strip()) for line in path.read_bytes().splitlines())
    case_index = json.loads(
        (ROOT / "app" / "data" / "optical_cases" / "index.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot.counts.pool_records == pool_record_count
    assert snapshot.counts.formal_designs_total == len(case_index)
    assert snapshot.counts.raw_unique_publications == snapshot.counts.pool_records
    assert snapshot.counts.raw_roots_without_formal_artifact > 0
    assert audit_saturation_snapshot(snapshot).saturation_complete is False
