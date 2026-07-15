---
quick_id: 260715-patent-generic-summary-metadata-parser
status: active
owner: Codex
base: c3f7af8
---

# Generic summary metadata parser census and deterministic expansion

## Goal

Reduce the largest current frozen-pool parser signature,
`generic_summary_metadata_missing` (294 items), by auditing every affected latest replay item and
its retained official USPTO PPUBS HTML, grouping the exact published metadata layouts, and adding
only deterministic embodiment-bound extraction rules.

This quick does not infer optical values, promote staging candidates, change quality/scoring
thresholds, or claim patent saturation.

## Evidence contract

1. Build a strict before census from the latest 619-root result set, bound to cohort and result-set
   hashes. Retain root, publication, item, embodiment, raw HTML path/hash, and normalized layout
   signature for all 294 matching items.
2. Inspect the complete census before choosing a format family. Historical parser names and
   assignee assumptions are not evidence.
3. Every accepted EFL, F-number, and half-field value must be an exact published token or an
   explicitly defined deterministic transform such as full-field divided by two.
4. Metadata without a provable embodiment binding, damaged OCR, or ambiguous multiple candidates
   remains a structured parser-review item.

## Implementation and replay contract

1. Rank exact layout groups by affected item/root count and implement the largest homogeneous
   source-proven group first.
2. Preserve existing family-specific parsers; do not make the generic parser permissive enough to
   steal or cross-bind another family's tables.
3. Add exact-source regression fixtures for every layout and negative tests for ambiguity and
   cross-embodiment leakage.
4. Replay affected roots append-only through the existing process-isolated converter and 180-second
   root budget. Successful output remains `converted_pending_intake`.
5. Recompute the full summary, strict external-evidence audit, and before/after census. Record the
   next largest measured bucket.

## Safety and verification

- Use `PYTHONUTF8=1` on Windows and `uv` only.
- Confirm CODE V inventory is zero before and after replay; do not start CODE V/codevm.
- Run focused parser/replay tests, the patent regression set, Ruff, strict audit, and
  `git diff --check`.
- Do not modify scorers, redlines, forbidden paths, or physical thresholds.

## Runtime census checkpoint (2026-07-15)

- Strict before census: 294 document-scoped items / 294 roots, bound to result set
  `2e0a9ceb2e8b930393168dc7f9cda50c1659aebeacab6afe98f0b96dfea5d506`.
- Optional alphanumeric table suffixes (`1A`, `1B`) are included in layout segmentation. The
  census has 179 exact normalized signatures; artifact SHA-256 is
  `fa145da695c2e9d2dbff1fe8d9c5144ceb84773e1fa1e2edf70d6af211da82c4`.
- The first source-proven family is 8 roots / 58 disclosed embodiments with exact published
  `f=... mm, Fno=..., HFOV=...` headers. Deterministic dry-run yields 52 complete prescriptions
  and 6 structured physical/OCR rejections. The two related exemplary tables with a different
  `S.sub.i` structure remain outside this implementation.
- Append-only replay completed all 8 roots. The generic document bucket changed 294→286; the 58
  disclosed embodiments produced 26 converted-pending-intake items, 26 terminal receipts, and 6
  structured parser rejections. No candidate was promoted. Result-set SHA-256 is
  `f0e4e3c1a0a0600fea49c276ce51cfe7a84558228d55bb0f404509bebe6f4dc8`; strict audit is
  619/619 with zero corrupt evidence. The after-first-layout census SHA-256 is
  `f165467dd70fe1ab98e529c61dbc95ef499e1f47523e854595ae1101f5673c35`.
- The second source-proven family is 3 roots / 21 disclosed folded-zoom states. Exact adjacent
  configuration tables bind EFL, F/#, HFOV, and every variable air gap by column. Twelve ASP
  states are deterministically recoverable. Six QTYP states retain the published duplicate `S7`
  / missing `S8` index failure; three index-complete QTYP states retain an explicit unsupported
  `QTYP/NR/A0-A6` rejection instead of translating a different polynomial basis as XASPHERE.
