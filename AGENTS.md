# Atelier — Optical Design Agent

独立研发仓库。前身是 `dlkuajing/lumira` 仓库的 `lumira-backend/` 目录，
2026-07-03 经 `git subtree split` 拆出（历史完整保留）。

## 北极星

**唯一目标真相锚 = [`.planning/NORTH-STAR.md`](.planning/NORTH-STAR.md)（v2，2026-07-27 主公裁定）。术语见 [`CONTEXT.md`](CONTEXT.md)。**
本节只作摘要，冲突以 `NORTH-STAR.md` 为准。

把手机镜头「**出一版设计**」这个动作自动化：从结构化 spec 到可评审交付物，零人工介入，
一次运行覆盖多个独立需求，质量对标同规格专利原设计。价值 = **产能放大**（设计师从"画图的人"
变成"选方案的人"）。替代边界只到「出设计」动作，**不碰**试制支持 / 装配方案 / 产线排查 / 客户现场。

四条判据全部可复算、**不需要任何人类签字**：① 产出能力（N 需求零介入产 M 交付物）
② 异源打平率（seed 与对照专利不同族时不劣于原设计的比例；同源提升率仅作内部诊断）
③ 交付物四件套（处方 / 像质 / 公差良率 / 相对成本，缺一不算交付）④ 第三方可独立复核。
`N`、打平率门槛、`T` 一律**待实测再填，禁止先验拍板**。

`[EXPERT]` 已从开发 gate 移到销售验收环节——项目内不存在该角色，产品内不得再有任何
等待专家签字才能推进的节点。AR 近眼显示与严格杂散光/鬼像验证为外部工具链例外格，明确不做。
非商用，不管侵权（商用/合规定位=待主公决策项）。

⚠️ **v0.1 的 A–F gate 治理协议已 SUPERSEDED**，冻结于 `.planning/archive/north-star-v0.1/`，
不再是任何 gate、判据或工作源。其废弃根因与仍需重新引入的部分（M-01~M-06 机器并发安全，
须剥离密码学签名链）见该目录 `SUPERSEDED.md`。

历史执行路线：`.planning/ROADMAP.md` 九阶段（2026-07-03 立项）：Phase 1/3/4/5/8 完成
（CODE V 11.5 装于 `D:\CODEV115`，ZMX↔CODE V 闭环=DB 读数直出重建，见
`app/core/engines/codev_readout.py`+`zmx_writer.py`）、2/7/9 进行中、6 待启。
staging ZMX 不可得（主公 2026-07-05 裁定），底库靠 USPTO 采集。ROADMAP 阶段划分成型于 v0.1
体系下，**须按 v2 判据重新对齐**。

## 推进范式（2026-07-27 主公裁定）

**主力 = goal-driven**：读 `.planning/NORTH-STAR.md` 判断当前最该做的一铲 → 做 →
看结果 → 再定下一步。判断留在回路内。

**`gsd-loop` 降级为按需调用的批量工具**，不再是默认推进方式。只在任务同时满足三条时才用：
① 能预先枚举成一串**同构**小任务 ② 每条判据**机器可判** ③ **不需要看上一条结果**决定下一条。

判定依据（实测，非推断）：

- loop 累计产出 57 条 `loop:` 提交、41 条进 main，**全部是上述形态**——USPTO 波次采集
  （`DATA-08x`：续采 ≥100 落 batchN，`@accept` 为 `grep -q "1814" tests/test_patent_pool.py`）
  与 parser 受让人族扩展（`DATA-09x`）。底库 159 → 1814 原料池 / 442 可路由案例是 loop 的实绩。
- 但 v2 判据缺口对应的工作，多数**不满足条件③**：46 blocked 根因诊断、按诊断修产出率、
  MC 饱和、成本模型设计，都要看上一步结果才知道下一步做什么。
- 结构原因：loop 的"指挥官"是 [`orchestrator.sh`](file) 的
  `pick_task_line()` = `grep '^- \[ \]' backlog.md | head -1`，**无模型**；
  执行层裸调 `codex exec`，不传 `--model`/effort，全部继承 `~/.codex/config.toml`
  （当前 `gpt-5.6-sol` / `model_reasoning_effort=high`）。**全部规划智能被前置到"写 backlog
  那一刻"，循环运行期间零判断**——跑偏了回路内没有任何环节能察觉。

⚠️ 注意：全局 CLAUDE.md 提到的项目级 `.codex/config.toml` **本仓库不存在**，
codex 推理强度实际由全局配置决定；`--effort xhigh` 逐次升档只对 `codex:rescue` 路径有效，
loop 路径没有传参口子。

## 与 lumira 官网的关系（drift 契约）

- 生产（fly.io）仍从 lumira 仓库的 `lumira-backend/` 部署；本仓库为纯研发，
  成熟后再决定回灌或切换。
- **生产 bugfix 双打契约**：修 bug 先在本仓库落地，再 cherry-pick 回
  lumira/lumira-backend；反向变更同理必须同步，防止双仓 drift。
- 官网 `/agent` 前端滑块边界（BOUNDS）⊆ 本仓库 `app/core/parameter_guards.py`
  的 SCENARIO_BOUNDS，改边界必须两边对齐。
- 代码里 `cd lumira-backend && ...` 形式的命令字符串是烙进契约/测试断言的
  展示文案，本仓库中执行探针以脚本自身位置解析 backend 根（见
  `scripts/export_acceptance_tasks.py` 的 BACKEND_ROOT 注释），勿按字面重构。

## 技术要点（接手必读）

- Python 只用 `uv`；测试：`uv sync --frozen --group dev --group optical`
  然后 `uv run pytest`（LLM 调用已 mock，CI 用 placeholder key）。
- **Windows 本机跑测试必须 `PYTHONUTF8=1`**：案例 JSON 为 UTF-8，中文
  Windows 默认 GBK 会炸 42 个测试（CI 在 Ubuntu 不受影响）。
- Optiland 0.6 陷阱：angle 视场 / NaN / numpy / sentinel，见
  `app/core/optiland_patches.py`。
- ZMX ingest 曾因 XASPHERE 系数错移一阶+截断 8 项导致 RMS 407µm 假象
  （E1-01 已修）；渐晕 VDX/VDY 离焦丢失是第二病灶（E1-02 已修）。
  改 ingest/metrology 前先读这两段 git 历史。
- 已知问题：专利 seed case_id 无 IMH token → 运行时像高 0.0，近乎不可路由。
  E2 批 2 头号工单「可路由化三件套」：ZMX 实算真 IMH / 路由重锚 / eval 重锚。

## 数据资产

- `app/data/optical_cases/`：442 个正式案例（17 个原始真实设计 + 425 个专利设计）
- `data/zmx/`：442 颗正式 ZMX
- `data/patents/`：714 条 USPTO 发现元数据；不是全文专利湖
- `data/patent-ledger/`：专利饱和 snapshot/audit（必须由脚本重算，不以手写摘要为真值）
- `lens-data-staging/` 的 109 颗外部 ZMX 不可得（主公 2026-07-05 裁定），不得当作当前可用资产
