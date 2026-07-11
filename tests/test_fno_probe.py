"""Tests for the Phase 15 Stage A/B FNO failure-mode probe (fno_probe.py).

All tests are offline (mock CODE V subprocess or pure-text classifier calls)
per the Stage 1 brief: "targeted 测试绿 + ruff 绿 -> commit"; no real CODE V
invocation happens in this file.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from app.core.engines import codev_batch
from app.core.engines.codev_batch import CodeVBatchError
from app.core.engines.codev_optimize import default_optimize_seed
from app.core.engines.fno_probe import (
    build_fno_probe_sequence,
    classify_fno_listing,
    run_fno_probe,
)

# ---------------------------------------------------------------------------
# Real-evidence .lis fixtures, verbatim from
# .planning/loop/candidates-2026-07-09/US20170045714A1/both/
# atelier_codev_target_A_vig020.lis (lines ~26-30 for the ray-aiming warning,
# ~868-896 for the RAY ERROR: REFL/MISS block) — untouched real CODE V output,
# not synthesized. Real-machine confirmed: 14 REFL + 105 MISS occurrences in
# the full listing; this excerpt carries the first co-occurring block.
# ---------------------------------------------------------------------------

_REAL_TIR_AND_MISS_EXCERPT = """\
    Zemax command LANG ignored
     WARNING - Glass catalog list not used.
     WARNING - Ray aiming not used.
     WARNING - Pupil shift for ray aiming not used.
    Zemax command SDMA ignored

 CYCLE NUMBER 0:

  EFL                    =   3.79700E+00   3.97145E+00   1.744E-01    **

  Weighted Constraints:        target        value        WTC/PTC     contrib
  @ATELIER_LATCOLOR      =   0.00000E+00   1.37721E+00   1.000E-02   1.897E+02
  @ATELIER_RMSSPOT       =   0.00000E+00   9.43415E+00   1.000E-03   8.900E+01

  Constraints added:      EFL (=)                     GL C S4 (<)
                          GL C S12 (<)                Mn CT S1 (>)
 RAY ERROR: MISS 11
 RAY ERROR: REFL 13
 RAY ERROR: REFL 13
  Constraints added:      GL B S6 (<)                 GL B S16 (<)
 RAY ERROR: MISS 14
 RAY ERROR: MISS( 15)  15
  Constraints added:      GL C S6 (<)                 GL C S10 (<)
                          GL A S18 (<)
 RAY ERROR: MISS 14
 RAY ERROR: MISS( 15)  15
  Constraints released:   GL B S6 (<)
  Constraints added:      GL B S14 (<)
 RAY ERROR: MISS 14
 RAY ERROR: MISS( 15)  15
 RAY ERROR: MISS 13
 RAY ERROR: MISS 13
 RAY ERROR: REFL 13
 RAY ERROR: MISS 14
 RAY ERROR: MISS 14
 RAY ERROR: MISS 14
     Normal AUTO Completion - System improvement less than IMP
AUT> GO
"""

# Real evidence, same corpus family (US20170003482A1 asphere run), a healthy
# AUT completion with no RAY ERROR lines anywhere.
_REAL_OK_EXCERPT = """\
 CYCLE NUMBER 0:

  ABERR F. =        0.23586894
  CONST F. =      127.92366266
  ERR. F.  =      128.15953160

 CYCLE NUMBER 13:

  ABERR F. =        0.17323803
  CONST F. =       26.95327543
  ERR. F.  =       27.12651346       (change =       -0.01919572)

     Normal AUTO Completion - System improvement less than IMP
