# ③ 优化落地 · 自主 loop 进度 digest（2026-07-09，续 07-10）

> **07-10 追记（主公授权"按工程最佳实践自主推进"后）**：
> 1. **PR #45 已合 main（0ea7650，PR CI 31m51s 绿 + main CI 绿，AI Release Authority 全 gate）**——③ 全部成果落主线。合并前对抗审查（8 finder 角度 + recall verify）：18 候选 15 CONFIRMED/3 PLAUSIBLE/0 REFUTED，13 项修复入 d421d2b（含 stale readout 认领事故残余、returncode 闸、BUF EXP 危险文件名机制守卫、provenance per-config 如实、NaN 穿透、epd_mm schema）；维护类 5 项记 backlog。
> 2. **vig token 真相二纠**：非"覆写混叠"而是 CODE V 拒写含 `.20_` 中缀文件名 → 受影响 rung ZMX 从未落盘（fail-open 静默吞）；修复后候选 2 两配置 ZMX 已交付（归属一致 0.03%）。
> 3. **C1 harness M1 实施中（feat/c1-orchestration-m1，spec a309f3b 已定稿=执行既定方案）**：C1-a rank_seeds 抽取（行为逐位不变，golden 未翻转，1119 保护网绿）→ C1-b 骨架+诚实不变量（-O 下 raise 实测）→ C1-c scorecard+RI（全库零渐晕声明 → RI=纯 cos⁴θ 数据现状如实钉死）→ C1-d orchestrator+离线报告（banner 置顶+资深留白节）。69 orchestration 测试绿，全仓回归跑批中。
> 4. 下一步：C1 批次审查闸 → PR → merge；然后 Mode3 真接入（CONVERGED_FIELDS 缩窄 {"efl"}）与三个交接工程铲（Stage B CRA / 落真实玻璃 / 良品率矩阵扩充）。



> Orchestrator：Fable 5（无人值守 loop）；executor：Sonnet subagents。
> 真值来源：真机 tsv/.lis + pytest + git（非 AI 自报）。良品率/合格判定不在本报告（[EXPERT] 红线）。

## 已完成铲（按时间序）

### 铲 1 · GLC 玻璃变量修好（commit 7b504c6 + 9ca9e26）
- **根因（证据链）**：`GLC S^s 0` 转 fictitious glass 后 CODE V 自动套默认 `GLA NFK5 NSK16 NLAF2 SF4`（Schott **矿物玻璃**边界）——不适配塑料手机镜头。灾难案例 US20170003482A1：S14 nd 1.535→1.718（塑料不可实现、未触默认界），ERR.F. 爆炸 ×1204 仍报 "Normal AUTO Completion"（IMP 判据假阳性）。
- **修复**：`_glass_map_hull` 在 **(nd, nF-nC) 玻璃图平面**算凸包（★通用陷阱：CODE V 的 GLA 凸性检查在此平面，不是 (nd,vd)★），glass/both 时注入塑料域 GLA（`DEFAULT_GLASS_BOUNDS_ND_VD`，可参数覆盖）。
- **真机 5-seed**：灾难态消除、5/5 EFL 收敛、3/5 RMS 较 asphere 再降 33-80%（最佳 US20170003482A1 → **8.7µm**）；US10281683B2 +35%、US20180143405A1 陷局部极小退化。
- **工程决策（自决留痕）**：不死磕单配置全胜——C1 编排按 {asphere, both} 并跑取优（多产候选=北极星形态）。
- 判据：30 测绿（含真机冒烟）+ 全仓 1502 passed + ruff 绿。

### 铲 2 · Mode3 标准入口（commit 98562dc + b3adfef）
- 新增 `run_codev_target_standard`：{asphere, both} 串行并跑 → preferred=纯数值规则（conv 优先→RMS 小者→缺值 fail-closed），**双份数据全保留** + provenance 诚实标注（fictitious glass / 裁瞳 RMS / "preferred 是数值排序非良品判定"）。
- docstring 写死 C1 spec §10 契约锚：已落地接缝 1（EFL→target）+ 2（玻璃可变塑料域）+ 3a（FNO 锁 F#）；IMH/FOV（Stage C）未落地；接缝 4-6 在 case_library 侧不属本函数。
- **C1 harness 本体未实施**（实施路径主公单议中，不越权）。
- 判据：36 mock 测绿 + ruff 绿；真机端到端补验排队（CODE V 被矩阵占用）。

### 铲 3 · .lis 清单错位结案（commit 248581c + 8681618）
- **"timeout 孤儿进程串扰"假设被证伪**：干净 rung（无超时）同样中招。真根因=CODE V 把 `.seq` 名末尾 `.<数字>` 当版本号剥离（`_e0.3` 系列收编进同 root 滚动组）+ Python 侧裸猜 `with_suffix('.lis')` 且从不清理残留。
- **数值 tsv 走显式 BUF EXP 绝对路径，完全无损**——纯诊断信息污染。
- 修复：启动前清理裸名 .lis + 快照 diff 认领 listing_path + 超时分支补 listing_tail + docstring 命名警告。判据：50 测绿 + ruff 绿。

## 进行中

### 铲 4 · seed-target 匹配量化（真机矩阵跑至 23/24 组合）
- 设计：可追迹 seed 池扩容（5→8，新增 US9239447B1/US9651759B2/US9810880B2/US20210165194A1 中筛入者）× 3 个固定绝对 EFL target（3.218/3.797/4.315mm，距离谱系 -36%~+79%，含负偏移新信号）× asphere+autovig 标准配置。
- **初扫信号（待 executor 正式分析）**：|ΔEFL| <7% 全收敛且 RMS 放大 ≤1.25×（负偏移 -1.8% 甚至 ×0.29 变好）；15-20% 混合区；>25% 多数灾难/不收敛；负偏移（缩焦）耐受明显好于正偏移（US9810880B2 -35.6% 仍 conv 且 RMS 60µm vs US20210165194A1 +33.7% 直接 269µm 不收敛）。
- 产出（进行中）：`.planning/loop/seed-target-matching-report.md` + 打分 heuristic 草案。

## Backlog 剩余
- Mode3 入口真机端到端补验（矩阵释放 CODE V 后）
- ERR.F./ABERR.F./CONST.F. 假阳性守卫进 tsv（诚实可观测性）
- GLA 软约束轻微越界 → 落真实玻璃（GLASSFIT/Glass Expert）收口
- Stage B 宽视场 CRA、收敛半径精细刻画
- 终版 handoff：完整候选设计 + 量化 scorecard 矩阵（AI 出数据，go/no-go 判在资深）
