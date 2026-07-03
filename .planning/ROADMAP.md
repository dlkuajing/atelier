# Roadmap: Atelier — 光学设计 Agent 独立演示产品

## Overview

从现有确定性光学后端（Optiland 快引擎、案例库、Wizard LLM 编排）出发，构建可插拔双引擎架构，先用 Null/Sleep 引擎把抽象层和异步任务层跑通（不依赖 CODE V 安装），再做 ZMX↔CODE V 互通 spike 验证转换保真度，随后接入真实 CODE V 适配器并解决专利 seed 路由死结，补全专家级分析视图，搭建本地演示前端，最终一键启动 + 完整彩排收尾。CODE V 安装是外部依赖，前几个阶段必须在没有 CODE V 的机器上（含 CI）可执行可测试。手机镜头专利底库规模化采集不依赖 CODE V、不依赖引擎抽象，使用现有 patent_crawler/e2_intake/generate_cases/audit_seed_intake 流水线，可在早期与引擎工作并行推进；但底库"可路由 seed 规模"验收门只能在专利 seed 可路由化（真 IMH 实算）完成后才能真正关闭。

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: 引擎抽象与降级** - 可插拔计算引擎接口 + NullDeepEngine + 运行时探测，全链路无 CODE V 可跑通
- [ ] **Phase 2: 专利底库规模化采集** - 同步 109 颗 staging ZMX + 双源专利定向采集入库，为规模验收打底（可与 Phase 1/3 并行）
- [ ] **Phase 3: 通用后台任务层** - 假引擎（SleepEngine）验证异步任务 + SSE 进度流 + 单席位信号量
- [ ] **Phase 4: 专家分析补全** - 点列图/场曲畸变/处方表/波前误差 RMS·Strehl，不依赖 CODE V
- [ ] **Phase 5: ZMX↔CODE V 互通 Spike** - 专利 seed ZMX 实算往返，非球面/玻璃/渐晕三项一致性核对
- [ ] **Phase 6: 专利 seed 可路由化与底库规模验收** - 真 IMH 实算、路由重锚、eval golden 重锚、底库规模门（≥500 可路由 seed，专利 seed 为主要来源）关闭
- [ ] **Phase 7: CODE V 引擎适配器与深度成果展示** - 真实 .seq 批处理适配器 + 优化前后对比 + 公差敏感度 + 溯源标注
- [ ] **Phase 8: 演示前端** - 本地服务 + 浏览器界面，覆盖需求到 CODE V 成果全叙事
- [ ] **Phase 9: 一键启动与演示彩排** - 单命令拉起 + 预缓存 + 完整彩排（里程碑验收）

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

### Phase 2: 专利底库规模化采集
**Goal**: 把手机镜头专利/staging 设计规模化收入案例库，为"专家级说服力"的数据规模基础做准备；使用既有采集/摄入流水线，不依赖引擎抽象或 CODE V，可与 Phase 1/3 并行推进
**Depends on**: Nothing (独立于引擎工作；可并行执行)
**Requirements**: DATA-01, DATA-02
**Success Criteria** (what must be TRUE):
  1. lens-data-staging/ 的 109 颗手机镜头 ZMX 已同步进本仓库 data/zmx/ 并全部过 QC intake 流水线（audit_seed_intake 无阻断性失败）
  2. patent_crawler 已针对手机镜头设计专利（3P-7P，覆盖 Largan/Sunny/舜宇/玉晶光等大厂 + 高引用专利）完成定向规模化采集，双源（USPTO/Espacenet）交叉验证通过
  3. 新采集案例全部走 e2_intake QC 门 + generate_cases 正式生成 case_id，与既有 39 案例共存于同一案例库结构下
**Plans**: TBD
**Note**: DATA-01 有外部依赖——109 颗 ZMX 文件位于另一台电脑（lens-data-staging/），需主公先行同步至可访问位置或本仓库。此依赖不由本阶段内工作解除。

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
  1. 至少一个专利 seed ZMX 案例完成 CODE V 往返，导出结果可被现有 zmx_ingest 正常解析
  2. 往返前后 EFL 误差 <2%，且逐面玻璃 nd/vd 数值差异、非球面项数差异被明确记录（非仅"能解析"）
  3. 渐晕字段（VDX/VDY）在往返后未丢失
  4. CODE V 实际调用方式（可执行文件/CLI 参数/输出格式）已从安装后的 Macro-PLUS 手册确认并记录，不再依赖二手资料假设
**Plans**: TBD

### Phase 6: 专利 seed 可路由化与底库规模验收
**Goal**: 解除专利 seed 因 IMH=0.0 导致的不可路由死结，使其成为可被匹配、可被评估回归覆盖的正式案例；在此基础上关闭底库规模验收门（Phase 2 采集的案例只有在真 IMH 重锚后才计入"可路由 seed"）
**Depends on**: Phase 5, Phase 2
**Requirements**: SEED-01, SEED-02, SEED-03, DATA-03
**Success Criteria** (what must be TRUE):
  1. 全部专利 seed 案例（含 Phase 2 新采集的批次）拥有实算得出的真实 IMH（不再是 0.0 占位）
  2. match_case 使用实算 IMH 重建的距离度量，可将专利 seed 作为最近邻候选返回
  3. evaluate_design_agent 回归集通过 --fail-on-regression，覆盖重锚后的专利 seed
  4. 可路由 seed 总量 ≥500 颗（专利 seed 为主要来源；主公 2026-07-03 定调，采集按批次滚动），全部通过 audit_seed_intake 审计
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
  3. 核心演示叙事从头到尾完整跑通至少一次不翻车，且降级路径（无 CODE V）被显式演练过
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order with one parallel branch: 1 and 2 can start together → 3, 4 (after 1) → 5 (after 1) → 6 (after 5 and 2) → 7 (after 3 and 5) → 8 (after 4 and 7) → 9 (after 8)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. 引擎抽象与降级 | 0/TBD | Not started | - |
| 2. 专利底库规模化采集 | 0/TBD | Not started | - |
| 3. 通用后台任务层 | 0/TBD | Not started | - |
| 4. 专家分析补全 | 0/TBD | Not started | - |
| 5. ZMX↔CODE V 互通 Spike | 0/TBD | Not started | - |
| 6. 专利 seed 可路由化与底库规模验收 | 0/TBD | Not started | - |
| 7. CODE V 引擎适配器与深度成果展示 | 0/TBD | Not started | - |
| 8. 演示前端 | 0/TBD | Not started | - |
| 9. 一键启动与演示彩排 | 0/TBD | Not started | - |
