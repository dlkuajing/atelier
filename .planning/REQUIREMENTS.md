# Requirements — Atelier 独立演示产品 v1

按类别分组，REQ-ID 唯一。v1 = 第一里程碑（完整跑通一场含 CODE V 成果的客户演示）。

## v1 Requirements

### ENGINE — 双引擎与 CODE V 集成

- [ ] **ENGINE-01**: 可插拔计算引擎抽象（Protocol/ABC + 注册表 + NullDeepEngine 默认），运行时探测 CODE V 可用性，无 CODE V 环境全链路降级纯 Optiland（CI/其他开发机测试可过）
- [ ] **ENGINE-02**: 通用后台任务层：内存 JobStore + asyncio 任务 + 单席位信号量（防止双重占用 CODE V license），先用假引擎（SleepEngine）验证全部管线
- [ ] **ENGINE-03**: ZMX↔CODE V 互通 spike：导入专利 seed ZMX → CODE V 实算 → 导出回 ZMX → 过现有 ingest 比对指标一致性（非球面系数/玻璃目录/渐晕三大雷区必须逐项核对）
- [ ] **ENGINE-04**: CODE V 引擎适配器：.seq 宏生成 → 批量调起（subprocess）→ 结构化输出解析（宏内显式输出，不刮日志）→ 硬超时 + CPU 心跳（防隐形挂起）→ 逐项结果验证（退出码 0 不可信）
- [ ] **ENGINE-05**: CODE V 产物回灌：优化结果转 ZMX 走现有 zmx_ingest 流水线入库（ZMX 为唯一真相源，不造第二条数据路径）

### SEED — 专利 seed 可路由化（E2 头号工单）

- [ ] **SEED-01**: 专利 seed 真 IMH 实算（CODE V 或 Optiland 实算，替换 case_id token 缺失导致的 0.0）
- [ ] **SEED-02**: 路由重锚：match_case 用实算 IMH 重建距离度量，专利 seed 变为可路由
- [ ] **SEED-03**: eval golden 重锚：evaluate_design_agent 回归集更新并通过 --fail-on-regression

### ANLZ — 专家可信度分析补全（不依赖 CODE V）

- [ ] **ANLZ-01**: 点列图（多视场 × 多波长网格 + Airy 半径叠加）— 设计师第一眼诊断
- [ ] **ANLZ-02**: 场曲 + 畸变图（基于现有 Optiland 追迹数据的新分析模块）
- [ ] **ANLZ-03**: 处方表视图（曲率半径/厚度/玻璃/非球面系数完整镜头数据表）
- [ ] **ANLZ-04**: RMS 波前误差 / Strehl 比在界面呈现（区分"几何玩具"与"衍射感知的真工具"）

### SHOW — CODE V 深度成果展示（依赖 ENGINE）

- [ ] **SHOW-01**: 优化前后对比视图：Optiland 种子 vs CODE V 精修结果（MTF 曲线叠加 / 点列图收缩 / RMS 波前增量）— 双受众最高杠杆特性
- [ ] **SHOW-02**: 公差敏感度摘要：从 CODE V 批处理输出提取 top-N 敏感参数表 — 设计师可信度的压舱石
- [ ] **SHOW-03**: "经 CODE V 交叉验证"背书标识 + 数据溯源标注（每个数字标明来源：实算追迹 / CODE V 运行，LLM 永不碰数值的架构事实要在界面上可见）

### UI — 演示前端（本地服务 + 浏览器）

- [ ] **UI-01**: 演示界面覆盖完整叙事：自然语言需求输入 → 场景提取确认 → 设计生成（光路图/处方表/全套分析图）→ 评估报告 → CODE V 深度成果展示
- [ ] **UI-02**: 长任务进度流：SSE 推送 CODE V 优化任务进度（与 LLM token 流分端点，避免队头阻塞）
- [ ] **UI-03**: 双语呈现：现有双语执行摘要接入界面，术语向决策者做平实转译

### OPS — 演示可靠性

- [ ] **OPS-01**: 一键启动：单命令拉起后端 + 前端，演示机可靠复现
- [ ] **OPS-02**: 演示结果预缓存：所有演示案例的 CODE V 深度成果预先算好落盘，现场绝不实时依赖 license/网络（CODE V 是溯源背书，不是现场算力）
- [ ] **OPS-03**: 完整演示彩排：核心叙事从头到尾跑通不翻车，含降级预案（里程碑验收标准）

## v2 Requirements (deferred)

- **SHOW-04**: 优化收敛可视化（merit function 随迭代下降曲线）— 叙事加强项，不阻塞首次彩排
- **SHOW-05**: 完整 Monte Carlo 良率分布图 — top-N 敏感度表验证受众反应后再深化
- **DATA-01**: 同步 109 颗手机镜头 ZMX（lens-data-staging/，另一台电脑）扩充底库

## Out of Scope

- 云端部署 / SaaS 多租户 — CODE V Windows-only 按席位授权，服务端化不可行且违反演示定位
- CODE V 进在线实时链路 / 现场实时跑深度优化 — 违反亚秒级约束 + 演示日最大翻车点
- Zemax OpticStudio 集成 — ZOS-API 性能烂账已实证弃选；引擎接口可插拔，未来有真实需求再加
- 原生工具全功能对齐（完整公差模块等）— 范围爆炸；只做证明概念的薄切片
- 零样本全拓扑 AI 生成 — 非当前 SOTA 实际能力，过度声称反伤可信度
- 与 lumira 官网互通 — 产品线已独立

## Traceability

<!-- 由 roadmap 填充：REQ-ID → Phase 映射 -->

---
*Last updated: 2026-07-03 after initial definition*
