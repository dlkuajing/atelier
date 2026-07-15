# Roadmap: Atelier — 光学设计 Agent 独立演示产品

## Overview

从现有确定性光学后端（Optiland 快引擎、案例库、Wizard LLM 编排）出发，构建可插拔双引擎架构，先用 Null/Sleep 引擎把抽象层和异步任务层跑通（不依赖 CODE V 安装），再做 ZMX↔CODE V 互通 spike 验证转换保真度，随后接入真实 CODE V 适配器并解决专利 seed 路由死结，补全专家级分析视图，搭建本地演示前端，最终一键启动 + 完整彩排收尾。CODE V 安装是外部依赖，前几个阶段必须在没有 CODE V 的机器上（含 CI）可执行可测试。手机镜头专利底库穷尽不依赖 CODE V、不依赖引擎抽象；现有 patent_crawler/patent_to_zmx/e2_intake/generate_cases/audit_seed_intake 是起点，但验收终点已从历史“≥500”改为选定公开来源游标耗尽、逐专利族/逐 embodiment 唯一终态、冻结池确定性回放无新增 seed，并保持正式 seed 全部真实 IMH 可路由。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: 引擎抽象与降级**（2026-07-04 夜车批次1，PR #1） - 可插拔计算引擎接口 + NullDeepEngine + 运行时探测，全链路无 CODE V 可跑通
- [~] **Phase 2: 专利底库穷尽采集**（进行中：2026-07-15 基线为 714 个 USPTO 根、442 个正式设计；无全文湖、无 source exhausted 证据） - 建原始专利湖、官方族归并、可恢复游标和逐记录终态账本，按最大失败桶持续回放（可与其他阶段并行）
- [x] **Phase 3: 通用后台任务层**（2026-07-04 夜车批次1，PR #1） - 假引擎（SleepEngine）验证异步任务 + SSE 进度流 + 单席位信号量
- [x] **Phase 4: 专家分析补全**（2026-07-04/05 批次2+3，PR #2/#3/#10 含数值锚点与版本守卫） - 点列图/场曲畸变/处方表/波前误差 RMS·Strehl，不依赖 CODE V
- [x] **Phase 5: ZMX↔CODE V 互通 Spike**（2026-07-05 批次5+6）- 探测/批处理链路/导入实算真 IMH/DB 读数重建 ZMX 全通；CODE V 11.5 无原生 ZMX 导出（WRL 只出 .seq），已采用 04a 数据库读数 + 04b 自研 ZMX writer 关闭回程闭环；`US20170003482A1.zmx` 往返四项保真全过（EFL 偏差 `3.19e-13%`，逐面 nd/vd 无 mismatch，非球面项数保持 S1-S15 各 8 项，VDX/VDY 未丢失），证据见 `.planning/loop/codev-roundtrip-report.md`
- [~] **Phase 6: 专利 seed 可路由化与饱和验收**（历史判据1-3 完成 2026-07-06 批次7，PR #22；饱和判据进行中）- 正式库现有 442/442 非空 IMH；剩余验收不是固定数量，而是全部发现记录唯一终态、正式工件一致、冻结池回放无新增 seed、来源 exhausted 证据闭环
- [x] **Phase 7: CODE V 引擎适配器与深度成果展示**（2026-07-06 批次8，PR #24；SHOW-03 先期 PR #8）- AUT 优化适配器（EFL 锁定/玻璃冻结，US20170003482A1 实测 RMS spot ↓61%/横向色差 ↓92%/波前 ↓86%）+ 并排对比视图（MTF 双频轴叠加）+ CODE V 扰动敏感度 top-N 表 + 溯源从产物 run 证据推导（夹具/降级禁标 codev-run）；优化产物 readout→zmx_writer→zmx_ingest 单一路径；真实预缓存产物入库支持断网演示
- [x] **Phase 8: 演示前端**（批次3+4：骨架/输入流/SSE进度/双语摘要/结果页整合叙事，PR #4/#7/#11） - 本地服务 + 浏览器界面，覆盖需求到 CODE V 成果全叙事
- [~] **Phase 9: 一键启动与演示彩排**（一键启动+预缓存机制+全叙事E2E已完成 PR #12/#14；两段式彩排第一段完成：三遍彩排零瑕疵，待主公终验） - 单命令拉起 + 预缓存 + 完整彩排（里程碑验收）
- [ ] **Phase 10: 量产设计产出引擎探路（C1 多产编排 + 良品率 go/no-go 闸）**（2026-07-08 北极星转向探路阶，非完整里程碑） - 建"朝客户 target 收敛 + 落地交付"的优化编排（现状 AUT 锁 seed 自身焦距/玻璃不变/产物仅离线展示），对给定需求批量产出量产级候选；请资深设计师实测筛一批，量化"值得看一眼率（良品率）"作为整个"设计引擎"北极星的 go/no-go 闸

