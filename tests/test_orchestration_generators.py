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

import hashlib
import json
import math
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from app.core.batch_run_lock import BatchRunnerLockHeldError, batch_runner_lock
from app.core.case_library import _candidate_scenarios, load_case_library, match_case, rank_seeds
from app.core.engines.codev_batch import DEFAULT_CODEV_EXECUTABLE, CodeVBatchError
from app.core.engines.seed_target_score import SeedTargetScore
from app.core.lens_system import Scenario
from app.core.mtf_fields import MTF_CANONICAL_FIELD_FRACS, format_mtf_field_fraction
from app.core.optical_sample import OpticalSampleData
from app.core.orchestration import generators as generators_module
from app.core.orchestration.candidate import (
    CandidateSet,
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
from app.core.orchestration.orchestrator import orchestrate
from app.core.orchestration.scorecard import score_candidate
from app.core.parameter_guards import SCENARIO_BOUNDS, ParameterGuardError, validate_scenario_params
from app.core.zmx_ingest import ZMX_AMMO_DIR

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
    spec = TargetSpec(scenario=Scenario.AR_NEAR_EYE, efl_mm=10.0, fov_deg=40.0, fnum=2.0)
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
# TargetConvergedGenerator — Mode3 真接入 (§6.4, §8, 2026-07-10)
# ---------------------------------------------------------------------------


def test_target_converged_generator_mode_class_var():
    assert TargetConvergedGenerator.mode is GenerationMode.TARGET_CONVERGED
    assert RetrievalGenerator.mode is GenerationMode.RETRIEVED


def test_target_converged_generator_rejects_custom_stagec_runner_in_production():
    def custom_runner(**_kwargs: object) -> Path:
        raise AssertionError("custom Stage C runner must never be admitted")

    with pytest.raises(ValueError, match="official Stage C runner"):
        TargetConvergedGenerator(stagec_runner=custom_runner)


def test_target_converged_generator_returns_empty_when_efl_target_missing():
    """Mode3 无 target EFL 无法定义"朝哪收敛"——正常降级（`[]`），不是调用方
    传参错误（与 RetrievalGenerator 的 fail-fast `raise` 不同）。"""
    generator = TargetConvergedGenerator()
    spec = TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, fov_deg=78.0, fnum=2.4)
    assert generator.generate(spec, spec, n=4) == []


def test_target_converged_generator_returns_empty_when_codev_unavailable(
    monkeypatch, tmp_path: Path
):
    """CODE V 硬依赖不可用 → 降级返回 `[]`，不破坏无 CODE V 全链路（§8）。"""
    monkeypatch.setattr(
        generators_module, "DEFAULT_CODEV_EXECUTABLE", tmp_path / "no-codev-here.exe"
    )
    generator = TargetConvergedGenerator()
    spec = _wide_target_spec()
    assert generator.generate(spec, spec, n=4) == []


def _real_case_with_zmx() -> OpticalSampleData:
    for case in load_case_library():
        if case.metadata is not None and (ZMX_AMMO_DIR / case.metadata.source_zmx).is_file():
            return case
    raise AssertionError("case library has no case with an on-disk source ZMX")


def _fake_match(
    *, band: str = "lt5", score: float = 2.0, delta_pct: float = 2.0
) -> SeedTargetScore:
    return SeedTargetScore(
        delta_efl_pct=delta_pct, abs_delta_efl_pct=abs(delta_pct), score=score, band=band
    )


def _fake_ladder_result(
    *,
    optimized_zmx_path: str | None,
    target_efl_mm: float = 3.797,
    fnum_target: float = 2.3,
    target_achieved: bool = True,
) -> dict[str, object]:
    accepted = {
        "rung_index": 3,
        "target_fnum": fnum_target,
        "status": "measured",
        "measured_fnum": fnum_target,
        "fnum_target_deviation_pct": 0.0,
        "fno_param_achieved": target_achieved,
        "ray_traceable": target_achieved,
        "ray_grid": (
            {
                "category": "ok",
                "refl_count": 0,
                "miss_count": 0,
                "ray_aiming_warning": False,
                "aperture_conflict_matched": None,
                "excerpt": None,
                "note": "positive measured listing evidence",
                "normal_completion": True,
                "abnormal_completion_matched": None,
            }
            if target_achieved
            else {"category": "TIR", "refl_count": 1, "miss_count": 0}
        ),
        "efl_target_deviation_pct": 0.01,
        "post_aut.max_rms_spot_diameter_um": 12.3,
        "post_aut.max_rms_wavefront_error_waves": 0.04,
        "err_f_ratio": 0.09,
        "aut_termination": "normal_completion",
        "aut_converged": True,
        "autovig.edge_used": "0.0",
        "autovig.converged": "1",
        "effective_edge_used": "0.0",
        "quality_note": "measured on accepted ladder pupil",
        "optimized_zmx_path": optimized_zmx_path,
        "ray_retry": None,
        "error": None,
    }
    return {
        "schema": "atelier-p15-fno-ladder-v1",
        "source_zmx": "seed.zmx",
        "stage": "B",
        "target_efl_mm": target_efl_mm,
        "fnum_target": fnum_target,
        "rung_count": 3,
        "fnum_tolerance_pct": 8.0,
        "vig_ladder": [0.0, 0.2, 0.3],
        "ray_retry_vig_ladder": [0.2, 0.3, 0.4, 0.5],
        "num_fields": 3,
        "extra_dof": "both",
        "native_fnum_measured": 2.5,
        "rungs": [accepted],
        "last_measured_rung_index": 3,
        "last_measured_rung": accepted,
        "target_achieved": target_achieved,
        "accepted_final": accepted if target_achieved else None,
        "blocked": False,
    }


def _fov_variant_pair() -> tuple[OpticalSampleData, OpticalSampleData]:
    """Two synthetic seeds sharing one real on-disk ZMX + identical EFL/F#/
    image-height, differing only in native FOV (36 deg vs 78 deg) and
    `case_id` — the exact real-machine-exposed failure shape
    (fix/mode3-seed-fov-prefilter, 2026-07-10): stage 2's EFL-only score
    ties the two, so only stage 1's FOV-weighted `rank_seeds` distance can
    tell them apart."""
    base = _real_case_with_zmx()
    assert base.metadata is not None

    narrow = base.model_copy(deep=True)
    assert narrow.metadata is not None
    narrow.metadata.case_id = f"{base.metadata.case_id}-fovtest-narrow"
    narrow.metadata.fov_deg = 36.0

    wide = base.model_copy(deep=True)
    assert wide.metadata is not None
    wide.metadata.case_id = f"{base.metadata.case_id}-fovtest-wide"
    wide.metadata.fov_deg = 78.0

    return narrow, wide


# ---------------------------------------------------------------------------
# `_rank_seeds_by_target_match` — FOV 近邻预筛（fix/mode3-seed-fov-prefilter，
# 2026-07-10）
# ---------------------------------------------------------------------------


def test_rank_seeds_by_target_match_prefers_fov_near_seed_when_fov_constrained(monkeypatch):
    """真机实锤复现的最小案例：同 EFL-band 两颗 seed，FOV 36 deg vs 78 deg。
    stage 2（EFL-only）单独打分二者打平；target fov=78 时 stage 1 的 FOV
    近邻预筛必须把 78 deg 那颗排到最前——特意把 36 deg 那颗放在
    `cases_for_scenario` 返回列表最前面，若 stage 1 没生效，稳定排序会让
    36 deg 那颗（错的那颗）留在最前，测试才有意义。"""
    narrow_fov, wide_fov = _fov_variant_pair()
    assert narrow_fov.metadata is not None and wide_fov.metadata is not None
    monkeypatch.setattr(
        generators_module,
        "cases_for_scenario",
        lambda scenario: [narrow_fov, wide_fov],  # noqa: ARG005
    )
    spec = TargetSpec(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=narrow_fov.paraxial.effective_focal_length_mm,
        fov_deg=78.0,
        fnum=narrow_fov.paraxial.f_number,
    )
    scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
    case_ids = [case.metadata.case_id for case, _ in scored if case.metadata is not None]
    assert case_ids[0] == wide_fov.metadata.case_id


def test_rank_seeds_by_target_match_degrades_to_efl_only_when_fov_unconstrained(monkeypatch):
    """`spec.fov_deg is None`（§7-E unconstrained）→ stage 1 跳过，退化为纯
    EFL 排序（原行为）：两颗 seed EFL 相同打平，stable sort 保留
    `cases_for_scenario` 原始顺序——本测试把 36 deg（对 target fov=78 而言
    错配）那颗放在池子最前面，验证退化路径确实没做 FOV 近邻过滤（否则会
    像上一测试一样选中 78 deg 那颗，掩盖了"未过滤"这件事）。"""
    narrow_fov, wide_fov = _fov_variant_pair()
    assert narrow_fov.metadata is not None and wide_fov.metadata is not None
    monkeypatch.setattr(
        generators_module,
        "cases_for_scenario",
        lambda scenario: [narrow_fov, wide_fov],  # noqa: ARG005
    )
    spec = TargetSpec(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=narrow_fov.paraxial.effective_focal_length_mm,
        fov_deg=None,
        fnum=narrow_fov.paraxial.f_number,
    )
    scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
    case_ids = [case.metadata.case_id for case, _ in scored if case.metadata is not None]
    assert case_ids[0] == narrow_fov.metadata.case_id  # 退化路径未做 FOV 过滤
    assert wide_fov.metadata.case_id in case_ids  # 两颗都还在（没被 stage 1 剔除）


