# CODE V 空闲看门狗标定（2026-07-30 真机）

`scripts/p2_crosssource_trial.py::IDLE_TIMEOUT_SECONDS` 从 **60.0s → 150.0s**。
换值不是主要产出，**这个闸第一次有了实测底数**才是。

红线①：三次 bench 前后 CODE V 会话数均实测 **0**（记在每份 run log 首末行）。

## 为什么必须真机测：完成的 run 是被审查过的证据

跑完的 rung **按构造**都满足「最大静默 < 闸值」——不然它就被 kill 了。
所以历史产物里 828 条完成 rung 一条都不能回答「健康的静默到底多长」，
它们只能复述闸值本身。要破这层删失，只能让看门狗**看而不杀**。

`scripts/codev_idle_gap_bench.py` 就是干这个的：把真实批次留下的 rung `.seq`
原样重放，`idle_timeout_seconds=None, observe_idle_gaps=True`，0.5s 轮询记录
每一次输出间隔（生产用 5s 轮询会把一条 5s 就跑完的健康 rung 整个量化进一个桶）。

## 读数

### 健康 rung（n=8，看门狗关闭）

| 最大静默 | 总时长 | AUT cycles | 来源 trial |
|---|---|---|---|
| **7.64s** | 123.22s | 20 | US-20240201471-A1-e4 both vig0200 |
| 7.59s | 117.17s | 20 | US-11906710-B2-e4 both vig0200 |
| 6.06s | 73.58s | 15 | US-11906710-B2-e3 both vig0200 |
| 2.56s | 78.52s | 26 | US-20250216655-A1-e7 both vig0300 |
| 2.55s | 80.75s | 26 | US-12282142-B2-e7 both vig0300 |
| 2.55s | 89.83s | 23 | US-11906710-B2-e2 both vig0200 |
| 2.03s | 8.16s | 9 | US-11668898-B2-e6 asphere vig0600 |
| 2.03s | 6.84s | 9 | US-11668898-B2-e6 asphere vig0700 |

117s 那条记录了 **86 段间隔**，绝大多数 0.5–2s。
⇒ **CODE V 是连续写清单的，不是攒到结束一次性 flush。**
「健康但安静」这个假想失效模式在采样范围内**实测为假**。

### 被 60s 闸杀掉的 rung（n=3，同样关闭看门狗重放）

| 最大静默 | 总时长 | AUT cycles | 清单 |
|---|---|---|---|
| 596.44s | 600.27s（撞硬超时） | 3 | 16106B |
| 596.45s | 600.39s（撞硬超时） | 1 | 27973B |
| 581.23s | 600.39s（撞硬超时） | 1 | 28719B |

三条**全部**在 2–4s 内写完最后一个字节，然后 **600s 窗口内一声不吭、也不退出**。
其中两条正是触发本次调查的 `US-11668898-B2-e6` 的两个配置。
清单字节数与原批次逐字节同尺寸（16106/27973/28719），说明重放忠实。

⇒ **原假设「AUT 静默算了 60 秒以上、看门狗在制造失败」在这 3 条上被证伪。**
它们是真僵尸。分离度：健康 7.64s vs 僵尸 ≥581s，**76 倍**。

## 发火率：JSON 记录严重低估

| 口径 | 分子/分母 | 比例 |
|---|---|---|
| trial JSON 里 `configs.*.error` 带 `no progress for 60.0s` | 18 / 138 config rung | 13.0% |
| 同上，按 trial 计 | 15 / 176 trial | 8.5% |
| **按 rung 从产物重建**（`.seq`/`.lis` 时间戳 + BUF EXP `.tsv` 是否落地） | **218 / 1153** | **18.9%** |

trial JSON 只在**整个配置**死掉时才记 `configs.*.error`；autovig 阶梯**内部**被杀的
rung 一条记录都不留。重建口径：1153 条 rung 中 325 条（28.2%）没产出结果文件，
其中 284 条有后继 rung 可测静默，**218 条落在 58–75s 带**（= 60s 闸 + 5s 轮询 + 启动开销）。

