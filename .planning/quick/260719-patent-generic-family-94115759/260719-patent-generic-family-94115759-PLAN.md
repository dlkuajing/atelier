# Quick Plan: Patent generic family 94115759

**Status:** Complete shovel — parent saturation remains incomplete
**Date:** 2026-07-19
**Parent:** Global patent saturation ledger (incomplete)

## Entry facts

- Family ID: `94115759`
- Root / publication: `US-12560789` / `US-12560789-B2`
- Application: `18/465987`
- Title: `Optical lens assembly and electronic device`
- First inventor: `Chen; Ping-Yi`
- Applicant: `NEWMAX TECHNOLOGY CO., LTD.`
- Assignee in retained queue record: unpublished
- Retained prior-publication marker: `US 20250013025 A1 Jan. 09, 2025`; only the
  B2 is retained in the frozen cohort, so this marker is not treated as a second root.
- Raw HTML:
  `data/patent-lake/uspto-ppubs-html/USPAT/bf9bd6013b3118d1/US-12560789-B2.html`
- Raw bytes / characters / SHA-256: `115279` / `113559` /
  `bf9bd6013b3118d153420f9942f11d057cb2bdcfce65550683fdf5680b9aa561`
- Layout signature:
  `83fa195a53c2afaf1f9a4e36a2a627409d3212d03966359958cc930bbaae7637`
- Entry marker scan: EFL=16, embodiment=120, example=0, F-number=0,
  full-field=2, half-field=0, queue table count=32. These counts are routing
  observations only, not a prescription, denominator or terminal outcome.
- Completed pre-change generic residual: 60 roots/items, result set
  `b9655a70613c2c5d95b2edd607f8fa7abb90064b782e27affe96a7457ca9021b`;
  the before census is copied byte-for-byte from the completed Family 94801574
  after census at SHA-256
  `84fa7c3f36a164251b24462a59e0446580b8b3f66e3fbc3372697abb91f965aa`.

## Objective

Independently reconcile the exact retained official B2, its application/family
lineage, every disclosed lens prescription, embodiment, variant and device wrapper,
all table/formula objects, claims, figures and source metadata; establish a complete
source-item denominator and bind each numerical value only to the item that directly
publishes it; encode only source-proven conversions or precise terminal/nonterminal
states; then close the root by append-only deterministic replay and full-ledger
evidence while preserving every global saturation invariant.

## Work plan

- [x] Open this GSD quick before source investigation or code edit and freeze the
  exact completed entry snapshot.
- [x] Copy the current 60-family generic residual census byte-for-byte and record the
  single selected root.
- [x] Reconcile bibliography, application/family lineage, section/paragraph/claim
  denominators, declared figures, every table/formula object and every source item.
- [x] Establish the complete document/page/figure/table/embodiment/item denominator
  independently of recognized prescriptions and marker counts.
- [x] Bind surfaces, spacings, materials, aspheres and system metadata only to the
  directly publishing item; never infer missing values from drawings, ratios, related
  publications, titles or generic lens terminology.
- [x] Inspect official PDF/original raster evidence only where necessary for layout or
  printed-token ambiguity; never enhance or measure drawings or invent numeric cells.
- [x] Add the narrowest exact parser/classifier support and focused tests only after
  source reconciliation; do not alter generic heuristics, scoring or redline criteria.
- [x] Replay twice under the frozen 180-second worker / 1,500-second patent budgets,
  compare only explicitly normalized business semantics, audit all 619 roots and
  rebuild the after census twice.
- [x] Refresh only live shared-ledger pointers required by deterministic tests while
  preserving historical snapshots.
- [x] Run focused/full offline tests, guards, compile/Ruff, JSON/evidence/output/
  contamination audits, strict corruption audit, CODE V inventory, primary-repository
  cleanliness and staged diff review.
- [x] Update STATE and decisions, mark this quick complete, commit atomically and select
  the next residual family without claiming global saturation.

