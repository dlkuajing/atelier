"""Library-wide gate: every data/zmx GLAS row must be CODE-V-resolvable.

Root cause guarded against (real-machine evidence 2026-07-10,
scratch_diag/rebuild_inf_efl): CODE V's ZEMAXOS_TO_CV importer silently drops
a named catalog glass it cannot resolve to **air** (nd=1.0). The 17 legacy
real-design seeds (3P_/4P_/5P_*) carried plastic-resin trade names with
model_flag=0 under catalogs that don't list them, importing as all-air
zero-power systems — Optiland masked it via the
``optiland_patches._patch_zemax_glass_materials`` fallback, and Mode3 surfaced
it three layers downstream as ``zmx_rebuild_error: non-finite EFL: -inf``.

The assertion mirrors the conventions the rest of the pipeline already trusts:

* patent-derived seeds (scripts/patent_to_zmx.py output) encode explicit model
  glass — ``GLAS ___BLANK <flag> ... <nd> <vd> ...`` — with inline physical
  nd/vd (flag 1 = model glass, flag 2 = glass pickup; both carry inline nd/vd
  and both resolve via the importer's "BLANK" substring branch);
* the DATA-09d1 intake gate (scripts/e2_intake.py ``_looks_like_index``)
  accepts an inline nd in [1.3, 2.2];
* a *named* glass with model_flag=0 delegates resolution to CODE V's catalogs,
  which is only legitimate for names verified to resolve on the real machine
  (``CODEV_RESOLVABLE_GLASS_NAMES`` in scripts/repair_legacy_zmx_glass.py);
* the repaired legacy form is ``GLAS <trade-name>_BLANK 1 0 <nd> <vd>``: the
  ``_BLANK`` marker is what makes ZEMAXOS_TO_CV take its model-glass branch
  (substring match, macro L1523 — real-machine verified 2026-07-10; a bare
  trade name with model_flag=1 still imports as AIR), while the trade name
  stays recoverable for the case library / prescription table.

For the repaired form, the inline nd/vd must equal ``lookup_nd_vd`` exactly —
that identity is what guarantees CODE V and Optiland compute on the same
material and keeps every Optiland golden stable.
"""

from __future__ import annotations

import math
from pathlib import Path

from app.core.zmx_ingest import ZMX_AMMO_DIR
from app.core.zmx_materials import lookup_nd_vd
from scripts.repair_legacy_zmx_glass import (
    CODEV_MODEL_GLASS_MARKER,
    CODEV_RESOLVABLE_GLASS_NAMES,
    decode_zmx_text,
    glas_line_needs_repair,
    iter_glas_lines,
    repair_glas_line,
)

ND_RANGE = (1.3, 2.2)  # mirrors scripts/e2_intake.py::_looks_like_index
VD_RANGE = (10.0, 100.0)


def _zmx_files() -> list[Path]:
    return sorted(
        (path for path in ZMX_AMMO_DIR.iterdir() if path.suffix.lower() == ".zmx"),
        key=lambda path: path.name,
    )


def _parse_inline_nd_vd(tokens: list[str]) -> tuple[float, float] | None:
    try:
        return float(tokens[4]), float(tokens[5])
    except (IndexError, ValueError):
        return None


def _glas_row_problem(tokens: list[str]) -> str | None:
    """Return a human-readable defect for one GLAS row, or None if resolvable."""
    if len(tokens) < 3:
        return f"malformed GLAS row (too few tokens): {' '.join(tokens)}"
    name, flag = tokens[1], tokens[2]
    if name.upper() == "MIRROR":
        return None
    if name == "___BLANK" or name.endswith(CODEV_MODEL_GLASS_MARKER):
        # Explicit model glass: ZEMAXOS_TO_CV keys on the "BLANK" substring in
        # the name and uses the inline nd/vd, so they must be physical.
        inline = _parse_inline_nd_vd(tokens)
        if inline is None:
            return f"model glass without parseable inline nd/vd: {' '.join(tokens)}"
        nd, vd = inline
        if not (math.isfinite(nd) and ND_RANGE[0] <= nd <= ND_RANGE[1]):
            return f"model glass nd {nd!r} outside {ND_RANGE}: {' '.join(tokens)}"
        if not (math.isfinite(vd) and VD_RANGE[0] <= vd <= VD_RANGE[1]):
            return f"model glass vd {vd!r} outside {VD_RANGE}: {' '.join(tokens)}"
        if name != "___BLANK":
            # Repaired legacy form: canonical encoding is model_flag=1 —
            # CODE V keys on the BLANK substring either way, but real Zemax
            # reads flag=0 as catalog-name semantics (unresolvable -> air),
            # so a marker name with any other flag is a defective hybrid.
            if flag != "1":
                return (
                    f"marker-suffixed model glass {name!r} must carry "
                    f"model_flag=1, got {flag!r}: {' '.join(tokens)}"
                )
            # Inline values must equal the datasheet table the Optiland
            # fallback resolves (lookup strips the marker), else the two
            # engines silently compute on different materials.
            real = lookup_nd_vd(name)
            if real is None:
                return (
                    f"marker-suffixed model glass {name!r} has no entry in "
                    f"app.core.zmx_materials.MATERIAL_ND_VD: {' '.join(tokens)}"
                )
            if abs(nd - real[0]) > 1e-9 or abs(vd - real[1]) > 1e-9:
                return (
                    f"named model glass {name!r} inline nd/vd ({nd}, {vd}) diverge "
                    f"from the Optiland datasheet table {real}: {' '.join(tokens)}"
                )
        return None
    if flag == "0":
        if name in CODEV_RESOLVABLE_GLASS_NAMES:
            return None
        return (
            f"named catalog glass {name!r} (model_flag=0) is not real-machine "
            "verified as CODE-V-resolvable; ZEMAXOS_TO_CV imports it as air"
        )
    if flag == "1":
        return (
            f"bare named model glass {name!r} (model_flag=1, no _BLANK marker) "
            "imports as air — real-machine verified 2026-07-10; use "
            f"<name>{CODEV_MODEL_GLASS_MARKER}: {' '.join(tokens)}"
        )
    return f"unrecognized GLAS encoding (model_flag={flag!r}): {' '.join(tokens)}"


