# Phase 15 Stage A/B — 显式 FNO 失败模式采证报告（2026-07-11 真机）

> **边界声明**：本报告只出失败模式分类与原始数字，**良品/合格判定全部留给资深**（AGENTS.md 北极星 [EXPERT] 红线）。
> 真值来源：真机 CODE V .lis/.tsv（本目录逐格留存）+ results.tsv（42 数据行），非 AI 自报。
> 探针设计：短 AUT（MXC 2/MNC 1），**EFL 锁 seed 自身 native 值**——观测到的失败可归因于显式 FNO retarget 单一变量（而非同时拉 EFL）。分类基于 .lis 全文（落盘 >500 行的清单只留关键段+原始行号，分类在运行时已对全文完成）。

## 0. 核心发现：「FNO 系统参数达值」与「光线可追迹性」是两个完全分离的维度

这是 Stage B 阶梯引擎设计的关键输入，必须分开读：

| 维度 | 结果 | 含义 |
|---|---|---|
| ① **FNO 系统参数达值** | **40/40 非超时格全部逐位达值**（`post_aut.fno == target`，含全部 32 个 TIR 格） | FNO 模式在 CODE V 系统参数层面是锁定的（E1 探针结论再验证）：把 F# "设到" target 从来不是问题 |
| ② **光线可追迹性** | 仅 **7/42 格 clean**（无任何 RAY ERROR）；32 格 TIR、1 格 chief-ray-missing、2 格 timeout | 问题全部在这里：新光阑口径下优化光栅里大量光线 REFL（全反射）/MISS，merit 在带伤光栅上计算 |
| （参照）EFL 收敛 | 39/40 `aut_converged=1`（EFL 锁 native，唯一例外 US-12443014-B2-e1 loosen→3.8，dev 2.48%） | EFL 维不受 FNO retarget 破坏 |

**推论**：Stage B 的工程问题不是"F# 拉不到 target"，而是"拉到之后光栅带伤"——`aut_converged=1` + `post_aut.fno==target` 会给出**双重假阳性达标信号**，而光栅里 REFL×64 的像质读数（RMS/WFE 由 SPOTDATA/RMSWE 在部分场次失败的光栅上算出）不可作为可信像质。任何 Stage B 达标判据必须把「参数达值」与「光栅干净度」两个证据分开上报。阶梯引擎每级重解渐晕（autovig 爬梯裁掉 TIR 光线）正是对症设计。

## 1. 分类分布总表（42 格 = 12 seed × 收紧/放松）

| outcome | count | pct |
|---|---|---|
| TIR | 32 | 76.2% |
| ok | 7 | 16.7% |
| timeout | 2 | 4.8% |
| chief-ray-missing | 1 | 2.4% |
| aperture-conflict | 0 | 0% |

## 2. 按方向：收紧全灭，放松部分干净

| direction | ok | TIR | chief-ray-missing | timeout | 合计 |
|---|---|---|---|---|---|
| tighten（收紧） | **0** | 15 | 1 | 2 | 18 |
| loosen（放松） | **7** | 17 | 0 | 0 | 24 |

- **没有任何一颗 seed 能"直接收紧"**（收紧方向 0/18 clean）。收紧方向的 F# 达 target 必须依赖渐晕/ray-setup 工程。
- 最温和的收紧失败：US20170003482A1 native 2.32→2.00（-14%）只有 chief-ray-missing（MISS 4，REFL 0）——全矩阵唯一非 TIR 的收紧失败，也是收紧可行性最好的信号。
- 两个 timeout 都是 **95° 超广角 + 收紧**（US20180143405A1 1.86→1.80、US20210165194A1 2.00→1.80）——与 opt3 已知的 TIR-flood 拖死 AUT 机制一致（US20180143405A1 正是当年 v=0 全臂超时的那颗）。

## 3. 按 FOV：宽视场更糟，但窄视场并不安全

| fov bucket | ok | TIR | 其他 | 合计 |
|---|---|---|---|---|
| wide (≥75°) | 3 | 20 | 3（2 timeout + 1 chief-ray-missing） | 26 |
| tele (<30°) | 4 | 12 | 0 | 16 |

