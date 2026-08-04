# Project State

## Project Reference

唯一目标真相锚 = `.planning/NORTH-STAR.md`（v2，2026-07-27）。术语 = `CONTEXT.md`。
另见 `.planning/PROJECT.md` 与 `AGENTS.md`。

**北极星 v2 摘要：** 把手机镜头「出一版设计」这个动作自动化——结构化 spec → 交付物，
零人工介入，多需求覆盖，质量对标同规格专利原设计。价值 = 产能放大。
四条判据全部可复算、不需要人类签字。

**命名：** `production-ready` / "生产可用"是 loop2 时期的工程代号，不是量产可用结论。

## 四判据当前读数（2026-08-04 · 新 session 先看这里）

**唯一记分板 = [`.planning/evidence/north-star-scoreboard-2026-08-04.md`](evidence/north-star-scoreboard-2026-08-04.md)**
（26 个 headline 数字全部经 `scripts/audit_scoreboard_numbers.py` 从产物重算比对）。
下面只是索引，冲突以记分板为准。

| 判据 | 读数 | 一句话 |
|---|---|---|
| **P1 产出能力** | N=**59** / M=**49 on-spec** / T=**31.5 min** | 第一次有三元组；3 条 trial 吃掉 21.9% 墙钟（autovig，未修） |
| **P2 异源打平率** | **0** | **优化器这条路已封闭**（加权与硬约束各一条剂量-反应曲线）；卡在 seed 供给与异源规则，属主公口径 |
| **P3 四件套** | **50** 产出四件 → **49** 打中 spec → **45** 良率有意义 | 第一次有数；此前恒 `not_assessable` |
| **P4 可独立复核** | 218 次重算 0 失败 | **畸变 1.0005 跨引擎可复现**（⇒ P2 的结论不是单引擎假象）；RMS/MTF 不可逐项复现 |
| **T1 客户侧采用** | **不可测** | 无客户渠道。**T1 闭合前不得表述为「已达成北极星」** |

**下一步不在代码里**：P2 能否推进取决于
[`.planning/PENDING-RULINGS.md`](PENDING-RULINGS.md) 第 **00** 项（异源定义 / 对照集组成）
与第 **0** 项（对照侧要不要装像质闸）——两条都改判据分母，AI 不碰。

### 2026-08-05 补：P2 卡点的机制第一次被拆开（0 真机）

见 [`evidence/p2-seed-pool-census-2026-08-05.md`](evidence/p2-seed-pool-census-2026-08-05.md)。
**§00 的结论没变（仍是主公口径决策），但它给的三条理由都不成立**，且错在把可测的说成不可测：
合格池是 **129 case / 46 专利**（9 是被**选中**的数）；「四闸」第三闸 `|Δfov|` 不存在
（是软惩罚不是过滤）；「普查加不进一个条目」——普查加进来的就是下面这两张表。

**能服务 spec 的直线 seed 从哪来**（品牌闸、且只把品牌闸抬掉；2% 档，59 个对照）：
异源可取 **6/59**，同品牌·异专利 **48/59**（中位 5 个互异处方）。
⚠️ **两者不互斥，族规则能够到的是并集 52/59**；**59 个对照 case 只是 37 个互异设计**
⇒ **选项 A（受让人→专利族）第一次有价码：6/59 → 上界 52/59（按设计 5/37 → 30/37）**，
解锁只差主公注册一个 EPO OPS 免费 key（`ops.epo.org` 实测 403，网络本身通）。

**合格域在哪一层耗尽**（限制在对照 ±5° 视场内；不带这个限制的版本近乎空话）：
按 case `cross_source` **10** / `reachable` **32** / `preferred` **11** / `chosen` **0** / 无需 6；
按对照设计 **7 / 17 / 8 / 0 / 5**
⇒ **路由不是病灶**（两个分母、四档阈值全 0）；**拿掉最多的是 `MAX_SEED_EFL_STRETCH=0.25`
（32/59，17/37 设计），比品牌闸还多**。
⛔ **但不要为它排真机**：被挡掉的 seed 需要的额外拉伸量中位 **+370%**（短了 4–5 倍焦距），
把闸抬到 +100% 只放行 3/63 ⇒ 复标定这个常数改变不了任何东西。详见待裁定队列第 5 项。

**⚠️ 下面的 Phase 13–18 / loop2 段落成型于 v0.1 体系，仅作沿革，不是当前工作源。**

## Current Position

