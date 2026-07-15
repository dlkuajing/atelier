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
4. Replay affected roots append-only through the existing process-isolated converter. Keep the
   120-second per-embodiment hard timeout unchanged; when a root discloses enough embodiments to
   exceed the 180-second default cumulative budget, raise only that root budget explicitly and
   retain the budget-exhausted attempt. Successful output remains `converted_pending_intake`.
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
- The tenth source-proven family is the inline Kantatsu surface/asphere layout in
  `US-20210364759` and `US-20220163773`. A hash-verified ownership scan of all 272 remaining
  generic roots matched only these two publications. Both bind narrative example/table numbers to
  exact `f/ih/Fno/TTL/ω` headers, explicitly define ω as half field, print a Stop, and define
  A4--A20. The first root's twelve examples all retain official OCR/numeric damage, including
  split surface tokens, an out-of-bounds printed index, `Step`/`lnfinity`/`Obiect` glyphs, and
  malformed coefficient exponents or labels. The parser does not repair any of them.
- `US-20220163773` publishes eleven examples. Example 1 omits all A20 values in its first two
  coefficient groups and remains a parser rejection. Examples 2--11 parse deterministically. Its
  official rows omit optional source surfaces 16/17 and continue with filter rows 18/19; output
  indices follow the published physical row order without inserting dummy surfaces or values.
- Append-only replay retained all 23 disclosed examples. The ten complete prescriptions produced
  two converted-pending-intake staging ZMX files and eight terminal `trace_failed` receipts; the
  thirteen source-damaged examples remain structured parser rejections. No candidate was promoted.
  The generic document bucket changed 272 to 270. Result-set SHA-256 is
  `3907d3680a24f06b388b158ed8fb286e6ba09bb0c4873fa0bc5b76d3fad9a811`; summary artifact
  SHA-256 is `b108122da32ce2936ebed27a487b87d0e99b217312e127931276b15fbac48cec`;
  strict audit is 619/619 with zero corrupt evidence. The after-tenth-layout census SHA-256 is
  `c7793ae9d0f7ec6c9ba9ac8d0f7642712a78b4ecd5bbc534bb7fb8aa19216b7b` and contains 270 roots
  across 156 normalized signatures; CODE V inventory remains zero.
- The eleventh source-proven family is the four-example Kantatsu six-lens grouped layout in
  `US-20210382275`. A complete 270-root ownership scan matched only this retained official PPUBS
  document. Its narrative binds examples 1--4 to tables 1--4, explicitly defines the header field
  as half field of view, publishes surface 1 as Stop, and defines K/A4--A16 for surfaces 2--13.
  Examples 2 and 3 parse deterministically. Example 1 retains the published split exponent
  `1.183031 E-01`; example 4 publishes no A16 row in its second coefficient group. Neither value
  is joined, inferred, or copied from another example.
- Append-only replay retained all four examples. Example 2 produced one
  converted-pending-intake staging ZMX with real IMH `1.343337673215634` mm; example 3 received a
  terminal `trace_failed` receipt because full-field real rays did not reach the image surface;
  examples 1 and 4 remain structured parser rejections. No candidate was promoted. The generic
  document bucket changed 270 to 269. Result-set SHA-256 is
  `a53e735db0867e6fe352f71b22f1c58b6ca065029a6cd8f942531572a5fd4c1e`; summary artifact
  SHA-256 is `21b3d6c41c34e81df0f355d89d1298ba174ccc6297860b726afc47d31ca7fb33`;
  strict audit is 619/619 with zero corrupt evidence. The after-eleventh-layout census SHA-256 is
  `9bb1f22c42b1915bb0cf95a5429ad7c44b416e2afc61203e1a97b1253a6bdc80` and contains 269 roots
  across 155 normalized signatures; 101 focused parser/census/replay/process tests and Ruff pass;
  CODE V inventory remains zero.
- The twelfth source-proven family is the four-example Kantatsu `f/ih/Fno/TTL/half-field` layout
  in `US-20210364766`. A complete 269-root ownership scan matched only this retained official
  PPUBS document. The narrative binds all four examples to tables 1--4, defines the field as half
  field of view, prints a Stop, and defines K/A4--A16. The parser normalizes only spaces inside
  textual Object/Stop/material-label parentheses; it does not join numeric tokens.
- All four disclosed examples retain official numeric damage: table 1 splits `55.86` into
  `55. 6`, table 2 splits the surface-13 radius into `-13.4 77`, table 3 splits several numeric
  tokens including `1 544`, and table 4 prints `Fno = 2 41`. Append-only replay replaced one
  document-scoped generic failure with four source-hash-bound embodiment parser rejections; no
  conversion ran and no candidate was promoted. The generic document bucket changed 269 to 268.
  Result-set SHA-256 is
  `9149666fd16e422ead35413b1ef271f512f215bba6d025b3d2bda12df77e8182`; summary artifact
  SHA-256 is `79d82a6e804db54e64575667d488533705e988f2942e063c291b97ece5d67be0`;
  strict audit is 619/619 with zero corrupt evidence. The after-twelfth-layout census SHA-256 is
  `842df767c0ca217e16334f4d17dff962d528fcfa2c90e5c497dbe167c1e80d1e` and contains 268 roots
  across 154 normalized signatures; 104 focused parser/census/replay/process tests and Ruff pass;
  CODE V inventory remains zero.
- The thirteenth source-proven family is the six-example Kantatsu layout in
  `US-20210373296`. A complete 268-root ownership scan matched only this retained official PPUBS
  document. Its narrative defines the field symbol as half field of view and binds examples 1--6
  to tables 1--6, but every table header publishes only `f/Fno/ih/TTL`; no per-example half-field
  value is present. The parser explicitly refuses to derive the missing angle from `f` and `ih`.
- Append-only replay replaced the one document-scoped generic failure with six source-hash-bound
  embodiment parser rejections stating that the published half-field value is absent. No
  conversion ran and no candidate was promoted. The generic document bucket changed 268 to 267.
  Result-set SHA-256 is
  `49332a57b7888eda04118ab704c042a56a27de66cdfc46fd04630a70176d4e49`; summary artifact
  SHA-256 is `0389de238a252f7fa9ea0832e44a1adc90ee4c8079d8745ac287a2268f36400d`;
  strict audit is 619/619 with zero corrupt evidence. The after-thirteenth-layout census SHA-256
  is `56d2836382bad8321a3d24e3418af4ff94175ced5fe1f9dd73c2e36693d0f5d6` and contains 267 roots
  across 153 normalized signatures; 107 focused parser/census/replay/process tests and Ruff pass;
  CODE V inventory remains zero.
