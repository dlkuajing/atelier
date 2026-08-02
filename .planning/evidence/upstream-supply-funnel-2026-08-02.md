# 上游供给漏斗：异源 seed 池只有 4 颗，而且坏在一个批次上（2026-08-02）

`.planning/GOAL-PROMPT-AUTONOMOUS.md` §5 把「一阶瓶颈 = 上游供给」定成结论，但没有把
供给是**在哪一步、被哪道闸、削成多少**说出来。本页把它算出来。

所有数字由 `scripts/upstream_supply_funnel.py` 从两个输入重算，产物
`upstream-supply-funnel-2026-08-02.json` 带三份 sha256（census / index / quarantine）。
**不跑 CODE V、不跑 Optiland、不追迹**——只读 2026-07-28 的逐视场普查与语料索引。

```bash
uv run python scripts/upstream_supply_funnel.py --census D:/atelier-stagec-runs/trace-census-20260728/perfield-census.jsonl --json .planning/evidence/upstream-supply-funnel-2026-08-02.json
```

## 一、漏斗

| 段 | 数 |
|---|---|
| 语料索引 | 442 |
| 有 CODE V **全场**读数（`n_positive == num_fields`） | 218 |
| 且过「可追迹 + 保真度」两闸 | 192 |
| 且过产品参数闸（`load_usable_case_ids` 的 screen 3） | **74** |

74 里按受让人：LARGAN 45 ／ **受让人未知 25** ／ KANTATSU 2 ／ AAC 1 ／ NINGBO SUNNY 1。
受让人未知的既不能当对照（`control_provenance_unknown` 25），也不能当异源 seed
（`brand_of_case` 返回 `None` 即被排除）。

⇒ **一个 LARGAN 对照——49 条 trial 里的 45 条——在全语料里能取到的跨受让人 seed 是 4 颗。**
这就是 `seed_reuse = [["US-12044826-B2-e4", 41], ...]` 的来历，不是打分器偏心。

## 二、可达性从来不是那道绑定闸（推翻一个流行说法）

记分板把 `seed_pool_basis = {reachable_only: 46, reachable_and_quality: 3}` 读成
「+25% 拉焦上限逼着我们用差 seed」。把 2026-08-02 那 49 条真机 trial 的
`spec_efl / seed_efl - 1` 逐条算出来：

| | |
|---|---|
| 最小 | **−0.434**（缩焦） |
| 中位 | **−0.209**（缩焦） |
| 最大 | **+0.193** |
| 超过 +25% 的 | **0 / 49** |

**一条都没顶到那道闸。**`reachable_only` 这个标签下面其实是**质量短缺**：
逐对照把池子筛下去（seed 池按两闸口径），中位 59 → 43（可达）→ 13（≤语料中位）；
但在**今天的三闸 seed 池**里，同一串筛只剩 4 → 更少 → 3/49 有质量达标的可达 seed。
**区别全在 screen 3，不在 +25%。**

## 三、screen 3 是对照侧的判据，却被同时施加在 seed 上

`load_usable_case_ids` 的 docstring 自己写着 screen 3 的理由：

> **inside the product's domain** — the control's own spec must pass
> `parameter_guards.validate_scenario_params` … A control defines the spec a
> customer would ask for; if the product's own guard would reject that request
> with HTTP 400, measuring against it says nothing about the product.

这段推理**从头到尾是关于对照的**。seed 不是一个请求，它是被优化到**对照的** spec 去的起点；
候选是否落在产品域内由对照的 spec 决定，与 seed 自己的 spec 无关。
而 `p2_pair_census.census()` 的异源池写的是 `case_id in usable_set`（三闸），
于是这道对照侧的闸把 seed 池一起砍了：

| seed 池口径 | 每个对照能取到的跨受让人 seed（中位） |
|---|---|
| 今天（三闸） | **4**（min 4, max 48） |
| screen 3 只施于对照 | **59**（min 59, max 164） |

## 四、⚠️ 但「直接放开」会换来另一种假象——已实测，不要照做

把 seed 池换成两闸口径后，`rank_seeds` 选出来的 seed：

| | 今天（三闸） | 两闸 |
|---|---|---|
| 被选中 seed 的 CODE V 全场 RMS，中位 | 101.27 µm | **2.64 µm** |
| seed / 对照 RMS 中位 | 13.93 | **0.36** |
| `seed_pool_basis` | 46 + 3 | **49 全部 reachable_and_quality** |
| **被选中 seed 与对照的 \|ΔFOV\|，中位** | — | **43.9°（49 条里只有 2 条 ≤5°）** |

那批「更好的」seed 好在**视场窄**：头号 seed `US-20200057277-A1-e1` 是 31.7° 全场、
像高 1.007 mm，要被重新对准到 70–90° 全场去。**起点数字漂亮，候选大概率照样烂。**
所以正确形态是**联合**：screen 3 只留给对照，同时给 seed 加视场匹配上限——
而不是单纯放开。加上 20° 视场上限后，能拿到「可达 + 视场匹配 + ≤语料中位」seed 的对照
只有 **8/49**（今天是 3/49）。这是真实的天花板，不是调参能绕过去的。

## 五、坏得有批次形状：DATA-10b 是 0/28

| intake_batch | n | 中位 RMS | ≤语料中位 | **≤自身 FOV 桶中位** | 受让人 |
|---|---|---|---|---|---|
| DATA-09d1 | 103 | 8.83 µm | 60 | **67** | LARGAN 58 / SAMSUNG 24 / KANTATSU 15 / AAC 4 |
| （无批次） | 29 | 15.83 | 8 | 6 | 未知 28 |
| **DATA-10b** | **28** | **134.71 µm** | **0** | **1** | **NINGBO SUNNY 22 / ABILITY 6** |
| DATA-06c | 25 | 5.61 | 19 | 21 | LARGAN 25 |
| DATA-06f | 18 | 8.20 | 12 | 10 | LARGAN 18 |
| DATA-06f-b11 | 11 | 7.32 | 9 | 6 | LARGAN 11 |
| DATA-10a | 2 | 223.23 | 1 | 1 | AAC 2 |

