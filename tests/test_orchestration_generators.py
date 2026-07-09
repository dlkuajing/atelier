"""Tests for `app.core.orchestration.generators` — C1 §6 Generator 契约。

权威依据：C1 spec §6（Generator 契约）+ §9（测试策略）。
`docs/superpowers/specs/2026-07-08-c1-multi-candidate-orchestration-design.md`

覆盖（§9）：
- `_generate` 产 `mode=TARGET_CONVERGED` 的 `RetrievalGenerator` 伪造 →
  `generate` `raise ValueError`（并验证 `python -O` 下仍 raise）。
- 子类定义 `generate` → `__init_subclass__` `raise TypeError`（覆盖绕过
  路径）。
- `rank_seeds` 一致性：`RetrievalGenerator` 的 top-4 与现有
  `candidate_comparison` 一致（重构不改行为）；N>4 有稳定
  `nearby_alternative_N`。
- 降级测试：无 CODE V 跑通 Mode1，全链路绿；`TargetConvergedGenerator`
  恒返回 `[]`。
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import ClassVar

import pytest

from app.core.case_library import _candidate_scenarios, load_case_library, match_case
from app.core.lens_system import Scenario
from app.core.mtf_fields import MTF_CANONICAL_FIELD_FRACS, format_mtf_field_fraction
from app.core.orchestration.candidate import (
    GeneratedCandidate,
    GenerationMode,
    OpticalExtras,
    TargetSpec,
)
from app.core.orchestration.generators import (
    CandidateGenerator,
    RetrievalGenerator,
    TargetConvergedGenerator,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

_WIDE_REQUEST: dict[str, object] = {
    "efl_mm": 2.8,
    "fov_deg": 78.0,
    "fnum": 2.4,
    "image_height_mm": 3.3,
    "priority": "cost",
}


def _wide_target_spec() -> TargetSpec:
    return TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, **_WIDE_REQUEST)


def _wide_pool_size() -> int:
    allowed = _candidate_scenarios(Scenario.SMARTPHONE_WIDE)
    return sum(1 for c in load_case_library() if c.metadata and c.metadata.scenario in allowed)


# ---------------------------------------------------------------------------
# __init_subclass__ runtime override guard (§6.1, §9)
# ---------------------------------------------------------------------------


def test_subclass_overriding_generate_raises_type_error_at_definition():
    with pytest.raises(TypeError, match="不得覆盖 final 方法 generate"):

        class BadGenerator(CandidateGenerator):
            mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

            def _generate(self, spec, target, *, n):  # noqa: ANN001
                return []

            def generate(self, spec, target, *, n):  # noqa: ANN001 — illegal override
                return self._generate(spec, target, n=n)


def test_subclass_only_implementing_generate_is_fine():
    class GoodGenerator(CandidateGenerator):
        mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

        def _generate(self, spec, target, *, n):  # noqa: ANN001
            return []

    assert GoodGenerator().generate(_wide_target_spec(), _wide_target_spec(), n=1) == []


# ---------------------------------------------------------------------------
# Mode mismatch invariant — must raise even under `python -O` (§9)
# ---------------------------------------------------------------------------


def test_generate_raises_when_generator_forges_wrong_mode_in_process():
    case = load_case_library()[0]
    assert case.metadata is not None

    class ForgingGenerator(CandidateGenerator):
        mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

        def _generate(self, spec, target, *, n):  # noqa: ANN001
            return [
                GeneratedCandidate(
                    candidate_id="forged",
                    mode=GenerationMode.TARGET_CONVERGED,  # lies about its declared mode
                    source_case_id=case.metadata.case_id,
                    payload=case,
                    optical_extras=OpticalExtras(),
                    generation_notes=["forged mode for invariant test"],
                )
            ]

    with pytest.raises(ValueError, match="!= 声明"):
        ForgingGenerator().generate(_wide_target_spec(), _wide_target_spec(), n=1)


def test_generate_raises_under_python_dash_O_subprocess():
    """The mode check uses `raise ValueError`, not `assert`, so it must
    survive `python -O` (which strips `assert` statements + `__debug__`
    blocks). Runs the check in a real subprocess to prove it."""
    script = textwrap.dedent(
        """
        import sys
        from typing import ClassVar

        from app.core.case_library import load_case_library
        from app.core.orchestration.candidate import (
            GeneratedCandidate,
            GenerationMode,
            OpticalExtras,
        )
        from app.core.orchestration.generators import CandidateGenerator

        case = load_case_library()[0]
        assert case.metadata is not None

        class ForgingGenerator(CandidateGenerator):
            mode: ClassVar[GenerationMode] = GenerationMode.RETRIEVED

            def _generate(self, spec, target, *, n):
                return [
                    GeneratedCandidate(
                        candidate_id="forged",
                        mode=GenerationMode.TARGET_CONVERGED,
                        source_case_id=case.metadata.case_id,
                        payload=case,
                        optical_extras=OpticalExtras(),
                        generation_notes=["forged mode for invariant test"],
                    )
                ]

        try:
            ForgingGenerator().generate(None, None, n=1)
        except ValueError:
            print("RAISED_OK")
        else:
            print("NOT_RAISED")
        """
    )
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
        timeout=120,
    )
    assert "RAISED_OK" in result.stdout, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "NOT_RAISED" not in result.stdout
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# RetrievalGenerator — behavior parity with match_case (§6.2, §9)
# ---------------------------------------------------------------------------


def test_retrieval_generator_top4_matches_match_case_candidate_comparison():
    sample = match_case(
        Scenario.SMARTPHONE_WIDE,
        _WIDE_REQUEST["efl_mm"],
        _WIDE_REQUEST["fnum"],
        _WIDE_REQUEST["fov_deg"],
        image_height_mm=_WIDE_REQUEST["image_height_mm"],
        priority=_WIDE_REQUEST["priority"],
        lightweight_design_assessment=True,
    )
    assert sample is not None and sample.design_assessment is not None
    expected = [(c.case_id, c.role) for c in sample.design_assessment.candidate_comparison]
    assert expected  # sanity: match_case actually produced comparisons

    generator = RetrievalGenerator()
    spec = _wide_target_spec()
    candidates = generator.generate(spec, spec, n=4)

    actual = [(c.source_case_id, c.candidate_id.split("::", 1)[1]) for c in candidates]
    assert actual == expected

    for c in candidates:
        assert c.mode is GenerationMode.RETRIEVED
        assert c.source_case_id is not None
        assert c.payload is not None
        assert c.generation_notes[0] == "检索最近邻 seed，未朝 target 优化"
        # C1-c: RI 已接进 generator 阶段（relative_illumination.py），恒产出
        # 全部 canonical field 的 key（值可用/不可用取决于该 case 的实际光追结果）。
        assert c.optical_extras.ri_by_field is not None
        expected_keys = {format_mtf_field_fraction(f) for f in MTF_CANONICAL_FIELD_FRACS}
        assert set(c.optical_extras.ri_by_field.keys()) == expected_keys


def test_retrieval_generator_n_less_than_4_is_prefix_of_top4():
    spec = _wide_target_spec()
    generator = RetrievalGenerator()
    top4 = generator.generate(spec, spec, n=4)
    top2 = generator.generate(spec, spec, n=2)
    assert [c.candidate_id for c in top2] == [c.candidate_id for c in top4[:2]]


def test_retrieval_generator_n_greater_than_4_has_stable_nearby_alternative_numbering():
    pool_size = _wide_pool_size()
    n = min(8, pool_size)
    assert n > 4, f"wide-family pool too small for this test (pool_size={pool_size})"

    spec = _wide_target_spec()
    generator = RetrievalGenerator()
    candidates_a = generator.generate(spec, spec, n=n)
    candidates_b = generator.generate(spec, spec, n=n)

    assert len(candidates_a) == n
    ids_a = [c.candidate_id for c in candidates_a]
    ids_b = [c.candidate_id for c in candidates_b]
    assert ids_a == ids_b  # deterministic across calls

    # every candidate is a distinct case
    source_ids = [c.source_case_id for c in candidates_a]
    assert len(set(source_ids)) == n

    roles = [c.candidate_id.split("::", 1)[1] for c in candidates_a]
    known_special_roles = {"best_match", "cost_variant", "thin_variant", "performance_variant"}
    nearby_indices = []
    for role in roles:
        if role in known_special_roles:
            continue
        assert role.startswith("nearby_alternative_"), role
        nearby_indices.append(int(role.rsplit("_", 1)[1]))

    # nearby_alternative_N numbering is a gapless, duplicate-free 1..count sequence
    assert sorted(nearby_indices) == list(range(1, len(nearby_indices) + 1))


def test_retrieval_generator_raises_when_efl_or_fov_is_none():
    """Mode1 检索层仍要求 efl_mm/fov_deg 确定值——`TargetSpec.efl_mm`/
    `fov_deg` 放宽到 `float | None` 是 §7-E scorecard 打分层的 unconstrained
    语义，不下沉进 `rank_seeds` 的检索排序查询（没有"不检索这一维"的
    语义）；`None` 时 fail-fast，而不是猜一个默认值。"""
    generator = RetrievalGenerator()
    spec_no_efl = TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, fov_deg=78.0, fnum=2.4)
    with pytest.raises(ValueError, match="efl_mm/fov_deg"):
        generator.generate(spec_no_efl, spec_no_efl, n=4)

    spec_no_fov = TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, efl_mm=2.8, fnum=2.4)
    with pytest.raises(ValueError, match="efl_mm/fov_deg"):
        generator.generate(spec_no_fov, spec_no_fov, n=4)


def test_retrieval_generator_unknown_scenario_family_returns_empty_when_pool_empty():
    # AR near-eye has no seeds in the smartphone case library family; the
    # generator must fail closed (empty list), not raise, when the filtered
    # pool is empty (mirrors match_case's `if not cases: return None`).
    spec = TargetSpec(
        scenario=Scenario.AR_NEAR_EYE, efl_mm=10.0, fov_deg=40.0, fnum=2.0
    )
    generator = RetrievalGenerator()
    pool = [
        c
        for c in load_case_library()
        if c.metadata and c.metadata.scenario in _candidate_scenarios(Scenario.AR_NEAR_EYE)
    ]
    candidates = generator.generate(spec, spec, n=4)
    if pool:
        assert len(candidates) > 0
    else:
        assert candidates == []


# ---------------------------------------------------------------------------
# TargetConvergedGenerator — empty-slot stub (§6.4, §8)
# ---------------------------------------------------------------------------


def test_target_converged_generator_returns_empty_mode3_not_wired():
    generator = TargetConvergedGenerator()
    spec = _wide_target_spec()
    result = generator.generate(spec, spec, n=4)
    assert result == []


def test_target_converged_generator_mode_class_var():
    assert TargetConvergedGenerator.mode is GenerationMode.TARGET_CONVERGED
    assert RetrievalGenerator.mode is GenerationMode.RETRIEVED
