"""③优化落地实验矩阵 runner — 跑 target-mode AUT，出资深 go/no-go 报告.

spec: docs/superpowers/specs/2026-07-08-codev-target-convergence-spike-design.md §5.
按最小闸条件展开（§5.3）：每 seed 跑 baseline-lock 参照 + Stage A/B 甜区 + 天花板臂，
抓三快照像质，算收敛 + 质量倍率，出报告——**三色 verdict 栏留空由资深填**（[EXPERT] 红线）。

用法：uv run python scripts/codev_target_experiment.py [--seeds a.zmx b.zmx]
无 CODE V 自动 skip。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.engines.codev_batch import (  # noqa: E402
    DEFAULT_CODEV_EXECUTABLE,
    CodeVBatchError,
    run_codev_batch,
)
from app.core.engines.codev_optimize import (  # noqa: E402
    _fmt_number,
    _quote_codev_path,
    default_optimize_seed,
    run_codev_target,
)
from app.core.zmx_ingest import ZMX_AMMO_DIR  # noqa: E402

SWEET_FACTOR = 1.12   # 甜区偏移 +12%（探针证 +12% 可收敛）
CEILING_FACTOR = 1.35  # 天花板臂 +35%（负向对照）
TIMEOUT = 180.0
_FO_SCHEMA = "atelier-codev-firstorder-v1"
_FO_REQUIRED = ("schema", "status", "efl", "fno", "maximh")


def _first_order_seq(source_zmx: Path, result_path: Path) -> str:
    return "\n".join([
        "! scratch: seed first-order read.",
        "OUT NO",
        f"IN CV_MACRO:ZEMAXOS_TO_CV {_quote_codev_path(source_zmx)}",
        "^efy == ABSF((EFY))",
        "^fno == ABSF((FNO))",
        "^ftyp == (TYP FLD)",
        "^maximh == 0",
        "FOR ^f 1 (NUM F)",
        "  ^yh == (YRI F^f Z1)",
        '  IF ^ftyp = "ANG"',
        "    ^yh == ^efy * TANF((YAN F^f Z1)*4*ATANF(1)/180)",
        '  ELS IF ^ftyp = "IMG"',
        "    ^yh == (YIM F^f Z1)",
        "  END IF",
        "  IF ABSF(^yh) > ^maximh",
        "    ^maximh == ABSF(^yh)",
        "  END IF",
        "END FOR",
        '^row == 1',
        'BUF PUT B1 I^row J1 "schema"', 'BUF PUT B1 I^row J2 "atelier-codev-firstorder-v1"', '^row == ^row+1',
        'BUF PUT B1 I^row J1 "status"', 'BUF PUT B1 I^row J2 "ok"', '^row == ^row+1',
        'BUF PUT B1 I^row J1 "efl"', "BUF PUT B1 I^row J2 ^efy", '^row == ^row+1',
        'BUF PUT B1 I^row J1 "fno"', "BUF PUT B1 I^row J2 ^fno", '^row == ^row+1',
        'BUF PUT B1 I^row J1 "maximh"', "BUF PUT B1 I^row J2 ^maximh", '^row == ^row+1',
        f"BUF EXP B1 {_quote_codev_path(result_path)}",
        "BUF DEL B1", "OUT YES", "EXI YES", "",
    ])


def read_first_order(seed: Path, work_dir: Path, executable) -> dict[str, float] | None:
    seq = work_dir / "fo.seq"
    res = work_dir / "fo.tsv"
    seq.write_text(_first_order_seq(seed, res), encoding="ascii")
    try:
        b = run_codev_batch(
            sequence_path=seq, result_path=res, executable=executable, work_dir=work_dir,
            timeout_seconds=TIMEOUT, expected_schema=_FO_SCHEMA, required_keys=_FO_REQUIRED,
            allow_nonzero_ok_result=True,
        )
    except CodeVBatchError:
        return None
    efl = float(b.data["efl"])
    # 导入自检（spec §4.1）：EFL 非有限/超合理界(手机镜头 ~1-30mm) → 导入退化，判 tooling-blocked
    if not (efl == efl) or abs(efl) > 1.0e3 or abs(efl) < 1.0e-3:
        print(f"[exp] {seed.name}: 导入自检失败 EFL={efl:.4g}(非物理) → tooling-blocked，排除")
        return None
    return {"efl": efl, "fno": float(b.data["fno"]), "maximh": float(b.data["maximh"])}


@dataclass
class RunRow:
    seed: str
    arm: str
    data: dict[str, str]


def _g(d: dict[str, str], k: str, default: float = float("nan")) -> float:
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _ratio(a: float, b: float) -> float:
    return a / b if b not in (0.0,) and b == b else float("nan")


def run_matrix(seed: Path, work_dir: Path, executable) -> list[RunRow]:
    fo = read_first_order(seed, work_dir, executable)
    rows: list[RunRow] = []
    if fo is None:
        print(f"[exp] {seed.name}: 一阶读取失败(导入不了)，跳过")
        return rows
    efl, fno = fo["efl"], fo["fno"]
    sweet, ceiling, lock = efl * SWEET_FACTOR, efl * CEILING_FACTOR, efl
    print(f"[exp] {seed.name}: seed EFL={efl:.4f} F#={fno:.3f} IMH={fo['maximh']:.4f} "
          f"→ sweet {sweet:.4f} / ceiling {ceiling:.4f}")
    plan = [
        ("baseline-lock", dict(target_efl_mm=lock, stage="baseline-lock")),
        ("A(甜区)", dict(target_efl_mm=sweet, stage="A")),
        ("B(甜区+F#)", dict(target_efl_mm=sweet, target_f_number=fno, stage="B")),
        ("天花板(+35%)", dict(target_efl_mm=ceiling, stage="ceiling")),
    ]
    for arm, kw in plan:
        try:
            data = run_codev_target(source_zmx=seed, work_dir=work_dir, executable=executable,
                                    timeout_seconds=TIMEOUT, **kw)
            rows.append(RunRow(seed.name, arm, data))
            print(f"[exp]   {arm}: EFL→{_g(data,'post_aut.efl_y_mm'):.4f} "
                  f"dev%={_g(data,'efl_target_deviation_pct'):.3g} conv={data.get('aut_converged')}")
        except CodeVBatchError as exc:
            rows.append(RunRow(seed.name, arm, {"error": f"{exc.kind}: {exc.message}"}))
            print(f"[exp]   {arm}: INVALID/tooling ({exc.kind})")
    return rows


def write_report(all_rows: list[RunRow], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    L = [
        "# ③优化落地实验矩阵 — 资深 go/no-go 报告",
        "",
        "- **探针边界**：机器只出客观数字；**三色 verdict / 良品率由资深填**（[EXPERT] 红线，AI 不代判）。",
        "- **收敛=机器客观**（EFL 落 target 2% 内）；**像质好坏=资深判**（畸变/RMS 倍率是裸数字）。",
        "- **玻璃冻结**（接缝2 隔离）：像质劣化含'冻结玻璃只动曲率/厚度'的本征代价。",
        "",
        "| seed | 臂 | EFL seed→post (target,偏差%,conv) | F# | IMH | RMS点列 seed→post(µm,×) | 波前(waves) | 畸变%(×) | **资深verdict** |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in all_rows:
        d = r.data
        if "error" in d:
            L.append(f"| {r.seed} | {r.arm} | INVALID/tooling: {d['error']} | | | | | | ☐ |")
            continue
        s_efl, p_efl = _g(d, "seed_baseline.efl_y_mm"), _g(d, "post_aut.efl_y_mm")
        tgt, dev, conv = _g(d, "target.efl_mm"), _g(d, "efl_target_deviation_pct"), d.get("aut_converged")
        s_fno, p_fno = _g(d, "seed_baseline.fno"), _g(d, "post_aut.fno")
        s_imh, p_imh = _g(d, "seed_baseline.maximh_mm"), _g(d, "post_aut.maximh_mm")
        s_spot, p_spot = _g(d, "seed_baseline.max_rms_spot_diameter_um"), _g(d, "post_aut.max_rms_spot_diameter_um")
        s_wfe, p_wfe = _g(d, "seed_baseline.max_rms_wavefront_error_waves"), _g(d, "post_aut.max_rms_wavefront_error_waves")
        s_dis, p_dis = _g(d, "seed_baseline.max_distortion_pct"), _g(d, "post_aut.max_distortion_pct")
        conv_mark = "✅" if str(conv) == "1" else "❌"
        L.append(
            f"| {r.seed} | {r.arm} | {s_efl:.3f}→{p_efl:.3f} "
            f"(t{tgt:.3f},{dev:.2g}%,{conv_mark}) | {s_fno:.2f}→{p_fno:.2f} | {s_imh:.3f}→{p_imh:.3f} | "
            f"{s_spot:.2f}→{p_spot:.2f}(×{_ratio(p_spot,s_spot):.2f}) | "
            f"{s_wfe:.3f}→{p_wfe:.3f}(×{_ratio(p_wfe,s_wfe):.2f}) | "
            f"{s_dis:.2f}→{p_dis:.2f}(×{_ratio(p_dis,s_dis):.2f}) | ☐ |"
        )
    L += [
        "",
        "## 机器客观结论（非良品率）",
        "- **收敛半径**：甜区(+12%) vs 天花板(+35%) 的 conv 标志对比 = 机制可收敛偏移带。",
        "- **go-signal**：EFL 是否落 target 2% 内（机制通）。",
        "- **待资深判**：像质倍率是否在'值得看一眼/接近可用'带内；填 verdict 栏。",
    ]
    report_path.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="*", default=None)
    ap.add_argument("--work-dir", type=Path, default=Path("scratch_experiment"))
    ap.add_argument("--report", type=Path, default=Path(".planning/loop/codev-target-experiment-report.md"))
    args = ap.parse_args()

    executable = Path(DEFAULT_CODEV_EXECUTABLE.__fspath__())
    if not executable.is_file():
        print(f"[skip] CODE V not found at {executable}")
        return 0
    work_dir = args.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    if args.seeds:
        seeds = [Path(s) if Path(s).is_absolute() else ZMX_AMMO_DIR / s for s in args.seeds]
    else:
        seeds = [
            default_optimize_seed(),
            ZMX_AMMO_DIR / "5P_F1.8_FOV74.1_EFL2.9_IMH2.3_TTL4.15.zmx",
        ]

    all_rows: list[RunRow] = []
    for seed in seeds:
        if not seed.is_file():
            print(f"[exp] seed 不存在: {seed}")
            continue
        all_rows.extend(run_matrix(seed, work_dir, executable))
    write_report(all_rows, args.report)
    print(f"[exp] report → {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