- The fourteenth source-proven family is the four-example Kantatsu layout in
  `US-20210396957`. A complete 267-root ownership scan matched only this retained official PPUBS
  document, whose SHA-256 is
  `9b970512355845fe334608f7850c37c952153e6600f2775493f858cf1477f71a`.
  Its narrative defines f, Fno, half field, and ih, and binds examples 1--4 to tables 1--4, but
  each source table header retains five numeric positions while the ih/Fno/half-field labels are
  absent. The parser refuses to bind those positions by order or infer their identities.
- Append-only replay replaced the one document-scoped generic failure with four source-hash-bound
  embodiment parser rejections stating that the published ih/Fno/half-field labels are absent.
  No conversion ran and no candidate was promoted. The generic document bucket changed 267 to
  266. Result-set SHA-256 is
  `53652aa9fbad3a49960de0736c8415df00f5df919bb2d8934278dac245c40dc5`; summary artifact
  SHA-256 is `3e37d32bac8d69dc04b84877e9008e61def1b66451bba0b02003e988c40a19b6`;
  strict audit is 619/619 with zero corrupt evidence. The after-fourteenth-layout census SHA-256
  is `7b15036db05a82a178f0608395c4de692ea50a15ffd724843aa89539c1e922e2` and contains 266 roots
  across 152 normalized signatures; 110 focused parser/census/replay/process tests and Ruff pass;
  CODE V inventory remains zero.
- The fifteenth source-proven family starts from `US-20210373295-A1`, whose retained official
  PPUBS HTML SHA-256 is
  `371d425dcf4161259f4f6373c5597b9069e99641100d1f7f781a6dbb106a9f8d`. The A-publication
  exposes four examples but embeds prescription tables 1--4 as five TIFF objects. Anonymous
  official PPUBS exact-application search resolves `US-11947087-B2`; that grant has the same
  application number `17/391819`, its Prior Publication Data explicitly names
  `US 20210373295 A1`, and its retained HTML SHA-256 is
  `9563226c2a8ee53f7b532892296df7f358c63516f248e89924654740541cfc95` with all five tables
  in text. No parent-application prescription or OCR value is substituted.
- The recovery executor now activates only for A-publications containing official embedded TIFF
  objects. It requires exact application-number equality, an exact grant-to-publication binding,
  and more textual tables in the grant. It retains the original A-publication, actual B2 parser
  input, and a deterministic linkage manifest (SHA-256
  `df96b7466024d290aaf46906d99ceb8e922d150c985ff14af67bd43354d16d36`) as distinct evidence.
  The new exact five-lens parser binds four table/example pairs, published f/ih/Fno/TTL/half-field,
  Stop, surfaces 1--11 plus published filter rows 18/19, and K/A4--A20 without repairing tokens.
- Append-only replay converted all four disclosed examples to staging-only ZMX with distinct
  fingerprints. Two consecutive process-isolated replays produced identical conversion-request
  and ZMX hashes for all four examples. No candidate was promoted; intake duplicate, quality,
  physical-reasonableness, and routing gates remain pending. The generic document bucket changed
  266 to 265. Result-set SHA-256 is
  `11d5f4378e74f939ac30aafe9a3909d1e47f2158e8d893e26def74be2301412e`; summary artifact
  SHA-256 is `79b27b43d5c0e5442ed5af292027079ec462480a28a230c8407a74506704e09f`;
  strict audit is 619/619 with zero corrupt evidence. The after-fifteenth-layout census SHA-256 is
  `8ef8d4c1064e37471b459adba7090c22d3f740834adf060e80b0c6c37726589c` and contains 265 roots
  across 151 normalized signatures; 99 patent parser/replay/process tests and Ruff pass; CODE V
  inventory remains zero.
- Source-proven terminal classification was added for three exact publications found by a complete
  265-root ownership scan. `US-12591117-B2` and `US-20260160982-A1` each publish five S1--S19
  prescriptions but disclose the stop only as somewhere between the second and third lenses, with
  no axial coordinate; their ten embodiments are now `metadata_unpublished` instead of parser
  review. `US-20130301136-A1` contains 78 coating/material/transmittance tables and no surface
  prescription, so its document item is `confirmed_no_prescription`. Two append-only replays
  retained stable terminal payloads. The generic bucket changed 265 to 262; result-set SHA-256 was
  `f3d5fa1655ed38a75190d3c6d47278b415abb685730caec5c8008a5d7c37b3e6`; the after-source-terminal
  census SHA-256 is `d1536c901baf58bf28b35b6d5c0713151a6aac897b01af59eff4ffafcafa01dd`.
- The sixteenth executable layout is the 23-table Samsung even-order family in
  `US-20240036290-A1` (official PPUBS SHA-256
  `6580ff97379aaf56b60649bd30522972b43027a7f0084316bcb802b7cc4d31d2`). A complete 262-root
  ownership scan matched only this publication. Its source binds ten surface/asphere table pairs,
  explicitly defines HFOV as half field, publishes S1--S19 with S4 as Stop, and labels K plus every
  even asphere order from 4 through 30 for S1--S16. Published HFOV values, including 85.x degrees,
  are retained exactly rather than heuristically halved.
- Official application-number search for `18/096148` returned only the A1. Its first asphere table
  prints the continuation header as `S9 S10 S1 S12 ...`, so embodiment 1 remains a source-bound
  parser rejection without rewriting `S1` to `S11`. Embodiments 2--10 parse exactly. The initial
  180-second replay retained its budget-exhausted items; two subsequent append-only replays used a
  1200-second cumulative root budget while preserving the 120-second worker limit. Both complete
  runs produced identical item states, all nine request SHA-256 values, and the three staging ZMX
  hashes: e5 `aebdcf3000f2669a9d73e869fc2297b0f8e19145557bf2280ea7856f4de72d82`, e6
  `38d8edbfd2e623774bc88711432948751135f9fe4b8f44d3ccdba25ba139e247`, and e9
  `36b94831ef9ef7d5fcce229522b85661701e37126aca74be6f15837739a1fc7e`.
