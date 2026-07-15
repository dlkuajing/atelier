from __future__ import annotations

import asyncio
import math
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from app.core.patent_replay import (
    PatentReplayError,
    ReplayCohortManifest,
    ReplayItemResult,
    ReplayItemState,
    RootReplayResult,
    RootReplayState,
    SourceFetchAttempt,
    SourceFetchState,
    build_replay_cohort,
    canonical_json_bytes,
    cohort_sha256,
    latest_result_path,
    load_replay_cohort,
    load_root_replay_result,
    next_result_attempt,
    parser_failure_signature,
    sha256_bytes,
    summarize_replay_results,
    verify_replay_cohort_inputs,
)
from app.core.patent_saturation import EvidenceRef, TerminalStatus
from scripts import patent_pool_replay, patent_to_zmx

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "patent-ledger" / "snapshot.json"


def _actual_cohort() -> ReplayCohortManifest:
    return build_replay_cohort(repo_root=ROOT, saturation_snapshot_path=SNAPSHOT)


def _source_error(publication_id: str = "US-TEST-A1") -> SourceFetchAttempt:
    return SourceFetchAttempt(
        publication_id=publication_id,
        source_bucket="US-PGPUB",
        state=SourceFetchState.HTTP_ERROR,
        http_status=404,
        exception_type="HTTPStatusError",
    )


def _nonterminal_result(
    cohort: ReplayCohortManifest,
    *,
    root_id: str,
    publication_id: str,
    result_attempt: int,
) -> RootReplayResult:
    return RootReplayResult(
        cohort_sha256=cohort_sha256(cohort),
        root_id=root_id,
        result_attempt=result_attempt,
        publication_id=publication_id,
        root_state=RootReplayState.SOURCE_EXHAUSTED_PENDING_ALTERNATES,
        reason_code=(
            "source_exhausted_pending_alternates.uspto_ppubs_all_buckets_not_found"
        ),
        source_attempts=(_source_error(publication_id),),
        items=(),
    )


def test_actual_frozen_cohort_is_exact_deterministic_619_root_complement() -> None:
    first = _actual_cohort()
    second = _actual_cohort()

    assert len(first.members) == 619
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert cohort_sha256(first) == cohort_sha256(second)
    assert [member.root_id for member in first.members] == sorted(
        member.root_id for member in first.members
    )
    assert sum(len(member.publications) for member in first.members) == 619
    verify_replay_cohort_inputs(first, repo_root=ROOT)


def test_frozen_cohort_refuses_snapshot_or_input_manifest_drift() -> None:
    cohort = _actual_cohort()
    bad_snapshot_ref = cohort.saturation_snapshot.model_copy(update={"sha256": "0" * 64})
    bad_snapshot = cohort.model_copy(update={"saturation_snapshot": bad_snapshot_ref})
    with pytest.raises(PatentReplayError, match="snapshot hash drift"):
        verify_replay_cohort_inputs(bad_snapshot, repo_root=ROOT)

    bad_case_ref = cohort.inputs.case_index.model_copy(update={"sha256": "0" * 64})
    bad_inputs = cohort.inputs.model_copy(update={"case_index": bad_case_ref})
    bad_manifest = cohort.model_copy(update={"inputs": bad_inputs})
    with pytest.raises(PatentReplayError, match="input manifest differs"):
        verify_replay_cohort_inputs(bad_manifest, repo_root=ROOT)


