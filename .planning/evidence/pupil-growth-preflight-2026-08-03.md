# 可达性只闸了一半：光圈那一半从来没人管（2026-08-03）

## 结论

`run_codev_target_standard` 同时打两个靶：**EFL 和 F/#**。
`seed_efl_is_reachable`（+25% 拉焦上限）闸的是第一个，**第二个一直没闸**。

实测 2026-08-02 那轮 49 条 trial（`p1-selectpref-ab-20260802`），
定义 **pupil growth = seed F/# ÷ spec F/#**（>1 = 要把光圈开大）：

| | n | 判出 verdict | 占用真机时间 |
|---|---|---|---|
| growth > 1.05 | **11** | **0（0%）** | **13013 s = 全轮的 53.4%** |
| growth ≤ 1.05 | 38 | 35（92%） | 11343 s |

**开大光圈超过 5% 的 trial，一条都没判出来，却烧掉了半轮真机时间。**

## 为什么这是因果而不是相关

49 条里 **41 条跑的是同一颗 seed**（`US-12044826-B2-e4`，F/2.03）。
同一颗 seed 意味着 growth 变动**只**来自对照的光圈，是干净的单变量阶梯——
而结果对它**单调**：

```
 growth  spec F/#   结果
 0.8120   2.50      worse            124.7 s
 0.8638   2.35      worse × 6
 0.8826   2.30      worse × 8
 0.8904   2.28      worse × 2
 0.9144   2.22      worse × 2
 0.9227   2.20      worse × 3
 0.9442   2.15      worse × 2
 0.9807   2.07      worse × 2
 0.9902   2.05      worse × 2 + unmeasurable × 2   ← 见下「不是唯一病因」
 1.0150   2.00      worse × 2       409 s
 1.0410   1.95      worse            49.3 s   ← 判出的最大 growth
 ────────────────────────────────────────── 闸口在这条缝里
 1.0973   1.85      unmeasurable   1266.6 s
 1.1600   1.75      unmeasurable × 2  各 1100 s
 1.2303   1.65      aut_not_converged × 5  各 ~1876 s
```

CODE V 自己给的话是 `Abnormal AUTO Completion - Unable to scale up Pupil and
Field specifications`——它在说的正是这件事。

## 闸口取 1.05 的出处

判出的最大 growth = **1.0410**；比它大的最小值 = **1.0973**。**闸就放在这条缝里。**

**故意不收得更紧**：把闸压到 1.02 会开始砍掉真判出了 verdict 的 trial
（1.0410 那条）。而且 growth ≤ 闸的一侧也有 3 条失败
（0.9902 两条 `optimize_no_preferred` 各烧 2177 s、1.0099 一条 41.5 s），
所以 **growth 超闸是失败的充分条件，不是失败的完整解释**——
这道闸省时间，不负责解释所有失败。

## 诚实边界（三条，缺一条这页就是自欺）

1. **闸是从被它评价的同一轮数据里读出来的。**「零误伤」在这 49 条上**按构造成立**，
   是一次观测到的界，**没有做样本外验证**。
2. **11 条超闸的 trial 只是 5 个互不相同的 (seed, spec F/#) 情形**——
   小样本假象在本项目已中过四次，这里必须说清。
3. **实际省下的是 9 条不是 11 条**：其中 2 条 blocked 在
   `control_engine_disagreement`，那道闸在本预检**之前**，它们各只烧 2.3 s。
   省下的时间 ≈ **13008 s**，占比不变（53.4%）。

## 实现要点

- 预检放在**对照探针之后**：它除的那个 spec F/# 取自探针读数、不是 plan 的声明值，
  这样被闸的数就是 `run_codev_target_standard` 真正会拿到的数（有测试钉死）。
- 判 `verdict="spec_not_met"` / `blocked_at="pupil_growth_not_reachable"`，
  与既有的 `seed_field_not_rebuildable` 同一形态：**trial 照样进分母**，
  只是不烧真机时间。省时间不许抬高 par rate（有测试钉死）。
- seed 没写 `FNUM` 时**放行不拦**（442 颗里 8 颗只写 `ENPD`）——
  拿缺记录当失败是凭空造一个失败。记录里照样留下 `growth: null` 可查。
- 读 `FNUM` 的函数放进 `zmx_import_prep`（`declared_field_count` 的邻居），
  并有一条**全语料对账测试**：与 `codev_roundtrip._parse_system_facts`
  在 442 颗上逐颗相等——两个读同一条记录的函数迟早会给出两个答案。

## 这会改变什么

**不改任何已判出的读数。** 主指标（异源打平率）的分子分母都不动：
被拦的 11 条本来就都在 `judged` 之外。改变的只有**下一轮真机怎么花时间**——
同样的墙钟能跑约 2 倍的 trial。

## 复算

```bash
uv run pytest tests/test_p2_crosssource_trial.py tests/test_zmx_import_prep.py
```

本页每个数字由 `scratchpad/pupil_growth.py` 从 `D:/atelier-p1-runs/p1-selectpref-ab-20260802`
的 49 份 trial JSON + `data/zmx` 的 seed 文件重算，未引用任何跨压缩带过来的记忆值。
