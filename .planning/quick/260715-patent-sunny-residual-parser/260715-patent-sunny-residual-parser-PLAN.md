# Quick: Patent Sunny residual parser

**Status:** complete-largest-bucket-shovel-saturation-incomplete
**Parent:** patent saturation engineering (active / incomplete)
**Started:** 2026-07-15
**Entry evidence:** frozen 619-root replay result set
`ed9087181ff378f73bb3adccab677183915a3f1429b264355ed8cc908735871f` is strict with
missing=0 and corrupt=0. `sunny_embodiment_metadata_missing` is the largest current parser
signature at 199 items; `generic_summary_metadata_missing` is next at 198.

## Objective

Reduce the largest measured Sunny metadata failure bucket using only official retained source
facts and deterministic parsing. Keep every publication/embodiment independent, preserve all
failed attempts append-only, and never infer F-number, field angle, material, or optical cells
from unrelated geometry. A field transform is allowed only when the source itself publishes the
exact defining equation and every operand for that embodiment.

## Plan

1. Recompute the 199-item Sunny census to an explicitly named artifact; do not overwrite any
   historical before/after census.
2. Cluster the current items by exact official Family ID, title, source layout, and current failure
   detail. Select the largest source-proven family rather than generalizing by title alone.
3. Implement only exact layouts whose metadata and prescription bindings are completely published.
   Classify source-proven missing metadata terminally; leave ambiguous/OCR-damaged values
   fail-closed. Do not modify scorers, redlines, or physical thresholds.
4. Replay the selected roots append-only at least twice, verify semantic stability, run the strict
   619-root audit, and write a new explicit Sunny census.
5. Run focused parser/census/replay/process tests with `PYTHONUTF8=1`, Ruff, and `git diff --check`.
   Keep CODE V/codevm inventory at zero before and after every meaningful command.
6. Update STATE, decisions, this plan, and resumable artifacts. Record the next largest measured
   failure bucket. Parent saturation remains incomplete.

## Completion condition

This quick is complete only when the current Sunny census is reproducible, the selected family is
source-proven and regression-tested, repeated targeted replay is stable, the full audit has zero
missing/corrupt results, and the next largest measured bucket is recorded. It does not complete the
parent saturation goal.

## Result

- The explicit before census records 199 Sunny metadata items / 53 roots at result set
  `ed9087181ff378f73bb3adccab677183915a3f1429b264355ed8cc908735871f`.
  Exact Family ID 77932615 is the largest measured family cluster: `US-12078782-B2` and
  `US-20220137337-A1`, each disclosing eight embodiments.
- Retained official raw HTML SHA-256 values are
  `2ceeeedb0c95b9958a372642aa47b06b0be0093d4f740bdabcacc8e6aab7a08e` and
  `c40d066678be0f6fe2a8f592488381f13f611ee8cad7a25b481dee336763ce55`;
  normalized SHA-256 values are
  `33b7f4f716197047a5a2f53227d90a274a0c3af57f94dd839b4b3f855fdcb997` and
  `42e843b251d6b8caf8bec222638338249583e171a77ab3e4809924e717b614bc`.
  Both bind application 17/509745, the same sixteen source tables, the A1-only `TABLE I` label,
  the official `Sphericai` non-numeric typo, and the exact P1/P2 folded-coordinate rows.
- TABLE 16 publishes `f x tan(Semi-FOV)` as
  `5.12, same, 5.12, 5.76, 5.12, 5.12, 6.15, 5.12`; the prose defines Semi-FOV as the maximum
  semi-field and publishes EFL/Fno for every embodiment except the blank embodiment-5 EFL. The
  parser therefore uses only `degrees(atan(published_product / published_EFL))` for embodiments
  1/3/4/6/7/8. Their reconstructed sanity image heights reproduce the exact published products.
  It does not derive embodiment 5 and does not flatten embodiment 2's two mirrors/signed coordinate
  reversals.
- Each root now has eight independent results: embodiments 4/8 are
  `converted_pending_intake`; 1/3/6/7 are terminal `trace_failed` because the unchanged real-ray
  gate reports full-field rays did not reach the image surface; 5 is terminal
  `metadata_unpublished.configuration_effective_focal_length_and_numeric_semi_fov_absent`; and 2
  remains an explicit folded-coordinate parser gap. Across both same-application publications this
  is four staging conversions, eight trace failures, two metadata terminals, and two parser items.
  Nothing was promoted to the formal library.
- Replay attempts 3/4 are append-only. Receipt paths/hashes differ by retry identity, as designed;
  after removing only result-attempt, conversion-attempt, and receipt-reference identity, the
  stable result hashes are
  `d8604ce0d93bbb466dc5f170407e578f103272d2a1984fb191c24c8b44e10dd6` and
  `1dfd9e2b1e8f6b89b400d40f163bde8057a96bf166e9b69588d3dd85dbc68974`.
- The strict full-pool audit remains 619/619 results with missing=0 and corrupt=0. The reproducible
  after census is 187 items / 51 roots, SHA-256
  `a07909c51a957a5e9d4793e58ff0c6e72438d2b3df809040848799d1b9e1d3bf`;
  two consecutive builds are byte-identical. Current result-set/summary/report SHA-256 values are
  `8e5f3b0edc386a7cfe21a4ab66f37189c9a25064bce6d6204f76ac72a92e5b5e`,
  `6d6f73c3920c868dc4e9474c3ceeb184740e5ec64bd91b303e1a0952abb8dc4b`, and
  `0bea580148a5df6f49d5a70344105288cbc09b5737bbccf3845764a564fa5d7e`.
- 230 focused parser/replay/census/process/saturation tests pass with `PYTHONUTF8=1`; Ruff and
  `git diff --check` pass. CODE V/codevm inventory stayed zero. The next largest measured parser
  bucket is `generic_summary_metadata_missing` at 198, followed by Sunny at 187. Parent patent
  saturation remains active and incomplete.
