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

**Patent saturation focus (2026-07-16, branch work):** `origin/main@42803f8` 起的独立
`codex/patent-saturation-ledger` worktree 已建立 GSD quick 控制面。运行时重算为 714 个 USPTO
元数据根、442 个正式设计（425 个专利设计、116 个美国专利根）、95 个本地池根有正式工件、
619 个未覆盖；发现并集为 735 根（另 21 个正式根不在本地元数据池）。canonical snapshot
SHA-256=`c86527b71e0500074bf14e1668bc3ab6701e5d54d3d22ef5826686101d6b5ec1`；
foundation snapshot 的严格 audit 为 `saturation_complete=false`，明确 735 根未归族/未终态、
425 个正式 embodiment 尚未按新 provenance 合约闭环、25 个旧 seed embodiment 身份未明确；
当时 735 根均无保留全文。第三个 quick 现已为冻结的 619 个本地未覆盖根全部保留官方 PPUBS
HTML 并生成严格回放结果，但尚未把这些非终态闭合进总饱和账本。这是未合 main 的进行中证据，
不是饱和完成声明；500 仅为历史进度标记。当前严格 replay result set 为
`3b35abd57d957037c12d2589b1e0c551b1f3bf86af67ebd443e17310ebaf37bb`：619/619、
missing=0、corrupt=0。Family ID `53345880` 的 `US-20160161712-A1` 与 `US-9810879-B2`
已完成同申请 `14/832442`、先前公开关系、精确 HTML、五张文本表、四幅图与两张 drawing
sheet 的全分母审计。每份公开包含两项处方：TABLES 1/2 与 3/4 分别给出 surface/asphere
数据，TABLE 5 直接给出焦距、F-number 与 DOF。HTML、7/7 页 exact-raster PDF 及 OCR 视图
均没有 `FOV`、`HFOV`、`field of view` 或 `angle of view`；源文把 DOF 展开为
`depth of feild`，不得把景深偷换成视场。两根 attempts 2/3 各生成两个 source-proven
`metadata_unpublished.system_field_of_view_absent` 终态，未调用 worker、未生成
receipt/fingerprint/ZMX。Generic 从 177 items/roots 降至 175/175，两次 after census
byte-identical，SHA-256=`829fe330d4957de1127234154014d6c14e7b12556af4b80dff546d1b81824758`。
按非终态 root 数，generic 175 仍高于 Sunny 49 roots/177 items 与 AAC Raytech 55 roots/
174 items；下一 exact same-layout family 为 `88236580`（`US-12631860`、
`US-20260153717`），layout
`2839abb89a9f0b8c35e4e9fea01fcc28fb417bb16ec6a7f400d4e8f23f6cd61e`。

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
| Patent saturation | ACTIVE / INCOMPLETE. Frozen replay is 619/619, missing=0, corrupt=0, result set `3b35abd5...37bb`. Current roots: 359 parser review, 141 mixed, 94 terminal, 25 converted; items: 544 staging, 1402 parser review, 902 terminal, 28 conversion retry. Family 53345880 converts each exact same-application publication from one generic parser item to two source-proven system-field-unpublished terminals, with no worker/ZMX. Generic 177→175 roots/items and still ranks first by nonterminal roots; next deterministic same-layout family is 88236580. This is not source/global saturation. |

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

## Session Continuity

Resume from `.planning/loop/prod-loop2-final-handoff-2026-07-13.md`.

For patent saturation work, resume from
`.planning/quick/260716-patent-generic-family-53345880/260716-patent-generic-family-53345880-PLAN.md`,
then preserve the cohort-pinned `data/patent-ledger/snapshot.json`; rebuilding that frozen input
while replay staging is active invalidates strict cohort audit. Never infer terminal outcomes from
chat or historical free-text reports. Before any test sweep, confirm the
non-`real_machine` CODE V subprocess guard is active and inventory is zero. The current
highest-value executable work is the complete-cohort largest parser bucket:
`generic_summary_metadata_missing` (175 roots/items), ahead by root count of
`sunny_embodiment_metadata_missing` (49 roots/177 items) and
`aac_raytech_summary_metadata_missing` (55 roots/174 items). Its next exact family under
deterministic root/item/layout/family ordering is Family ID `88236580`, roots `US-12631860` and
`US-20260153717`, shared layout `2839abb8...f6cd61e`. Use the same strict before/after census,
source-proven layout, append-only targeted replay, and full-pool audit contract. Remeasure after
every shovel.

For north-star work, read `.planning/north-star/evidence-matrix.md`, then
`.planning/north-star/gap-ledger.json`, the canonical `UNRATIFIED` schema, its three
non-authoritative mirrors, and
`.planning/north-star/backlog.md`. The ledger is never gate proof.

Do not resume a P18 or Stage C runner from chat memory and do not recreate the closed loop2
heartbeat. Before any future machine call, recheck the retained ledger/artifact hashes and prove
`runner`, `codev`, `codevm`, `p18_owner`, `global_owner`, `per_call_owner`, and `launched_subtree`
are all zero or absent in the exact pre/during/post snapshot contract, with `unknown_carrier` absent
and the separate attested lease broker still holding the same lease through durable receipt.
