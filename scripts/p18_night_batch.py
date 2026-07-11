"""P18-2: night batch queue CLI — target list -> per-job orchestration ->
the P18-1 archive ledger (`app.core.batch_archive.BatchArchive`). Thin
wrapper around `app.core.batch_runner.run_batch`.

Run:
    uv run python scripts/p18_night_batch.py --engine fake --sample-n 5
    uv run python scripts/p18_night_batch.py --engine fake --targets my_targets.json --max-jobs 3
    uv run python scripts/p18_night_batch.py --resume <batch_id> --engine real --max-wall-min 480

**禁跑 CODE V 铁律（P18 批量生产任务书 执行授权）**: `--engine real` runs
`orchestration.orchestrate()`'s default modes, which invokes real CODE V
(Mode3) whenever `DEFAULT_CODEV_EXECUTABLE` is present on this machine. Only
the loop orchestrator is meant to pass `--engine real`, during a scheduled
CODE V window — `--engine fake` (Mode1-only, structurally zero CODE V
dependency, see `app/core/batch_runner.py`'s module docstring) is what every
dev/test invocation on the demo machine (CODE V IS installed here) must use.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.batch_archive import BatchArchive  # noqa: E402
from app.core.batch_runner import DEFAULT_N, FakeEngine, RealEngine, run_batch  # noqa: E402

_DEFAULT_TARGETS_PATH = (
    Path(__file__).resolve().parents[1] / ".planning" / "loop" / "sweet-zone-topic-set.json"
)


def _load_targets_from_file(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"--targets 文件须为非空 JSON 列表，实际 {type(data).__name__}")
    return data


def _sample_default_targets(
    sample_n: int, *, seed: int | None
) -> tuple[list[dict[str, object]], str]:
    pool = _load_targets_from_file(_DEFAULT_TARGETS_PATH)
    n = min(sample_n, len(pool))
    sampled = random.Random(seed).sample(pool, k=n) if seed is not None else pool[:n]
    source = f"{_DEFAULT_TARGETS_PATH.name} sample N={n} seed={seed}"
    return sampled, source


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine",
        choices=["fake", "real"],
        required=True,
        help="fake=Mode1-only 检索批（零 CODE V 依赖）；real=完整编排（可能真跑 CODE V）",
    )
    parser.add_argument(
        "--targets", type=Path, default=None,
        help="显式 target 清单 JSON 文件（列表，每项含 TargetSpec 字段）；省略则从"
        " sweet-zone-topic-set.json 抽样",
    )
    parser.add_argument("--sample-n", type=int, default=50, dest="sample_n")
    parser.add_argument("--sample-seed", type=int, default=None, dest="sample_seed")
    parser.add_argument("--batch-id", type=str, default=None, dest="batch_id")
    parser.add_argument(
        "--resume", action="store_true",
        help="从磁盘账本续跑既有 batch（需配 --batch-id）；跳过已终态(succeeded/failed)的 job",
    )
    parser.add_argument("--max-jobs", type=int, default=None, dest="max_jobs")
    parser.add_argument("--max-wall-min", type=float, default=None, dest="max_wall_min")
    parser.add_argument("--job-timeout-sec", type=float, default=None, dest="job_timeout_sec")
    parser.add_argument("--n", type=int, default=DEFAULT_N, help=f"每 target 产出候选数（默认 {DEFAULT_N}）")
    parser.add_argument("--repeat-runs", type=int, default=1, dest="repeat_runs")
    parser.add_argument(
        "--archive-dir", type=Path, default=None, dest="archive_dir",
        help="覆盖 settings.batch_archive_dir（主要供测试/隔离用）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.resume and not args.batch_id:
        print("--resume 需要同时提供 --batch-id", file=sys.stderr)
        return 2

    archive = BatchArchive(root=args.archive_dir) if args.archive_dir else BatchArchive()
    engine = (
        FakeEngine(n=args.n)
        if args.engine == "fake"
        else RealEngine(n=args.n, repeat_runs=args.repeat_runs)
    )

    targets: list[dict[str, object]] | None = None
    target_source = ""
    if not args.resume:
        if args.targets is not None:
            targets = _load_targets_from_file(args.targets)
            target_source = str(args.targets)
        else:
            targets, target_source = _sample_default_targets(args.sample_n, seed=args.sample_seed)

    summary = run_batch(
        engine=engine,
        archive=archive,
        targets=targets,
        target_source=target_source,
        batch_id=args.batch_id,
        resume=args.resume,
        max_jobs=args.max_jobs,
        max_wall_min=args.max_wall_min,
        job_timeout_sec=args.job_timeout_sec,
        engine_name=args.engine,
    )

    succeeded = sum(1 for j in summary.jobs if j.status == "succeeded")
    failed = sum(1 for j in summary.jobs if j.status == "failed")
    failure_categories: dict[str, int] = {}
    for job in summary.jobs:
        if job.failure is not None:
            failure_categories[job.failure.category] = failure_categories.get(job.failure.category, 0) + 1

    print(
        f"batch {summary.batch.batch_id}: status={summary.batch.status} "
        f"{succeeded} succeeded, {failed} failed, "
        f"{len(summary.jobs)}/{summary.batch.target_count} attempted"
    )
    if failure_categories:
        print(f"failure categories: {failure_categories}")
    if summary.budget_exhausted:
        print(
            "[BUDGET] this invocation stopped early on a max-jobs/max-wall-min limit — "
            f"rerun with --resume --batch-id {summary.batch.batch_id} to continue",
            file=sys.stderr,
        )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