## Phase Details

### Phase 1: 引擎抽象与降级
**Goal**: 建立计算引擎的可插拔抽象，使后续所有阶段（包括没有 CODE V 的开发机和 CI）都能在统一接口下开发和测试
**Depends on**: Nothing (first phase)
**Requirements**: ENGINE-01
**Success Criteria** (what must be TRUE):
  1. 系统启动时自动探测 CODE V 是否可用，无需人工配置
  2. 无 CODE V 环境下，现有全部光学计算路径（追迹/MTF/评估）行为不变，测试全绿
  3. 引擎接口对 FastEngine（Optiland 包装）和 NullDeepEngine 提供一致调用契约
**Plans**: TBD

### Phase 2: 专利底库穷尽采集
**Goal**: 将合法公开、可重复获取的手机镜头专利分层收入原始专利湖，完成官方族归并、全文/处方恢复、确定性转换与十类唯一终态；500 仅为历史标记，不构成停止条件
**Depends on**: Nothing (独立于引擎工作；可并行执行)
**Requirements**: DATA-01, DATA-02
**Success Criteria** (what must be TRUE):
  1. 所有选定官方数据源、CPC/IPC、查询族和受让人别名的分页游标均有可重算 exhausted 证据，并建立截止日后的增量游标
  2. 所有发现记录完成官方专利族归并；每个专利根和每个已知 embodiment 恰有一个允许的结构化终态，无 unknown/静默跳过/临时 staging 遗留
  3. 原始全文/图像/OCR 与正式 seed 分层保存；任何正式入库均有确定性处方、完整 provenance、质量闸、真实 IMH、物理合理性、去重和路由验收证据
  4. 同一冻结原始池完整回放不再产生新 seed，账本与工件哈希可复现
**Plans**: TBD
**Note**: 109 颗外部 `lens-data-staging/` ZMX 当前不可得，不计入本阶段可用资产或完成依赖。

### Phase 3: 通用后台任务层
**Goal**: 提供长任务的异步执行 + 进度推送基础设施，在真实 CODE V 存在之前用假引擎验证全链路
**Depends on**: Phase 1
**Requirements**: ENGINE-02
**Success Criteria** (what must be TRUE):
  1. 提交一个假的长任务（SleepEngine）后可通过 SSE 实时看到进度更新直到完成
  2. 同时提交第二个任务时被单席位信号量正确阻塞/排队，不会并发抢占
  3. 任务记录（状态/结果/错误）在进程内可查询，无需外部依赖（Redis/Celery）
**Plans**: TBD

### Phase 4: 专家分析补全
**Goal**: 补齐资深设计师第一眼诊断所需的分析视图，全部基于现有 Optiland 追迹数据，不依赖 CODE V
**Depends on**: Phase 1
**Requirements**: ANLZ-01, ANLZ-02, ANLZ-03, ANLZ-04
**Success Criteria** (what must be TRUE):
  1. 任意设计可生成多视场×多波长点列图，并叠加 Airy 斑半径作为衍射极限参考
  2. 任意设计可生成场曲与畸变图
  3. 任意设计可查看完整处方表（曲率半径/厚度/玻璃/非球面系数）
  4. 任意设计可查看 RMS 波前误差与 Strehl 比数值
