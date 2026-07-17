# Project State

## Project Reference

See `.planning/PROJECT.md` and `AGENTS.md`.

**Core value:** 专家级量产设计论证；AI 多产候选与量化证据，资深保留全部
`[EXPERT]` 良品/合格/量产可用判定权。

**Naming:** `production-ready` / “生产可用”是 loop2 工程代号，不是资深 verdict。

**Current focus:** production-ready loop2 的技术探路与 PR #82 docs/main CI release 已闭合；
`d35b3d07` 的 main CI run `29233888562` success。当前本机 inventory 未发现
`atelier-loop2` heartbeat，但没有保留可独立重算的 deletion operation receipt，因此只将其
记为“当前不存在”的观察，不声称删除动作来源已证明。这些工程标签不同于北极星治理 gate
A–F。北极星现为 `ACTIVE`，66-object canonical schema 与 claim/contract/authority mirrors 均为
`v0.1-draft` + `UNRATIFIED`，
北极星 A–F 全 false，专家与制造指标 unavailable。技术闭环不等于北极星 go/no-go 已通过。

**Patent saturation focus (2026-07-17, branch work):** `origin/main@42803f8` 起的独立
`codex/patent-saturation-ledger` worktree 已建立 GSD quick 控制面。运行时重算为 714 个 USPTO
元数据根、442 个正式设计（425 个专利设计、116 个美国专利根）、95 个本地池根有正式工件、
619 个未覆盖；发现并集为 735 根（另 21 个正式根不在本地元数据池）。canonical snapshot
SHA-256=`c86527b71e0500074bf14e1668bc3ab6701e5d54d3d22ef5826686101d6b5ec1`；
foundation snapshot 仍为 `saturation_complete=false`。冻结的 619 根均已保留官方 PPUBS HTML
并有严格回放结果，但 parser、trace、staging intake、family/source closure 与正式设计 provenance
仍未全闭合。这是未合 main 的进行中证据，不是饱和完成声明；500 仅为历史进度标记。

当前严格 replay result set 为
`df9054f7d29128d7d9db857916c547ca7ce91b7a7a341876e1f3e3e31ca60780`：619/619、
missing=0、corrupt=0。Family ID `82951912` 的 frozen root `US-12591109` 已完成
exact-source 对账：官方 B2 绑定一个 related-application 段、Background 1-3、Summary 4-6、
drawing description 1-35、Detailed Description 36-131、claims 1-18、34 个文字图号、
3 个 tagged table、0 个 MathML 与 9 个 source items。Embodiments 1-7 是反射件/支架/
冲压金属支撑与弯折结构，embodiment 8 是四摄手机 wrapper，embodiment 9 是 AR 头戴显示
wrapper；三张表只有弯折角和机械最小间距。全部九项成为 confirmed-no-prescription
terminals。四次 `radius of curvature` 都是冲压圆角，四次 `thickness` 都是 0.15 mm 金属板；
没有 ordered optical radius/spacing/material/conic/asphere sequence，也没有 focal length、
F-number 或 angular field。官方 B2/A1 均为 44 页 image-only、32 张 drawing sheets，零 decoded
raster 相同。文字与 specification 写 `FIG. 10`，对应官方 panel 写 `FIG. 1C`；差异留痕但不抄图
或据图推数。Attempts 2/3 仅移除 `result_attempt` 后 canonical 语义一致；没有 worker/request/
receipt/fingerprint/candidate/ZMX，formal intake 为零，CODE V 未使用。当前 roots 为 309 parser
review、148 mixed、137 terminal、25 converted；items 为 1403 parser review、1164 terminal、
561 staging、28 conversion retry。Generic 从 120 降至 119 roots/items，仍高于 AAC Raytech
55 roots/174 items 与 Sunny 49 roots/177 items；下一 exact family 为 `80893318`
（`US-12461279-B2`）。

**Patent saturation latest authoritative update (2026-07-17):** This supersedes the earlier
Family 82951912 snapshot above. Strict replay is 619/619 with missing=0, corrupt=0 and result set
`8537d6a5f8f863c11725d848467d218c472535e4117dddeec7228ee44647da30`. Family `80893318`
(`US-12461279-B2`) reconciles five exact source items: three plastic light-folding/reflective-film
architectures and two smartphone camera-placement wrappers. TABLES 1/3 are film-layer indices and
nanometer thicknesses; TABLE 2 is 671 wavelength/reflectivity rows. No ordered lens prescription or
required focal-length/F-number/angular-field metadata exists, so all five items are source-proven
confirmed-no-prescription terminals. Official B2/A1 each have 30 image-only pages and 17 drawing
sheets; their complete contact sheets and eight critical pages were reviewed with no transcription,
numeric derivation or cross-publication borrowing. Current roots are 308 parser review, 148 mixed,
138 terminal and 25 converted; items are 1402 parser review, 1169 terminal, 561 staging and 28
conversion retry. Generic metadata is 118 roots/items and remains the largest executable bucket;
deterministic ordering selects Family `63246213` (`US-20230333291-A1`) next. Parent/global patent
saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 63246213):** This
supersedes the Family 80893318 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`0278c809e43a9b92dce1b8365533c195e764073c169e5d618f791468773ddf40`. Family `63246213`
(`US-20230333291-A1`) reconciles 15 exact source items: eight light-blocking-sheet mechanical
embodiments, four imaging-assembly placement embodiments that expressly omit lens details, and
three electronic-device camera-placement wrappers. The 12 tagged tables contain sheet or
placement dimensions, not optical surface sequences; no ordered optical prescription exists.
All 15 items are source-proven confirmed-no-prescription terminals. Official A1/B2 each have 68
image-only pages and 45 drawing sheets; complete contact sheets and 11 critical pages were
reviewed with no transcription, numeric derivation or cross-publication borrowing. Current roots
are 307 parser review, 148 mixed, 139 terminal and 25 converted; items are 1401 parser review,
1184 terminal, 561 staging and 28 conversion retry. Generic metadata is 117 roots/items and
remains the largest executable bucket; deterministic ordering selects Family `100037253`
(`US-20260161906-A1`) next. Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 100037253):** This
supersedes the Family 63246213 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`d06a4e642a7a2e9f42f90b530e27b3f70f295385863cd67386e38616b2c71b7c`. Family `100037253`
(`US-20260161906-A1`) reconciles three exact source items: an indicia-reader apparatus, its
operating method and a computer-readable medium. The source functionally names imaging and
illumination assemblies, an image sensor, NPU/controller and symbolic field/working-distance
blocks, but publishes no ordered optical radius, spacing, material, conic, asphere or direct
numeric angular-field prescription. All three items are source-proven confirmed-no-prescription
terminals. The official A1 has 12 image-only pages and five drawing sheets; all decoded rasters,
the contact sheet and nine critical pages were reviewed with no transcription, numeric derivation
or cross-publication borrowing. Current roots are 306 parser review, 148 mixed, 140 terminal and
25 converted; items are 1400 parser review, 1187 terminal, 561 staging and 28 conversion retry.
Generic metadata is 116 roots/items and remains the largest executable bucket; deterministic
ordering selects Family `38997638` (`US-7551370-B2`) next. Parent/global patent saturation
remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 38997638):** This
supersedes the Family 100037253 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`e295fdfe60dfa528492c3d3e761ec603b51fad337a9042ed0a0080c98c5a5e58`. Family `38997638`
(`US-7551370-B2`) reconciles four exact source items: the indicia-reader apparatus, means
apparatus, operating method and negative-spherical-aberration imaging lens assembly. Generic
lens placement, the aberration component, aperture stop and reader working-range values publish
no ordered optical radius, spacing, material, conic, asphere coefficient or required numeric
system prescription. All four items are source-proven confirmed-no-prescription terminals.
Official B2 and same-application A1 each have eight image-only pages and three drawing sheets;
all decoded rasters, both contact sheets and original-resolution pages 2-8 were reviewed. The A1
`FIG. 6` versus corrected B2/textual `FIG. 4` discrepancy has no numeric effect, and there is no
transcription, numeric derivation or cross-publication borrowing. Current roots are 305 parser
review, 148 mixed, 141 terminal and 25 converted; items are 1399 parser review, 1191 terminal,
561 staging and 28 conversion retry. Generic metadata is 115 roots/items and remains the largest
executable bucket; deterministic ordering selects Family `65528235` (`US-20190294840-A1`)
next. Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 65528235):** This
supersedes the Family 38997638 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`ca7e22772b69b793e94d6e4bfb7eacafd2687891d6ce178e9ac608d6f4f23c7b`. Family `65528235`
(`US-20190294840-A1`) reconciles eleven exact Summary items: reader and manufacturing
architecture, free-floating chassis/lens installation, three aligned chassis/lens assemblies,
a dual-working-range imaging engine, and four aiming-pattern spacing/intensity/safety
constraints. A1 claims 1-21 map completely to four of those items. Working distances,
mechanical clearances, aiming angles, intensity and laser-safety values are not an ordered
optical radius, spacing, material, conic, asphere-coefficient or required numeric system
prescription. All eleven items are source-proven confirmed-no-prescription terminals. Official
A1 has 29 image-only pages/18 drawing sheets; same-application B2 has 30 image-only pages/18
drawing sheets plus a references page. All decoded rasters, both contact sheets and 18
original-resolution critical pages were reviewed without transcription, numeric derivation or
cross-publication borrowing. Current roots are 304 parser review, 148 mixed, 142 terminal and
25 converted; items are 1398 parser review, 1202 terminal, 561 staging and 28 conversion retry.
Generic metadata is 114 roots/items and remains the largest executable bucket; deterministic
ordering selects Family `76444624` (`US-11783729-B2`) next. Parent/global patent saturation
remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 76444624):** This
supersedes the Family 65528235 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`70f401d6eed9d416e81a098e179b9a764c9244589f9d089d337b24a88c4dea80`. Family `76444624`
(`US-11783729-B2`) reconciles four exact source items: a colorblind-accessible image-rendering
system, its rendering method, a color-vision-deficiency transformation-model method and a
machine-readable-medium wrapper. The source contains 11 RGB/CVD pseudocode listings and
generic camera/viewfinder context, but no ordered optical radius, spacing, material, conic,
asphere coefficient, focal length or F-number prescription. All four items are source-proven
confirmed-no-prescription terminals. Official B2/A1 have 31/32 image-only pages and 15 drawing
sheets each; all decoded rasters, both contact sheets and 20 original-resolution critical pages
were reviewed without transcription, numeric derivation or cross-publication borrowing. Current
roots are 303 parser review, 148 mixed, 143 terminal and 25 converted; items are 1397 parser
review, 1206 terminal, 561 staging and 28 conversion retry. Generic metadata is 113 roots/items
and remains the largest executable bucket; deterministic ordering selects Family `89620713`
(`US-20240272406-A1`) next. Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 89620713):** This
supersedes the Family 76444624 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`40fb3df65d25a15fb24a7a474d8cc3964111ee5c1209ed5873b417b94d5dcecc`. Family `89620713`
(`US-20240272406-A1`) reconciles ten exact examples. Examples 1-7 publish folded optical-module,
light-blocking-membrane and nanostructure architecture; their BS/RS values are coating
microstructure sizes rather than optical radii or spacings. Examples 8-10 are smartphone and
vehicle multi-camera placement/digital-zoom wrappers. The source publishes no ordered optical
radius, spacing, material, conic, asphere coefficient, stop or required F-number prescription,
so all ten items are source-proven confirmed-no-prescription terminals. Official current and
parent A1 publications each have 40 image-only pages and 27 drawing sheets; all decoded rasters,
both contact sheets and 17 original-resolution critical pages were reviewed without
transcription, numeric derivation or cross-publication borrowing. Current roots are 302 parser
review, 148 mixed, 144 terminal and 25 converted; items are 1396 parser review, 1216 terminal,
561 staging and 28 conversion retry. Generic metadata is 112 roots/items and remains the largest
executable bucket; deterministic ordering selects Family `95155833` (`US-12671891-B2`) next.
Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 95155833):** This
supersedes the Family 89620713 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`58b441fcdfed487d3bdf21d16787515390f3c85feeb3a4958c03de7deec7f651`. Family `95155833`
(`US-12671891-B2`) reconciles five exact hardware-button user-interface items spanning media
capture routing, touch-control reconfiguration, context-sensitive behavior, configurable
settings and press-type handling. Camera, focal-length, f-stop, depth-of-field, field-of-view,
lens and sensor language describes UI state, simulated effects or generic device architecture;
the source publishes no ordered optical radius, spacing, material, conic, asphere, stop or
required system prescription. All five items are source-proven confirmed-no-prescription
terminals. Official B2/A1 publications contain 150/130 image-only pages and 56 drawing sheets
each; all 280 decoded rasters, both contact sheets and 18 retained critical pages were reviewed
without transcription, numeric derivation or cross-publication borrowing. Current roots are 301
parser review, 148 mixed, 145 terminal and 25 converted; items are 1395 parser review, 1221
terminal, 561 staging and 28 conversion retry. Generic metadata is 111 roots/items and remains
the largest executable bucket; deterministic ordering selects Family `97107726`
(`US-12425721-B1`) next. Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 97107726):** This
supersedes the Family 95155833 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`290aa22efc7e5bc983b3fe3b5b880b04cf9b36d5ce679cfdd1b46d7a8d102acd`. Family `97107726`
(`US-12425721-B1`) reconciles eight exact source items: a setting-analysis calibration process,
motorized camera calibration system, stepped-barcode calibration target, iterative setting
search, lens/camera setting selection, machine-learning calibration process, calibration
computing architecture and generic computing-environment wrapper. The sampled `f/2.8` and
`f/1.8` values are camera-setting vectors, while every radius is a target radius/fraction; no
item publishes an ordered optical radius, spacing, material, conic, asphere, stop or complete
required system prescription. All eight items are source-proven confirmed-no-prescription
terminals. The retained USPTO HTML is the classification truth. The recorded USPTO PDF endpoint
returns 404; one official Gazette exemplar was retained and reviewed, while Google declares nine
drawings whose direct image requests return 403, so no full-drawing review is claimed. There is
no drawing transcription, numeric derivation, cross-publication borrowing, worker, request,
receipt, fingerprint, candidate, staging ZMX or formal intake, and CODE V is unused. Current
roots are 300 parser review, 148 mixed, 146 terminal and 25 converted; items are 1394 parser
review, 1229 terminal, 561 staging and 28 conversion retry. Generic metadata is 110 roots/items
and remains the largest executable bucket; deterministic ordering selects Family `97917964`
(`US-20250378431-A1`) next. Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 97917964):** This
supersedes the Family 97107726 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`9043abe67b562809797b4c1f73ab16ba8858763598f03d0881abe07cbeb2c019`. Family `97917964`
(`US-20250378431-A1`) reconciles two exact source items: the indicia-reader weigh-platter
power-storage architecture in Summary paragraph 4/claims 1-11 and the overlapping
data-capture-device architecture in Summary paragraph 5/claims 12-22. FIGS.1-6 and Detailed
Description paragraphs 14-40 publish shared load-cell, platter, wireless/wired power transfer,
storage-placement, selective-charging and optional embedded-subsystem architecture. Lens,
camera, image-sensor and FOV wording is generic reader background; the 2 mm value is platter
clearance and 0.5/1/2 oz values are charge-control weight thresholds. The source publishes no
ordered optical radius, spacing, material, conic, asphere, stop, focal length, F-number or numeric
angular-field prescription, so both items are source-proven confirmed-no-prescription terminals.
The retained USPTO HTML is the classification truth. The recorded USPTO PDF endpoint returns
404; no PDF or drawing raster is retained and no full-drawing review is claimed. There is no
drawing transcription, numeric derivation, related-family borrowing, worker, request, receipt,
fingerprint, candidate, staging ZMX or formal intake, and CODE V is unused. Current roots are 299
parser review, 148 mixed, 147 terminal and 25 converted; items are 1393 parser review, 1231
terminal, 561 staging and 28 conversion retry. Generic metadata is 109 roots/items and remains
the largest executable bucket; deterministic ordering selects Family `98774980`
(`US-20260086434-A1`) next. Parent/global patent saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 98774980):** This
supersedes the Family 97917964 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`5b4f099d2358c5979b03c112399cdf9c5d96fa03596e40ceb9ce1566f300a89e`. Family `98774980`
(`US-20260086434-A1`) reconciles all 151 numbered paragraphs, claims 1-30, 64 figure-label
occurrences/63 unique labels, three tagged mechanical tables, eleven MathML objects and ten exact
source items. Seven items are resilience-wiring-sheet, lens-carrier and camera-drive examples;
three are smartphone, folded-telephoto and vehicle-camera wrappers. TABLES 1-3 publish only
mechanical `D/Hn/L/Wc/Wf` dimensions and ratios. The sole focal-length phrase is generic
multi-camera zooming, and the 40-to-90-degree vehicle visual angle is placement coverage. No item
publishes an ordered optical radius, spacing, material, conic, asphere, stop, image-height,
F-number or prescription-specific angular-field design, so all ten are source-proven
confirmed-no-prescription terminals. The original duplicate `FIG. 2O` declaration is preserved.
The retained USPTO HTML is the classification truth; the PDF endpoint returns 404, no raster is
retained and no full-drawing review is claimed. There is no drawing transcription, numeric
derivation, related-family borrowing, worker, request, receipt, fingerprint, candidate, staging
ZMX or formal intake, and CODE V is unused. Current roots are 298 parser review, 148 mixed, 148
terminal and 25 converted; items are 1392 parser review, 1241 terminal, 561 staging and 28
conversion retry. Generic metadata is 108 roots/items and remains the largest executable bucket;
deterministic ordering selects Family `99480653` (`US-20260113525-A1`) next. Parent/global patent
saturation remains active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 99480653):** This
supersedes the Family 98774980 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`e24815b37caf7679a86256c00d1f239b6437758c29484c9dc6f70b7b5bde3e67`. Family `99480653`
(`US-20260113525-A1`) reconciles all 52 numbered paragraphs, claims 1-20, three claim families,
ten figure declarations, one nine-row antenna performance table and four exact source items. The
first two items use a camera unit/circuit-board trace as part of an antenna radiator; the third
names only a generic imaging lens assembly, lens set and photosensitive element on an antenna
board; the fourth is a notebook wrapper. GHz/VSWR values, quarter wavelength, 40 mm board length
and 0.1/0.3 mm coupling spacings are antenna/circuit geometry. The source publishes no ordered
optical radius, spacing, material, conic, asphere, stop, EFL, F-number, image-height or angular-field
prescription, so all four items are source-proven confirmed-no-prescription terminals. The retained
USPTO HTML is classification truth; the PDF endpoint returns 404, no raster is retained and no
full-drawing review is claimed. There is no drawing transcription, numeric derivation,
related-family borrowing, worker, request, receipt, fingerprint, candidate, staging ZMX or formal
intake, and CODE V is unused. Current roots are 297 parser review, 148 mixed, 149 terminal and 25
converted; items are 1391 parser review, 1245 terminal, 561 staging and 28 conversion retry.
Generic metadata is 107 roots/items and remains the largest executable bucket; deterministic
ordering selects Family `48982045` (`US-8820942-B2`) next. Parent/global patent saturation remains
active and incomplete.

