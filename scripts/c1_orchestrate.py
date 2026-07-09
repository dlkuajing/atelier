"""C1 离线 batch 编排报告 — 需求集 -> CandidateSet -> scorecard 报告(MD+JSON)。

权威依据：
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`
§4（数据流）+ §13（交付形态：离线 batch → scorecard 报告，供资深离线筛）。

Run:
    uv run python scripts/c1_orchestrate.py --out <dir>
    uv run python scripts/c1_orchestrate.py --out <dir> --requirements reqs.json --n 4

内置 demo 需求（--requirements 省略时）是 2-3 组 SMARTPHONE_WIDE（手机主摄）
规格，落在 `parameter_guards.SCENARIO_BOUNDS[SMARTPHONE_WIDE]` 内——该边界是
`scripts/compute_bounds_stats.py` 从 31 颗真实手机主摄设计统计再derive 的
（见 `parameter_guards.py` 注释），不是凭空编数字。

每条需求产一份 Markdown（人读）+ 一份 JSON（`CandidateSet.model_dump` 全量，
机读/可回读）。**[EXPERT] 红线**：报告只出量化数据 + 留白表格，不下"合格/
良品"判定——那一列永远是资深填的。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.lens_system import Scenario  # noqa: E402
from app.core.orchestration.candidate import (  # noqa: E402
    CandidateSet,
    MetricValue,
    OpticalExtras,
    ScoredCandidate,
    TargetDeviation,
    TargetSpec,
)
from app.core.orchestration.orchestrator import DEFAULT_N, orchestrate  # noqa: E402

# ---------------------------------------------------------------------------
# Built-in demo requirement set — 2-3 组手机主摄 (SMARTPHONE_WIDE) 规格。
# ---------------------------------------------------------------------------

DEMO_REQUIREMENTS: list[dict[str, object]] = [
    {
        "label": "旗舰大底主摄",
        "scenario": Scenario.SMARTPHONE_WIDE.value,
        "efl_mm": 4.8,
        "fov_deg": 79.0,
        "fnum": 1.8,
        "image_height_mm": 4.4,
        "n_elements": 7,
        "priority": "performance",
    },
    {
        "label": "主流中端主摄",
        "scenario": Scenario.SMARTPHONE_WIDE.value,
        "efl_mm": 3.8,
        "fov_deg": 80.0,
        "fnum": 2.0,
        "image_height_mm": 3.6,
        "n_elements": 6,
        "priority": "balanced",
    },
    {
        "label": "入门轻薄主摄",
        "scenario": Scenario.SMARTPHONE_WIDE.value,
        "efl_mm": 2.8,
        "fov_deg": 78.0,
        "fnum": 2.4,
        "image_height_mm": 3.3,
        "n_elements": 5,
        "priority": "cost",
    },
]


def _load_requirements(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return DEMO_REQUIREMENTS
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(
            f"--requirements 文件须为非空 JSON 列表，实际 {type(data).__name__}"
        )
    return data


def _requirement_label(req: dict[str, object], index: int) -> str:
    label = req.get("label")
    return str(label) if label else f"requirement_{index}"


def _target_spec_from_requirement(req: dict[str, object]) -> TargetSpec:
    fields = {k: v for k, v in req.items() if k != "label"}
    return TargetSpec(**fields)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _fmt_metric(m: MetricValue, *, precision: int = 3) -> str:
    if m.status == "unavailable" or m.value is None:
        return "N/A"
    return f"{m.value:.{precision}f}"


def _fmt_optional(value: float | int | None) -> str:
    return "(unconstrained)" if value is None else str(value)


def _md_safe(value: str) -> str:
    """Collapse newlines and escape pipes so a free-form string (user-JSON
    requirement fields like `manufacturing_tier`/`priority`/`label`,
    generation notes, or a batch-summary note that may embed a multi-line
    generator exception message) can't break Markdown table/list structure."""
    return "; ".join(value.splitlines()).replace("|", "\\|")