**Plans**: TBD
**UI hint**: yes

### Phase 5: ZMX↔CODE V 互通 Spike
**Goal**: 在真实代码路径依赖 CODE V 之前，验证 ZMX 导入→CODE V 实算→导出回 ZMX 的转换保真度，摸清 CODE V 真实调用机制
**Depends on**: Phase 1 (需要引擎抽象作为集成点；实际验证需 CODE V 已安装)
**Requirements**: ENGINE-03
**Success Criteria** (what must be TRUE):
  1. 实测结论（2026-07-05）：`US20170003482A1.zmx` 已完成 CODE V 导入 → 04a 数据库读数 → 04b 重建 `exported.zmx`，导出结果可被现有 `zmx_ingest` 正常解析
  2. 实测结论（2026-07-05）：往返 EFL 误差 `3.19e-13%`（<2%），逐面玻璃 nd/vd 无 mismatch，非球面项数保持 S1-S15 各 8 项
  3. 实测结论（2026-07-05）：渐晕字段 `VDX=(0,0,0)`、`VDY=(0,0,0)` 在往返后未丢失
  4. CODE V 实际调用方式（可执行文件/CLI 参数/输出格式）已从安装后的 Macro-PLUS 手册确认并记录，不再依赖二手资料假设
**Plans**: TBD

### Phase 6: 专利 seed 可路由化与饱和验收
**Goal**: 保证每个通过 Phase 2 转换的设计只有在真实 IMH、可追迹性、物理合理性、同族/处方去重、质量闸和路由验收全部通过后才进入正式库，并闭合全库一致性与冻结池饱和证明
**Depends on**: Phase 5, Phase 2
**Requirements**: SEED-01, SEED-02, SEED-03, DATA-03
**Success Criteria** (what must be TRUE):
  1. 全部专利 seed 案例（含 Phase 2 新采集的批次）拥有实算得出的真实 IMH（不再是 0.0 占位）
  2. match_case 使用实算 IMH 重建的距离度量，可将专利 seed 作为最近邻候选返回
  3. evaluate_design_agent 回归集通过 --fail-on-regression，覆盖重锚后的专利 seed
  4. 正式底库、ZMX、案例索引、路由 golden、统计报告和 provenance 完全一致；冻结池完整回放无新增合格 seed，全部测试/CI/独立只读审查/PR/main CI 闭环
**Plans**: TBD

### Phase 7: CODE V 引擎适配器与深度成果展示
**Goal**: 接入真实 CODE V 深引擎，并将其优化产物转化为客户可见的、有溯源标注的对比叙事
**Depends on**: Phase 3, Phase 5
**Requirements**: ENGINE-04, ENGINE-05, SHOW-01, SHOW-02, SHOW-03
**Success Criteria** (what must be TRUE):
  1. 提交一个真实设计到 CODE V 深引擎后，系统生成 .seq 批处理并返回结构化解析结果（非日志刮取），异常挂起时硬超时可靠终止
  2. CODE V 优化结果通过现有 zmx_ingest 流水线正式入库，不存在第二条数据路径
  3. 界面可并排查看 Optiland 种子设计 vs CODE V 精修结果（MTF 曲线叠加/点列图收缩/RMS 波前增量）
  4. 界面展示 CODE V 批处理输出中提取的 top-N 公差敏感参数表
  5. 每个展示数值标注来源（实算追迹 / CODE V 运行），带"经 CODE V 交叉验证"标识
**Plans**: TBD