**Patent saturation latest authoritative update (2026-07-17, Family 48982045):** This
supersedes the Family 99480653 snapshot immediately above. Strict replay is 619/619 with
missing=0, corrupt=0 and result set
`f2ef7dfeb977ae87f8e1a1090f757b9628545c426d13968467889985930f25e1`. Family `48982045`
(`US-8820942-B2`) reconciles Background/Summary paragraphs 1-17, Description paragraphs 1-30,
claims 1-27, two claim families, seven figure declarations, zero tagged tables, zero MathML and two
exact source items. The first is a four-prism light-dividing topology; the second composes
light-combining/total-reflection prisms, digital micromirrors, four reflecting-lens assemblies,
eight relay lenses, five reflecting mirrors and a generic imaging lens into a multi-view projection
path. The source publishes only the unnumbered word `acute` for prism angle and no ordered optical
radius, spacing, thickness, material, index, Abbe, conic, asphere, stop, EFL, F-number,
image-height or numeric angular-field prescription. Both items are therefore source-proven
confirmed-no-prescription terminals. The retained USPTO HTML is classification truth; the PDF
endpoint returns 404, no raster is retained and no full-drawing review is claimed. There is no
drawing transcription, derivation, prior-publication/family borrowing, worker, request, receipt,
fingerprint, candidate, staging ZMX or formal intake, and CODE V is unused. Current roots are 296
parser review, 148 mixed, 150 terminal and 25 converted; items are 1390 parser review, 1247
terminal, 561 staging and 28 conversion retry. Generic metadata is 106 roots/items and remains the
largest executable bucket; deterministic ordering selects Family `78342471` (`US-12092276-B2`)
next. Parent/global patent saturation remains active and incomplete.

## Current Position

| Scope | Status |
|---|---|
| Phase 13 glass-snap 铲3 | 完成；PR #74，matrix v7 20/20 可执行格。 |
| Phase 14 TOR 铲2 | 完成；PR #68。默认公差表仍待资深 ratify，yield unavailable。 |
| Phase 15 Stage B F/# | 完成；PR #75。F/# 仅由候选自己的 closed ladder gate 条件授予。 |
| Phase 17 close-out | 完成；PR #71。ZMX 持久化与串行 repeat engine 落地。 |
| Phase 18 batch | 完成；PR #72/#77/#80。50/50：29 succeeded、21 degraded、0 failed。 |
| Phase 16 Stage C | 完成技术证据闭环；PR #76/#78/#79/#81。48-run matrix + 单 exact target production/export。 |
| Loop2 G | PR #82 / main CI `29233888562` success；heartbeat 当前 inventory 不存在，但 deletion operation receipt 未保留，G 的该子项不可独立重算。 |
| North-star control plane | ACTIVE / UNRATIFIED；A–F=false。历史固定树 `57c305f/2b3c73d`、`a5ea60e/930767a`、`ff76ae0/4317805`、`d9e0e75/00c7af0`、`bd2e1cf/cf9c6f3`、`aca7241/53c2455`、`ead809c/b140543`、`8acb078/5856f8d`、`0915ccf/7e004a0`、`2c74a54/5784bac`、`02f9d17/7abf1b6` 与 `ab7ce4d/f2ff988` 均被独立只读审查拒绝，不能发布；`8acb078`、`2c74a54` 与 `ab7ce4d` 的同树 RELEASE_GIT_CI PASS 均被其他 scope finding 作废，`0915ccf`、`02f9d17` 的 RELEASE_GIT_CI 自身为 CHANGES_REQUIRED。tracked STATE 不自证承载它的 commit/tree、worktree 状态、fresh review、PR、CI 或 merge；O-07 只能由 merge 后树外签发的 registered RUN_CODE_RELEASE package 证明且不闭任何 A–F，O-09 detached release evidence 才可能闭 F。 |
| Patent saturation | ACTIVE / INCOMPLETE. Frozen replay is 619/619, missing=0, corrupt=0, result set `f2ef7dfe...25e1`. Current roots: 296 parser review, 148 mixed, 150 terminal, 25 converted; items: 561 staging, 1390 parser review, 1247 terminal, 28 conversion retry. Frozen Family 48982045 reconciles a four-prism light-dividing topology and a multi-view projection optical-machine topology. Component counts and the unnumbered acute-angle relationship are architecture only; no ordered optical prescription is published, so both items are source-proven confirmed-no-prescription terminals. The retained USPTO HTML is classification truth; the PDF endpoint returns 404, no raster is retained and no full-drawing review is claimed. No worker/request/receipt/fingerprint/candidate/staging ZMX/formal intake is produced, and CODE V is unused. Generic 107->106 roots/items remains first by nonterminal roots; deterministic ordering selects Family 78342471 next. External-family repair, reflective/odd-power representation, staging intake and source exhaustion remain outside completion, so this is not family/source/global saturation. |