**意外信号：窄视场长焦也大量 TIR**（12/16）。两颗长焦 seed（US-12443014-B2-e1、US-12372756-B2-e8）连放松方向都全 TIR。细看 US-12372756-B2-e8：5 格 `efl_target_deviation_pct` 逐位相同（0.0402268）、MISS 恒为 5，REFL 随 F# 放松单调下降（64→60→36→28→20）——强烈暗示该 seed **导入即带固有光线病灶**（MISS 5 与 F# 无关的份额）+ **口径相关份额**（REFL 随口径收紧增加）。见 §6 对照臂缺口。

## 4. 按幅度：失败烈度随 |ΔF#| 递增（收紧方向梯度）

| seed | native→target (Δ%) | outcome | REFL | MISS |
|---|---|---|---|---|
| US20170003482A1 | 2.32→2.00 (-14%) | chief-ray-missing | 0 | 4 |
| US20170003482A1 | 2.32→1.80 (-22%) | TIR | 1 | 6 |
| US20140111876A1 | 2.07→2.00 (-3%) | TIR | 4 | 11 |
| US20140111876A1 | 2.07→1.80 (-13%) | TIR | 17 | 3 |
| US20140111876A1 | 2.07→1.60 (-23%) | TIR | 26 | 1 |
| US-12372756-B2-e8 | 2.45→2.00 (-18%) | TIR | 60 | 5 |
| US-12372756-B2-e8 | 2.45→1.80 (-27%) | TIR | 64 | 5 |
| US-11940597-B2-e6 | 3.57→2.00 (-44%) | TIR | 33 | 6 |
| US-11940597-B2-e6 | 3.57→1.80 (-50%) | TIR | 45 | 6 |

同 seed 内 REFL 计数随收紧幅度单调或近似单调上升（US20140111876A1: 4→17→26；US-12443014 为例外：-36% 时 22 而 -29% 时 56，见原始 .lis）。**梯度存在 = 小步阶梯（几何级距）+ 每级渐晕清理有物理依据**——这正是 Stage 3 `run_codev_target_fno_ladder` 的设计假设。

## 5. 放松方向哪些 clean（7 格 / 5 seed）

| seed | FOV | native→target | 备注 |
|---|---|---|---|
| US20210165194A1 | 95° | 2.00→2.40 | 放松到 ultrawide 带上界即 clean |
| US20170003482A1 | 91° | 2.32→2.40 | +3% 小幅放松 clean（opt3 最佳收敛种子） |
| US8908290B1 | 91.2° | 2.00→2.40 | 同上模式 |
| US-20260160979-A1-e3 | 19° | 1.68→2.18 / 2.68 / 4.00 | **全部三个放松格 clean**（含 +138% 大幅放松）——唯一全绿 seed |
| US-11940597-B2-e6 | 18.8° | 3.57→4.00 | 放松 clean，收紧全 TIR |

而 US10281683B2 / US10330891B2 / US20140111876A1 / US10310222B2 / US20180143405A1 放松也 TIR——与 opt3 诊断一致（这些宽+快种子导入丢 ray-aiming 后**离轴宽角光线**固有 TIR，与光阑口径松紧无关的份额显著）。

## 6. 诚实限制（资深/下一窗必读）

