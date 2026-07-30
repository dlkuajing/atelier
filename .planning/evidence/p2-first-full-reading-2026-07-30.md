# P2 首份完整读数：49 条跑满，par 0（2026-07-30）

裁瞳映射修好后的第一次跑满。**红线① 前后 CODE V 会话数均为 0**，
`run_provenance` 记在 `plan.json` 与 `summary.json`（`git_sha=122d1240`，census sha256 `fdfe52b6…`）。

## 读数

```
trials 49   par 0   worse 35   spec_not_met 5   unmeasurable 9
par rate / all trials  0.0%      par rate / judged only  0.0%
```

**⚠️ 分母不是 49。** 按设计计：**27 个不同对照设计 / 5 个不同 seed 设计**
（49 次 run 里 22 次重复同一对照设计，见 `p2-sample-ceiling-by-design-2026-07-30.md`）。
⇒ **报「par 0/35 judged」时必须同报「27 个独立对照设计」。**

## 逐指标：par 不是「处处全输」

| 指标 | judged 中 par 的条数 |
|---|---|
| RMS 点列径 | **3** |
| MTF | **1** |
| 畸变 | **0** |

⇒ 候选在个别 trial 上**确实打平了单项**，但**没有一条同时打平三项**。
这比「par=0」这三个字提供的信息多得多：差距不是均匀的，畸变是最硬的一项。

## 视场覆盖已基本healthy（裁瞳修正的功劳）

```
field witness shortfall   both_full=40, candidate_partial=3, candidate_zero=6
field coverage cand/ctl   median 1.0  min 1.0   (n=45)
```

修正前同期是 `both_full 4/18`。**49 条里 40 条两侧全视场出数。**

## 四件套（判据③）

| 件 | 实测 |
|---|---|
| 处方 ZMX | **45/49** |
| 相对成本 | **45/49** |
| 像质 | **32/49**（修正前 2/10） |
| 公差良率 | **0/49**（本次按请求跳过） |
| `all_four` | **not_assessable**，并按名报出原因 |

## 选优偏差在规模上更大

```
config choice decided by  aut_not_converged=17, rms_spot=19, tie_fixed_priority=1
RMS gain when RMS chose   median +71.5%  (n=19)
```

11 条样本时中位增益是 +30.1%，**37 条时是 +71.5%** —— 小样本低估了这个偏差。
（`aut_converged` 决定的 17 条不构成该偏差，它不是被判指标。）

## 阻塞分布

```
aut_not_converged 5 ｜ control_engine_disagreement 2 ｜ optimize_no_preferred 2
```

`control_engine_disagreement` 2 条 = 两引擎对对照焦距分歧超容差时**主动不判**，
在最贵那段之前就停 —— 闸按设计工作。

## 时间

中位单条 **178.2s**，49 条约 2.4 小时（跳过公差）。

## 这份读数的定位

**这是基线，不是终点。** 它跑在**旧 seed 池**上——那颗承担多数 trial 的 seed 原生就是
101.27 µm，而对照在 2.3–11.2 µm（`p1-root-cause-routing-gate-2026-07-30.md`）。
seed 质量闸已修但**不在这次批跑里**。下一批带闸重跑才是对
「seed 进入对照量级后 par 会不会动」的检验；本页的 0 是那次对照的基线。