- The latest Samsung result contains three `converted_pending_intake` items, five terminal
  `trace_failed` receipts, one 120-second `trace_timeout`, and one parser rejection. No candidate
  was promoted. The generic bucket changed 262 to 261. Current result-set SHA-256 is
  `f527823e4ff73f146a70ca67f6ff45750712f9aa6dbc6a2692583c61cf0e3bc0`; summary artifact SHA-256
  is `bbf2d414d4728d8341346cd09421a4cc1e62a41aeecfff024bdaf137b3c1c933`; after-sixteenth-layout
  census SHA-256 is `94e48368a74e0a6f96d7e7e927c693207afa869442121c15b6c4da8d2ccb992e`.
  Strict audit remains 619/619 with zero corrupt evidence; 104 parser/replay tests and Ruff pass;
  CODE V inventory remained zero before and after both full replays.
- The seventeenth executable layout starts from image-only Ability publication
  `US-10684452-B2`. Official PPUBS HTML declares the exact FIG. 2A/2B/5/7 prescription
  drawings but contains no table text. The official USPTO PDF is a 16-page raster document;
  its generated PDF wrapper changes `/CreationDate` between requests. The Google citation PDF
  is accepted only after every decoded page raster is pixel-identical to the official PDF. The
  PDF workflow therefore retains both raw PDFs, every official page-image SHA-256, key-page OCR
  tokens with coordinates/confidence, tool versions, and canonical parser JSON. No OCR token is
  repaired or filled by an LLM.
- OL1 remains a per-embodiment parser rejection because FIG. 2B does not independently classify
  every asphere cell. OL2 publishes a complete 19-surface spherical prescription and exact
  `F=2.32`, `FNO=2.82`, `FOV=170`; deterministic conversion uses half-field 85 degrees and
  produced one staging-only candidate with real IMH `3.53289981438067` mm, fingerprint
  `00c779a7ac5b42a4`, request SHA-256
  `110e974769178b2efb84247d9508c7ff1eb5aa7e03c5e446988ace69d9422184`, and ZMX SHA-256
  `c1ada4f996ee9a2ebfa14b0e8bd2dedd5421c3fdb41570cd4ef8fc441a1a9750`.
- The first two PDF replay manifests exposed the dynamic USPTO wrapper hash. Recovery now writes
  an immutable, hash-checked source pin after the first exact-image linkage and reuses that frozen
  PDF pair instead of refetching it. Append-only attempts 4 and 5 have identical parser-input SHA
  `8b54de447644363c03ac4c5f392fa36fc8d35cfc8a0786b4d25b4684c077c148`, recovery-manifest SHA
  `0c3938f1ee10005e94654f7945132fca54214099fb4d1f02a3ec5561403428e6`, request/fingerprint,
  item states, real IMH, and ZMX hash. The replay evidence type now distinguishes official
  PDF/OCR parser JSON from recovered PPUBS HTML.
- Generic summary changed 261 to 260. Current result-set SHA-256 is
  `ffc0667f7ba18c2e10520c9258c33fd05f9d5c0fd5629b30ae6b363e2ffdf63b`; summary artifact
  SHA-256 is `a88087b1dba696497c7e6567925983d6057485c8f29316c2799f1c2951bb697a`; the Ability after-census
  SHA-256 is `a891746e53826bc3b6e35ec75ab9c828c5c3be7b6abe987dfadd81cc9d73e673`.
  Strict audit remains 619/619 with zero corrupt evidence. The focused parser/replay suite is
  110 passed, the offline CODE V guard suite is 5 passed, full Ruff and `git diff --check` pass.
- The remaining Ability subfamily was measured from the 16-root largest normalized signature.
  `US-11231565-B2` has one image-only FIG. 2 surface table and one FIG. 3 asphere table. Its
  official PPUBS HTML SHA-256 is
  `836b4c2bd3c50743d2ba5324fe9f69e3c75b52d0ab1ca4b408010a78141e4183`; it binds the two
  figures to one prescription, defines F/FNO/FOV symbolically, and contains zero numeric
  assignments to those three system values. The 11 official USPTO page rasters are pixel-identical
  to the Google OCR-overlay page images. FIG. 2/FIG. 3 are pages 4/5; neither the overlay text nor
  independent coordinate OCR contains an F, FNO, or FOV label. Corrupt optical OCR cells remain
  unparsed and no value is inferred from geometry or tracing.
- A second canonical Ability profile now retains the official HTML hash, exact source-statement
  counts, all-page image hashes, both PDFs, key-page OCR tokens, and tool versions. The frozen
  official/mirror pair is source-pinned after first exact-image verification. Parser input SHA-256
  is `d05273c2316a54a59dcd552f3ba06f9251204c0777ac720a3cce11076b2d71a0`; recovery-manifest
  SHA-256 is `cea92a4169691a6cf0e2df325e32ec3ba09a279028ebcdc82bcb58d85f723917`.
  Any page/role/count change or possible system-value label fails back to parser review. The sole
  disclosed item is therefore source-proven
  `metadata_unpublished.system_f_fno_fov_values_absent`; no conversion worker or ZMX is created.
- Append-only attempts 2 and 3 have identical parser/manifest/source hashes, terminal payloads,
  and canonical result SHA-256 (excluding the attempt sequence)
  `ab0ab85962d09522082da0b7ac08f920a69f34db48520d9d598b9c9d7b62b242`.
  Generic summary changed 260 to 259. Current result-set SHA-256 is
  `96978077e26ccf694c1e69fa132ba50fd0df37d125224ceae3e8951907426eec`; summary artifact
  SHA-256 is `72245fe68b29f43e2cfd36afde03096a7d4caadd3115fa4f91e120e275d6184d`; after-census
  SHA-256 is `6aafc95f17dcf45fab27134cf9bc84eaa7e60733e8866bd27b5f3d0082cecbba`.
  Strict audit remains 619/619 with zero corrupt evidence. The focused parser/replay suite is
  114 passed, the offline CODE V guard suite is 5 passed, full Ruff and `git diff --check` pass;
  CODE V inventory is zero before and after replay/testing.
