---
quick_id: 260715-patent-saturation-ledger
status: complete
owner: Codex
base: 42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7
---

# Patent saturation ledger foundation

## Goal

Establish the recomputable, fail-closed control plane for the patent-library saturation
program before any further full-pool conversion or source expansion. Replace historical
wave-local free-text outcomes with one canonical ledger in which every discovered patent
family/root and every known embodiment has exactly one structured terminal status.

This shovel is a foundation for the larger saturation goal. It does not claim that the
current pool, parser set, source set, or formal seed library is saturated.

## Frozen runtime baseline

- Git base: `origin/main@42803f8de6c6d8f6a2dbd5a0d4eb0c2ed8cf5ad7`.
- Raw USPTO metadata pool: 11 JSONL files, 714 records, 714 normalized US patent roots.
- Concatenated pool bytes SHA-256:
  `bba21147e576ee4674105884a95eb31b466b0f1aa6e8166e627dd9ba8867309e`.
- Formal case index: 442 designs; 425 patent designs; 116 US patent roots.
- Raw/formal overlap: 95 roots; raw roots without a formal seed: 619.
- Case-index bytes SHA-256:
  `3845d04dff1a86048a3dc8552a3e815db0ac24d37ce8f38573660676cf50a441`.
- No retained patent HTML/XML/PDF/TIFF raw documents were found under `data/`.
- `data/patents/crawl-cursor.json` is absent. The tracked `convert-cursor.json` is a
  historical conversion-wave cursor and is not source-exhaustion evidence.

All counts and hashes above must be recomputed by the ledger builder; they are not trusted
as hand-maintained assertions.

## Canonical terminal statuses

The only terminal statuses are:

- `intaken`
- `duplicate`
- `quality_rejected`
- `confirmed_no_prescription`
- `fulltext_unavailable`
- `parser_family_missing`
- `metadata_unpublished`
- `trace_failed`
- `trace_timeout`
- `externally_blocked`

There is no `unknown`, generic `failed`, silent skip, staging-only success, or free-text-only
terminal state. Human-readable detail may supplement, but never replace, a structured status,
reason code, source identity, retry identity, and evidence hashes.

## Scope of this shovel

1. Define strict models for source records, patent-family/root records, embodiments, attempts,
   artifacts, and terminal outcomes.
2. Build a deterministic baseline command from tracked raw-pool JSONL and the formal case
   index. It must normalize roots, reject duplicate identities, bind input bytes by SHA-256,
   map formal embodiments, and emit canonical JSON plus a compact report.
3. Add an auditor that fails if any discovered root is absent, duplicated, non-terminal,
   inconsistent with formal artifacts, or represented only in staging.
4. Import only facts that current tracked artifacts can prove. Historical prose such as
   `dead`, `partially`, `failed`, or `skipped` must not be silently translated into a terminal
   category without machine-readable evidence.
5. Record the remaining roots as explicit work items outside the terminal ledger until a
   deterministic replay produces one allowed terminal outcome. The terminal auditor must
   therefore report incomplete saturation and exit non-zero at this stage.
6. Add focused tests, run Ruff, and run the relevant offline regression subset with
   `PYTHONUTF8=1`.

## Follow-on shovel ordering

1. Add a process-level per-patent/per-embodiment conversion worker with hard timeout,
   kill-tree termination, bounded reap, retained raw input, structured log summary, and stable
   retry identity. A daemon thread is not an acceptable timeout implementation.
2. Freeze and replay the 619 uncovered local roots. Select the next parser/source-recovery
   work from the largest structured failure bucket after every replay.
3. Persist official-source raw documents and source cursors separately from formal seeds.
4. Expand official discovery/family/full-text sources only after cursor, provenance, rate-limit,
   and terms evidence is represented in the same control plane.
5. Repeat deterministic replay until a frozen pool produces no new accepted seed, then perform
   formal-library/golden/provenance reconciliation and independent read-only review.

## Hard gates

- No LLM-generated, inferred, midpoint-filled, guessed, or repaired optical number.
- Do not modify scoring rulers, redline criteria, or existing physical thresholds.
- Do not run CODE V or `codevm`.
- Do not populate `[EXPERT]`, declare good-part/yield/qualification, or equate routing intake
  with production usability.
- Raw patent artifacts and formal seed artifacts remain separate.
- Network/source failures stay explicit and never become `confirmed_no_prescription`.
- A family/root terminal status cannot hide non-terminal embodiments.
- No direct push to `main`; release remains reviewed PR -> PR CI -> merge -> matching main CI.

## Verification contract

- Deterministic unit tests cover schema closure, root normalization, exactly-one terminal
  outcome, hash reproducibility, formal-index reconciliation, staging rejection, and incomplete
  saturation exit behavior.
- `PYTHONUTF8=1 uv run pytest <targeted tests>` passes.
- `PYTHONUTF8=1 uv run ruff check <changed Python files and tests>` passes.
- Re-running the builder on unchanged inputs produces byte-identical canonical output and
  report hashes.
- `git diff --check` passes.
- This quick remains `active` until the foundation is implemented, tested, reviewed, and its
  evidence is recorded. Completion of this quick is not completion of patent saturation.

## Completion evidence

- Canonical snapshot SHA-256:
  `c86527b71e0500074bf14e1668bc3ab6701e5d54d3d22ef5826686101d6b5ec1`.
- Recomputed counts: 714 raw roots; 442 formal designs; 425 formal patent artifacts;
  116 formal roots; 95 overlap; 619 uncovered raw roots; 21 formal-only roots; 735-root union.
- Strict audit exits 1 with five explicit gaps: 735 unresolved family memberships, 735
  unresolved root outcomes, 425 unresolved embodiment outcomes, 25 legacy-unspecified
  embodiment identities, and 735 roots without retained full text.
- `PYTHONUTF8=1` relevant regression: 66 passed.
- Ruff: all changed Python files pass.
- Snapshot, audit, and report hashes are byte-identical after a second full rebuild.
- `git diff --check`: pass.

The quick is complete because its foundation contract is implemented and verified. The parent
patent-saturation goal remains active and incomplete; the next GSD shovel is process isolation
and hard timeout.
