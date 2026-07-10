# Phase 13 铲 1：真实玻璃 snap 设计

日期：2026-07-11
状态：设计 + 纯 Python 离线 spike；**不接** `codev_optimize` 主链

## 1. 目标与边界

把 AUT 在塑料 GLA 域内产生的 fictitious model glass，确定性匹配到真实材料牌号；
每面独立选择，整机统一回验。AI/LLM 不参与牌号、坐标或数值计算。snap 不是“最邻近就
一定替换”：超出容差必须保留 fictitious，并把原因、最近距离和 provenance 如实输出。

本铲只交付算法契约和离线核。固定真实玻璃、短 AUT、三快照、ZMX 写回及 scorecard
接线属于铲 2，须在真机窗口验证后实现。

## 2. 已证实事实与证据边界

| 事实 | 证据 |
|---|---|
| GLASSFIT 用 `Nd` 与 `dn=(Nd-1)/Vd` 的接近度，不考虑 stain、bubbles、partial dispersion、availability 等 | `D:\CODEV115\macro\glassfit.seq:16-23` |
| 宏参数 `disp_factor` 表示色散差相对 Nd 差的权重；宏按当前波长把它换算成 `dispFac` | `glassfit.seq:68-77,107-112` |
| 实际排序距离为 `sqrt(delta_Nd² + (delta_dn*dispFac)²)` | `glassfit.seq:666-687` |
| 官方宏需要选目录、任务、面范围并回答提示，是交互式流程，不能原样塞进无人批跑 | `glassfit.seq:156-200,303-330,421-423,534-580` |
| CODE V 目录名称不是跨目录唯一；目录可列索引/可用性，停产材料仍可能为兼容旧设计而保留 | `LensSystemSetupRM.pdf` 印刷页 406、409（PDF 页序约 420、423） |
| fictitious 与 real 即使 Nd/Vd 相近，partial dispersion 差异仍可能显著影响二级色差 | `LensSystemSetupRM.pdf` 印刷页 410（PDF 页序约 424） |
| 当前仓库批跑以 `.seq → codev.exe /B → BUF EXP → Python parse` 取结构化结果，不抓 stdout 数值 | `app/core/engines/codev_batch.py:1-4,142-188` |
| 当前 target AUT 用 `GLC S^s 0` 放开玻璃，并注入 GLA 凸包 | `app/core/engines/codev_optimize.py:604,687-711` |
| 当前读数已有 EFL 与 RMS WFE 结构；RMS WFE 调 `RMSWE` | `app/core/engines/codev_optimize.py:54-81,1686-1742` |
| 仓库确定性材料表及 H-LAK53A 的 Python 值 | `app/core/zmx_materials.py:27-52`（H-LAK53A 在 46 行） |

`Optimization.pdf` 第 9 章/印刷页 201 起含 Glass Expert；本铲没有据此推断可直接批跑的
Glass Expert 命令。如何用批处理冻结目录玻璃、如何设置短 AUT 周期，均列为**待真机验证**。

## 3. Python 确定性 snap

### 3.1 输入目录

默认候选目录从 `MATERIAL_ND_VD` 中显式筛出手机镜头塑料域真实牌号：ZEONEX、OKP、
EP、APEL、SP3810。不能把 GLA 探边点、PMMA/PC 抽象角点或未知 placeholder 当真实牌号。
未来可附加真实玻璃目录，但每条必须至少带稳定的 `catalog_id + glass_name + Nd + Vd +
source/version`；因 CODE V 名称跨目录不唯一，最终标识不能只有 glass name（手册印刷页
406）。

### 3.2 距离与确定性

对 target 与每个目录材料计算：

```text
dn = (Nd - 1) / Vd
D  = sqrt((Nd_target - Nd_real)^2
          + (disp_factor * (dn_target - dn_real))^2)
```

这是 GLASSFIT 的同坐标、同加权欧氏距离；离线核把 `disp_factor` 直接作为归一化权重。
官方宏还会按当前 FGW/波长换算 `dispFac`（`glassfit.seq:107-112`），铲 2 若需逐字节复现
CODE V 排序，换算关系须用真机样本校准，当前不得臆造。

输入、目录值和权重必须有限；`Nd>1`、`Vd>0`、`disp_factor>=0`。距离相同按牌号字典序
打破平局，保证跨运行稳定。离线 spike 的暂定接受边界为 `D <= 0.01`；这是 **Atelier
策略值，不是 CODE V 官方容差**，真机矩阵后再 ratify。边界包含等号。

### 3.3 每面独立 snap + fail closed

1. 从 CODE V readout 取每个玻璃面的 fictitious `(Nd,Vd)`；同一实体元件的前后面若共享
   材料，铲 2 必须先建立 element identity，避免两个面被独立写成不同牌号（待真机验证）。
2. 每面独立跑最近邻，保留 `delta_Nd/delta_dn/distance/disp_factor/catalog version`。
3. 最近邻距离在容差内才产生真实牌号；否则 `glass_name=None`，保留 fictitious，记录最近
   距离并标 `fictitious`。绝不强行替换后标成 real。
4. 所有面选择完成后才进入整机冻结与全局回验；局部距离小不代表整机像质可接受，尤其
   GLASSFIT 明确未考虑 partial dispersion（`glassfit.seq:16-23`；手册印刷页 410）。

## 4. snap 后处理链（铲 2 目标）

```text
before-fictitious
  → 每面确定性 snap
  → 固定真实目录玻璃（GLC 关闭）
  → after-snap-frozen 快照
  → 短 AUT：只放半径/已授权非球面 DOF，玻璃保持冻结
  → after-snap-reopt 快照
  → 三快照差异 + per-surface snap ledger + provenance
```

