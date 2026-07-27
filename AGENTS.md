# Atelier — Optical Design Agent

独立研发仓库。前身是 `dlkuajing/lumira` 仓库的 `lumira-backend/` 目录，
2026-07-03 经 `git subtree split` 拆出（历史完整保留）。

## 北极星

**唯一目标真相锚 = 仓库根 [`NORTH-STAR.md`](NORTH-STAR.md)（v2，2026-07-27 主公裁定）。术语见 [`CONTEXT.md`](CONTEXT.md)。**
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
体系下，**须按 v2 判据重新对齐**。推进方式=gsd-loop 多车道夜车（见 `.planning/decisions.log`）。

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

- `app/data/optical_cases/`：39 个案例 seed（17 真实设计 + 22 专利 seed）
- `data/zmx/`：39 颗 ZMX 原文件
- `lens-data-staging/`（109 颗手机镜头 zmx）在另一台电脑，尚未同步进本仓库
