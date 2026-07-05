# Atelier — Optical Design Agent

独立研发仓库。前身是 `dlkuajing/lumira` 仓库的 `lumira-backend/` 目录，
2026-07-03 经 `git subtree split` 拆出（历史完整保留）。

## 北极星

专家级展示论证：资深光学设计师看了不能觉得"比不过"。非商用，不管侵权。
执行路线已切换为 .planning/ROADMAP.md 九阶段（2026-07-03 立项）：Phase 1/3/4/8 完成、5 部分完成（CODE V 11.5 已装于 D:\CODEV115，spike 进程闭环，无原生 ZMX 导出待方案）、2/6/7/9 进行中/待推进。推进方式=gsd-loop 多车道夜车（见 .planning/decisions.log）。

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