### Phase 8: 演示前端
**Goal**: 提供本地浏览器界面，让需求输入到 CODE V 深度成果的完整叙事可被现场演示
**Depends on**: Phase 4 (可提前并行), Phase 7 (深度成果视图依赖)
**Requirements**: UI-01, UI-02, UI-03
**Success Criteria** (what must be TRUE):
  1. 用户在浏览器中输入自然语言需求后，可依次看到场景提取确认、设计生成（光路图/处方表/分析图）、评估报告、CODE V 深度成果
  2. CODE V 长任务的进度通过独立 SSE 端点推送，不与 LLM token 流争用同一连接
  3. 界面呈现双语执行摘要，决策者可读到平实语言转译而非纯技术术语
**Plans**: TBD
**UI hint**: yes

### Phase 9: 一键启动与演示彩排
**Goal**: 确保演示机可单命令可靠复现全流程，且现场不依赖实时 CODE V 算力
**Depends on**: Phase 8
**Requirements**: OPS-01, OPS-02, OPS-03
**Success Criteria** (what must be TRUE):
  1. 单条命令即可同时拉起后端与前端服务，无需手动分步操作
  2. 演示案例的 CODE V 深度成果已预先算好落盘，现场断网/无 license 时仍可展示完整叙事
  3. 两段式彩排第一段已完成：核心演示叙事三遍彩排零瑕疵，含降级路径显式演练；第二段待主公终验
**Plans**: TBD

### Phase 10: 量产设计产出引擎探路（C1 多产编排 + 良品率 go/no-go 闸）
**Goal**: 验证"AI 多产量产级候选 + 资深筛判"这个产出-判断分工是否成立——核心是量化 AI 候选良品率（值得资深看一眼/接近可用率），作为北极星转向的 go/no-go 闸
**Depends on**: Phase 7（CODE V 优化适配器）, Phase 6（可路由 seed）
**Requirements**: TBD（探路阶，闸过后再正式立 requirements 与完整里程碑）
**Success Criteria** (what must be TRUE):
  1. 优化编排能对给定客户 target（EFL/FOV/像质）批量产出朝 target 收敛的候选（不再锁 seed 自身焦距、材料可参与），而非仅锁 seed 焦距做像质微调
  2. 候选携带资深判断所需依据（至少分频 MTF + 真公差敏感度/良率〔接 CODE V TOR〕 + 相对照度），支撑"快速筛判"
  3. 至少一位资深光学设计师实测筛一批候选，量化良品率，形成 go/no-go 结论
**Plans**: TBD
**Note**: 里程碑级转向的探路阶，非完整里程碑。良品率闸过→启动完整 new-milestone（重写 PROJECT.md 定位/用户/Out of Scope + 重排路线图）；不过→回看模型/seed/优化，不 sink 完整规划成本。量产"合格/可用"真值判断权在资深设计师（[EXPERT] 红线，不可 AI 代填）。

## Progress

**Execution Order:**
Phases execute in numeric order with one parallel branch: 1 and 2 can start together → 3, 4 (after 1) → 5 (after 1) → 6 (after 5 and 2) → 7 (after 3 and 5) → 8 (after 4 and 7) → 9 (after 8)；Phase 10 探路阶 after 6+7（北极星转向 go/no-go 闸）

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. 引擎抽象与降级 | 0/TBD | Not started | - |
| 2. 专利底库穷尽采集 | GSD quick active | In progress（714 根基线账本已建立，来源/全文/终态未饱和） | - |
| 3. 通用后台任务层 | 0/TBD | Not started | - |
| 4. 专家分析补全 | 0/TBD | Not started | - |
| 5. ZMX↔CODE V 互通 Spike | 0/TBD | Completed | 2026-07-05 |
| 6. 专利 seed 可路由化与饱和验收 | GSD quick active | In progress（442 正式设计；全池终态与回放未闭） | - |
| 7. CODE V 引擎适配器与深度成果展示 | 0/TBD | Not started | - |
| 8. 演示前端 | 0/TBD | Not started | - |
| 9. 一键启动与演示彩排 | 0/TBD | In progress（第一段彩排完成，待主公终验） | - |
| 10. 量产设计产出引擎探路 | 0/TBD | Not started | - |