def test_summary_is_resumable_append_only_and_fails_closed_on_corrupt_latest(
    tmp_path: Path,
) -> None:
    actual = _actual_cohort()
    cohort = actual.model_copy(update={"members": actual.members[:2]})
    results = tmp_path / "results"

    first_member = cohort.members[0]
    first_path, first_number = next_result_attempt(results, first_member.root_id)
    first_result = _nonterminal_result(
        cohort,
        root_id=first_member.root_id,
        publication_id=first_member.publications[0].publication_id,
        result_attempt=first_number,
    )
    first_path.write_bytes(canonical_json_bytes(first_result))

    partial = summarize_replay_results(cohort, results_dir=results)
    assert partial.roots_with_results == 1
    assert partial.result_file_count == 1
    assert partial.missing_root_ids == (cohort.members[1].root_id,)
    assert partial.next_missing_index == 1
    assert partial.cohort_replay_complete is False
    assert partial.saturation_complete is False

    second_member = cohort.members[1]
    second_path, second_number = next_result_attempt(results, second_member.root_id)
    second_result = _nonterminal_result(
        cohort,
        root_id=second_member.root_id,
        publication_id=second_member.publications[0].publication_id,
        result_attempt=second_number,
    )
    second_path.write_bytes(canonical_json_bytes(second_result))
    complete = summarize_replay_results(cohort, results_dir=results)
    assert complete.roots_with_results == 2
    assert complete.result_file_count == 2
    assert complete.cohort_replay_complete is True
    assert complete.root_state_counts[
        RootReplayState.SOURCE_EXHAUSTED_PENDING_ALTERNATES
    ] == 2
    assert complete.result_set_sha256 == summarize_replay_results(
        cohort, results_dir=results
    ).result_set_sha256

    corrupt_path, retry_number = next_result_attempt(results, first_member.root_id)
    assert retry_number == 2
    corrupt_path.write_text("not json", encoding="utf-8")
    corrupt = summarize_replay_results(cohort, results_dir=results)
    assert corrupt.roots_with_results == 1
    assert corrupt.result_file_count == 1
    assert corrupt.corrupt_result_paths == (corrupt_path.as_posix(),)
    assert corrupt.cohort_replay_complete is False


def test_audit_fails_closed_when_referenced_external_evidence_is_missing(
    tmp_path: Path,
) -> None:
    actual = _actual_cohort()
    cohort = actual.model_copy(update={"members": actual.members[:1]})
    member = cohort.members[0]
    publication_id = member.publications[0].publication_id
    raw = tmp_path / "raw.html"
    raw.write_bytes(b"raw")
    evidence = EvidenceRef(
        evidence_type="uspto_ppubs_parser_input_html",
        path=raw.relative_to(tmp_path).as_posix(),
        sha256=sha256_bytes(raw.read_bytes()),
    )
    item = ReplayItemResult(
        item_id=f"{publication_id}:document",
        state=ReplayItemState.PARSER_REVIEW_REQUIRED,
        reason_code="parser_review_required.deterministic_parser_rejected",
        detail="PatentParseError: fixture",
        evidence=(evidence,),
    )
    result = RootReplayResult(
        cohort_sha256=cohort_sha256(cohort),
        root_id=member.root_id,
        result_attempt=1,
        publication_id=publication_id,
        root_state=RootReplayState.PARSER_REVIEW_REQUIRED,
        reason_code="parser_review_required.all_disclosed_items_rejected",
        source_attempts=(
            SourceFetchAttempt(
                publication_id=publication_id,
                source_bucket="fixture",
                state=SourceFetchState.RETAINED,
                http_status=200,
            ),
        ),
        raw_document=evidence,
        items=(item,),
    )
    result_path, _ = next_result_attempt(tmp_path / "results", member.root_id)
    result_path.write_bytes(canonical_json_bytes(result))

    assert summarize_replay_results(
        cohort,
        results_dir=tmp_path / "results",
        evidence_root=tmp_path,
    ).cohort_replay_complete
    raw.unlink()
    missing = summarize_replay_results(
        cohort,
        results_dir=tmp_path / "results",
        evidence_root=tmp_path,
    )
    assert missing.cohort_replay_complete is False
    assert missing.corrupt_result_paths == (result_path.as_posix(),)


