# Phase 12 铲 1：Genius / SEKONIX / NEWMAX 解析器家族普查

## 结论

优先级：**SEKONIX > NEWMAX > Genius**。

| 家族 | JSONL 命中 / 未开采 | 全文可得 | 判定 | 表内 embodiment 毛数 | 按 JSONL 完全相同摘要去重后 | 实现量级 |
|---|---:|---:|---|---:|---:|---|
| SEKONIX | 18 / 18 | 18 | `parseable-with-new-family`（17 颗）；1 颗 `dead` | 73 | 58 | 中 |
| NEWMAX | 16 / 16 | 15 | `parseable-with-new-family` 为主；2 颗 `partially`；2 颗 `dead`；1 颗全文缺失 | 76（不含缺失颗） | 73 | 中高 |
| Genius | 30 / 30 | 18 | 18 颗文本处方 `dead`；12 颗 `partially`（全文缺失） | 0（仅指已取得的 18 颗） | 0 | 不应先做 |

三家族相对旧账本的实际命中为 **30 / 18 / 16**；NEWMAX 比
`.planning/loop/seed-intake-500-report.md` 的 15 多 1 颗。436 条 index 中没有任何一个
三家族专利根号，故全部仍属未开采。当前五家族解析入口对所有可取得全文均返回
`PatentParseError: embodiment f/Fno/HFOV line not found`。

### 证据边界（重要）

确定性脚本检查 12 个 JSONL：714 行、714 个唯一 ID；每条只含 `id/title/abstract/
claim_excerpt/inventors/assignee/ipc_classes/filing_date/source/source_url`，360 条另有
`family_hint`。**没有 description 或全文处方表字段**。因此任务所要求的“直接引用 JSONL
中的处方表原文”在给定输入中客观不存在。本报告不把外部全文伪称为 JSONL 内容：

- 各家族先列 JSONL 原文样本，证明本地证据实际可见范围；
- 表结构和 embodiment 数来自按 JSONL ID 取得的公开全文；
- USPTO 匿名 HTML API 本次 60 秒无响应，JSONL 中带连字符的 PDF URL 返回 404；普查以
  Google Patents 展示的同一 US publication 全文作结构证据。未能取得的记录一律为
  `partially`、数量为 `null`，不外推。

计数规则：每个实际数值 surface prescription 表算一个 embodiment；asphere 表、条件式
汇总表不重复计数。`estimated_embodiments` 是解析器可尝试产量，不等于通过追迹和六门的
最终入库量。完全相同摘要的 A1/B2 公开对另列去重数，不把它们假装成两个独立设计。

## 与现有五家族的格式对照

| 格式 | 元数据 | surface 行 | asphere | 新家族关系 |
|---|---|---|---|---|
| primary bracket-style | embodiment 行内 f/Fno/HFOV | Lens N / Stop / image | `Surface #` + A/B... | NEWMAX 最接近，但表头与 A2/A4 阶次不同 |
| Fujifilm | Example basic/spec 配对 | Sn/R/D/Nd | Sn 分块 | SEKONIX 同为表对，但表头、surface label、Qcon 不同 |
| AAC Raytech | detached summary | 紧凑 R/d | detached | SEKONIX 可复用“表块配对 + detached metadata”编排 |
| Sunny OBJ/STO | 多种 detached/narrative | OBJ/STO/Sn | split header A4... | SEKONIX 的 STO/Sn 词汇相近；数值列和 Qcon 系数不同 |
| Ability Opto | f/HEP + HAF | ordinal lens rows | `Surface 1 2...` | NEWMAX 的 Lens N/Stop/IR-filter 最接近此扩展后的 primary |

## SEKONIX

### 未开采专利号与表计数