- Append-only replay completed all 3 roots. The 21 states produced 9 converted-pending-intake
  items, 3 terminal process receipts (`trace_timeout` after the 120-second worker hard limit), and
  9 structured parser rejections. No candidate was promoted. The generic document bucket changed
  286→283. Result-set SHA-256 is
  `3aab024784036d6f268f741deb0396d68438300226b20e9805f0c20f05d48bd6`; summary artifact
  SHA-256 is `80310958a437ab64a90f997035cfc065c7aa73a9ec399f4c56e56a8ed44dcb19`;
  strict audit is 619/619 with zero corrupt evidence. The after-second-layout census SHA-256 is
  `fb68b3362117a00506dcadbc34189b7a6222a3d4afbddeb9559295aabbdc4798`. The
  family-ownership scan matches exactly these 3 roots before replay and zero remaining roots after
  replay; 74 focused parser/census/replay/process tests and Ruff pass.
- A larger 3-root / 30-embodiment layout was inspected but remains fail-closed. Its retained
  official PPUBS text defines only asphere terms A--H and J, while the published tables also carry
  nonzero L--P columns without an official exponent definition; it also does not bind a stop
  location to each embodiment. Translating those columns or selecting a stop would therefore be an
  unsupported optical-value inference.
- The third source-proven family is the exact Apple `TABLE 1A/1B`, `2A/2B` exemplary layout in
  `US-20170090155` and `US-9897779`. Each A table publishes embodiment-bound f, F-number, HFOV,
  S0--S9 geometry and materials; each paired B table publishes K and A--F under the patent's own
  asphere definition. A full 283-root ownership scan matched only these two roots and recovered
  4/4 prescriptions without parser errors.
- Append-only replay completed both roots and all four embodiments as
  converted-pending-intake; the two publication roots share the same two prescription fingerprints,
  so duplicate disposition remains an intake responsibility rather than a parser guess. No
  candidate was promoted. The generic document bucket changed 283 to 281. Result-set SHA-256 is
  `099a5180a6237899947be146612b2117666b55b859dcbcdac116bd6aa03e64ad`; summary artifact
  SHA-256 is `607f64d35302fc199e531bc55d9d28972b582bfd5224d7beb874f2a3ee3f57b1`;
  strict audit is 619/619 with zero corrupt evidence. The after-third-layout census SHA-256 is
  `1e3800f286ed316840dd70b3b379987b187da8ede95b6f38595b94cf001319f8`; 77 focused
  parser/census/replay/process tests and Ruff pass.
- The fourth source-proven family is the exact 22-table Samsung wide-horizontal-FOV layout in
  `US-12560782` and `US-20260153712`. Ten narrative statements bind table pairs 1/2 through
  19/20 to embodiments one through ten; S9 is the published stop, table 21 binds f, f-number, and
  HFOV by embodiment column, and the official text defines A--H/J as aspherical constants. The
  same text explicitly defines HFOV as full horizontal field of view, so the parser divides each
  published value by two for the pipeline half-field input. A full 281-root ownership scan matched
  only these two roots and recovered 20/20 prescriptions without parser errors.
- Append-only replay completed both roots and all twenty embodiments as
  converted-pending-intake. Corresponding embodiments across the application and grant have the
  same ten prescription fingerprints; duplicate disposition remains deferred to intake. No
  candidate was promoted. The generic document bucket changed 281 to 279. Result-set SHA-256 is
  `846ec2bb7bdd342281532daf5b31975838eec4e1908837162c3dd290e12f5e9e`; summary artifact
  SHA-256 is `70456cf863ab2daf58826dab71bff755963a62b89f5746fc4b6548f7842ecc84`;
  strict audit is 619/619 with zero corrupt evidence. The after-fourth-layout census SHA-256 is
  `d0fc9ec820763cc0255a6a164bf014d451f205b089862d87343a1467c5470629`; 80 focused
  parser/census/replay/process tests and Ruff pass.
- The fifth source-proven family is the exact 24-table mobile imaging-lens layout in
  `US-20220276465`. Its official PPUBS text publishes twelve surface/asphere table pairs, explicit
  stop rows, f/Fno/ω in every surface-table header, and explicitly defines ω as half field of
  view. A complete 279-root ownership scan matched only this root. Eleven embodiments parse
  deterministically; example 2 remains fail-closed because official TABLE 4 splits the nonzero
  coefficient token `1.729 E-04`. The parser does not join or repair it.
