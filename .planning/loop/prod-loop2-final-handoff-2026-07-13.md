# “生产可用”工程代号 loop2 终版 handoff（2026-07-13）

> **判定边界**：本文只记录代码、CI、机器过程与可重算工件。`[EXPERT]` 始终为空；
> AI 未作良品、合格、qualification、量产可用或良品率判定。
> “生产可用”/`production-ready` 只是本轮工程代号，不是资深判定结果。
>
> **发布终点**：loop2 技术实现经 PR #68–81 落地；最终功能 merge 为
> `9249f97834a3bff52bb38e3e6ff456c7ec0aaec3`。PR #81 CI run `29227838587`
> success，匹配该 merge SHA 的 main CI run `29229500265` success。

## 一、A–G 完成定义

| 车道 | 终态 | 磁盘 / Git 真值 |
|---|---|---|
| A · P13 铲3 | ✅ | PR #74；freeze-seq 谜团 CLOSED；矩阵 v7 为 20/20 可执行格。见 [dossier](p13-freeze-seq-mystery-2026-07-11.md) 与 [matrix](p13-matrix-2026-07-11/p13-snap-matrix.md)。 |
| B · P14 铲2 | ✅ | PR #68；TOR 接线与 PER/MC 语义闭合。默认公差表在阳性设计上 MC 饱和 0.858–0.916，故 yield 仍 unavailable，公差表待资深 ratify。见 [语义记录](p14-per-semantics-2026-07-11.md) 与 [matrix](p14-tor-matrix-2026-07-11/README.md)。 |
| C · Stage B F/# | ✅ | PR #75；`CONVERGED_FIELDS` 能力上限为 `efl + conditional fnum`。F/# 仅在本候选 ladder 四条件 gate 全真时为 converged。 |
| D · P17 收尾 | ✅ | PR #71；优化 ZMX 持久化与 1–3 次串行 repeat 引擎落地，重复分布固定到首个成功 run 的 preferred config，禁止跨配置混样。见 [review summary](../quick/260711-p17-closeout-review-fixes/260711-p17-closeout-review-fixes-SUMMARY.md)。 |
| E · P18 批量 | ✅ | PR #72/#77/#80；50 targets / 50 jobs / 50 valid CandidateSets，29 succeeded / 21 degraded / 0 failed。见 [晨检](phase18-night-20260711-morning-audit.md)。 |
| F · Stage C | ✅ | PR #76/#78/#79/#81；离线 contract、runner-attested v3、8×3×2 真机矩阵、单 exact target production/export 与 Stage C 实现发布检查闭合。 |
| G · 收官 | 发布 gate | 本 handoff、`STATE.md`、`decisions.log` 与本机 shared memory 按同一事实更新；仅在本 tracked 变更 PR→CI→merge→main CI 成功并删除 heartbeat 后记为 ✅。 |

## 二、四层证据，禁止互相偷换

### 1. P18 夜批是流水线状态，不是良品率

- tracked audit JSON SHA256：
  `5b6fb2aa99df291d98923235820bc00837971e6cbf65df9394eb4a19b5278c31`。
- 50/50 全终态：29 `succeeded`、21 `degraded`、0 `failed`。
- `job-0020/attempt-1` 与 `job-0021/attempt-1` 永久排除；current attempt-2 才可信。
- 29/21 描述编排结果，不描述候选是否为良品。

### 2. Stage B 8/8 是选定输入闭环，不是良品率

- authority manifest：`D:\atelier-stagec-runs\stageb-inputs\manifest-v2.json`。
- SHA256：`29384d5d9a10356c8b9bd908c48ab6970977fcafe77ac59a100aaf268350d969`。
- 8 unique accepted / 30 unique outcomes / `complete=true` / 无 incomplete attempt。
- 6 条为 `pre-run-bound`；2 条为显式
  `retrospective-current-state-adoption`，绝不升级伪称 pre-run attestation。
- e5/e6 属同一专利族相关样本；8 条不构成独立良品率样本。
- legacy 14 文件 inventory SHA256 仍为
  `7ef51a215fd3d54de432c7acff724afda967323205d755266ba7761f8eee24d7`，
  SHA/size/mtime 均未改写。