| 专利号 | verdict | embodiments |
|---|---|---:|
| US-20220214515-A1 | `dead`（self-aligning camera lens assembly；无数值处方表） | 0 |
| US-12619054-B2 | `parseable-with-new-family` | 3 |
| US-12498545-B2 | `parseable-with-new-family` | 5 |
| US-12339423-B2 | `parseable-with-new-family` | 5 |
| US-12306384-B2 | `parseable-with-new-family` | 5 |
| US-12235412-B2 | `parseable-with-new-family` | 5 |
| US-12174344-B2 | `parseable-with-new-family` | 5 |
| US-20240184081-A1 | `parseable-with-new-family` | 3 |
| US-20240053586-A1 | `parseable-with-new-family` | 3 |
| US-20230048740-A1 | `parseable-with-new-family` | 5 |
| US-20220326489-A1 | `parseable-with-new-family` | 5 |
| US-11454785-B2 | `parseable-with-new-family` | 2 |
| US-11454786-B2 | `parseable-with-new-family` | 5 |
| US-11409081-B2 | `parseable-with-new-family` | 5 |
| US-20220128796-A1 | `parseable-with-new-family` | 5 |
| US-20220128795-A1 | `parseable-with-new-family` | 5 |
| US-11099361-B2 | `parseable-with-new-family` | 5 |
| US-20210124150-A1 | `parseable-with-new-family` | 2 |

完全相同摘要对：`12619054/20240053586`（3）、`12498545/20230048740`（5）、
`12174344/20220128796`（5）、`11454785/20210124150`（2）。毛数 73，扣这四个
重复 publication 后 58。

### JSONL 原文样本（本地没有处方表）

`US-12174344-B2` 的 `abstract` 原文：

> Disclosed is a small lens system including a first lens, a second lens, and a third lens sequentially arranged from an object along an optical axis, wherein the thickness (ct 1 ) of the first lens, the thickness (ct 3 ) of the second lens, and the thickness (ct 5 ) of the third lens satisfy ct 1 /ct 3 >1.5 and ct 1 /(ct 3 +ct 5 )>0.8, the refractive power (P 2 ) of the second lens satisfies −0.01<P 2 <0.01, the lens thickness (et) at a predetermined height and the center thickness (ct) of the second lens thereof satisfy |et−ct|<5 μm up to 30% of the height of the rear effective diameter thereof and satisfy et−ct<−20 μm at 70% of the height of the rear effective diameter thereof, and the f-number of the lens system is less than 1.7.

这段只有条件式，没有逐面 radius/thickness/material/asphere 数值，不能生成处方。

### 公开全文表结构原样节选（补充证据，非 JSONL）

`US-11099361-B2`：

> TABLE 1 RDY Nd Vd Surface (Radius of THI (Refractive (Abbe (Surface Number) Curvature) (Thickness) Index) Number) FOCAL OBJECT INFINITY INFINITY 1 1.823 1.13 1.544 56.0 2 -9.001 0.11 3 -66.481 0.22 1.671 19.5 STO: 4.136 1.04

同文的系数表开头：

> TABLE 2 K A3 A4 A5 A6 s1 0.12627 1.552030E-04 7.296990E-05 1.297390E-03 1.451520E-03

另一个稳定子型（`US-12619054-B2`）是 `Surface Number / Type / Radius / Thickness /
Glass Code / Y Semi-Aperture`，并使用 `Qcon Asphere`。证据表明至少有三种行头：RDY/THI、
Sphere/Asphere、Qcon Asphere；但全都保持奇数 surface 表 + 偶数 coefficient 表配对。

### 实现方案

在 `scripts/patent_to_zmx.py` 新增 `_parse_sekonix_table_attempts()`，接在 Sunny fallback
之后；不要扩张 primary 的宽松度。复用 AAC 的 `_PatentTableBlock`/成对表编排和 Sunny 的
OBJ/STO/Sn surface-label 思路：

1. 识别奇数 surface 表（RDY/THI、Y Radius/Thickness、Qcon 三表头），按表号与紧邻偶数
   coefficient 表绑定。
2. 新增 `_parse_sekonix_surface_table()`，接受 OBJECT/FOCAL OBJECT、数字/Sn、STOP/STO，
   material 既可能是 nd/vd，也可能是 `Glass Code` 形式；后者需确定性拆出 nd/vd，无法拆出
   就 fail closed。
3. 新增 `_parse_sekonix_asphere_table()`：K + A3/A4... 或 Qcon 的 4th/6th... 项，必须显式
   映射到现有 Code V 阶次并沿用高阶非零拒绝门。