- Append-only replay retained all twelve disclosed embodiments: the eleven complete
  prescriptions received terminal `trace_failed` receipts because full-field real rays did not
  reach the image surface, while the damaged second embodiment remains a structured parser-review
  item pending alternate official fulltext/image recovery. No ZMX was promoted or left in staging.
  The generic document bucket changed 279 to 278. Result-set SHA-256 is
  `18a0a3102b5b3c8fedfff26b1500db893e931b3bd0068893133ce9071ef4f036`; summary artifact
  SHA-256 is `b20fbe2d945280148d3555c9c19cf870b6eb0d5f4d8d053f70aaff2e5db0b3e9`;
  strict audit is 619/619 with zero corrupt evidence. The after-fifth-layout census SHA-256 is
  `7026ffe86f8cfbb7472e53cf30807d27487fd2c5d7505c168d85803c559041fa`; CODE V inventory
  remains zero; 84 focused parser/census/replay/process tests and Ruff pass.
- The sixth source-proven family is the exact 26-table Kantatsu nine-lens layout in
  `US-20210364764`. Its official PPUBS text binds table pairs 1/2 through 25/26 to thirteen
  numerical-data examples, defines ω as half angle of view, publishes the stop at surface 1,
  and publishes K/A4--A16 for surfaces 1--18. A hash-verified ownership scan of all 278 remaining
  generic roots matched only this root. Examples 1--3 and 5--6 parse deterministically. Example 4
  retains the official split surface token as a parser rejection; examples 7--13 retain the
  official `[nm]` surface-table unit instead of silently repairing it to `[mm]`.
- Append-only replay retained all thirteen disclosed embodiments: examples 3, 5, and 6 are
  converted-pending-intake staging candidates; examples 1 and 2 have terminal `trace_failed`
  receipts because full-field real rays did not reach the image surface; the eight source-damaged
  examples remain structured parser-review items. No candidate was promoted. The generic document
  bucket changed 278 to 277. Result-set SHA-256 is
  `d989da868801c39202dc943d636f5684b8ef7082f3f27f2bc2607cd0097eda47`; summary artifact
  SHA-256 is `f3cfc0c56b8972c65d583f5908b2a1975c8c4a94e953cc8ec318a2d20d4e7a8b`;
  strict audit is 619/619 with zero corrupt evidence. The after-sixth-layout census SHA-256 is
  `d391572abd94870b92b42d6f8fb69aced2ad87b15f51f683a87f843f87539a59`; CODE V inventory
  remains zero; 87 focused parser/census/replay/process tests and Ruff pass.
- `US-20260063876` remains fail-closed after official-text inspection. Its prescriptions use a
  refractive prism and publish two direction-specific stops plus `f/EPDmax`; the current
  rotationally symmetric sequential model cannot represent the coordinate bend or directional
  pupils. Collapsing those disclosures to one inferred stop/F-number would change the optical
  model, so this is not treated as the next scalar-table parser layout.
- The seventh source-proven family is the 20-table Kantatsu nine-lens layout in
  `US-20210396972`. The official PPUBS text identifies smartphone/cellular-phone use, binds ten
  numerical-data examples to surface/asphere table pairs, defines ω as half angle of view, and
  publishes f/Fno/ω plus K/A4--A16. A hash-verified ownership scan of all 277 remaining generic
  roots matched only this root. Six examples parse deterministically; examples 1--4 retain their
  published split numeric tokens as per-example parser failures.
- Append-only replay retained all ten disclosed embodiments: examples 7 and 9 are
  converted-pending-intake staging candidates; examples 5, 6, 8, and 10 have terminal
  `trace_failed` receipts because full-field real rays did not reach the image surface; examples
  1--4 remain structured parser-review items. No candidate was promoted. The generic document
  bucket changed 277 to 276. Result-set SHA-256 is
  `53ccc5108b5a6e92656adfea1229a4f9438fdb327fecd712f7afedbb80f929bf`; summary artifact
  SHA-256 is `e7696b73b4605faf71aaa50c6ce679a31300beee13fef4293d553f6a3c4a14cb`;
  strict audit is 619/619 with zero corrupt evidence. The after-seventh-layout census SHA-256 is
  `f7f6a3433cc01860d310c8a275619a37621725bcf8519173bc3fb3543d6ed998`; CODE V inventory
  remains zero; 90 focused parser/census/replay/process tests and Ruff pass.
