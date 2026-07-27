# Atelier — 光学设计 Agent 独立演示产品

## What This Is

Atelier 是一个可独立部署的产品级**手机镜头**光学设计 Agent 软件：客户在浏览器界面里用自然语言输入需求，系统实时给出设计（光路图 / MTF / 专家级评估报告），并展示由 Code V 深度优化产出的专业级设计成果。设计能力植根于可追迹、可路由的手机镜头专利底库；500 颗仅为历史进度标记，现行终点是选定公开数据源游标耗尽、逐专利族/逐 embodiment 唯一终态、冻结池确定性回放不再产生新 seed。目标用户是镜头/模组厂的工程团队与决策者，用于现场客户演示。它从 lumira 官网后端剥离而来，现在是独立产品线，与官网可不互通。

## Core Value

资深光学设计师看了演示产出不能觉得"比不过"——专家级可信度是唯一不可失守的东西；观感和流畅度服务于它，不能替代它。

**（2026-07-08 主公定向升级）** 产品从"现场演示"升级为**量产设计的产出引擎**：AI 批量产出量产级候选设计，把初/中级设计师"一稿数周"的产出瓶颈，压缩为资深设计师对成品的快速判断与背书。可信度内核不变——AI 只多产、不越权定夺，"合格/可用"的最终判断权与 [EXPERT] 背书始终在资深设计师。里程碑级转向，完整重规划（含 What This Is / 目标用户 / Out of Scope 重审）待 ROADMAP Phase 10 探路阶的"良品率 go/no-go 闸"验证后启动。

## Requirements

### Validated

<!-- 从现存代码推断（brownfield，见 .planning/codebase/）。 -->

- ✓ 确定性光学计算（薄透镜/paraxial/Airy/DOF/ABCD，LLM 禁止估算的地真数学）— existing
- ✓ Optiland 集成：场景参考设计缩放 + 光线追迹 + MTF/PSF/Zernike + SVG 光路图 — existing
- ✓ 案例库与路由：39 案例（17 真实 + 22 专利 seed）、match_case 最近邻、DesignAssessment 评估包 — existing
- ✓ ZMX 摄入流水线（XASPHERE/渐晕病灶已修，EFL 误差 <2% 合约）— existing
- ✓ Wizard LLM 编排：自然语言场景提取（参数夹紧）、封面图、双语执行摘要 — existing
- ✓ 参数守卫（6 场景 SCENARIO_BOUNDS）+ 画质地板评估 + eval golden 回归 — existing
- ✓ 24 个测试文件约 5600 行，CI 就绪（LLM 全 mock）— existing

### Active

<!-- 本 milestone 的假设，跑通演示即验证。 -->

- [ ] Code V 深引擎集成：宏批处理模式（生成 .seq → 批跑 → 解析结果），可插拔引擎接口 + 运行时探测，无 Code V 时自动降级纯 Optiland
- [ ] ZMX ↔ Code V 互通验证（spike 先行）：导入专利 seed ZMX → 实算真 IMH → 导出回 ZMX → 过现有 ingest 比对指标一致性
- [ ] 专利 seed 可路由化：真 IMH 实算 / 路由重锚 / eval 重锚（解 E2 头号工单）
- [ ] 演示前端：本地起服务 + 浏览器界面，覆盖"需求 → 设计 → 评估 → Code V 深度成果"全流程叙事
- [ ] Code V 深度优化成果展示：优化前后对比、优化过程可视化、"经 Code V 交叉验证"背书信息
- [ ] 一键启动：单命令拉起后端 + 前端，演示机可靠复现
- [ ] 完整演示彩排：核心叙事从头到尾跑一遍不翻车（第一里程碑验收标准）
- [ ] 手机镜头专利底库穷尽：合法公开来源的原始专利湖、官方族归并、逐 embodiment 确定性解析/进程硬超时/质量闸/真实 IMH/路由验收、十类唯一终态、冻结池无新增 seed 回放与可恢复增量游标；500 仅为历史标记