def test_run_replay_resumes_without_refetching_completed_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual = _actual_cohort()
    cohort = actual.model_copy(update={"members": actual.members[:2]})
    token_calls = 0
    replayed_roots: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    async def fake_token(_client: object) -> str:
        nonlocal token_calls
        token_calls += 1
        return "not-recorded"

    async def fake_replay_member(
        _client: object,
        _token: str,
        *,
        cohort_sha256_value: str,
        member: object,
        result_attempt: int,
        **_kwargs: object,
    ) -> RootReplayResult:
        root_id = member.root_id
        replayed_roots.append(root_id)
        publication_id = member.publications[0].publication_id
        result = _nonterminal_result(
            cohort,
            root_id=root_id,
            publication_id=publication_id,
            result_attempt=result_attempt,
        )
        assert result.cohort_sha256 == cohort_sha256_value
        return result

    monkeypatch.setattr(patent_pool_replay.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(patent_pool_replay, "_ppubs_access_token", fake_token)
    monkeypatch.setattr(patent_pool_replay, "_replay_member", fake_replay_member)
    kwargs = {
        "results_dir": tmp_path / "results",
        "summary_path": tmp_path / "summary.json",
        "report_path": tmp_path / "report.md",
        "raw_document_dir": tmp_path / "raw",
        "attempts_dir": tmp_path / "attempts",
        "staging_dir": tmp_path / "staging",
        "limit": 1,
        "delay_seconds": 0.0,
        "conversion_timeout_seconds": 1.0,
        "patent_budget_seconds": 10.0,
    }

    assert asyncio.run(patent_pool_replay.run_replay(cohort, **kwargs)) == 1
    assert asyncio.run(patent_pool_replay.run_replay(cohort, **kwargs)) == 1
    assert asyncio.run(patent_pool_replay.run_replay(cohort, **kwargs)) == 0

    assert replayed_roots == [member.root_id for member in cohort.members]
    assert token_calls == 2
    assert summarize_replay_results(
        cohort, results_dir=tmp_path / "results"
    ).cohort_replay_complete

    kwargs["retry_root_states"] = frozenset(
        {RootReplayState.SOURCE_EXHAUSTED_PENDING_ALTERNATES}
    )
    assert asyncio.run(patent_pool_replay.run_replay(cohort, **kwargs)) == 1
    assert replayed_roots[-1] == cohort.members[0].root_id
    assert token_calls == 3

    kwargs["retry_root_states"] = None
    kwargs["retry_parser_signatures"] = frozenset(
        {"aac_raytech_summary_metadata_missing"}
    )
    assert asyncio.run(patent_pool_replay.run_replay(cohort, **kwargs)) == 0
    assert token_calls == 3

    kwargs["retry_parser_signatures"] = frozenset(
        {"sunny_embodiment_metadata_missing"}
    )
    latest = latest_result_path(tmp_path / "results", cohort.members[0].root_id)
    assert latest is not None
    previous = load_root_replay_result(latest)
    parser_evidence = EvidenceRef(
        evidence_type="fixture",
        path="fixture.html",
        sha256="0" * 64,
    )
    parser_item = ReplayItemResult(
        item_id=f"{previous.publication_id}:e1",
        state=ReplayItemState.PARSER_REVIEW_REQUIRED,
        reason_code="parser_review_required.deterministic_parser_rejected",
        detail="PatentParseError: Sunny embodiment 1 metadata missing: Fno",
        evidence=(parser_evidence,),
    )
    parser_result = RootReplayResult(
        cohort_sha256=previous.cohort_sha256,
        root_id=previous.root_id,
        result_attempt=previous.result_attempt + 1,
        publication_id=previous.publication_id,
        root_state=RootReplayState.PARSER_REVIEW_REQUIRED,
        reason_code="parser_review_required.all_disclosed_items_rejected",
        source_attempts=(
            SourceFetchAttempt(
                publication_id=previous.publication_id,
                source_bucket="fixture",
                state=SourceFetchState.RETAINED,
                http_status=200,
            ),
        ),
        raw_document=parser_evidence,
        items=(parser_item,),
    )
    parser_path, _ = next_result_attempt(
        tmp_path / "results", cohort.members[0].root_id
    )
    parser_path.write_bytes(canonical_json_bytes(parser_result))
    assert asyncio.run(patent_pool_replay.run_replay(cohort, **kwargs)) == 1
    assert replayed_roots[-1] == cohort.members[0].root_id
    assert token_calls == 4


def test_replay_schemas_reject_unstructured_or_duplicate_outcomes() -> None:
    evidence = EvidenceRef(evidence_type="fixture", path="fixture", sha256="0" * 64)
    with pytest.raises(ValidationError, match="namespaced"):
        ReplayItemResult(
            item_id="US-TEST-A1:e1",
            state=ReplayItemState.TERMINAL,
            reason_code="quality_rejected.bad",
            terminal_status=TerminalStatus.QUALITY_REJECTED,
            evidence=(evidence,),
        )

    item = ReplayItemResult(
        item_id="US-TEST-A1:e1",
        state=ReplayItemState.TERMINAL,
        reason_code="terminal.process_receipt_classified",
        terminal_status=TerminalStatus.QUALITY_REJECTED,
        evidence=(evidence,),
    )
    with pytest.raises(ValidationError, match="item IDs must be unique"):
        RootReplayResult(
            cohort_sha256="0" * 64,
            root_id="US-TEST",
            result_attempt=1,
            publication_id="US-TEST-A1",
            root_state=RootReplayState.TERMINAL,
            reason_code="terminal.all_disclosed_items_terminal",
            source_attempts=(
                SourceFetchAttempt(
                    publication_id="US-TEST-A1",
                    source_bucket="fixture",
                    state=SourceFetchState.RETAINED,
                    http_status=200,
                ),
            ),
            raw_document=evidence,
            items=(item, item),
        )


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        (
            "PatentParseError: AAC Raytech summary metadata did not contain f/F number/FOV for example 3",
            "aac_raytech_summary_metadata_missing",
        ),
        (
            "PatentParseError: Sunny embodiment 6 metadata missing: Fno, Semi-FOV",
            "sunny_embodiment_metadata_missing",
        ),
        (
            "PatentParseError: SEKONIX surface 3600 row is incomplete",
            "sekonix_surface_row_incomplete",
        ),
        (
            "PatentParseError: surface 18 radius is not numeric: Surface",
            "generic_surface_radius_not_numeric",
        ),
        (
            "PatentParseError: vendor format token 123 was misplaced",
            "other_vendor_format_token_n_was_misplaced",
        ),
    ],
)
def test_parser_failure_signatures_are_deterministic_actionable_buckets(
    detail: str,
    expected: str,
) -> None:
    assert parser_failure_signature(detail) == expected