# ---------------------------------------------------------------------------
# `_fov_bounded_efl_close_extras` — stage 1b 甜区召回补齐（P11 甜区覆盖率
# 漏斗调优 + 对抗审 BLOCKER 修复，2026-07-11）。实锤依据：
# `scripts/sweet_zone_coverage.py` 量化，wide/tele/uw 三场景 miss 中
# 100%/100%/100% 是 `efl_material_exists_but_not_selected`（存在性扫描口径，
# EFL 维真空洞=0）——库内存在甜区带内 seed，但 stage 1 的
# top-`_FOV_PREFILTER_TOP_K` 没选中它。cap 锚点=旧路径真机席位
# （primary-only stage 2 排序后前 `_TARGET_MAX_SEEDS` 颗）的最差 |FOV
# 失配|——安全证明见生产函数 docstring。见 `.planning/loop/
# mode3-funnel-tuning-report.md` 的 K/cap 量化扫描。
# ---------------------------------------------------------------------------


def _efl_fov_variant(
    base: OpticalSampleData, case_id: str, *, efl_mm: float, fov_deg: float
) -> OpticalSampleData:
    """`base` 的 deep copy，覆写 case_id / 原生 EFL（metadata+paraxial 两处
    一起改，同 `test_sweet_zone_coverage.py` 的既有惯例）/ 原生 FOV。"""
    variant = base.model_copy(deep=True)
    assert variant.metadata is not None
    variant.metadata.case_id = case_id
    variant.metadata.computed_efl_mm = efl_mm
    variant.paraxial.effective_focal_length_mm = efl_mm
    variant.metadata.fov_deg = fov_deg
    return variant


def test_fov_bounded_efl_close_extras_includes_seed_within_adaptive_fov_cap():
    """单成员 primary（席位=其自身）|FOV 失配|=5.0（target_fov=80, 成员
    fov=85）定义 cap；候选 seed fov=83（失配 3.0 <= 5.0）且 EFL
    band=lt5（delta≈-2%）必须被纳入 extras。"""
    base = _real_case_with_zmx()
    target_efl = base.paraxial.effective_focal_length_mm

    primary_member = _efl_fov_variant(base, "PRIMARY-1", efl_mm=target_efl * 3.0, fov_deg=85.0)
    within_cap = _efl_fov_variant(base, "WITHIN-CAP", efl_mm=target_efl * 0.98, fov_deg=83.0)

    extras = generators_module._fov_bounded_efl_close_extras(
        [primary_member],
        [primary_member, within_cap],
        target_efl_mm=target_efl,
        target_fov_deg=80.0,
    )
    extra_ids = {c.metadata.case_id for c in extras if c.metadata is not None}
    assert "WITHIN-CAP" in extra_ids
    assert "PRIMARY-1" not in extra_ids  # 已在 primary 里，不重复纳入


def test_fov_bounded_efl_close_extras_excludes_seed_beyond_adaptive_fov_cap():
    """同上设定（cap=5.0），候选 seed fov=91（失配 11.0 > 5.0）即便 EFL
    band=lt5 也必须被排除——这是"不比旧路径真机席位的 FOV 容差更差"的核心
    不变量，直接对应判据 2（FOV 质量不回退）。"""
    base = _real_case_with_zmx()
    target_efl = base.paraxial.effective_focal_length_mm

    primary_member = _efl_fov_variant(base, "PRIMARY-1", efl_mm=target_efl * 3.0, fov_deg=85.0)
    beyond_cap = _efl_fov_variant(base, "BEYOND-CAP", efl_mm=target_efl * 0.98, fov_deg=91.0)

    extras = generators_module._fov_bounded_efl_close_extras(
        [primary_member],
        [primary_member, beyond_cap],
        target_efl_mm=target_efl,
        target_fov_deg=80.0,
    )
    extra_ids = {c.metadata.case_id for c in extras if c.metadata is not None}
    assert "BEYOND-CAP" not in extra_ids


def test_fov_bounded_efl_close_extras_excludes_seed_with_far_efl_band_even_within_fov_cap():
    """FOV 失配在自适应上限内（3.0 <= 5.0），但 EFL band=gt30（delta 远超
    `_EFL_CLOSE_BANDS_FOR_RECALL`）——band 门禁必须独立生效，不能靠 FOV
    近就绕过 EFL 接近度要求。"""
    base = _real_case_with_zmx()
    target_efl = base.paraxial.effective_focal_length_mm

    primary_member = _efl_fov_variant(base, "PRIMARY-1", efl_mm=target_efl * 3.0, fov_deg=85.0)
    far_efl_near_fov = _efl_fov_variant(
        base, "FAR-EFL-NEAR-FOV", efl_mm=target_efl * 5.0, fov_deg=83.0
    )

    extras = generators_module._fov_bounded_efl_close_extras(
        [primary_member],
        [primary_member, far_efl_near_fov],
        target_efl_mm=target_efl,
        target_fov_deg=80.0,
    )
    extra_ids = {c.metadata.case_id for c in extras if c.metadata is not None}
    assert "FAR-EFL-NEAR-FOV" not in extra_ids


def test_fov_bounded_efl_close_extras_empty_primary_yields_zero_cap():
    """`primary` 为空（结构上不应发生，防御性覆盖）：`fov_cap` 退化为 0.0
    （`default=0.0`），任何非零 FOV 失配的候选都会被排除。"""
    base = _real_case_with_zmx()
    target_efl = base.paraxial.effective_focal_length_mm
    candidate = _efl_fov_variant(base, "CANDIDATE", efl_mm=target_efl, fov_deg=80.5)

    extras = generators_module._fov_bounded_efl_close_extras(
        [], [candidate], target_efl_mm=target_efl, target_fov_deg=80.0
    )
    assert extras == []


def test_fov_bounded_efl_close_extras_cap_anchored_to_old_codev_seats_not_primary_max():
    """对抗审 BLOCKER 复现（helper 级）：primary 内单颗 FOV 离群点若 EFL
    差到进不了旧路径真机席位（stage 2 前 `_TARGET_MAX_SEEDS` 颗），就不得
    撑大 cap。SEAT-A/B（FOV 78=target，ΔEFL -10%/-12%，5to15）占据两个旧
    席位（失配 0,0 → cap=0）；OUTLIER（FOV 20，ΔEFL +40%，gt30）虽在
    primary 里但排不进席位；PR#48 形状的 X（FOV 36，ΔEFL≈-0.1%，lt5）在
    第一版 cap（primary 全体最差=58°）下会被纳入并以 lt5 碾压全场——现版本
    必须排除它。"""
    base = _real_case_with_zmx()
    target_efl = 4.0
    seat_a = _efl_fov_variant(base, "SEAT-A", efl_mm=target_efl / 0.90, fov_deg=78.0)
    seat_b = _efl_fov_variant(base, "SEAT-B", efl_mm=target_efl / 0.88, fov_deg=78.0)
    outlier = _efl_fov_variant(base, "OUTLIER-FOV20", efl_mm=target_efl / 1.40, fov_deg=20.0)
    pr48_shape = _efl_fov_variant(base, "PR48-X-FOV36", efl_mm=target_efl / 0.999, fov_deg=36.0)

    extras = generators_module._fov_bounded_efl_close_extras(
        [seat_a, seat_b, outlier],
        [seat_a, seat_b, outlier, pr48_shape],
        target_efl_mm=target_efl,
        target_fov_deg=78.0,
    )
    assert extras == []  # cap=0（席位失配 0,0），不是 58（primary 全体最差）


def test_fov_bounded_efl_close_extras_all_tight_seats_give_zero_cap_no_extras():
    """对抗审 BLOCKER 指出的反向退化边界（接受为 fail-safe 行为并钉死）：
    旧席位全部精确贴合 target FOV（失配 0）→ cap=0 → 即便 extras 候选
    失配只有 0.5° 且 EFL 完美命中也不召回。语义：宁可少召回（保持旧路径
    行为），不可回退 FOV。"""
    base = _real_case_with_zmx()
    target_efl = 4.0
    tight = [
        _efl_fov_variant(base, f"TIGHT-{i}", efl_mm=target_efl / 0.90, fov_deg=80.0)
        for i in range(3)
    ]
    near_extra = _efl_fov_variant(base, "NEAR-EXTRA", efl_mm=target_efl, fov_deg=80.5)

    extras = generators_module._fov_bounded_efl_close_extras(
        tight, [*tight, near_extra], target_efl_mm=target_efl, target_fov_deg=80.0
    )
    assert extras == []


