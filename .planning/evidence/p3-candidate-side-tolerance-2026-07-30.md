# P3 候选侧没被测到，不是公差链路坏了——是候选不成像 + 阈值卡在标称下面（2026-07-30）

**一句话**：候选侧 TOR「没产出导出文件」**不是 TOR/writer 缺陷**，CODE V 自己在
同目录的 `.lis` 里写着 `ERROR - Ray tracing errors during clear aperture trace -
OPTION TERMINATED`——候选镜头追不了参考光线。而唯一两侧都测到的那条 trial
`yield=0.0/0.0` 也不是「阈值太紧」，是**0.25 波阈值卡在标称设计下面**。

> ⚠️ **本文推翻交办任务书里的一条前提**：`US-20240168263-A1-e7` 走到
> `spec_not_met` 并**不**意味着像质被测到了。它的 `metrics.*.verdict` 全是
> `unmeasurable`、`spec_verdict_override=unmeasurable`，`spec_not_met` 来自 EFL
> 一致性闸（候选 5.010 mm vs 对照 3.860 mm，差 29.8%）。

**真机状态**：全程**零真机作业**。开工与收工两次实测 `codev` 会话数**均为 1**
（另一 worktree 在跑 `p2-phase2-20260730 --skip-tolerance`，pid 从 25656 变到
21984）。本文所有结论出自**磁盘上已有的真机产物**，无一条来自新跑批。

## 缺陷① 候选侧 TOR 无导出 = 候选追不了参考光线

现场完整保留在 `D:/atelier-stagec-runs/p2-gated-20260729/trial_*/tolerance/candidate/`。

```
CODE V> TOR
     ERROR - Ray tracing errors during clear aperture trace - OPTION TERMINATED
CODE V> SNS
     ERROR - Invalid command SNS
     WARNING - Sequence aborted
```

`TOR` 自己就没进选项 → `SNS`（TOR 选项**内**子命令）变成非法顶层命令 →
整条序列 abort → `NTR / CHT / WBF / GO / BUF EXP` **一条都没执行** → 没有导出。

手册定死含义（`D:/CODEV115/doc/TroubleshootingGuide.pdf`, "Analysis Errors and
Warnings"）：

> Most CODE V options require that the reference rays (R1-R5) be traceable from
> object to image. … Although reference rays can be blocked by apertures or
> obscurations, they must be traceable from object to image.

候选自己的像质探针清单里 `ERROR - Total reflection at surface 3` 出现 **54 次**，
`rms_fields_ok: 0`、`mtf_fields_ok: 0`、三项指标全 null。**候选不成像。**

### 六条 trial 的相关性是精确的

| trial | 候选视场覆盖 | 候选侧 TOR |
|---|---|---|
| US-12436366-B2-e11 | **2/2** | **measured（两个导出都有）** |
| US-11933948-B2-e10 | 1/2 | CA-trace ERROR |
| US-12210142-B2-e9 | 1/2 | CA-trace ERROR |
| US-20240201471-A1-e8 | 1/2 | CA-trace ERROR |
| US-20240168263-A1-e7 | 0/2 | CA-trace ERROR |
| US-11668898-B2-e6 | 无（更早阻塞） | 未跑 |

唯一全视场追迹通过的那颗，就是唯一 TOR 跑通的那颗。

### 任务书点名的三个嫌疑，全部排除（附证据，别重走）

| 嫌疑 | 实测结论 |
|---|---|
| 渐晕行 `VDXN/VDYN/VCXN/VCYN` | **排除**：`ZEMAXOS_TO_CV` 直接丢弃，**两侧都**报 `WARNING - Vignetting angles not used.` 对称 |
| `XDAT 1` 声明项数硬编码 | **排除**：只产生 `WARNING - Maximum term number not used.`，CODE V 按系数表自推，非致命 |
| 「TOR 拒绝了优化器写的某个东西」 | **排除**：测量路径与 TOR 路径读的是**逐字节相同**的同一份暂存 ZMX（md5 `deb7689b…` 三份一致），测量路径读得进去 |

### 已修：错误信息把调查带偏了

`run_codev_tor` 抛的是「finished without producing fresh export files」，details
里只有缺失文件名——**答案就在隔壁 `.lis` 里却被丢掉**。这次调查因此先去查 XDAT
与渐晕行。现已复用 `codev_batch` 既有的 `.lis` 快照-认领机制（抗滚动重命名），
把 CODE V 的原话提到 message 并全量进 `details.codev_diagnosis`；重复射线错误按
计数折叠（真机见过同一行 54 次）。

### 已修：不再花真机时间去重新发现探针已知的事

前置闸键在 `rms_wavefront_waves` 是否有读数——**不是代理，它就是本 TOR 的判据**
（polychromatic RMS wavefront error）。四条终止的候选全部把它 withheld 成
`rms_wavefront_seed_value`（度量宏返回理想种子值 = 没有视场被评估）。

**交叉验证**：e11 候选探针读 **0.348343** 波，TOR PER 标称读 **0.348154** 波——
两条独立 CODE V 路径差 **0.05%**。这同时确认了缺陷②所依据的 PER 标称是真的 RMS 波前。

## 缺陷② 0.25 波阈值卡在标称设计下面，两侧一起归零

