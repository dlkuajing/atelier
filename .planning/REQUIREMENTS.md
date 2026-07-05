# Requirements — Atelier 独立演示产品 v1

按类别分组，REQ-ID 唯一。v1 = 第一里程碑（完整跑通一场含 CODE V 成果的客户演示）。

## v1 Requirements

### ENGINE — 双引擎与 CODE V 集成

- [x] **ENGINE-01**: 可插拔计算引擎抽象（Protocol/ABC + 注册表 + NullDeepEngine 默认），运行时探测 CODE V 可用性，无 CODE V 环境全链路降级纯 Optiland（CI/其他开发机测试可过）
- [x] **ENGINE-02**: 通用后台任务层：内存 JobStore + asyncio 任务 + 单席位信号量（防止双重占用 CODE V license），先用假引擎（SleepEngine）验证全部管线
- [ ] **ENGINE-03**: ZMX↔CODE V 互通 spike：导入专利 seed ZMX → CODE V 实算 → 导出回 ZMX → 过现有 ingest 比对指标一致性（非球面系数/玻璃目录/渐晕三大雷区必须逐项核对）
- [ ] **ENGINE-04**: CODE V 引擎适配器：.seq 宏生成 → 批量调起（subprocess）→ 结构化输出解析（宏内显式输出，不刮日志）→ 硬超时 + CPU 心跳（防隐形挂起）→ 逐项结果验证（退出码 0 不可信）
- [ ] **ENGINE-05**: CODE V 产物回灌：优化结果转 ZMX 走现有 zmx_ingest 流水线入库（ZMX 为唯一真相源，不造第二条数据路径）

### SEED — 专利 seed 可路由化（E2 头号工单）

- [ ] **SEED-01**: 专利 seed 真 IMH 实算（CODE V 或 Optiland 实算，替换 case_id token 缺失导致的 0.0）
- [ ] **SEED-02**: 路由重锚：match_case 用实算 IMH 重建距离度量，专利 seed 变为可路由
- [ ] **SEED-03**: eval golden 重锚：evaluate_design_agent 回归集更新并通过 --fail-on-regression

### ANLZ — 专家可信度分析补全（不依赖 CODE V）

- [x] **ANLZ-01**: 点列图（多视场 × 多波长网格 + Airy 半径叠加）— 设计师第一眼诊断
- [x] **ANLZ-02**: 场曲 + 畸变图（基于现有 Optiland 追迹数据的新分析模块）
- [x] **ANLZ-03**: 处方表视图（曲率半径/厚度/玻璃/非球面系数完整镜头数据表）
- [x] **ANLZ-04**: RMS 波前误差 / Strehl 比在界面呈现（区分"几何玩具"与"衍射感知的真工具"）

### SHOW — CODE V 深度成果展示（依赖 ENGINE）

- [ ] **SHOW-01**: 优化前后对比视图：Optiland 种子 vs CODE V 精修结果（MTF 曲线叠加 / 点列图收缩 / RMS 波前增量）— 双受众最高杠杆特性
- [ ] **SHOW-02**: 公差敏感度摘要：从 CODE V 批处理输出提取 top-N 敏感参数表 — 设计师可信度的压舱石
- [x] **SHOW-03**: "经 CODE V 交叉验证"背书标识 + 数据溯源标注（每个数字标明来源：实算追迹 / CODE V 运行，LLM 永不碰数值的架构事实要在界面上可见）

### UI — 演示前端（本地服务 + 浏览器）

- [x] **UI-01**: 演示界面覆盖完整叙事：自然语言需求输入 → 场景提取确认 → 设计生成（光路图/处方表/全套分析图）→ 评估报告 → CODE V 深度成果展示
- [x] **UI-02**: 长任务进度流：SSE 推送 CODE V 优化任务进度（与 LLM token 流分端点，避免队头阻塞）
- [x] **UI-03**: 双语呈现：现有双语执行摘要接入界面，术语向决策者做平实转译

### DATA — 手机镜头专利底库规模化（说服力基础）

