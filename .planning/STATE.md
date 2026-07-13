# Project State

## Project Reference

See `.planning/PROJECT.md` and `AGENTS.md`.

**Core value:** 专家级量产设计论证；AI 多产候选与量化证据，资深保留全部
`[EXPERT]` 良品/合格/量产可用判定权。

**Naming:** `production-ready` / “生产可用”是 loop2 工程代号，不是资深 verdict。

**Current focus:** production-ready loop2 的技术与证据链已完成 A–F；G 的终态记录为
本次 handoff、`STATE.md`、shared memory 与决策日志。G 只有在该文档变更经 PR/main CI 落地且
`atelier-loop2` heartbeat 删除后才成立；技术闭环不等于北极星 go/no-go 已通过。

## Current Position

| Scope | Status |
|---|---|
| Phase 13 glass-snap 铲3 | 完成；PR #74，matrix v7 20/20 可执行格。 |
| Phase 14 TOR 铲2 | 完成；PR #68。默认公差表仍待资深 ratify，yield unavailable。 |
| Phase 15 Stage B F/# | 完成；PR #75。F/# 仅由候选自己的 closed ladder gate 条件授予。 |
| Phase 17 close-out | 完成；PR #71。ZMX 持久化与串行 repeat engine 落地。 |
| Phase 18 batch | 完成；PR #72/#77/#80。50/50：29 succeeded、21 degraded、0 failed。 |
| Phase 16 Stage C | 完成技术证据闭环；PR #76/#78/#79/#81。48-run matrix + 单 exact target production/export。 |
| Loop2 G | 发布契约：tracked handoff/STATE/decisions + 本机 shared memory + docs PR/main CI + heartbeat 删除。 |

**Release truth:** PR #81 merge
`9249f97834a3bff52bb38e3e6ff456c7ec0aaec3`；PR CI run `29227838587`
success；匹配 merge SHA 的 main CI run `29229500265` success。

**Progress:** loop2 A–F 100%；G 以本文档变更的 PR/main CI 与随后 heartbeat 删除为
最终 gate。北极星的资深良品率 go/no-go 未执行，不能写成“量产可用已通过”。

## Evidence Snapshot

- P18：50 targets / 50 jobs / 50 valid CandidateSets；29 succeeded / 21 degraded /
  0 failed；污染的 job-0020/0021 attempt-1 永久排除。
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

- NEED 主公/资深：候选人工筛判与良品率 go/no-go；`[EXPERT]` 仍为空。
- NEED 资深：TOR 默认公差表 ratification；当前 MC 饱和使 yield unavailable。
- post-P1 executable lease 加固后未再次启动真实 CODE V；下一真机须重走 official gate。
- 单 exact target 证据不可外推为通用生产能力。
- 外部依赖：另一台电脑的 109 ZMX、商用/合规定位、严格杂散光与 AR 外部工具链。
- 存量工单：unknown dispersion provenance、专利 WAVM 24 槽化、5P MTF NaN、P13
  GLD/withheld EFL、Stage B listing/WRX/WRY、C1 artifact-key collision。

## Quick Tasks

| ID | Status | Evidence |
|---|---|---|
| `260712-stagec-real-evidence` | complete | `.planning/quick/260712-stagec-real-evidence/`；PR #81 / main CI success。 |
| `260713-loop2-final-handoff` | release-gated | `.planning/quick/260713-loop2-final-handoff/`；仅匹配 main CI success 后闭合。 |

## Session Continuity

Resume from `.planning/loop/prod-loop2-final-handoff-2026-07-13.md`.

Do not resume a P18 or Stage C runner from chat memory. Before any future machine call, recheck
the retained ledger/artifact hashes and prove runner, CODE V/codevm, P18 owner, global owner,
and per-call owner are all zero. The `atelier-loop2` heartbeat is deleted only after G's docs
PR and matching main CI succeed.