| Scope | Status |
|---|---|
| 北极星 v2 | ACTIVE（2026-07-27 主公经 grilling 六轮逐条裁定并落盘）。`N` / 异源打平率门槛 / `T` 三个数值**待实测**。 |
| 北极星 v0.1 A–F 治理协议 | **SUPERSEDED**，冻结于 `.planning/archive/north-star-v0.1/`。不再是 gate、判据或工作源，不消耗 loop 预算。 |
| Phase 13 glass-snap 铲3 | 完成；PR #74，matrix v7 20/20 可执行格。 |
| Phase 14 TOR 铲2 | 完成；PR #68。默认公差表在 v2 下**不再需要专家 ratify**（同表同施于候选与对照，排序不变），但 MC 饱和仍是真实病灶。 |
| Phase 15 Stage B F/# | 完成；PR #75。F/# 仅由候选自己的 closed ladder gate 条件授予。 |
| Phase 17 close-out | 完成；PR #71。ZMX 持久化与串行 repeat engine 落地。 |
| Phase 18 batch | 完成；PR #72/#77/#80。50/50：29 succeeded、21 degraded、0 failed。 |
| Phase 16 Stage C | 完成技术证据闭环；PR #76/#78/#79/#81。48-run matrix + 单 exact target production/export。 |
| ROADMAP 九阶段 | 阶段划分成型于 v0.1 体系下，**须按 v2 判据重新对齐**（未做）。 |

**Release truth:** PR #81 merge `9249f97834a3bff52bb38e3e6ff456c7ec0aaec3`；PR CI run
`29227838587` success；匹配 merge SHA 的 main CI run `29229500265` success。
Loop2 G docs PR #82 merge `d35b3d07cead830396d24d2b10665199c73985e0`；匹配 main CI run
`29233888562` success。

## Evidence Snapshot

以下数字产生于 v0.1 体系，**在 v2 下不自动继承任何含义**；重新计量须按 `NORTH-STAR.md` 判据口径。

- **P18**：50 targets / 50 jobs / 50 valid CandidateSets；29 succeeded / 21 degraded / 0 failed。
  污染的 job-0020/0021 attempt-1 永久排除。
- **Stage B**：8/8 unique accepted，30 outcomes，6 pre-run-bound + 2 retrospective，no incomplete。
  manifest SHA256 `29384d5d9a10356c8b9bd908c48ab6970977fcafe77ac59a100aaf268350d969`。
- **Stage C**：48/48 receipts，**6 delivered / 42 blocked**；6/48 run metrics usable；3/24 cells complete。
  ← PR #89 按 CODE V 单精度回读修正不可满足的 landing 比较后重放全包所得；v2 判据 ①
  的当前真实基线仍是产能堵塞，不是放大。
- **Production**：仅 `US9304295B2` 一个 exact target 完成 fresh Stage B → Stage C receipt →
  candidate → exports-v2 同源闭环；外层 C1 CLI exit=1。
- **Convergence**：`TARGET_CONVERGED` capability ceiling 为 `efl + conditional fnum`；
  IMH 可被 Stage C 证明 achieved 但非 Stage B converged；FOV derived/measured-only。
- **Case library**：442 = smartphone-wide 227 / telephoto 137 / ultrawide 78；442/442 `image_height_mm` 非空。
  ← v2 下这 442 颗的角色从"说服力素材"升级为**统计对照组**。
- **旗舰候选**：RMS 2.80µm（片数/规格与外部参考的可比性**未核**，不得直接对外比较）。

### Patent saturation import and transport

这些数字是专利数据资产与离线重放状态，不自动证明 v2 北极星距离：

- 714 个 USPTO 元数据根；正式库 442 个设计，其中 425 个为专利设计。
- 冻结重放 619/619，missing=0、corrupt=0；generic metadata residual 已降为 0，
  但外部家族队列、正式 family closure、source exhaustion 与更广义专利饱和仍未闭合。
- 完整 229-commit 逻辑历史保留在本地 source archive
  `codex/patent-saturation-ledger@6dad8ab8`；发布分支
  `codex/patent-saturation-slim` 只改变传输/证据闭包。
- 最终 LFS 清单为 4,269 路径、4,226 个唯一 SHA-256 对象、
  2,043,282,327 logical bytes / 1,942,561,003 unique bytes。
- `20572753` 的发布前传输审计：普通 Git delta 为 22,510 blobs /
  1,015,117,510 uncompressed bytes，最大 blob 4,557,660 bytes，独立 pack
  30,010,009 bytes，远低于 GitHub 2 GiB 单次 push 限制。
- fresh-checkout 修复补入此前被忽略、但被测试/账本引用的 865 个 patent-lake 文件与
  8,675 个 conversion-attempt/staging 文件；两个无引用 OCR ONNX 模型继续忽略。
- 首轮传输/证据闭包门禁为 4,133 passed、1 skipped、10 deselected；合入
  `origin/main@42e05fbb` 后的本地完整离线门禁为 4,133 passed、1 skipped，
  31 条定向并行回归全绿；Ruff、CI YAML、diff、LFS fsck 与 hydrated manifest
  rehash 均通过。
- 合入主线后首次照搬 `uv run pytest -q -n 4` 时，因上游命令未排除 marker 且本机
  安装了 CODE V，意外启动了一条 `real_machine` round-trip；该用例以 wavelength
  24 vs 3 失败并退出，未重跑。CI 已改为显式
  `uv run pytest -q -n 4 -m "not real_machine"`，后续全量验证未再触发 CODE V。
- `origin/main` 在最终全量门禁后通过 PR #89 前移的两提交已由 `17d71802` 合入；
  四个受影响 Stage C/orchestration 测试文件 193/193 通过。
