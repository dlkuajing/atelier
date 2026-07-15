"""Freeze and resumably replay the local uncovered USPTO patent cohort."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.patent_replay import (  # noqa: E402
    PatentReplayError,
    ReplayCohortManifest,
    ReplayCohortMember,
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
    replay_report_markdown,
    sha256_bytes,
    summarize_replay_results,
    verify_replay_cohort_inputs,
)
from app.core.patent_saturation import EvidenceRef, TerminalStatus  # noqa: E402
from scripts.patent_crawler import _ppubs_access_token  # noqa: E402
from scripts.patent_to_zmx import (  # noqa: E402
    DEFAULT_ATTEMPTS_DIR,
    DEFAULT_CONVERSION_TIMEOUT_SECONDS,
    DEFAULT_RAW_DOCUMENT_DIR,
    ConversionAttempt,
    PatentCandidate,
    _convert_candidate,
)

DEFAULT_REPLAY_ROOT = ROOT / "data" / "patent-ledger" / "replay" / "local-uncovered"
DEFAULT_COHORT_PATH = DEFAULT_REPLAY_ROOT / "cohort.json"
DEFAULT_RESULTS_DIR = DEFAULT_REPLAY_ROOT / "results"
DEFAULT_SUMMARY_PATH = DEFAULT_REPLAY_ROOT / "summary.json"
DEFAULT_REPORT_PATH = ROOT / ".planning" / "loop" / "patent-local-replay-report.md"
DEFAULT_SATURATION_SNAPSHOT = ROOT / "data" / "patent-ledger" / "snapshot.json"
DEFAULT_STAGING_DIR = ROOT / "data" / "zmx-staging" / "patent-local-replay"
DEFAULT_REPLAY_ATTEMPTS_DIR = DEFAULT_ATTEMPTS_DIR / "local-replay"
DEFAULT_PATENT_BUDGET_SECONDS = 180.0


def freeze_cohort(
    *,
    cohort_path: Path,
    saturation_snapshot_path: Path,
    results_dir: Path,
    summary_path: Path,
    report_path: Path,
) -> ReplayCohortManifest:
    cohort = build_replay_cohort(
        repo_root=ROOT,
        saturation_snapshot_path=saturation_snapshot_path,
    )
    _atomic_write(cohort_path, canonical_json_bytes(cohort))
    _refresh_summary_artifacts(
        cohort,
        results_dir=results_dir,
        summary_path=summary_path,
        report_path=report_path,
    )
    return cohort


async def run_replay(
    cohort: ReplayCohortManifest,
    *,
    results_dir: Path,
    summary_path: Path,
    report_path: Path,
    raw_document_dir: Path,
    attempts_dir: Path,
    staging_dir: Path,
    limit: int,
    delay_seconds: float,
    conversion_timeout_seconds: float,
    patent_budget_seconds: float,
    only_roots: frozenset[str] | None = None,
    retry_nonterminal: bool = False,
    retry_root_states: frozenset[RootReplayState] | None = None,
    retry_parser_signatures: frozenset[str] | None = None,
) -> int:
    """Replay up to ``limit`` roots, atomically checkpointing after each root."""

    if limit < 0:
        raise PatentReplayError("limit must be non-negative")
    if delay_seconds < 0:
        raise PatentReplayError("delay_seconds must be non-negative")
    if patent_budget_seconds <= 0:
        raise PatentReplayError("patent_budget_seconds must be positive")
    retry_selectors = sum(
        (
            bool(retry_nonterminal),
            bool(retry_root_states),
            bool(retry_parser_signatures),
        )
    )
    if retry_selectors > 1:
        raise PatentReplayError(
            "retry_nonterminal, retry_root_states, and retry_parser_signatures "
            "are mutually exclusive"
        )
    verify_replay_cohort_inputs(cohort, repo_root=ROOT)
    digest = cohort_sha256(cohort)
    selected = [
        member
        for member in cohort.members
        if only_roots is None or member.root_id in only_roots
    ]
    if only_roots is not None:
        missing_requested = sorted(only_roots - {member.root_id for member in selected})
        if missing_requested:
            raise PatentReplayError(
                "requested roots are outside frozen cohort: " + ", ".join(missing_requested)
            )

    pending: list[ReplayCohortMember] = []
    for member in selected:
        latest = latest_result_path(results_dir, member.root_id)
        if latest is not None and latest.is_file():
            previous = load_root_replay_result(latest)
            if previous.cohort_sha256 != digest or previous.root_id != member.root_id:
                raise PatentReplayError(f"result/cohort mismatch: {latest}")
            if retry_root_states is not None:
                if previous.root_state not in retry_root_states:
                    continue
            elif retry_parser_signatures is not None:
                current_signatures = {
                    parser_failure_signature(item.detail)
                    for item in previous.items
                    if item.state is ReplayItemState.PARSER_REVIEW_REQUIRED
                }
                if current_signatures.isdisjoint(retry_parser_signatures):
                    continue
            elif not retry_nonterminal or previous.root_state is RootReplayState.TERMINAL:
                continue
        pending.append(member)
        if limit and len(pending) >= limit:
            break
    if not pending:
        _refresh_summary_artifacts(
            cohort,
            results_dir=results_dir,
            summary_path=summary_path,
            report_path=report_path,
        )
        return 0

    processed = 0
    async with httpx.AsyncClient(timeout=60) as client:
        token = await _ppubs_access_token(client)
        for member in pending:
            result_path, attempt_number = next_result_attempt(results_dir, member.root_id)
            result = await _replay_member(
                client,
                token,
                cohort_sha256_value=digest,
                member=member,
                result_attempt=attempt_number,
                raw_document_dir=raw_document_dir,
                attempts_dir=attempts_dir,
                staging_dir=staging_dir,
                conversion_timeout_seconds=conversion_timeout_seconds,
                patent_budget_seconds=patent_budget_seconds,
            )
            _atomic_write(result_path, canonical_json_bytes(result))
            processed += 1
            _refresh_summary_artifacts(
                cohort,
                results_dir=results_dir,
                summary_path=summary_path,
                report_path=report_path,
            )
            if delay_seconds:
                await asyncio.sleep(delay_seconds)
    _refresh_summary_artifacts(
        cohort,
        results_dir=results_dir,
        summary_path=summary_path,
        report_path=report_path,
    )
    return processed


async def _replay_member(
    client: httpx.AsyncClient,
    token: str,
    *,
    cohort_sha256_value: str,
    member: ReplayCohortMember,
    result_attempt: int,
    raw_document_dir: Path,
    attempts_dir: Path,
    staging_dir: Path,
    conversion_timeout_seconds: float,
    patent_budget_seconds: float,
) -> RootReplayResult:
    combined_source_attempts: list[SourceFetchAttempt] = []
    chosen_publication = member.publications[-1]
    conversion_attempts: list[ConversionAttempt] = []
    for publication in member.publications:
        chosen_publication = publication
        candidate = PatentCandidate(
            patent_id=publication.publication_id,
            title=publication.title,
            source_url=publication.source_url,
            pool_path=ROOT / publication.pool_file,
            line_number=publication.line_number,
        )
        conversion_attempts = await _convert_candidate(
            client,
            token,
            candidate,
            staging_dir,
            formal_case_stems=frozenset(),
            seen_prescription_fingerprints=None,
            raw_document_dir=raw_document_dir,
            attempts_dir=attempts_dir,
            conversion_timeout_seconds=conversion_timeout_seconds,
            patent_budget_seconds=patent_budget_seconds,
        )
        source_attempts = _source_attempts(conversion_attempts)
        combined_source_attempts.extend(source_attempts)
        if any(attempt.state is SourceFetchState.RETAINED for attempt in source_attempts):
            break

    source_attempts = _dedupe_source_attempts(combined_source_attempts)
    if not source_attempts:
        raise PatentReplayError(f"replay produced no source-attempt evidence: {member.root_id}")
    retained_attempt = next(
        (
            attempt
            for attempt in conversion_attempts
            if attempt.raw_document_path and attempt.raw_document_sha256
        ),
        None,
    )
    if retained_attempt is None:
        all_not_found = all(
            attempt.state is SourceFetchState.HTTP_ERROR and attempt.http_status == 404
            for attempt in source_attempts
        )
        root_state = (
            RootReplayState.SOURCE_EXHAUSTED_PENDING_ALTERNATES
            if all_not_found
            else RootReplayState.SOURCE_RETRY_REQUIRED
        )
        reason_code = (
            "source_exhausted_pending_alternates.uspto_ppubs_all_buckets_not_found"
            if all_not_found
            else "source_retry_required.uspto_ppubs_fetch_incomplete"
        )
        return RootReplayResult(
            cohort_sha256=cohort_sha256_value,
            root_id=member.root_id,
            result_attempt=result_attempt,
            publication_id=chosen_publication.publication_id,
            root_state=root_state,
            reason_code=reason_code,
            source_attempts=source_attempts,
            items=(),
        )

    raw_document = _checked_evidence(
        retained_attempt.raw_document_path,
        expected_sha256=retained_attempt.raw_document_sha256,
        evidence_type=(
            "uspto_ppubs_primary_html"
            if retained_attempt.parser_input_document_path
            else "uspto_ppubs_parser_input_html"
        ),
    )
    items = tuple(
        _item_from_conversion_attempt(
            attempt,
            publication_id=chosen_publication.publication_id,
            raw_document=raw_document,
        )
        for attempt in conversion_attempts
    )
    root_state, reason_code = _root_state(items)
    return RootReplayResult(
        cohort_sha256=cohort_sha256_value,
        root_id=member.root_id,
        result_attempt=result_attempt,
        publication_id=chosen_publication.publication_id,
        root_state=root_state,
        reason_code=reason_code,
        source_attempts=source_attempts,
        raw_document=raw_document,
        items=items,
    )


def _item_from_conversion_attempt(
    attempt: ConversionAttempt,
    *,
    publication_id: str,
    raw_document: EvidenceRef,
) -> ReplayItemResult:
    item_suffix = (
        f"e{attempt.embodiment_number}"
        if attempt.embodiment_number is not None
        else "document"
    )
    item_id = f"{publication_id}:{item_suffix}"
    base = {
        "item_id": item_id,
        "embodiment_number": attempt.embodiment_number,
        "embodiment_label": attempt.embodiment,
        "detail": attempt.reason,
        "prescription_fingerprint": attempt.prescription_fingerprint or None,
        "conversion_attempt_id": attempt.attempt_id or None,
        "conversion_request_sha256": attempt.request_sha256 or None,
        "coverage": attempt.coverage,
    }
    receipt = (
        _checked_evidence(
            attempt.receipt_path,
            evidence_type="patent_conversion_receipt",
        )
        if attempt.receipt_path
        else None
    )
    recovery_evidence: tuple[EvidenceRef, ...] = ()
    recovery_fields = (
        attempt.parser_input_document_path,
        attempt.parser_input_document_sha256,
        attempt.parser_input_publication_id,
        attempt.parser_input_source_bucket,
        attempt.fulltext_recovery_manifest_path,
        attempt.fulltext_recovery_manifest_sha256,
    )
    if any(recovery_fields):
        if not all(recovery_fields):
            raise PatentReplayError(f"incomplete fulltext recovery evidence: {item_id}")
        parser_input = _checked_evidence(
            attempt.parser_input_document_path,
            expected_sha256=attempt.parser_input_document_sha256,
            evidence_type="uspto_ppubs_recovered_parser_input_html",
        )
        recovery_manifest = _checked_evidence(
            attempt.fulltext_recovery_manifest_path,
            expected_sha256=attempt.fulltext_recovery_manifest_sha256,
            evidence_type="patent_fulltext_recovery_manifest",
        )
        recovery_evidence = (parser_input, recovery_manifest)
    if attempt.status == "success":
        if receipt is None or not attempt.zmx_path:
            raise PatentReplayError(f"success lacks receipt/ZMX evidence: {item_id}")
        zmx = _checked_evidence(attempt.zmx_path, evidence_type="staging_zmx")
        return ReplayItemResult(
            **base,
            state=ReplayItemState.CONVERTED_PENDING_INTAKE,
            reason_code="converted_pending_intake.process_isolated_zmx_ready",
            evidence=(raw_document, *recovery_evidence, receipt, zmx),
        )
    terminal_by_status = {
        "quality_rejected": TerminalStatus.QUALITY_REJECTED,
        "trace_failed": TerminalStatus.TRACE_FAILED,
        "trace_timeout": TerminalStatus.TRACE_TIMEOUT,
    }
    terminal_status = terminal_by_status.get(attempt.status)
    if terminal_status is not None and receipt is not None:
        return ReplayItemResult(
            **base,
            state=ReplayItemState.TERMINAL,
            reason_code="terminal.process_receipt_classified",
            terminal_status=terminal_status,
            evidence=(raw_document, *recovery_evidence, receipt),
        )
    source_terminal_by_status = {
        "confirmed_no_prescription": TerminalStatus.CONFIRMED_NO_PRESCRIPTION,
        "metadata_unpublished": TerminalStatus.METADATA_UNPUBLISHED,
    }
    source_terminal_status = source_terminal_by_status.get(attempt.status)
    if source_terminal_status is not None:
        if not attempt.reason_code.startswith(f"{attempt.status}."):
            raise PatentReplayError(
                f"source terminal status lacks a namespaced reason code: {item_id}"
            )
        return ReplayItemResult(
            **base,
            state=ReplayItemState.TERMINAL,
            reason_code=f"terminal.{attempt.reason_code}",
            terminal_status=source_terminal_status,
            evidence=(raw_document, *recovery_evidence),
        )
    if attempt.status in {"trace_failed", "trace_timeout"}:
        return ReplayItemResult(
            **base,
            state=ReplayItemState.CONVERSION_RETRY_REQUIRED,
            reason_code="conversion_retry_required.missing_process_receipt",
            evidence=(raw_document, *recovery_evidence),
        )
    if attempt.status == "conversion_retry_required":
        return ReplayItemResult(
            **base,
            state=ReplayItemState.CONVERSION_RETRY_REQUIRED,
            reason_code=(
                attempt.reason_code
                or "conversion_retry_required.patent_budget_exhausted"
            ),
            evidence=(raw_document, *recovery_evidence),
        )
    if attempt.status == "failed":
        return ReplayItemResult(
            **base,
            state=ReplayItemState.PARSER_REVIEW_REQUIRED,
            reason_code="parser_review_required.deterministic_parser_rejected",
            evidence=(raw_document, *recovery_evidence),
        )
    raise PatentReplayError(f"unmapped replay conversion status {attempt.status!r}: {item_id}")


def _root_state(
    items: tuple[ReplayItemResult, ...],
) -> tuple[RootReplayState, str]:
    if not items:
        return (
            RootReplayState.PARSER_REVIEW_REQUIRED,
            "parser_review_required.no_disclosed_embodiment_result",
        )
    states = {item.state for item in items}
    if states == {ReplayItemState.CONVERTED_PENDING_INTAKE}:
        return (
            RootReplayState.CONVERTED_PENDING_INTAKE,
            "converted_pending_intake.all_disclosed_items_converted",
        )
    if states == {ReplayItemState.TERMINAL}:
        return RootReplayState.TERMINAL, "terminal.all_disclosed_items_terminal"
    if states == {ReplayItemState.PARSER_REVIEW_REQUIRED}:
        return (
            RootReplayState.PARSER_REVIEW_REQUIRED,
            "parser_review_required.all_disclosed_items_rejected",
        )
    if states == {ReplayItemState.CONVERSION_RETRY_REQUIRED}:
        return (
            RootReplayState.CONVERSION_RETRY_REQUIRED,
            "conversion_retry_required.all_disclosed_items_retryable",
        )
    return RootReplayState.MIXED_NONTERMINAL, "mixed_nonterminal.multiple_item_states"


def _source_attempts(attempts: list[ConversionAttempt]) -> tuple[SourceFetchAttempt, ...]:
    for attempt in attempts:
        if attempt.source_attempts:
            return attempt.source_attempts
    return ()


def _dedupe_source_attempts(
    attempts: list[SourceFetchAttempt],
) -> tuple[SourceFetchAttempt, ...]:
    seen: set[tuple[object, ...]] = set()
    result: list[SourceFetchAttempt] = []
    for attempt in attempts:
        key = (
            attempt.publication_id,
            attempt.source_bucket,
            attempt.state,
            attempt.http_status,
            attempt.exception_type,
        )
        if key not in seen:
            seen.add(key)
            result.append(attempt)
    return tuple(result)


def _checked_evidence(
    path_text: str,
    *,
    evidence_type: str,
    expected_sha256: str | None = None,
) -> EvidenceRef:
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise PatentReplayError(f"evidence file is missing: {path}")
    digest = sha256_bytes(path.read_bytes())
    if expected_sha256 is not None and digest != expected_sha256:
        raise PatentReplayError(f"evidence hash mismatch: {path}")
    with contextlib.suppress(ValueError):
        path_text = path.resolve().relative_to(ROOT).as_posix()
    if Path(path_text).is_absolute():
        path_text = path.resolve().as_posix()
    return EvidenceRef(evidence_type=evidence_type, path=path_text, sha256=digest)


def _refresh_summary_artifacts(
    cohort: ReplayCohortManifest,
    *,
    results_dir: Path,
    summary_path: Path,
    report_path: Path,
    validate_evidence: bool = False,
) -> None:
    summary = summarize_replay_results(
        cohort,
        results_dir=results_dir,
        evidence_root=ROOT if validate_evidence else None,
    )
    _atomic_write(summary_path, canonical_json_bytes(summary))
    _atomic_write(report_path, replay_report_markdown(cohort, summary).encode("utf-8"))


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_bytes(content)
    temp.replace(path)


def _load_only_roots(path: Path | None) -> frozenset[str] | None:
    if path is None:
        return None
    return frozenset(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _add_common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cohort", type=Path, default=DEFAULT_COHORT_PATH)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and replay uncovered local patent roots.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    freeze_parser = subparsers.add_parser("freeze")
    _add_common_paths(freeze_parser)
    freeze_parser.add_argument(
        "--saturation-snapshot",
        type=Path,
        default=DEFAULT_SATURATION_SNAPSHOT,
    )
    run_parser = subparsers.add_parser("run")
    _add_common_paths(run_parser)
    run_parser.add_argument("--raw-document-dir", type=Path, default=DEFAULT_RAW_DOCUMENT_DIR)
    run_parser.add_argument("--attempts-dir", type=Path, default=DEFAULT_REPLAY_ATTEMPTS_DIR)
    run_parser.add_argument("--staging-dir", type=Path, default=DEFAULT_STAGING_DIR)
    run_parser.add_argument("--limit", type=int, default=25, help="0 processes every missing root")
    run_parser.add_argument("--delay-seconds", type=float, default=0.25)
    run_parser.add_argument(
        "--conversion-timeout-seconds",
        type=float,
        default=DEFAULT_CONVERSION_TIMEOUT_SECONDS,
    )
    run_parser.add_argument(
        "--patent-budget-seconds",
        type=float,
        default=DEFAULT_PATENT_BUDGET_SECONDS,
    )
    run_parser.add_argument("--only-roots", type=Path)
    run_parser.add_argument("--retry-nonterminal", action="store_true")
    run_parser.add_argument(
        "--retry-root-state",
        action="append",
        choices=tuple(state.value for state in RootReplayState),
        default=[],
    )
    run_parser.add_argument(
        "--retry-parser-signature",
        action="append",
        default=[],
        help="append-only retry of roots whose latest result contains this parser signature",
    )
    audit_parser = subparsers.add_parser("audit")
    _add_common_paths(audit_parser)
    report_parser = subparsers.add_parser("report")
    _add_common_paths(report_parser)
    args = parser.parse_args()

    if args.command == "freeze":
        cohort = freeze_cohort(
            cohort_path=args.cohort,
            saturation_snapshot_path=args.saturation_snapshot,
            results_dir=args.results_dir,
            summary_path=args.summary,
            report_path=args.report,
        )
        print(f"frozen_roots={len(cohort.members)} cohort_sha256={cohort_sha256(cohort)}")
        return 0

    cohort = load_replay_cohort(args.cohort)
    verify_replay_cohort_inputs(cohort, repo_root=ROOT)
    if args.command == "run":
        processed = asyncio.run(
            run_replay(
                cohort,
                results_dir=args.results_dir,
                summary_path=args.summary,
                report_path=args.report,
                raw_document_dir=args.raw_document_dir,
                attempts_dir=args.attempts_dir,
                staging_dir=args.staging_dir,
                limit=args.limit,
                delay_seconds=args.delay_seconds,
                conversion_timeout_seconds=args.conversion_timeout_seconds,
                patent_budget_seconds=args.patent_budget_seconds,
                only_roots=_load_only_roots(args.only_roots),
                retry_nonterminal=args.retry_nonterminal,
                retry_root_states=frozenset(
                    RootReplayState(value) for value in args.retry_root_state
                )
                or None,
                retry_parser_signatures=frozenset(args.retry_parser_signature) or None,
            )
        )
        summary = summarize_replay_results(cohort, results_dir=args.results_dir)
        print(
            f"processed={processed} roots_with_results={summary.roots_with_results} "
            f"missing={len(summary.missing_root_ids)}"
        )
        return 0


    _refresh_summary_artifacts(
        cohort,
        results_dir=args.results_dir,
        summary_path=args.summary,
        report_path=args.report,
        validate_evidence=True,
    )
    summary = summarize_replay_results(
        cohort,
        results_dir=args.results_dir,
        evidence_root=ROOT,
    )
    if args.command == "report":
        print(replay_report_markdown(cohort, summary), end="")
        return 0
    print(
        f"cohort_replay_complete={str(summary.cohort_replay_complete).lower()} "
        f"roots_with_results={summary.roots_with_results}/{summary.cohort_roots} "
        f"corrupt={len(summary.corrupt_result_paths)}"
    )
    return 0 if summary.cohort_replay_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
