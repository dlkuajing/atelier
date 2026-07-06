# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-03)

**Core value:** 资深光学设计师看了演示产出不能觉得"比不过"——专家级可信度是唯一不可失守的东西
**Current focus:** Phase 1 (引擎抽象与降级)

## Current Position

Phase: 完成 1/3/4/5/7/8，Phase 6 余规模门（可路由案例 106，原料池 354→主公裁定扩至 2000-3000，转换产率 26.7%=spike 3.7 倍），进行中 2/9；Phase 9 首轮 AI 彩排完成（2 必修雷修复中=车道c 批次10）
Plan: 夜车模式（gsd-loop 垂直切片）替代 phase-plan 执行
Status: 九批次 40 切片已合 main(798c5fd)，测试 131→690，案例库 39→106 颗
Last activity: 2026-07-06 — 批次9收官：多实施例+XASPHERE 放量/67 颗批量入库（案例库 106）/golden 全库覆盖；采集批次6+7（池 354，Largan 36%）；提速改造（三车道+班车+天花板 97）

Progress: [████████░░] ~82%（余：规模门放量、演示雷修复、终验彩排）

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Deep engine = CODE V (macro-batch, not interactive API); dual-engine architecture (Optiland fast + CODE V deep)
- Product form = local service + browser (no desktop shell)
- ZMX interop spike sequenced before real CODE V adapter (research-confirmed ordering)
- Zemax OpticStudio rejected (ZOS-API per-call overhead 10s→118s measured)
- Patent-library scale-up (DATA-01/02) inserted as Phase 2: uses existing patent_crawler/e2_intake/generate_cases/audit_seed_intake pipeline, independent of CODE V engine work, can run parallel to Phase 1/3
- DATA-03 (≥500 routable seed, patent-majority; 主公 2026-07-03 将目标从 150 上调至 500) acceptance gate folded into Phase 6 (专利 seed 可路由化), not Phase 2 — patent seeds only count as "routable" after real-IMH reanchor closes

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

- Phase 5 已在本机 CODE V 11.5 实测关闭；后续 Phase 7 仍需保持无 CODE V 环境可降级，真实深引擎成果只在演示机/预计算路径依赖 CODE V。
- CODE V's authoritative Macro-PLUS CLI/output-format details are gated behind a licensed docs portal — must be read from the installed manual during Phase 5, not assumed from secondary sources.
- COM fallback path (if batch mode proves insufficient) has no verified Python+CODE V sample anywhere — would need a dedicated research pass if triggered.
- DATA-01 external dependency: 109 手机镜头 ZMX 位于另一台电脑（lens-data-staging/），需主公先行同步至可访问位置，Phase 2 无法自行解除此依赖。

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 requirement | SHOW-04: 优化收敛可视化 | Deferred | Initial requirements definition |
| v2 requirement | SHOW-05: 完整 Monte Carlo 良率分布图 | Deferred | Initial requirements definition |

## Session Continuity

Last session: 2026-07-05
Stopped at: 状态回写补账；夜车 backlog 已空待批次5蒸馏
Resume file: None