- The third Ability PDF profile is source-bound to `US-11175479-B2` (official PPUBS HTML SHA-256
  `71e2de18fc731e17525617401999d416cc86864d16a0fe6cf69506f3e73a3e18`). The source binds
  OL1--OL3 to FIG. 4A/4B, 5A/5B, and 6A/6B and publishes their F/FNO/full-FOV values in FIG. 7.
  The official and OCR-overlay PDFs have 15 pixel-identical decoded page rasters; combined surface/asphere
  tables are pages 6/7/8 and system metadata is page 9. Recovery retains all source/page hashes,
  coordinate/confidence tokens, source figure counts, and the unchanged 0.99 optical-number gate.
- F/FNO/FOV columns parse deterministically, but the first unresolved source cells are OL1 S3's
  refractive-index token, OL2 S3's conic token, and OL3 S3's curvature token. Each is present below
  the confidence gate or is not independently classified; no sign, decimal, infinity glyph, or
  material value is repaired. The three disclosures remain parser-review items rather than a
  false terminal or conversion. No worker, request, receipt, or ZMX is created.
- Append-only attempts 2/3 preserve parser-input SHA-256
  `1abbdbbb7912ea30e5399e1c558485aa31676d1e5c0d866f6f2f73f2a17038dc`, recovery-manifest
  SHA-256 `3337dff42164d2d6607b161a4c4bd364af12b07027faa027536dd4c38b40e7c3`, and canonical result
  SHA-256 (excluding attempt sequence)
  `b670da254846fc3972db6324dc1e5a21f574df088c92535d209f879e50a1a1cf`.
  Generic summary changed 259 to 258. Current result-set SHA-256 is
  `478a3b2e9013d5f4fc202763fe3c9d9a467b3af67949f8fd8a07165ccfa96258`; summary artifact
  SHA-256 is `aaa47670730ea5603b9a591beb3047fa6e045d3ee5a5d04c1f0bf8515f8c7125`; after-census
  SHA-256 is `4857e660c31aa19d869874a2a1d0320a4ca2110e8edf589e64cd349738278e8c`.
  Strict audit remains 619/619 with zero corrupt evidence; 118 focused tests, 5 CODE V guard tests,
  Ruff, and `git diff --check` pass with CODE V inventory zero.
- The fourth Ability PDF profile is source-bound to application publication
  `US-20200201001-A1` (official PPUBS HTML SHA-256
  `8321e4c6f37bd824e18092ace74a133e967009ce32db252b5248269e2630efc6`). Exact source counts
  bind FIG. 3A/3B and 4A/4B once each and FIG. 5 twice. The 12-page official and OCR-overlay PDFs
  have pixel-identical decoded rasters; pages 4/5 publish two five-lens surface/asphere tables and
  page 6 publishes exact `f/Fno/FOV` columns. Synthetic complete fixtures recover both 16-surface
  prescriptions at `(2.1, 2.0, 70.0)` and `(2.5, 2.0, 55.0)` using full-FOV divided by two.
- The retained real OCR remains fail-closed per embodiment. OL1 does not independently locate the
  printed stop label (`1S`, confidence 0.844495); OL2 first fails at the S11 infinity glyph token,
  whose confidence is 0.964980 and therefore does not clear the unchanged 0.99 optical-number
  gate. No label, infinity glyph, sign, decimal, material, or coefficient is repaired. Both items
  remain parser review and launch no conversion worker or ZMX.
- Repeated recovery exposed that `pypdf` can emit a TIFF container with one nondeterministic padding
  byte even when decoded pixels are identical. Hashing those container bytes caused false linkage
  failures and non-reproducible page hashes. Recovery now compares decoded raster shape/dtype/pixels
  and hashes the canonical `decoded-page-raster-v1` preimage. A lossless multi-encoding regression
  test proves container bytes may differ while page identity remains equal. Three actual recoveries
  produced identical parser SHA-256
  `ab762093159604b48db94723ca579173f14cf9009257575b6869c6770ba4d3de`.
- Append-only attempts 2/3 preserve the same two-item payload after removing only
  `result_attempt` (SHA-256
  `e613cbb07458e2ace72a8512bcadb3fa5ff6625239f6e721403969886f3e6473`) and recovery-manifest
  SHA-256 `28ba9fc4994dd5e08eb9f31dbc8300839ff95d7e7b69fc3461b4278474b925fb`.
  Generic summary changed 258 to 257. Current result-set SHA-256 is
  `a81589742414e9ab982fd02e21bbff17a6bf4cfa094935a4a492d5269ed7eea3`; summary artifact
  SHA-256 is `e29f5e059eaa422e2dca2542d5062c1ab76a1e862de6c86fa02a148ecb41769e`;
  after-census SHA-256 is `95d070bf7b5149c475b9927b1ae5e1bc5490ae884cd65c53bcc8cbea39382769`.
  Strict audit remains 619/619 with zero corrupt evidence; 124 focused parser/replay tests, Ruff,
  and `git diff --check` pass with CODE V inventory zero.
- The corresponding grant `US-11768354-B2` is not treated as an independent optical source. Its
  official PPUBS HTML SHA-256
  `b54234c78c881767f36db6f1c4eae08d64f41e5dace70bc3f74fc4bd9f664901` contains a unique
  Prior Publication Data entry for `US-20200201001-A1`; both official documents publish exact
  application number `16/683826`. The new inverse same-application path fetches that A-publication,
  reuses its pixel-verified PDF/OCR evidence, and writes a parser payload whose candidate identity
  remains B2 while its source-publication identity remains A1. The recovery manifest binds both
  official HTML hashes and refuses missing/ambiguous prior-publication or application-number links.