**Release truth:** PR #81 merge
`9249f97834a3bff52bb38e3e6ff456c7ec0aaec3`；PR CI run `29227838587`
success；匹配 merge SHA 的 main CI run `29229500265` success。
Loop2 G docs PR #82 merge `d35b3d07cead830396d24d2b10665199c73985e0`；匹配 main CI
run `29233888562` success；本机 automation inventory 当前无 `atelier-loop2` heartbeat，
但没有 durable deletion operation receipt，故不外推删除动作的可重算 provenance。

**Progress:** loop2 技术探路及发布链已闭合，heartbeat 当前缺席但删除 provenance 有证据缺口。
北极星 A–F 均为 false；资深良品率 go/no-go 未执行，不能写成“量产可用已通过”。

## Evidence Snapshot

- P18：50 targets / 50 jobs / 50 valid CandidateSets；29 succeeded / 21 degraded /
  0 failed；污染的 job-0020/0021 attempt-1 永久排除。仅 exploratory，不是专家率或 yield。
- Stage B authority：8/8 unique accepted，30 outcomes，6 pre-run-bound + 2 retrospective，
  no incomplete，`expert_verdict=null`。manifest SHA256
  `29384d5d9a10356c8b9bd908c48ab6970977fcafe77ac59a100aaf268350d969`。
- Stage C matrix：48/48 receipts，2 delivered / 46 blocked；6/48 run metrics usable，
  3/24 cells complete，21/24 unavailable。不得换算为 yield。
- Production：仅 `US9304295B2` 的一个 exact target 完成 fresh Stage B → Stage C
  receipt → candidate → exports-v2 同源闭环；外层 C1 CLI exit=1。
- Convergence：`TARGET_CONVERGED` capability ceiling 为 `efl + conditional fnum`；
  IMH 可被 Stage C 证明 achieved 但非 Stage B converged；FOV derived/measured-only。
- Case library：442 = smartphone-wide 227 / telephoto 137 / ultrawide 78；442/442
  `image_height_mm` 非空。

## Blockers / Concerns

- 十二个历史固定树均不得发布：`57c305f37da6a4cc511e485900e6dcb04602a988` / tree
  `2b3c73d321677e863f2826e5e290e98e5b2bf8d7` 暴露 mapping、schema、draw/activation、pre-label、
  machine bijection 与 main-CI 六类 P1；后续 `a5ea60e0799c50af51110c2601169e5908a15851` /
  tree `930767afdded9fb5419531643fc6b1e7f0352d82` 又暴露 source-attestation 签名链、terminal
  pagination null、exhaustive digest registry、signed GitHub source profile、canonical O-07 release
  chain与 tracked-doc 时态问题；`ff76ae0c8dd87533820b73725590134d0a05dd03` / tree
  `431780535989ad8789de83ba0bbbdaec7e7da0ee` 又暴露 release/GitHub exact-source 与外部
  exact-base freeze 闭包问题；`d9e0e75ed291189bc3afbc8fc1f7f1ee05eb25fe` / tree
  `00c7af0f45c09896708cd2c570f93f86bdf6746a` 再暴露空 human roster/零 quorum、零 expert
  rater/阈值可真空闭 D，以及一个 mid-name hash 和两个 OID-or-marker 未入穷尽 selector。
  `bd2e1cf585375a3716a8ea2dd53f698b19068492` / tree
  `cf9c6f3e36ad1e2cac8f899c407ddf3e54624950` 的 GOVERNANCE/MACHINE scope 虽 PASS，
  RELEASE_GIT_CI 仍发现 GET 型 PR observation 的必填 `request_body_hash` 同时被要求为
  `SINGLE_DIGEST` 与 no-body marker，发布链不可满足；同树两份 PASS 已随 P1 作废。
  第六固定 commit `aca724155d464496e18e36700733931e9d05638a` / tree
  `53c24554606312fcbe54f9ddd836142f524fb34e` 的 GOVERNANCE/RELEASE_GIT_CI scope 虽 PASS，
  MACHINE 仍发现 inventory/admission 只有不透明 activation hash，缺少闭世界 typed 对象、原始外部
  OS attestation、selected-policy schema/control equality 及实际 ticket/intent/pre-spawn/start/terminal
  重算链；同树两份 PASS 已随 P1 作废。
  第七固定 commit `ead809c52b126cd9c9b99b14fd4db38cfcd22d2d` / tree
  `b140543e34e7da9e725ce613ba72e09a7c8175d5` 又被三路审查拒绝：GOVERNANCE 发现 inventory/
  admission 的签名 message preimage 排除了 `signature_algorithm`，且未明确绑定外部 trust roots、
  attester allowlist 与 allowed signature suite；MACHINE 发现 durable pre-spawn receipt 只重复初始
  inventory/admission hash，没有 fresh raw native revalidation、parser membership、外部 OS attester、
  单次原子 gate transaction 与延续至 process-start 的有界有效期；RELEASE_GIT_CI 另指出本文件把
  六棵树误写成“五个”。
  第八固定 commit `8acb078317e08fde061bc33dcd226864c5b6dcea` / tree
  `5856f8dd475942dcf3349d3302b22f0e3843e1aa` 也被拒绝：GOVERNANCE 发现 inventory/admission
  两条 content-hash 分类使用未注册的 `registered_object_hash` 别名；MACHINE 发现 DURABLE_COMMIT
  event subject 经同一 event-time leaf 的 source-attestation record 形成不可构造的哈希环，且
  acceptance mirror 同时保留过期 `25/25/46` 与规范 `27/27/48` 计数；同树 RELEASE_GIT_CI PASS
  随这些 P1 作废。
  第九固定 commit `0915ccf000438701bf10075e6f529ef349730e2a` / tree
  `7e004a031844720fdeb0226a328f2c40cb4d0bb9` 也被拒绝：GOVERNANCE/RELEASE_GIT_CI 发现本文件
  Current Position 与 Quick Tasks 两个入口摘要漏记第八拒绝树；MACHINE 发现 PRE_LEASE crash
  没有定义可构造的 pre-chain sequence/member 初始锚，却要求 last-durable 四元组来自已重放
  partial-chain transition；其 RELEASE_GIT_CI 自身也因入口摘要漂移判定 CHANGES_REQUIRED。
  第十固定 commit `2c74a540e11187d3fe8250e78d77dae291a7b7a7` / tree
  `5784baccc296586863f2d2bcc2788719b3a2064c` 的 GOVERNANCE/RELEASE_GIT_CI scope 虽 PASS，
  MACHINE 仍发现同一 `last_durable_member_hash` 路径在 PRE_LEASE 指 registered object、其他
  frontier 指 typed leaf，违反一固定路径一 reference class；同树两份 PASS 随 P1 作废。
  第十一固定 commit `02f9d17cfeb2c34749612bdc41744a4820e537e7` / tree
  `7abf1b6189718d2a9366bda030662181676fdb60` 又被三路审查拒绝：GOVERNANCE/MACHINE 发现
  `machine_partial_chain_member_template.typed_leaf_hash` 仍同时承载 typed leaf 与 registered
  `PROTECTED_ACCESS_TERMINAL_ENVELOPE`，且 GOVERNANCE 发现 crash record 的单一 registered-object
  路径条件承载 intent/terminal 两种 exact object type，均违反一固定路径一类/一 exact type；
  MACHINE/RELEASE_GIT_CI 还确认 PLAN/SUMMARY/VERIFICATION 保留 `2054/2061`，与固定 schema
  实算 `2055/2062` 漂移。
  第十二固定 commit `ab7ce4d82876361e686a8da603fbbc6712c1aa7d` / tree
  `f2ff988ab3bd0abe97dd066dd1a2aa90af820bcf` 的 GOVERNANCE/RELEASE_GIT_CI scope 虽 PASS，
  MACHINE 仍发现 24 个非terminal partial-chain typed member kind 只有 11 个 recovery kind 有
  exact template/domain 映射，其余 kind 可用同一 reference class 下的另一真实 leaf 冒充并推进 FSM；
  同树两份 PASS 随 P1 作废。当前第十三棵 clean-parent fix-forward 正补齐 24-key exact
  template/policy-schema/domain/context 解析表及 normal/recovery 分区，仍不是固定树审查证据。
  canonical template 的结构目标现为 66 registry objects（含两个 stage-bound authority
  roster/quorum content objects 与两个 machine inventory/admission objects）、24
  signer classes、10 hash-reference classes、26-field sealed manifest、exact-19 machine policy、
  27/27/48 machine bindings（另 33-field ACTIVE CAS）、29 machine typed leaves、32-field evidence、43-field
  release/authority mirror、25 shared bindings、64 release typed templates、20 protocol bindings，
  authority mirror 有 109 个全 null human-owned choices。任何 publication 必须重新形成固定
  commit/tree，让 GOVERNANCE/MACHINE/RELEASE_GIT_CI 三个 scope 的全新非作者只读 review
  都 PASS，再以 merge 后树外签发的 registered RUN_CODE_RELEASE package 证明 PR CI、expected-head
  CAS、provider acquisition→snapshot→merge-admission→terminal base/policy freeze 与 matching main
  CI；该 package 不闭 A–F；tracked
  文件中的“当前/已 PASS”文字永远不能替代该证据。
- NEED 主公/资深：候选人工筛判与良品率 go/no-go；`[EXPERT]` 仍为空。
- NEED 人类 minimum-claim authority：外部治理锚、目标 genesis、active floor、floor signature
  set、append-only atomic-CAS checkpoint store/high-water 与确定性版本血缘/equal-or-broader
  comparison 均未签或未建立；v0.1 场景集合变化及任何窄 scope 永久只能 exploratory。
- NEED 独立 custody/time authority：custody audit store policy/identity/genesis、独立 store
  attester allowlist、pre-draw clock policy/attester，以及 review store/clock/event-time source
  attester 均未外部锚定或签名；因此 draw 与人类 review 都未授权。
- NEED 资深：TOR 默认公差表 ratification；当前 MC 饱和使 yield unavailable。
- post-P1 executable lease 加固后未再次启动真实 CODE V；下一真机须重走 official gate。
- CODE V 当前低层启动链与用户级可替换锁不构成唯一 canonical launcher / machine-wide
  lease / human-approved OS admission boundary；直接 Popen 与 Web/CLI/batch/probe/test
  启动面须在任何真机前统一关进 launch
  ticket、冲突监控与 receipt-last 控制面；`pre_launch`/`during_run`/`post_run` 必须逐项覆盖
  `runner`、`codev`、`codevm`、`p18_owner`、`global_owner`、`per_call_owner`、
  `launched_subtree` 和 `unknown_carrier`。lease-owning broker 与这些归零对象分离，并以同一
  `lease_instance_id` 独占持有至 durable receipt；固定终态顺序为 `terminal_artifacts →
  post_run_snapshot_and_monitor → zero_state_proof → ACTIVE status CAS → machine receipt →
  protected terminal → release transition → PREPARED journal → OS release + OS_RELEASE_COMMITTED
  journal as one atomic authority transaction →
  RELEASED status CAS → release receipt`。只有前七项全零/缺席且 unknown absent 才沿该链
  释放 lease；未知/
  不可读状态 fail-closed 且不杀不清。
- 单 exact target 证据不可外推为通用生产能力。
- 机器协议的 19 个选择必须逐项满足 canonical typed minimum；policy hash 使用唯一 domain
  和 exact 19-key preimage。minimum-claim floor 只有在 X-00A 冻结 exact schema/anchor/goal
  后才可独立于 run code 签署；正式 protocol/TOR 签名必须晚于全部 O/M 代码的 O-07
  fixed-tree PR/CAS/main-CI release，H-03 draw/activation 更晚；讨论稿可并行但无权限。
- 外部依赖：另一台电脑的 109 ZMX、商用/合规定位、严格杂散光与 AR 外部工具链。
- 存量工单：unknown dispersion provenance、专利 WAVM 24 槽化、5P MTF NaN、P13
  GLD/withheld EFL、Stage B listing/WRX/WRY、C1 artifact-key collision。