4. 元数据需另做 census fixture：全文 surface 表本身未统一携带 f/Fno/FOV。优先从每一
   embodiment 的邻近 prose/summary 提取；只有范围式（如 `FOV<22°`）而无实例值时该
   embodiment 必须 `partially`，不能填中点。

复杂度：中（约 3 个解析函数 + 3 类 fixture）。收益上限 58 个去重处方，格式规律、实现
边界最清楚，故第一优先。

## NEWMAX

### 未开采专利号与表计数

| 专利号 | verdict | embodiments |
|---|---|---:|
| US-12474548-B2 | `partially`（多焦态/多组移动表） | 7 |
| US-10101561-B2 | `parseable-with-new-family` | 3 |
| US-20180113281-A1 | `parseable-with-new-family`（上项 A1/B2 重复） | 3 |
| US-20260147219-A1 | `partially`（全文不可得） | ? |
| US-12596237-B2 | `parseable-with-new-family` | 7 |
| US-12578548-B2 | `parseable-with-new-family` | 5 |
| US-20260063869-A1 | `parseable-with-new-family` | 6 |
| US-12560789-B2 | `partially`（near/far 移动组，同一 embodiment 多状态） | 8 |
| US-12554104-B2 | `parseable-with-new-family` | 7 |
| US-12535652-B2 | `parseable-with-new-family` | 6 |
| US-12510732-B2 | `parseable-with-new-family` | 6 |
| US-12510730-B2 | `parseable-with-new-family` | 7 |
| US-12498546-B2 | `parseable-with-new-family` | 5 |
| US-12487435-B2 | `parseable-with-new-family` | 6 |
| US-11892707-B2 | `dead`（optical verification system，非数值镜头处方） | 0 |
| US-20220229269-A1 | `dead`（上项 A1/B2 重复） | 0 |

已见毛数 76；`10101561/20180113281` 完全相同摘要，扣除重复后 73；缺失全文的
`US-20260147219-A1` 不计入，未作外推。

### JSONL 原文样本（本地没有处方表）

`US-10101561-B2` 的 `abstract` 原文：

> A five-piece optical imaging lens, in order from an object side to an image side, includes: an aperture stop; a first lens element with a positive refractive power having an object-side surface being convex near an optical axis and the image-side surface being concave near the optical axis; a second lens element with a negative refractive power having an object-side surface being convex near the optical axis and an image-side surface being concave near the optical axis; a third lens element with a negative refractive power having an image-side surface being concave near the optical axis; a fourth lens element with a positive refractive power having an object-side surface being concave near the optical axis and an image-side surface being convex near the optical axis; a fifth lens element with a negative refractive power having an image-side surface being concave near the optical axis.

它能证明镜片拓扑，不能提供逐面数值。

### 公开全文处方原样节选（补充证据，非 JSONL）

同一专利的第三 embodiment：

> TABLE 5 Embodiment 3 f(focal length) = 3.35 mm, Fno = 2.2, FOV = 84 deg. Surface Curvature Radius Thickness Material index Abbe # Focal length 0 object Infinity Infinity 1 Infinity 0.160 2 stop Infinity -0.160 3 lens 1 1.172 (ASP) 0.479 plastic 1.544 56.000 2.420

其系数表：

> TABLE 6 Aspheric Coefficients surface 3 4 5 6 7 K: -7.3032E+00 1.0830E+02 -7.8511E+01 1.3248E+01 1.3955E+02 A: 5.4995E-01 -2.3465E-01 -1.0387E-01 1.4748E-02 -3.1986E-01

现代子型（`US-12596237-B2`）把元数据直接放在 surface 表头：

> TABLE 1 Embodiment 1 f = 2.47 mm, Fno = 1.21, FOV = 149.87° Refractive Abbe Radius of Thickness/ index number Focal Surface curvature gap Material (nd) (vd) length 0 Object Infinity Infinity 1 First lens -96.977 (ASP) 1.200 plastic 1.643 22.5 -4.34

### 实现方案

新增 `_parse_newmax_table_attempts()`，放在 primary 失败后、Fujifilm 前或统一 fallback 链
首位；内部复用 primary/Ability 的 surface 与 coefficient 语义，但保持独立 header gate：

