"""Phase 15 Stage A/B: FNO 显式 F# target 失败模式采证 harness.

Context: `.planning/loop/opt3-final-handoff-2026-07-09.md` 限制#1 —— target-mode
AUT 已支持显式 CODE V ``FNO <target>`` 命令（``target_f_number``），但只在锁
seed 自身 F# 时验证过；把它设到一个真正不同于 native 的值上，在宽视场 seed 上
会打崩主光线追迹（chief ray missing / 全反射），因为 CODE V 导入后不会为新光
阑口径自动重解 ray-aiming。这是 Phase 15（"F# 达 target"）要拆的第一块骨头。

本脚本是失败模式**采证** harness（不是收敛引擎——那是
``app.core.engines.codev_optimize.run_codev_target_fno_ladder``，Stage 3 交
付，另跑真机验证）：对每颗 seed × 每个显式 F# target（收紧/放松两方向），跑
一个短 AUT 探针（``app.core.engines.fno_probe.run_fno_probe``），把 CODE V
``.lis`` 清单分类为 TIR / chief-ray-missing / aperture-conflict / ok / other /
timeout 五+一类。只出数据与分类，不下良品判定（AGENTS.md 北极星 [EXPERT] 红
线）。

用法：
  离线生成 manifest（不跑 CODE V，随时可跑，供 review 矩阵范围）：
    uv run python scripts/p15_fno_evidence.py --mode manifest
  真机窗跑采证矩阵（写 evidence 目录 + results.tsv + summary.md）：
    uv run python scripts/p15_fno_evidence.py --mode run
  真机窗分批跑（避免单次会话超时；按 manifest 行序切片）：
    uv run python scripts/p15_fno_evidence.py --mode run --start 0 --limit 20

无 CODE V 自动 skip（--mode run 时）。种子选择依据、F# 阶梯计算方式见下方
``SEED_SELECTION`` 与 ``compute_direction_targets`` 的文档字符串。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json  # noqa: E402

from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE  # noqa: E402
from app.core.engines.fno_probe import FnoProbeResult, run_fno_probe  # noqa: E402
from app.core.lens_system import Scenario  # noqa: E402
from app.core.parameter_guards import SCENARIO_BOUNDS, ScenarioBounds  # noqa: E402
from app.core.zmx_ingest import ZMX_AMMO_DIR  # noqa: E402

_INDEX_JSON = Path(__file__).resolve().parents[1] / "app" / "data" / "optical_cases" / "index.json"

# ---------------------------------------------------------------------------
# 种子选择（≥10 颗，见 brief）：8 颗 wide/ultrawide（FOV>=75°，TIR 高危）+
# 4 颗 telephoto（窄视场，低 TIR 风险对照）。全部来自已在 opt3 (P15 前身 spike)
# 真机验证过导入/AUT 可跑的 22 颗真实专利 seed 池（wide/ultrawide 8 颗），加
# 4 颗来自更大规模 USPTO 采集池（P17 已修 exact-source_zmx 路由，见 AGENTS.md）
# 的 telephoto seed（narrow FOV，作为"低 TIR 风险"方向对照，同时覆盖不同 F#
# native 值与不同片数 n_pieces）。逐颗 native F#/FOV/片数依据 index.json 动态
# 读取（不在此处写死，避免与 index.json 漂移）——见 SEED_SELECTION 里的
# rationale 字段说明"为什么选它"。
# ---------------------------------------------------------------------------

SEED_SELECTION: tuple[dict[str, str], ...] = (
    {
        "case_id": "US10281683B2",
        "category": "wide",
        "rationale": "旗舰 TIR 案例：native F/1.68 全反射根因诊断的原始种子（见 "
        ".planning/debug/codev-target-convergence.md「诊断 v2」）。",
    },
    {
        "case_id": "US20180143405A1",
        "category": "wide",
        "rationale": "最难 seed（95° FOV、S14 TIR flood 历史上曾致 autovig 全臂超时），"
        "边缘案例覆盖。",
    },
    {
        "case_id": "US10330891B2",
        "category": "wide",
        "rationale": "已知 22 颗真机验证池内视场最宽（100°）。",
    },
    {
        "case_id": "US20210165194A1",
        "category": "wide",
        "rationale": "95° 超广角，5 片，native F/2.0 中庸参照。",
    },
    {
        "case_id": "US20170003482A1",
        "category": "wide",
        "rationale": "opt3 全程最佳收敛控制种子（渐晕0即收敛），作为「好行为」对照。",
    },
    {
        "case_id": "US8908290B1",
        "category": "wide",
        "rationale": "91.2° 超广角，6 片，native F/2.0（与 US20210165194A1 同 F# "
        "不同 FOV/片数对照）。",
    },
    {
        "case_id": "US20140111876A1",
        "category": "wide",
        "rationale": "75.2° 恰在 wide FOV 阈值边界，opt3 asphere/glass DOF 矩阵已用过。",
    },
    {
        "case_id": "US10310222B2",
        "category": "wide",
        "rationale": "76.2° + native F/1.8（wide 组第二快 F#），覆盖快光圈宽视场组合。",
    },
    {
        "case_id": "US-12443014-B2-e1",
        "category": "tele",
        "rationale": "15.8° 窄视场长焦（EFL~17.3mm），native F/2.8 中庸，低 TIR 风险方向对照。",
    },
    {
        "case_id": "US-12372756-B2-e8",
        "category": "tele",
        "rationale": "15.9° 窄视场，native F/2.45，5 片。",
    },
    {
        "case_id": "US-20260160979-A1-e3",
        "category": "tele",
        "rationale": "19.0° 窄视场但 native F/1.68 极快（8 片）——罕见「窄视场+快光圈」组合，"
        "且 native F# 低于其 telephoto scenario 的 f_number_min(1.8)，收紧方向 "
        "band 内无候选（如实记录为空集，非 bug）。",
    },
    {
        "case_id": "US-11940597-B2-e6",
        "category": "tele",
        "rationale": "18.8° 窄视场，native F/3.57（本矩阵最慢 F#），4 片最简单结构对照。",
    },
)

# 目标 F# 阶（brief 定义）：收紧 = native -> {1.6,1.8,2.0} 取带内（< native 且
# 落在该 seed scenario 的 [f_number_min, f_number_max] 内）；放松 = native ->
# {+0.5, +1.0, scenario 上界} 取带内（> native 且 clip 到 f_number_max）。
_TIGHTEN_MENU: tuple[float, ...] = (1.6, 1.8, 2.0)
_LOOSEN_STEPS: tuple[float, ...] = (0.5, 1.0)


def compute_direction_targets(
    native_fnum: float, bounds: ScenarioBounds
) -> dict[str, list[float]]:
    """收紧/放松两方向的显式 F# target 候选（见模块顶部「目标 F# 阶」注释）。

    收紧候选可能为空（如 US-20260160979-A1-e3：native 1.68 已低于其 scenario
    的 f_number_min 1.8，{1.6,1.8,2.0} 里没有"既 < native 又落在 band 内"的
    点）——如实返回空列表，调用方不得为空集造点。
    """
    tighten = sorted(
        value
        for value in _TIGHTEN_MENU
        if value < native_fnum and bounds.f_number_min <= value <= bounds.f_number_max
    )
    loosen_candidates = {
        round(native_fnum + step, 6) for step in _LOOSEN_STEPS if native_fnum + step > native_fnum
    }
    if bounds.f_number_max > native_fnum:
        loosen_candidates.add(round(bounds.f_number_max, 6))
    loosen = sorted({round(min(value, bounds.f_number_max), 6) for value in loosen_candidates})
    return {"tighten": tighten, "loosen": loosen}


@dataclass(frozen=True)
class MatrixRow:
    case_id: str
    category: str
    rationale: str
    source_zmx: str
    scenario: str
    fov_deg: float
    n_pieces: int
    native_efl_mm: float
    native_fnum: float
    direction: str
    target_f_number: float


def _load_case_index() -> dict[str, dict[str, object]]:
    with _INDEX_JSON.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    return {row["case_id"]: row for row in rows}


def build_matrix() -> list[MatrixRow]:
    index = _load_case_index()
    matrix: list[MatrixRow] = []
    for seed in SEED_SELECTION:
        case_id = seed["case_id"]
        row = index.get(case_id)
        if row is None:
            raise KeyError(f"seed {case_id!r} not found in {_INDEX_JSON}")
        scenario = Scenario(str(row["scenario"]))
        bounds = SCENARIO_BOUNDS[scenario]
        native_fnum = float(row["fnum"])
        native_efl_mm = float(row["efl_mm"])
        targets = compute_direction_targets(native_fnum, bounds)
        for direction, values in targets.items():
            for target in values:
                matrix.append(
                    MatrixRow(
                        case_id=case_id,
                        category=seed["category"],
                        rationale=seed["rationale"],
                        source_zmx=str(row["source_zmx"]),
                        scenario=scenario.value,
                        fov_deg=float(row["fov_deg"]),
                        n_pieces=int(row["n_pieces"]),
                        native_efl_mm=native_efl_mm,
                        native_fnum=native_fnum,
                        direction=direction,
                        target_f_number=target,
                    )
                )
    return matrix


_MANIFEST_HEADER = (
    "case_id",
    "category",
    "scenario",
    "fov_deg",
    "n_pieces",
    "native_efl_mm",
    "native_fnum",
    "direction",
    "target_f_number",
    "source_zmx",
    "rationale",
)


def write_manifest_tsv(matrix: list[MatrixRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(_MANIFEST_HEADER)]
    for row in matrix:
        lines.append(
            "\t".join(
                [
                    row.case_id,
                    row.category,
                    row.scenario,
                    f"{row.fov_deg:.3f}",
                    str(row.n_pieces),
                    f"{row.native_efl_mm:.4f}",
                    f"{row.native_fnum:.3f}",
                    row.direction,
                    f"{row.target_f_number:.3f}",
                    row.source_zmx,
                    row.rationale.replace("\t", " "),
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Stage 2: 真机跑采证矩阵
# ---------------------------------------------------------------------------

_LIS_LINE_THRESHOLD = 500
_LIS_CONTEXT_LINES = 2
# 信号行正则必须覆盖分类器（fno_probe.classify_fno_listing）的**全部**证据形
# 态，否则 trimmed 归档无法复核 runtime 分类（对抗审查 MAJOR-4 实锤：初版漏
# 了 "Total reflection"/"ERROR -" 形态的 TIR 行，5 格 runtime=TIR 的已归档清
# 单按 trimmed 文本重判会降级为 ok/aperture-conflict——见 summary.md §6）。
_LIS_SIGNAL_RE = re.compile(
    r"RAY ERROR|Total reflection|ERROR -|WARNING -|AUTO Completion|CYCLE NUMBER"
)


def _trim_large_lis(lis_path: Path) -> None:
    """大 .lis 只留关键段+行号（brief 明确允许），分类本身已在运行时基于全文
    完成（见 fno_probe.run_fno_probe），本函数只影响落盘/入库的内容。<=500
    行的小文件原样保留。

    可复核性锚（MAJOR-4 修复）：header 记录全文 sha256 与原始行数——信号正
    则覆盖分类器全部证据形态后，trimmed 文本重跑分类器可复现 runtime 分类；
    sha256 供任何持有原始 CODE V 输出的一方核对归档对应关系。"""
    if not lis_path.is_file():
        return
    full_text = lis_path.read_text(encoding="utf-8", errors="replace")
    raw_lines = full_text.splitlines()
    if len(raw_lines) <= _LIS_LINE_THRESHOLD:
        return
    full_sha256 = hashlib.sha256(full_text.encode("utf-8", errors="replace")).hexdigest()
    keep: set[int] = set(range(min(40, len(raw_lines))))  # 头部：导入/配置回显
    for i, line in enumerate(raw_lines):
        if _LIS_SIGNAL_RE.search(line):
            keep.update(range(max(0, i - _LIS_CONTEXT_LINES), min(len(raw_lines), i + _LIS_CONTEXT_LINES + 1)))
    excerpt = [f"{i + 1:6d}| {raw_lines[i]}" for i in sorted(keep)]
    # header 措辞刻意用连字符（"Total-reflection"）避开分类器正则
    # （fno_probe._TIR_RE 的 `Total\s+reflection` 分支）——否则 header 自述的
    # 信号清单会被 classify_fno_listing 误计一次 REFL（真机 recheck 实锤：
    # runtime REFL=1 的格，含旧措辞 header 的 trimmed 归档重判 REFL=2）。
    header = [
        f"! trimmed excerpt: {len(raw_lines)} raw lines -> {len(excerpt)} kept "
        "(RAY-ERROR / Total-reflection / ERROR-dash / WARNING / AUTO-Completion / "
        f"CYCLE-NUMBER lines + {_LIS_CONTEXT_LINES}-line context, plus the first "
        "40 lines; original line numbers prefixed). Classification already ran "
        "on the full text at run time -- this trimming only affects what's "
        "persisted to disk.",
        f"! full-text sha256: {full_sha256}  (raw line count: {len(raw_lines)})",
        "",
    ]
    lis_path.write_text("\n".join(header + excerpt) + "\n", encoding="utf-8")


def run_stage2(
    matrix: list[MatrixRow],
    *,
    evidence_root: Path,
    executable: Path,
    timeout_seconds: float,
) -> list[tuple[MatrixRow, FnoProbeResult]]:
    results: list[tuple[MatrixRow, FnoProbeResult]] = []
    for index, row in enumerate(matrix, start=1):
        source_zmx = ZMX_AMMO_DIR / row.source_zmx
        work_dir = evidence_root / row.case_id
        print(
            f"[p15-fno {index}/{len(matrix)}] {row.case_id} dir={row.direction} "
            f"target_f#={row.target_f_number:.3f} (native={row.native_fnum:.3f}, "
            f"FOV={row.fov_deg:.1f}deg)",
            flush=True,
        )
        result = run_fno_probe(
            source_zmx=source_zmx,
            work_dir=work_dir,
            native_efl_mm=row.native_efl_mm,
            native_fnum=row.native_fnum,
            target_f_number=row.target_f_number,
            direction=row.direction,  # type: ignore[arg-type]
            executable=executable,
            timeout_seconds=timeout_seconds,
        )
        if result.lis_path is not None:
            _trim_large_lis(Path(result.lis_path))
        print(
            f"[p15-fno {index}/{len(matrix)}]   -> outcome={result.outcome} "
            f"conv={result.aut_converged} dev%={result.efl_target_deviation_pct} "
            f"({result.duration_seconds:.1f}s)",
            flush=True,
        )
        results.append((row, result))
    return results


_RESULTS_HEADER = (
    *_MANIFEST_HEADER,
    "outcome",
    "aut_converged",
    "efl_target_deviation_pct",
    "post_aut_fno",
    "refl_count",
    "miss_count",
    "aperture_conflict_matched",
    "error_kind",
    "error_detail",
    "preflight",
    "duration_seconds",
    "lis_path",
)


def write_results_tsv(results: list[tuple[MatrixRow, FnoProbeResult]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(_RESULTS_HEADER)]
    for row, result in results:
        classification = result.classification
        lines.append(
            "\t".join(
                str(value).replace("\t", " ").replace("\n", " ")
                for value in [
                    row.case_id,
                    row.category,
                    row.scenario,
                    f"{row.fov_deg:.3f}",
                    row.n_pieces,
                    f"{row.native_efl_mm:.4f}",
                    f"{row.native_fnum:.3f}",
                    row.direction,
                    f"{row.target_f_number:.3f}",
                    row.source_zmx,
                    row.rationale,
                    result.outcome,
                    result.aut_converged,
                    result.efl_target_deviation_pct,
                    result.post_aut_fno,
                    classification.refl_count if classification else "",
                    classification.miss_count if classification else "",
                    classification.aperture_conflict_matched if classification else "",
                    result.error_kind or "",
                    result.error_detail or "",
                    result.preflight or "",
                    f"{result.duration_seconds:.2f}" if result.duration_seconds else "",
                    result.lis_path or "",
                ]
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_report(results: list[tuple[MatrixRow, FnoProbeResult]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(results)
    by_outcome: dict[str, int] = {}
    by_direction_outcome: dict[tuple[str, str], int] = {}
    by_fov_bucket_outcome: dict[tuple[str, str], int] = {}
    tighten_ok_seeds: set[str] = set()
    tighten_seeds: set[str] = set()

    def fov_bucket(fov: float) -> str:
        if fov < 30:
            return "tele(<30deg)"
        if fov < 75:
            return "mid(30-75deg)"
        return "wide(>=75deg)"

    for row, result in results:
        by_outcome[result.outcome] = by_outcome.get(result.outcome, 0) + 1
        key = (row.direction, result.outcome)
        by_direction_outcome[key] = by_direction_outcome.get(key, 0) + 1
        fkey = (fov_bucket(row.fov_deg), result.outcome)
        by_fov_bucket_outcome[fkey] = by_fov_bucket_outcome.get(fkey, 0) + 1
        if row.direction == "tighten":
            tighten_seeds.add(row.case_id)
            if result.outcome == "ok":
                tighten_ok_seeds.add(row.case_id)

    lines = [
        "# Phase 15 Stage A/B — 显式 FNO 失败模式采证报告",
        "",
        "- **探针边界**：机器只出失败模式分类（TIR / chief-ray-missing / "
        "aperture-conflict / ok / other / timeout）与原始数字；**良品/合格判定"
        "全部留给资深**（AGENTS.md 北极星 [EXPERT] 红线）。",
        "- 探针短（1-2 cycle），EFL 锁 native，隔离出显式 FNO retarget 单一变量"
        "的效应；不是收敛引擎（Stage 3 的 `run_codev_target_fno_ladder` 是引"
        "擎，另跑真机验证）。",
        f"- 矩阵规模：{total} 格（{len(SEED_SELECTION)} seed × 收紧/放松方向）。",
        "",
        "## 分类分布总表",
        "",
        "| outcome | count | pct |",
        "|---|---|---|",
    ]
    for outcome, count in sorted(by_outcome.items(), key=lambda kv: -kv[1]):
        pct = count / total * 100 if total else 0.0
        lines.append(f"| {outcome} | {count} | {pct:.1f}% |")

    lines += ["", "## 按方向（收紧 vs 放松）", "", "| direction | outcome | count |", "|---|---|---|"]
    for (direction, outcome), count in sorted(by_direction_outcome.items()):
        lines.append(f"| {direction} | {outcome} | {count} |")

    lines += ["", "## 按 FOV 分档", "", "| fov_bucket | outcome | count |", "|---|---|---|"]
    for (bucket, outcome), count in sorted(by_fov_bucket_outcome.items()):
        lines.append(f"| {bucket} | {outcome} | {count} |")

    lines += [
        "",
        "## 哪些 seed 收紧方向直接就能（outcome=ok）",
        "",
        f"- 有收紧候选的 seed 数：{len(tighten_seeds)}",
        f"- 收紧方向至少一格 outcome=ok 的 seed 数：{len(tighten_ok_seeds)}",
        "- 逐 seed 明细见 results.tsv（direction=tighten 行的 outcome 列）。",
        "",
        "## 逐格明细",
        "",
        "| case_id | dir | native F# | target F# | FOV | outcome | conv | "
        "dev% | REFL | MISS | duration(s) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row, result in results:
        classification = result.classification
        duration_cell = f"{result.duration_seconds:.1f}" if result.duration_seconds else "0"
        lines.append(
            f"| {row.case_id} | {row.direction} | {row.native_fnum:.3f} | "
            f"{row.target_f_number:.3f} | {row.fov_deg:.1f} | {result.outcome} | "
            f"{result.aut_converged} | "
            f"{result.efl_target_deviation_pct if result.efl_target_deviation_pct is not None else ''} | "
            f"{classification.refl_count if classification else ''} | "
            f"{classification.miss_count if classification else ''} | "
            f"{duration_cell} |"
        )

    lines += [
        "",
        "## 待资深/主公判断（NEED）",
        "",
        "- 上述分布是否支撑 Phase 15 Stage 3 阶梯引擎（"
        "`run_codev_target_fno_ladder`）的下一步真机验证优先级排序（先攻哪类失败）。",
        "- `aperture-conflict` 正则是 pending-real-machine（见 "
        "`app/core/engines/fno_probe.py` 模块文档字符串）——若本矩阵里从未命中，"
        "或命中了不该命中的行，需要根据本报告的 `other` 类原文摘录回填修正。",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["manifest", "run"], default="manifest")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=Path(".planning/loop/p15-stageb-evidence"),
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    matrix = build_matrix()
    print(f"[p15-fno] matrix size: {len(matrix)} cells across {len(SEED_SELECTION)} seeds")

    evidence_dir = args.evidence_dir
    manifest_path = evidence_dir / "manifest.tsv"
    write_manifest_tsv(matrix, manifest_path)
    print(f"[p15-fno] manifest -> {manifest_path}")

    if args.mode == "manifest":
        return 0

    executable = Path(DEFAULT_CODEV_EXECUTABLE.__fspath__())
    if not executable.is_file():
        print(f"[skip] CODE V not found at {executable}")
        return 0

    sliced = matrix[args.start :]
    if args.limit is not None:
        sliced = sliced[: args.limit]
    print(f"[p15-fno] running {len(sliced)} cells (start={args.start}, limit={args.limit})")

    results = run_stage2(
        sliced,
        evidence_root=evidence_dir,
        executable=executable,
        timeout_seconds=args.timeout,
    )
    results_path = evidence_dir / "results.tsv"
    write_results_tsv(results, results_path)
    print(f"[p15-fno] results -> {results_path}")

    summary_path = evidence_dir / "summary.md"
    write_summary_report(results, summary_path)
    print(f"[p15-fno] summary -> {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
