# ③ 优化落地 · 自主 loop 终版 handoff（2026-07-09）

> **⚠️ 2026-07-28 后记（本文写于合并之前，下面两处「未合 main」已过时）**：
> `spike/codev-target-convergence` **已由 PR #45 于 2026-07-09 14:05Z 合入 main**
> （merge commit `0ea76505`）。实测：`git merge-base --is-ancestor` 判定 fully merged，
> `origin/main..origin/spike/codev-target-convergence` **零未合提交**。
> 优化能力现在就在 main 上——`app/core/engines/codev_optimize.py` 的
> `run_codev_target` / `run_codev_target_autovig` / `run_codev_target_standard` /
> `run_codev_target_fno_ladder`。
> **加这条后记的原因**：本文这句话被一条 memory 原样继承，导致「优化能力尚未落地」
> 的错误认知，差点误导 P2 的排序。**P2 的卡点不是优化能力**，是配对协议与真机时间。
> 另注：文中 `[EXPERT] 红线` 的表述属北极星 v0.1 体系，**v2 已把 `[EXPERT]` 移出开发 gate**
> （见 `.planning/NORTH-STAR.md`）；本文其余内容作为 2026-07-09 的历史记录保留不动。

> **边界声明**：本报告只出量化数据、候选设计与机器可判事实。**"良品/合格/可用/值得看"判定全部留给资深（[EXPERT] 红线）**，go/no-go 由主公与资深依据本报告数据裁定。
> 真值来源：真机 CODE V tsv/.lis、pytest、git commit——非 AI 自报。

## 一、完成定义对照（任务书四项 → 机器可达最佳态）

| 项 | 状态 | 证据 |
|---|---|---|
| GLC 修好 | ✅ | commit 7b504c6：塑料域 GLA 边界（(nd,nF-nC) 平面凸包），灾难态消除，3/5 seed RMS 较 asphere 再降 33-80% |
| asphere 标配 | ✅ | commit 98562dc + 0416e95：`run_codev_target_standard` {asphere,both} 并跑取优；DOF 对齐数据锚 A..G（16 阶）后杠杆不降反升 |
| seed 匹配就位 | ✅ | commit a41b9ee：`seed_target_score.py`（N=24 真机矩阵 heuristic，rho=+0.744，方向不对称罚则） |
| autovig 保 F# | ✅ | 既有 d82c75e 基础上本轮全部真机跑复用，native F# 全程不变 |

**超出完成定义的附加成果**：候选 ZMX 交付闭环（0416e95，接缝 6 前置）、AUT 误差函数假阳性可观测（e9114eb）、.lis 诊断错位结案（248581c）。

## 二、本轮 commit 链（spike/codev-target-convergence，未合 main）

```
7b504c6 fix: GLC 玻璃变量套塑料域 GLA 边界（修玻璃拉飞负杠杆）
9ca9e26 docs: GLC 修复根因链+真机矩阵入 debug doc
98562dc feat: Mode3 标准入口 run_codev_target_standard
b3adfef docs: Mode3 入口留痕
248581c fix: .lis 清单认领改快照 diff + 启动前清理
8681618 docs: .lis 认领修复留痕
e9114eb feat: AUT 误差函数轨迹解析进结果（假阳性收敛可观测）
a41b9ee feat: seed-target 匹配打分模块（N=24 真机矩阵 heuristic 固化）
59920b5 docs: seed-target 匹配矩阵报告 + loop 进度 digest
0416e95 feat: target 模式候选 ZMX 交付 + asphere DOF 对齐数据锚（A..G）
1913855 docs: ZMX 交付 + DOF 对齐留痕
```

## 三、候选设计交付（scorecard，数字裸出）

**客户 target 场景**：EFL 3.797mm（seed 池 P50，真实主摄规格区间），F#/IMH 保 native（Stage B/C 未落地，见限制）。seed 由 `seed_target_score` 从 8 颗池选 lt5 带 2 颗。

| 项 | 候选1：US20170003482A1 | 候选2：US20170045714A1（对照） |
|---|---|---|
| ΔEFL（打分 band） | +4.8%（lt5） | -4.4%（lt5） |
| preferred 配置 | both（asphere+glass） | both |
| EFL 达成偏差 | ~2e-7% | 0.50% |
| RMS 点列（post，µm） | **2.80**（asphere 3.89） | 68.1（asphere 187.7）⚠ 见重复性 |
| WFE（波） | 0.042 | 1.94 |
| 畸变 | 5.4% | 2.3% |
| 渐晕 edge（provenance） | 0（未裁瞳） | 0.2 |
| native F#（保持） | 2.32 | 1.75 |
| err_f_ratio（AUT 误差函数末/初） | **0.09**（健康下降） | **115.3**（⚠ 上升两个量级，EFL 收敛但 merit 实质恶化） |
| 优化后 ZMX | **已交付两配置**（回读 EFL 误差 0.04%） | **已交付两配置**（vig token 修复后重产，回读 EFL 与采纳 rung tsv 差 0.03% 归属一致） |
| 玻璃 provenance | fictitious（塑料域 GLA 内），未落真实目录玻璃 | 同左（both 配置） |

**候选 ZMX 文件**：`.planning/loop/candidates-2026-07-09/US20170003482A1/{asphere,both}/US20170003482A1_target3.797_optimized.zmx`（+ 全部 tsv 读数）。