- [ ] **DATA-01**: 同步 109 颗手机镜头 ZMX（lens-data-staging/，另一台电脑）进仓库并过 QC intake 流水线入库
- [x] **DATA-02**: 手机镜头专利规模化采集：patent_crawler（USPTO/Espacenet 双源）定向手机镜头设计专利（3P-7P，Largan/Sunny/舜宇/玉晶光等大厂 + 高引用），批量走 e2_intake QC 门 + 双源验证
- [ ] **DATA-03**: 底库规模目标：可路由 seed 总量 ≥500 颗（专利 seed 为主要来源，约 ≥370；主公 2026-07-03 定调），全部通过 audit_seed_intake 审计 + eval golden 回归，采集按批次滚动（复用 E2 批次模式）

### OPS — 演示可靠性

- [x] **OPS-01**: 一键启动：单命令拉起后端 + 前端，演示机可靠复现
- [x] **OPS-02**（机制完成：缓存/回退/失效指纹；CODE V 产物接入后复用）: 演示结果预缓存：所有演示案例的 CODE V 深度成果预先算好落盘，现场绝不实时依赖 license/网络（CODE V 是溯源背书，不是现场算力）
- [~] **OPS-03**（全叙事 E2E 自动化已过；attended 真人彩排待主公）: 完整演示彩排：核心叙事从头到尾跑通不翻车，含降级预案（里程碑验收标准）

## v2 Requirements (deferred)

- **SHOW-04**: 优化收敛可视化（merit function 随迭代下降曲线）— 叙事加强项，不阻塞首次彩排
- **SHOW-05**: 完整 Monte Carlo 良率分布图 — top-N 敏感度表验证受众反应后再深化

## Out of Scope

- 云端部署 / SaaS 多租户 — CODE V Windows-only 按席位授权，服务端化不可行且违反演示定位
- CODE V 进在线实时链路 / 现场实时跑深度优化 — 违反亚秒级约束 + 演示日最大翻车点
- Zemax OpticStudio 集成 — ZOS-API 性能烂账已实证弃选；引擎接口可插拔，未来有真实需求再加
- 原生工具全功能对齐（完整公差模块等）— 范围爆炸；只做证明概念的薄切片
- 零样本全拓扑 AI 生成 — 非当前 SOTA 实际能力，过度声称反伤可信度
- 与 lumira 官网互通 — 产品线已独立

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ENGINE-01 | Phase 1 | ✓ 批次1 |
| DATA-01 | Phase 2 | Pending |
| DATA-02 | Phase 2 | ✓ 批次2-4(94颗) |
| ENGINE-02 | Phase 3 | ✓ 批次1 |
| ANLZ-01 | Phase 4 | ✓ 批次2 |
| ANLZ-02 | Phase 4 | ✓ 批次2 |
| ANLZ-03 | Phase 4 | ✓ 批次2 |
| ANLZ-04 | Phase 4 | ✓ 批次2 |
| ENGINE-03 | Phase 5 | Pending |
| SEED-01 | Phase 6 | Pending |
| SEED-02 | Phase 6 | Pending |
| SEED-03 | Phase 6 | Pending |
| DATA-03 | Phase 6 | Pending |
| ENGINE-04 | Phase 7 | Pending |
| ENGINE-05 | Phase 7 | Pending |
| SHOW-01 | Phase 7 | Pending |
| SHOW-02 | Phase 7 | Pending |
| SHOW-03 | Phase 7 | ✓ 批次3 |
| UI-01 | Phase 8 | ✓ 批次2/3 |
| UI-02 | Phase 8 | ✓ 批次3 |
| UI-03 | Phase 8 | ✓ 批次3 |
| OPS-01 | Phase 9 | ✓ 批次4 |
| OPS-02 | Phase 9 | ✓ 批次4(机制) |
| OPS-03 | Phase 9 | ◐ 批次4(E2E) |

Coverage: 24/24 v1 requirements mapped.

---
*Last updated: 2026-07-03 after roadmap revision (added DATA phase)*
</content>