三快照必须来自同一批跑设置、同一视场/波长/渐晕定义，并至少输出：

| 指标 | before-fictitious | after-snap-frozen | after-snap-reopt |
|---|---:|---:|---:|
| EFL (mm) | 值 | 值、绝对/相对偏差 | 值、相对 before 偏差 |
| max RMS spot (µm) | 值 | 值、绝对/相对偏差 | 值、相对 before 偏差 |
| max RMS WFE (waves) | 值 | 值、绝对/相对偏差 | 值、相对 before 偏差 |

任一快照缺失、非数或设置不一致，整颗候选 snap verification 为 unavailable/withheld，
不得用另外两列冒充完整验证。短 AUT 的具体 cycle/IMP、玻璃冻结命令、目录限定语法与
快照宏拼接方式均**待真机验证**。现有 `BUF EXP`/readout 只证明结构化导出路径可复用，
不证明上述新宏已经可运行（`codev_batch.py:142-188`; `codev_readout.py:183-343`）。

## 5. 跨引擎表值冲突

H-LAK53A 已知 Python 表为 `(1.678,55.5)`（`zmx_materials.py:46`），而任务锚记录 CODE V
目录约为 `Nd≈1.755`。本铲没有运行 CODE V GLD 实测，故后者仍标**待真机验证**。

处理原则：

1. 最终 CODE V 设计与三快照以当前安装版本、明确 catalog 的 CODE V 目录实测值为运行时
   真值；输出 `catalog_id/version` 和实测 Nd/Vd。
2. Python 表只做离线候选检索。与 CODE V 超出数值容差时添加
   `catalog-value-conflict`，禁止无声覆盖、禁止宣称两引擎一致。
3. 冲突材料在同步表值前不得取得 `real-catalog-snapped`；可保留 fictitious，或在 CODE V
   真值反哺并有来源版本后重新 snap。
4. 不自动“修正”仓库材料表；另开有证据的资料更新工单，避免影响 Optiland 既有基线。

## 6. provenance 与 scorecard 接缝

玻璃 provenance 是每面字段，再由候选派生汇总，调用方不可手填升级：

- `fictitious`：AUT model glass、无可接受目录邻居、目录冲突未决，或回验不可用。
- `real-catalog-snapped`：原为 fictitious，成功落真实牌号，且 frozen/reopt 三快照完整；这只
  说明来源真实，**不等于量产合格**。
- `real-catalog-native`：输入本来就是可解析且目录身份/数值已核验的真实材料，未经过 snap。

候选含多个面时取最保守档：任一面 fictitious → 整颗 fictitious；否则任一面 snapped →
整颗 snapped；全为 native 才是 native。scorecard 增加只读 `glass_provenance`、snap ledger、
三快照偏差和 verification status，不增加 pass/fail。该原则对齐 C1 的“纯量化、无
pass/fail”与派生 honesty invariant（C1 spec `:142-205`）；[EXPERT] 仍做最终判断。

## 7. 真机验证矩阵（orchestrator 排窗）

至少选择 3 颗已交付、`extra_dof=both` 且含 fictitious 玻璃的候选；必须包含
`US20170003482A1 × 3.797` 旗舰候选，其余两颗覆盖不同 EFL/玻璃域位置。每颗执行：

| 试验 | 变量 | 必收证据 |
|---|---|---|
| A 基线 | 原 fictitious | 每面 Nd/Vd、EFL/RMS/WFE、波长/视场/渐晕、AUT provenance |
| B 冻结 | 最近邻真实牌号，GLC 关 | CODE V catalog+glass、目录实测 Nd/Vd、每面距离、三指标偏差 |
| C 恢复 | B + 短 AUT 半径/非球面 | AUT cycle/termination/error trace、三指标偏差、玻璃仍冻结证明 |
| D 冲突 | 至少 H-LAK53A 或另一跨表冲突 | Python 值、CODE V GLD 值、冲突标签与 fail-closed 行为 |

矩阵只产数据，不预设 EFL/RMS/WFE 合格阈值。三颗完成后由资深根据偏差分布 ratify：snap
距离阈值、disp_factor、短 AUT 预算，以及是否进入铲 2 主链。

## 8. 开放问题（10 项，供对抗审）

1. `D<=0.01` 是否能同时覆盖低折高阿贝与高折低阿贝塑料，还是应按域分层？
2. Python 的归一化 `disp_factor` 是否需完全复刻 `glassfit.seq:107-112` 的 FGW 换算？
3. 目录应只含在产牌号，还是允许 discontinued 但强制 availability 标签？
4. 如何稳定表达 `catalog_id + glass_name`，避免同名跨目录歧义？
5. 同一实体元件前后两面如何从 readout 建立 identity，并保证只选一个材料？
6. CODE V 批处理下冻结真实玻璃、限定目录的准确命令序列是什么？**待真机验证。**
7. 短 AUT 放哪些曲率/非球面 DOF、cycle/IMP 预算多大才不把 snap 劣化藏进过拟合？
8. RMS spot/WFE 的三快照应取哪些字段/波长/视场聚合，才能严格可比？
9. partial dispersion、供应状态、注塑可得性何时进入二阶段筛选，而不污染本阶段距离？
10. H-LAK53A 差异来自错表、同名异目录还是波长/牌号版本？需 GLD/GPR 实测归因。

## 9. 本铲验收

- `glass_snap.py` 是纯 Python、确定性、无 LLM/CODE V/Optiland 依赖。
- 单测覆盖度量、权重、容差等号、超界 fail-closed、真实塑料牌号往返。
- 不修改 `codev_optimize`、golden、既有候选产物或 `decisions.log`。
