---
quick_id: 260708-telephoto-routing
date: 2026-07-08
status: in-progress
---

# Quick Task: 修复长焦404结构选型缺陷

## Problem (facts, verified)
- 案例库 343 颗 seed，**零颗** 标为 telephoto。`_classify_scenario(fov)` 仅按 FOV 二分 wide/ultrawide。
- 路由按 **烙进 JSON 的 `metadata.scenario`** 过滤（case_library.py:1315），非实时分类。
- telephoto 是 parameter_guards 合法一等 scenario（EFL5-18/FOV15-45），用户能过校验却撞
  `match_case→None→optical.py:645 HTTP 404`，形成"能提问不能作答"裂缝。
- `fov_deg` = 全视场角。`index.efl_mm == computed_efl_mm`（343/343 精确相等）。

## Ratified design (主公 via AskUserQuestion)
1. **分类规则**：telephoto ⟺ `computed_efl_mm ≥ 5.0 且 fov_deg ≤ 45.0`；elif `fov≥85` ultrawide；else wide。
   → 115 颗重标 telephoto（62 在 guard 界内可路由 + 53 深长焦<15°离开 wide 池）。
2. **真值来源 = 分类器（派生），不动数据文件**：load_case_library 加载后按 (fov, computed_efl)
   覆盖 baked scenario；e2_golden 也改用分类器派生 brief scenario（不读 index.json 旧标签）。
   index.json 不改（其 scenario 不参与路由；两个 case_library 消费者只读 image_height/edge-id）。
3. 不动 SCENARIO_BOUNDS → **无官网 drift**（telephoto guard 本就存在）。

## Tasks
- T1 `app/core/case_library.py`:
  - 加常量 `_TELEPHOTO_EFL_MIN=5.0`、`_TELEPHOTO_FOV_MAX=45.0`（近 line 147）。
  - `_classify_scenario(fov_deg, efl_mm)` 三档化。
  - 调用点 line 618 传 `computed_efl`。
  - `load_case_library()` 加载后覆盖 `metadata.scenario`（单一真值来源）。
- T2 `scripts/e2_golden.py:147`：brief scenario 改用 `_classify_scenario` 派生。
- T3 tests 反转 bug-as-expected：
  - `test_optical_match.py:1663` none→not-None + telephoto。
  - `test_optical_match.py:2011` 404→200 + telephoto seed。
  - `test_smoke_case_library.py:44` 允许集合加 telephoto。
- T4 `app/api/optical.py:651` 404 文案去掉 "wide/ultrawide only"（不再准确）。
- T5 新增分类/路由单测（`_classify_scenario` 各档 + telephoto 请求路由到真实 seed）。
- T6 重生成 `tests/data/eval_golden.json`（`uv run python scripts/e2_golden.py`），review diff。

## Verify
- `PYTHONUTF8=1 uv run pytest tests/test_optical_match.py tests/test_smoke_case_library.py tests/test_eval_golden_seeds.py tests/test_case_library.py tests/test_api_optical.py -q`
- 全量 `PYTHONUTF8=1 uv run pytest -q` 绿。
- telephoto 请求（EFL7/FOV30/f2.4）返回 200 + telephoto 真实 seed。
