# Phase 12 铲 3 — NEWMAX parser implementation notes

## 实现边界

- 新增独立 `_parse_newmax_table_attempts()`，放在 primary 失败后的 fallback 首位；不放宽
  primary 的 metadata/surface 规则。
- 仅接受表头同时给出 `TABLE N Embodiment M`、精确 `f`、`Fno`、全角 `FOV` 的静态处方；
  `hfov_deg = FOV / 2`。
- surface 表与紧邻的下一编号 coefficient 表成对；逐 embodiment 捕获错误并保留 fail-loud
  账本语义。
- 支持 Object、Stop、First/ordinal lens、Lens N、IR-filter/Optical filter、Image plane；
  Infinity 与负 stop gap 继续使用既有确定性距离解析。
- `plastic/glass nd vd` 必须同时印刷且落在物理窗口；缺任一值即 fail-closed。

## 方程证据与系数映射

来源均为 Google Patents 英文公开全文，测试 fixture 为页面表格逐字拷贝并仅压平空白。

### US-10101561-B2 — Equation 1 / alphabetic rows

原文项序列：

> A h^4 + B h^6 + C h^8 + D h^10 + E h^12 + G h^14 + …

同文 paragraph 68 将表内 `A, B, C, D, E, F, ...` 称为 high-order aspheric
coefficients，而公开 coefficient 表的第六行印作 `F`。实现按表格的连续高阶列位置映射：
`A/B/C/D/E/F -> h^4/h^6/h^8/h^10/h^12/h^14 -> Code V A/B/C/D/E/F`。测试以
TABLE 5/6 的 surface 3 断言 `A=5.4995E-01`、`F=-1.7283E+00`。

### US-12596237-B2 — Equation 2 / explicit even-order rows

原文：

> z(h) = ch^2/{1+[1-(k+1)c^2h^2]^0.5} + Σ(A_i)·(h^i)

因此 `A2` 明确乘 `h^2`，不得错移为 Code V A (`h^4`)。实现要求 A2 全为零，非零立即
fail-loud；`A4/A6/.../A30` 按下标幂次映射到 Code V。阶次回归以 TABLE 1/2 surface 1
断言 `A4=2.5005E-03 -> Code V A`、`A6=-1.2047E-04 -> Code V B` 且不存在 `A2` 槽。

## 正例状态

- 老子型：`US-10101561-B2` TABLE 5/6，Embodiment 3，完整端到端解析；断言
  `f=3.35`、`Fno=2.2`、`hfov=42°`、15 个非 object 面、首片 `nd/vd=1.544/56.000`
  与 alphabetic coefficients。
- 现代子型：`US-12596237-B2` TABLE 1/2，Embodiment 1，完整端到端解析；断言
  `f=2.47`、`Fno=1.21`、`hfov=74.935°`、14 个非 object 面、首片
  `nd/vd=1.643/22.5` 与 explicit-order coefficients。

## Fail-loud 账本

- 表头像 NEWMAX 但缺精确 `f/Fno/FOV`：不进入该 family；由既有总解析失败显式报告。
- surface 表缺 Object、未连续、缺 Image plane、过短：该 embodiment 失败。
- surface/material token 形似数据但距离非数值，或 plastic/glass 缺印刷 nd/vd：该
  embodiment 失败，不降为空气。
- coefficient 表不相邻、缺行、值非数值、引用未知 surface：该 embodiment 失败。
- `A2 != 0`：`nonzero NEWMAX A2 term`；不做阶次错移。
- 超出 Code V 支持阶次的非零项：`unsupported nonzero NEWMAX asphere term`；零值可忽略。

## 明确排除

- `US-12474548-B2`、`US-12560789-B2`：移动组、多状态，继续记为 `partially`；等待
  “每状态一处方 vs 只取 nominal”决策。
- `US-11892707-B2`、`US-20220229269-A1`：`dead`，非镜头数值处方。
- 本铲不跑入库，不修改 golden，不修改 `.planning/decisions.log`。