- 专利饱和当前缺口：619 个本地未覆盖根已完成新隔离执行器冻结回放，且当前 619 根均有
  官方 PPUBS HTML；但仍无 source crawl exhausted 游标、无官方 family closure，且 parser、trace、
  staging intake 与 patent-budget 非终态均未闭合。
- 2026-07-15 完整宿主 pytest 首轮暴露非 `real_machine` 路径仍可启动 CODE V；该轮立即作废并
  终止 pytest 树。`D:/CVUSER/codev.rec` 只记录 `LEN NEW` 启动与 `EXI Y`，无业务宏。测试入口
  现对所有非 `real_machine` 测试在 `subprocess.Popen` 前 fail-closed 拒绝
  `codev/cvcommand/codevm/cvgui`；77 项专利/围栏相关测试前后均确认无 CODE V 进程。围栏后的
  2738 项宿主全套在 704 秒外层上限内未结束、无失败输出，不计作通过；完整 CI 仍待 PR。

## Quick Tasks

| ID | Status | Evidence |
|---|---|---|
| `260712-stagec-real-evidence` | complete | `.planning/quick/260712-stagec-real-evidence/`；PR #81 / main CI success。 |
| `260713-loop2-final-handoff` | released-with-heartbeat-receipt-gap | `.planning/quick/260713-loop2-final-handoff/`；PR #82/main CI success；heartbeat 当前不存在但无 durable deletion receipt。 |
| `260713-n7x` | active-unratified-external-release-evidence-required | `.planning/north-star/` 与 `.planning/quick/260713-n7x-unratified-claim-contract-authority-evid/`；历史 `57c305f/2b3c73d`、`a5ea60e/930767a`、`ff76ae0/4317805`、`d9e0e75/00c7af0`、`bd2e1cf/cf9c6f3`、`aca7241/53c2455`、`ead809c/b140543`、`8acb078/5856f8d`、`0915ccf/7e004a0`、`2c74a54/5784bac`、`02f9d17/7abf1b6`、`ab7ce4d/f2ff988` 固定树均被拒；`8acb078`、`2c74a54` 与 `ab7ce4d` 的同树 RELEASE_GIT_CI PASS 被其他 scope finding 作废，`0915ccf`、`02f9d17` 的 RELEASE_GIT_CI 自身为 CHANGES_REQUIRED；tracked 文档只定义 fail-closed gate，不自证 fixed-tree review/PR/CI/merge；A–F 保持 false。 |
| `260715-patent-saturation-ledger` | active-foundation-complete-saturation-incomplete | `.planning/quick/260715-patent-saturation-ledger/`、`data/patent-ledger/` 与 `.planning/loop/patent-saturation-baseline.md`；66 相关测试+Ruff 绿，三工件二次重建 byte-identical，严格 audit exit=1。 |
| `260715-patent-conversion-hard-timeout` | active-shovel-complete-saturation-incomplete | `.planning/quick/260715-patent-conversion-hard-timeout/`；真实 sleeping worker 在 0.2 秒超时后杀树/回收，真实处方跨进程成功且 retry request hash 稳定；77 项相关测试+Ruff 绿；宿主全套安全围栏后超时，完整 CI 待 PR。 |
| `260715-patent-local-pool-replay` | complete-local-replay-saturation-incomplete | Cohort SHA `e809823c...b42b`; 619/619 strict results, missing=0, corrupt=0; result-set SHA `3bc0bbee...76df`. Final items: parser review 1388, receipt terminal 631, staging pending intake 359, patent-budget retry 16. All current roots retain official PPUBS HTML. No-op replay processed 0 and preserved summary SHA `65122027...d130`. Parent saturation remains incomplete. |
| `260715-patent-sunny-metadata-parser` | complete-shovel-saturation-incomplete | Before 299 items/64 roots; after 199/53, resolving 100 without missing-field regression. Result-set SHA `2e0a9ceb...d506`; 619/619 strict results, missing=0, corrupt=0; 95 tests+Ruff green, CODE V inventory zero. Next largest parser bucket is generic summary metadata=294. |
| `260715-patent-generic-summary-metadata-parser` | complete-largest-bucket-shovel-saturation-incomplete | Strict before census 294 items/294 roots. Source-proven HTML layouts, source terminals, exact-raster PDF profiles, B2→A1 prior-publication recovery, and explicit official-PDF-only OCR paths are replayed append-only. The latest exact Genius Family ID 48153254 recovery source-locks the 65/66-page layouts and +1/+2 drawing-sheet offsets, expands all three roots to 11 embodiments each, and retains measured OCR failures without repair. Attempts 5/6 are semantic-equal per root and create no worker/ZMX. Generic bucket is 198, result set `ed908718...871f`, summary `73de95a9...210a`, after-census `6826002d...3363`, and audit is 619/619 corrupt=0. The next largest measured bucket is Sunny metadata at 199. |
| `260715-patent-sunny-residual-parser` | complete-largest-bucket-shovel-saturation-incomplete | Family 77932615 exact-source parsing reduces Sunny metadata 199→187. Two same-application roots each produce two staging conversions, four trace-failed terminals, one metadata terminal, and one explicit folded-coordinate parser gap. Attempts 3/4 are stable after retry identity is excluded; result set `8e5f3b0e...e5b5`, summary `6d6f73c3...dc4b`, after-census `a07909c5...d3bf`; audit 619/619 corrupt=0; 230 focused tests+Ruff green; CODE V zero. Generic summary 198 is next. |
| `260715-patent-generic-residual-parser` | complete-largest-bucket-shovel-saturation-incomplete | Family 72082560 exact-source classification reduces generic metadata 198→195. Three roots expand to 24 explicit confirmed-no-prescription terminals for seven barrel/absorbing-geometry examples plus one smartphone wrapper each; no worker/ZMX. Attempts 2/3 are canonical-equal after excluding only result identity; result set `502722f7...bb104`, summary `42b0a594...b8db`, after-census `4aa52fed...c6dce`; audit 619/619 corrupt=0; 245 focused tests+Ruff green; CODE V zero. Family 44121309 remains figure-OCR recovery because official text points to prescriptions in FIGS. 14A/14B. |
| `260715-patent-generic-family-77725725` | complete-largest-bucket-shovel-saturation-incomplete | Three exact Family 77725725 roots reduce generic metadata 195→192. Each independently expands to two terminals: folded lens-barrel driving/sensing architecture with only d1/d2 sensor distances, and multi-camera electronic-device architecture; no worker/ZMX. Attempts 2/3 are canonical-equal after excluding result identity; result set `3d12a5b3...3beb6`, summary `d2218257...6e138`, after-census `d9b439ac...f4bf7`; audit 619/619 corrupt=0; 247 focused tests+Ruff green; CODE V zero. |
| `260715-patent-generic-family-74060373` | complete-largest-bucket-shovel-saturation-incomplete | Family 74060373 reduces generic metadata 192→189. US-12092800-B2 is an exact-source panoramic opto-mechanical terminal; US-12313825-B2 and US-20250284103-A1 retain explicit seven-lens FIG. 8C parser reviews because zero numeric table tokens meet 0.99. No ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `e0b098b9...4c180`, summary `2cdf8187...76237`, after census `d638c3c5...81db5`; audit 619/619 corrupt=0; 251 related tests+Ruff green; CODE V zero. |
| `260716-patent-generic-family-44121309` | complete-largest-bucket-shovel-saturation-incomplete | Family 44121309 reduces generic metadata 189→186. Three exact HTML sources and three official/Google PDF pairs prove two spherical FIG. 14A/14B prescriptions per root, but publish no prescription-specific EFL or field. Generic F/6/about-F/3/F/2.5 contexts are rejected as substitutes. Six metadata terminals, no worker/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `dbf8a68e...0469a`, summary `17e7297f...114a`, after census `f47b2a27...106d`; audit 619/619 corrupt=0; 268 related tests+Ruff green; CODE V zero. Next family 46327306 has three roots. |
| `260716-patent-generic-family-46327306` | complete-shovel-saturation-incomplete | Family 46327306 reduces generic metadata 186→183. Three exact HTML sources, 17 drawing groups/58 panels, two clinical tables, and three official/Google PDF pairs prove EDOF phase-element architecture and experiments but no optical surface prescription. Each root is one confirmed-no-prescription terminal; no worker/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `450f7be0...259f`, summary `dd00af1d...fcbe`, after census `ed3e4ee5...88ce`; audit 619/619 corrupt=0; 288 related tests+Ruff green; CODE V zero. Sunny metadata 187 is now the largest measured executable parser bucket. |
| `260716-patent-sunny-family-75759822` | complete-shovel-saturation-incomplete | Two exact same-application publications each bind five 12-surface/6-asphere prescriptions and full-FOV metadata. Attempts 3/4 create ten staging-only candidates with stable semantic requests/responses/ZMX, but traced IMH differs from published ImgH, so formal intake remains pending. Result set `e4264482...1150`, summary `5f455956...561`, after census `a7f8bea5...1b74`; audit 619/619 corrupt=0; 307 offline patent tests pass; CODE V zero. Generic summary 183 is now largest. |
| `260716-patent-generic-family-86764397` | complete-shovel-saturation-incomplete | Two exact Family 86764397 publications bind four formal embodiments, three first-embodiment wire-geometry examples/tables, and 15 drawing sheets. Each root expands to three wire-geometry and three device-architecture confirmed-no-prescription terminals; no worker/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `374086dd...01eb`, summary `6d6c9dda...ca18`, after census `08763a8b...12e1`; audit 619/619 corrupt=0; 311 offline patent tests pass; CODE V zero. Generic 181 remains largest; Family 84363056 is next. |
| `260716-patent-generic-family-84363056` | complete-shovel-saturation-incomplete | Two exact same-application Family 84363056 publications bind five drawings and one four-lens material/system architecture. FIG. 3 publishes total length/EFL/ratio/FOV/aperture, but neither source nor official rasters publish radii, spacings, conic constants, or asphere coefficients. Each root is one confirmed-no-prescription architecture terminal; no worker/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `f2248ec6...5e03`, summary `c320157f...d4a1`, after census `c6816010...cb3`; audit 619/619 corrupt=0; 315 offline patent tests pass; CODE V zero. Generic 179 remains largest; Family 55525612 is next. |
| `260716-patent-generic-family-55525612` | complete-shovel-saturation-incomplete | Two exact same-application Family 55525612 publications bind five image-only three-lens surface/asphere prescriptions plus FIG. 21 comparison. HTML and exact-raster OCR publish complete optical tables, EPD/f/FOV, but no system F-number; `f/EPD` is not derived. Each root expands to five metadata-unpublished terminals; no worker/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `f8dcf2d0...ed72`, summary `c5cd5db3...fb2b3`, after census `0e49a78f...0d50`; audit 619/619 corrupt=0; 330 offline patent tests pass; CODE V zero. Generic 177 roots remains first; Family 53345880 is next. |
| `260716-patent-generic-family-53345880` | complete-shovel-saturation-incomplete | Two exact same-application Family 53345880 publications bind two three-lens surface/asphere prescriptions and direct focal-length/F-number/DOF values. HTML, exact 7-page raster pairs, and drawing OCR expose zero field labels; source-defined depth of field is not substituted for optical field of view. Each root expands to two metadata-unpublished terminals; no worker/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `3b35abd5...37bb`, summary `38ee7890...52d`, after census `829fe330...4758`; audit 619/619 corrupt=0; 332 offline patent tests pass; CODE V zero. Generic 175 roots remains first; Family 88236580 is next. |
| `260716-patent-generic-family-88236580` | complete-shovel-saturation-incomplete | B2 application 18/474353 and continuation A1 application 19/460417 bind seven embodiments, six subordinate thin-film examples, ten text tables, 18 drawing sheets, and 30-page official rasters. The tables publish coating-stack indices and D/FNO/FOV but no ordered surface prescription. Each root expands to six thin-film/module-architecture plus three device-architecture confirmed-no-prescription terminals; no worker/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `35fd7ce4...98ba`, summary `0e33db4a...1e86`, after census `672c21b5...a935`; audit 619/619 corrupt=0; 339 offline patent tests pass; CODE V zero. Prior publication US-20240111139 is outside frozen cohort and queued. Generic 173 roots remains first; Family 78592599 is next. |
| `260716-patent-generic-family-78592599` | complete-shovel-saturation-incomplete | Two exact same-application Family 78592599 publications bind three optical embodiments, nine complete system/surface/asphere tables, 11 figures, seven drawing sheets, and 15-page official rasters. Direct EFL/HFOV is published, but no exact F-number label exists and none is derived from stop data. Each root expands to three metadata-unpublished terminals; no worker/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `5469f103...2243`, summary `2e63566c...5947`, after census `2898b100...f003`; audit 619/619 corrupt=0; 347 offline patent tests pass; CODE V zero. Generic 171 roots remains first; Family 63585563 is next. |
| `260716-patent-generic-family-63585563` | complete-shovel-saturation-incomplete | Two exact same-application Family 63585563 publications bind three numerical embodiments × visible/IR states, 11 tables, 18 figures/sheets, and 34-page official rasters. First-embodiment visible/IR prescriptions parse exactly; 0.82 um stays source-faithful. Worker receipts classify them trace-timeout/trace-failed without candidate ZMX. Official rasters prove TABLE 7 duplicate K, TABLE 8 nonnumeric radius, TABLES 6/10 label conflicts, and narrative/TABLE 11 conflict, so the other four states remain precise parser reviews without repair. Attempts 2/3 are semantic-equal after retry/receipt normalization; result set `8ed2cd5a...75dd8`, summary `8e024e94...0e75b`, after census `d0954acc...26b91`; audit 619/619 corrupt=0; 353 offline patent tests pass; CODE V zero. Generic 169 roots remains first; Family 85199256 is next. |
| `260716-patent-generic-family-85199256` | complete-shovel-saturation-incomplete | B2 application 18/097820 and continuation A1 application 19/413947 bind zero tables/numbered examples and FIGS.1-19/24 panels. The 40/39-page official rasters disclose meta-layer stacks, transmittance simulations, phase profiles, and device blocks but no optical surface prescription. Each root is one confirmed-no-prescription meta-optical architecture terminal; no worker/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `92300ced...191b`, summary `3247788e...567f`, after census `6e9004c1...a8ff`; audit 619/619 corrupt=0; 354 offline patent tests pass; CODE V zero. Prior publication US-20230236339 is outside frozen cohort and queued. Generic 167 roots remains first; Family 60001556 is next. |
| `260716-patent-generic-family-60001556` | complete-shovel-saturation-incomplete | Same-application B2/A1 records bind five Examples, one identical TABLE 1 prescription, FIGS.1-42/72 panels, and 47-page/23-drawing-sheet official rasters. Example III publishes the surface prescription but no direct numeric EFL, F-number, or angular field; the other four Examples have no independent prescription. Each root expands to four confirmed-no-prescription terminals plus one metadata-unpublished terminal, with no worker/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `a20cd853...c38c9`, summary `d9511a52...b6cf8`, after census `45950d20...77b5f`; audit 619/619 corrupt=0; 367 offline patent tests pass; CODE V zero. Generic 165 roots remains first; Family 39526858 is next. |
| `260716-patent-generic-family-39526858` | complete-shovel-saturation-incomplete | Same-application A1/B2 records bind one formal Example 1, four lettered materials/force/focus-response/control tables, FIGS.1-28, and 37/39-page official rasters. The 5.88 mm/F# 6.6 benchmark belongs to an external IT5000 triplet and neither source publishes its ordered surface prescription. Each root is one confirmed-no-prescription actuator/imaging-terminal architecture terminal; no worker/request/receipt/fingerprint/ZMX. Attempts 2/3 are semantic-equal excluding result attempt; result set `d1e244e1...29981`, summary `3c060a84...2351`, after census `334d9fb7...7ce5`; audit 619/619 corrupt=0; 369 offline patent tests pass; CODE V zero. Six direct parent-chain records are queued outside the frozen cohort. Generic 163 roots remains first; Family 59199108 is next. |
| `260716-patent-generic-family-59199108` | complete-shovel-saturation-incomplete | Same-application A1/B2 records bind seven examples, 14 optical/asphere table figures, two comparison figures, FIGS.1-35, and 36-page/25-drawing-sheet official rasters. Prose publishes exact TTL/Fno/image-height/HFOV and optical tables publish EFL, but dense rotated asphere panels retain source-faithful low-confidence or missing duplicate labels. Each root expands to seven exact parser reviews; no numeric cell is repaired, no family-peer value is borrowed, and no worker/request/receipt/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding result attempt; result set `261a2747...30e6`, summary `293454d1...8e5d`, after census `b45149cc...8432`; audit 619/619 corrupt=0; 375 offline patent tests, compile, Ruff, and diff check pass; CODE V zero. Ten direct parent-chain records are queued outside the frozen cohort. Generic 161 roots remains first; Family 89001540 is next. |
| `260716-patent-generic-family-89001540` | complete-shovel-saturation-incomplete | Same-application A1/B2 records bind seven finite-object object-space telecentric nine-lens embodiments, TABLES 1-8, FIGS.1-28, and 29/27-page official rasters. Beam-splitter material/index/dispersion and exact system F-number are unpublished; Embodiment 1 also lacks numeric angular field, while Embodiment 7 retains the same undefined spacing chain in both official rasters. Each root expands to seven source terminals; no value is inferred/repaired and no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding result attempt; result set `df1f858e...35df`, summary `9a909055...696a`, after census `65385b78...7d36`; audit 619/619 corrupt=0; 386 offline patent tests, compile, Ruff, and diff check pass; CODE V zero. Generic 159 roots remains first; Family 74187659 is next. |
| `260716-patent-generic-family-74187659` | complete-shovel-saturation-incomplete | Same-application A1/B2 records bind three five-lens prescriptions, FIGS.1-7 and 4A/4B-6A/6B, plus complete 13-page official raster denominators. Direct EFL/Fno/TTL is published, but no angular field exists; h/H are explicitly fifth-lens shape coordinates. OL2 FIG. 5A publishes `R1=-17.90` while FIG. 7 publishes `R1=+17.90`, so the sign is retained as conflicted. Each root expands to three metadata terminals; no value is inferred/repaired and no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding result attempt; result set `9a5bb4f9...3da3`, summary `5791ed3d...e9f4`, after census `6680be2f...68fe`; audit 619/619 corrupt=0; 393 offline patent tests, compile, Ruff, and diff check pass; CODE V zero. Generic 157 roots remains first; Family 48495278 is next. |
| `260716-patent-generic-family-48495278` | complete-shovel-saturation-incomplete | Continuation A1 and parent B2 records bind six four-lens embodiments, 12 optical/asphere table figures, FIG. 26 comparison, FIGS.1-28, and complete 36/31-page official raster denominators. FIG. 26 directly publishes six Fno values, correcting the generic error, but optical/asphere labels and coefficient tokens retain source-faithful OCR gaps or sub-gate confidence. Each root expands to six exact parser reviews; no cell is repaired/borrowed and no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding only result attempt; result set `eb1d0319...6076e`, summary `59cc2380...58969`, after census `1a112e9d...72b22`; audit 619/619 corrupt=0; 400 offline patent tests pass. Prior publication US-20140071340 is queued outside the cohort. Generic 155 roots remains first; all remaining exact families have one root and Family 73978649 is next. |
| `260716-patent-generic-family-73978649` | complete-shovel-saturation-incomplete | Same-application B2/A1 records bind five examples, FIGS.1A-5D/23 panels, one 671-row 380-1050 nm reflectivity table, and complete 39-page official raster denominators. Examples 1-4 publish low-reflection coating/light-blocking architecture; Example 5 is the smartphone/camera wrapper. Neither text nor drawings publish an ordered surface prescription. The frozen root expands to five confirmed-no-prescription terminals; no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding only result attempt; result set `c9937f32...7e425`, summary `30e75e67...de9f`, after census `7e67aaf4...4ba7`; audit 619/619 corrupt=0; 399 offline patent tests, compile, Ruff, and diff check pass; CODE V zero. Same-application A1 and parent grant US-11852848-B2 are queued outside the cohort. Generic 154 roots remains first; Family 90845725 is next. |
| `260716-patent-generic-family-90845725` | complete-shovel-saturation-incomplete | Exact A1 publication binds two near-eye folded three-lens prescriptions, TABLES 1-5, FIGS.1-10, and a complete 14-page official raster denominator. Surface/path and R1-R6 asphere data plus ENPD/image-height/FOV/ratios/track lengths are direct, but numeric system EFL and F-number are unpublished and not derived. The root expands to two metadata terminals; no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding only result attempt; result set `74ecf2b3...b1f15`, summary `0c7cd328...b2f57`, after census `0bb9f153...6a240`; audit 619/619 corrupt=0; 403 offline patent tests, compile, Ruff, and diff check pass; CODE V zero. Three CN/JP publications are queued outside the cohort. Generic 153 roots remains first; Family 82157375 is next. |
| `260716-patent-generic-family-82157375` | complete-shovel-saturation-incomplete | Exact B2 source binds 19 seven-lens embodiments, TABLES 1-39 plus 40-1/40-2/40-3, FIGS.1-20, and complete 45/42-page B2/A1 official raster denominators. TABLES 1-38 are 19 surface/asphere pairs and the four system tables directly publish all EFL/FOV values, but no exact system F-number; `F/ENPD` and `F/EPD` are not substituted or derived. The root expands to 19 metadata terminals; no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding only result attempt; result set `23682c95...06d0`, summary `049b4cc9...78f8`, after census `eadbb9c2...7734`; audit 619/619 corrupt=0; 407 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. A1/WO family records and two CN priority documents are queued outside the cohort. Generic 152 roots remains first; Family 85407590 is next. |
| `260716-patent-generic-family-85407590` | complete-shovel-saturation-incomplete | Exact B2 source binds four variable-aperture camera-module embodiments, five third-embodiment bearing contact variants, one multi-camera device embodiment, 41 panels, zero PPUBS/optical tables, and complete 45-page B2/A1 official raster denominators. FNO/FOV occur only as source-wide ranges and are not converted to embodiment metadata. The root expands to eight module/bearing architecture terminals plus one device terminal; no worker/request/receipt/fingerprint/candidate/ZMX is created. Attempts 2/3 are semantic-equal excluding only result attempt; result set `7a7a6245...6ae0c`, summary `0de74ee2...1d43`, after census `07a2f534...83d7`; audit 619/619 corrupt=0; 411 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Six US/EP/TW/CN family publications are queued outside the cohort. Generic 151 roots remains first; Family 87936009 is next. |
| `260716-patent-generic-family-87936009` | complete-shovel-saturation-incomplete | Exact B2 source binds five seven/eight-lens embodiments, ten retracted/working states, TABLES 1-16, FIGS.1-23, and complete 43-page B2/A1 official raster denominators. Five non-working states lack state-specific metadata; B2/A1 rasters independently confirm malformed `A26=2.2728-07` and `A24=-5.39SE-06`, which are not repaired. Three remaining working prescriptions parse exactly: Embodiments 3/5 trace-fail and Embodiment 2 creates one staging-only candidate with 3/5 finite rays. Attempts 3/4 are semantic-equal after permitted retry normalization; result set `9acd2262...bd35`, summary `4c36148a...a6df`, after census `9b94e589...dfb1`; audit 619/619 corrupt=0; 415 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Eight US/CN/WO/EP family publications are queued outside the cohort. Generic 150 roots remains first; Family 95157884 is next. |
| `260716-patent-generic-family-95157884` | complete-shovel-saturation-incomplete | Exact A1 source binds ten six-lens moving-group prescriptions, twenty infinity/macro states, five apparatus/device wrappers, 39 source tables, 64 figure panels, 62 drawing sheets, and two complete 106-page official wrappers with 106/106 decoded-raster equality. Nine intact infinity states parse exactly: six create staging-only candidates with 2/5-4/5 finite final rays and three trace-fail. Nine finite-object macro states remain explicit parser reviews because replay is infinity-conjugate only. Official page 96 proves the two ninth-embodiment states have a blank stop radius and conflicting terminal numbering; five architecture wrappers publish no additional prescription. Attempts 2/3 are semantic-equal after permitted retry/receipt normalization; result set `0955e458...b9429`, summary `880de370...97b11`, after census `1b0db2e5...03a73`; audit 619/619 corrupt=0; 421 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Four CN/DE/TW family/priority publications are queued outside the cohort. Generic 149 roots remains first; Family 57585487 is next. |
| `260717-patent-generic-family-57585487` | complete-shovel-saturation-incomplete | Exact A1 source binds 24 polymer synthesis examples, 32 near-IR cut-filter manufacturing examples, one comparative example, FIGS.1-4 on two sheets, TABLE 1 heat/solvent-resistance ratings, paragraphs 0001-0620, and claims 1-18. Two independently fetched official wrappers and one Google wrapper contain 114 image pages and agree on all 114 decoded rasters. Text and all-page contact review expose zero ordered-surface prescription markers or hidden optical tables, so the root becomes one `near_ir_absorbing_polymer_and_cut_filter_materials_only` terminal with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `f0745d7a...61a5b`, summary `d69b7c61...bf7c4`, after census `75a22680...dfe35`; audit 619/619 corrupt=0; 425 offline patent/guard tests pass. WO/JP/TW family publications are queued outside the cohort. Generic 148 roots remains first; Family 93653416 is next. |
| `260717-patent-generic-family-93653416` | complete-shovel-saturation-incomplete | Exact B2 source binds an XR content-collaboration GUI/device disclosure, paragraphs 0001-0248, claims 1-48, zero tables, 52 drawing sheets, and 57 actual panels. Two official B2 wrappers contain 108 image pages and agree on every decoded raster; same-application A1 official/Google 96-page wrappers do too. The source has no ordered-surface, focal-length, radius/index/Abbe/asphere, F-number, or optical-prescription data, so the root becomes one `xr_content_collaboration_user_interface_and_device_architecture_only` terminal with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `024ce7b8...248b`, summary `20879bb5...d9a1`, after census `7be0f127...a0cc`; audit 619/619 corrupt=0; 443 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Same-application A1 and one PCT publication are queued outside the cohort. Generic 147 roots remains first; Family 97227325 is next. |
| `260717-patent-generic-family-97227325` | complete-shovel-saturation-incomplete | Exact A1 source binds two imaging-lens-assembly light-blocking/dual-retainer embodiments, two smartphone wrappers, one mobile-transportation wrapper, paragraphs 0001-0116, claims 1-30, TABLES 1-2, and 30 drawing sheets/panels. Two official wrappers contain 44 image pages and agree on every decoded raster. The tables publish only Do/Di/Ds/La/As/Lr/Lo geometry and no ordered prescription, so the source expands to five architecture terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `5a8c946b...e9b8`, summary `bf82ca12...16ee`, after census `dcd7a2a5...025d`; audit 619/619 corrupt=0; 447 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Six TW/CN/DE/GB publications are queued outside the cohort. Generic 146 roots remains first; Family 90454980 is next. |
| `260717-patent-generic-family-90454980` | complete-shovel-saturation-incomplete | Exact B2 source binds two folded reflective/refractive-member embodiments, eight paired stray-light simulations, FIGS.1-20/22 panels, background 1-5, summary 6-9, drawing paragraphs 1-23, detailed paragraphs 24-169, claims 1-13, and zero tables. Two B2 wrappers agree on all 40 decoded rasters; same-application official/Google A1 wrappers also agree internally, while B2/A1 differ 40/40 and are not cross-borrowed. Formulas and numeric ranges constrain member/cutting-plane/FOV/image-height geometry, not an ordered lens prescription, so the root expands to two confirmed-no-prescription architecture terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `aafd6769...3706`, summary `0100c148...8f07`, after census `7b25fa8e...4361`; audit 619/619 corrupt=0; 451 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Five KR/WO/EP/CN records are queued outside the cohort. Generic 145 roots remains first; Family 59500840 is next. |
| `260717-patent-generic-family-59500840` | complete-shovel-saturation-incomplete | Exact B2 source binds one cross-reference paragraph, Background 1-3, Summary 4-52, one brief paragraph, detailed paragraphs 2-733, claims 1-29, TABLES 1-6, 57 Examples, 18 Comparative Examples, 19 resin rows, and one layer-stack FIG. 1. Two B2 wrappers agree on all 78 decoded rasters; same-application official/Google A1 wrappers agree on all 79, while B2/A1 have zero equal positions over the first 78 pages and are not cross-borrowed. The 75 material/process/evaluation rows and figure publish no ordered optical prescription, so the root becomes one `dye_aggregate_film_and_optical_filter_materials_only` terminal with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `011e72b8...5405`, summary `1b8c66b8...ea5c`, after census `dba7bda7...7f08`; audit 619/619 corrupt=0; 455 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V zero. Seven WO/JP/CN/TW publications are queued outside the cohort. Generic 144 roots remains first; Family 62052738 is next. |
| `260717-patent-generic-family-62052738` | complete-shovel-saturation-incomplete | Exact same-application B2/A1 sources each bind two five-lens prescriptions, TABLES 1-12, FIGS.1-8, and complete 12-page raster denominators. Direct focal lengths, R1-R12 surface/material data, R1-R10 k+A4-A16 coefficients, entrance-pupil diameter, image height, and diagonal field are published, but only the source-wide inequality `F-number <= 2.0`; no exact F-number is derived. Each root expands to two `metadata_unpublished.system_f_number_absent` terminals without worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `7a070df9...ed6`, summary `ffa0e9c8...43c`, after census `013ab6f6...ee33`; audit 619/619 corrupt=0; 459 offline patent/guard tests passed before final cleanup and focused source/raster/replay checks pass afterward; CODE V zero. Four CN/JP publications are queued outside the cohort. Generic 142 roots remains first; Family 94531539 is next. |
| `260717-patent-generic-family-94531539` | complete-shovel-saturation-incomplete | Exact A1 source binds nine embodiments, thirteen subordinate structural examples, paragraphs 0001-0189, claims 1-29, TABLES 1-2, and 53 drawing panels. Two official and one Google 68-page image-only wrappers have distinct container hashes but agree on all decoded rasters. TABLE 1 is a 70-layer H/L coating stack and TABLE 2 has eight R50 samples; aspheric/refractive-index/focal-length language remains prism, coating, or generic device context, with no ordered optical prescription or direct EFL/F-number/field metadata. The root expands to fifteen folded sensor/filter/nano-surface architecture terminals plus five device-architecture terminals; no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt; result set `4f0c32cb...754b`, summary `3b2bc327...c572`, after census `d03bb802...f69`; audit 619/619 corrupt=0; 463 offline patent/guard tests pass; CODE V zero. JP/KR/CN/TW records are queued outside the cohort. Generic 141 roots remains first; Family 71121572 is next. |
| `260717-patent-generic-family-71121572` | complete-shovel-saturation-incomplete | Exact B2 source binds three seven-lens prescriptions, 18 ordered surfaces/14 ASP surfaces each, direct EFL/FNO/full-FOV/pupil/image-height metadata, TABLES 1-13, FIGS.1-12, and claims 1-19. Two official plus one Google 18-page B2 wrappers agree on all decoded rasters; official/Google 17-page A1 wrappers do too, while B2/A1 have zero equal same-position rasters and are not cross-borrowed. Published negative aperture d0 values remain source-faithful. All three process-isolated full-field traces fail before candidate emission; attempts 2/3 are semantic-equal after permitted retry/receipt normalization. Result set `1d1abad3...4d43`, summary `3eda3b00...15a1`, report `9c6ff015...5d64`, after census `34faa5dd...ea55`; audit 619/619 corrupt=0; 468 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V and staging ZMX zero. US/JP/WO/CN external family/priority records remain queued. Generic 140 roots remains first; Family 64459548 is next. |
| `260717-patent-generic-family-64459548` | complete-shovel-saturation-incomplete | Exact A1 source binds two five-resin-lens manufacturing embodiments, 190 sequential paragraphs, claims 1-14, 11 drawing declarations/23 panels, and zero tables. Two official plus one Google current-A1 wrappers agree on all 21 decoded rasters; official/Google parent-A1 wrappers also agree on all 21, while current/parent publications have zero equal same-position rasters and are not cross-borrowed. Full text and raster review finds no ordered optical prescription or direct EFL/F-number/field metadata, so both items become `lens_barrel_surface_modification_and_manufacturing_architecture_only` terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `bf48bcde...c7d6`, summary `0f56eae8...3a16`, report `2efdbba0...6c6cf`, after census `4879b3aa...2f5a`; audit 619/619 corrupt=0; 473 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V and matching staging ZMX zero. Parent US A1 plus CN/JP records remain queued outside the cohort. Generic 139 roots remains first; Family 69286146 is next. |
| `260717-patent-generic-family-69286146` | complete-shovel-saturation-incomplete | Exact B2 source binds three autofocus lens-module plus five electronic-device embodiments, one related-application paragraph, Background 1-4, Summary 5-13, Description 1-100, claims 1-12, FIGS.1-24, and zero tables. Two official B2 containers agree on all 35 decoded rasters; Google B2 is 404 and is not substituted. Official/Google A1 and A9 wrappers each agree on all 35 rasters within publication, while B2/A1/A9 differ 35/35 and are not cross-borrowed. All numeric disclosures are paragraph-bound aperture/carrier/shielding/device geometry; no ordered prescription or direct EFL/F-number/field metadata exists. The root expands to eight architecture-only terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `f9ef042b...c404`, summary `34a9f7ee...0b29`, report `30f27719...5e97`, after census `96a45871...1b86`; audit 619/619 corrupt=0; 478 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V and matching staging ZMX zero. Thirteen US/TW/CN records remain queued outside the cohort. Generic 138 roots remains first; Family 74529057 is next. |
| `260717-patent-generic-family-74529057` | complete-shovel-saturation-incomplete | Exact A1 source binds related application 1, Background 2-3, Summary 4-5, Description 6-96, claims 1-25, 25 drawing declarations, eight tables, two plastic-lens optical-inspection assembly embodiments, and one smartphone embodiment. Table 1 contains 20 material Nd/critical-angle rows; Tables 2-8 contain inspection/manufacturing values for seven plastic lens elements. Two official containers and the Google wrapper agree on all 35 decoded rasters; the complete cover/drawings/specification/claims denominator was inspected. No ordered prescription or direct EFL/F-number/field metadata exists, so two assembly items plus one device item become architecture-only terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `a8d6f4b0...d343`, summary `74b6e903...e458`, report `c7df7559...3253`, after census `e66a1b8b...678f`; audit 619/619 corrupt=0; 483 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V and matching staging ZMX zero. The same-application US grant plus five TW/CN records remain queued outside the cohort. Generic 137 roots remains first; Family 79728652 is next. |
| `260717-patent-generic-family-79728652` | complete-shovel-saturation-incomplete | Exact B2 source binds Background/Summary 1-26, Description 1-204, claims 1-20, 31 drawing declarations/55 panels, zero tables, eleven sensor-cover nanostructure embodiments, and one lithography/etching manufacturing embodiment. Published dimensions, refractive indices, angles, wavelengths and FDTD transmission/reflection results are cover-structure data. Two official B2 containers agree on all 47 decoded rasters; Google B2 exposes no complete PDF. Official/Google A1 wrappers agree 47/47 within A1, while B2/A1 differ 47/47 and are not cross-borrowed. No ordered prescription or direct EFL/F-number/field metadata exists, so twelve items become architecture-only terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `30865890...96f6`, summary `9dd62a79...38a1`, report `902a6189...dfbf`, after census `736a7d5f...46e6`; audit 619/619 corrupt=0; 488 offline patent/guard tests, compile, Ruff, and diff check pass; CODE V and matching staging ZMX zero. The same-application A1 plus five JP/WO/CN/DE/KR records remain queued outside the cohort. Generic 136 roots remains first; Family 97107823 is next. |
| `260717-patent-generic-family-97107823` | complete-shovel-saturation-incomplete | Exact A1 source binds paragraphs 0001-0140, claims 1-33, 28 drawing declarations/panels, zero tables, two shared camera-module contexts, nine explicitly named adjustable-aperture examples, and three smartphone/drone/vehicle placement embodiments. All thicknesses and ratios concern tapered/coated light-blocking sheets, overlap, or anti-bending sheets; no ordered radius/spacing/material/asphere prescription or direct EFL/F-number/field metadata exists. Two independent official containers agree on all 43 decoded rasters. Google exposes no complete PDF and is not substituted. The root expands to nine light-blocking-sheet architecture terminals plus three device-placement architecture terminals, with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `4855cde8...e4e5`, summary `9a55f07b...1b12`, report `ee96cbb5...fff3`, after census `74660804...64b9`; audit 619/619 corrupt=0; 493 offline patent/guard tests pass; final guard/Ruff/compile/diff checks are recorded in the quick task. Four JP/CN/EP/KR records remain queued outside the cohort. Generic 135 roots remains first; Family 100215250 is next. |
| `260717-patent-generic-family-100215250` | complete-shovel-saturation-incomplete | Exact A1 source binds paragraphs 0001-0083, claims 1-22, 18 drawing declarations/panels, zero tables, one shared aperture-module context, two Hall-connection examples, one dual-purpose-magnet aperture embodiment and two smartphone placement embodiments. The sole focal-length occurrence is a nonnumeric multi-camera digital-zoom narrative; no ordered radius/spacing/material/asphere prescription or direct EFL/F-number/field metadata exists. Two independent official containers agree on all 29 decoded rasters. Google is 404; PatSnap exposes exact text and one abstract composite but no complete static PDF, so neither is substituted. The root expands to three magnet/Hall-control terminals plus two device-placement terminals, with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `5523856b...64164f`, summary `bad71bc0...8999`, report `988f5e36...a57`, after census `c6c01e92...ebc0`; audit 619/619 corrupt=0; 498 offline patent/guard tests pass. Priority-linked `VN-126009-A` remains outside the cohort. Generic 134 roots remains first; Family 62524045 is next. |
| `260717-patent-generic-family-62524045` | complete-shovel-saturation-incomplete | Exact B2 source binds Background 1-2, drawing description 1-5, Detailed Description 6-62, claims 1-5, FIGS.1-4, six tables and one four-lens embodiment. Tables 1-6 plus paragraph 61 directly publish the complete R1-R10/d0-d10 surface/material rows, R1-R8 k+A4-A16 coefficients, focal length, entrance-pupil diameter, image height, TTL and diagonal field. The publication contains no F-number/FNO/F/#/numerical-aperture marker, and f/EPD derivation is forbidden, so the sole item becomes `metadata_unpublished.system_f_number_absent` with no worker/request/receipt/fingerprint/candidate/ZMX. Two official B2 containers and exact Google B2 agree on all 6 decoded rasters; Google is not numeric truth. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `4b299a66...d784`, summary `e385651f...27db`, report `b757d77e...bc38`, after census `3d201d88...a379`; audit 619/619 corrupt=0; guard 5/5, focused 5/5 and full offline 503 tests pass; compile, Ruff, JSON and diff checks pass; CODE V zero. Five US/CN/JP records remain outside the cohort. Generic 133 roots remains first; Family 61244801 is next. |
| `260717-patent-generic-family-61244801` | complete-shovel-saturation-incomplete | Exact B2 source binds paragraphs 1-87, claims 1-18, FIGS.1-8/eight drawing sheets, five image data tables, two source-named Sample Designs, 37 claim-style Examples and one mobile-device wrapper. Examples 1-18/19-36 are dependent six-/five-element constraint chains without additional coordinate tables; Example 37 maps to the third ledger item. Two official plus Google 19-page wrappers agree on all decoded rasters. Design 1 has incomplete coefficient OCR and no design-specific required system metadata; Design 2 has direct EFL/F-number/field/image-height but incomplete/joined coefficient OCR. Neither receives coordinate repair or conversion. The wrapper is `electronic_device_wrapper_only`, so the root is mixed with two parser reviews plus one terminal and no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 4/5 are semantic-equal excluding only result attempt. Result set `34dc2a55...a864`, summary `d6c329f3...a8a4`, report `21530397...7c38`, after census `cc6bd6ec...49d1`; audit 619/619 corrupt=0; focused 3/3 and all 495 offline patent/guard tests pass; compile, Ruff, JSON and diff checks are recorded in the quick task; CODE V zero. Ten family/related publications remain outside the cohort. Generic 132 roots remains first; Family 68533575 is next. |
| `260717-patent-generic-family-68533575` | complete-shovel-saturation-incomplete | Exact A1 source binds paragraphs 1-77, cancelled claims 1-20, active claims 21-33, three equations, zero HTML tables, 20 panels and six transmitter/model items. Two official plus exact Google 29-page raster-only wrappers agree on all decoded rasters. FIG. 8 publishes EFL/F-number and a power budget but no ordered surfaces; FIG. 13 uses a different-family lens because the Canon prescription was unavailable; FIG. 14 uses an unidentified ZEMAX database fish-eye. No external coordinates are imported. All six items become source-proven `confirmed_no_prescription` terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `7da144ba...2187`, summary `79c97023...28fd`, report `67c07340...5623`, after census `724c1d80...e1ec`; audit 619/619 corrupt=0; focused 3/3 and all 493 offline patent tests pass; guard 5/5, compile, Ruff, JSON and diff checks pass; CODE V and formal contamination zero. Three same-family and two cited-model publications remain outside the cohort. Generic 131 roots remains first; Family 79728600 is next. |
| `260717-patent-generic-family-79728600` | complete-shovel-saturation-incomplete | Exact A1 source binds paragraphs 1-138, claims 1-36, 14 panels, three tagged table blocks, one 20-row/16-QT1-surface base prescription and three unique variants. FIGS.2C/2D alter only the prism; FIGS.2B/2E inherit the base coordinates with 2.5/2.45 mm directional apertures. Table 2 publishes nonzero A6-A8, but exact A1 and same-application B2 define only Q0-Q5, publish no per-surface conic values, and omit referenced logical Table 3. No convention or coordinates are inferred. All three variants become source-proven metadata terminals with no worker/request/receipt/fingerprint/candidate/ZMX. Two official plus exact Google 19-page raster-only wrappers agree on all decoded rasters. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `dbbdf20c...f834d`, summary `b6c11b22...7007`, report `1c60b7b4...60b`; after census `ed5f2b68...c166`; audit 619/619 corrupt=0; focused 4/4, all 497 offline patent tests and guard 5/5 pass; compile, Ruff, JSON and diff checks pass; CODE V/formal contamination zero. Same-application B2, PCT, continuation grants and foreign records remain outside the cohort. Generic 130 roots remains first; Family 94050343 is next. |
| `260717-patent-generic-family-94050343` | complete-shovel-saturation-incomplete | Exact A1 source binds paragraphs 1-131, claims 1-20, FIGS.1-18, 17 tagged tables, 52 MathML objects and eight four-lens prescriptions. TABLES 1a/1b through 8a/8b publish direct system values and full surface/coefficient rows; TABLE 9 reconciles all examples. Every coefficient table has nonzero A3/A5/A7 on surfaces 8/9, and source prose plus official PDF formula proves true odd powers i=3..20. The current even-power `PatentSurfaceInput`/XASPHERE mapping cannot preserve them. TABLE 1a also prints em dashes for S6/S7 radii. All eight items remain parser reviews; no terminal inference, numeric synthesis, foreign coordinate borrowing, worker/request/receipt/fingerprint/candidate/ZMX. Two official 31-page raster-only containers agree on all decoded rasters; exact Google restores only the summation symbol. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `473b2a42...bfec`, summary `e9cad3a6...94d6`, report `8a26e150...c542`; after census `30789176...d97e`; audit 619/619 corrupt=0; focused 4/4, all 503 offline patent tests and guard 5/5 pass; compile, Ruff, JSON and diff checks pass; CODE V/formal contamination zero. CN/EP family members remain queue-only. Generic 129 roots remains first; Family 90040110 is next. |
| `260717-patent-generic-family-90040110` | complete-shovel-saturation-incomplete | Exact B2 and continuation-A1 sources reconcile both frozen roots of Family 90040110. Each publication binds six four-lens folded-path prescriptions, one FIG.20 electronic-device wrapper, TABLES 1-15, FIGS.1-20/24 panels, claims 1-9 and a complete 33-page image-only PDF denominator with 18 drawing sheets. TABLES 1-13 share the same numeric payload and directly publish ordered surfaces/aspheres plus f/TTL/BFL/ImgHT, but neither publication discloses a prescription-specific F-number or angular field; no aperture or f/image-height derivation is allowed. Twelve prescription items become metadata terminals and two wrappers become confirmed-no-prescription terminals, with no cross-publication numeric borrowing, worker/request/receipt/fingerprint/candidate/ZMX. Attempts 2/3 are semantic-equal per root excluding only result attempt. Result set `3cebf1af...f06926`, summary `38d766ca...c4edb`, report `1573d434...6d79`, after census `c49e747e...f3ff`; audit 619/619 corrupt=0; focused 7/7 and all 510 offline patent tests pass; final guard/Ruff/compile/JSON/diff checks are recorded in the quick task; CODE V zero. US/TW/KR family records remain queue-only. Generic 127 roots remains first; Family 91069629 is next. |
| `260717-patent-generic-family-91069629` | complete-shovel-saturation-incomplete | Exact A1 and same-application queue-only B2 sources reconcile Family 91069629, application 18/499185, JP2022-185927 priority, claims 1-7, FIGS.1-7/8A/8B, TABLES 1-4, one formula and three complete reflective pancake prescriptions. TABLES 1-3 share identical numeric payloads and directly publish f/Fno/half-field/image-height/TTL, 29-row paths, reflective surfaces 8/14, negative-thickness return rows and A4-A20. The current DTO/readout/rebuild path has no half-mirror, reflective-polarizer, quarter-wave-plate or polarization branch/multipass semantics and drops MIRROR material, so flattening would synthesize a different system. All three items remain nonterminal parser reviews, with no coordinate synthesis, raster transcription, cross-publication numeric borrowing, worker/request/receipt/fingerprint/candidate/ZMX. Two official 18-page raster-only containers and eight drawing sheets each are fully hashed and contact-reviewed. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `81366338...9138b6`, summary `36042d58...c58e`, report `ec4977fc...94f6`, after census `867f457f...ceb3`; audit 619/619 corrupt=0; focused 8/8, all 518 offline patent tests and guard 5/5 pass; final Ruff/compile/JSON/diff checks are recorded in the quick task; CODE V zero. Same-application B2 remains outside the frozen cohort. Generic 126 roots remains first; Family 82656625 is next. |
| `260717-patent-generic-family-82656625` | complete-shovel-saturation-incomplete | Exact B2 and continuation-A1 sources reconcile both frozen Family 82656625 roots, seven source items, 23 tagged tables and 24 figure panels per publication. All 23 table numeric payloads agree; Tables 9/18/23 differ only in text layout/order. Embodiments 1-6 publish lens count/order, refractive indices and nanostructure/coating/transmittance data while explicitly leaving surface shapes to demand; neither publication contains focal length, F-number, curvature-radius or asphere-coefficient disclosure. Embodiment 7 publishes only four-camera placement and FOV ranges. Fourteen items become source-proven confirmed-no-prescription terminals with no coordinate synthesis, raster transcription, cross-publication borrowing, worker/request/receipt/fingerprint/candidate/ZMX. B2, prior A1 and continuation A1 official PDFs contain 58/58/52 image-only pages and 22 drawing sheets each; every page is hashed and contact-reviewed. Attempts 2/3 are semantic-equal per root excluding only result attempt. Result set `1a8e93f1...e92c7`, summary `1a39d21b...b12b`, report `7ac8e16d...f049`, after census `a8dfa3de...e88f`; audit 619/619 corrupt=0; focused 7/7, all 525 offline patent tests and guard 5/5 pass; Ruff/compile/JSON/diff/formal-contamination checks pass; CODE V zero. Prior US A1 and EP/DE family records remain queue-only. Generic 124 roots remains first; Family 97303742 is next. |
| `260717-patent-generic-family-97303742` | complete-shovel-saturation-incomplete | Exact A1 source reconciles application 18/932225, Taiwan priority, paragraphs 1-266, claims 1-28, FIGS.1-45, 61 MathML objects, 29 tagged tables and fourteen source items. TABLES 1A/1B and 2A/2B/2C through 10A/10B/10C publish ten complete 17-row folded-prism prescriptions with direct f/f-over-EPDmax/HFOV, 12 asphere surfaces and material data; source definitions support half-field and working F-number. Four negative segments are adjacent to the first zero-power stop and become nonnegative under retained axial ordering; no mirror row or coordinate is invented. Ten items produce exact staging candidates; the image-unit and three electronic-device wrappers are confirmed-no-prescription terminals. The 69-page official PDF has 35 drawing sheets and one raster/zero text per page; all pages are hashed and critical pages contact-reviewed without numeric derivation. Attempts 2/3 have byte-identical request/response/candidate payloads and semantic-equal outcomes after only runtime identity normalization. Result set `18e49565...d4dc21`, summary `c0ceaa90...2c635`, report `87739d47...f8d81`; audit 619/619 corrupt=0; focused 6/6, all 531 offline patent tests and guard 5/5 pass; Ruff/compile pass; CODE V/formal intake zero. TW/CN/DE/GB records remain queue-only. Generic 123 roots remains first; Family 56417699 is next. |
| `260717-patent-generic-family-56417699` | complete-shovel-saturation-incomplete | Exact B2 source reconciles application 15/545636, PCT/US2016/014162, 71 numbered description segments, claims 1-14, FIGS.1-12, two tagged table blocks, three MathML objects and ten FIGS.3-12 source designs. FIG.3/TABLE 1 publish two tenth-order Legendre free-form reflectors, 66 coefficient pairs, f=52 mm and vertical/horizontal full fields 35/60 degrees, but no prescription-specific F-number, so it is metadata-unpublished. FIGS.4-12 have no independent complete prescriptions and become nine free-form reflective HMD architecture-only terminals. No free-form/non-sequential flattening, coordinate synthesis, raster transcription, cross-publication borrowing, worker/request/receipt/fingerprint/candidate/ZMX. Official and Google 17-page PDF containers have raster-identical decoded pages; critical drawing/table pages were visually reviewed. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `0d53acbc...d830`, summary `ef816071...ec7a`, report `b853ee46...ba79`; audit 619/619 corrupt=0; focused 5/5, all 536 offline patent tests and guard 5/5 pass; Ruff/compile/nine-JSON/hash/diff/formal-contamination checks pass; CODE V zero. Generic 122 roots remains first; Family 92714478 is next. |
| `260717-patent-generic-family-92714478` | complete-shovel-saturation-incomplete | Exact B2 source reconciles application 18/185364, prior A1, six background/related-technology paragraphs, 207 description paragraphs, FIGS.1-9, one tagged table, zero MathML objects and claims 1-25. FIGS.1-4 are usage scenarios; FIGS.5-9 are shared system/frame/sensor/ROI diagrams. TABLE 1 is explicitly four exemplary commodity-camera comparison rows, not four prescriptions. All source material maps to one smart-glasses ROI/camera-selection architecture item. Telephoto, wide-angle and periscope modules are named, but no ordered curvature/spacing/material/conic/asphere sequence is published, so the item becomes confirmed-no-prescription without commodity-lens substitution, drawing transcription or cross-publication borrowing. Official B2/A1 are 31/30 image-only pages; contact review proves scope only. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `99331d16...9fa8`, summary `686a2da2...b462`, report `e7e808bd...8423`; audit 619/619 corrupt=0; focused 5/5, all 541 offline patent tests and guard 5/5 pass; Ruff/compile/nine-JSON/hash/LF/diff/formal-contamination checks pass; CODE V zero. Generic 121 roots remains first; Family 75614661 is next. |
| `260717-patent-generic-family-75614661` | complete-shovel-saturation-incomplete | Exact A1 source reconciles application 19/384402, Korean priority, paragraphs 1-91, FIGS.1-10, TABLES 1-12, ten MathML objects and claims 1-12. Five surface/asphere pairs plus direct f/FNO/full-FOV metadata define five seven-lens examples. Examples 1/2/4/5 parse completely, including coincident powered/aspheric stops in examples 4/5; example 3 remains a precise parser review because all fourteen TABLE 5 lens radii conflict with TABLE 6. No conflicting value, drawing coordinate or related-family coordinate is substituted. The 22-page official PDF has ten drawing sheets and one raster per page; every page is hashed and critical table pages are visually checked. Attempts 3/4 are semantic-equal after only append-only receipt identity/path/hash normalization; four raw receipt chains remain committed and classify trace timeout, one item remains parser review, and no staging ZMX/formal intake exists. Result set `e6b551ee...a5d`, summary `7ed17fd3...8ff`, report `16d40be0...d23`; audit 619/619 corrupt=0; focused 6/6, all 547 offline patent tests and guard 5/5 pass; Ruff/compile/32-JSON/hash/diff/formal-contamination checks pass; CODE V zero. Generic 120 roots remains first; Family 82951912 is next. |
| `260717-patent-generic-family-82951912` | complete-shovel-saturation-incomplete | Exact B2 source reconciles application 17/930078, prior A1, one related-application paragraph, Background 1-3, Summary 4-6, drawing descriptions 1-35, Detailed Description 36-131, claims 1-18, 34 textual figure declarations, three tagged mechanical tables, zero MathML objects and nine source items. Embodiments 1-7 publish reflector-holder/insert-molded stamped support architecture; embodiment 8 is a four-camera smartphone wrapper and embodiment 9 is an AR head-mounted/display wrapper. Every curvature-radius occurrence is a stamped round corner and every thickness occurrence is a 0.15 mm metal plate; no ordered optical prescription or focal length/F-number/field metadata exists. All nine items become confirmed-no-prescription terminals. Official B2/A1 are each 44 image-only pages with 32 drawing sheets; text says FIG.10 while the panel says FIG.1C, retained without transcription or derivation. Attempts 2/3 are semantic-equal excluding only result attempt. Result set `df9054f7...60780`, summary `44122a90...cd73`, report `cbea4375...dccc`; audit 619/619 corrupt=0; focused 5/5, all 552 offline patent tests and guard 5/5 pass; Ruff/compile/JSON/hash/diff/formal-contamination checks pass; CODE V zero. Generic 119 roots remains first; Family 80893318 is next. |
| `260717-patent-generic-family-98774980` | complete-shovel-saturation-incomplete | Exact A1 source reconciles application 19/331023, provisional US63/698631, paragraphs 1-151, claims 1-30, 64 figure declarations/63 unique labels, three tagged mechanical tables, eleven MathML objects and ten source items. Seven examples publish resilience-wiring-sheet/lens-carrier/camera-drive architecture; three wrappers publish smartphone, folded-telephoto and vehicle-camera placement. Tables contain only D/Hn/L/Wc/Wf mechanics, the sole focal-length phrase is generic zooming and the vehicle visual angle is coverage. All ten items become confirmed-no-prescription terminals without source-label repair, drawing transcription, derivation, family borrowing or formal output. PDF endpoint 404; no raster/full-drawing claim. Attempts 2/3 semantic-equal excluding only result attempt. Result set `5b4f099d...a89e`, summary `5eac1373...1a0d`, report `fd4e34dd...52eab`, after census `8c10d69c...ab9f`; audit 619/619 corrupt=0; focused 5/5, all 607 offline patent tests and guard 5/5 pass; CODE V zero. Generic 108 roots remains first; Family 99480653 is next. |
| `260717-patent-generic-family-99480653` | complete-shovel-saturation-incomplete | Exact A1 source reconciles application 19/317450, US/TW priorities, paragraphs 1-52, claims 1-20, ten figure declarations, one tagged nine-row antenna table, zero MathML and four source items. Two items integrate camera-unit traces into antenna radiators; one names a generic imaging lens assembly/lens set/photosensitive element on an antenna board; one is a notebook wrapper. GHz/VSWR, quarter wavelength and board/coupling dimensions are antenna data. All four items become confirmed-no-prescription terminals without drawing transcription, derivation, family borrowing or formal output. PDF endpoint 404; no raster/full-drawing claim. Attempts 2/3 semantic-equal excluding only result attempt. Result set `e24815b3...3e67`, summary `91dcd231...8868`, report `28216762...0ba4`, after census `7078708e...fb66`; audit 619/619 corrupt=0; focused 5/5, all 612 offline patent tests and guard 5/5 pass; CODE V zero. Generic 107 roots remains first; Family 48982045 is next. |
| `260717-patent-generic-family-48982045` | complete-shovel-saturation-incomplete | Exact B2 source reconciles application 13/530530, Taiwan priority, paragraphs 1-47 across the old Background/Summary and Description numbering, claims 1-27, seven figure declarations, zero tables/MathML and two source items. One item is the four-prism light-dividing topology; one is the multi-view projection path with generic lens assemblies. The unnumbered acute angle and component counts do not publish a constituent lens prescription. Both become confirmed-no-prescription terminals without drawing transcription, derivation, prior-publication/family borrowing or formal output. PDF endpoint 404; no raster/full-drawing claim. Attempts 2/3 semantic-equal excluding only result attempt. Result set `f2ef7dfe...25e1`, summary `6bbf5578...3e548`, report `6d856a1c...43f99`, after census `b2dcc025...a0f4`; audit 619/619 corrupt=0; focused 5/5, all 617 offline patent tests and guard 5/5 pass; CODE V zero. Generic 106 roots remains first; Family 78342471 is next. |