1. **无 native 对照臂**：本矩阵没有跑"同宏、不设 FNO"的对照格。US10281683B2 等种子已有真机记录证明 native 导入即 TIR（.planning/debug/codev-target-convergence.md 诊断 v2），故本矩阵中"TIR"分类 ≠ "FNO retarget 导致 TIR"——它是「FNO 设定后的光栅状态」快照，其中混有 seed 固有份额。**区分两种份额需要下一真机窗补 12 格 native 对照**（每 seed 一格，成本 ~5 分钟）。
2. **aperture-conflict 正则 0 命中，但发现两个新终止措辞**：`Abnormal AUTO Completion - Scaled down SPC data`（13 次）与 `Abnormal AUTO Completion - Scaled down nominal system cannot be traced`（6 次）——都属 aperture/pupil 缩放失败家族，且**不在** `codev_optimize._AUT_TERMINATION_KEYWORDS` 清单里（该清单遇未知措辞如实返回 None，fail-open 无害）。回填工单：这两个措辞应进 `_AUT_TERMINATION_KEYWORDS`，并考虑并入 fno_probe 的 aperture-conflict 正则（但 TIR 优先级更高，当前分类不受影响）。
3. **本探针短 AUT（2 cycle）**：终止措辞分布（21 次 "Maximum cycle limit reached"）是 MXC 2 的直接后果，不代表完整优化的终止形态；本探针只采失败模式，不采收敛质量。
4. **像质读数不入本报告**：带 RAY ERROR 的光栅上 RMS/WFE 数字不可信（SPOTDATA fail-open 跳过失败场次），故本报告刻意不出像质列；阶梯引擎的 per-rung 像质必须连同渐晕 edge_used 一起读。
5. 逐格原始证据：`results.tsv`（42 行全量）+ 每 seed 子目录 `.seq/.tsv/.lis`（大 .lis 为关键段摘录+原始行号，分类时已用全文）。
6. **归档口径与 5 格不可复核清单（对抗审查 MAJOR-4 实锤，如实声明）**：初版 trim 信号正则漏了 `Total reflection`/`ERROR -` 形态的 TIR 行（分类器的 TIR 证据有 `RAY ERROR: REFL` 与 `Total reflection` 两种形态，trim 只保留了前者），导致以下 5 格的**已归档 trimmed 清单**重跑分类器无法复现 runtime 分类（runtime 分类基于全文、results.tsv 数字为真值；全文在 trim 时被原位覆写、本窗禁跑 CODE V 无法重采）：

   | cell | runtime 分类（results.tsv） | trimmed 归档重判 |
   |---|---|---|
   | US10330891B2 loosen→2.400 | TIR（REFL 1） | ok |
   | US20170003482A1 tighten→1.800 | TIR（REFL 1, MISS 6） | aperture-conflict |
   | US20140111876A1 loosen→2.570 | TIR（REFL 1） | ok |
   | US20140111876A1 loosen→3.000 | TIR（REFL 1） | ok |
   | US-12443014-B2-e1 loosen→4.000 | TIR（REFL 2） | ok |

   共性：这 5 格 runtime REFL 计数极低（1-2），其 TIR 证据恰好全部来自被丢弃的 `Total reflection`/`ERROR -` 行。其余 37 格 trimmed 归档重判与 runtime 一致（可复核）。**修复已落**：trim 正则补齐两种形态 + header 记录全文 sha256/原始行数（后续采证全部可复核）；**这 5 格排入下一真机窗重采队列**（同格重跑 ~15s/格，归档即得全证据）。分布结论稳健性：即使把这 5 格保守地从 TIR 改记 ok，TIR 仍 27/42（64%）、收紧方向仍 0 clean，§0-§4 结论不变。

## 7. 对 Stage 3 阶梯引擎（已建，待真机验证）的输入

- **每级必须重解渐晕**（autovig 爬梯）——32/42 TIR 证明裸 FNO retarget 光栅必伤；阶梯引擎已按此设计（每 rung 独立 `run_codev_target_autovig`）。
- **达标判据必须双维上报**：`measured_fnum`（EFL_real/EPD_real 活算，不信构造值）+ 光栅干净度证据（渐晕 edge_used、err_f_ratio）。引擎已实现 measured_fnum fail-closed；**建议下一窗把 per-rung .lis 分类（fno_probe.classify_fno_listing）也接进 rung 记录**，光栅干净度即可量化上报。
- **收紧方向预期需要更多渐晕/更细阶梯**：0/18 clean 说明收紧的每一级都要靠渐晕清理救；95° 超广角收紧有 timeout 风险（引擎已实现每级吞并续爬）。
- **CONVERGED_FIELDS 不得扩 fnum**：本采证再次证明 `aut_converged=1` + `post_aut.fno==target` 双假阳性——在光栅干净度证据未接入引擎并真机验证 ≥8 seed 前，扩展是提前标注未验证能力（诚实红线）。