def _fmt_deviation_row(dev: TargetDeviation) -> str:
    target_str = "unconstrained" if dev.target is None else f"{dev.target:.3f}"
    rel_str = "N/A" if dev.rel_violation is None else f"{dev.rel_violation:.1%}"
    converged_str = "是" if dev.converged_toward_target else "否"
    return (
        f"| {dev.field} | {dev.constraint_kind} | {target_str} | {dev.achieved:.3f} "
        f"| {dev.violation:.3f} | {rel_str} | {converged_str} |"
    )


def _render_requirement_echo(label: str, target: TargetSpec) -> list[str]:
    tier = _md_safe(target.manufacturing_tier) if target.manufacturing_tier else "(unspecified)"
    priority = _md_safe(target.priority) if target.priority else "(unspecified)"
    return [
        f"# C1 候选报告 — {_md_safe(label)}",
        "",
        "## 需求回显",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| scenario | {target.scenario.value} |",
        f"| efl_mm | {_fmt_optional(target.efl_mm)} |",
        f"| fov_deg | {_fmt_optional(target.fov_deg)} |",
        f"| fnum | {target.fnum} |",
        f"| image_height_mm | {_fmt_optional(target.image_height_mm)} |",
        f"| max_total_track_mm | {_fmt_optional(target.max_total_track_mm)} |",
        f"| n_elements | {_fmt_optional(target.n_elements)} |",
        f"| max_weight_g | {_fmt_optional(target.max_weight_g)} |",
        f"| manufacturing_tier | {tier} |",
        f"| priority | {priority} |",
        "",
    ]


def _render_banner(candidate_set: CandidateSet) -> list[str]:
    if candidate_set.honesty_banner is None:
        return []
    return [f"> **[诚实告警]** {candidate_set.honesty_banner}", ""]


def _render_summary(candidate_set: CandidateSet) -> list[str]:
    s = candidate_set.summary
    mode_str = (
        ", ".join(f"{mode.value}={count}" for mode, count in s.mode_counts.items())
        or "(none)"
    )
    ri_available = s.candidate_count - s.ri_missing_count
    ri_str = f"{ri_available}/{s.candidate_count}" if s.candidate_count else "0/0"
    lines = [
        "## 批次摘要",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 候选总数 | {s.candidate_count} |",
        f"| modes 分布 | {mode_str} |",
        f"| ranked | {s.ranked_count} |",
        f"| withheld | {s.withheld_count} |",
        f"| RI 可用 | {ri_str} |",
        "",
    ]
    if s.notes:
        lines.append("**备注：**")
        lines.extend(f"- {_md_safe(note)}" for note in s.notes)
        lines.append("")
    return lines


_IMAGE_QUALITY_ROWS: tuple[tuple[str, str], ...] = (
    ("MTF sag（代表频率，跨视场保守值）", "mtf_sag"),
    ("MTF tan（代表频率，跨视场保守值）", "mtf_tan"),
    ("衍射截止 (lp/mm)", "diffraction_cutoff_lp_per_mm"),
    ("RMS 点列半径 max (um)", "rms_spot_radius_max_um"),
    ("RMS 点列半径 mean (um)", "rms_spot_radius_mean_um"),
    ("min Strehl ratio", "min_strehl_ratio"),
    ("RMS 波前误差 (waves)", "rms_wavefront_error_waves"),
    ("场曲 tangential峰值Δ (mm)", "field_curvature_tangential_delta_mm"),
    ("场曲 sagittal峰值Δ (mm)", "field_curvature_sagittal_delta_mm"),
    ("最大畸变 (%)", "max_distortion_pct"),
    ("相对照度 RI (worst field)", "relative_illumination"),
)


