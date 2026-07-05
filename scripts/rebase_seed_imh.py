"""Rebase patent seed image heights from CODE V database readouts."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE
from app.core.engines.codev_readout import CodeVReadoutResult, run_codev_readout

INDEX_PATH = REPO_ROOT / "app" / "data" / "optical_cases" / "index.json"
ZMX_DIR = REPO_ROOT / "data" / "zmx"
REPORT_PATH = REPO_ROOT / ".planning" / "loop" / "seed-imh-rebase-report.md"


@dataclass(frozen=True)
class SeedImhRebaseRow:
    case_id: str
    source_zmx: str
    old_image_height_mm: float
    measured_image_height_mm: float
    delta_mm: float
    duration_seconds: float | None


ReadoutRunner = Callable[..., CodeVReadoutResult]


def rebase_seed_imh(
    *,
    index_path: Path | str = INDEX_PATH,
    zmx_dir: Path | str = ZMX_DIR,
    report_path: Path | str = REPORT_PATH,
    work_root: Path | str | None = None,
    executable: Path | str | os.PathLike[str] = DEFAULT_CODEV_EXECUTABLE,
    timeout_seconds: float = 90.0,
    readout_runner: ReadoutRunner = run_codev_readout,
    generated_at: datetime | None = None,
) -> list[SeedImhRebaseRow]:
    """Read US seed IMH values through CODE V, update index.json, and write a report."""

    index_path = Path(index_path)
    zmx_dir = Path(zmx_dir)
    report_path = Path(report_path)

    if work_root is None:
        with tempfile.TemporaryDirectory(prefix="seed-imh-rebase-") as tmp:
            return _rebase_seed_imh_in_work_root(
                index_path=index_path,
                zmx_dir=zmx_dir,
                report_path=report_path,
                work_root=Path(tmp),
                executable=executable,
                timeout_seconds=timeout_seconds,
                readout_runner=readout_runner,
                generated_at=generated_at,
            )

    return _rebase_seed_imh_in_work_root(
        index_path=index_path,
        zmx_dir=zmx_dir,
        report_path=report_path,
        work_root=Path(work_root),
        executable=executable,
        timeout_seconds=timeout_seconds,
        readout_runner=readout_runner,
        generated_at=generated_at,
    )


def _rebase_seed_imh_in_work_root(
    *,
    index_path: Path,
    zmx_dir: Path,
    report_path: Path,
    work_root: Path,
    executable: Path | str | os.PathLike[str],
    timeout_seconds: float,
    readout_runner: ReadoutRunner,
    generated_at: datetime | None,
) -> list[SeedImhRebaseRow]:
    records = _load_index(index_path)
    patent_entries = _patent_seed_entries(records, zmx_dir)
    work_root.mkdir(parents=True, exist_ok=True)

    rows: list[SeedImhRebaseRow] = []
    for entry, zmx_path in patent_entries:
        case_id = _required_text(entry, "case_id")
        old_image_height = _required_float(entry, "image_height_mm")
        seed_work_dir = work_root / zmx_path.stem
        seed_work_dir.mkdir(parents=True, exist_ok=True)

        result = readout_runner(
            source_zmx=zmx_path,
            work_dir=seed_work_dir,
            executable=executable,
            timeout_seconds=timeout_seconds,
        )
        measured_image_height = _positive_float(
            result.readout.image_height_y_mm,
            label=f"{zmx_path.name} CODE V image_height_y_mm",
        )
        entry["image_height_mm"] = round(measured_image_height, 6)
        rows.append(
            SeedImhRebaseRow(
                case_id=case_id,
                source_zmx=zmx_path.name,
                old_image_height_mm=old_image_height,
                measured_image_height_mm=measured_image_height,
                delta_mm=measured_image_height - old_image_height,
                duration_seconds=getattr(result.batch, "duration_seconds", None),
            )
        )

    _write_index(index_path, records)
    _write_report(
        report_path,
        rows,
        index_path=index_path,
        zmx_dir=zmx_dir,
        generated_at=generated_at or datetime.now(UTC),
    )
    return rows


def _load_index(index_path: Path) -> list[dict[str, object]]:
    records = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError(f"case index must be a list: {index_path}")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError(f"case index records must be JSON objects: {index_path}")
    return records


def _write_index(index_path: Path, records: Sequence[dict[str, object]]) -> None:
    index_path.write_text(
        json.dumps(list(records), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _patent_seed_entries(
    records: list[dict[str, object]],
    zmx_dir: Path,
) -> list[tuple[dict[str, object], Path]]:
    zmx_paths = sorted(zmx_dir.glob("US*.zmx"), key=lambda path: path.name)
    if not zmx_paths:
        raise ValueError(f"no patent seed ZMX files found under {zmx_dir}")

    by_source = {
        _required_text(record, "source_zmx"): record
        for record in records
        if isinstance(record.get("source_zmx"), str)
    }
    by_case_id = {
        _required_text(record, "case_id"): record
        for record in records
        if isinstance(record.get("case_id"), str)
    }
    entries: list[tuple[dict[str, object], Path]] = []
    missing: list[str] = []
    for zmx_path in zmx_paths:
        entry = by_source.get(zmx_path.name) or by_case_id.get(zmx_path.stem)
        if entry is None:
            missing.append(zmx_path.name)
            continue
        entries.append((entry, zmx_path))
    if missing:
        raise ValueError(f"patent seed ZMX files missing from index: {', '.join(missing)}")
    return entries


def _write_report(
    report_path: Path,
    rows: Sequence[SeedImhRebaseRow],
    *,
    index_path: Path,
    zmx_dir: Path,
    generated_at: datetime,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SEED-01a 真 IMH 重锚报告",
        "",
        f"- Generated: {generated_at.astimezone(UTC).isoformat(timespec='seconds')}",
        f"- Source ZMX glob: `{_repo_relative(zmx_dir)}/US*.zmx`",
        "- Readout path: `app.core.engines.codev_readout.run_codev_readout`",
        f"- Updated index: `{_repo_relative(index_path)}`",
        f"- Seed count: {len(rows)}",
        "",
        "| case_id | old image_height_mm | CODE V IMH mm | delta mm |",
        "|---|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row.case_id} | "
            f"{row.old_image_height_mm:.6f} | "
            f"{row.measured_image_height_mm:.6f} | "
            f"{row.delta_mm:+.6f} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _required_text(record: dict[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"case index record missing text field {key!r}")
    return value


def _required_float(record: dict[str, object], key: str) -> float:
    return _positive_float(record.get(key), label=f"case index field {key!r}")


def _positive_float(value: object, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric, got {value!r}") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{label} must be positive, got {number!r}")
    return number


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX_PATH)
    parser.add_argument("--zmx-dir", type=Path, default=ZMX_DIR)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--executable", type=Path, default=DEFAULT_CODEV_EXECUTABLE)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = rebase_seed_imh(
        index_path=args.index,
        zmx_dir=args.zmx_dir,
        report_path=args.report,
        work_root=args.work_dir,
        executable=args.executable,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"rebased {len(rows)} patent seed image heights")
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
