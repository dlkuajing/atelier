# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-03)

**Core value:** 资深光学设计师看了演示产出不能觉得"比不过"——专家级可信度是唯一不可失守的东西
**Current focus:** Phase 1 (引擎抽象与降级)

## Current Position

Phase: 完成 1/3/4/5/8，进行中 2/7/9；Phase 5 已用 04a 数据库读数 + 04b ZMX 重建关闭 CODE V 回程闭环，下一阻塞点=attended 彩排(Phase 9)
Plan: 夜车模式（gsd-loop 垂直切片）替代 phase-plan 执行
Status: 五批次 23 切片已合 main(f9d1431)，测试 131→319
Last activity: 2026-07-05 — ENGINE-04c 闭环验收：US20170003482A1.zmx → CODE V 导入 → 04a 读数 → 04b 重建 exported.zmx → compare_roundtrip_zmx，四项保真 PASS

Progress: [█████░░░░░] ~50%（按 24 需求中 14 完成/2 部分计）

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