唯一两侧都测到的 trial（`US-12436366-B2-e11`）报 `yield = 0.0 / 0.0`。PER 直说原因：

| e11 | 标称 f1 | 标称 f2 |
|---|---|---|
| 候选 | 0.3482 waves | 0.2825 waves |
| 对照 | 1.0011 waves | 1.9405 waves |

**施加任何公差之前**四个数就全部越过 0.25 波。未扰动镜头本身不过线时，yield 已不
回答「这设计好不好造」，而是回答「随机扰动多久能把一个已经不合格的设计意外救回来」。

⚠️ **不能说成「算术上必为 0」**：扰动确实能改善某个视场。e11 候选 f2 有 1/20 样本
读到 0.2030（低于标称 0.2825），那 0.05 的 per-field「良率」是运气不是良率。

### 全库普遍性（45 个 TOR 目录 / 118 个视场行）

- **13/118 行（11.0%）标称越线**，落在 **6/45** 个目录
- 越线行**集中在候选侧**：2.71/7.13、5.05/4.40、0.35/0.28 waves
- 对照侧多在 0.03–0.21 waves
- 标称分布：min 0.0306 / 中位 0.1071 / max 7.1331 waves

⇒ 候选像质当前远差于对照（见 memory `project-p1-bottleneck-is-now-candidate-quality`），
**绝对阈值 yield 在候选侧就会永远读 0**，无论公差表现如何。**P3 报的其实是 P2。**

### 两个轴确实正交（这是关键，不是修辞）

`four-piece-v2/trial_US-12210142-B2-e1`：

| | 最坏标称 | 97.7% 最坏退化 |
|---|---|---|
| 候选 | **7.1331** waves（废品） | 0.6293 |
| 对照 | 0.1274 waves | 0.3119 |

候选标称差约 56 倍，公差敏感度只差 2 倍——在 field 2 上候选（0.33）**比对照
（0.31）还结实**。设计差 ≠ 公差脆。

### 已修：改报退化量与相对曲线（`app/core/engines/tor_sensitivity.py`）

北极星禁先验拍绝对阈值。这三个读数一个都不需要：

1. **`tolerance_sensitivity`** — 直接读 CODE V 自己的 PER 退化列、自己的累积概率
   档位（50 / 84.1 / 97.7 / 99.9%）。**零自造数字。** 按方向归一化成「正 = 更差」：
   原始 Change 列对 RMS 为正、对 MTF 为负（真机 `sns-verify/mtf` 读到 **-6.7220**），
   跨判据直接比会**静默翻转符号**。
2. **`relative_yield_curve`** — 阈值取各视场**自身标称**的无量纲倍数，报一条曲线让
   读者自己划线。
3. **`yield_is_informative`** — 标称已越线时判定绝对 yield 不回答公差问题。

**同一批数据，绝对阈值判成平局的两侧被区分开了**：

| e11 | 1.0× | 1.25× | 1.5× | 2.0× | 3.0× |
|---|---|---|---|---|---|
| 候选 | 0.00 | **0.30** | 0.40 | 0.55 | 0.85 |
| 对照 | 0.00 | **1.00** | 1.00 | 1.00 | 1.00 |

97.7% 最坏退化：候选 0.7503 vs 对照 0.1493 = **候选敏感 5.03 倍**。
出厂指标对这同一批数据说的是 `0.0` vs `0.0`。

### 不做「对着存量分布报百分位」

`corpus_quality.py`（PR #156）在像质侧的形状**在这里不适用**：那 45 个目录**不是一个
总体**——公差表都不同（`DLR` vs `DLS`、0.005 vs 0.010）。排名会伪造分母，而不是命名它。

## 仍然没解决的（不要读成已解决）

- **P3 候选侧仍然只有 1 个可测样本**。缺陷①的根因是 P1 候选质量，不在公差链路里，
  本铲修不掉；修好的是「不再误报成公差缺陷、不再烧真机时间、失败时说真话」。
- **`relative_yield_curve` 的倍数梯子（1.0/1.25/1.5/2.0/3.0）是无量纲但未标定的**。
  它是曲线而非单点，所以不需要为任何一档辩护；真要定档需要实测。
- **公差表本身仍 uncalibrated**（`DLT 0.005 / DLR 0.01`，声明为 starter set）。
- **`zmx_writer._append_object_surface` 无条件写 `DISZ INFINITY`** 的缺陷是真的，
  但只影响 10 颗原始真实设计（`3P_*`/`4P_*`/`5P_*`，物距 350–1200 mm），P2 全部
  seed 都是无穷共轭专利，与本故障无关。**另案。**
- **本 worktree 跑不了 4 个既有测试**：路径含 `.claude` 触发
  `ensure_codev_safe_input_path` 的点号分量闸。主仓库 `D:/atelier` 下同文件 55 全绿。

## 复算方式

```bash
uv run pytest tests/test_tor_sensitivity.py tests/test_p2_crosssource_trial.py -q
```

夹具全为真机导出原文（`tests/data/codev_tor/real_sample_*_p2gated_e11_*`、
`real_sample_lis_p2gated_e7_candidate_ca_trace_terminated.txt`）。
五处变异注入（符号不翻 / informative 恒真 / 不剔越域样本 / 去掉前置闸 /
去掉波前判断）**全部被测试抓住**。
