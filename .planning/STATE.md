# Project State

## Project Reference

See `.planning/PROJECT.md` and `AGENTS.md`.

**Core value:** 专家级量产设计论证；AI 多产候选与量化证据，资深保留全部
`[EXPERT]` 良品/合格/量产可用判定权。

**Naming:** `production-ready` / “生产可用”是 loop2 工程代号，不是资深 verdict。

**Current focus:** 北极星控制面 v13 已从干净 `origin/main` 经三路独立只读 PASS、PR #83、
PR CI、merge 与匹配 merge SHA 的 main CI 发布；Windows Stage B reviewed-source pin 漂移
已由 PR #84 发布闭合。当前从 `42803f8d` 的干净基线执行
O-01 strict preregistration/ITT protocol kernel。66-object canonical schema 与
claim/contract/authority mirrors 仍为 `v0.1-draft` + `UNRATIFIED`，北极星 A–F 全 false，
专家与制造指标 unavailable。控制面发布与离线内核实现都不等于北极星 go/no-go 已通过。

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
| North-star control plane | ACTIVE / UNRATIFIED / control-plane-released；A–F=false。历史十二个拒绝树继续禁止发布。v13 fixed commit `2ca16029` / tree `6a75caf1` 经 GOVERNANCE、MACHINE、RELEASE_GIT_CI 三路独立只读 PASS，PR #83 的 head CI run `29346835530` success，merge commit `7f53436d` 的 tree 与 reviewed tree 完全相同，匹配 main CI run `29349180244` success。该发布仅闭合控制面代码交付，不是 registered RUN_CODE_RELEASE package，不闭任何 A–F；O-09 detached release evidence 才可能闭 F。 |

**Release truth:** PR #81 merge
`9249f97834a3bff52bb38e3e6ff456c7ec0aaec3`；PR CI run `29227838587`
success；匹配 merge SHA 的 main CI run `29229500265` success。
Loop2 G docs PR #82 merge `d35b3d07cead830396d24d2b10665199c73985e0`；匹配 main CI
run `29233888562` success；本机 automation inventory 当前无 `atelier-loop2` heartbeat，
但没有 durable deletion operation receipt，故不外推删除动作的可重算 provenance。
North-star control-plane PR #83 reviewed head `2ca16029cc1b49b1ab2f17c0f379f7866a181c23`
/ tree `6a75caf13826c595be4f1a698af6ddf72bee5131`；PR CI run `29346835530` success；
merge `7f53436d3e470fde589bf62177b88d5ad11cebd5` 保持同一 tree，匹配 main CI run
`29349180244` success。
Stage B pin PR #84 reviewed head `2d36cb9096afb2c46100e40e484b5c4ad8930b9e` / tree
`839635e5ee732fa6a22ccba193deb27a90246efc`；PR CI run `29356580472` success；merge
`42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7` 保持同一 tree，匹配 main CI run
`29359056663` success。

**Progress:** loop2 技术探路、north-star v13 控制面与 Stage B Windows pin 修复发布链已闭合；
O-01 首个 `0ae75a9/5937ae7`、第二个 `66331983/f3ab3aaf`、第三个
`2d467ae6/344074d6`、第四个 `cc409880/f5cd22c9`、第五个 `536e26f/23ad364f` 与
第六个 `17a2eaa/87c50bf`
固定树均被独立只读审查拒绝
并禁止发布。前两树 fix-forward 已补报告自身 freeze-hash 绑定、冻结的
candidate reported-delivery 聚合、条件选择/exclusion 账本、嵌套 exact model class 与
model scalar exact-type/value 检查；第三树 fix-forward 再以 exact built-in raw 深快照消除
容器二次迭代，并强制 frozen 为 exact root model；第四树 fix-forward 要求 Pydantic
extra/private 槽严格为 None；第五树 fix-forward 再以声明注解先验 exact-type 检查、exact
built-in model storage、hidden slot 存在性与 raw cycle guard 封闭自替换容器、隐藏 extra、
缺失槽和循环载荷；第六树 fix-forward 又以物理键数+exact string key 先验检查、identity-only
类型分派与递归异常封装，阻断恶意 key/class/metaclass hook 和深层 raw 异常泄漏。91 项精确
检查、Ruff、mypy 与 2267 项全仓离线回归均已绿；新的 clean-parent fixed-tree identity
以 Git 为准，全新三路只读审查 pending。
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

## Quick Tasks

| ID | Status | Evidence |
|---|---|---|
| `260712-stagec-real-evidence` | complete | `.planning/quick/260712-stagec-real-evidence/`；PR #81 / main CI success。 |
| `260713-loop2-final-handoff` | released-with-heartbeat-receipt-gap | `.planning/quick/260713-loop2-final-handoff/`；PR #82/main CI success；heartbeat 当前不存在但无 durable deletion receipt。 |
| `260713-n7x` | control-plane-released-unratified | `.planning/north-star/` 与 `.planning/quick/260713-n7x-unratified-claim-contract-authority-evid/`；十二个历史固定树均被拒且禁止发布；v13 `2ca16029/6a75caf1` 三路独立只读 PASS，PR #83 / PR CI `29346835530` / merge `7f53436d` / main CI `29349180244` success。该链不构成 registered RUN_CODE_RELEASE，不闭 A–F。 |
| `260714-stageb-pin-line-ending` | released | `.planning/quick/260714-stageb-pin-line-ending/`；PR #84 / PR CI `29356580472` / merge `42803f8d` / main CI `29359056663` success；reviewed LF pins 未改，Windows uniform CRLF checkout 可验证，mixed/bare CR 仍拒绝。 |
| `260714-o01` | fixed-tree-review-pending-v7 | `.planning/quick/260714-north-star-o01-protocol-kernel/`；前六棵至 `17a2eaa/87c50bf` 均被只读审查拒绝且禁止发布；当前 candidate 91 targeted + Ruff/mypy + 2267 full offline 绿，clean-parent identity 以 Git 为准，全新三路审查 pending；A–F/GO 保持 false。 |

## Session Continuity

Resume from `.planning/loop/prod-loop2-final-handoff-2026-07-13.md`.

For north-star work, read `.planning/north-star/evidence-matrix.md`, then
`.planning/north-star/gap-ledger.json`, the canonical `UNRATIFIED` schema, its three
non-authoritative mirrors, and
`.planning/north-star/backlog.md`. The ledger is never gate proof.

Do not resume a P18 or Stage C runner from chat memory and do not recreate the closed loop2
heartbeat. Before any future machine call, recheck the retained ledger/artifact hashes and prove
`runner`, `codev`, `codevm`, `p18_owner`, `global_owner`, `per_call_owner`, and `launched_subtree`
are all zero or absent in the exact pre/during/post snapshot contract, with `unknown_carrier` absent
and the separate attested lease broker still holding the same lease through durable receipt.