def test_rank_seeds_by_target_match_outlier_primary_does_not_reopen_pr48_blindspot(monkeypatch):
    """对抗审 BLOCKER 指定的端到端回归测试（断言最终胜者，不是 helper
    include/exclude）：9 颗近 FOV primary + 1 颗极远离群 primary + 1 个
    PR#48 形状 extra。

    构造（复现审查现场合成反例的确切形状）：target EFL=4.0/FOV=78°；
    primary = 9 颗 FOV 78°（ΔEFL -10%，5to15）+ 1 颗 FOV 20°（ΔEFL +40%，
    gt30，进不了席位）；primary 外 1 颗 FOV 36°、ΔEFL≈-0.1%（lt5，EFL
    score 碾压全场）。第一版 cap（primary 全体最差 |FOV 失配|=58°）会把
    FOV 36° 那颗放进竞争池并让它夺冠 = PR#48 的 36° seed 打 78° target
    盲区回归；席位锚 cap（席位=两颗 78° seed，失配 0 → cap=0）必须把它
    挡在外面，最终前 `_TARGET_MAX_SEEDS` 颗全部是近 FOV seed。

    `rank_seeds` 打桩为固定 primary 序（本测试的对象是 stage 1b+2 的组合
    安全性，不是 rank_seeds 的多维距离——打桩才能确定性复现"离群点在
    top-10 内"这个审查场景，不依赖 rank_seeds 权重的未来演化）。"""
    base = _real_case_with_zmx()
    target_efl = 4.0
    near = [
        _efl_fov_variant(base, f"NEAR-{i}", efl_mm=target_efl / 0.90, fov_deg=78.0)
        for i in range(9)
    ]
    outlier = _efl_fov_variant(base, "OUTLIER-FOV20", efl_mm=target_efl / 1.40, fov_deg=20.0)
    pr48_shape = _efl_fov_variant(base, "PR48-X-FOV36", efl_mm=target_efl / 0.999, fov_deg=36.0)

    pool = [pr48_shape, *near, outlier]  # 对抗性池序：PR#48 形状的 extra 放最前
    primary = [*near, outlier]  # 10 席 stage 1：9 近 + 1 极远（审查合成形状）
    monkeypatch.setattr(generators_module, "cases_for_scenario", lambda scenario: pool)  # noqa: ARG005
    monkeypatch.setattr(
        generators_module,
        "rank_seeds",
        lambda cases, **kwargs: SimpleNamespace(ranked_cases=primary),  # noqa: ARG005
    )

    spec = TargetSpec(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=target_efl,
        fov_deg=78.0,
        fnum=base.paraxial.f_number,
    )
    scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
    scored_ids = [c.metadata.case_id for c, _ in scored if c.metadata is not None]

    seats = scored_ids[: generators_module._TARGET_MAX_SEEDS]
    assert all(seat_id.startswith("NEAR-") for seat_id in seats), seats  # 无 FOV 大幅回退
    assert "PR48-X-FOV36" not in scored_ids  # 盲区形状 extra 未被离群点撑大的 cap 放进来


def test_rank_seeds_by_target_match_output_invariant_under_pool_permutation(monkeypatch):
    """对抗审 MINOR：extras 同 band/同 score 的 tie 由显式键（|FOV 失配|
    再 case_id）裁决，不再依赖 `cases_for_scenario`/索引文件顺序——库顺序
    置换后输出序必须逐位相同（"输入集合相同即复现"，CODE V 真机对象不随
    库文件重排漂移）。三颗 extras 同 EFL（band/score 全 tie）：失配 1° 的
    X-ALPHA，失配 2° 的 X-BETA/X-GAMMA（仅 case_id 可分）。"""
    base = _real_case_with_zmx()
    target_efl = 4.0
    seat_a = _efl_fov_variant(base, "SEAT-A", efl_mm=target_efl / 0.90, fov_deg=75.0)  # 失配 3
    seat_b = _efl_fov_variant(base, "SEAT-B", efl_mm=target_efl / 0.88, fov_deg=75.0)
    x_alpha = _efl_fov_variant(base, "X-ALPHA", efl_mm=target_efl / 0.98, fov_deg=77.0)
    x_beta = _efl_fov_variant(base, "X-BETA", efl_mm=target_efl / 0.98, fov_deg=76.0)
    x_gamma = _efl_fov_variant(base, "X-GAMMA", efl_mm=target_efl / 0.98, fov_deg=76.0)

    pool = [seat_a, seat_b, x_alpha, x_beta, x_gamma]
    primary = [seat_a, seat_b]  # 席位失配 3°,3° → cap=3°，三颗 extras 全部可召回
    monkeypatch.setattr(
        generators_module,
        "rank_seeds",
        lambda cases, **kwargs: SimpleNamespace(ranked_cases=primary),  # noqa: ARG005
    )
    spec = TargetSpec(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=target_efl,
        fov_deg=78.0,
        fnum=base.paraxial.f_number,
    )

    orders: list[list[str]] = []
    permutations = [pool, list(reversed(pool)), [x_gamma, x_alpha, seat_b, x_beta, seat_a]]
    for permuted in permutations:
        monkeypatch.setattr(
            generators_module,
            "cases_for_scenario",
            lambda scenario, p=permuted: p,  # noqa: ARG005
        )
        scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
        orders.append([c.metadata.case_id for c, _ in scored if c.metadata is not None])

    assert orders[0] == orders[1] == orders[2]
    # 显式键的期望序：三颗 lt5 extras（失配 1° < 2°，2° tie 按 case_id）在前，
    # 两颗 5to15 席位 seed（score 10 < 12）在后。
    assert orders[0] == ["X-ALPHA", "X-BETA", "X-GAMMA", "SEAT-A", "SEAT-B"]


# ---------------------------------------------------------------------------
# `_rank_seeds_by_target_match` — stage 1b 甜区召回补齐端到端（真实库反例
# 锚，PR#60 `test_sweet_zone_coverage.py::
# test_efl_band_material_real_library_counterexample_anchors` 同源反例，
# 逐点核验用真实 `TargetConvergedGenerator._rank_seeds_by_target_match`
# 确认「改后必须被选中」，而不仅是 PR#60 那条测试的"材料存在性"弱断言）
# ---------------------------------------------------------------------------


def test_rank_seeds_by_target_match_recovers_real_wide_anchor_excluded_from_stage1_top_k():
    """真库反例（`.planning/loop/mode3-funnel-tuning-report.md` 逐点核验）：
    wide target EFL=5.2mm/FOV=61.5° 时，`US-11719917-B2-e6`
    （原生 EFL≈5.364mm，ΔEFL≈-3.06%，band=lt5）在 stage 1 的 FOV 近邻
    top-10 里排不进（sanity 断言验证这一点，否则本测试没有意义）——stage
    1b 甜区召回补齐后必须成为 `_rank_seeds_by_target_match` 的第一名。"""
    pool = [
        c
        for c in load_case_library()
        if c.metadata is not None
        and c.metadata.scenario in _candidate_scenarios(Scenario.SMARTPHONE_WIDE)
        and (ZMX_AMMO_DIR / c.metadata.source_zmx).is_file()
    ]
    target_efl, target_fov, target_fnum = 5.2, 61.5, 2.2

    ranking = rank_seeds(pool, efl_mm=target_efl, fov_deg=target_fov, fnum=target_fnum)
    primary_ids = {c.metadata.case_id for c in ranking.ranked_cases[:10] if c.metadata is not None}
    assert "US-11719917-B2-e6" not in primary_ids  # sanity: 真是漏斗排除，非已在 primary

    spec = TargetSpec(
        scenario=Scenario.SMARTPHONE_WIDE, efl_mm=target_efl, fov_deg=target_fov, fnum=target_fnum
    )
    scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
    assert scored[0][0].metadata is not None
    assert scored[0][0].metadata.case_id == "US-11719917-B2-e6"


def _telephoto_narrowest_in_domain_fov_deg(target_efl_mm: float) -> float:
    """本场景下 target EFL 对应的**最窄合法全视场**，由产品自己的闸导出。

    `SCENARIO_BOUNDS` 逐轴独立判定，`fov_deg_min=15.0` 是**全轴**下界，不是
    "这个 EFL 下的"下界：视场与焦距不独立，`imh = efl·tan(fov/2)`。所以在
    给定 EFL 上真正咬合的下边界是**像高下限**，不是 `fov_deg_min` ——
    EFL=11.5mm 时 `fov_deg_min` 对应像高 1.54mm，被 `image_height_mm_min=2.5`
    拒收（本文件同名回归测试 `test_..._target_is_in_domain` 钉住这一点）。

    2026-07-29 `fov_deg` 重锚（半视场 → 全视场）之后这条推导才有必要：重锚
    前本测试的 target 15.3° 是按**半视场**写的（= 全视场 30.6°），语料重锚
    了、target 没跟着重锚，于是它变成了一条产品自己不接的单。
    """
    bounds = SCENARIO_BOUNDS[Scenario.SMARTPHONE_TELEPHOTO]
    return math.degrees(2.0 * math.atan(bounds.image_height_mm_min / target_efl_mm))


