# `rank_seeds` 的权重不是那条回归的根因——过期的是 target，不是权重（2026-07-30）

## 结论先行

1. **权重不该重调**：对北极星主指标的可测代理，整张权重网格（含 `fov→0`、EFL-only、
   FOV-only）读数**恒为 6/49、中位比 13.93 不动**。原因是结构性的：**49 个对照里有 45 个
   的异源种子池只有 4 颗**。四选一，打分函数没有杠杆。
2. **那条 xfail 的归因是错的**：锚点 `US-20210364737-A1-e8` **从来没有**进过
   `rank_seeds` 的 top-10（重锚前 rank 66、重锚后 rank 53），它的第一名一直由
   stage 1b 召回给的。**把 fov 权重调到 0，锚点从 53 掉到 63——更差。**
3. **真正过期的是测试的 target**：`fov_deg` 重锚了（半→全），这条测试的 `fov=15.3`
   没跟着重锚。按全视场读，它蕴含的像高是 **1.5446mm**，被产品自己的
   `image_height_mm_min=2.5` 拒收。修 target 不修权重，xfail 已摘。
4. **顺带查实一条不成立的既有读数**：`28/59` 复算不出来；语料中位数闸不是"零 trial
   代价"，而是 **49 → 4**。

## 一、权重对主指标没有杠杆（实测）

判据取自 `.planning/evidence/p1-root-cause-routing-gate-2026-07-30.md`：
**配对里有多少条，seed 起点就已经比它要打平的对照成像更好**（两侧都是 CODE V RMS 点列
直径、同一份 census、同一把尺子）。`rank_seeds` 的 argmin 决定 seed，所以这个计数是权重的
函数。

复算：

```bash
uv run python scripts/seed_routing_weight_sensitivity.py --gate off --verify
```

`--verify` 先断言"重算的 argmin 在全部 49 对上与生产 `rank_seeds` 一致"，再报变体——
不然比的就不是同一个东西。

| 变体 | 起点领先 | 中位 seed/对照 | 用到的 seed | 改变的配对 |
|---|---|---|---|---|
| **生产（fov 0.46）** | **6 / 49** | **13.926** | 5 | 0 |
| fov 0.46 → 0.30 / 0.20 / 0.10 | 6 | 13.926 | 5 | 0 |
| **fov → 0** | 6 | 13.926 | 5 | **0** |
| efl 0.20 → 0.46 / 0.60 | 6 | 13.926 | 5 | 0 |
| efl 0.46 / fov 0.20（对调） | 6 | 13.926 | 5 | 0 |
| quality → 0 | 6 | 13.926 | 6 | 2 |
| efl only | 6 | 13.926 | 6 | 3 |
| fov only | 7 | 13.926 | 6 | 4 |

**池子大小分布：`{4: 45, 47: 2, 48: 2}`。** 92% 的对照是在 4 颗里挑 1 颗。

`fov only` 那个 7（+1/49）不作数：它是丢掉 EFL 维的退化权重，且 n=49 上 +1 就是
`feedback-measurement-traps` 第 ② 条点名的小样本假象。

⇒ 这与 `domain-bounds-vs-market-2026-07-29.md` 从另一侧得到的结论一致
（"打分不是瓶颈，可选项的数量才是"）。**本铲把它从"顺手证伪一条 backlog"升级为
"对主指标本身实测无杠杆"。**

### 顺带回答任务书里另外两问

- **池相对归一化（`_norm_delta` 按池跨度归一，跨对照不可比）**：确实存在，但**不是这里的
  杠杆**。改成相对误差归一（`|target−value|/target`，无标度、跨对照可比）后，长焦锚点
  从 rank 53 挪到 47，**第一名不变**。单对照内 argmin 有定义、跨对照比较无意义这一点仍然
  成立，但它是**报告口径**问题而非路由质量问题——`p2-pair-feasibility-2026-07-28.md` 已经
  记着「`rank_seeds` 距离跨池不可比，只有 argmin 有效」，本铲补上的是"换成无标度归一也不
  改变谁被选中"这一条实测。**不需要为它单开修复工单**，需要的是任何报距离数的地方都不要
  跨对照比。
- **给 `rank_seeds` 加像质距离维**：它**已经有**一维（`quality`，权重 0.24–0.45）。
  把它归零只改动 2/49 条配对，判据纹丝不动。再加一维像质距离在当前池子大小下同样没有
  杠杆——**这条不做**，理由是实测而非偏好。

## 二、锚点丢掉第一名的真实机制（重锚前后同代码 A/B）

同一份代码，只有语料变了（`67a4dd9b^` vs 本栈 HEAD），target `efl 11.5 / fov 15.3 / f2.2`：

| | 重锚前 | 重锚后 |
|---|---|---|
| primary（`rank_seeds` top-10）最好两席的 band / score | `5to15` / 12.6 · 14.3 | **`gt30` / 35.1 · 36.0** |
| 对应的 seed 原生 EFL（target 11.5mm） | ≈13.2 · 13.4 mm | **17.7 · 18.0 mm（差 54–57%）** |
| stage 1b 的 fov cap | 3.700° | 2.592° |
| stage 1b 召回数 | **17** | **0** |
| 锚点 `US-20210364737-A1-e8` 的 `rank_seeds` rank | **66** | **53** |
| 锚点 `\|Δfov\|` | 2.984° | **9.333°** |
| 锚点最终名次 | **1**（走 stage 1b） | 被淘汰 |