- Real B2 attempts 2/3 retain the same two source-bound OCR failures as the A-publication and create
  no worker, request, or ZMX. Their canonical result SHA-256 after removing only `result_attempt` is
  `6a205da6f64f476a07dba5c1c2fdf8c52b607aebe3c4bc77b7896467fa94a646`; linked parser SHA-256
  is `0ef3e2001fbb26398661c6c4890d75b9ece7626244c4646caf884d5f80fe0f3b`; recovery-manifest
  SHA-256 is `119a8ba8c86d49fa321e2359d51ff53a62ddf794851e5e7f057044954653a83d`.
  Generic summary changed 257 to 256. Current result-set SHA-256 is
  `bde5ef2636d8499475a02a0168440de0556963d114427d9c95c0df7c9c80a84a`; summary artifact
  SHA-256 is `8147f4836c85f5d3379e7623cd82ef85b8d0782f8179ef5bb5d43a55c2fae86a`;
  after-census SHA-256 is `c4e665e12e5db7bcb43b51a6840c0a7fec4a41932cf4e74ce13b5012df479a15`.
  Strict audit is 619/619 with zero corrupt evidence; 127 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- The next measured optical root inside the largest 14-root zero-table signature is
  `US-10690884-B2`, not the signature's unrelated barcode/UI/calibration documents. Official PPUBS
  HTML SHA-256 `de49a99af89787c46d4a08689739f916033ee5fe4748d145ed3eb640cc9222a0`
  binds OL1 to FIG. 4A/4B, OL2 to FIG. 5A/5B, and both systems to FIG. 6. The 13-page official and
  OCR-overlay PDFs have pixel-identical decoded rasters; the two prescription pages are 5/6 and
  system page is 7.
- FIG. 6 publishes F, TTL, and full FOV columns but no FNO, F-number, or F/#. Those labels occur
  zero times in official HTML, all three retained overlay pages, and independent coordinate OCR.
  Each disclosed optical lens is therefore terminal
  `metadata_unpublished.system_f_number_absent`; corrupt surface/asphere cells are deliberately not
  parsed, and no focal or aperture value is derived from geometry.
- Append-only attempts 2/3 have identical canonical result SHA-256
  `f423dea72bd0d4ac86ef06dc9a8009df5fccb7d6923a84afe57507333bcbdd72`, parser SHA-256
  `ba5076be6cf606d7bc96c46cc12a94714c93781445da6bd331fae76c7f464dae`, and recovery-manifest
  SHA-256 `4f480901783d4e1b5aadcf483f98235dd7b1c8dfe2992eea2824bf95a0adac53`.
  Generic summary changed 256 to 255. Current result-set SHA-256 is
  `ddf8aa92aa0e10a8d0be4d9c26f592d29b41a5964f0a94d339c131314433c28c`; summary artifact
  SHA-256 is `1645bf2b3daeff0366ac2cc14d6db55508bbea25092cde708197596fb6304043`;
  after-census SHA-256 is `9ce366aa248bbe5e720910a6e1a2fd286b3dd4346566185b75d7bc8bb0e5bd58`.
  Strict audit is 619/619 with zero corrupt evidence; 131 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero and no worker/ZMX for this root.
- The next source-proven optical root in that heterogeneous zero-table signature is
  `US-10809497-B2`. Official PPUBS HTML SHA-256
  `a4776865cc4bf356f17d6648922065957c134be2d6db92d035423d79c8993490` binds four
  prescriptions: OL1 FIG. 2A/2B, OL2 FIG. 4A/4B, OL3 FIG. 6A/6B, and OL4 FIG. 8; FIG. 9 is their
  published property table. All 14 official/mirror decoded page rasters are pixel-identical, with
  key pages 3/4/6/7/8.
- FIG. 9 publishes focal lengths, curvature radii, and ratios but no FNO, F-number, or F/#. Those
  labels occur zero times in official HTML and both retained OCR views. The profile therefore
  records e1--e4 independently as terminal
  `metadata_unpublished.system_f_number_absent`; it does not parse damaged prescription cells,
  derive aperture from geometry, launch a worker, or create ZMX.
- Append-only attempts 2/3 have identical canonical result SHA-256
  `6aeaae4372e276e13bd2b02893d0b4086bb21c4212d14cf59b5b5cd024143a24`, parser SHA-256
  `88e33380711f36f0b86086814041a12201b7a2625406e7a6622256da6b0e09ed`, and recovery-manifest
  SHA-256 `a77d47c8ea3ab7d0adbb4bb343b1396217d01b2f659778709db6eac3bc1e48e0`.
  Generic summary changed 255 to 254. Current result-set SHA-256 is
  `85cb7850bbf805c01aa1528f3ada7bd337aed3eb82a1d67b8188ecd0a7259053`; summary artifact
  SHA-256 is `bf11224997c6a8d11f7bffa569bf7165b3aebba942be2dd2994a04ab903fe32e`;
  after-census SHA-256 is `31e2d1e72a50baa50e3162894bab16b272cc8ee5bd12326f5d3336efa9270ce8`.
  Strict audit is 619/619 with zero corrupt evidence; 135 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- The next largest measured signature contains 13 actual optical prescriptions. The first
  source-proven root, `US-12449639-B2`, binds exactly one Prior Publication Data record,
  `US-20220137372-A1`; both official records publish application `17/577825`. The A-publication
  official HTML SHA-256 is
  `ea81961d51b85e34fae9da57ff9b11c2de92fc3da1079b6cb9e8096ea85c08a7`. Exact source counts
  bind FIG. 7--13 once each. All 21 official/mirror decoded page rasters are pixel-identical; pages
  8--14 retain three surface tables, three asphere tables, and TABLE 7 metadata.
- The Largan profile parses 3/3 complete cross-checked fixtures into 14-surface prescriptions and
  uses published HFOV directly. It also makes grant recovery robust when a grant has no mirror PDF:
  direct recovery failure is retained until the exact same-application A-publication succeeds, and
  still fails closed when that prior path is absent or invalid.
- Real e1/e2/e3 remain independently rejected at unchanged gates: stop thickness `-0.295` has
  confidence 0.989782 below 0.99; surface 4 radius `100.00000 (ASP)` has confidence 0.981783 below
  0.99; surface label `11` has confidence 0.919665 below 0.95. No token, sign, decimal, coefficient,
  or surface label is repaired; no worker or ZMX is created.