def test_fetch_fulltext_records_each_official_bucket_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_fetch(
        _client: object,
        _token: str,
        patent_id: str,
        source: str,
    ) -> str:
        calls.append(source)
        if len(calls) == 1:
            request = httpx.Request("GET", f"https://example.invalid/{patent_id}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("missing", request=request, response=response)
        return "<html>retained</html>"

    monkeypatch.setattr(patent_to_zmx, "_ppubs_patent_html", fake_fetch)
    fetched = asyncio.run(
        patent_to_zmx._fetch_patent_html(object(), "not-recorded", "US-12345678-A1")
    )

    assert fetched.html == "<html>retained</html>"
    assert len(fetched.attempts) == 2
    assert fetched.attempts[0].state is SourceFetchState.HTTP_ERROR
    assert fetched.attempts[0].http_status == 404
    assert fetched.attempts[1].state is SourceFetchState.RETAINED
    assert {attempt.publication_id for attempt in fetched.attempts} == {"US-12345678-A1"}


def test_fetch_fulltext_raises_with_complete_structured_failure_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_everywhere(
        _client: object,
        _token: str,
        patent_id: str,
        _source: str,
    ) -> str:
        request = httpx.Request("GET", f"https://example.invalid/{patent_id}")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)

    monkeypatch.setattr(patent_to_zmx, "_ppubs_patent_html", fail_everywhere)
    with pytest.raises(patent_to_zmx.PatentFulltextFetchError) as error:
        asyncio.run(
            patent_to_zmx._fetch_patent_html(
                object(), "not-recorded", "US-12345678-A1"
            )
        )

    assert len(error.value.attempts) == 3
    assert all(
        attempt.state is SourceFetchState.HTTP_ERROR
        and attempt.http_status == 404
        and attempt.publication_id == "US-12345678-A1"
        for attempt in error.value.attempts
    )