AUT> GO
"""

# Synthetic-but-documented aperture-conflict fixture — the phrase is the one
# real termination keyword already known to codev_optimize.parse_aut_error_
# trace (_AUT_TERMINATION_KEYWORDS: "unable_to_scale_pupil_field"), assembled
# into a minimal listing shape. No real .lis sample confirms this fires under
# an explicit off-native FNO target yet — pending-real-machine per module
# docstring; this fixture only locks in the pattern-matching behavior.
_SYNTHETIC_APERTURE_CONFLICT_EXCERPT = """\
 CYCLE NUMBER 0:

  ABERR F. =        1.00000000
  CONST F. =        1.00000000
  ERR. F.  =        2.00000000

     Abnormal AUTO Completion - Unable to scale up Pupil and Field specifications
AUT> GO
"""

_NO_SIGNAL_EXCERPT = """\
CODE V> IN CV_MACRO:ZEMAXOS_TO_CV "seed.zmx"
CODE V> DEF VAR SA
CODE V> AUT
AUT> SUR N
"""


def test_classify_real_tir_and_miss_excerpt_prioritizes_tir() -> None:
    result = classify_fno_listing(_REAL_TIR_AND_MISS_EXCERPT)
    assert result.category == "TIR"
    assert result.refl_count == 3
    assert result.miss_count == 12
    assert result.ray_aiming_warning is True
    assert result.excerpt is None  # only "other" carries an excerpt


def test_classify_real_ok_excerpt() -> None:
    result = classify_fno_listing(_REAL_OK_EXCERPT)
    assert result.category == "ok"
    assert result.refl_count == 0
    assert result.miss_count == 0


def test_classify_miss_only_is_chief_ray_missing() -> None:
    text = "RAY ERROR: MISS 4\nRAY ERROR: MISS 5\n     Normal AUTO Completion\nAUT> GO\n"
    result = classify_fno_listing(text)
    assert result.category == "chief-ray-missing"
    assert result.miss_count == 2
    assert result.refl_count == 0


def test_classify_aperture_conflict_synthetic_fixture() -> None:
    result = classify_fno_listing(_SYNTHETIC_APERTURE_CONFLICT_EXCERPT)
    assert result.category == "aperture-conflict"
    assert result.aperture_conflict_matched is not None
    assert "Pupil and Field" in result.aperture_conflict_matched


@pytest.mark.parametrize(
    "phrase",
    [
        "Abnormal AUTO Completion - Scaled down SPC data",
        "Abnormal AUTO Completion - Scaled down nominal system cannot be traced",
    ],
)
def test_classify_scaled_down_family_is_aperture_conflict(phrase: str) -> None:
    """真机回填（P15 Stage 2 corpus）：两个 "Scaled down" 终止措辞（13 次 / 6
    次）属 aperture/pupil 缩放失败家族，无 RAY ERROR 行时必须归 aperture-
    conflict——修复前它们会因"无错误标记 + 有 AUT 结构"被误判 ok（MAJOR-3）。"""
    text = f" CYCLE NUMBER 0:\n\n     {phrase}\nAUT> GO\n"
    result = classify_fno_listing(text)
    assert result.category == "aperture-conflict"
    assert "Scaled down" in result.aperture_conflict_matched
    assert result.abnormal_completion_matched is not None


def test_classify_unknown_abnormal_termination_is_not_ok() -> None:
    """未登记的 Abnormal 终止措辞 fail-closed：绝不落 ok（MINOR-5）。"""
    text = (
        " CYCLE NUMBER 0:\n\n"
        "     Abnormal AUTO Completion - Some brand new failure phrase\n"
        "AUT> GO\n"
    )
    result = classify_fno_listing(text)
    assert result.category == "other"
    assert "Some brand new failure phrase" in result.note
    assert result.excerpt is not None


def test_classify_no_completion_evidence_is_other_not_ok() -> None:
    """fail-closed ok（MAJOR-3）：有 AUT 结构、无错误标记，但没有 Normal AUTO
    Completion 正面证据（清单截断/进程中途被杀/未知措辞）→ other，不是 ok。
    修复前的旧行为（AUT 结构存在即 ok）会把这类清单误判成功。"""
    text = " CYCLE NUMBER 0:\n\n  ERR. F.  =      128.15953160\n"
    result = classify_fno_listing(text)
    assert result.category == "other"
    assert "not success" in result.note
    assert result.normal_completion is False


def test_classify_ok_requires_normal_and_no_abnormal() -> None:
    """ok 的正面证据双条件：Normal 存在且 Abnormal 不存在。同一清单里两者都
    出现（多 AUT 块场景）→ 不是 ok。"""
    text = (
        "     Normal AUTO Completion - System improvement less than IMP\n"
        "     Abnormal AUTO Completion - Some other failure later\n"
    )
    result = classify_fno_listing(text)
    assert result.category == "other"
    assert result.normal_completion is True
    assert result.abnormal_completion_matched is not None


def test_classify_no_listing_text_is_other_no_signal() -> None:
    for missing in (None, "", "   "):
        result = classify_fno_listing(missing)
        assert result.category == "other"
        assert result.note == "no-listing-text"
        assert result.excerpt is None


def test_classify_no_signal_but_nonempty_text_is_other_with_excerpt() -> None:
    result = classify_fno_listing(_NO_SIGNAL_EXCERPT)
    assert result.category == "other"
    assert result.excerpt is not None
    assert result.excerpt.startswith("CODE V>")


def test_classify_tir_takes_priority_over_aperture_conflict() -> None:
    text = (
        "RAY ERROR: REFL 4\n"
        "Abnormal AUTO Completion - Unable to scale up Pupil and Field specifications\n"
    )
    result = classify_fno_listing(text)
    assert result.category == "TIR"


def test_describe_round_trips_all_fields() -> None:
    result = classify_fno_listing(_REAL_TIR_AND_MISS_EXCERPT)
    described = result.describe()
    assert described["category"] == "TIR"
    assert described["refl_count"] == 3
    assert set(described) == {
        "category",
        "refl_count",
        "miss_count",
        "ray_aiming_warning",
        "aperture_conflict_matched",
        "excerpt",
        "note",
        "normal_completion",
        "abnormal_completion_matched",
    }


# ---------------------------------------------------------------------------
# build_fno_probe_sequence — structural isolation invariants
# ---------------------------------------------------------------------------


def test_probe_sequence_locks_efl_to_native_and_sets_fno() -> None:
    seq = build_fno_probe_sequence(
        source_zmx=default_optimize_seed(),
        result_path=Path("r.tsv"),
        native_efl_mm=4.057,
        target_f_number=1.8,
        stage="probeA",
    )
    assert "EFL = 4.057" in seq
    assert "FNO 1.8" in seq
    assert '"stage"' in seq and '"probeA"' in seq


def test_probe_sequence_omits_vignetting_and_glass_dof() -> None:
    seq = build_fno_probe_sequence(
        source_zmx=default_optimize_seed(),
        result_path=Path("r.tsv"),
        native_efl_mm=4.057,
        target_f_number=2.4,
    )
    assert "\nVUY " not in seq
    assert "GLA " not in seq
    assert "GLC S" not in seq


def test_probe_sequence_default_cycles_are_short() -> None:
    seq = build_fno_probe_sequence(
        source_zmx=default_optimize_seed(),
        result_path=Path("r.tsv"),
        native_efl_mm=4.057,
        target_f_number=2.4,
    )
    assert "MXC 2" in seq
    assert "MNC 1" in seq


# ---------------------------------------------------------------------------
# run_fno_probe — mock CODE V subprocess (no real machine)
# ---------------------------------------------------------------------------


def _fake_codev_executable(tmp_path: Path) -> Path:
    executable = tmp_path / "codev.exe"
    executable.write_text("", encoding="utf-8")
    return executable


def _buf_exp_single_path(sequence_path: Path) -> Path:
    sequence = sequence_path.read_text(encoding="ascii")
    matches = re.findall(r'BUF EXP B1 "([^"]+)"', sequence)
    assert len(matches) == 1
    return Path(matches[0])


def _write_probe_result(path: Path, *, converged: str = "1", dev: str = "0.001") -> None:
    rows = [
        ("schema", "atelier-codev-target-v1"),
        ("status", "ok"),
        ("mode", "target"),
        ("stage", "probe"),
        ("source_zmx", "seed.zmx"),
        ("num_fields", "3"),
        ("vignetting_edge", "0"),
        ("target.efl_mm", "4.057"),
        ("target.f_number", "1.8"),
    ]
    for snap, efl, fno, imh in [
        ("seed_baseline", "4.057", "2.32", "3.686"),
        ("config_pre_aut", "4.057", "1.8", "3.686"),
        ("post_aut", "4.058", "1.8", "3.69"),
    ]:
        rows += [
            (f"{snap}.efl_y_mm", efl),
            (f"{snap}.max_lateral_color_um", "3.0"),
            (f"{snap}.max_rms_spot_diameter_um", "9.5"),
            (f"{snap}.max_rms_wavefront_error_waves", "0.4"),
            (f"{snap}.max_distortion_pct", "2.0"),
            (f"{snap}.fno", fno),
            (f"{snap}.epd_mm", "1.56"),
            (f"{snap}.maximh_mm", imh),
        ]
    rows += [("efl_target_deviation_pct", dev), ("aut_converged", converged)]
    path.write_text("\n".join(f"{k}\t{v}" for k, v in rows) + "\n", encoding="utf-8")


def test_run_fno_probe_ok_case_reads_listing_and_classifies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 111
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            result_path = _buf_exp_single_path(sequence_path)
            _write_probe_result(result_path)
            sequence_path.with_suffix(".lis").write_text(_REAL_OK_EXCERPT, encoding="utf-8")
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_fno_probe(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        native_efl_mm=4.057,
        native_fnum=2.32,
        target_f_number=1.8,
        direction="tighten",
        executable=executable,
        timeout_seconds=12.0,
    )
    assert result.outcome == "ok"
    assert result.classification is not None
    assert result.classification.category == "ok"
    assert result.aut_converged is True
    assert result.efl_target_deviation_pct == pytest.approx(0.001)
    assert result.post_aut_fno == pytest.approx(1.8)
    assert result.lis_path is not None and Path(result.lis_path).is_file()
    assert result.tsv_path is not None
    assert result.direction == "tighten"


def test_run_fno_probe_tir_case_classifies_from_real_excerpt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 112
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            result_path = _buf_exp_single_path(sequence_path)
            _write_probe_result(result_path, converged="0", dev="9.0")
            sequence_path.with_suffix(".lis").write_text(
                _REAL_TIR_AND_MISS_EXCERPT, encoding="utf-8"
            )
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_fno_probe(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        native_efl_mm=3.797,
        native_fnum=1.75,
        target_f_number=2.3,
        direction="loosen",
        executable=executable,
        timeout_seconds=12.0,
    )
    assert result.outcome == "TIR"
    assert result.classification is not None
    assert result.classification.refl_count == 3
    assert result.aut_converged is False


def test_run_fno_probe_timeout_reports_timeout_outcome_with_partial_listing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A hard timeout (TIR-flood hang) must report outcome="timeout" even if a
    partial listing hints at TIR — the timeout itself is the primary
    evidence, per brief: "超时也是一类证据"."""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 113
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[bytes, bytes]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            # A partial listing is left behind before the hang is killed.
            sequence_path.with_suffix(".lis").write_text(
                _REAL_TIR_AND_MISS_EXCERPT, encoding="utf-8"
            )
            raise subprocess.TimeoutExpired(self.command, timeout, output=b"flood")

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(
        codev_batch.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b""),
    )

    result = run_fno_probe(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        native_efl_mm=3.797,
        native_fnum=1.75,
        target_f_number=2.3,
        direction="loosen",
        executable=executable,
        timeout_seconds=0.01,
        platform_name="nt",
    )
    assert result.outcome == "timeout"
    assert result.error_kind == "timeout"
    # partial classification still attached for context, but did not override outcome
    assert result.classification is not None
    assert result.classification.category == "TIR"


