---
quick_id: 260713-loop2-final-handoff
status: release-gated
owner: Codex
base: 9249f97834a3bff52bb38e3e6ff456c7ec0aaec3
---

# Production-ready loop2 final handoff

## Goal

Close G after A–F are merged and main CI is green. Publish one concise, reader-tested
handoff; refresh project state and decision truth; update local shared memory without
rewriting historical evidence; then land the tracked documentation through PR → CI → merge
→ main CI and delete the `atelier-loop2` heartbeat.

## Gates

- `[EXPERT]` remains empty. No yield, qualification, good-part, or production-usable verdict.
- Preserve the distinction between P18 pipeline status, Stage B selected-input closure,
  Stage C delivered/blocked observations, and an expert yield decision.
- Canonical artifacts and hashes come from tracked files or retained runtime bytes, not AI
  summaries.
- Historical incident evidence remains immutable and is clearly marked non-publishable.
- Tracked docs start from clean `origin/main@9249f978` and land only through a reviewed PR.
- Local shared memory records the same facts and supersedes stale status without deleting
  history or reading credential/reference files.

## Work

1. Add `.planning/loop/prod-loop2-final-handoff-2026-07-13.md` with A–G status, canonical
   evidence, honesty boundaries, incidents, and next-owner gates.
2. Refresh `.planning/STATE.md` from stale 2026-07-08 state to the loop2 terminal truth.
3. Append minimal architecture/honesty/release decisions to `.planning/decisions.log`.
4. Update local shared memory: current-entry section in `project-atelier-batch5-handoff.md`,
   a focused loop2 evidence memory, index ordering, and superseded banners on stale C1/North
   Star snapshots.
5. Run deterministic doc checks and independent reader tests; fix any ambiguity.
6. PR, PR CI success, merge, matching main CI success, then remove heartbeat and mark the
   active goal complete.

## Verification before release

- `git diff --check` and explicit trailing-whitespace scan: PASS.
- Handoff relative-link existence scan: PASS.
- Disk SHA256 recheck: P18 audit, Stage B manifest-v2, Stage C matrix plan/state/current
  report, and production receipt all match the handoff.
- Runtime safety check during documentation work: `codev`/`codevm` process count zero; no
  runner, Python import, pytest, or real-machine action started.
- Fresh reader test initially found naming, checklist, conditional-F/#, and matrix-status
  ambiguities; all were fixed and the re-read closed P0–P3.
- Independent semantic audit against manifest/matrix/code: PASS, P0–P3 none.
- Independent tracked-diff review: PASS, P0–P3 none; docs-only change needs no additional
  machine or functional test. PR CI and matching main CI remain the release authority.

`release-gated` is deliberate: local work and independent review are complete, but this
plan must not claim G terminal until its tracked PR/main CI succeed and the heartbeat is
removed.