def test_document_parse_failure_keeps_retained_source_attempt_and_raw_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = SourceFetchAttempt(
        publication_id="US-TEST-A1",
        source_bucket="US-PGPUB",
        state=SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="<html>fixture</html>",
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    def fail_document_parse(*_args: object, **_kwargs: object) -> object:
        raise patent_to_zmx.PatentParseError("document family unsupported")

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(
        patent_to_zmx, "_parse_prescription_attempts", fail_document_parse
    )
    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-TEST-A1",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert len(attempts) == 1
    assert attempts[0].status == "failed"
    assert attempts[0].source_attempts == (source_attempt,)
    assert Path(attempts[0].raw_document_path).is_file()
    assert attempts[0].raw_document_sha256 == sha256_bytes(b"<html>fixture</html>")


def test_conversion_request_encodes_explicit_infinite_radius_as_zmx_plane(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "source.html"
    raw.write_bytes(b"fixture")
    prescription = patent_to_zmx.PatentPrescription(
        patent_id="US-TEST-A1",
        embodiment="Embodiment 1",
        focal_length_mm=4.0,
        f_number=2.0,
        hfov_deg=30.0,
        surfaces=[
            patent_to_zmx.PatentSurface(
                index=0,
                label="plane",
                radius_mm=math.inf,
                thickness_mm=1.0,
                material=None,
                nd=None,
                vd=None,
                surface_type="SPH",
            )
        ],
    )
    source = patent_to_zmx.SourceDocumentEvidence(
        source_bucket="fixture",
        retained_path=raw.as_posix(),
        sha256=sha256_bytes(raw.read_bytes()),
    )

    request = patent_to_zmx._conversion_request(prescription, source)

    assert request.prescription.surfaces[0].radius_mm == 0.0
    assert patent_to_zmx.build_readout_from_prescription(prescription).surfaces[0].radius_y_mm == 0.0


def test_invalid_conversion_dto_is_per_embodiment_nonterminal_not_batch_abort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = SourceFetchAttempt(
        publication_id="US-TEST-A1",
        source_bucket="US-PGPUB",
        state=SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="<html>fixture</html>",
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    def invalid_prescription(number: int) -> patent_to_zmx.PatentPrescription:
        return patent_to_zmx.PatentPrescription(
            patent_id="US-TEST-A1",
            embodiment=f"Embodiment {number}",
            focal_length_mm=4.0,
            f_number=2.0,
            hfov_deg=30.0,
            surfaces=[
                patent_to_zmx.PatentSurface(
                    index=0,
                    label="surface",
                    radius_mm=1.0,
                    thickness_mm=1.0,
                    material=None,
                    nd=math.nan,
                    vd=None,
                    surface_type="SPH",
                )
            ],
        )

    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(
        patent_to_zmx,
        "_parse_prescription_attempts",
        lambda *_args, **_kwargs: [
            patent_to_zmx._PrescriptionParseAttempt(
                embodiment_number=number,
                embodiment=f"Embodiment {number}",
                prescription=invalid_prescription(number),
            )
            for number in (1, 2)
        ],
    )

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-TEST-A1",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
        )
    )

    assert len(attempts) == 2
    assert all(attempt.status == "failed" for attempt in attempts)
    assert all(attempt.reason.startswith("ConversionInputError:") for attempt in attempts)
    assert [attempt.embodiment_number for attempt in attempts] == [1, 2]


def test_patent_budget_marks_every_unlaunched_embodiment_for_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_attempt = SourceFetchAttempt(
        publication_id="US-TEST-A1",
        source_bucket="US-PGPUB",
        state=SourceFetchState.RETAINED,
        http_status=200,
    )

    async def fake_fetch(*_args: object) -> patent_to_zmx.FetchedPatentHtml:
        return patent_to_zmx.FetchedPatentHtml(
            html="<html>fixture</html>",
            source_bucket="US-PGPUB",
            attempts=(source_attempt,),
        )

    def valid_prescription(number: int) -> patent_to_zmx.PatentPrescription:
        return patent_to_zmx.PatentPrescription(
            patent_id="US-TEST-A1",
            embodiment=f"Embodiment {number}",
            focal_length_mm=4.0,
            f_number=2.0,
            hfov_deg=30.0,
            surfaces=[
                patent_to_zmx.PatentSurface(
                    index=0,
                    label="surface",
                    radius_mm=1.0,
                    thickness_mm=1.0,
                    material=None,
                    nd=None,
                    vd=None,
                    surface_type="SPH",
                )
            ],
        )

    clock = iter((0.0, 2.0, 2.0))
    monkeypatch.setattr(patent_to_zmx, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr(patent_to_zmx, "_fetch_patent_html", fake_fetch)
    monkeypatch.setattr(
        patent_to_zmx,
        "_parse_prescription_attempts",
        lambda *_args, **_kwargs: [
            patent_to_zmx._PrescriptionParseAttempt(
                embodiment_number=number,
                embodiment=f"Embodiment {number}",
                prescription=valid_prescription(number),
            )
            for number in (1, 2)
        ],
    )

    attempts = asyncio.run(
        patent_to_zmx._convert_candidate(
            object(),
            "not-recorded",
            patent_to_zmx.PatentCandidate(
                patent_id="US-TEST-A1",
                title="fixture",
                source_url="https://example.invalid",
                pool_path=tmp_path / "pool.jsonl",
                line_number=1,
            ),
            tmp_path / "staging",
            raw_document_dir=tmp_path / "raw",
            attempts_dir=tmp_path / "attempts",
            patent_budget_seconds=1.0,
        )
    )

    assert [attempt.status for attempt in attempts] == [
        "conversion_retry_required",
        "conversion_retry_required",
    ]
    assert all(
        attempt.reason_code == "conversion_retry_required.patent_budget_exhausted"
        for attempt in attempts
    )


def test_item_mapping_preserves_evidence_and_never_promotes_staging_to_intaken(
    tmp_path: Path,
) -> None:
    raw = tmp_path / "source.html"
    receipt = tmp_path / "receipt.json"
    zmx = tmp_path / "candidate.zmx"
    raw.write_bytes(b"raw")
    receipt.write_bytes(b"receipt")
    zmx.write_bytes(b"zmx")
    raw_evidence = EvidenceRef(
        evidence_type="source",
        path=raw.as_posix(),
        sha256=sha256_bytes(raw.read_bytes()),
    )
    attempt = patent_to_zmx.ConversionAttempt(
        patent_id="US-TEST-A1",
        title="fixture",
        status="success",
        reason="converted",
        attempt_id="request/attempt-0001",
        request_sha256="1" * 64,
        receipt_path=receipt.as_posix(),
        raw_document_path=raw.as_posix(),
        raw_document_sha256=raw_evidence.sha256,
        embodiment_number=1,
        embodiment="Embodiment 1",
        prescription_fingerprint="2" * 64,
        zmx_path=zmx.as_posix(),
    )

    item = patent_pool_replay._item_from_conversion_attempt(
        attempt,
        publication_id="US-TEST-A1",
        raw_document=raw_evidence,
    )

    assert item.state is ReplayItemState.CONVERTED_PENDING_INTAKE
    assert item.terminal_status is None
    assert item.reason_code == "converted_pending_intake.process_isolated_zmx_ready"
    assert {evidence.evidence_type for evidence in item.evidence} == {
        "source",
        "patent_conversion_receipt",
        "staging_zmx",
    }


@pytest.mark.parametrize(
    ("status", "reason_code", "terminal_status"),
    [
        (
            "metadata_unpublished",
            "metadata_unpublished.stop_axial_coordinate_absent",
            TerminalStatus.METADATA_UNPUBLISHED,
        ),
        (
            "confirmed_no_prescription",
            "confirmed_no_prescription.ir_filter_coating_tables_only",
            TerminalStatus.CONFIRMED_NO_PRESCRIPTION,
        ),
    ],
)
def test_item_mapping_accepts_source_proven_terminal_without_process_receipt(
    tmp_path: Path,
    status: str,
    reason_code: str,
    terminal_status: TerminalStatus,
) -> None:
    raw = tmp_path / "source.html"
    raw.write_bytes(b"official source")
    raw_evidence = EvidenceRef(
        evidence_type="source",
        path=raw.as_posix(),
        sha256=sha256_bytes(raw.read_bytes()),
    )
    attempt = patent_to_zmx.ConversionAttempt(
        patent_id="US-TEST-A1",
        title="fixture",
        status=status,
        reason="source-proven terminal outcome",
        reason_code=reason_code,
        raw_document_path=raw.as_posix(),
        raw_document_sha256=raw_evidence.sha256,
        embodiment_number=1,
        embodiment="Example 1",
    )

    item = patent_pool_replay._item_from_conversion_attempt(
        attempt,
        publication_id="US-TEST-A1",
        raw_document=raw_evidence,
    )

    assert item.state is ReplayItemState.TERMINAL
    assert item.terminal_status is terminal_status
    assert item.reason_code == f"terminal.{reason_code}"
    assert item.conversion_attempt_id is None
    assert item.evidence == (raw_evidence,)


@pytest.mark.parametrize(
    ("source_bucket", "parser_evidence_type"),
    [
        ("USPAT", "uspto_ppubs_recovered_parser_input_html"),
        ("USPTO-PDF-OCR-JSON", "uspto_official_pdf_ocr_parser_input"),
    ],
)
def test_item_mapping_includes_recovered_parser_input_and_linkage_manifest(
    tmp_path: Path,
    source_bucket: str,
    parser_evidence_type: str,
) -> None:
    raw = tmp_path / "primary.html"
    parser_input = tmp_path / "grant.html"
    manifest = tmp_path / "recovery.json"
    receipt = tmp_path / "receipt.json"
    zmx = tmp_path / "candidate.zmx"
    for path, content in (
        (raw, b"primary"),
        (parser_input, b"grant"),
        (manifest, b"manifest"),
        (receipt, b"receipt"),
        (zmx, b"zmx"),
    ):
        path.write_bytes(content)
    raw_evidence = EvidenceRef(
        evidence_type="source",
        path=raw.as_posix(),
        sha256=sha256_bytes(raw.read_bytes()),
    )
    attempt = patent_to_zmx.ConversionAttempt(
        patent_id="US-TEST-A1",
        title="fixture",
        status="success",
        reason="converted",
        attempt_id="request/attempt-0001",
        request_sha256="1" * 64,
        receipt_path=receipt.as_posix(),
        raw_document_path=raw.as_posix(),
        raw_document_sha256=raw_evidence.sha256,
        parser_input_document_path=parser_input.as_posix(),
        parser_input_document_sha256=sha256_bytes(parser_input.read_bytes()),
        parser_input_publication_id="US-TEST-B2",
        parser_input_source_bucket=source_bucket,
        fulltext_recovery_manifest_path=manifest.as_posix(),
        fulltext_recovery_manifest_sha256=sha256_bytes(manifest.read_bytes()),
        embodiment_number=1,
        embodiment="Embodiment 1",
        prescription_fingerprint="2" * 64,
        zmx_path=zmx.as_posix(),
    )

    item = patent_pool_replay._item_from_conversion_attempt(
        attempt,
        publication_id="US-TEST-A1",
        raw_document=raw_evidence,
    )

    assert {evidence.evidence_type for evidence in item.evidence} == {
        "source",
        parser_evidence_type,
        "patent_fulltext_recovery_manifest",
        "patent_conversion_receipt",
        "staging_zmx",
    }


def test_freeze_command_writes_loadable_canonical_artifacts(tmp_path: Path) -> None:
    cohort_path = tmp_path / "cohort.json"
    results_dir = tmp_path / "results"
    summary_path = tmp_path / "summary.json"
    report_path = tmp_path / "report.md"

    cohort = patent_pool_replay.freeze_cohort(
        cohort_path=cohort_path,
        saturation_snapshot_path=SNAPSHOT,
        results_dir=results_dir,
        summary_path=summary_path,
        report_path=report_path,
    )

    assert load_replay_cohort(cohort_path) == cohort
    assert cohort_path.read_bytes() == canonical_json_bytes(cohort)
    assert b"frozen_roots: 619" in report_path.read_bytes()
    assert summarize_replay_results(cohort, results_dir=results_dir).cohort_replay_complete is False