## Session Continuity

Resume from `.planning/loop/prod-loop2-final-handoff-2026-07-13.md`.

For patent saturation work, resume from
`.planning/quick/260717-patent-generic-family-48982045/260717-patent-generic-family-48982045-PLAN.md`,
then preserve the cohort-pinned `data/patent-ledger/snapshot.json`; rebuilding that frozen input
while replay staging is active invalidates strict cohort audit. Never infer terminal outcomes from
chat or historical free-text reports. Before any test sweep, confirm the
non-`real_machine` CODE V subprocess guard is active and inventory is zero. The current
highest-value executable work is the complete-cohort largest parser bucket:
`generic_summary_metadata_missing` (106 roots/items), ahead by root count of
`sunny_embodiment_metadata_missing` (49 roots/177 items) and
`aac_raytech_summary_metadata_missing` (55 roots/174 items). Its next exact family under
deterministic root/item/layout/family ordering is Family ID `78342471`, root
`US-12092276`, publication `US-12092276-B2`, layout
`398622f52ff511311c349f40626f79b6e19bad3e73c2c0586750234eb69b3715`. Use
the same strict before/after census, source-proven layout,
append-only targeted replay, and full-pool audit contract. Remeasure after every shovel.

For north-star work, read `.planning/north-star/evidence-matrix.md`, then
`.planning/north-star/gap-ledger.json`, the canonical `UNRATIFIED` schema, its three
non-authoritative mirrors, and
`.planning/north-star/backlog.md`. The ledger is never gate proof.

Do not resume a P18 or Stage C runner from chat memory and do not recreate the closed loop2
heartbeat. Before any future machine call, recheck the retained ledger/artifact hashes and prove
`runner`, `codev`, `codevm`, `p18_owner`, `global_owner`, `per_call_owner`, and `launched_subtree`
are all zero or absent in the exact pre/during/post snapshot contract, with `unknown_carrier` absent
and the separate attested lease broker still holding the same lease through durable receipt.
