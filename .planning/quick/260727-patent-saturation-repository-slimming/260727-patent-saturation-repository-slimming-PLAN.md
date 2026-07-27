# Quick Plan: Patent saturation repository slimming

**Status:** Complete (PR publication pending)
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

Use Git LFS for immutable evidence binaries and retain code, schemas,
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
- Final checkout contains 4,269 LFS paths backed by 4,226 unique objects.
- LFS logical bytes are 2,043,282,327; unique LFS object bytes are 1,942,561,003.
- Remaining ordinary-Git delta history contains 22,490 blobs totaling 1,010,973,488
  uncompressed bytes; the largest remaining blob is 4,557,660 bytes.
- A conservative standalone pack of every ordinary-Git object in
  `origin/main..HEAD` is 29,439,968 bytes, well below GitHub's 2 GiB push limit.
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

## Reproducibility closure

Validation exposed that the source worktree's green suite depended on ignored local
evidence that was absent from Git. A fresh checkout first missed USPTO HTML and PDF
sources, then conversion receipts referenced by the replay ledger. The derivative now
tracks the complete tested offline closure while leaving the source archive untouched:

- 865 previously ignored patent-lake evidence files: 610 HTML, 127 PDF, 123 JSON,
  four PNG and one text file. PDF/PNG content follows the existing LFS policy.
- 8,108 previously ignored conversion-attempt files and 567 staging ZMX files,
  totaling 32,934,259 bytes.
- The two local OCR ONNX model files remain ignored because the offline suite does not
  require them and they are not part of any checked evidence reference.
- Raw USPTO batches, the frozen optical-case index, and quick-task JSON/Markdown
  evidence have explicit checkout-byte rules so Linux and Windows reproduce the hashes
  recorded by the manifests.

The complete non-`real_machine` verification is green: 4,133 passed, one skipped and
10 deselected. This is composed of the 1,477-test patent shard and four non-patent
partitions (the heaviest first partition was itself split after one transient wrapper
exit). `git lfs fsck`, the 4,269-path manifest hash test, Ruff and diff checks pass.
Those initial transport and evidence-closure gates did not start or control CODE V.

## Latest-main integration

The six commits that first reached `origin/main` during validation were merged through
`6016b662`, whose second parent is `42e05fbb`. Replaying the newly inherited
`uv run pytest -q -n 4` command on a Windows machine with CODE V installed exposed two
separate issues:

- Because the command lacked a marker exclusion, it accidentally selected one
  `real_machine` round-trip test. That test started the local CODE V executable, exited
  with a 24-versus-3 wavelength mismatch, and was not rerun. The CI command now
  explicitly uses `-m "not real_machine"`.
- Six offline tests failed only under xdist because destination-derived temporary
  filenames crossed the Windows `MAX_PATH` boundary. Same-directory temporary names
  now use only a UUID while retaining atomic replace or exclusive-create semantics.
  The reviewed Stage B wrapper hard pin was recomputed for the resulting source bytes.

After those corrections, the exact CI-equivalent offline command passed with 4,133
passed and one skipped in 22 minutes 12 seconds. The focused parallel regression passed
31/31; Ruff, CI YAML parsing, diff checks, `git lfs fsck`, manifest rehash, source
worktree and process inventories also pass. The later PR #89 pair was merged through
`17d71802`; its four affected Stage C/orchestration test files pass 193/193 under the
same explicit non-`real_machine` marker.

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
- [x] Run the complete non-`real_machine` test suite, Ruff, diff, object-size,
  protected-path, worktree and primary-repository audits.
- [x] Record the final storage/restore contract in `STATE.md` and `decisions.log`.
- [x] Commit the storage migration and reproducibility closure after proving the branch
  is below GitHub's push limits and the evidence contract remains intact.
- [x] Integrate the six commits that first reached `origin/main` during validation and
  make the inherited parallel CI command explicitly offline-safe.
- [x] Integrate the two commits from PR #89 that reached `origin/main` after the final
  full local gate and rerun the affected gates.
- [ ] Push the slim branch and publish it through a reviewed PR.