**锚点两次都不在 `rank_seeds` 的 top-10 里。** 它的第一名从来由
`_fov_bounded_efl_close_extras`（stage 1b）给，而 stage 1b 的筛选是一道**硬**
`|Δfov| ≤ cap`，与权重无关。锚点自己的 `fov_deg` 从 12.316 翻成 24.633，`|Δfov|` 2.98 →
9.33，**连重锚前的 3.7° cap 都过不去**。

单变量消融（长焦池 n=110）进一步排除权重嫌疑：

| 变体 | 锚点 rank |
|---|---|
| 生产 | 53 |
| **fov 权重 → 0** | **63（更差）** |
| quality 权重 → 0 | 46 |
| quality → 0 且关掉 spec_guard | 20 |
| fov → 0 且 quality → 0 | 5 |

`fov→0` 反而更差，是因为权重会重归一：让出来的 0.46 摊到 `quality` 上，而锚点的
`quality` 恰好是满格 1.0（**它被判为像质 floor violation，占它距离平方的 85%**）。
真正压住锚点的是 `quality` + `_seed_spec_guard_penalty`（+0.2566），不是 fov 权重。

## 三、根因：过期的是 target

长焦桶**整桶**都存的半视场，重锚时统一 ×2.00（抽查
`US-12372756-B2-e7/e9/e10`、`US-20260160979-A1-e6`、`US-12436366-B2-e10`、
`US-12571987-B2-e2/e5`、锚点本身，全部 ×2.00）。**但测试的 target `fov=15.3` 没有跟着挪。**
兄弟那条 wide 测试没坏，正是因为它的锚点 `US-11719917-B2-e6` 的 `fov_deg`
**本来就是全视场**（61.4612 → 61.4612，×1.00）——一条坏一条不坏，由数据解释干净。

按全视场读，`efl 11.5 / fov 15.3` 蕴含的像高：

```
imh = 11.5 · tan(15.3°/2) = 1.5446 mm      < image_height_mm_min = 2.5
```

产品自己的闸**拒收**这条 spec。它此前之所以看着"合法"，是因为
`validate_scenario_params` **逐轴独立**判定，从不校验 `imh ≈ efl·tan(fov/2)`——
不报像高就查不出来。（同一条一致性计算，`p2_crosssource_trial._first_order_imh_disclosure`
已经在算了，但那里"只披露不筛"。）

原 docstring 的意图是"target 贴近场景 FOV 下界，仍是合法客户请求"。重锚后这句话的正确
表达是：**在给定 EFL 上真正咬合的下边界是像高下限，不是 `fov_deg_min`**——

```
fov_min(efl) = 2·atan(image_height_mm_min / efl) = 2·atan(2.5 / 11.5) = 24.530°
```

该 target 下实测：**rank 1 = 锚点本身，band `lt5`，score 4.260**，且
sanity 断言仍成立（锚点仍不在 `rank_seeds` top-10 里，仍是货真价实的 stage 1b 召回）。
24.53–27° 区间内结论不变，不是踩在悬崖边上。

**这不是重新钉锚点**：24.530° 由 `SCENARIO_BOUNDS.image_height_mm_min` 与 target EFL 独立
导出，锚点自己的视场是 24.633°——它落在边界内侧是测出来的，不是写进去的。测试里 target
**按公式现算**，`SCENARIO_BOUNDS` 再改或视场约定再翻一次，机器会自己复核。

### 主动交代：另一种读法不成立，以及为什么 24.530° 才是忠实的那个

有人会问「作者写 15.3 是不是就是半视场，重锚后直接翻倍成 30.6° 就好」。**实测：30.6° 下
rank 1 是 `US-12372756-B2-e6`（band `5to15`、score 5.715），不是锚点。** 所以这两种读法给出
不同结论，必须说清楚选哪个、为什么：

原 docstring 把 15.3 的来历写死了——**"贴近场景 FOV 下界 15.0°"**，即它是照着
`SCENARIO_BOUNDS.fov_deg_min` 挑的，不是照着某颗镜头的半视场挑的。所以忠实的重锚是
**"该 EFL 下最窄的合法视场"**，而重锚之后这个"最窄"由像高下限咬合、不再由 `fov_deg_min`
咬合 ⇒ 24.530°。30.6° 那种读法要求作者当初想的是半视场，与它自己的 docstring 冲突。

### 不是踩在悬崖边上（0.25° 步长扫描）

| target fov | rank 1 | band |
|---|---|---|
| **24.00 – 27.25** | **锚点 `US-20210364737-A1-e8`** | `lt5`（score 4.260） |
| 27.50 – 32.50 | `US-12372756-B2-e6` | `5to15` |
| 32.75 以上 | 逐段换人，全部 `5to15` | |