def test_zmx_library_is_nonempty() -> None:
    assert len(_zmx_files()) > 300  # 353 seeds at the time of writing


def test_marker_is_transparent_to_material_lookup() -> None:
    """`_canon` strips the `_BLANK` repair marker, so a marked name resolves to
    the same datasheet values as the bare trade name — the identity the
    repaired inline nd/vd are checked against."""
    assert lookup_nd_vd("APL5014CL_14_BLANK") == lookup_nd_vd("APL5014CL_14")
    assert lookup_nd_vd("ZEONEX-E48R_14_BLANK") == lookup_nd_vd("ZEONEX-E48R")
    assert lookup_nd_vd("D263T_BLANK") == lookup_nd_vd("D263T")
    # The plain Zemax model-glass placeholder must NOT be treated as marked.
    assert lookup_nd_vd("___BLANK") is None


def test_every_glas_row_is_codev_resolvable() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _zmx_files():
        text, _encoding = decode_zmx_text(path.read_bytes())
        for line_number, tokens in iter_glas_lines(text):
            problem = _glas_row_problem(tokens)
            if problem is not None:
                offenders.setdefault(path.name, []).append(f"L{line_number}: {problem}")
    assert not offenders, (
        f"{len(offenders)} ZMX file(s) carry GLAS rows CODE V cannot resolve "
        "(import drops them to air -> zero-power system). Run "
        "`uv run python scripts/repair_legacy_zmx_glass.py`:\n"
        + "\n".join(
            f"{name}\n  " + "\n  ".join(problems)
            for name, problems in sorted(offenders.items())
        )
    )


def test_repair_appends_marker_to_bare_flag1_named_model_glass() -> None:
    """裸商品名 + model_flag=1 仍被 CODE V 导入为空气（真机判定：宏按名字符串
    的 "BLANK" 子串选 model-glass 分支，不看 flag）——修复必须补上标记并把
    nd/vd 归一到数据表（W7a）。"""
    line = "  GLAS APL5014CL_14 1 0 1.5 40 0 0 1 0 0 0 \r\n"
    fixed, changed = repair_glas_line(line)
    assert changed
    assert fixed == "  GLAS APL5014CL_14_BLANK 1 0 1.544 56 0 0 1 0 0 0 \r\n"


def test_repair_fixes_flag_without_renaming_marked_names() -> None:
    """已带标记但 flag=0 的行：只归一 flag（与 nd/vd），绝不二次加后缀（W7b）。"""
    line = "  GLAS OKP1_14_BLANK 0 0 1.636 22.5 0 0 0 0 0 0 \r\n"
    fixed, changed = repair_glas_line(line)
    assert changed
    assert fixed == "  GLAS OKP1_14_BLANK 1 0 1.636 22.5 0 0 0 0 0 0 \r\n"
    assert fixed.count("_BLANK") == 1


def test_repair_is_idempotent() -> None:
    line = "  GLAS ZEONEX-E48R_14 0 0 1.5 40 0 0 1 0 0 0 \r\n"
    once, changed_once = repair_glas_line(line)
    twice, changed_twice = repair_glas_line(once)
    assert changed_once and not changed_twice
    assert twice == once
    assert once.count("_BLANK") == 1


def test_repair_verdict_agrees_with_gate_verdict() -> None:
    """`--check`（glas_line_needs_repair）与本模块 gate（_glas_row_problem）
    对同一输入的判定必须一致，且修复产物必然过 gate（W7c）。"""
    rows = [
        "GLAS APL5014CL_14 0 0 1.5 40 0 0 1 0 0 0",  # flag0 不可解析
        "GLAS APL5014CL_14 1 0 1.5 40 0 0 1 0 0 0",  # 裸 flag1 商品名
        "GLAS OKP1_14_BLANK 0 0 1.636 22.5 0 0 0 0 0 0",  # 标记名 + 错 flag
        "GLAS OKP1_14_BLANK 1 0 1.6 22.5 0 0 0 0 0 0",  # 标记名 + nd 偏离数据表
        "GLAS OKP1_14_BLANK 1 0 1.636 22.5 0 0 0 0 0 0",  # 已修复态
        "GLAS ___BLANK 1 0 1.656 18.4 0 0 0 0 0 0",  # 专利管线约定
        "GLAS ___BLANK 2 3 1.545 56 0 0 0 0 0 0",  # glass pickup（既有库内形态）
        "GLAS BK7 0 0 1.5 40 0 0 0 0 0 0",  # 真机验证目录可解析名
        "GLAS MIRROR 0 0 0 0 0 0 0 0 0 0",  # 反射面
    ]
    for row in rows:
        tokens = row.split()
        gate_flags = _glas_row_problem(tokens) is not None
        assert glas_line_needs_repair(tokens) == gate_flags, row
        fixed, _changed = repair_glas_line(row)
        assert _glas_row_problem(fixed.split()) is None, fixed