- Initial attempt 2 is retained append-only. After error evidence was made token-specific, attempts
  3/4 have identical canonical result SHA-256
  `5d9791f834be88a01e4366a4d6dee40cb22a079374e219ab98389ba3571d7f45`, parser SHA-256
  `dc1d887aef56dbb30932099eb93460b50e8f29d93a9e480cf5742f0b30c3456b`, and recovery-manifest
  SHA-256 `7434873655a3d4ad12d981b0637e9e61fc1ba323e1af7901bd1be0348faae5d6`.
  Generic summary changed 254 to 253. Current result-set SHA-256 is
  `1625eb8c803dcc9775115f422f2bc3190e570b6c248f15c31fe11a21cc1bb3a7`; summary artifact
  SHA-256 is `0338d0e34b6ce95d6d16876909a96340a77c0730a6d01566d3e5e5643b9f9202`;
  after-census SHA-256 is `09ddad25aeeb79f2e18d4f99d8c1d8ad5ea9ad96f9a4a5b1e72ea74f32c0892a`.
  Strict audit is 619/619 with zero corrupt evidence; 138 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- Exact-title source census identified `US-20160305871-A1` and `US-10724947-B2` as one
  surface-texture machine-vision camera/illumination family, not smartphone lens prescriptions.
  Both official documents have zero PPUBS tables and identical structural counts: seven occurrences
  of `vision system camera assembly`, one catalog-like 105 mm focal length, one 1 mm axial spacing,
  four semi-reflecting-mirror mentions, two structured-illumination mentions, and one FIG. 10
  alternate-architecture description. They contain no curvature-radius, surface-number, Abbe,
  asphere-coefficient, or F-number marker.
- The narrow classifier requires every one of those counts and rejects any prescription marker.
  Both roots are terminal
  `confirmed_no_prescription.surface_texture_acquisition_architecture_only`; no optical numeric
  value is interpreted, no worker or ZMX is created. Attempts 2/3 are stable: A1 canonical result
  SHA-256 `2d6a805fcbc5ac5a43e2b9786bb271af2203e37671978e1225030b418593677e`; B2 canonical result
  SHA-256 `3b694b3f1309ee48e80e3e114bcdeb0b6e7e32e121ccaf8b709d2564cfcbe81e`.
- Generic summary changed 253 to 251. Current result-set SHA-256 is
  `7e72eb412ea5c4c28d25cbe9c2c8e407421c8307de4045bc62fead610bb76442`; summary artifact
  SHA-256 is `508766426d48d4c0fcef9a926ced3f28d44e1904344898aeb85818f6ec6eaf7b`;
  after-census SHA-256 is `4ede47182c669058962d214e004c0c39fc5ace182a466e22725905ba6107d982`.
  Strict audit is 619/619 with zero corrupt evidence; 140 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- Exact application-number and Prior Publication Data bindings partitioned four Ability zoom roots
  into two families: application 17/331960 (`US-20210373301-A1` / `US-12541082-B2`) and
  application 17/364515 (`US-20220066127-A1` / `US-12321034-B2`). Each official source binds
  FIG. 3 telescopic, FIG. 4 wide-angle, FIG. 5 asphere, and FIG. 6 system metadata. The latter
  grant uses the exact same-application A-publication because its direct grant mirror has no OCR
  text layer; its retained 15-page source manifest proves decoded-raster identity.
- The `ability_zoom_two_state_census_v1` profile retains both disclosed states independently and
  validates variable `S1..Sn`, one `STO`, final `IMA`, and material-cell pairing without changing
  the 0.95 label or 0.99 numeric confidence gates. All eight state records fail closed on actual
  OCR evidence: application 17/331960 at S15 Abbe token `72` confidence 0.841798, and application
  17/364515 at surface label `S8` confidence 0.942588. No coefficient cell is split or repaired,
  and no worker or ZMX is created.
- Append-only attempt 2 is retained, including the initial document-scoped FIG. 5 binding failures
  for the 17/364515 family. Attempts 3/4 are stable after the binding correction. Their per-root
  canonical result SHA-256 values are `7e6d874e88c34af518eada50713be1faa7415899ba58fa5d8788ba7032853b8a`,
  `394cfd34494c77948d342eac77b46022f0546b0652ad89ee123c7a285f698f93`,
  `e4a219a3ac9423a27c4357a29030660ff5a1a9306d54ff17fbd184edc5e9198e`, and
  `ed81411f42c0f3177b747ccf990ec1e2acdf99db43d5d89c22db291fd7058133` in root-list order.
- Generic summary changed 251 to 247. Current result-set SHA-256 is
  `76b0f1eab60a5f997f4c2558d703e4e1009d704f9b85ada0b5b83e293dfdf3df`; summary artifact
  SHA-256 is `08352cd4bc835a4a6cc8e4b50bc0b68c3faa1f5837df99b87b99c8ab321f3330`;
  after-census SHA-256 is `4f96268ea235205fdae177e90beff4e8ac9d19f49a6a809342cedf836322b5a8`.
  Strict audit is 619/619 with zero corrupt evidence; 143 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- The largest 12-root normalized layout was not treated as one parser family merely because all
  titles were Genius. The first exact source family, `US-20170097490-A1` (official HTML SHA-256
  `0211f3fe1bdd3152ab6c57c25e4991603504980b37398c9ae5cbcb9812c43dea`), uniquely binds eleven
  optical-data figures, eleven asphere figures, and FIG. 46's comparison table for all eleven Fno
  values. This proves eleven disclosed embodiments rather than one document-scoped failure.
- The retained 66-page official PDF SHA-256 is
  `bc7c5e69d66788055add6e305596fd1e172abba355736d581b9cab082b82d2d9`; the Google overlay
  SHA-256 is `e7597fe7ee2f76e7912ff6df00844252f4859420d62a7862623c11178839c0b3`.
  All decoded page rasters are pixel-identical. The parser retains 23 key pages; overlay text is
  blank on key pages 17, 21, 33, and 45, so coordinate RapidOCR is the only independent text view
  there. FIG. 46's three Fno rows pass the unchanged gates.
- `genius_four_lens_eleven_embodiment_census_v1` retains all eleven embodiments separately. Every
  one remains fail-closed on source-specific optical/asphere evidence: corrupt or below-0.95
  `Surface#`, `Radius`, surface-ID, or coefficient labels. No OCR token is repaired, the profile
  does not claim numeric-cell parsing is complete, and no worker or ZMX is created.