def test_rank_seeds_by_target_match_recovers_real_telephoto_anchor_excluded_from_stage1_top_k():
    """真库反例：tele target EFL=11.5mm、FOV 取该 EFL 下**最窄的合法全视场**
    （≈24.53°，由 `image_height_mm_min` 导出，见
    `_telephoto_narrowest_in_domain_fov_deg`）时，`US-20210364737-A1-e8`
    （原生 EFL≈12.012mm，ΔEFL≈-4.26%，band=lt5）被 stage 1 top-10 挡在外面，
    stage 1b 补齐后必须夺回第一名。

    target 的 FOV **不是钉住锚点自己的视场**（锚点 24.633°，target 24.530°）
    ——它由产品闸 + target EFL 独立导出，锚点恰好落在这条边界内侧是被测出来
    的结果，不是被写进去的前提。原始 docstring 的意图（"贴近场景 FOV 下界，
    仍是合法客户请求"）在重锚后的表达就是这条边界。

    实测（2026-07-30）：该 target 下 rank 1 = 本锚点、band=lt5、score=4.260，
    且 24.53–27° 区间内结论不变；旧的 15.3° target 下 rank 1 是
    `US-12571987-B2-e5`（band=**gt30**、score=35.13，EFL 差 54%）——不是权重
    回归，是 target 自己过期了，详见
    `.planning/evidence/seed-routing-weight-sensitivity-2026-07-30.md`。
    """
    pool = [
        c
        for c in load_case_library()
        if c.metadata is not None
        and c.metadata.scenario in _candidate_scenarios(Scenario.SMARTPHONE_TELEPHOTO)
        and (ZMX_AMMO_DIR / c.metadata.source_zmx).is_file()
    ]
    target_efl, target_fnum = 11.5, 2.2
    target_fov = _telephoto_narrowest_in_domain_fov_deg(target_efl)

    ranking = rank_seeds(pool, efl_mm=target_efl, fov_deg=target_fov, fnum=target_fnum)
    primary_ids = {c.metadata.case_id for c in ranking.ranked_cases[:10] if c.metadata is not None}
    assert "US-20210364737-A1-e8" not in primary_ids  # sanity: 真是漏斗排除

    spec = TargetSpec(
        scenario=Scenario.SMARTPHONE_TELEPHOTO,
        efl_mm=target_efl,
        fov_deg=target_fov,
        fnum=target_fnum,
    )
    scored = TargetConvergedGenerator._rank_seeds_by_target_match(spec)
    assert scored[0][0].metadata is not None
    assert scored[0][0].metadata.case_id == "US-20210364737-A1-e8"


def test_telephoto_anchor_target_is_in_domain_but_the_stale_one_is_not():
    """钉住上一条测试改 target 的**理由**，不只是改后的数字。

    `validate_scenario_params` 逐轴独立判定，从不校验 `imh ≈ efl·tan(fov/2)`
    ——所以旧 target（EFL 11.5 / FOV 15.3）只要不报像高就能过闸，一旦把它自己
    蕴含的像高报上去（1.5446mm）就会被产品自己拒收。这条测试保证：以后谁再
    动 `SCENARIO_BOUNDS` 或再翻一次视场约定，"target 是合法客户请求"这句话
    会被机器复核，而不是留在 docstring 里靠人记得。
    """
    target_efl = 11.5
    stale_fov = 15.3  # 重锚前按半视场写的 target，重锚后按全视场读
    in_domain_fov = _telephoto_narrowest_in_domain_fov_deg(target_efl)

    def implied_image_height_mm(fov_deg: float) -> float:
        return target_efl * math.tan(math.radians(fov_deg / 2.0))

    # 旧 target 蕴含的像高在域外——它从来不是"合法客户请求"，只是没被问到像高。
    with pytest.raises(ParameterGuardError):
        validate_scenario_params(
            Scenario.SMARTPHONE_TELEPHOTO,
            efl_mm=target_efl,
            f_number=2.2,
            fov_deg=stale_fov,
            image_height_mm=implied_image_height_mm(stale_fov),
            n_elements=7,
        )

    # 新 target 蕴含的像高恰好落在像高下限上，逐轴闸全过。
    bounds = SCENARIO_BOUNDS[Scenario.SMARTPHONE_TELEPHOTO]
    assert implied_image_height_mm(in_domain_fov) == pytest.approx(bounds.image_height_mm_min)
    assert bounds.fov_deg_min <= in_domain_fov <= bounds.fov_deg_max
    validate_scenario_params(
        Scenario.SMARTPHONE_TELEPHOTO,
        efl_mm=target_efl,
        f_number=2.2,
        fov_deg=in_domain_fov,
        image_height_mm=implied_image_height_mm(in_domain_fov),
        n_elements=7,
    )


def test_rank_seeds_by_target_match_does_not_force_in_genuinely_far_fov_ultrawide_anchor():
    """诚实留痕（非缺陷）：PR#60 存在性扫描给出的第三个反例
    `US-12210213-B2-e3`（ultrawide target EFL=3.2mm，原生 FOV≈103.6°）逐点
    核验（`.planning/loop/mode3-funnel-tuning-report.md` §ultrawide 反例
    核验）显示这**不是**一个 stage-1-宽度排除案例：目标 FOV 与其原生 FOV
    足够接近时（fov>=98.5°）它本来就在 stage 1 top-10 里、稳居第一；目标
    FOV 明显偏远时（fov<=98.0°，失配 >5.6°）它的 |FOV 失配| 超出该 target
    下 primary 池自身的自适应上限，`_fov_bounded_efl_close_extras`
    正确地不把它拉进候选池——两者之间不存在"排除但可召回"的中间地带（细
    粒度扫描确认过渡宽度为 0）。本测试锁定这个边界行为：target_fov=98.0
    （刚好在自适应上限外）时它必须不出现在候选池里，target_fov=98.5
    （刚好在自适应上限内/已在 primary）时它必须是第一名——防止未来有人
    "修复"成强行拉近它反而破坏了自适应上限本身的不变量。"""
    target_efl, target_fnum = 3.2, 2.1
    anchor_id = "US-12210213-B2-e3"

    # 2026-07-30: the boundary moved by about one degree when `fov_deg` was re-anchored
    # from half to full angle. It is a *recalibration*, not a regression -- rescanned and
    # the structure this test exists to protect is intact and still sharp:
    #
    #     target fov 98.0 -> anchor EXCLUDED     98.5 -> anchor EXCLUDED
    #     target fov 99.5 -> anchor RANK 1      100.5..104.5 -> anchor RANK 1
    #
    # Still no "excluded but recoverable" middle ground, and the anchor is still never
    # forced in below the adaptive cap. The cap tightened because 253 of 442 cases had
    # stored a half angle: with the pool's angles corrected, the primary pool near this
    # target is tighter, so the adaptive cap derived from its spread is tighter too, and a
    # 5.1-degree mismatch now falls outside it.
    spec_far = TargetSpec(
        scenario=Scenario.SMARTPHONE_ULTRAWIDE, efl_mm=target_efl, fov_deg=98.5, fnum=target_fnum
    )
    scored_far = TargetConvergedGenerator._rank_seeds_by_target_match(spec_far)
    far_ids = {c.metadata.case_id for c, _ in scored_far if c.metadata is not None}
    assert anchor_id not in far_ids  # 自适应上限正确拒绝了它——不是漏斗缺陷

    # One degree lower must still reject it: the invariant is "never forced in", so the
    # rejection has to hold on the whole far side, not only at the boundary.
    spec_farther = TargetSpec(
        scenario=Scenario.SMARTPHONE_ULTRAWIDE, efl_mm=target_efl, fov_deg=98.0, fnum=target_fnum
    )
    farther_ids = {
        c.metadata.case_id
        for c, _ in TargetConvergedGenerator._rank_seeds_by_target_match(spec_farther)
        if c.metadata is not None
    }
    assert anchor_id not in farther_ids

    spec_near = TargetSpec(
        scenario=Scenario.SMARTPHONE_ULTRAWIDE, efl_mm=target_efl, fov_deg=99.5, fnum=target_fnum
    )
    scored_near = TargetConvergedGenerator._rank_seeds_by_target_match(spec_near)
    assert scored_near[0][0].metadata is not None
    assert scored_near[0][0].metadata.case_id == anchor_id


def test_candidate_for_seed_notes_flag_fov_unfiltered_selection_when_fov_unconstrained(
    tmp_path: Path, monkeypatch
):
    """`spec.fov_deg is None` 时诚实降级注记：generation_notes 必须出现"未做
    FOV 近邻过滤"字样，不能静默；`fov_deg` 有值时不应出现这条注记。见
    `_mode3_generation_notes` 的 `fov_prefiltered` 参数。"""
    seed = _real_case_with_zmx()
    assert seed.metadata is not None

    unconstrained_zmx = tmp_path / f"{seed.metadata.case_id}_target3.797_optimized.zmx"
    unconstrained_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(unconstrained_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )
    spec_unconstrained = TargetSpec(
        scenario=seed.metadata.scenario,
        efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum=seed.paraxial.f_number,
    )
    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed, match=_fake_match(), spec=spec_unconstrained, work_dir=tmp_path / "work-a"
    )
    assert candidate is not None
    assert any("未做 FOV 近邻过滤" in note for note in candidate.generation_notes)

    constrained_zmx = tmp_path / f"{seed.metadata.case_id}_target3.797_optimized2.zmx"
    constrained_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(constrained_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )
    spec_constrained = TargetSpec(
        scenario=seed.metadata.scenario,
        efl_mm=seed.paraxial.effective_focal_length_mm,
        fov_deg=seed.metadata.fov_deg,
        fnum=seed.paraxial.f_number,
    )
    candidate_constrained = TargetConvergedGenerator._candidate_for_seed(
        seed=seed, match=_fake_match(), spec=spec_constrained, work_dir=tmp_path / "work-b"
    )
    assert candidate_constrained is not None
    assert not any("未做 FOV 近邻过滤" in note for note in candidate_constrained.generation_notes)


# ---------------------------------------------------------------------------
# `_candidate_for_seed` — unit-level (mocked CODE V, real Optiland payload build)
# ---------------------------------------------------------------------------