### 3. Stage C 矩阵是 2 delivered / 46 blocked，不是 4.17% yield

- 冻结 plan SHA256：
  `fa7aa3105ff756ca146699467a27224e899dd8aa58e7ef9e1df735e1c25a1ba1`。
- state SHA256：
  `dfb5da3779f7f8052a63fa63703e082ca3e902d616475a3047705e892a7e19aa`。
- 8 unique seeds × 3 canonical arms × 2 repeats = 48；48 attempts / 48 runs /
  48 unique run IDs / 48 unique receipt hashes；failed=0、incomplete=0。
- 结果为 2 delivered / 46 blocked；仅 6/48 run 的 spot/WFE 可用，3/24 cell
  complete，21/24 unavailable。
- `delivered/blocked` 是逐 run 的完整交付 gate；`blocked` 表示至少一个交付条件未过，
  不等于执行 failed/incomplete。`cell complete` 是另一条指标聚合口径：同一 cell 的
  两次 repeat 都有可用 spot/WFE；因此 3 complete cells 对应 6 metric-usable runs，
  其中仍可有 run 因其它交付条件而 blocked。
- 当前可发布报告：
  - JSON SHA256 `36759d97bdd6860a47df39ad494e84774dc1ed7d7200e71b872e6b028c22baf8`
  - Markdown SHA256 `1cda840291168b9f9354def55b858463e2cfc59d0f41ff07af1c13c003d4addb`
- 首版统计误混 sentinel，已逐字节保存在
  `D:\atelier-stagec-runs\stagec-real-matrix-20260713\historical-pre-sentinel-stats-fix`；
  旧 JSON/MD SHA256 分别为
  `3eb0e38e44eef5f7223c70f6956c5de0f7d5fe513656a716b2746a05f8440aa4` /
  `c7b786724e5f1e716452accc1ddcaf9c81f9a9ce6a8a399bd9d0961bade11925`，
  只作 incident evidence，不得发布。

### 4. Production 只闭合一个 exact target

- seed：`US9304295B2`；smartphone-wide；EFL
  `3.558938281682459 mm`；IMH `2.91297 mm`；F/2.5；6 elements。
- FOV 不硬填四舍五入值，而由同源 EFL/IMH 派生为
  `78.60024620364187°`。
- fresh Stage B attempt `6b70df21fd6541cb81ff63301fddec49`；accepted ZMX SHA256：
  `5c438b3e56845888017cf90f600a5c4509b71dddb6619532f113a9d195ab57b9`。
- production receipt：
  `C:\Users\Administrator\.atelier\stagec-runs\stagec_20260713T041603Z_47d3b72fd1\post-run-receipt.json`，
  SHA256 `e7ffd0b7d68741fe3ae4f306cc3f7febd963696f4a3232e5d4cde45cefe10b18`。
- reconstructed/delivered candidate 字节相等，SHA256：
  `3a445ec1d063553a3c8c83675cd75cd54392cd4b20e7b49ce9ae11a88b2e09e8`。
- publishable `exports-v2`：
  - manifest `de2af28a70827d77cea4fddea7ef5f56a7c832febc3aacf7e67be4f9c7199d04`
  - XLSX `102994106800eeecc105f242ce8366f3703c351162624b01d1412720f4617351`
  - ZIP `88197068db356b4cc26f2bda06726989d6d5d5c92de0993c738501f3f0bb0f64`
- 该闭环只证明这个 exact target 的 fresh Stage B → Stage C receipt → candidate →
  export 同源；不能外推为通用量产能力。

## 三、当前语义真值

- `CONVERGED_FIELDS[TARGET_CONVERGED] = {"efl", "fnum"}`：这是能力上限。EFL
  为该 mode 能力；F/# 必须由本候选自己的 Stage B ladder 逐候选证明，四条件为：
  实测 F/# 在外层 target/tolerance 内（布尔值须重算一致）、AUT converged、
  ray-traceable，以及 closed-positive ray grid（Normal AUTO completion、REFL/MISS=0、
  无 abnormal/aperture-conflict）。任一不满足都不授予 `fnum` converged。
- IMH 可由 production Stage C 的 RIH reconstruction + machine receipt 证明
  `achieved`，但不是 Stage B optimizer 的 converged field。
