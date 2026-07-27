# Project State

## Project Reference

唯一目标真相锚 = `.planning/NORTH-STAR.md`（v2，2026-07-27）。术语 = `CONTEXT.md`。
另见 `.planning/PROJECT.md` 与 `AGENTS.md`。

**北极星 v2 摘要：** 把手机镜头「出一版设计」这个动作自动化——结构化 spec → 交付物，
零人工介入，多需求覆盖，质量对标同规格专利原设计。价值 = 产能放大。
四条判据全部可复算、不需要人类签字。

**命名：** `production-ready` / "生产可用"是 loop2 时期的工程代号，不是量产可用结论。

## Current Position

| Scope | Status |
|---|---|
| 北极星 v2 | ACTIVE（2026-07-27 主公经 grilling 六轮逐条裁定并落盘）。`N` / 异源打平率门槛 / `T` 三个数值**待实测**。 |
| 北极星 v0.1 A–F 治理协议 | **SUPERSEDED**，冻结于 `.planning/archive/north-star-v0.1/`。不再是 gate、判据或工作源，不消耗 loop 预算。 |
| Phase 13 glass-snap 铲3 | 完成；PR #74，matrix v7 20/20 可执行格。 |
| Phase 14 TOR 铲2 | 完成；PR #68。默认公差表在 v2 下**不再需要专家 ratify**（同表同施于候选与对照，排序不变），但 MC 饱和仍是真实病灶。 |
| Phase 15 Stage B F/# | 完成；PR #75。F/# 仅由候选自己的 closed ladder gate 条件授予。 |
| Phase 17 close-out | 完成；PR #71。ZMX 持久化与串行 repeat engine 落地。 |
| Phase 18 batch | 完成；PR #72/#77/#80。50/50：29 succeeded、21 degraded、0 failed。 |
| Phase 16 Stage C | 完成技术证据闭环；PR #76/#78/#79/#81。48-run matrix + 单 exact target production/export。 |
| ROADMAP 九阶段 | 阶段划分成型于 v0.1 体系下，**须按 v2 判据重新对齐**（未做）。 |

**Release truth:** PR #81 merge `9249f97834a3bff52bb38e3e6ff456c7ec0aaec3`；PR CI run
`29227838587` success；匹配 merge SHA 的 main CI run `29229500265` success。
Loop2 G docs PR #82 merge `d35b3d07cead830396d24d2b10665199c73985e0`；匹配 main CI run
`29233888562` success。

## Evidence Snapshot

以下数字产生于 v0.1 体系，**在 v2 下不自动继承任何含义**；重新计量须按 `NORTH-STAR.md` 判据口径。

- **P18**：50 targets / 50 jobs / 50 valid CandidateSets；29 succeeded / 21 degraded / 0 failed。
  污染的 job-0020/0021 attempt-1 永久排除。
- **Stage B**：8/8 unique accepted，30 outcomes，6 pre-run-bound + 2 retrospective，no incomplete。
  manifest SHA256 `29384d5d9a10356c8b9bd908c48ab6970977fcafe77ac59a100aaf268350d969`。
- **Stage C**：48/48 receipts，**2 delivered / 46 blocked**；6/48 run metrics usable；3/24 cells complete。
  ← 这是 v2 判据 ① 的当前真实基线：产能不是放大，是堵塞。
- **Production**：仅 `US9304295B2` 一个 exact target 完成 fresh Stage B → Stage C receipt →
  candidate → exports-v2 同源闭环；外层 C1 CLI exit=1。
- **Convergence**：`TARGET_CONVERGED` capability ceiling 为 `efl + conditional fnum`；
  IMH 可被 Stage C 证明 achieved 但非 Stage B converged；FOV derived/measured-only。
- **Case library**：442 = smartphone-wide 227 / telephoto 137 / ultrawide 78；442/442 `image_height_mm` 非空。
  ← v2 下这 442 颗的角色从"说服力素材"升级为**统计对照组**。
- **旗舰候选**：RMS 2.80µm（片数/规格与外部参考的可比性**未核**，不得直接对外比较）。

## Blockers / Concerns

**v2 体系下的真实阻塞：**

- **判据 ① 基线极差**：Stage C 2/46。零介入多需求产出能力是当前头号缺口。
- **判据 ② 无数据**：异源跨规格泛化能力从未系统实测。memory 记录 `缩焦全收敛 / 拉焦 +25% 起挂`
  （2026-07-09 观察，需重新核实）。**`N` 与打平率门槛必须等这轮摸底数据才能填。**
- **判据 ③ 缺两件**：公差良率（MC 饱和 → yield unavailable）与相对成本指数（模型不存在）
  均未落地。四件套目前只有处方 + 像质两件。
- **CODE V 并发安全**：当前低层启动链与用户级可替换锁不构成单实例保证；直接 `Popen`
  与 Web/CLI/batch/probe/test 多个启动面未收口。真机跑批前必须解决——这是**普通工程需求**，
  按普通 backlog 项处理，**不再套 v0.1 的密码学签名链**。
  参考 `.planning/archive/north-star-v0.1/backlog.md` 的 M-01~M-06 节（仅取工程内容）。
- **存量工单**：unknown dispersion provenance、专利 WAVM 24 槽化、5P MTF NaN、
  P13 GLD/withheld EFL、Stage B listing/WRX/WRY、C1 artifact-key collision。
- **外部依赖**：另一台电脑的 109 颗 staging ZMX；商用/合规定位（待主公决策）。

**已解除的阻塞（v0.1 遗留，v2 下不再成立）：**

- ~~NEED 资深：TOR 默认公差表 ratification~~ → v2 用相对比较，公差表绝对值不影响排序。
- ~~NEED 人类 minimum-claim authority / custody / clock attester~~ → 整套治理协议已废。
- ~~13 棵固定树不得发布~~ → 该发布链随 v0.1 归档，不再适用。

## Session Continuity

**新 session 起手**：读 `.planning/NORTH-STAR.md` → 根 `CONTEXT.md` → 本文件 → `.planning/loop/backlog.md`。

**不要**从 `.planning/archive/north-star-v0.1/` 恢复任何 gate、backlog 或判据——它是冻结归档。

**真机前提**：不要从 chat memory 恢复 P18 或 Stage C runner。任何 CODE V 调用前先确认
`runner` / `codev` / `codevm` 相关进程为零，并复核保留的 ledger/artifact 哈希。
