# Loop3 进度 digest（2026-07-10，自主 loop：Mode3 产能 + 底库 + 演示/前端）

> 供主公异步查看。真值来源：git/pytest/真机 tsv/CI——非 AI 自报。

## 铲 1：rebuild -inf EFL 根因（✅ 完成，PR#49 已合 main=f9b0b22，main CI 绿）

- **根因**（真机采证，systematic-debugging 全链）：非 rebuild 链代码 bug——17 颗遗留真实设计 seed（3P_/4P_/5P_*.zmx）玻璃行 `GLAS <商品名> 0`，CODE V ZEMAXOS_TO_CV 目录查无该名 → 导入即全空气系统（baseline EFL=1e35 铁证）→ 重建 ZMX 忠实回显 → Optiland f2()=-inf。Optiland 可路由假象=Python 侧查表 fallback（CODE V 无等价物）。宏源码 L1523 按 "BLANK" 子串（非 flag）判 model glass——真机隔离对照实证。
- **修复**：数据锚升级 `<商品名>_BLANK 1 0 nd vd`（nd/vd 取 Optiland fallback 同一查表，零杜撰；保留商品名身份）+ 全库 353 颗 GLAS 可解析回归测试 + baseline EFL 预检守卫（坏 seed 14 次真机 run→1 次）+ writer 对标记名写 flag=1（交付物在真 Zemax/二次 CODE V 导入不退化空气）。
- **审查闸**：8 角度 finder → 21 候选 → 10 实锤 → 9 修 + 1 记 backlog；code-simplifier 轮判无可简化。
- **真机战果**：Mode3 首次从 5P seed 产出 2 个 TARGET_CONVERGED 候选（FOV78.8：RMS 25.95µm / EFL 达成偏差 0.006%；FOV78.7：偏差 0.77%）。**17 颗真实设计 seed 全部解锁 Mode3**（此前 Mode3 事实只吃专利系 seed）。
- **判据**：mock 全量 1296 passed + 真机子集 390 passed，golden 零翻转，PR CI 22m23s 绿，main CI 绿。
- 新独立工单（已留痕）：H-LAK53A Python 表值与 CODE V 目录不一致；e2_intake 缺 CODE V 可解析性预检（现靠 CI 全库测试兜底）。

## 铲 2：底库填充 353→≥500（🔄 executor 进行中，worktree D:\atelier-intake，分支 data/intake-500）

- 评估结论：353 可路由（wide 201 / tele 119 / uw 33，AR/DSLR/microscope=0），全部 ZMX-backed + EFL 有限 + index 层 IMH 353/353（真 IMH 欠账已还清）；原料池 714 颗唯一专利、约 91 颗已入库 → **约 620 颗可挖**，缺口 147 ≈ 40 颗专利（历史良率 ~3.7 embodiment/颗），可达。
- 打法：既有管线 patent_to_zmx → e2_intake 六闸（fail-closed）→ golden 重锚（e2_golden，≤2% 铁律）→ 全量 mock 闸。薄场景（tele/uw）优先。

## 铲 3：端到端演示打通（🔄 启动，web 侦察已完成）

- 现状：web 层已有完整检索演示链（index → /wizard/confirm LLM 提取 → /jobs 异步 → SSE 进度 → /results/{id} 结果页，provenance 徽章 + degraded 态诚实）；**Mode3/C1 零 web 接线**（c1_orchestrate 纯离线 CLI）。
- 形态（已定）：CandidateOrchestrationEngine（镜像 ResultSummaryEngine 模式，job store 后台层跑 orchestrate()，在线路径亚秒级不破）+ POST /candidates + candidate_set.html（诚实横幅置顶 / mode+rank 徽章 / 5 维 target-deviation / [EXPERT] 留白栅格照抄离线报告语义）。无 CODE V → Mode3 空 → banner 如实出现=降级天然诚实。

## 红线遵守

- 全程未下良品/合格判定（scorecard 只出量化数据，[EXPERT] 栅格留白）；无伪造数值（nd/vd 查表、拒收如实上报）；未碰全局配置；发布走 PR→CI→merge。