完成 rung 与无结果 rung 的形态差别也很干净：清单中位 **94141B vs 16179B**，
launch→最后输出中位 **7.5s vs 2.4s**。

## 定值

**150.0s**，同时越过两条互相独立的锚：

1. **19.6× 实测健康最大静默（7.64s）**。10× 这条*规则*继承自同日探针标定
   （`feedback-containment-bounds-need-their-own-calibration`）；被乘的**基数**
   是这里现测的，不是借来的——这正是那条教训的全部内容。
2. **高于记录中最长的完整健康 rung（123.22s 墙钟）**。一个 run 的总时长是它
   最大静默的理论上限，所以这条锚**不依赖**「CODE V 连续 flush」这个（已测为真、
   但对未采样的 seed/config 不可证）的行为假设。

上限：必须**低于 180.0s 硬超时**，否则看门狗永远不会开火，而且是**静默地**
不存在——所有 rung 都改由硬超时收走，没有任何东西会报告它已失效。

失败方向是刻意的：**太紧 = 把健康工作静默变成 `unmeasurable`**，与真失败不可区分，
并且系统性污染北极星主指标；**太松 = 只多花墙钟**，硬超时照样兜底。⇒ 朝「跑完」失败。

代价核算：僵尸 rung 从 65s 涨到 155s，对照 180s 硬超时仍省 25s/条。
按历史 218 条僵尸算，看门狗仍在做事，只是不再逼近健康区间。

## 落地

- `app/core/engines/codev_batch.py`：观测与执行拆开。`idle_timeout_seconds` 管杀，
  `observe_idle_gaps` 管看；间隔序列进 `CodeVRawProcessCapture.idle_gaps`、
  `CodeVBatchResult.max_idle_gap_seconds`、错误 details 与 `codev_idle_profile` 日志。
- `app/core/engines/codev_optimize.py`：每条 rung 的 `max_idle_gap_seconds` 进结果字典，
  ⇒ **今后每次批跑都在为这个闸续标定**，不必再靠一次性 bench。
- `scripts/p2_crosssource_trial.py`：新增 `--idle-timeout`（`0` = 关闭），
  重标定不需要改代码。
- `tests/test_p2_idle_timeout_calibration.py`：四条机器闸（余量 / 越过最长健康 rung /
  低于硬超时 / 注释必须带证据）。已逐条验证过**把值改回 60.0 或 180.0 时它们真的会失败**。

## 自陈局限

- 僵尸样本 **n=3 / 218**，且三条同属一颗对照（`US-11668898-B2-e6`）。
  「218 条全是真僵尸」是外推，不是实测。
- 健康样本 n=8，取自 442 颗底库中的 6 颗对照。未采样的 seed/config 只由锚 2 兜底。
- 重放曾**静默测了个空**：`p2-phase1-20260730` 跑完后被改名成 `-VIGNETTE-CONTAMINATED`，
  `.seq` 里烙的是旧路径，按子串重写匹配不到任何东西 → CODE V 报
  `ERROR - Unable to open file` 而 bench 照样打印 "completed 3.72s"。
  已改为**按 basename 重写 + 重写后断言没有任何绝对路径指向重放目录之外**，
  并记录原 rung 的 cycle 数做保真对照（`replay_matches_source`）。
  两条废读数已重跑，本文所有数字来自修复后的运行。

## 原始产物

- `D:/atelier-stagec-runs/idle-gap-bench-20260730/`（healthy 2 + parked 3）
- `D:/atelier-stagec-runs/idle-gap-bench-20260730-healthy-tail/`（healthy 3 有效 + 2 废）
- `D:/atelier-stagec-runs/idle-gap-bench-20260730-healthy-tail2/`（healthy 3，重跑）
- 每目录 `bench.json` + 同名 `.log`