def test_run_fno_probe_preflight_defect_is_not_masked_as_aperture_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Seed-level import defects (unresolved glass) must surface their real
    kind/preflight tag, not get bucketed into a ray-tracing failure
    category."""
    executable = _fake_codev_executable(tmp_path)

    class FakePopen:
        pid = 114
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            result_path = _buf_exp_single_path(sequence_path)
            _write_probe_result(result_path)
            text = result_path.read_text(encoding="utf-8")
            result_path.write_text(
                text.replace("seed_baseline.efl_y_mm\t4.057", "seed_baseline.efl_y_mm\t1e+35"),
                encoding="utf-8",
            )
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_fno_probe(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        native_efl_mm=4.057,
        native_fnum=2.32,
        target_f_number=1.8,
        direction="tighten",
        executable=executable,
        timeout_seconds=12.0,
    )
    assert result.error_kind == "failure"
    assert result.preflight == "unresolved-glass"
    assert result.outcome != "aperture-conflict"


def test_run_fno_probe_native_control_arm_omits_fno(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """native 对照臂（target_f_number=None + direction="native"）：生成的宏
    不含 FNO 命令、文件名 tag 为 _native、结果正常分类——用于区分 seed 固有
    光线病灶与 FNO 诱发病灶（summary.md §6 限制 1 的控制实验）。"""
    executable = _fake_codev_executable(tmp_path)
    seen_seq_text: list[str] = []

    class FakePopen:
        pid = 116
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            seen_seq_text.append(sequence_path.read_text(encoding="ascii"))
            result_path = _buf_exp_single_path(sequence_path)
            _write_probe_result(result_path)
            sequence_path.with_suffix(".lis").write_text(_REAL_OK_EXCERPT, encoding="utf-8")
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    result = run_fno_probe(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        native_efl_mm=4.057,
        native_fnum=2.32,
        target_f_number=None,
        direction="native",
        executable=executable,
        timeout_seconds=12.0,
    )
    assert len(seen_seq_text) == 1
    assert "\nFNO " not in seen_seq_text[0]  # 对照臂不发 FNO 命令
    assert result.direction == "native"
    assert result.target_f_number is None
    assert result.outcome == "ok"
    assert result.lis_path is not None and result.lis_path.endswith("_native.lis")


def test_run_fno_probe_uses_dot_free_filename_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CODE V BUF EXP filename hazard guard: the tag derived from a target F#
    like 1.8 must not contain a raw decimal point followed by more digits and
    an underscore (see codev_batch.ensure_buf_exp_safe_filename)."""
    executable = _fake_codev_executable(tmp_path)
    seen_names: list[str] = []

    class FakePopen:
        pid = 115
        returncode = 1

        def __init__(self, command: list[str], **kwargs: Mapping[str, object]) -> None:
            self.command = command
            self.kwargs = kwargs

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            sequence_path = Path(self.kwargs["cwd"]) / self.command[-1]
            seen_names.append(sequence_path.name)
            result_path = _buf_exp_single_path(sequence_path)
            _write_probe_result(result_path)
            return "ignored", ""

    monkeypatch.setattr(codev_batch.subprocess, "Popen", FakePopen)

    run_fno_probe(
        source_zmx=default_optimize_seed(),
        work_dir=tmp_path,
        native_efl_mm=4.057,
        native_fnum=2.32,
        target_f_number=1.83,
        direction="tighten",
        executable=executable,
        timeout_seconds=12.0,
    )
    assert seen_names == ["atelier_codev_target_probe_fno0183.seq"]
    for exc in (CodeVBatchError,):  # sanity: guard didn't need to fire, no ValueError raised
        assert exc is CodeVBatchError
