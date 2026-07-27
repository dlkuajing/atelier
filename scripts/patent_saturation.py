"""Build and audit the canonical patent-saturation snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.patent_saturation import (  # noqa: E402
    audit_saturation_snapshot,
    build_saturation_snapshot,
    canonical_json_bytes,
    load_saturation_snapshot,
    saturation_report_markdown,
    sha256_bytes,
)

DEFAULT_LEDGER = ROOT / "data" / "patent-ledger" / "snapshot.json"
DEFAULT_AUDIT = ROOT / "data" / "patent-ledger" / "audit.json"
DEFAULT_REPORT = ROOT / ".planning" / "loop" / "patent-saturation-baseline.md"


def _resolve(root: Path, value: Path) -> Path:
    return value if value.is_absolute() else root / value


def _build(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    snapshot = build_saturation_snapshot(
        repo_root=root,
        pool_dir=_resolve(root, args.pool_dir),
        case_index_path=_resolve(root, args.case_index),
        case_data_dir=_resolve(root, args.case_data_dir),
        zmx_dir=_resolve(root, args.zmx_dir),
        raw_document_dir=_resolve(root, args.raw_document_dir),
        staging_dirs=tuple(_resolve(root, path) for path in args.staging_dir),
        pool_glob=args.pool_glob,
    )
    snapshot_bytes = canonical_json_bytes(snapshot)
    audit = audit_saturation_snapshot(snapshot, snapshot_sha256=sha256_bytes(snapshot_bytes))
    audit_bytes = canonical_json_bytes(audit)
    report_bytes = saturation_report_markdown(snapshot, audit).encode("utf-8")

    ledger_path = _resolve(root, args.ledger)
    audit_path = _resolve(root, args.audit)
    report_path = _resolve(root, args.report)
    for path, payload in (
        (ledger_path, snapshot_bytes),
        (audit_path, audit_bytes),
        (report_path, report_bytes),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    print(
        json.dumps(
            {
                "audit": str(audit_path),
                "ledger": str(ledger_path),
                "report": str(report_path),
                "saturation_complete": audit.saturation_complete,
                "snapshot_sha256": audit.snapshot_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _audit(args: argparse.Namespace) -> int:
    root = args.repo_root.resolve()
    ledger_path = _resolve(root, args.ledger)
    ledger_bytes = ledger_path.read_bytes()
    snapshot = load_saturation_snapshot(ledger_path)
    audit = audit_saturation_snapshot(snapshot, snapshot_sha256=sha256_bytes(ledger_bytes))
    if args.full:
        print(canonical_json_bytes(audit).decode("utf-8"), end="")
    else:
        print(
            json.dumps(
                {
                    "errors": list(audit.errors),
                    "legacy_unspecified_embodiments": len(
                        audit.legacy_unspecified_embodiment_ids
                    ),
                    "roots_without_retained_fulltext": len(
                        audit.roots_without_retained_fulltext
                    ),
                    "saturation_complete": audit.saturation_complete,
                    "snapshot_sha256": audit.snapshot_sha256,
                    "staging_patent_candidates": len(audit.staging_patent_candidates),
                    "terminal_status_counts": {
                        status.value: count
                        for status, count in audit.terminal_status_counts.items()
                    },
                    "unresolved_embodiments": len(audit.unresolved_embodiment_ids),
                    "unresolved_family_roots": len(audit.unresolved_family_root_ids),
                    "unresolved_families": len(audit.unresolved_family_ids),
                    "unresolved_roots": len(audit.unresolved_root_ids),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return 0 if audit.saturation_complete else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="rebuild deterministic ledger/audit/report")
    build.add_argument("--pool-dir", type=Path, default=Path("data/patents"))
    build.add_argument("--pool-glob", default="uspto-smartphone-batch*.jsonl")
    build.add_argument(
        "--case-index",
        type=Path,
        default=Path("app/data/optical_cases/index.json"),
    )
    build.add_argument(
        "--case-data-dir",
        type=Path,
        default=Path("app/data/optical_cases"),
    )
    build.add_argument("--zmx-dir", type=Path, default=Path("data/zmx"))
    build.add_argument(
        "--raw-document-dir",
        type=Path,
        default=Path("data/patent-lake/raw"),
    )
    build.add_argument(
        "--staging-dir",
        type=Path,
        action="append",
        default=[Path("data/zmx-staging"), Path("data/zmx_staging")],
    )
    build.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    build.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    build.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    build.set_defaults(handler=_build)

    audit = subparsers.add_parser("audit", help="fail unless every saturation gate is closed")
    audit.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    audit.add_argument(
        "--full",
        action="store_true",
        help="print the complete audit; default output is a compact summary",
    )
    audit.set_defaults(handler=_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