**测试的 24.530° 落在 3.25° 宽的平台内侧**（距下沿 0.53°、上沿 2.7°）。

### 域外那一段本身是不稳的（值得单独记一笔）

同样 0.25° 步长，往域下界**以下**扫：

| target fov | 蕴含像高 | band |
|---|---|---|
| 15.00 – 15.75 | 1.51 mm | **`gt30`**（score 35.13） |
| 16.00 – 16.25 | 1.62 mm | `5to15` |
| 16.50 – 17.25 | 1.67 mm | `lt5` |
| **17.50 – 18.00** | 1.77 mm | **`gt30`** |
| 18.25 – 18.50 | 1.85 mm | `5to15` |
| 18.75 以上 | 1.90 mm | `lt5` |

**在产品域外，target fov 动 0.25° 就能让漏斗在「EFL 差 4.5%」和「EFL 差 35%」之间来回跳。**
域内（≥24.53°）没有这个现象。机制：stage 1b 的 cap 由 primary 自己导出，而域外的 primary
本身在churn ⇒ cap 跟着跳 ⇒ 召回集合跳。

⇒ **那条"回归"是这段不稳定区的一次采样**，不是权重的系统性偏移。也说明
`validate_scenario_params` 不校验 `imh ≈ efl·tan(fov/2)` 这个缺口有真实后果：它放进来的
请求，漏斗给出的答案是不可复现的。

### 附带修的

新增 `test_telephoto_anchor_target_is_in_domain_but_the_stale_one_is_not`：把"target 是
合法客户请求"这句话本身变成机器判据——旧 target 连同它蕴含的像高必须被
`ParameterGuardError` 拒收，新 target 必须整轴通过。

## 四、`28/59` 复算不出来，语料中位数闸也不是零代价

任务书要我拿 `28/59`（闸打开后起点领先的配对数）当判据。**它复算不出来**：

| 闸 | trials |
|---|---|
| 关 / 100 µm | **49** |
| **语料 p50（当前默认）** | **4** |
| 语料 p25 | 4 |

`scripts/p2_pair_census.py::default_seed_quality_limit_um` 的 docstring 声称中位数闸
"costs **zero** trials -- all 59 eligible controls still have a qualifying cross-source
seed"。实测**代价是 49 → 4**，且"59"在树里找不到出处：三份 P2 run plan
（`D:/atelier-stagec-runs/p2-*/plan.json`）记的都是 `trials_available = 49`。

引入该闸的提交与本栈 HEAD 之间只动过一份证据文档和一份测试文件，**语料 / provenance /
census 脚本一律未动**，所以那个提交当时也是 4，不是 59。

机制：74 颗 usable 里 45 颗 Largan、25 颗 provenance 未知，非 Largan 只剩 4 颗；Largan
对照的异源池至多就是这 4 颗，中位数闸下一颗都不合格 ⇒ **45 个 Largan 对照全部掉出**。

**这条假声明不只在 docstring 里，它被钉成了一条测试，而且那条测试本来就是红的**：
`tests/test_p2_pair_census.py::test_gating_at_the_corpus_median_costs_no_trials` 断言
`gated["trials"] == loose["trials"]`，在本栈 HEAD（未动任何代码时）实测
`assert 4 == 49` 失败。**CI 看不见它**——它带 `skipif(not _PERFIELD.is_file())`，而那份
runtime census 在 worktree 之外，只有装了 CODE V 的 Windows 机器上才有，Ubuntu runner 上
恒跳过。本铲把它改成钉**实测代价**（`gated < loose/2`、且掉出的确实是
`no_cross_brand_seed_available`），并保留它唯一为真的那半（闸确实丢掉了坏 seed 设计）。

**后果是活的**：`plan_trials` 走的是 `census()` 的默认值，所以本栈上再跑一批 P2，计划的是
**4 条**而不是 49 条——依据是一句实测为假的"零代价"。

**本铲只更正 docstring，不动默认值**：改它等于在"主指标样本量掉一个数量级"和"主指标
可信度"之间二选一，属主公裁定项，已记入待裁定队列。

## 复算

```bash
uv run python scripts/seed_routing_weight_sensitivity.py --gate off --verify
uv run python scripts/seed_routing_weight_sensitivity.py --gate p50
uv run pytest tests/test_orchestration_generators.py -k "telephoto_anchor or recovers_real or genuinely_far_fov"
```

## 诚实边界

- 判据本身**只在当前池子大小下**无杠杆。底库长到异源池不再是 4 颗时，本结论必须重测——
  脚本留着就是为了那一天。
- 6/49 与 4/49 都是**起点**读数，不是打平率；它只说明"起点有没有戏"，不预测 par。
- 长焦锚点那段 A/B 用的是重锚前后两份语料 + 同一份代码，隔离的是语料变量；stage 1b 的
  cap 收紧（3.7 → 2.592）与锚点自身 `|Δfov|` 翻倍**两条都足以单独淘汰它**，本页没有把
  两者的相对贡献拆开——因为任一条都是充分的，拆开不改变结论。