- Draft PR #92 已完整上传 4,226/4,226 LFS 对象；首轮 CI `30253145666` 的 LFS
  hydration/fsck 成功，但旧 `-n 4` 路径出现七个失败标记并在 45 分钟、76% 时取消，
  不构成 merge pass。
- 主线已实测私有 runner 为 2 cores / 7 GB 并证伪 xdist；当前合入
  `origin/main@a5d3eb07`，保留主线串行 `--durations=25`，叠加
  `-m "not real_machine"` 与 LFS hydration，扩展套件 timeout 有界提高到 75 分钟。
  新增 acceptance/wavelength/material 受影响套件 122/122 通过、3 条真实机 deselected；
  替换 CI `30280348106` 在 56m54s 内跑完，结果为 4 failed / 4,128 passed /
  7 skipped / 10 deselected。四项均为历史 Windows 路径在 Linux checkout 中的解析失败：
  两项反斜杠相对路径、一项回执绝对 worktree 路径、一项离线 CODE V 守卫按宿主
  `Path` 解析 Windows 命令。修复仅在测试读取层用 `PureWindowsPath` 映射当前 checkout，
  保留 1,616 份含绝对路径的原始回执及其哈希不变；精确失败集与守卫参数 8/8 通过，
  Ruff/diff 通过。run `30285724536` 在 `f96270b0` 全绿：4,132 passed / 7 skipped /
  10 deselected，pytest 54m47s、job 56m55s，LFS fsck 成功。
- 该 run 期间 `origin/main` 经 PR #93/#94 前移 8 提交至 `4449d7c9`，包含多波长
  导入接缝、指标 fail-closed、测试与可追迹率普查；已无冲突合入
  `ec5f02e5`。因上游触及生产 engine 与测试，`f96270b0` 的绿不能覆盖新 HEAD；
  又因下述本机进程红线继续暂停本地 Python/pytest，须由下一轮 hydrated PR CI
  完成最终集成验证。
- 2026-07-28 00:38 +08:00 的测试后只读库存两次发现短时 `codev`/`codevm`：
  PIDs 22288/21752（00:38:03）及 3516/5288（00:38:38）；均在 CIM 父进程查询前自行
  退出，来源未能证明。未终止或控制进程；发现后停止本地 Python/pytest，余下只做
  Git/GitHub 发布操作。测试前库存为 0。

## Blockers / Concerns

**v2 体系下的真实阻塞：**

- **判据 ① 基线极差**：Stage C 2/46。零介入多需求产出能力是当前头号缺口。
- **判据 ② 无数据**：异源跨规格泛化能力从未系统实测。memory 记录 `缩焦全收敛 / 拉焦 +25% 起挂`
  （2026-07-09 观察，需重新核实）。**`N` 与打平率门槛必须等这轮摸底数据才能填。**
- **判据 ③ 缺两件**：公差良率（MC 饱和 → yield unavailable）与相对成本指数（模型不存在）
  均未落地。四件套目前只有处方 + 像质两件。
- **CODE V 并发安全**：当前低层启动链与用户级可替换锁不构成单实例保证；直接 `Popen`
  与 Web/CLI/batch/probe/test 多个启动面未收口。真机跑批前必须解决——这是**普通工程需求**，
  按普通 backlog 项处理，**不再套 v0.1 的密码学签名链**。
  参考 `.planning/archive/north-star-v0.1/backlog.md` 的 M-01~M-06 节（仅取工程内容）。
- **存量工单**：unknown dispersion provenance、专利 WAVM 24 槽化、5P MTF NaN、
  P13 GLD/withheld EFL、Stage B listing/WRX/WRY、C1 artifact-key collision。
- **外部依赖**：另一台电脑的 109 颗 staging ZMX；商用/合规定位（待主公决策）。

**已解除的阻塞（v0.1 遗留，v2 下不再成立）：**

- ~~NEED 资深：TOR 默认公差表 ratification~~ → v2 用相对比较，公差表绝对值不影响排序。
- ~~NEED 人类 minimum-claim authority / custody / clock attester~~ → 整套治理协议已废。
- ~~13 棵固定树不得发布~~ → 该发布链随 v0.1 归档，不再适用。

## Session Continuity

**新 session 起手**：读 `.planning/NORTH-STAR.md` → 根 `CONTEXT.md` → 本文件 → `AGENTS.md`「推进范式」节。

**推进范式（2026-07-27 主公裁定）**：主力 = **goal-driven**（读北极星判断下一铲 → 做 →
看结果 → 再定下一步，判断留在回路内）。`gsd-loop` **降级为按需调用的批量工具**，不再是默认
方式——只在任务能枚举成一串同构小任务、判据机器可判、且不需看上条结果定下条时才用。
`.planning/loop/backlog.md` 当前**不存在**（loop2 收尾时清空），需要时按上述三条件现写。
详见 `AGENTS.md`「推进范式」节。

**不要**从 `.planning/archive/north-star-v0.1/` 恢复任何 gate、backlog 或判据——它是冻结归档。

**真机前提**：不要从 chat memory 恢复 P18 或 Stage C runner。任何 CODE V 调用前先确认
`runner` / `codev` / `codevm` 相关进程为零，并复核保留的 ledger/artifact 哈希。
