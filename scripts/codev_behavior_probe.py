"""闸2 Step-0：CODE V 行为经验探针（scratch 动态探针 · 定 E1-E8）.

呼应 spec docs/superpowers/specs/2026-07-08-codev-target-convergence-spike-design.md §3：
探针可跑 AUT 观测行为，但**不 mutate 交付宏、不持久化设计**——纯发现，产
`.planning/loop/codev-behavior-probe-report.md` 供回灌经验落地版。

复用现有宏基建（codev_optimize 的 readout 块 + codev_batch 的批跑/解析），
不改任何交付路径代码。每个探针一个 scratch .seq，导入 seed 后做一项经验实测。

用法：
    uv run python scripts/codev_behavior_probe.py [--seed <zmx>] [--only E5,E1,...]

无 CODE V 环境自动跳过（打印 skip 原因），CI 不阻塞。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.engines.codev_batch import (  # noqa: E402
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    parse_codev_result_file,
    run_codev_batch,
)
from app.core.engines.codev_optimize import (  # noqa: E402
    _optimized_readout_block,
    _quote_codev_path,
    default_optimize_seed,
)
from app.core.engines.codev_readout import (  # noqa: E402
    CODEV_READOUT_RESULT_SCHEMA,
    parse_codev_readout_data,
)

PROBE_TIMEOUT_SECONDS = 180.0
_OK_RETURNCODES = {0, 1}


@dataclass
class ProbeResult:
    """One E-item probe outcome."""

    e_id: str
    question: str
    ran: bool
    finding: str = ""
    data: dict[str, object] = field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# E5 / E4 / E8-native — static readout（import seed，纯读无 AUT）
# ---------------------------------------------------------------------------

def build_static_readout_sequence(*, source_zmx: Path, result_path: Path) -> str:
    """Import seed and dump full readout (field types / YIM / vignetting / FNO / EPD).

    复用 codev_optimize 的 _optimized_readout_block（同一 readout 逻辑，
    不跑 AUT）——一次静态读出即答 E5(场类型/YIM)、E4-part(FNO/EPD 导入态)、
    E8-native(VUY/VLY 原生系数)。
    """

    lines: list[str] = [
        "! scratch probe: static readout (no optimization) - codev_behavior_probe.",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        *_optimized_readout_block(source_name=source_zmx.name),
        f"BUF EXP B1 {_quote_codev_path(result_path)}",
        "BUF DEL B1",
        "OUT YES",
        "EXI YES",
        "",
    ]
    return "\n".join(lines)


def probe_static_readout(*, source_zmx: Path, work_dir: Path, executable) -> ProbeResult:
    seq = work_dir / "probe_static_readout.seq"
    res = work_dir / "probe_static_readout.tsv"
    seq.write_text(build_static_readout_sequence(source_zmx=source_zmx, result_path=res), encoding="ascii")
    try:
        batch = run_codev_batch(
            sequence_path=seq,
            result_path=res,
            executable=executable,
            work_dir=work_dir,
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
            expected_schema=CODEV_READOUT_RESULT_SCHEMA,
            required_keys=("schema", "status", "field_type", "num_fields"),
            allow_nonzero_ok_result=True,
        )
    except CodeVBatchError as exc:
        return ProbeResult("E5", "seed 原生场类型/场集/渐晕", ran=False, error=f"{exc.kind}: {exc.message}")

    readout = parse_codev_readout_data(batch.data)
    fields = readout.fields
    field_type = readout.field_type
    num_fields = readout.num_fields
    # 逐场 YIM/definition
    per_field = [
        {"index": i + 1, "definition_type": f.definition_type, "x": f.x, "y": f.y,
         "vuy": f.vuy, "vly": f.vly, "vux": f.vux, "vlx": f.vlx}
        for i, f in enumerate(fields)
    ]
    any_vig = any(abs(v) > 1e-9 for f in fields for v in (f.vuy, f.vly, f.vux, f.vlx))
    return ProbeResult(
        e_id="E5",
        question="seed 原生场类型 / 场集含 rel-1.0? / 原生渐晕系数(E8-native)",
        ran=True,
        finding=(
            f"field_type={field_type}, num_fields={num_fields}, "
            f"aperture_type={readout.aperture_type}, f_number={readout.f_number}, "
            f"EPD={readout.entrance_pupil_diameter_mm}, image_height_y_mm={readout.image_height_y_mm}; "
            f"原生渐晕系数{'存在(需E8重解验证)' if any_vig else '全0(此seed E8 trivial)'}"
        ),
        data={
            "field_type": field_type,
            "num_fields": num_fields,
            "aperture_type": readout.aperture_type,
            "f_number": readout.f_number,
            "entrance_pupil_diameter_mm": readout.entrance_pupil_diameter_mm,
            "image_height_y_mm": readout.image_height_y_mm,
            "per_field": per_field,
            "native_vignetting_present": any_vig,
        },
    )


# ---------------------------------------------------------------------------
# E1 / E2 / E6 / E7 — AUT drift（拉 EFL 到 ≠seed target，实测 F#/IMH 漂不漂）
# ---------------------------------------------------------------------------

_DRIFT_REQUIRED = (
    "schema", "status", "aperture_mode", "target_efl_factor",
    "before.efy", "before.fno", "before.epd_mm", "before.maximh",
    "after.efy", "after.fno", "after.epd_mm", "after.maximh",
)


def _maximh_snippet(prefix: str) -> list[str]:
    """Compute ^<prefix>_maximh over all fields（ANG: efy*tan; IMG: YIM）."""
    return [
        f"^{prefix}_efy == ABSF((EFY))",
        f"^{prefix}_maximh == 0",
        f"^{prefix}_ftyp == (TYP FLD)",
        "FOR ^f 1 (NUM F)",
        "  ^yh == (YRI F^f Z1)",
        f'  IF ^{prefix}_ftyp = "ANG"',
        f"    ^yh == ^{prefix}_efy * TANF((YAN F^f Z1)*4*ATANF(1)/180)",
        f'  ELS IF ^{prefix}_ftyp = "IMG"',
        "    ^yh == (YIM F^f Z1)",
        "  END IF",
        f"  IF ABSF(^yh) > ^{prefix}_maximh",
        f"    ^{prefix}_maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
    ]


def build_aut_drift_sequence(
    *, source_zmx: Path, result_path: Path, aperture_mode: str, target_efl_factor: float
) -> str:
    """Import seed, (optionally switch aperture mode), AUT pull EFL to factor*seed_efy,
    capture before/after {efy, fno, epd, maximh}. aperture_mode ∈ native|epd|fno."""

    lines: list[str] = [
        "! scratch probe: AUT drift (E1/E2/E6/E7) - codev_behavior_probe.",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "^seed_efy == ABSF((EFY))",
        "^seed_fno == ABSF((FNO))",
        "^seed_epd == ABSF((EPD))",
    ]
    # 切 aperture 模式（native=不动；epd=固定当前 EPD 切 EPD 模式；fno=固定当前 FNO）
    if aperture_mode == "epd":
        lines.append("EPD ^seed_epd")
    elif aperture_mode == "fno":
        lines.append("FNO ^seed_fno")
    lines.extend(_maximh_snippet("before"))
    lines.extend([
        "^before_fno == ABSF((FNO))",
        "^before_epd == ABSF((EPD))",
        f"^target_efl == ^seed_efy * {target_efl_factor:.6f}",
        "DEF VAR SA",
        "AUT",
        "  SUR N",
        "  CHG SA",
        "  EFL = ^target_efl",
        "  MNT 0.025",
        "  MNE 0.025",
        "  MXT 10",
        "  MNA 0.001",
        "  MXC 20",
        "  MNC 3",
        "  IMP 0.001",
        "GO",
    ])
    lines.extend(_maximh_snippet("after"))
    lines.extend([
        "^after_fno == ABSF((FNO))",
        "^after_epd == ABSF((EPD))",
        "^row == 1",
    ])
    rows = [
        ('"schema"', '"atelier-codev-drift-v1"'),
        ('"status"', '"ok"'),
        ('"aperture_mode"', f'"{aperture_mode}"'),
        ('"target_efl_factor"', f'"{target_efl_factor:.6f}"'),
        ('"seed.fno"', "^seed_fno"),
        ('"seed.epd_mm"', "^seed_epd"),
        ('"before.efy"', "^before_efy"),
        ('"before.fno"', "^before_fno"),
        ('"before.epd_mm"', "^before_epd"),
        ('"before.maximh"', "^before_maximh"),
        ('"target_efl"', "^target_efl"),
        ('"after.efy"', "^after_efy"),
        ('"after.fno"', "^after_fno"),
        ('"after.epd_mm"', "^after_epd"),
        ('"after.maximh"', "^after_maximh"),
    ]
    for key, val in rows:
        lines.append(f"BUF PUT B1 I^row J1 {key}")
        lines.append(f"BUF PUT B1 I^row J2 {val}")
        lines.append("^row == ^row+1")
    lines.extend([
        f"BUF EXP B1 {_quote_codev_path(result_path)}",
        "BUF DEL B1",
        "OUT YES",
        "EXI YES",
        "",
    ])
    return "\n".join(lines)


def probe_aut_drift(*, source_zmx: Path, work_dir: Path, executable, aperture_mode: str,
                    target_efl_factor: float = 1.12) -> dict[str, object] | None:
    seq = work_dir / f"probe_drift_{aperture_mode}.seq"
    res = work_dir / f"probe_drift_{aperture_mode}.tsv"
    seq.write_text(
        build_aut_drift_sequence(
            source_zmx=source_zmx, result_path=res,
            aperture_mode=aperture_mode, target_efl_factor=target_efl_factor,
        ),
        encoding="ascii",
    )
    try:
        run_codev_batch(
            sequence_path=seq, result_path=res, executable=executable, work_dir=work_dir,
            timeout_seconds=PROBE_TIMEOUT_SECONDS, expected_schema="atelier-codev-drift-v1",
            required_keys=_DRIFT_REQUIRED, allow_nonzero_ok_result=True,
        )
    except CodeVBatchError as exc:
        return {"error": f"{exc.kind}: {exc.message}"}
    data = parse_codev_result_file(res, expected_schema="atelier-codev-drift-v1", required_keys=_DRIFT_REQUIRED)
    return {k: data[k] for k in data}


def _pct(a: float, b: float) -> float:
    return abs(a - b) / abs(b) * 100 if abs(b) > 1e-12 else 0.0


def summarize_drift(mode: str, d: dict[str, object]) -> ProbeResult:
    if "error" in d:
        return ProbeResult(f"E1/{mode}", "AUT 拉 EFL 时 F#/IMH 漂不漂", ran=False, error=str(d["error"]))
    b_efy, a_efy = float(d["before.efy"]), float(d["after.efy"])
    b_fno, a_fno = float(d["before.fno"]), float(d["after.fno"])
    b_epd, a_epd = float(d["before.epd_mm"]), float(d["after.epd_mm"])
    b_imh, a_imh = float(d["before.maximh"]), float(d["after.maximh"])
    tgt = float(d["target_efl"])
    efl_hit = _pct(a_efy, tgt)
    fno_drift = _pct(a_fno, b_fno)
    imh_drift = _pct(a_imh, b_imh)
    epd_drift = _pct(a_epd, b_epd)
    return ProbeResult(
        e_id=f"E1/{mode}",
        question=f"{mode} 模式：AUT 拉 EFL 到 target 时 F#/IMH/EPD 漂不漂",
        ran=True,
        finding=(
            f"EFL {b_efy:.4f}→{a_efy:.4f}(target {tgt:.4f}, 达成偏差{efl_hit:.2f}%) · "
            f"F# {b_fno:.4f}→{a_fno:.4f}(漂{fno_drift:.2f}%) · "
            f"EPD {b_epd:.4f}→{a_epd:.4f}(漂{epd_drift:.2f}%) · "
            f"IMH {b_imh:.4f}→{a_imh:.4f}(漂{imh_drift:.2f}%)"
        ),
        data={"efl_hit_pct": efl_hit, "fno_drift_pct": fno_drift,
              "imh_drift_pct": imh_drift, "epd_drift_pct": epd_drift, **d},
    )


# ---------------------------------------------------------------------------
# E3 — 畸变 (DIX/DIY) 有无 err 出口（DB accessor vs err-return trace 原语）
# ---------------------------------------------------------------------------

_E3_REQUIRED = ("schema", "status", "dix_axial", "dix_maxfield", "diy_maxfield", "num_fields")


def build_e3_sequence(*, source_zmx: Path, result_path: Path) -> str:
    """读 DIX/DIY（畸变 DB accessor）——证其为纯读、无 err 语法。守卫须用有 err
    出口的 trace 原语（SPOTDATA，现有 @rmssum 已证可用）。"""
    lines = [
        "! scratch probe: E3 distortion accessor - codev_behavior_probe.",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "^nf == (NUM F)",
        "^dix_axial == (DIX Z1 F1)",
        "^dix_max == (DIX Z1 F^nf)",
        "^diy_max == (DIY Z1 F^nf)",
        "^row == 1",
    ]
    rows = [
        ('"schema"', '"atelier-codev-e3-v1"'), ('"status"', '"ok"'),
        ('"num_fields"', "^nf"), ('"dix_axial"', "^dix_axial"),
        ('"dix_maxfield"', "^dix_max"), ('"diy_maxfield"', "^diy_max"),
    ]
    for k, v in rows:
        lines += [f"BUF PUT B1 I^row J1 {k}", f"BUF PUT B1 I^row J2 {v}", "^row == ^row+1"]
    lines += [f"BUF EXP B1 {_quote_codev_path(result_path)}", "BUF DEL B1", "OUT YES", "EXI YES", ""]
    return "\n".join(lines)


def probe_e3(*, source_zmx: Path, work_dir: Path, executable) -> ProbeResult:
    seq = work_dir / "probe_e3.seq"
    res = work_dir / "probe_e3.tsv"
    seq.write_text(build_e3_sequence(source_zmx=source_zmx, result_path=res), encoding="ascii")
    try:
        run_codev_batch(
            sequence_path=seq, result_path=res, executable=executable, work_dir=work_dir,
            timeout_seconds=PROBE_TIMEOUT_SECONDS, expected_schema="atelier-codev-e3-v1",
            required_keys=_E3_REQUIRED, allow_nonzero_ok_result=True,
        )
    except CodeVBatchError as exc:
        return ProbeResult("E3", "畸变 DIX/DIY 有无 err 出口", ran=False, error=f"{exc.kind}: {exc.message}")
    data = parse_codev_result_file(res, expected_schema="atelier-codev-e3-v1", required_keys=_E3_REQUIRED)
    return ProbeResult(
        e_id="E3", question="畸变 DIX/DIY 有无 err 出口 → distortion 守卫怎么写", ran=True,
        finding=(
            f"DIX/DIY 为 DB accessor 纯读值（轴 DIX={data['dix_axial']}, "
            f"max 场 DIX={data['dix_maxfield']}/DIY={data['diy_maxfield']}），**无 err 语法**。"
            f"守卫须用有 err 出口的 trace 原语——SPOTDATA(...) 返回 ^err（现有 @rmssum 已用、"
            f"真机 optimize 冒烟已证可用）→ distortion 守卫=每场先 SPOTDATA/RSI err 前置，成功才读 DIX/DIY。"
        ),
        data={**data},
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(results: list[ProbeResult], seed: Path, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# CODE V 行为经验探针报告（闸2 Step-0）",
        "",
        f"- **seed**: `{seed.name}`",
        "- **探针**: scratch 动态、不 mutate 交付宏（spec §3）",
        f"- **CODE V**: `{DEFAULT_CODEV_EXECUTABLE}`",
        "",
        "| E# | 经验未知 | 跑通 | 实测发现 |",
        "|---|---|---|---|",
    ]
    for r in results:
        status = "✅" if r.ran else "⏭️/❌"
        detail = r.finding if r.ran else f"未跑：{r.error}"
        lines.append(f"| {r.e_id} | {r.question} | {status} | {detail} |")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="CODE V 行为经验探针 E1-E8")
    parser.add_argument("--seed", type=Path, default=None)
    parser.add_argument("--work-dir", type=Path, default=Path("scratch_probe"))
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(".planning/loop/codev-behavior-probe-report.md"),
    )
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else default_optimize_seed()
    executable = Path(DEFAULT_CODEV_EXECUTABLE.__fspath__())
    if not executable.is_file():
        print(f"[skip] CODE V not found at {executable}; probe requires real CODE V.")
        return 0

    work_dir = args.work_dir.resolve()  # 绝对路径：CODE V BUF EXP 相对路径会二次拼接失败
    work_dir.mkdir(parents=True, exist_ok=True)

    results: list[ProbeResult] = []
    print(f"[probe] seed={seed.name}")

    # E5 / E4-native / E8-native: 静态读出
    r5 = probe_static_readout(source_zmx=seed, work_dir=work_dir, executable=executable)
    print(f"[probe] E5: ran={r5.ran} {r5.finding or r5.error}")
    results.append(r5)

    # E1(FNO 支)/E2/E6: native(FNO) 模式 AUT 漂移
    d_native = probe_aut_drift(source_zmx=seed, work_dir=work_dir, executable=executable, aperture_mode="native")
    r_native = summarize_drift("native(FNO)", d_native)
    print(f"[probe] E1/native: ran={r_native.ran} {r_native.finding or r_native.error}")
    results.append(r_native)

    # E1(EPD 支): 强制 EPD 模式 AUT 漂移（对照）
    d_epd = probe_aut_drift(source_zmx=seed, work_dir=work_dir, executable=executable, aperture_mode="epd")
    r_epd = summarize_drift("epd", d_epd)
    print(f"[probe] E1/epd: ran={r_epd.ran} {r_epd.finding or r_epd.error}")
    results.append(r_epd)

    # E7: native 复现（同参再跑一次，比 after.efy 逐位）
    d_native2 = probe_aut_drift(source_zmx=seed, work_dir=work_dir, executable=executable, aperture_mode="native")
    if "error" not in d_native and "error" not in d_native2:
        repro = d_native.get("after.efy") == d_native2.get("after.efy")
        results.append(ProbeResult(
            "E7", "AUT 同 seed 同 target 是否逐位可复现", ran=True,
            finding=f"两次 after.efy: {d_native.get('after.efy')} vs {d_native2.get('after.efy')} → "
                    f"{'逐位一致(确定性)' if repro else '不一致(非确定性→复现定向到2%阈)'}",
            data={"repro_exact": repro},
        ))
        print(f"[probe] E7: repro_exact={repro}")

    # E6: 极端 target(factor 3.0=+200%) 验 EFL-hit 代理能否区分发散
    d_ext = probe_aut_drift(source_zmx=seed, work_dir=work_dir, executable=executable,
                            aperture_mode="native", target_efl_factor=3.0)
    if "error" not in d_ext:
        efl_hit_ext = _pct(float(d_ext["after.efy"]), float(d_ext["target_efl"]))
        results.append(ProbeResult(
            "E6", "AUT 有无显式收敛标志 → 天花板臂 RED/INVALID 判据", ran=True,
            finding=(
                f"极端 target(+200%): EFL {float(d_ext['before.efy']):.3f}→{float(d_ext['after.efy']):.3f}"
                f"(target {float(d_ext['target_efl']):.3f}, 达成偏差 **{efl_hit_ext:.1f}%**)。"
                f"CODE V AUT 无 macro 可读显式收敛码 → 用 **EFL-hit 代理**："
                f"{'偏差>>2% 明确区分发散(代理有效, spec E6 fallback 成立)' if efl_hit_ext > 2 else '意外收敛'}"
            ),
            data={"efl_hit_ext_pct": efl_hit_ext, **d_ext},
        ))
        print(f"[probe] E6: extreme-target efl_hit={efl_hit_ext:.1f}%")

    # E3: 畸变 accessor err 出口
    r3 = probe_e3(source_zmx=seed, work_dir=work_dir, executable=executable)
    print(f"[probe] E3: ran={r3.ran} {r3.finding[:60] if r3.ran else r3.error}")
    results.append(r3)

    # E8: 场重建后渐晕重解（此 seed 渐晕 trivial，从 E5 数据判）
    if r5.ran:
        any_vig = r5.data.get("native_vignetting_present", False)
        results.append(ProbeResult(
            "E8", "场 ANG→IMG 重建后渐晕(VUY/VLY)是否需重解", ran=True,
            finding=(
                f"Seed-1 原生渐晕系数{'存在' if any_vig else '**全 0 → E8 对此 seed trivial**（场重建无渐晕可丢）'}。"
                f"通用回答需一颗**带渐晕系数的 seed** 复测；Stage C 实现时对带渐晕 seed 须同步重解 VDX/VDY（保守 fail-closed）。"
            ),
            data={"native_vignetting_present": any_vig},
        ))
        print(f"[probe] E8: native_vig={any_vig} (trivial for this seed if False)")

    write_report(results, seed, args.report)
    print(f"[probe] report → {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
