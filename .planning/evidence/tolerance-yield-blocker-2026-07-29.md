# 四件套最后一件（公差良率）的拦路虎已定位到行（2026-07-29）

**一句话**：TOR 真机管线**跑通了**，MC 侧格式**完全吻合**，卡点是
**`_parse_per` 只支持 `metric='mtf'` 变体**——而 `run_codev_tor` 接受
`metric='rms'` 并产出它解析不了的表头。顺带在真机 MC 数据里逮到
**第 10 例「退化值 = 理想读数」**。

> ⚠️ **本文首版把这条写成「PER 解析器认不出真机导出的表头」，那个说法太宽、
> 会误导下一任去改错地方。** 实测更正见文末「更正记录」。

## 真机跑批结果

seed `US-12124006-B2-e2`，20 次 Monte-Carlo，metric=`rms`。
CODE V 报「28 tolerances and compensators have been used」，两个导出都生成。

**红线①**：两次真机跑批前后实测 `codev`/`codevm` 会话数**均为 0**。

| | 状态 |
|---|---|
| TOR 管线（`run_codev_tor`） | ✅ 跑通 |
| MC 导出解析 | ✅ 格式与解析器期望**逐字吻合** |
| **PER 导出解析** | ❌ **`TOR export parse failed: PER declarations/header missing`** |
| yield 语义 ratify | ❌ 被 PER 挡住 |

## MC 侧是好的（别去动它）

```
	Number of Monte-Carlo samples:	20
Sample	Zoom	Field	Criterion	Value
1	1	1	RMS	0.648139
1	1	2	RMS	1.1183
```

20 样本 × 2 视场 = 40 行，样本号 1–20 齐全。`_parse_mc` 的期望
（声明行 + `["Sample","Zoom","Field","Criterion","Value"]` 表头）**完全匹配**。

## PER 侧才是卡点

真机 PER 表头（第 13–14 行）带**概率分位列**：

```
		Relative Field						Design + tolerances				Changes				Compensator Range(+/-)
Eval Zoom	Eval Field	X	Y			Weight	Design	Criterion	50.0D0%	84.1D0%	97.7D0%	99.9D0%	...
```

`50.0D0%` / `84.1D0%` / `97.7D0%` / `99.9D0%` 是**概率分布点**（约 ±1σ、±2σ、±3σ）。
`_parse_per` 认不出这个两行表头结构。

⚠️ **这不是「照着改格式」就行的活**：要先看懂这些分位列的语义
（它们是「设计+公差后的性能在该概率下的值」），才能决定解析成什么。
**所以我没有动它。**

## ⚠️ 第 10 例「退化值 = 理想读数」，就藏在良率原始数据里

真机 MC 第 21 行：

```
4	1	1	RMS	0
```

**RMS 波前误差恰好为 0** —— 物理不可能（衍射设下界）。

这正是 `tor_yield.mc_saturation_fraction` 要数的东西，也解释了
`TorYieldPolicy.max_saturation_fraction` 为何是**必填**字段。

**如果有人直接拿 MC 值算良率，这颗样本会被当成「完美装配」计入通过率。**
`tor_yield` 那道 default-off 的闸**不是多余的**。

## 下一任的第一步（卡点已具体到行）

1. 修 `_parse_per`：认真机的两行表头 + 分位列（`app/core/engines/codev_tolerance.py:318`）
2. 然后才谈 ratify yield 语义：`TorYieldPolicy` 需要
   `semantics_ratified=True` + `semantics_evidence` + `max_saturation_fraction`
3. 公差表本身**未标定**——按北极星 §3，绝对值不准不影响排序，
   **但必须两侧同表**（与相对成本指数同一条道理）

## 本次用的输入（可复算）

```python
table = TorToleranceTable(('DLT S1..16 0.01', 'DLR S1..16 0.02'),
                          'uncalibrated mobile-lens starter set (atelier)')
comp  = TorCompensators(('CMP DLZ SI',), 'image-plane focus only',
                        'back focus refocus at assembly')
```

**踩过的坑**：`CMP THI S16` 是错的——CODE V 报 `ERROR - Expecting tolerance`，
该位置要的是公差类型（`DLZ`）不是 `THI`。`DLR` 在空气面会被跳过（只是 warning，不致命）。
产物在 `D:/atelier-stagec-runs/tor-probe2/`（仓库外）。


## 更正记录：不是「认不出真机表头」，是「只支持 MTF 变体」

首版结论过宽。补跑 `metric='mtf'` 后拿到决定性证据：

| metric | TOR 是否跑完 | 导出 | 解析 |
|---|---|---|---|
| `rms` | ✅ 跑完 | ✅ PER+MC 都生成 | ❌ PER 表头无 `Frequency`/`Azimuth` 两列 |
| `mtf` | ❌ **跑不完** | ❌ 无 | — |

**`_parse_per` 期望的表头是**：

```python
["Eval Zoom","Eval Field","X","Y","Frequency","Azimuth","Weight","Design","Criterion"]
```

`Frequency`/`Azimuth` **只有 MTF 变体才有**——RMS 波前误差没有空间频率与方位角，
CODE V 在那两列输出空白。**所以解析器不是「读不懂真机」，
而是只为 MTF 写的，却被一个接受 `metric='rms'` 的 API 喂了 RMS 输出。**

**这仍是真缺陷**，但形状不同：是 **API 接受的入参空间 > 解析器支持的空间**，
修法是「让 `_parse_per` 按 metric 走两套列布局」，**不是**「重写它去认真机格式」。

### 另一条独立事实：这颗 seed 做不了 MTF-metric TOR

`metric='mtf'` @ 100 lp/mm 在 `US-12124006-B2-e2` 上直接终止：

```
WARNING - This system is not isoplanatic at field(s) 2.
ERROR - No rays traced in position 1, field 2 - RUN TERMINATED
CODE V> BUF EXP B1 ... ERROR - Buffer number 1 does not exist
```

即**换 metric 绕不开**：这颗 seed 的第 2 视场在该频率下追不出光线。
下一任若要走 MTF 路线，得先换一颗能在 100 lp/mm 出数的 seed 做语义 ratify。