## Constraints

- This quick is one reversible root shovel inside an incomplete parent goal.
- Do not start, control, probe or terminate CODE V; read-only process inventory only.
- Do not run `real_machine` tests or create formal optical cases/ZMX without complete
  source-proven metadata and existing quality gates.
- Preserve raw source typography; do not repair, derive or cross-borrow numeric values.

## Exact-source result

- The exact B2 binds application `18/465987`, Family ID `94115759`, prior
  `US-20250013025-A1`, and Taiwanese priority `TW-112124850` without borrowing
  content from the prior publication.
- The specification has 158 numbered section occurrences but 149 distinct labels:
  background 1–4, summary 5–27, and detailed description 19–149. The summary and
  detailed description intentionally repeat labels 19–27. Eighteen numbered drawing
  declarations, fourteen claims, 32 flattened tables, one MathML object, eight optical
  prescriptions and one electronic-device wrapper reconcile with no unmapped item.
- Items 1–8 are three-physical-lens multipass prescriptions. Every item directly
  publishes four tables, one ordered stop-bearing surface/material path, aspheres,
  near/far focal length, EPD, full FOV and the 555 nm reference wavelength. Exact
  whole-document scans publish neither a direct system F-number nor IMH/ImgH/image
  height. No `f/EPD`, `f*tan(FOV/2)`, path flattening or numeric repair is used.
- Item 5's near focal length `21.44 mm` exceeds its far focal length `21.12 mm` in
  the source; both values remain verbatim and unreordered.
- Paragraphs 146–149 and FIG. 9 reuse an assembly selected from embodiments 1–8
  inside a head-mounted device; they disclose no ninth prescription. Claims 2–14
  all depend on the sole independent claim 1 and do not add a device-claim family.
- Two independent official PDF fetches are byte-identical at `963a8b2b...12f` and
  decode to the same 38 original raster pages at `ff0b03a4...44b`: one front page,
  eighteen drawing sheets, nineteen specification pages, fifteen table pages and two
  claims pages. Review used no enhancement, drawing measurement, numeric raster
  transcription or inference.
- Attempts 2/3 are semantic-equal after removing only `result_attempt` at
  `3a0f398b...ec33`. Items 1–8 close as
  `metadata_unpublished.system_f_number_and_image_height_absent`; item 9 closes as
  `confirmed_no_prescription.electronic_device_wrapper_only`. No worker request,
  receipt, fingerprint, candidate ZMX, staging ZMX or formal intake is created.
- Generic residual is 60→59, after censuses are byte-identical at `ec3865af...bd11`,
  result set is `c1ed3dee...9432`, and strict audit is 619/619 with zero missing or
  corrupt results. Stable ordering selects Family `97232688`, root/publication
  `US-20250314947` / `US-20250314947-A1` next; global saturation remains incomplete.
- The complete patent parser file passes 841/841. The non-overlapping remaining 100
  test files pass in four stable shards (398 + 1714 + 282 + 355), for complete offline
  coverage of 3591 passed, one skipped and ten `real_machine` tests deselected: the
  841-test patent-file sweep and 2749-test remainder sweep were followed by the newly
  added sealed-evidence test, which passes separately. The
  initial monolithic remainder invocation hit its 1,204-second outer timeout without a
  pytest verdict; read-only inventory showed no orphan process, and the four exhaustive
  shards provide the valid result. Focused/sealed family tests pass 6/6 and explicit
  CODE V guard tests pass 5/5; Ruff, compile,
  JSON/evidence/formal-output/contamination/protected-path/diff/primary-repository and
  strict-ledger audits pass, with CODE V inventory zero.
- Sixty-three historical evidence manifests refresh shared summary/report records and
  eleven explicitly live result-set fields; historical census/replay/queue snapshots
  remain fixed. The next active GSD quick is
  `260719-patent-generic-family-97232688`.