def test_candidate_for_seed_returns_none_on_codev_batch_error(tmp_path: Path, monkeypatch):
    seed = _real_case_with_zmx()
    assert seed.metadata is not None

    def _boom(**kwargs):  # noqa: ANN003
        raise CodeVBatchError("timeout", "mock CODE V timeout")

    monkeypatch.setattr(generators_module, "run_codev_target_fno_ladder", _boom)
    result = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(scenario=seed.metadata.scenario, efl_mm=3.797, fnum=2.3),
        work_dir=tmp_path / "work",
    )
    assert result is None


def test_candidate_for_seed_returns_none_when_no_preferred_config(tmp_path: Path, monkeypatch):
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: {  # noqa: ANN003
            "preferred": None,
            "preferred_reason": "两配置均报 CodeVBatchError",
            "configs": {
                "asphere": {"error": {"kind": "timeout"}},
                "both": {"error": {"kind": "timeout"}},
            },
            "provenance": {},
        },
    )
    result = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(scenario=seed.metadata.scenario, efl_mm=3.797, fnum=2.3),
        work_dir=tmp_path / "work",
    )
    assert result is None


def test_candidate_for_seed_returns_none_when_zmx_rebuild_unavailable(tmp_path: Path, monkeypatch):
    """`optimized_zmx_path` 为 None（如 H/J 系数非零，zmx_writer fail-open）
    → 该 seed 不产候选，不用假数据填 payload。"""
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(optimized_zmx_path=None),  # noqa: ANN003
    )
    result = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(scenario=seed.metadata.scenario, efl_mm=3.797, fnum=2.3),
        work_dir=tmp_path / "work",
    )
    assert result is None


def test_candidate_for_seed_payload_build_failure_is_fail_closed(tmp_path: Path, monkeypatch):
    """`load_normalized_zmx`/`build_sample_from_optic` 炸（模拟 even_asphere
    数值异常等）→ fail closed，不产候选，不炸调用方。"""
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    bogus_zmx = tmp_path / "not-a-real-zmx.zmx"
    bogus_zmx.write_text("this is not valid ZMX content", encoding="ascii")
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(bogus_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )
    result = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(scenario=seed.metadata.scenario, efl_mm=3.797, fnum=2.3),
        work_dir=tmp_path / "work",
    )
    assert result is None


def test_candidate_for_seed_success_path_produces_target_converged_candidate(
    tmp_path: Path, monkeypatch
):
    """Success path: mocks only the CODE V layer (`run_codev_target_fno_ladder`);
    the optimized-ZMX rebuild pipeline (`load_normalized_zmx` +
    `build_sample_from_optic`) runs for real against an existing on-disk case
    ZMX's *content*, copied to a filename that does not collide with anything
    under `ZMX_AMMO_DIR` — mirroring the real generator's actual optimized-ZMX
    filenames (`{stem}_target{efl}..._optimized.zmx`, never a bare ammo-dir
    name). Since P17-4 (loop3 遗留#4 closure) that non-colliding location is
    exactly what proves the RI wiring: the ammo-dir lookup for this filename
    misses, so the *only* way the RI assertions below can see real values is
    `_candidate_for_seed` explicitly handing `optimized_zmx_path` to
    `compute_relative_illumination(zmx_path=...)`."""
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    stand_in_zmx = tmp_path / f"{seed.metadata.case_id}_target3.797_optimized.zmx"
    stand_in_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(stand_in_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )
    spec = TargetSpec(
        scenario=seed.metadata.scenario,
        efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum=seed.paraxial.f_number,
    )
    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed, match=_fake_match(), spec=spec, work_dir=tmp_path / "work"
    )

    assert candidate is not None
    assert candidate.mode is GenerationMode.TARGET_CONVERGED
    assert candidate.source_case_id == seed.metadata.case_id
    assert candidate.candidate_id == f"{seed.metadata.case_id}::target-converged-stageb-ladder"
    assert candidate.payload is not None
    # CODE V 真机数字如实摘入 codev_post_aut（诊断 side-channel，非打分输入）
    extras = candidate.optical_extras
    assert extras.codev_post_aut is not None
    assert extras.codev_post_aut["post_aut.max_rms_spot_diameter_um"] == pytest.approx(12.3)
    assert extras.codev_post_aut["err_f_ratio"] == pytest.approx(0.09)
    assert extras.codev_post_aut["aut_termination"] == "normal_completion"
    assert candidate.fnum_ladder_evidence is not None
    assert candidate.fnum_ladder_achieved is True
    assert candidate.fnum_ladder_evidence.accepted_final is not None
    assert candidate.fnum_ladder_evidence.accepted_final.optimized_zmx_path == str(stand_in_zmx)
    assert candidate.payload.metadata is not None
    assert candidate.payload.metadata.source_zmx == stand_in_zmx.name
    fnum_row = next(
        dev for dev in score_candidate(candidate, spec).target_deviations if dev.field == "fnum"
    )
    assert fnum_row.achieved == candidate.payload.paraxial.f_number
    # P17-4（loop3 遗留#4 闭合）：RI 用优化后 ZMX 的显式路径实算——不再因
    # "临时目录不在 ZMX_AMMO_DIR 下" 而结构性 miss。轴上场 RI 恒 1.0（cos^4(0)
    # 归一），离轴至少一场 < 1.0（真实 cos^4 衰减，非编造常数）。
    assert extras.ri_by_field is not None
    available = {k: m for k, m in extras.ri_by_field.items() if m.status == "available"}
    assert available, "RI must genuinely compute from the explicit optimized-ZMX path"
    assert extras.ri_by_field["0.0"].status == "available"
    assert extras.ri_by_field["0.0"].value == pytest.approx(1.0)
    assert any(m.value is not None and m.value < 1.0 for m in available.values())
    joined_notes = " ".join(candidate.generation_notes)
    assert "band=lt5" in joined_notes
    assert "preferred" in joined_notes
    # 注记不再宣称"恒 unavailable"（那会是对新行为的撒谎），改为如实注明
    # 显式路径实算 + fail-closed。
    assert "恒 unavailable" not in joined_notes
    assert "Stage C 场重建未落地" not in joined_notes
    assert "Stage C RIH 重建与真机 receipt 验证 achieved" in joined_notes
    assert "FOV 只允许由同源 EFL/IMH 派生或实测" in joined_notes
    assert any("P17-4 接线" in note for note in candidate.generation_notes)


def test_target_converged_generator_injected_ladder_runner_keeps_negative_evidence(
    tmp_path: Path,
):
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    stand_in_zmx = tmp_path / "negative-last-measured.zmx"
    stand_in_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    calls: list[dict[str, object]] = []

    def runner(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        return _fake_ladder_result(
            optimized_zmx_path=str(stand_in_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
            target_achieved=False,
        )

    generator = TargetConvergedGenerator(ladder_runner=runner)
    spec = TargetSpec(
        scenario=seed.metadata.scenario,
        efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum=seed.paraxial.f_number,
    )
    candidate = generator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=spec,
        work_dir=tmp_path / "work",
        ladder_runner=generator.ladder_runner,
    )

    assert candidate is not None
    assert calls and calls[0]["fnum_target"] == pytest.approx(seed.paraxial.f_number)
    assert calls[0]["ray_retry_vig_ladder"] == generators_module.RAY_RETRY_VIG_LADDER
    assert candidate.fnum_ladder_evidence is not None
    assert candidate.fnum_ladder_evidence.target_achieved is False
    assert candidate.fnum_ladder_evidence.accepted_final is None
    assert candidate.fnum_ladder_achieved is False


def test_candidate_for_seed_rejects_ladder_claim_disagrees_with_loaded_payload(
    tmp_path: Path, monkeypatch
):
    """Review regression: a copied native seed cannot wear fake 3.797/2.3 evidence."""
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    assert (
        abs(seed.paraxial.effective_focal_length_mm - 3.797) / 3.797 * 100
        >= generators_module.EFL_TARGET_TOLERANCE_PCT
        or abs(seed.paraxial.f_number - 2.3) / 2.3 * 100 > 8.0
    )
    stand_in_zmx = tmp_path / "native-seed-falsely-labelled-optimized.zmx"
    stand_in_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(optimized_zmx_path=str(stand_in_zmx)),  # noqa: ARG005
    )

    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(scenario=seed.metadata.scenario, efl_mm=3.797, fnum=2.3),
        work_dir=tmp_path / "work",
    )
    assert candidate is None


def test_candidate_for_seed_rejects_payload_fnum_disagrees_with_accepted_measurement(
    tmp_path: Path, monkeypatch
):
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    fake_target_fnum = seed.paraxial.f_number / 2.0
    stand_in_zmx = tmp_path / "native-seed-falsely-labelled-fnum.zmx"
    stand_in_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(stand_in_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )

    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(
            scenario=seed.metadata.scenario,
            efl_mm=seed.paraxial.effective_focal_length_mm,
            fnum=fake_target_fnum,
        ),
        work_dir=tmp_path / "work",
    )
    assert candidate is None


def test_candidate_for_seed_persists_optimized_zmx_bytes(tmp_path: Path, monkeypatch):
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    source = tmp_path / "ephemeral.zmx"
    expected = (ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes()
    source.write_bytes(expected)
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(source),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )
    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(
            scenario=seed.metadata.scenario,
            efl_mm=seed.paraxial.effective_focal_length_mm,
            fnum=seed.paraxial.f_number,
        ),
        work_dir=tmp_path / "work",
        artifact_dir=tmp_path / "artifacts",
        run_index=1,
    )
    assert candidate is not None
    persisted = Path(candidate.optimized_zmx_path or "")
    assert persisted.read_bytes() == expected
    assert (
        persisted
        == tmp_path
        / "artifacts"
        / "candidates"
        / (f"{seed.metadata.case_id}--stageb-ladder--run-1")
        / "candidate.zmx"
    )
    assert candidate.artifact_warnings == []