_CODEV_POST_AUT_ROWS: tuple[tuple[str, str], ...] = (
    ("post_aut EFL_y (mm)", "post_aut.efl_y_mm"),
    ("post_aut RMS 点列径 (um)", "post_aut.max_rms_spot_diameter_um"),
    ("post_aut RMS 波前 (waves)", "post_aut.max_rms_wavefront_error_waves"),
    ("post_aut 畸变 (%)", "post_aut.max_distortion_pct"),
    ("post_aut F#", "post_aut.fno"),
    ("post_aut 半像高 (mm)", "post_aut.maximh_mm"),
    ("EFL target 偏差 (%)", "efl_target_deviation_pct"),
    ("aut_converged", "aut_converged"),
    ("渐晕 edge_used", "autovig.edge_used"),
    ("AUT err_f_ratio（末/初）", "err_f_ratio"),
    ("AUT 终止措辞", "aut_termination"),
)


def _fmt_codev_value(value: float | str | None) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4g}"
    return _md_safe(str(value))


def _render_codev_post_aut(extras: OpticalExtras) -> list[str]:
    """Mode3 专属 provenance 区（`OpticalExtras.codev_post_aut`）：CODE V
    真机快照数字，裁瞳口径，不参与本报告任何排序/打分——只供资深核对
    provenance。`None`（RetrievalGenerator 等未提供）时不渲染这一节。"""
    if extras.codev_post_aut is None:
        return []
    lines = [
        "**CODE V 真机快照（post_aut，裁瞳口径 · provenance only）**",
        "",
        "> 以下数字来自 CODE V `run_codev_target_standard` preferred 配置的批跑读数，"
        "**裁瞳（vignetted pupil）口径**，与下方 target 偏差/像质摘要的 Optiland "
        "满口径口径不可直接横比，仅供资深核对 provenance——不参与本报告任何排序/打分。",
        "",
        "| 项 | 值 |",
        "|---|---|",
    ]
    for label, key in _CODEV_POST_AUT_ROWS:
        lines.append(f"| {label} | {_fmt_codev_value(extras.codev_post_aut.get(key))} |")
    lines.append("")
    return lines


def _render_candidate(index: int, sc: ScoredCandidate) -> list[str]:
    row = sc.scorecard
    gen = sc.generated
    lines = [f"### 候选 {index}: `{row.candidate_id}`", ""]

    lines.append(f"- provenance: mode=`{row.mode.value}` source_case_id=`{gen.source_case_id or '(none)'}`")
    lines.append("- generation_notes:")
    lines.extend(f"  - {_md_safe(note)}" for note in gen.generation_notes)
    lines.append("")

    lines += _render_codev_post_aut(gen.optical_extras)

    lines.append("**Target 偏差（5 维）**")
    lines.append("")
    lines.append("| 维 | 约束类型 | target | achieved | violation | rel_violation | 已朝target收敛 |")
    lines.append("|---|---|---|---|---|---|---|")
    lines.extend(_fmt_deviation_row(dev) for dev in row.target_deviations)
    lines.append("")

    lines.append("**像质摘要**")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---|")
    for name, attr in _IMAGE_QUALITY_ROWS:
        metric: MetricValue = getattr(row.image_quality, attr)
        lines.append(f"| {name} | {_fmt_metric(metric)} |")
    lines.append("")

    mfg = row.manufacturability
    lines.append("**可制造性 proxy**")
    lines.append("")
    lines.append(f"- TTL: {mfg.total_track_mm:.3f} mm")
    lines.append(f"- 片数: {mfg.n_pieces}")
    lines.append(f"- 特殊高折射玻璃: {'是' if mfg.has_special_glass else '否'}")
    lines.append(f"- 非球面项数: {_fmt_metric(mfg.aspheric_term_count)}")
    lines.append(f"- 非球面面数: {_fmt_metric(mfg.aspheric_surface_count)}")
    lines.append(f"- 主光线角 (deg): {_fmt_metric(mfg.chief_ray_angle_deg)}")
    lines.append(f"- **{_md_safe(mfg.note)}**")
    lines.append("")

    lines.append("**排序结果**")
    lines.append("")
    if row.rank.status == "ranked":
        assert row.rank.score is not None
        lines.append(
            f"- status=`ranked`, score={row.rank.score:.3f}, "
            f"coverage_pct={row.rank.coverage_pct:.0%}"
        )
    else:
        missing = ", ".join(row.rank.missing_metrics) or "(none)"
        lines.append(
            f"- status=`withheld`, coverage_pct={row.rank.coverage_pct:.0%}, "
            f"missing_metrics={missing}"
        )
    lines.append(f"- {row.rank_explanation}")
    lines.append("")
    return lines