- Attempts 2/3 have identical canonical result SHA-256
  `ad9c4e484a6bb0a4eb37d4fa85295956a5cde3cde5c340420ed595f27be4085e`, parser-input SHA-256
  `a30e48af334c8f8ae3d18c78f5086fa9b81c41728a0da1104a710e5587916c22`, and recovery-manifest
  SHA-256 `bb0ac8d6bbd05395764b1d988c6646b2713b2d0ea6b1614c342331925fda2e00`.
- Generic summary changed 247 to 246. Current result-set SHA-256 is
  `427df235546c80de9d61f28bd8ce76d56fa6320a859f47706e7464142f29bd7a`; summary artifact
  SHA-256 is `85c42e3b64e97403d25197eb9bebb397223bec14fb0af2ff2c55040b599956aa`;
  after-census SHA-256 is `99a285cf0c66e3d956eeb2abc95d472e338fd24b4f5fdf40e8500db445db68d2`.
  Strict audit is 619/619 with zero corrupt evidence; 145 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- Exact official source markers bind `US-12429676-B2`, `US-20240369810-A1`, and
  `US-20260009980-A1` to five optical-data figures (9/13/17/21/25), five asphere figures
  (10/14/18/22/26), and comparison FIGS. 27/28. The grant uniquely links application
  18/661719 to prior publication `US-20240369810-A1`; all three retain key PDF pages
  6/7/9/10/12/13/15/16/18/19/20/21.
- The first two recovery manifests retain a Google overlay whose decoded page rasters equal the
  official PDF. Google exposes no citation PDF for `US-20260009980-A1`, so that publication uses
  the distinct `uspto_official_pdf_coordinate_rapidocr` manifest: no overlay field, no raster-pair
  equality claim, immutable official-PDF source pin, canonical official decoded-raster hashes, and
  coordinate OCR only. Tests cover pin hash/path enforcement and the absence of false overlay
  claims.
- The exact five-embodiment profile expands all three document failures into 15 independent
  parser-review items. Actual source defects include below-0.95 `a2` labels, `Fn0`/missing `Fno`,
  below-gate drawing-sheet headers, and damaged fifth-embodiment metadata. No token or number is
  repaired, no worker or ZMX is created, and attempts 3/4 are canonical-equal per root:
  `eb4f30b28caa7db19b1aae46d6a0f34ccdf70680ad8e038ba19dfeb7e630d511`,
  `84af31b9ee352ebfff4f0dd8a557580978cfb255b50068c5f95fa94d39f8cb43`, and
  `f4b6004426880b37084f244e6f8c138ab3e8cc14c2d08db27111e805e78214f5` in root-list order.
- Parser-input SHA-256 values are `3f8cedfe3c90789e29d29b13d348c2845b53c55439f87c1f1c806aed5c6da835`,
  `ed05c7f5667a4b9d2e89f53bf9474cb4e58e55075a4c29404b06cc5150abda66`, and
  `f2abfb250dbb1d11a5c642648ff3ddeca17fe1615937ab6febd2e5e4c776d6b5`; manifest SHA-256
  values are `824075c7952e0d97b03357fa8420b659415a12e97a8815a6f97a9350f10ff309`,
  `93657b6017f910d7856db926310409e1cfe814780e3e50a6b2ad9685f6f7aca2`, and
  `6f404c3880bacc64982f8cad5b0dce77f6fd7d15134e109223adf096df5f50d2`.
- Generic summary changed 246 to 243. Current result-set SHA-256 is
  `24859a64abff52418fcf9731315a53b10933112a689d76f547f1df0a01fb8b9b`; summary artifact
  SHA-256 is `894fd534d0983b926221687a9ed9b645247c1be0071f6df8b100c67d750faded`;
  after-census SHA-256 is `3e8c99734063df5252beb42d223e4969bf939ba6670fbda8b89212976919ff2d`.
  Strict audit is 619/619 with zero corrupt evidence; 148 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- `US-12461345-B2` and `US-20260036791-A1` each bind nine optical-data figures
  (9/13/17/21/25/29/33/37/41), nine asphere figures (10/14/18/22/26/30/34/38/42), and
  comparison FIGS. 43/44 exactly once. Their independently recovered official PDFs retain the
  same key pages 6/7 through 30/31 plus 32/33, with 32 drawing sheets; the grant has 50 total
  pages and the continuation publication has 51.
- Neither publication currently exposes a Google citation PDF. Each therefore has its own
  immutable `uspto_official_pdf_coordinate_rapidocr` source pin and manifest, with no overlay
  field or pair-equality claim. The official PDF SHA-256 values are
  `e7e1bee02c6b844550a5bae736151f8742f2846db703e6211dcce31ba310b7cc` and
  `54281507d1181daa49cef509c5c4fdb569b77b1d3442a1af90f64a2ebae9b4c3`.
- Both roots expand to nine independent parser-review items. Actual failures include below-gate
  drawing-sheet headers, `a2`/`a4`/`a8`/`K` label damage, missing ninth-embodiment TTL in the
  grant OCR, and missing ninth-embodiment EFL in the A1 OCR. No number is inferred or repaired;
  no worker or ZMX is created. Attempts 3/4 are canonical-equal with result SHA-256 values
  `ed15555cbac0f44388b1e132f558901c20daba303c2ae51361671806b584805f` and
  `070424ce498ed6d3564ace216b28ca7a6e425192d34351706c99550e8b22d7cc`.
- Parser-input SHA-256 values are `0b26adba7e4c54f2e3c188ec82362f3634313fc61e6427a39cf00ac44bba2ac8`
  and `ace0aa7d53dd10987ae4c49249d522118a2ad1f65ab1933e95dd1555a943f597`;
  manifest SHA-256 values are `06e8de243d85ea73e0035a651b07eceb6631142cd8ee522917a18aecbaaa9241`
  and `c68538933c3cfc63080bc700ea7b995614f1544e02c41dbeb829fc26074cf2ee`.