@pytest.mark.parametrize(
    ("defect", "message"),
    [
        ("missing", "missing or contradictory"),
        ("unknown", "missing or contradictory"),
        ("contradictory", "missing or contradictory"),
        ("hash", "record bytes changed"),
    ],
)
def test_production_stageb_cache_binding_fails_closed(
    tmp_path: Path, defect: str, message: str
) -> None:
    record = tmp_path / "cache-record.json"
    raw_result = tmp_path / "raw-ladder-result.json"
    record.write_bytes(b"retained cache record")
    raw_result.write_bytes(b"retained raw ladder")
    entry = {
        "cache_scope": "pre-run-bound",
        "pre_run_bound": True,
        "cache_record_path": str(record.resolve()),
        "cache_record_sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
        "raw_ladder_result_path": str(raw_result.resolve()),
        "raw_ladder_result_sha256": hashlib.sha256(raw_result.read_bytes()).hexdigest(),
    }
    if defect == "missing":
        entry.pop("cache_scope")
    elif defect == "unknown":
        entry["cache_scope"] = "invented"
    elif defect == "contradictory":
        entry["pre_run_bound"] = False
    else:
        entry["cache_record_sha256"] = "0" * 64
    raw = json.dumps({"accepted": [entry]}, allow_nan=False).encode()

    with pytest.raises(ValueError, match=message):
        generators_module._production_stageb_cache_binding(raw)


def test_candidate_for_seed_production_stagec_uses_accepted_bytes_for_attested_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.engines import stagec_attested as attested_module
    from app.core.engines import stagec_field as stagec_field_module
    from app.core.engines.stagec_attested import (
        StageCAttestedEvidence,
        StageCAttestedField,
    )
    from app.core.engines.stagec_field import validate_reconstructed_field_artifact
    from app.core.orchestration import candidate as candidate_module

    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    accepted = tmp_path / "accepted.zmx"
    accepted.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    result = _fake_ladder_result(
        optimized_zmx_path=str(accepted),
        target_efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum_target=seed.paraxial.f_number,
    )
    result["source_zmx"] = seed.metadata.source_zmx
    fake_codev = tmp_path / "codev.exe"
    fake_codev.write_bytes(b"fixture CODE V")
    monkeypatch.setattr(generators_module, "DEFAULT_CODEV_EXECUTABLE", fake_codev)
    fake_macro = tmp_path / "zemaxos_to_cv.seq"
    fake_macro.write_bytes(b"fixture official macro")
    monkeypatch.setattr(attested_module, "_TRUSTED_CODEV_EXECUTABLE", fake_codev)
    monkeypatch.setattr(attested_module, "_OFFICIAL_ZEMAX_MACRO", fake_macro)
    real_reconstruct = stagec_field_module.reconstruct_image_fields

    def reconstruct_fixture(**kwargs: object):
        source_zmx = Path(str(kwargs["source_zmx"]))
        angular = tmp_path / "angular-fixture.zmx"
        source_text = source_zmx.read_text(encoding="utf-16")
        assert "FTYP 3 " in source_text
        angular.write_text(
            source_text.replace("FTYP 3 ", "FTYP 0 ", 1),
            encoding="utf-16",
        )
        reconstructed = real_reconstruct(
            source_zmx=angular,
            output_zmx=Path(str(kwargs["output_zmx"])),
            resolved_target=kwargs["resolved_target"],
            allow_nonzero_vignetting_for_machine=True,
        )
        source_sha = hashlib.sha256(source_zmx.read_bytes()).hexdigest()
        return reconstructed.model_copy(
            update={
                "source_path": str(source_zmx.resolve()),
                "source_sha256_before": source_sha,
                "source_sha256_after": source_sha,
            }
        )

    monkeypatch.setattr(generators_module, "reconstruct_image_fields", reconstruct_fixture)
    restored: StageCAttestedEvidence | None = None

    def fake_stagec_runner(**kwargs: object) -> Path:
        nonlocal restored
        with pytest.raises(BatchRunnerLockHeldError), batch_runner_lock(tmp_path / "p18-archive"):
            raise AssertionError("the production P18 window unexpectedly reopened")
        plan = json.loads(Path(str(kwargs["execution_plan"])).read_text(encoding="utf-8"))
        assert set(plan) == {
            "schema_id",
            "matrix_id",
            "stageb_manifest",
            "stageb_manifest_sha256",
            "seed_count",
            "cell_count",
            "repeat_count",
            "expected_run_count",
            "stageb_cache_scope_counts",
            "all_inputs_pre_run_bound",
            "retrospective_seed_ids",
            "cells",
            "expert_verdict",
        }
        assert plan["schema_id"] == "atelier-stagec-production-execution-plan-v1"
        assert (plan["seed_count"], plan["cell_count"], plan["repeat_count"]) == (1, 1, 1)
        assert plan["expected_run_count"] == 1
        assert plan["stageb_cache_scope_counts"] == {"pre-run-bound": 1}
        assert plan["all_inputs_pre_run_bound"] is True
        assert plan["retrospective_seed_ids"] == []
        authority = Path(str(kwargs["stageb_manifest"]))
        assert plan["stageb_manifest"] == str(authority.resolve())
        assert plan["stageb_manifest_sha256"] == hashlib.sha256(authority.read_bytes()).hexdigest()
        reconstruction = plan["cells"][0]["reconstruction"]
        assert plan["cells"][0]["cache_scope"] == "pre-run-bound"
        assert plan["cells"][0]["pre_run_bound"] is True
        assert len(plan["cells"][0]["cache_record_sha256"]) == 64
        assert Path(plan["cells"][0]["cache_record_path"]).is_file()
        assert len(plan["cells"][0]["raw_ladder_result_sha256"]) == 64
        assert Path(plan["cells"][0]["raw_ladder_result_path"]).is_file()
        output = Path(reconstruction["output_path"])
        parsed = validate_reconstructed_field_artifact(
            output,
            expected_num_fields=reconstruction["num_fields"],
            expected_fractions=tuple(reconstruction["normalized_fractions"]),
            target_image_height_mm=reconstruction["target_image_height_mm"],
            vignetting_mode="finite-nonzoom",
        )
        expected_profiles = tuple(
            (vuy, vly, vux, vlx)
            for vuy, vly, vux, vlx in zip(
                parsed.vuy, parsed.vly, parsed.vux, parsed.vlx, strict=True
            )
        )
        fields = tuple(
            StageCAttestedField(
                field_index=index,
                sample_id=f"field-{index:04d}",
                normalized_fraction=fraction,
                definition_x_ri_mm=0.0,
                definition_y_ri_mm=fraction * reconstruction["target_image_height_mm"],
                rsi_actual_x_mm=0.0,
                rsi_actual_y_mm=fraction * reconstruction["target_image_height_mm"],
                rsi_direction_l=0.0,
                rsi_direction_m=0.0,
                rsi_direction_n=1.0,
                rayrsi_return_code=0,
                rer=0,
                bls=0,
                spotdata_return_code=0,
                rms_spot_diameter_um=10.0,
                rmswe_return_value=1.0,
                rms_wfe_waves=0.2,
                vuy=expected_profiles[index - 1][0],
                vly=expected_profiles[index - 1][1],
                vux=expected_profiles[index - 1][2],
                vlx=expected_profiles[index - 1][3],
                ray_classification="valid",
            )
            for index, fraction in enumerate(reconstruction["normalized_fractions"], start=1)
        )
        package = tmp_path / "trusted-package"
        restored = StageCAttestedEvidence.model_construct(
            schema_id="atelier-stagec-attested-evidence-v3",
            evidence_kind="attested-machine",
            run_id="production-test-run",
            matrix_id=kwargs["matrix_id"],
            cell_id=f"{seed.metadata.case_id}--production-target",
            seed_id=seed.metadata.case_id,
            arm="production-target",
            repeat_index=1,
            receipt_sha256="1" * 64,
            execution_plan_sha256=hashlib.sha256(
                Path(str(kwargs["execution_plan"])).read_bytes()
            ).hexdigest(),
            stageb_cache_scope=plan["cells"][0]["cache_scope"],
            stageb_pre_run_bound=plan["cells"][0]["pre_run_bound"],
            stageb_cache_record_sha256=plan["cells"][0]["cache_record_sha256"],
            stageb_raw_ladder_result_sha256=plan["cells"][0]["raw_ladder_result_sha256"],
            package_path=str(package),
            source_zmx_sha256=hashlib.sha256(
                Path(str(result["accepted_final"]["optimized_zmx_path"])).read_bytes()
            ).hexdigest(),
            reconstructed_zmx_sha256=parsed.sha256,
            target_efl_mm=reconstruction["target_efl_mm"],
            target_image_height_mm=reconstruction["target_image_height_mm"],
            normalized_fractions=tuple(reconstruction["normalized_fractions"]),
            expected_vignetting_profile=expected_profiles,
            measured_efl_mm=reconstruction["target_efl_mm"],
            fields=fields,
            process_returncode_observed=0,
            process_duration_seconds=0.1,
            artifact_bindings_valid=True,
            receipt_attested=True,
            field_type="RIH",
            expert_verdict=None,
        )
        return package / "post-run-receipt.json"

    def fake_restore(_path: Path) -> StageCAttestedEvidence:
        assert restored is not None
        return restored

    from app.core.engines import stageb_authority as authority_module

    monkeypatch.setattr(authority_module, "OFFICIAL_EXECUTABLE", fake_codev)
    monkeypatch.setattr(authority_module, "OFFICIAL_MACRO", fake_macro)
    monkeypatch.setattr(
        authority_module,
        "TRUSTED_CODEV_SHA256",
        hashlib.sha256(fake_codev.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(authority_module, "TRUSTED_CODEV_SIZE_BYTES", fake_codev.stat().st_size)
    monkeypatch.setattr(
        authority_module,
        "TRUSTED_MACRO_SHA256",
        hashlib.sha256(fake_macro.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(authority_module, "TRUSTED_CODEV_FILE_VERSION", "11.5-test")

    def fake_authority_runner(**kwargs: object) -> dict[str, object]:
        payload = json.loads(json.dumps(result))
        payload["source_zmx"] = Path(str(kwargs["source_zmx"])).name
        for key in (
            "stage",
            "target_efl_mm",
            "fnum_target",
            "rung_count",
            "fnum_tolerance_pct",
            "num_fields",
            "extra_dof",
        ):
            payload[key] = kwargs[key]
        payload["vig_ladder"] = list(kwargs["vig_ladder"])
        payload["ray_retry_vig_ladder"] = list(kwargs["ray_retry_vig_ladder"])
        return payload

    def fake_open_authority(config: object):
        assert isinstance(config, authority_module.StageBAuthorityConfig)
        assert config.executable == fake_codev.resolve()
        monkeypatch.setattr(authority_module, "P18_GLOBAL_WINDOW_ROOT", config.p18_lock_root)
        test_config = authority_module.StageBAuthorityConfig(
            # Keep the Windows pytest fixture below MAX_PATH; production path
            # placement is asserted separately from the retained manifest.
            authority_root=tmp_path / "authority",
            output_lock_root=config.output_lock_root,
            p18_lock_root=config.p18_lock_root,
            executable=fake_codev,
            official_macro=fake_macro,
            _codev_version_for_tests="11.5-test",
        )
        return authority_module._open_stageb_authority_for_tests(  # noqa: SLF001
            test_config, fake_authority_runner
        )

    monkeypatch.setattr(generators_module, "open_stageb_authority", fake_open_authority)
    monkeypatch.setattr(generators_module, "restore_stagec_attested_evidence", fake_restore)
    monkeypatch.setattr(candidate_module, "restore_stagec_attested_evidence", fake_restore)
    spec = TargetSpec(
        scenario=seed.metadata.scenario,
        efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum=seed.paraxial.f_number,
        image_height_mm=2.3,
    )

    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=spec,
        work_dir=tmp_path / "work",
        artifact_dir=tmp_path / "artifacts",
        run_index=1,
        ladder_runner=generators_module.run_codev_target_fno_ladder,
        stagec_runner=fake_stagec_runner,
        stageb_p18_lock_root=tmp_path / "p18-archive",
    )

    assert candidate is not None
    with batch_runner_lock(tmp_path / "p18-archive"):
        pass
    assert candidate.stagec_field_evidence is restored
    assert candidate.stagec_field_evidence.image_height_achieved is True
    assert Path(candidate.optimized_zmx_path or "").name == "candidate-rih.zmx"
    assert candidate.payload.metadata is not None
    assert candidate.payload.metadata.image_height_mm == 2.3


def test_candidate_for_seed_production_stagec_collision_fails_closed(
    tmp_path: Path,
) -> None:
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    source = tmp_path / "accepted.zmx"
    source.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    result = _fake_ladder_result(
        optimized_zmx_path=str(source),
        target_efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum_target=seed.paraxial.f_number,
    )
    collision = (
        tmp_path / "artifacts" / "candidates" / (f"{seed.metadata.case_id}--stageb-ladder--run-1")
    )
    collision.mkdir(parents=True)
    (collision / "candidate.zmx").write_bytes(b"stale-candidate-must-not-be-reused")
    runner_called = False

    def forbidden_runner(**_kwargs: object) -> Path:
        nonlocal runner_called
        runner_called = True
        raise AssertionError("Stage C runner must not see a collided candidate directory")

    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(
            scenario=seed.metadata.scenario,
            efl_mm=seed.paraxial.effective_focal_length_mm,
            fnum=seed.paraxial.f_number,
            image_height_mm=2.3,
        ),
        work_dir=tmp_path / "work",
        artifact_dir=tmp_path / "artifacts",
        run_index=1,
        ladder_runner=lambda **_kwargs: result,
        stagec_runner=forbidden_runner,
        stageb_p18_lock_root=tmp_path / "p18-archive",
    )

    assert candidate is None
    assert runner_called is False
    assert (collision / "candidate.zmx").read_bytes() == b"stale-candidate-must-not-be-reused"
    assert not (collision / "stagec").exists()


def test_candidate_for_seed_persist_collision_records_warning(tmp_path: Path, monkeypatch):
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    source = tmp_path / "ephemeral.zmx"
    source.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(source),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )
    collision = (
        tmp_path / "artifacts" / "candidates" / (f"{seed.metadata.case_id}--stageb-ladder--run-1")
    )
    collision.mkdir(parents=True)
    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed,
        match=_fake_match(),
        spec=TargetSpec(
            scenario=seed.metadata.scenario,
            efl_mm=seed.paraxial.effective_focal_length_mm,
            fnum=seed.paraxial.f_number,
        ),
        work_dir=tmp_path / "work",
        artifact_dir=tmp_path / "artifacts",
    )
    assert candidate is not None
    assert candidate.optimized_zmx_path == str(source)
    assert candidate.artifact_warnings
    assert "fail-closed" in candidate.artifact_warnings[0]


