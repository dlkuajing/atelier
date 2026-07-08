---
quick_id: 260708-telephoto-routing
date: 2026-07-08
status: complete
commit: 08e24d0
---

# Summary: 修复长焦404结构选型缺陷

## What shipped
两个可逆软件缺陷（非缺数据）修复，让 smartphone-telephoto 请求从 HTTP 404 变为路由到真实 seed。

- `app/core/case_library.py`
  - `_classify_scenario(fov_deg, efl_mm)` 多档化：`efl>=5.0 且 fov<=45 → telephoto`；`fov>=85 → ultrawide`；else wide。EFL 为长焦判据（`_TELEPHOTO_EFL_MIN`/`_TELEPHOTO_FOV_MAX`，与 telephoto guard 对齐）。
  - `load_case_library()` 加载时按存储 (fov, computed_efl) **重新派生** `metadata.scenario`，覆盖烙进 JSON 的旧标签 → 分类器成为唯一真值来源，零数据文件迁移。
  - 入库调用点传 `computed_efl`。
- `scripts/e2_golden.py`：golden brief scenario 改用分类器派生（与 load 路径同键 fov+efl，index.efl_mm==computed_efl_mm 全 343 相等），`tests/data/eval_golden.json` 重生成。
- `app/api/optical.py`：404 文案去掉不再准确的 "wide/ultrawide only"。
- `SCENARIO_BOUNDS` **未改** → 无官网 /agent 滑块 drift（drift 契约满足）。

## Footprint
343 seed → **115 重标 telephoto**（wide 312→197，ultrawide 31 不变）。62 在 telephoto guard 界内（可被请求命中），53 深长焦<15°（离开 wide 池但请求floor不可达）。

## Tests
- 反转 2 条"把 bug 当预期"的测试：`test_match_case_routes_telephoto_to_real_seed`（原 None）、`test_match_endpoint_telephoto_routes_to_real_seed`（原 404）。
- 新增 `test_classify_scenario_tiers`（各档 + EFL 判据反例 US-11933948-e8）、`test_telephoto_tier_is_populated_after_reclassification`（115 颗）。
- `test_case_library.py` 允许集合加 telephoto。
- **重锚 2 条 curated wide 测试**（主公 ratify）：`test_match_case_uses_ttl_and_design_intent` 与 `test_full_field_proposals_block_on_quality_floor`。根因=洁净 wide 候选池（移除115长焦）收窄 FOV 归一化范围→ TTL 软惩罚 probe 翻选。诚实重锚（保留意图：TTL tradeoff 显式暴露，非隐藏）。

## Verification
- 全量 `pytest -n 8`：**1442 passed, 3 skipped(Code-V), 0 failed**。
- 直接行为验证：telephoto 请求(EFL7/FOV30)→US-12416792-B2-e12(telephoto 真实 seed)；wide/ultrawide 路由不变。
- code-simplifier：clean，无改动。ruff：无新增违规（1 处 I001 为既有、未触碰 import 块）。
- 对抗式多 agent 审查（4 维 review→verify）：3 raw findings **全部 REFUTED**，0 confirmed。

## Ratified decisions (主公 via AskUserQuestion)
1. 分类规则 = EFL≥5 且 FOV≤45 → telephoto。
2. 真值来源 = 加载时派生（非数据迁移）。
3. TTL-normalization 副作用：直接上线 + 重锚 2 测试。

## Follow-ups (out of scope)
- RAG 专利检索（`rag/store.py`）读 index.json 的 stale scenario → telephoto 检索返回空（主公已知/接受 no-data-diff 后果）。
- 按 drift 双打契约 cherry-pick 回 `lumira/lumira-backend`。
