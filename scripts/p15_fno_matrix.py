"""Phase 15 全矩阵：FNO 阶梯引擎 × ≥8 seed（ray-aware 重试开启）.

试点（.planning/loop/p15-stageb-evidence/ladder-pilot-2026-07-11/）验证四条件
判据后，orchestrator 授权的全矩阵 run。矩阵设计依据：

- **放松臂优先**（native 对照 §8：放松可"免费"达标甚至清掉固有病灶）：
  target = 各 seed scenario band 的 F# 上界（SCENARIO_BOUNDS 实域）。
- **收紧臂**只选 native 对照干净/轻伤的 4 颗（orchestrator 指定）：
  US20170003482A1 / US8908290B1 / US-11940597-B2-e6 / US20210165194A1。
  其中 US20170003482A1 收紧 target=2.0 刻意与试点同格——试点该格因
  autovig 与 ray 维脱钩失败（chief-ray-missing 未获渐晕清理），本矩阵
  ray-retry 开启后同格重跑 = 对 ray-aware 重试修复效果的直接真机验证。
- **95° 超广角负对照**：US20180143405A1 仅放松臂入列，rung 级 timeout 180s
  （orchestrator 预算条款）；收紧臂不入（native 对照即 timeout，烧不出新知）。

用法：
  清单预览（不跑 CODE V）： uv run python scripts/p15_fno_matrix.py --dry-run
  真机跑（窗口移交后）：     uv run python scripts/p15_fno_matrix.py
  分批：                     uv run python scripts/p15_fno_matrix.py --start 0 --limit 5

无 CODE V 自动 skip。每条 ladder 产出 per-seed 子目录（per-rung seq/tsv/lis +
ladder-result.json），最后写 matrix-results.tsv + matrix-summary.md（只出数据
与分类，不下良品判定——[EXPERT] 红线）。

已知环境注意（P13 车道 2026-07-11 真机钉死，知悉留档）：CRLF 行尾会破坏
ZEMAXOS_TO_CV 的 WAVM 解析；本矩阵不启用 emit_optimized_zmx（不产 ZMX 回读
链），不受影响。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError  # noqa: E402
from app.core.engines.codev_optimize import (  # noqa: E402
    RAY_RETRY_VIG_LADDER,
    run_codev_target_fno_ladder,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR  # noqa: E402

_INDEX_JSON = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"
_EVIDENCE_DEFAULT = Path(".planning/loop/p15-stageb-evidence/fno-matrix-2026-07-11")
_DEFAULT_TIMEOUT = 120.0


@dataclass(frozen=True)
class LadderJob:
    case_id: str
    direction: str  # "loosen" | "tighten"
    fnum_target: float
    timeout_seconds: float
    rationale: str


# 矩阵清单（12 seed / 13 ladders）。target 取自 SCENARIO_BOUNDS 实域（放松=
# band 上界；收紧=band 内一档），native F#/EFL 运行时从 index.json 读取（不
# 写死，防漂移）；rung0 会再用 CODE V 实测 native（引擎契约，不信标称）。
MATRIX: tuple[LadderJob, ...] = (
    # ---- 放松臂（优先） ----
    LadderJob("US20210165194A1", "loosen", 2.4, _DEFAULT_TIMEOUT,
              "native TIR(3,2) 但探针 loosen 2.4 clean——验证'放松清病灶'模式在阶梯全链成立"),
    LadderJob("US20170003482A1", "loosen", 2.4, _DEFAULT_TIMEOUT,
              "native ok；小幅放松（+3%），预期快速全绿"),
    LadderJob("US8908290B1", "loosen", 2.4, _DEFAULT_TIMEOUT,
              "native chief-ray-missing(6)，探针 loosen clean——放松清病灶第二例"),
    LadderJob("US-11940597-B2-e6", "loosen", 4.0, _DEFAULT_TIMEOUT,
              "native 微伤 TIR(1)，探针 loosen 4.0 clean；telephoto band 上界"),
    LadderJob("US-12443014-B2-e1", "loosen", 4.0, _DEFAULT_TIMEOUT,
              "native 重伤 TIR(45,11)——ray-retry 对重伤 seed 放松方向的效果测试"),
    LadderJob("US-12372756-B2-e8", "loosen", 4.0, _DEFAULT_TIMEOUT,
              "native 重伤 TIR(44,5)（MISS 5 固定份额）——重伤第二例"),
    LadderJob("US10281683B2", "loosen", 3.0, _DEFAULT_TIMEOUT,
              "旗舰固有 TIR 案例（F/1.68 宽快），wide band 上界——retry 能否清宽角固有 TIR"),
    LadderJob("US20140111876A1", "loosen", 3.0, _DEFAULT_TIMEOUT,
              "native TIR(7)，探针 loosen 仍 TIR——放松不自动清的案例给 retry"),
    LadderJob("US10330891B2", "loosen", 2.4, _DEFAULT_TIMEOUT,
              "100° 已验证池最宽视场，native TIR(7)"),
    # ---- 收紧臂（orchestrator 指定 4 颗 native 干净/轻伤） ----
    LadderJob("US20170003482A1", "tighten", 2.0, _DEFAULT_TIMEOUT,
              "★与试点同格：试点 rung3 chief-ray-missing 未获渐晕清理而失败，"
              "ray-retry 开启后同格重跑=修复效果直接验证★"),
    LadderJob("US8908290B1", "tighten", 1.8, _DEFAULT_TIMEOUT,
              "native 轻伤 MISS(6)，收紧一档到 ultrawide band 下界"),
    LadderJob("US20210165194A1", "tighten", 1.8, _DEFAULT_TIMEOUT,
              "native 轻伤 TIR(3,2)，收紧一档"),
    LadderJob("US-11940597-B2-e6", "tighten", 2.0, _DEFAULT_TIMEOUT,
              "native 微伤 TIR(1) 但探针收紧 REFL 33-45（放大 45 倍）——retry 最硬考验"),
    # ---- 95° 超广角负对照（rung 级 timeout 180s，orchestrator 预算条款） ----
    LadderJob("US20180143405A1", "loosen", 2.4, 180.0,
              "95° 负对照：native 对照即 timeout（TIR flood），预期 blocked/大量 error rung"
              "——真实负对照，验证吞并续爬真机行为"),
)


def _load_index() -> dict[str, dict[str, object]]:
    with _INDEX_JSON.open(encoding="utf-8") as handle:
        return {row["case_id"]: row for row in json.load(handle)}


def _summarize(results: list[tuple[LadderJob, dict[str, object] | None, str | None, float]],
               evidence: Path) -> None:
    tsv_lines = ["\t".join([
        "case_id", "direction", "fnum_target", "native_fnum_measured", "target_achieved",
        "last_measured_rung_index", "blocked", "rungs_total", "rungs_ray_retry_triggered",
        "rungs_ray_retry_accepted", "duration_s", "error",
    ])]
    md = [
        "# P15 FNO 阶梯全矩阵 — 汇总（数据与分类，不下良品判定=[EXPERT] 红线）",
        "",
        "| seed | dir | target F# | native 实测 | target_achieved | 爬到 | blocked | "
        "retry 触发/采纳 | 耗时(s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    achieved = 0
    for job, result, error, duration in results:
        if result is None:
            tsv_lines.append("\t".join(str(x) for x in [
                job.case_id, job.direction, job.fnum_target, "", "", "", "", "", "", "",
                f"{duration:.1f}", error or "",
            ]))
            md.append(f"| {job.case_id} | {job.direction} | {job.fnum_target} | — | — | — | — "
                      f"| — | {duration:.0f} | ")
            continue
        rungs = result["rungs"]
        triggered = sum(1 for r in rungs if isinstance(r.get("ray_retry"), dict))
        accepted = sum(
            1 for r in rungs
            if isinstance(r.get("ray_retry"), dict)
            and r["ray_retry"].get("accepted_edge") is not None
        )
        achieved += 1 if result["target_achieved"] else 0
        tsv_lines.append("\t".join(str(x) for x in [
            job.case_id, job.direction, job.fnum_target,
            result["native_fnum_measured"], result["target_achieved"],
            result["last_measured_rung_index"], result["blocked"],
            len(rungs), triggered, accepted, f"{duration:.1f}", "",
        ]))
        md.append(
            f"| {job.case_id} | {job.direction} | {job.fnum_target} | "
            f"{result['native_fnum_measured']} | {result['target_achieved']} | "
            f"rung{result['last_measured_rung_index']} | {result['blocked']} | "
            f"{triggered}/{accepted} | {duration:.0f} |"
        )
    ok_jobs = [r for _j, r, _e, _d in results if r is not None]
    md += [
        "",
        f"- target_achieved: {achieved}/{len(results)}（分母含 error ladder）",
        f"- ladder 完整产出: {len(ok_jobs)}/{len(results)}",
        "- per-seed 明细：各子目录 ladder-result.json（per-rung 双维记录 + ray_retry 轨迹）"
        " + per-rung seq/tsv/lis 全文。",
        "- 口径：measured_fnum=EFL_real/EPD_real 活算；RMS/WFE 若在裁瞳（effective_edge_used>0）"
        "上测=偏乐观，须连列读；ray-retry 采纳格详见各 rung ray_retry.quality_note。",
    ]
    (evidence / "matrix-results.tsv").write_text("\n".join(tsv_lines) + "\n", encoding="utf-8")
    (evidence / "matrix-summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[matrix] summary -> {evidence / 'matrix-summary.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="打印矩阵清单，不跑 CODE V")
    parser.add_argument("--evidence-dir", type=Path, default=_EVIDENCE_DEFAULT)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--rung-count", type=int, default=3)
    args = parser.parse_args()

    index = _load_index()
    jobs = list(MATRIX)[args.start:]
    if args.limit is not None:
        jobs = jobs[: args.limit]

    print(f"[matrix] {len(jobs)} ladders (of {len(MATRIX)}), rung_count={args.rung_count}, "
          f"ray_retry={RAY_RETRY_VIG_LADDER}")
    for i, job in enumerate(jobs, 1):
        meta = index[job.case_id]
        print(f"[matrix] {i:2d}. {job.case_id:22s} {job.direction:7s} "
              f"native F/{meta['fnum']} -> F/{job.fnum_target} "
              f"(FOV {meta['fov_deg']}, timeout {job.timeout_seconds:.0f}s)")
        print(f"[matrix]      {job.rationale}")
    if args.dry_run:
        return 0

    executable = Path(DEFAULT_CODEV_EXECUTABLE.__fspath__())
    if not executable.is_file():
        print(f"[skip] CODE V not found at {executable}")
        return 0

    evidence = args.evidence_dir
    evidence.mkdir(parents=True, exist_ok=True)
    results: list[tuple[LadderJob, dict[str, object] | None, str | None, float]] = []
    for i, job in enumerate(jobs, 1):
        meta = index[job.case_id]
        work_dir = evidence / f"{job.case_id}_{job.direction}"
        print(f"[matrix {i}/{len(jobs)}] {job.case_id} {job.direction} -> F/{job.fnum_target}",
              flush=True)
        started = time.monotonic()
        try:
            result = run_codev_target_fno_ladder(
                source_zmx=ZMX_AMMO_DIR / str(meta["source_zmx"]),
                work_dir=work_dir,
                target_efl_mm=float(meta["efl_mm"]),  # EFL 锁 native（隔离 F# 维）
                fnum_target=job.fnum_target,
                rung_count=args.rung_count,
                ray_retry_vig_ladder=RAY_RETRY_VIG_LADDER,
                timeout_seconds=job.timeout_seconds,
                executable=executable,
            )
        except CodeVBatchError as exc:
            duration = time.monotonic() - started
            print(f"[matrix {i}/{len(jobs)}]   -> LADDER ERROR {exc.kind}: {exc.message} "
                  f"({duration:.0f}s)", flush=True)
            results.append((job, None, f"{exc.kind}: {exc.message}", duration))
            continue
        duration = time.monotonic() - started
        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "ladder-result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"[matrix {i}/{len(jobs)}]   -> target_achieved={result['target_achieved']} "
              f"last_rung={result['last_measured_rung_index']} blocked={result['blocked']} "
              f"({duration:.0f}s)", flush=True)
        results.append((job, result, None, duration))
    _summarize(results, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