def test_candidate_for_seed_ri_fails_closed_when_optimized_zmx_deleted_before_ri(
    tmp_path: Path, monkeypatch
):
    """RI 接线的 fail-closed 半边：显式路径解析不到（模拟极端竞态/重建产物
    被清掉，payload 构建已完成但 RI 复算时文件没了）→ RI 全 unavailable，
    候选照常产出（RI 缺失不否决候选，与 Mode1 单颗 RI 失败不拖垮整批同则）。

    实现方式：让 `build_sample_from_optic` 一结束就删掉优化 ZMX——通过
    monkeypatch 包装 `load_normalized_zmx` 完成加载后删除文件即可模拟
    "payload 构建成功、RI 复算时文件已不存在" 的窗口。
    """
    seed = _real_case_with_zmx()
    assert seed.metadata is not None
    stand_in_zmx = tmp_path / f"{seed.metadata.case_id}_target3.797_optimized.zmx"
    stand_in_zmx.write_bytes((ZMX_AMMO_DIR / seed.metadata.source_zmx).read_bytes())
    monkeypatch.setattr(
        generators_module,
        "run_codev_target_fno_ladder",
        lambda **kwargs: _fake_ladder_result(
            optimized_zmx_path=str(stand_in_zmx),
            target_efl_mm=kwargs["target_efl_mm"],
            fnum_target=kwargs["fnum_target"],
        ),
    )

    real_load = generators_module.load_normalized_zmx

    def _load_then_delete(path):  # noqa: ANN001
        optic = real_load(path)
        Path(path).unlink()  # file vanishes between payload build and RI compute
        return optic

    monkeypatch.setattr(generators_module, "load_normalized_zmx", _load_then_delete)
    spec = TargetSpec(
        scenario=seed.metadata.scenario,
        efl_mm=seed.paraxial.effective_focal_length_mm,
        fnum=seed.paraxial.f_number,
    )
    candidate = TargetConvergedGenerator._candidate_for_seed(
        seed=seed, match=_fake_match(), spec=spec, work_dir=tmp_path / "work"
    )

    assert candidate is not None  # RI 缺失不否决候选
    assert candidate.optical_extras.ri_by_field is not None
    assert all(m.status == "unavailable" for m in candidate.optical_extras.ri_by_field.values())


# ---------------------------------------------------------------------------
# `_codev_post_aut_snapshot` — 0.0 追迹全失败哨兵归 None（诚实红线）
# 哨兵结案：`codev_optimize._standard_config_rms` docstring（宏累加器 ^max=0
# 起始，全场次追迹失败原样写出 0.0——不是真实零误差）。
# ---------------------------------------------------------------------------


def _sentinel_snapshot_config(**overrides: object) -> dict[str, object]:
    config: dict[str, object] = {
        "post_aut.efl_y_mm": "3.797",
        "post_aut.max_rms_spot_diameter_um": "0.0",
        "post_aut.max_rms_wavefront_error_waves": "0",
        "post_aut.max_distortion_pct": "0.000",
        "post_aut.fno": "2.3",
        "post_aut.maximh_mm": "3.3",
        "efl_target_deviation_pct": "0.0",
        "aut_converged": "0",
        "autovig.edge_used": "0.0",
        "aut_error_trace": {"err_f_ratio": 1.0, "termination": "trace_failed"},
    }
    config.update(overrides)
    return config