def _render_expert_blank_section(candidate_set: CandidateSet) -> list[str]:
    lines = [
        "## 良品率判定（[EXPERT] 留白 — AI 不代判）",
        "",
        "以下判定由资深填写：每候选 值得细看 / 不值得 / 需补数据 —— AI 不代判。",
        "",
        "| 候选 ID | 值得细看 | 不值得 | 需补数据 | 备注 |",
        "|---|---|---|---|---|",
    ]
    lines.extend(f"| `{sc.scorecard.candidate_id}` | ☐ | ☐ | ☐ | |" for sc in candidate_set.candidates)
    lines.append("")
    return lines


def render_markdown(label: str, candidate_set: CandidateSet) -> str:
    lines: list[str] = []
    lines += _render_requirement_echo(label, candidate_set.target)
    lines += _render_banner(candidate_set)
    lines += _render_summary(candidate_set)
    lines.append("## 候选详情")
    lines.append("")
    for i, sc in enumerate(candidate_set.candidates, start=1):
        lines += _render_candidate(i, sc)
    lines += _render_expert_blank_section(candidate_set)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="输出目录（MD+JSON 报告）")
    parser.add_argument(
        "--requirements",
        type=Path,
        default=None,
        help="需求集 JSON 文件（列表，每项是 TargetSpec 字段 + 可选 label）；省略则用内置 demo 需求",
    )
    parser.add_argument("--n", type=int, default=DEFAULT_N, help=f"每条需求产出候选数（默认 {DEFAULT_N}）")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        dest="min_coverage_pct",
        help=(
            "必需维覆盖率下限，覆盖 score_candidate 的 min_coverage_pct（§7-E 可配"
            "旋钮，见 scorecard.py `_rank` docstring）；省略则用其内建默认（当前 80%）"
        ),
    )
    return parser.parse_args(argv)


def _requirement_failed(candidate_set: CandidateSet) -> bool:
    """A requirement counts as a hard failure when its generator crashed
    (recorded by `orchestrate`'s isolation strategy as a
    "mode=... generator=... 失败" note) or it produced zero candidates
    outright — either way the report has nothing (or nothing trustworthy)
    for a reviewer. The .md/.json still get written either way (fail loud on
    stdout/exit code, not by withholding the report)."""
    s = candidate_set.summary
    if s.candidate_count == 0:
        return True
    return any("generator=" in note and "失败" in note for note in s.notes)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    requirements = _load_requirements(args.requirements)
    args.out.mkdir(parents=True, exist_ok=True)

    index_lines = ["# C1 编排批量报告索引", ""]
    any_failed = False
    for i, req in enumerate(requirements, start=1):
        label = _requirement_label(req, i)
        target = _target_spec_from_requirement(req)
        candidate_set = orchestrate(
            target, target, n=args.n, min_coverage_pct=args.min_coverage_pct
        )

        md_path = args.out / f"report_{i:02d}.md"
        json_path = args.out / f"report_{i:02d}.json"
        md_path.write_text(render_markdown(label, candidate_set), encoding="utf-8")
        json_path.write_text(
            json.dumps(candidate_set.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        index_lines.append(f"- `{md_path.name}` / `{json_path.name}` — {label}")

        s = candidate_set.summary
        failed = _requirement_failed(candidate_set)
        any_failed = any_failed or failed
        status_tag = "[FAIL]" if failed else "[OK]"
        print(
            f"{status_tag} [{i}/{len(requirements)}] {label}: {s.candidate_count} candidates "
            f"({s.ranked_count} ranked, {s.withheld_count} withheld) -> {md_path}"
        )

    (args.out / "index.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    if any_failed:
        print(
            "[FAIL] 至少一条需求产 0 候选或触发 generator 错误——报告已照常落盘，"
            "见上方 [FAIL] 行 / 各 report_*.json 的 summary.notes",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
