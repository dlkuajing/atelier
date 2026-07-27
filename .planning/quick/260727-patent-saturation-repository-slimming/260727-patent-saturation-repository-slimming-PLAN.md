# Quick Plan: Patent saturation repository slimming

**Status:** Active
**Date:** 2026-07-27
**Base:** `origin/main` at `42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7`
**Source branch:** `codex/patent-saturation-ledger` at
`6dad8ab815498453fb2b3e1970ff7bfddd5e85d1`

## Objective

Publish the completed patent-saturation work without importing the source branch's
approximately 2.62 GB of ordinary Git blobs into `main`. Preserve deterministic code,
ledger state, source identities, hashes and reproducible evidence boundaries while
keeping normal clone and CI costs proportionate.

## Frozen inventory

Recomputed from the source branch tree at
`6dad8ab815498453fb2b3e1970ff7bfddd5e85d1`:

- 10,527 tracked files totaling 1,887,069,812 bytes in the final checkout.
- 4,138 binary evidence files totaling 1,751,304,821 bytes:
  3,561 PNG, 343 PDF, 233 TIFF and 1 GIF.
- Every binary candidate is below `.planning/quick/` or `data/patent-lake/`;
  there are no matching binaries outside that scope.
- The final tree excluding those binaries is 135,764,991 bytes.
- The source branch contains 229 commits over `origin/main`; its new ordinary-Git
  blob history totals approximately 2.62 GB.

## Storage decision

Use Git LFS for the 4,138 immutable evidence binaries and retain code, schemas,
manifests, ledgers, receipts and text metadata in ordinary Git.

- Rewrite only the unpublished derivative branch
  `codex/patent-saturation-slim`, excluding `origin/main`.
- Preserve the source branch, source worktree and source SHA unchanged.
- Preserve commit order, messages and logical trees; only commit IDs and binary
  storage representation change on the derivative branch.
- Hydrate LFS objects in CI before tests because source-evidence tests hash the
  checkout bytes. Cache `.git/lfs` by the checked-in pointer set to avoid repeated
  bandwidth use.
- Do not delete, regenerate, deduplicate by discarding paths, or externalize evidence
  behind an unversioned URL.

## Migration result

`git lfs migrate import` rewrote the 230 unpublished derivative commits (the 229
source commits plus this quick's plan commit) and produced a complete old/new commit
map:

- Rewritten migration head:
  `8c877abab2eaf1d89e28f5173bae18541e0a25f0`.
- Source branch restored and verified at:
  `6dad8ab815498453fb2b3e1970ff7bfddd5e85d1`.
- `origin/main` remains:
  `42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7`.
- Current checkout contains 4,138 LFS paths backed by 4,124 unique objects.
- LFS logical bytes are 1,751,304,821; unique LFS object bytes are 1,718,987,981.
- Remaining ordinary-Git delta history contains 16,631 blobs totaling 903,375,763
  uncompressed bytes; the largest remaining blob is 4,557,660 bytes.
- A full standalone pack of every object in `origin/main..HEAD` is 15,328,265 bytes
  (16,172,781 bytes including its index), well below GitHub's 2 GiB push limit.
- `lfs-commit-object-map.csv` records all 230 old/new commit pairs.
- `lfs-evidence-manifest.json` records every path, exact byte count and SHA-256 LFS
  object ID and is the CI cache-key source.

Git LFS also moved the local source-branch ref because it pointed into the rewritten
commit set, despite the explicit include-ref. The old objects remained present; the
source ref was immediately restored with a guarded `git update-ref`, and its worktree
returned clean at the original SHA. No file content or source commit was discarded.

CI now restores `.git/lfs`, runs `git lfs pull`, and verifies the hydrated objects
with `git lfs fsck` before dependency installation and tests. Tests therefore continue
to see the original evidence bytes rather than pointer text.

## Safety boundary

- Preserve the source branch and worktree unchanged as the complete local evidence
  archive; never rewrite, reset, clean or force-push it.
- Work only in `D:\atelier-wt-patent-slim` on
  `codex/patent-saturation-slim`.
- Do not push or merge until the slim tree, evidence policy and tests are complete.
- Never direct-push `main`; publication remains PR-only.
- Do not start, control, probe or terminate CODE V; process inventory is read-only.
- Do not weaken evidence, parser, terminal, scoring, quality or protected-path gates to
  make the slim tree pass.

## Work plan

- [x] Recompute the source branch's final-tree and history-only size distribution by
  path, extension and artifact role.
- [x] Reconcile every source-evidence reference and determine which artifacts must
  remain checkout-local for deterministic tests.
- [x] Select and record the smallest viable storage policy (ordinary Git, Git LFS, or
  external immutable archive) using repository and GitHub runtime facts.
- [x] Fast-forward this transport-only derivative from `origin/main` to the source
  branch's complete 229-commit logical history.
- [x] Migrate eligible large binary evidence out of ordinary Git while preserving
  byte/hash/source receipts and checkout behavior.
- [x] Recompute evidence manifests and acceptance checks without inventing or repairing
  source data.
- [ ] Run the complete non-`real_machine` test suite, Ruff, diff, object-size,
  protected-path, worktree and primary-repository audits.
- [ ] Record the final storage/restore contract in `STATE.md` and `decisions.log`.
- [ ] Commit atomically; push and PR only after the slim branch is demonstrably below
  GitHub's limits and the user-approved evidence contract remains intact.