def test_codev_post_aut_snapshot_maps_trace_failed_zero_sentinels_to_none():
    snapshot = generators_module._codev_post_aut_snapshot(_sentinel_snapshot_config())
    # 质量三键的 0.0 = 追迹全失败哨兵 → None（web/离线报告渲染 N/A，不是 "0"）
    assert snapshot["post_aut.max_rms_spot_diameter_um"] is None
    assert snapshot["post_aut.max_rms_wavefront_error_waves"] is None
    assert snapshot["post_aut.max_distortion_pct"] is None
    # 0.0 合法的键原样保留（edge_used=0 = 无渐晕裁切；EFL 偏差可以就是 0）
    assert snapshot["autovig.edge_used"] == pytest.approx(0.0)
    assert snapshot["efl_target_deviation_pct"] == pytest.approx(0.0)
    # 非哨兵键不受影响
    assert snapshot["post_aut.efl_y_mm"] == pytest.approx(3.797)
    assert snapshot["post_aut.fno"] == pytest.approx(2.3)
    assert snapshot["post_aut.maximh_mm"] == pytest.approx(3.3)


def test_codev_post_aut_snapshot_sentinel_mapping_is_per_key():
    """真机可见形态：同一快照 distortion=43.86（真实测量）与 rms=0.0（哨兵）
    并存——映射逐键独立，不因一键哨兵抹掉别键的真实数字。"""
    snapshot = generators_module._codev_post_aut_snapshot(
        _sentinel_snapshot_config(**{"post_aut.max_distortion_pct": "43.86"})
    )
    assert snapshot["post_aut.max_rms_spot_diameter_um"] is None
    assert snapshot["post_aut.max_rms_wavefront_error_waves"] is None
    assert snapshot["post_aut.max_distortion_pct"] == pytest.approx(43.86)


def test_codev_post_aut_snapshot_legit_nonzero_quality_values_pass_through():
    snapshot = generators_module._codev_post_aut_snapshot(
        _sentinel_snapshot_config(
            **{
                "post_aut.max_rms_spot_diameter_um": "12.3",
                "post_aut.max_rms_wavefront_error_waves": "0.04",
                "post_aut.max_distortion_pct": "3.1",
            }
        )
    )
    assert snapshot["post_aut.max_rms_spot_diameter_um"] == pytest.approx(12.3)
    assert snapshot["post_aut.max_rms_wavefront_error_waves"] == pytest.approx(0.04)
    assert snapshot["post_aut.max_distortion_pct"] == pytest.approx(3.1)


def test_codev_post_aut_none_renders_na_in_both_report_paths():
    """哨兵归 None 后，两条渲染路径（web candidate_set 页 + 离线 c1 报告）都
    必须把 None 显示为 N/A——资深永远不会看到假 "0"。"""
    from app.main import _fmt_codev_value as web_fmt
    from scripts.c1_orchestrate import _fmt_codev_value as offline_fmt

    assert web_fmt(None) == "N/A"
    assert offline_fmt(None) == "N/A"


# ---------------------------------------------------------------------------
# `_generate` — seed selection + per-seed isolation (§9)
# ---------------------------------------------------------------------------


def test_generate_isolates_single_seed_failure_and_keeps_survivor(monkeypatch, tmp_path: Path):
    """一颗 seed 失败（`_candidate_for_seed` 返回 `None`）不炸整个
    generator——另一颗仍能出候选。"""
    seed_a = load_case_library()[0]
    seed_b = load_case_library()[1]
    assert seed_a.metadata is not None and seed_b.metadata is not None
    survivor = GeneratedCandidate(
        candidate_id="survivor",
        mode=GenerationMode.TARGET_CONVERGED,
        source_case_id=seed_b.metadata.case_id,
        payload=seed_b,
        optical_extras=OpticalExtras(),
        generation_notes=["mock survivor"],
    )

    monkeypatch.setattr(
        generators_module,
        "DEFAULT_CODEV_EXECUTABLE",
        Path(__file__),  # any real file — `.is_file()` True
    )
    monkeypatch.setattr(
        TargetConvergedGenerator,
        "_rank_seeds_by_target_match",
        staticmethod(lambda spec: [(seed_a, _fake_match()), (seed_b, _fake_match())]),
    )

    calls: list[str] = []

    def _fake_candidate_for_seed(*, seed, match, spec, work_dir, **kwargs):  # noqa: ANN001
        calls.append(seed.metadata.case_id)
        if seed is seed_a:
            return None
        return survivor

    monkeypatch.setattr(
        TargetConvergedGenerator, "_candidate_for_seed", staticmethod(_fake_candidate_for_seed)
    )

    spec = TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, efl_mm=3.797, fnum=2.3)
    result = TargetConvergedGenerator().generate(spec, spec, n=4)

    assert len(calls) == 2  # both seeds attempted — first's failure didn't short-circuit
    assert result == [survivor]


def test_generate_caps_seed_count_at_max_regardless_of_n(monkeypatch):
    """真机成本控制：即便 `n` 请求更大，Mode3 每次编排最多真机跑
    `_TARGET_MAX_SEEDS` 颗 seed。"""
    cases = [c for c in load_case_library() if c.metadata is not None][:5]
    assert len(cases) == 5

    monkeypatch.setattr(generators_module, "DEFAULT_CODEV_EXECUTABLE", Path(__file__))
    monkeypatch.setattr(
        TargetConvergedGenerator,
        "_rank_seeds_by_target_match",
        staticmethod(lambda spec: [(c, _fake_match()) for c in cases]),
    )
    attempted: list[str] = []

    def _fake_candidate_for_seed(*, seed, match, spec, work_dir, **kwargs):  # noqa: ANN001
        attempted.append(seed.metadata.case_id)
        return None

    monkeypatch.setattr(
        TargetConvergedGenerator, "_candidate_for_seed", staticmethod(_fake_candidate_for_seed)
    )

    spec = TargetSpec(scenario=Scenario.SMARTPHONE_WIDE, efl_mm=3.797, fnum=2.3)
    TargetConvergedGenerator().generate(spec, spec, n=10)
    assert len(attempted) == generators_module._TARGET_MAX_SEEDS


# ---------------------------------------------------------------------------
# Real CODE V end-to-end (task report requirement — actual machine run,
# `-k real` opt-in, matches the repo's `test_real_*` real-machine convention)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not DEFAULT_CODEV_EXECUTABLE.is_file(),
    reason="real CODE V installation required for the Mode3 end-to-end smoke",
)
@pytest.mark.real_machine
def test_real_target_converged_generator_orchestrate_end_to_end():
    """真机端到端：`orchestrate()` 全 modes 开，target EFL=3.797mm /
    FOV=78deg / F#=2.3（wide 场景，池内实测甜区附近，见
    `.planning/loop/opt3-final-handoff-2026-07-09.md` §三）。如实打印
    Mode3 是否产出候选、banner 状态、provenance——不预设 payload 现算一定
    躲过 even_asphere 溢出风险（该风险的真实表现是本测试要观测的对象，不是
    要断言掉的噪声）。"""
    target = TargetSpec(
        scenario=Scenario.SMARTPHONE_WIDE,
        efl_mm=3.797,
        fov_deg=78.0,
        fnum=2.3,
    )
    result = orchestrate(target, target, n=4)

    print(f"[real e2e] modes_present={sorted(m.value for m in result.modes_present)}")
    print(f"[real e2e] honesty_banner={result.honesty_banner!r}")
    print(f"[real e2e] summary.notes={result.summary.notes}")
    for sc in result.candidates:
        if sc.mode is GenerationMode.TARGET_CONVERGED:
            print(f"[real e2e] TARGET_CONVERGED candidate_id={sc.scorecard.candidate_id}")
            for note in sc.generated.generation_notes:
                print(f"[real e2e]   note: {note}")
            print(f"[real e2e]   codev_post_aut={sc.generated.optical_extras.codev_post_aut}")
            efl_dev = next(d for d in sc.scorecard.target_deviations if d.field == "efl")
            print(
                f"[real e2e]   efl converged={efl_dev.converged_toward_target} "
                f"achieved={efl_dev.achieved} target={efl_dev.target}"
            )

    # Honest assertion set: Mode3 may legitimately produce zero candidates if
    # every selected seed's payload rebuild hits the known even_asphere risk
    # (or CODE V itself times out/errors on this host) — that is itself a
    # valid, fail-closed outcome, not a test failure. What must always hold:
    # `orchestrate` never raises, RETRIEVED still works regardless, and *if*
    # a TARGET_CONVERGED candidate is present, the banner disappears and its
    # EFL deviation is genuinely marked converged with real CODE V numbers
    # attached.
    assert isinstance(result, CandidateSet)
    assert any(sc.mode is GenerationMode.RETRIEVED for sc in result.candidates)
    if GenerationMode.TARGET_CONVERGED in result.modes_present:
        assert result.honesty_banner is None
        tc = next(sc for sc in result.candidates if sc.mode is GenerationMode.TARGET_CONVERGED)
        efl_dev = next(d for d in tc.scorecard.target_deviations if d.field == "efl")
        assert efl_dev.converged_toward_target is True
        assert tc.generated.optical_extras.codev_post_aut is not None
    else:
        print(
            "[real e2e] Mode3 produced 0 candidates this run (all selected seeds "
            "fail-closed, or CODE V unavailable/errored) — see notes above for why"
        )