1. 识别 `TABLE N Embodiment M f...Fno...FOV...`；兼容 `f(focal length)`、`FOV
   (field of view 2ω)`、`Central thickness/gap` 与 `Radius of curvature` 的换行重排。
2. surface label 兼容 Object、Stop、First lens/Lens 1、IR-filter/Optical filter、Image plane；
   `Infinity` 与负 stop gap 沿用 primary 的确定性距离规则。
3. coefficient 支持两套命名：K+A/B/C... 与 K+A2/A4...。A2 必须验证为 0；A4 起按实际
   偶次幂映射，不能把 A2 错移成 Code V 的 A4。
4. `US-12474548-B2` 和 `US-12560789-B2` 单列第二阶段：同 embodiment 有 near/far 状态和
   移动组间距。先定义“每状态一 prescription”还是只取 published nominal state；在决策前
   保持 `partially`。

复杂度：中高（标准静态子型约 3 个函数 + fixtures；移动组再加状态绑定）。静态子型去重
产量约 58（73 减去两颗 partial 的 15）；与 SEKONIX 相近但表头分支更多，故第二优先。

## Genius

### 未开采专利号

`dead`（可取得全文但无机器可读数值处方表，18）：

US-20250020895-A1、US-20260110881-A1、US-20260093094-A1、US-12607828-B2、
US-20260036791-A1、US-20260009980-A1、US-12461345-B2、US-12429676-B2、
US-12298484-B2、US-20240411113-A1、US-20240369810-A1、US-20130301136-A1、
US-20170097490-A1、US-9341816-B2、US-20150138653-A1、US-20150077867-A1、
US-8976467-B2、US-8929000-B2。

`partially`（全文不可得，12；不能判死、不能估量）：

US-20260186247-A1、US-20260186249-A1、US-20260186250-A1、US-20260177783-A1、
US-20260169267-A1、US-20260169260-A1、US-20260169264-A1、US-20260169265-A1、
US-12656577-B2、US-12656578-B2、US-20260147189-A1、US-12625349-B2。

### JSONL 原文样本（本地没有处方表）

`US-12429676-B2` 的 `abstract` 原文：

> An optical lens assembly is provided, including a first lens element, a second lens element, a third lens element, a fourth lens element, a fifth lens element, and a sixth lens element sequentially along an optical axis from a first side to a second side. The optical lens assembly satisfies a conditional expression of EPL/BFL≥3.800.

这是投影镜头条件式，不是数值处方。可取得的 18 篇全文中未检出 surface radius +
thickness + material 的成套文本表；老一组 mobile-device 专利有大量 embodiment 叙述，
但正文展示层仍无数值表，文本解析器没有输入可吃。

### 实现方案

本轮**不新增 Genius parser**。先做一个独立的 source-recovery spike：

1. 对 12 颗不可得 publication 用 USPTO Patent Center/授权公报再取证；
2. 对 18 颗已取得但无文本表的记录确认表是否仅存在于 PDF 图像；若是，问题是 OCR/表格
   恢复，不是 `patent_to_zmx.py` regex family；
3. 只有恢复出至少两个一致数值表样本后，才决定复用 primary 还是新增 family。

现阶段可证实产量为 0，代码成本不可估，故第三优先。把 12 颗未知按每颗若干 embodiment
外推会违反本铲诚实红线。

## 下一铲建议与验收口径

1. 先实现 SEKONIX 静态处方，fixture 覆盖 RDY/THI、Sphere/Asphere、Qcon 三子型；按完全
   重复摘要对做 family dedup，避免 A1/B2 双入库。
2. 再实现 NEWMAX 静态表，先排除两颗移动组 partial 和两颗 verification dead；特别加
   A2/A4 阶次错移回归测试。
3. 每个 parser 继续走 `_parse_prescription_attempts` 的 per-embodiment fail-loud 账本；缺少
   实例 f/Fno/FOV、玻璃 nd/vd 或出现未支持高阶项时不得填值。
4. 下一铲预期“可尝试转换”的去重上限：SEKONIX 58 + NEWMAX 静态约 58 = **约 116**；这
   不是承诺入库数，仍需经过追迹、FOV plausibility、近重复等既有门。

机器可读逐专利账本见 `p12-parser-census.json`。