### Out of Scope

- 云端部署 / SaaS 多租户 — 独立产品跑演示机本地，商业软件许可与并发不允许服务端化
- Code V 进在线实时链路 — 在线交互必须亚秒级，Code V 只做离线深度层；现场跑全局优化是另一产品形态，需另行论证
- 与 lumira 官网互通 / 双打契约同步 — 产品线已独立，改为 lumira 有需要时单向摘取（待改写 AGENTS.md 契约）
- Zemax OpticStudio 集成 — 复核后弃选：ZOS-API 逐调用开销严重（10s→118s 实测案例）；引擎接口可插拔，未来想加随时能加
- 商用合规 / 侵权处理 — 主公明示非商用演示定位，许可风险主公自评

## Context

- **技术底座**：Python 3.12 + uv + FastAPI + Optiland 0.6，架构与雷区详见 `.planning/codebase/`（STACK / ARCHITECTURE / CONCERNS 等 7 份文档）
- **前端缺口**：本仓库只有后端；现有前端在 lumira 官网（Next.js + CF），独立产品需要新建演示界面
- **双引擎定位**：Optiland = 快引擎（在线交互，亚秒级）；Code V = 深引擎（离线全局优化 + 交叉验证，宏批处理驱动）
- **Code V 选型依据**（2026-07-03 复核）：一线设计师口碑其优化效率远胜 Zemax；ZOS-API 有严重逐调用性能问题；Code V 宏批处理模式（.seq 一次性批跑）绕开交互式 API 开销；主公可咨询的设计师群体用 Code V，人的生态加分
- **已知雷区**：Optiland 0.6 四补丁必须先于任何 Optiland import；ZMX 摄入历史病灶 E1-01/E1-02；专利 seed IMH=0.0 不可路由（E2 头号工单，本 milestone 顺手解决）；Windows 跑测试必须 PYTHONUTF8=1
- **外部资产裁定**：109 颗 `lens-data-staging/` ZMX 当前不可得（2026-07-05）；专利饱和工程不得依赖它们完成
- **演示受众双层**：工程团队（技术深度：真实指标、可追溯评估）+ 决策者（叙事观感：流畅、直观、故事完整）

## Constraints

- **平台**: 演示机为 Windows（Code V Windows-only），后端本地跑，浏览器访问 localhost
- **Tech stack**: Python 只用 uv；Code V 集成走宏批处理（.seq 生成 → 批跑 → 解析），不走交互式 API
- **性能**: 在线交互路径（追迹/MTF/SVG/路由）必须保持亚秒级；Code V 深度计算只在离线/后台层
- **降级能力**: 无 Code V 环境（CI、其他开发机）全链路可降级纯 Optiland 跑通测试
- **数据锚**: 全部资产以 ZMX 格式为锚，Code V 产物必须回到 ZMX 走现有 ingest 流水线
- **依赖**: Code V 安装由主公负责；集成开发在安装完成后才能实测（前置可先做接口设计与 mock）

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 深引擎选 Code V 而非 Zemax | 设计师口碑优化效率远胜；ZOS-API 逐调用性能烂账实锤；主公可咨询的专家用 Code V | — Pending |
| 集成模式 = 宏批处理而非交互式 API | .seq 一次性批跑绕开逐调用开销，所有计算在 Code V 内部全速跑 | — Pending |
| 双引擎架构：Optiland 快 + Code V 深 | 在线交互要亚秒级，深度优化不限时；引擎可插拔 + 运行时探测降级 | — Pending |
| 产品形态 = 本地服务 + 浏览器 | 开发快、演示效果好、复用 Web 技术栈；桌面壳弃选（打包复杂度不值） | — Pending |
| ZMX 互通 spike 为第一步 | 转换保真度（非球面/玻璃/渐晕正是 E1 翻车雷区）必须实测，不能信宣传 | — Pending |
| 解除与 lumira 的双打契约 | 产品线独立，同步义务拖节奏；改单向摘取 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-03 after initialization*