**诚实要点（资深必读）**：
1. 同为 lt5 良配带，两候选质量差 ~24 倍——**匹配打分是收敛风险代理，不是质量保证**；seed 内在品质因素存在但在 N=24 内无独立统计信号（baseline RMS p=0.63）。
2. **候选2 重复性差（边缘 seed 实锤）**：同 seed 同 target 三次真机跑 RMS 12.6（矩阵，edge0.5）/ 71.1（冒烟，edge0.2）/ 187.7（本次，edge0.2）——autovig 在该 seed 处于收敛边缘（dev 在 2% 阈值附近抖动），微小宏差异即走不同优化路径。候选1 三次跑数字逐位复现（确定性成立）。**"重复性"应进未来 scorecard 维度。**
3. 候选2 的 err_f_ratio=115（及冒烟跑的 53.6）是 ERR.F. 守卫的直接产出：`aut_converged=1`（EFL-hit）会掩盖 merit 恶化，此字段是唯一区分手段（灾难/健康案例的 CODE V 终止行文字逐字相同，真机实锤）。
4. RMS 均在裁瞳光栅上测（edge>0 时偏乐观），须连同渐晕列读。
5. 候选1 玻璃是塑料域内 fictitious model glass，**未 snap 到真实材料目录**（GLASSFIT/Glass Expert 未接，见限制）。

## 四、良品率数据矩阵（AI 只出分布，不判良品）

**匹配矩阵（8 seed × 3 target，asphere 配置，N=24）**：

| \|ΔEFL\| 桶 | 收敛率 | RMS 中位（µm） |
|---|---|---|
| <5% | 100% (5/5) | 6.3 |
| 5-15% | 100% (5/5) | 34.5 |
| 15-30% | 86% (6/7) | 46.2 |
| >30% | 43% (3/7) | 274 |

**方向不对称（核心新信号）**：缩焦 12/12 全收敛（最深 -35.6%）；拉焦 +25.1% 起见失败，>+35% 全灭。打分公式对拉焦超 +20% 加罚。

**GLC 修复对照（5 seed，+12% target，both vs asphere）**：3/5 both 更优（-33%~-80% RMS）、1/5 +35%、1/5 局部极小退化 → 标准配置=并跑取优而非单配置。

**绝对像质分布参考（收敛臂）**：最佳 2.80µm（良配+both）；lt5 带多数 <10µm 与 71µm 并存；>30% 带典型 100-400µm。原始逐行数据：`scratch_diag/match_matrix_results.tsv`（24 行全量）+ `.planning/loop/seed-target-matching-report.md`。

## 五、已知限制与残留（诚实清单）

1. **F# 优化未落地（Stage B）**：现只锁 native F#；改 F# 的显式 FNO 命令致宽视场主光线追迹失败（需 CRA/ray-aiming 工程）。客户 target 的 F# 维目前"保 native"而非"达 target"。
2. **IMH/FOV 未落地（Stage C 场重建）**：同上，target 只有 EFL 维真优化。
3. **fictitious glass 未落真实玻璃**：both 配置产物玻璃是塑料域内 model glass；GLASSFIT.SEQ / Glass Expert（手册 LensSetupRM p.423 / Opt RM Ch.9）未接。量产可信度收口活。
4. **GLA 软约束轻微越界**：4/5 seed 有 1-3 面终值微越塑料边界（CODE V 对 GLA 非硬边界）——落真实玻璃时一并收口。
5. **Optiland even_asphere 回读溢出（既有独立问题，本轮暴露）**：重建 ZMX 满口径追迹数值溢出 → 无 CODE V 环境（CI/降级链）复核候选的缺口。此前被 ZMX 重建 fail-open 掩盖。
6. **US20180143405A1 边缘性矛盾**：曾 e0.7 recovered（RMS 86µm），本轮连一阶读数都 60s 超时，三度不稳定。如实记录，不下结论。
7. **打分 heuristic N=24**：描述性拟合、同数据验证、精度 ±1 桶；仅 EFL 维、Stage A only。扩池后应重标定。
8. **边缘 seed 重复性**：US20170045714A1 三跑 RMS 12.6/71/188µm（收敛阈值边缘抖动）；US20180143405A1 时好时坏三度记录。**重复性维度未进 scorecard**——建议 C1 编排对候选跑 ≥2 次取分布。
8a. **per-rung 文件名怪癖（已修，commit 967569e）**：真相比初判"覆写混叠"更深——含 `.20_` 中缀的文件名让 CODE V BUF EXP 拒写中止宏（与 .seq 版本号剥离同源怪癖），受影响 rung 的 ZMX 从未落盘、被 fail-open 静默吞掉。修复=无小数点定宽 token（`_vig020`）全 rung 消歧 + `_blocked_or_best` 兜底 edge_used 归属修正。候选2 两配置 ZMX 已重产交付（归属一致 0.03%）。
9. **spike 分支未合 main**：全部成果在 spike/codev-target-convergence，合并决策在主公（涉及 C1 实施路径单议）。
10. **全仓终版判据**：1551 passed, 3 skipped（净增 49 测试，零回归，含真机冒烟）。

## 六、待主公/资深的决策点（NEED 主公）

1. **良品率 go/no-go**：§三/§四数据是否支撑"值得资深看一眼率"过闸（北极星第一里程碑判据）——判在资深。
2. **C1 实施路径**：Mode3 标准入口已备好（`run_codev_target_standard` + `seed_target_score`），C1 harness 本体（app/core/orchestration/）实施路径（夜车切片 vs attended）仍待主公单议。
3. **Stage B（F#）与落真实玻璃**两个工程铲的优先级排序。
4. spike 分支合 main 时机。
