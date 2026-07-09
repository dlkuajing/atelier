"""Tests for `app.core.orchestration.orchestrator` — C1 §4/§7-E/§8/§9 编排入口。

权威依据：C1 spec §4（数据流）+ §7-E（排序/coverage gate）+ §8（降级能力）+
§9（测试策略）。
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

覆盖（本铲 C1-d，任务清单）：
- orchestrate 端到端（真实 case library，n=4）-> CandidateSet 含 4 颗
  RETRIEVED + honesty_banner 在（Mode3 空插槽，全 RETRIEVED）。
- modes 过滤：只跑被选中的 mode，被排除的 generator 连实例化都不发生。
- 排序正确：ranked 按 score 降序在前，withheld 沉底。
- generator 抛错隔离：单 mode 失败记入 summary.notes，不炸整批、不外抛。
- `scripts/c1_orchestrate.py` 冒烟：产出 MD+JSON，MD 含 banner + 留白节，
  JSON 可经 `CandidateSet.model_validate` 回读。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar

import pytest

from app.core.lens_system import Scenario
from app.core.orchestration import orchestrator
from app.core.orchestration.candidate import (
    NO_TARGET_CONVERGED_BANNER,
    CandidateSet,
    GenerationMode,
    OpticalExtras,
    TargetSpec,
)
from app.core.orchestration.generators import CandidateGenerator, RetrievalGenerator
from app.core.orchestration.orchestrator import orchestrate

_WIDE_REQUEST: dict[str, object] = {
    "efl_mm": 2.8,
    "fov_deg": 78.0,
    "fnum": 2.4,
    "image_height_mm": 3.3,
    "priority": "cost",
}


def _wide_target_spec() -> TargetSpec:
    return TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, **_WIDE_REQUEST)


# ---------------------------------------------------------------------------
# End-to-end: real case library, n=4 (§9)
# ---------------------------------------------------------------------------


def test_orchestrate_end_to_end_real_case_library_produces_4_retrieved_with_banner():
    target = _wide_target_spec()
    result = orchestrate(target, target, n=4)

    assert isinstance(result, CandidateSet)
    assert len(result.candidates) == 4
    assert all(sc.mode is GenerationMode.RETRIEVED for sc in result.candidates)
    assert result.summary.candidate_count == 4
    assert result.summary.mode_counts == {GenerationMode.RETRIEVED: 4}
    assert result.summary.ranked_count + result.summary.withheld_count == 4
    # Mode3 空插槽 -> 全批 RETRIEVED -> honesty_banner 自动为固定常量
    assert result.honesty_banner == NO_TARGET_CONVERGED_BANNER
    assert result.target is target


# ---------------------------------------------------------------------------
# modes filtering (§4)
# ---------------------------------------------------------------------------


def test_orchestrate_modes_filter_to_target_converged_only_yields_no_candidates():
    target = _wide_target_spec()
    result = orchestrate(target, target, n=4, modes=[GenerationMode.TARGET_CONVERGED])
    assert result.candidates == []
    assert result.summary.candidate_count == 0
    assert result.summary.notes == []  # Mode3 空插槽合法返回 [] ，不是错误


def test_orchestrate_modes_filter_never_instantiates_excluded_generator(monkeypatch):
    def _boom(self, spec, target, *, n):  # noqa: ANN001
        raise RuntimeError("RetrievalGenerator should not run when excluded by modes filter")

    monkeypatch.setattr(RetrievalGenerator, "_generate", _boom)
    target = _wide_target_spec()
    result = orchestrate(target, target, n=4, modes=[GenerationMode.TARGET_CONVERGED])
    assert result.candidates == []
    assert result.summary.notes == []  # RetrievalGenerator 从未跑过 -> 无错误记录


def test_orchestrate_modes_dedupes_and_preserves_order():
    target = _wide_target_spec()
    result = orchestrate(
        target, target, n=2, modes=[GenerationMode.RETRIEVED, GenerationMode.RETRIEVED]
    )
    assert len(result.candidates) == 2  # 重复 mode 去重，不翻倍


def test_orchestrate_unregistered_mode_raises():
    target = _wide_target_spec()
    with pytest.raises(ValueError, match="unregistered generation mode"):
        orchestrate(target, target, n=4, modes=["not-a-real-mode"])  # type: ignore[list-item]


def test_registry_is_immutable():
    """`_REGISTRY` is a `MappingProxyType` — consistency hardening alongside
    `candidate.py::CONVERGED_FIELDS`; runtime in-place mutation must raise."""
    with pytest.raises(TypeError):
        orchestrator._REGISTRY[GenerationMode.RETRIEVED] = RetrievalGenerator


# ---------------------------------------------------------------------------
# Ranking: ranked-desc-by-score first, withheld sinks to the bottom (§7-E)
# ---------------------------------------------------------------------------


class _MixedRankGenerator(CandidateGenerator):
    """测试专用：2 颗真实可打分候选 + 1 颗故意退化(空 MTF fields)的候选，
    后者 `score_candidate` 必然 withheld（§7-E coverage gate 缺 mtf）——
    用来断言排序而不直接摸 `_rank` 私有实现。"""

    mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

    def _generate(self, spec, target, *, n):  # noqa: ANN001
        base = RetrievalGenerator()._generate(spec, target, n=3)
        assert len(base) == 3, "wide-family pool too small for this fixture"
        degraded_mtf = base[2].payload.mtf.model_copy(update={"fields": []})
        degraded_payload = base[2].payload.model_copy(update={"mtf": degraded_mtf})
        degraded = base[2].model_copy(
            update={"candidate_id": "degraded-withheld", "payload": degraded_payload}
        )
        return [base[0], base[1], degraded]


def test_orchestrate_ranked_sorted_desc_and_withheld_sinks_to_bottom(monkeypatch):
    # `_REGISTRY` is now a `MappingProxyType` (immutable) — swap the whole
    # module attribute instead of `monkeypatch.setitem`.
    monkeypatch.setattr(
        orchestrator,
        "_REGISTRY",
        MappingProxyType({**orchestrator._REGISTRY, GenerationMode.RETRIEVED: _MixedRankGenerator}),
    )
    target = _wide_target_spec()
    result = orchestrate(target, target, n=3, modes=[GenerationMode.RETRIEVED])

    assert len(result.candidates) == 3
    statuses = [sc.scorecard.rank.status for sc in result.candidates]
    assert statuses == ["ranked", "ranked", "withheld"]
    assert result.candidates[-1].scorecard.candidate_id == "degraded-withheld"
    scores = [sc.scorecard.rank.score for sc in result.candidates[:2]]
    assert scores[0] is not None and scores[1] is not None
    assert scores[0] >= scores[1]
    assert result.summary.ranked_count == 2
    assert result.summary.withheld_count == 1


# ---------------------------------------------------------------------------
# RI-all-missing batch alert (§7-E)
# ---------------------------------------------------------------------------


class _AllRIUnavailableGenerator(CandidateGenerator):
    mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

    def _generate(self, spec, target, *, n):  # noqa: ANN001
        base = RetrievalGenerator()._generate(spec, target, n=n)
        return [c.model_copy(update={"optical_extras": OpticalExtras(ri_by_field=None)}) for c in base]


def test_orchestrate_summary_flags_when_ri_missing_across_whole_batch(monkeypatch):
    # `_REGISTRY` is now a `MappingProxyType` (immutable) — swap the whole
    # module attribute instead of `monkeypatch.setitem`.
    monkeypatch.setattr(
        orchestrator,
        "_REGISTRY",
        MappingProxyType(
            {**orchestrator._REGISTRY, GenerationMode.RETRIEVED: _AllRIUnavailableGenerator}
        ),
    )
    target = _wide_target_spec()
    result = orchestrate(target, target, n=3, modes=[GenerationMode.RETRIEVED])
    assert result.summary.ri_missing_count == result.summary.candidate_count
    assert any("RI 全缺" in note for note in result.summary.notes)


# ---------------------------------------------------------------------------
# Generator failure isolation (§4/§8 "隔离策略")
# ---------------------------------------------------------------------------


def test_orchestrate_isolates_single_generator_failure(monkeypatch):
    def _boom(self, spec, target, *, n):  # noqa: ANN001
        raise RuntimeError("simulated generator crash")

    monkeypatch.setattr(RetrievalGenerator, "_generate", _boom)
    target = _wide_target_spec()

    result = orchestrate(target, target, n=4)  # both modes registered

    assert isinstance(result, CandidateSet)  # orchestrate 本身不外抛 -- fail-open
    assert result.candidates == []  # RETRIEVED 崩了；TARGET_CONVERGED 本就合法空
    assert result.summary.candidate_count == 0
    assert len(result.summary.notes) == 1
    note = result.summary.notes[0]
    assert "retrieved" in note
    assert "RetrievalGenerator" in note
    assert "simulated generator crash" in note
    assert result.honesty_banner == NO_TARGET_CONVERGED_BANNER


# ---------------------------------------------------------------------------
# scripts/c1_orchestrate.py smoke test (§13)
# ---------------------------------------------------------------------------


def test_c1_orchestrate_script_smoke(tmp_path: Path):
    from scripts.c1_orchestrate import main

    out_dir = tmp_path / "c1_report"
    exit_code = main(["--out", str(out_dir), "--n", "2"])
    assert exit_code == 0

    index_path = out_dir / "index.md"
    assert index_path.exists()

    md_files = sorted(out_dir.glob("report_*.md"))
    json_files = sorted(out_dir.glob("report_*.json"))
    assert md_files
    assert len(md_files) == len(json_files)

    md_text = md_files[0].read_text(encoding="utf-8")
    assert NO_TARGET_CONVERGED_BANNER in md_text
    assert "[EXPERT] 留白" in md_text
    assert "值得细看" in md_text

    json_payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    roundtripped = CandidateSet.model_validate(json_payload)
    assert roundtripped.summary.candidate_count == 2
    assert len(roundtripped.candidates) == 2


def test_c1_orchestrate_script_with_custom_requirements_file(tmp_path: Path):
    from scripts.c1_orchestrate import main

    reqs = [
        {
            "label": "自定义主摄",
            "scenario": Scenario.SMARTPHONE_WIDE.value,
            "efl_mm": 3.2,
            "fov_deg": 79.0,
            "fnum": 2.0,
            "image_height_mm": 3.5,
            "priority": "balanced",
        }
    ]
    reqs_path = tmp_path / "reqs.json"
    reqs_path.write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")

    out_dir = tmp_path / "custom_report"
    exit_code = main(["--out", str(out_dir), "--requirements", str(reqs_path), "--n", "1"])
    assert exit_code == 0

    md_files = sorted(out_dir.glob("report_*.md"))
    assert len(md_files) == 1
    assert "自定义主摄" in md_files[0].read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Markdown safety against embedded '|'/newline in notes / requirement-echo
# values (§13 report rendering)
# ---------------------------------------------------------------------------


def test_c1_orchestrate_markdown_safe_against_embedded_pipe_and_newline(tmp_path: Path):
    """Regression: a free-form requirement field (or a generation note) that
    contains a literal newline or '|' must not split a Markdown table row
    into extra rows / extra columns."""
    from scripts.c1_orchestrate import main

    reqs = [
        {
            "label": "边界情况\n第二行 | 有管道符",
            "scenario": Scenario.SMARTPHONE_WIDE.value,
            "efl_mm": 2.8,
            "fov_deg": 78.0,
            "fnum": 2.4,
            "image_height_mm": 3.3,
            "manufacturing_tier": "tier-A\ntier-B | risky",
            "priority": "cost\nurgent",
        }
    ]
    reqs_path = tmp_path / "reqs.json"
    reqs_path.write_text(json.dumps(reqs, ensure_ascii=False), encoding="utf-8")
    out_dir = tmp_path / "md_safety_report"

    exit_code = main(["--out", str(out_dir), "--requirements", str(reqs_path), "--n", "1"])
    assert exit_code == 0

    md_text = (out_dir / "report_01.md").read_text(encoding="utf-8")
    assert md_text.startswith("# C1 候选报告 — 边界情况; 第二行 \\| 有管道符")

    table_start = md_text.index("| 字段 | 值 |")
    table_block = md_text[table_start:].split("\n\n", 1)[0]
    table_rows = [ln for ln in table_block.splitlines() if ln.startswith("|")]
    # header + separator + 10 field rows; a raw embedded '\n' in
    # manufacturing_tier/priority would have split into extra rows.
    assert len(table_rows) == 12

    tier_row = next(r for r in table_rows if r.startswith("| manufacturing_tier"))
    assert tier_row == "| manufacturing_tier | tier-A; tier-B \\| risky |"
    priority_row = next(r for r in table_rows if r.startswith("| priority"))
    assert priority_row == "| priority | cost; urgent |"


# ---------------------------------------------------------------------------
# main() exit code reflects generator failure / zero-candidate requirements
# (§13 report caller contract)
# ---------------------------------------------------------------------------


def test_c1_orchestrate_main_returns_nonzero_when_generator_fails(tmp_path: Path, monkeypatch):
    """Regression: `main` previously always returned 0 even when every
    requirement's generator crashed and produced zero candidates. The report
    files must still land on disk (fail loud via exit code, not by
    withholding output)."""
    from scripts.c1_orchestrate import main

    def _boom(self, spec, target, *, n):  # noqa: ANN001
        raise RuntimeError("simulated total generator wipeout")

    monkeypatch.setattr(RetrievalGenerator, "_generate", _boom)

    out_dir = tmp_path / "failed_report"
    exit_code = main(["--out", str(out_dir), "--n", "2"])

    assert exit_code == 1
    assert (out_dir / "report_01.md").exists()
    assert (out_dir / "index.md").exists()