- FOV 只允许由同源 EFL/IMH 派生或实测；TTL 从不属于 optimizer converged。
- 当前案例库为 442：smartphone-wide 227、telephoto 137、ultrawide 78；442/442
  index 记录有非空 `image_height_mm`。
- 所有 expert verdict 仍为 `null`/文件不存在；机器结果页、XLSX 与 ZIP 均不代填。

## 四、必须保留的事故与限制

1. **外层 C1 CLI exit=1**：Mode1 在缺显式 FOV 时按其检索契约失败；唯一 Mode3
   production candidate 已闭合，但不得称“全 orchestrator 成功”。
2. **旧 production report 文案矛盾**：原始 `report_01.json/.md` 仍写 Stage C
   IMH/FOV 未落地，却同时含 attested `image_height_achieved=true`。原件不重写、不重签，
   只作 incident evidence；`exports-v2` 才是当前发布语义。
3. **PR #81 首轮 Ubuntu CI**：run `29225939487` 为 2700 passed / 17 skipped /
   2 fixture failures；两个测试夹具泄漏 Windows `D:` 路径。fix-forward 只隔离 fixture，
   未放宽 production authority，run `29227838587` success 后才合并。
4. **post-P1 真机边界**：最终 Windows executable lease/share-deny 加固后没有再次启动
   真实 CODE V。下一次真机必须重新走 official executable/macro/version gate；任何
   loader/version 不兼容只允许在 receipt 前 fail-closed。
5. **本地全仓超时非结论**：一次额外全仓 pytest 被 304 秒工具上限终止，未取得退出码，
   不计 PASS；PR/main CI 才是全仓真值。

完整实现、事故与回归细节见
[Stage C GSD plan](../quick/260712-stagec-real-evidence/260712-stagec-real-evidence-PLAN.md)。

## 五、下一棒：仍需资深或外部输入

| 项目 | 当前边界 / 下一动作 |
|---|---|
| 良品率 go/no-go | NEED 主公/资深：对交付候选做人工筛判；2/46、8/8、29/21 都不是 yield。 |
| TOR 默认公差表 | NEED 资深 ratify：阳性设计的 MC 仍高饱和，现有 yield 继续 unavailable。 |
| staging 109 ZMX | 外部电脑同步，尚未进入本仓。 |
| 商用/合规定位 | NEED 主公；本 loop 未改变非商用边界。 |
| 下一次 Stage C 真机 | 不从 chat memory resume；复核 retained ledger/artifact hashes；证明 runner、CODE V/codevm、P18/global/per-call owners 全零；再过 official executable/macro/version gate 与 lease 补丁后的首次兼容性验证。 |
| 数据/引擎工单 | `vd=0` 不得由 Optiland 伪成 50；专利 seed WAVM 短表需全池 24 槽化；5P rebuilt MTF NaN；P13 D 臂 GLD 与 withheld EFL；Stage B listing/WRX/WRY；C1 多 requirement artifact-key 冲突。 |
| 外部工具墙 | 严格杂散光/鬼像需非序列工具；AR 波导需 RCWA/物理光学工具链。 |

## 六、恢复入口

新 session 按以下顺序读取：

1. 本文件；
2. [Phase18 晨检](phase18-night-20260711-morning-audit.md)；
3. [Stage C GSD plan](../quick/260712-stagec-real-evidence/260712-stagec-real-evidence-PLAN.md)；
4. `app/core/orchestration/candidate.py::CONVERGED_FIELDS` 与相关测试；
5. retained runtime artifacts（按上列绝对路径与 SHA256 复核）。

真正发起下一次机器调用前，再按同一顺序执行：不从 chat memory resume；复核 retained
ledger/artifact hashes；证明 runner、CODE V/codevm、P18 owner、global owner、per-call
owner 全零；重走 official executable/macro/version gate；把 lease 补丁后的首次兼容性
验证作为 gate。loader/version 不兼容必须在 receipt 前 fail-closed。

heartbeat `atelier-loop2` 只在本 handoff、`STATE.md`、shared memory 与 decisions 落地且文档 PR/main
CI 成功后删除；删除即表示 loop2 自动续跑职责结束，不表示北极星 go/no-go 已由资深通过。