- The eighth source-proven family is the 22-table Corephotonics folded macro-tele layout in
  `US-12399351`. The retained official PPUBS text identifies a folded digital camera for portable
  mobile devices/smartphones and publishes five lens systems with 37 disclosed operational
  states. Systems 200, 220, 230, and 240 each publish one infinity-conjugate prescription with
  explicit EFL, F number, and Half FOV. Their remaining 24 states publish finite object distances,
  which the current infinity-conjugate replay model cannot represent. System 290 labels its
  whole-system focal token only as `F`; the official text does not define that token as EFL.
- A hash-verified ownership scan of all 276 remaining generic roots matched only
  `US-12399351`. A broader `EFL`-only probe also touched `US-20230132659`, but official evidence
  shows that document uses `F/#`, diagonal FOV, and QT1 surfaces; tightening the signature to the
  exact published `F number + Half FOV` header excludes this different parser family. Append-only
  replay retained all 37 states: the four infinity/EFL prescriptions are converted-pending-intake
  staging candidates with real IMH, while the 24 finite-object states and nine undefined-`F`
  states remain explicit deterministic parser rejections. No candidate was promoted.
- The generic document bucket changed 276 to 275. Result-set SHA-256 is
  `07e1ebda99d49d480c96bd5260e894c5e26386d2aef2b6672d4f0303d00cd795`; summary artifact
  SHA-256 is `ab03151b90e11e695088881ad147f906df6f896a1425a57a4dac511b65ca603b`;
  strict audit is 619/619 with zero corrupt evidence. The after-eighth-layout census SHA-256 is
  `371074751bc28244c286a019cd276b0761fe1d8d789397311bcf3664cc676668` and contains 275 roots
  across 161 normalized signatures; CODE V inventory remains zero; 93 focused
  parser/census/replay/process tests and Ruff pass.
- The ninth source-proven family is the ordinal-header NEWMAX residual layout in
  `US-12510730`, `US-12510732`, and `US-12535652`. Their retained official PPUBS text publishes
  nineteen ordinal-bound surface/asphere pairs with exact f, Fno, and full FOV, explicitly defines
  HFOV as half the maximum FOV, and places exactly one Stop in each complete prescription. The
  first and third roots explicitly identify mobile-device/mobile-phone applications.
- A hash-verified ownership scan of all 275 remaining generic roots matched only these three
  roots. Fourteen of nineteen embodiments parse deterministically. Example 2 in `US-12510730`
  and `US-12510732` starts at surface 2 after the object row in the retained official source;
  examples 2, 4, and 5 in `US-12535652` print `fdter` where the filter row label is required. All
  five remain per-embodiment parser rejections without renumbering or OCR repair.
- The first bounded replay exposed four `patent_budget_exhausted` items; an append-only retry with
  the same request identities and unchanged 120-second worker hard limit raised only the cumulative
  per-patent budget. A transient three-bucket USPTO `ConnectError` on `US-12535652` was then retried
  by exact root state. The final latest results contain ten converted-pending-intake staging ZMX
  candidates with real IMH, four terminal `trace_timeout` receipts, and five structured parser
  rejections, with zero source or budget retry state. No candidate was promoted.
- The generic document bucket changed 275 to 272. Result-set SHA-256 is
  `06a3d4b592f5842c54ae702d08cd309c22e0b9a1c8f255e6364ffa6ede89b669`; summary artifact
  SHA-256 is `9c6014d5468c4b03dd6669e1e206676dac0e3c9a398d17643b8b70f8b87fd0fd`;
  strict audit is 619/619 with zero corrupt evidence. The after-ninth-layout census SHA-256 is
  `999b0487e8ce7a1844cc8478baa8383a9c856021d7cb9f59252ede41dcbbf24c` and contains 272 roots
  across 158 normalized signatures; CODE V inventory remains zero; 105 focused
  parser/census/replay/process tests and Ruff pass.

## Completion condition

The quick is complete only when the 294-item before census is reproducible, implemented layouts
are source-proven and regression-tested, targeted replay and full audit pass, no metadata field
regresses, and the next largest measured failure bucket is recorded. Parent saturation remains
incomplete.