- Generic summary changed 243 to 241. Current result-set SHA-256 is
  `b65b39ad10343f95b0326b81b57ca24cc8050828d4551cfa498a556aa7681d17`; summary artifact
  SHA-256 is `ade8078358a5b864366314c35d24688cbd776f9f9bac17c0fb9b32357d238977`;
  after-census SHA-256 is `40ce630375c346f58405b73fc974bc9dc150479e7b27e23195ba1c3d5bc42912`.
  Strict audit is 619/619 with zero corrupt evidence; 150 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- `US-20260186249-A1` and `US-20260186250-A1` independently bind nine optical/asphere figure
  pairs (FIG.9/10 through FIG.41/42). Their exact official descriptions differ (`shows` with an
  official `nineth` spelling versus `illustrates`/`invention`), so they use separate closed
  profiles rather than an inferred family rule.
- The retained official-only PDFs prove distinct layouts: the first has 48 pages, 33 drawing
  sheets, prescription pages 6/7 through 30/31, and comparison pages 32/33/34 (FIG.43/44/45);
  the second has 50 pages, 34 drawing sheets, the same prescription pages, and comparison pages
  32/33/34/35 (FIG.43/44/45/46). Official PDF SHA-256 values are
  `304718c5f381d798203624ab62639d92d12652432e59c4c14470d58869649ea4` and
  `0bfc19465b92ffec2d2846b4e0f6c8565898d9036abce6c2a680822ae1a14986`.
- Google Patents returned 404 for both publication pages at recovery time. The manifests therefore
  use `uspto_official_pdf_coordinate_rapidocr`, omit an overlay, and make no decoded-raster-pair
  equality claim. A first 64-second batch diagnostic produced no output and was discarded; the
  successful split-page and formal runs are the only evidence counted.
- Both roots expand to nine independent parser-review items. Actual failures include below-gate
  sheet headers, missing exact `LCR`/`TTL`/`EFL`/`Fno` prefixes, and damaged `a2`/`a4`/`a6`/`a8`/`K`
  labels. No numeric repair, worker, ZMX, or promotion occurs. Attempts 3/4 are canonical-equal;
  result SHA-256 values are `cfe21c3e73276db2d952b611a3bf4a70185ee17944292b867e93be055d738357`
  and `3436ba5157113ba699d090a53388349ae0495101503a7f64d4800940d3b297c7`.
- Parser-input SHA-256 values are `4d5daf62585d9f2a51b14d15a1af3ad24cfb55340ea25724b7746c5379c99560`
  and `457170bdec39a7ec0683bc282abbf76392bf53e8a75aed0aef236804afc73c9e`;
  manifest SHA-256 values are `dd20221675f40eda03cf04c876ac865dafa10bf119babed8a6c30333e10e58a6`
  and `fabd647f260cd92fd7284c5eb0c4092f2c1b85d9d8f3d6a8d9a0de8a6d79f2c4`.
- Generic summary changed 241 to 239. Current result-set SHA-256 is
  `7bdd16ec9286daa78629b30c46f59023eb9d6ae8fc1298a34d740899236b0f8b`; summary artifact
  SHA-256 is `4426f2acab96696f862669cd74ef3e0513c2a6ebb02a58400b14d35288989121`;
  after-census SHA-256 is `225d06105090ce35407a8320edb1dea2eb747e8de11a492d2a4fc925a4281d56`.
  Strict audit is 619/619 with zero corrupt evidence; 154 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- `US-20260186247-A1` independently binds nine four-lens optical/asphere pairs (FIG.8/9 through
  FIG.40/41) plus comparison FIGS.42-45. Its retained official-only PDF has 47 pages and 33
  drawing sheets; optical pages are 5/8/11/14/17/20/23/26/29, asphere pages are
  6/9/12/15/18/21/24/27/30, and comparison pages are 31/32/33/34.
- The old four-lens eleven-embodiment profile is not reused: this source uses constant surface
  labels 15/16 through 95/96 rather than embodiment-prefixed labels. A first formal pass exposed
  that every asphere page contains two real `Surface` headers; the new profile's deterministic
  cardinality was corrected from all nine official pages before attempts 3/4, eliminating that
  false failure without changing any confidence threshold.
- All nine items remain parser review because of actual below-gate sheet headers, `HFOV`/`Fno`/
  `EFL`/`Material` labels, and `a4`/`a6` asphere labels. No number is inferred or repaired; no
  worker, ZMX, or promotion occurs. Attempts 3/4 are canonical-equal with result SHA-256
  `da7192bdf0bf21093144d8bd50a647785337d8b62736dc70b34dbb3542f531c9`.
- Parser-input SHA-256 is `0f698cbe3812f4d4c522a8ece7abf3248780b814498c76416641f3fd763af0fb`;
  manifest SHA-256 is `02ba2ce7eed84fd6dcfbb6cedb89ed27a95135335b39c114015726c82fccbc79`;
  retained official PDF SHA-256 is
  `85e7c155c897fdc5869d1c1c6d3722c8f8082efe81028ef981f68c27e92a7594`.
- Generic summary changed 239 to 238. Current result-set SHA-256 is
  `ecf14c32f005e5ecefa446107b03bbc4ab6aa027702091c3e0d30141f6e9281b`; summary artifact
  SHA-256 is `c28bbe655fe2dc9937c358902d09ad5999ee2298b8909ae63e7187a82968520d`;
  after-census SHA-256 is `076a35c6007825b5a216dcaea96253cadeb049e3d1233ef8ca04d4672d19d943`.
  Strict audit is 619/619 with zero corrupt evidence; 156 focused parser/replay tests, Ruff, and
  `git diff --check` pass with CODE V inventory zero.
- Verification incident: an unfiltered host-wide `pytest` command included a marked
  `real_machine` target-standard smoke and launched `D:\CODEV115\codev.exe /B
  atelier_codev_target_A.seq` plus `codevm.exe`. The pytest/CODE V process tree was terminated
  immediately after detection and both inventories returned to zero. The current `codev.rec`
  contains only startup/exit commands but its timestamp does not bind it to this event, so it is
  not treated as an execution receipt. A corrected `pytest -m "not real_machine"` run kept CODE V
  at zero under repeated monitoring but hit the outer 1200-second tool limit without a pass/fail
  result; it is recorded as no conclusion, not PASS. PR CI remains the eventual full-suite gate.

## Completion condition

The quick is complete only when the 294-item before census is reproducible, implemented layouts
are source-proven and regression-tested, targeted replay and full audit pass, no metadata field
regresses, and the next largest measured failure bucket is recorded. Parent saturation remains
incomplete.