**「≤自身 FOV 桶中位」这一列是专门用来反驳我自己的**：DATA-10b 里有 94°/130°/133° 这种
超广角，超广角本来点列就大，拿全库中位当尺子对它不公平。按**同 FOV 桶**中位重判后
仍是 **1/28**（DATA-09d1 是 67/103）。⇒ 不是「难设计被不公平判据打成缺陷」，是批次问题。

**这件事直接咬 P2**：异源要求把 P2 从 LARGAN 赶出去，而 LARGAN 之外只有
SAMSUNG（24 颗，健康）、KANTATSU（15）、SUNNY+ABILITY（28 颗，全在 DATA-10b）。
承担 41/49 条 trial 的那颗 seed `US-12044826-B2-e4` 正是 SUNNY / DATA-10b / 101.27 µm。

## 六、八颗发散追迹，被一道 16 个数量级的空档隔开

| 量 | 越 1e6 的 | 线下最大 | 线上最小 |
|---|---|---|---|
| `image_height_mm` | **8** | 51.875 | **5.837e+17** |
| CODE V 全场 RMS 直径 µm | **5** | 17358.0 | **3.196e+20** |

并集 8 颗，全在 DATA-10b（`US-11719917-B2-e2..e6`、`US-12032139-B2-e2/e4/e6`），
**`corpus-fidelity-quarantine.json` 一颗都没拦**。
截断值 1e6 不是调出来的：**真值最大与发散值最小之间隔着约 16 个数量级的空档**
（51.9 → 5.8e17；17358 → 3.2e20），1e6 只是落在这道空档里的一点。
脚本把两个边界都写进产物，读者可自证——**空档是事实，切点在空档里的哪个位置无关紧要**。

⚠️ 顺带证伪一个看似干净的判据：「点列直径 ≥ 自身像高 ⇒ 不是成像系统」在本库**几乎抓不到东西**
（218 颗里只有 1 颗），因为分母和分子**一起发散**——像高本身就是 5.8e17。
可用的是量级空档，不是这个比值。

## 七、出厂索引仍带着它自己那道像高闸拒收的行

`scripts/image_height_gate.py`（PR #167）只在**生成期**被 `patent_to_zmx.py` 调用；
出厂的 `index.json` 早于它，且**没有任何消费者复核**。把闸重新施于出厂索引：

| 判决 | 数 |
|---|---|
| plausible | 398 |
| implausible | 34 |
| reference-unusable | 10 |

（34 + 10 与 `scripts/e2_golden.py` 里钉的 pin 数一致，互证。）

- 被拒且仍在**域内对照池**里：**0** —— 今天没有对照拿 6e17 当 spec，这条是好消息。
- 被拒且仍在**两闸池**里：**15** —— ⇒ 第三节那个「screen 3 只给对照」的改动，
  **必须同时按这道闸过滤 seed 池**，否则等于把 15 行发散数据请进种子池。

## 八、分母对账（收口 GOAL-PROMPT §6 第 3 项）

在 main（`fa5275df`）上实跑 `scripts/p2_pair_census.py`：

```
case index 442 / usable 74 / valid cross-brand trials 49
excluded: control_provenance_unknown 25
seed_pool_basis: {"reachable_and_quality": 3, "reachable_only": 46}
seed_reuse: [["US-12044826-B2-e4",41], ["US-20260063869-A1-e3",4], ["US-11933948-B2-e11",2], ["US-12282142-B2-e7",1], ["US-12436366-B2-e5",1]]
```

与 2026-08-02 真机轮 `summary.json` 的 seed 分布**逐项相同**。

⇒ **当前口径 = 49 条 / 74 usable / 46+3。**
记分板 `north-star-scoreboard-2026-07-30.md` 的 **59** 与 `reachable_only 53 / both 6`
是 **fov 重锚之前**的数（`load_usable_case_ids` docstring 自述「the 55 (28.6%) this
docstring used to claim predates the `fov_deg` re-anchor」）。两个数不冲突，是两个时点。
**记分板那两处应标注为历史值。**

## 九、下一铲（按本页证据排序）

1. **修 DATA-10b**（28 颗，含 8 颗发散）。它是唯一一处「坏得成批、且正好坏在 P2 唯一
   能取种的那半边语料上」。诊断走静态解析，不需要真机。
2. **seed 池与对照池解耦**：screen 3 只施于对照 + seed 侧加像高闸 + 视场匹配上限。
   离线可先出 `seed_pool_basis` 与 `|ΔFOV|` 对照表，真机 A/B 再确认候选是否真变好。
3. **受让人未知 25 颗补齐 provenance**：它们今天两头都用不上，是最便宜的一块供给。

## 诚实边界

- 218/442 才有全场读数，本页所有质量结论的分母是 218，不是 442。
- census 是 2026-07-28 的，其后 `data/zmx` 未变更（最后一次提交早于普查），
  `index.json` 变过（fov 重锚等）但不碰 ZMX 字节；产物记了三份 sha256。
- 第四节「候选大概率照样烂」是**推断**，不是实测——它建立在「视场扩 2.2 倍是真实设计改动」
  这个物理事实上，但没有真机 A/B。要拿它当结论必须先跑。
- 第五节没有回答 DATA-10b **为什么**坏，只证明了它成批地坏。根因诊断是下一铲。
