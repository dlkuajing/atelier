# Family 75907839 source audit

## Identity and retained sources

- Root/publication: `US-12554102` / `US-12554102-B2`; application `18/460957`; prior publication `US-20240004164-A1`.
- The retained official USPTO grant HTML is 70,522 bytes with SHA-256 `03f007e37ed2e5c5c084d2f9caede96ec14592a23210cef7f61eb98d52e382c1`. Its normalized text SHA-256 is `b2212f5e81b21872e0df7c9b3fd3eb3afff0b3a81c37d5c515a6e6c1f47734c7`.
- The source identifies Family ID `75907839`, Samsung Electro-Mechanics, five inventors, Korean priority `10-2019-0150653` dated 2019-11-21, and continuation parent application `17/012244`.
- The exact official PDF is 912,850 bytes with SHA-256 `ed9a92d17429eb0422f9e915ac768d0991b8794f307f2eeddc1afd5ff2504359`. It contains 20 image-only pages and one raster per page; the ordered decoded-raster-set SHA-256 is `60e5e5276326d245f3c45d5ad0614a7a8510e0a479120aea91f965aa65eaa97e`.

## Complete source denominator

- The grant contains five claims, with claim 1 the sole independent claim; FIGS. 1-10; TABLES 1-12; one MathML object; and description paragraphs 1-75.
- Description paragraphs 36-42, 43-49, 50-56, 57-63 and 64-70 bind the five optical examples. TABLE pairs 1/2, 3/4, 5/6, 7/8 and 9/10 bind their surface and asphere prescriptions respectively.
- Every example publishes S1-S19, material data at S1/S3/S5/S7/S9/S11/S13/S15/S17 and K plus A-J coefficients for S1-S16. TABLE 11 directly publishes per-example `f`, `f number`, `IMGHT`, `FOV` and `TTL` values.
- Direct TABLE 11 metadata is: `f=(5.426, 5.789, 5.427, 5.658, 5.557) mm`, `f number=(1.483, 1.666, 1.629, 1.763, 1.566)`, `IMGHT=(4.85, 4.85, 4.85, 4.85, 4.85) mm`, full `FOV=(82.744, 78.662, 82.529, 80.291, 81.026) deg`, and `TTL=(7.127, 7.387, 6.700, 6.900, 6.900) mm`.
- The printed S1-S19 thickness sums, including the image row, are `7.129`, `7.388`, `6.701`, `6.900` and `6.899` mm. These source values are retained; TABLE 11 rounding is not used to repair any row.

## Stop adjudication and conversion boundary

- Example 1 prints a standalone, unnumbered `(Stop)` marker between S6 and S7. Paragraph 39 and FIG. 1 say only that the stop lies between the third and fourth lenses. No radius, thickness or axial split of the published S6-S7 air gap is supplied, so no unique stop coordinate exists. Example 1 therefore closes as `metadata_unpublished`; no stop coordinate is synthesized.
- Examples 2-5 print `(Stop)` directly in the S5 row, co-located with the Lens 3 front surface. These four prescriptions are exactly reconstructible and were sent through the isolated conversion worker.
- Example 2 and example 3 reproducibly reach the 180-second worker hard timeout. Example 4 converts to one staging candidate with SHA-256 `4b594e8bbd06b62cfef7a831d00ec07e3cad0acb47e1287188d727339fab7ed5`. Example 5 reproducibly fails because full-field real rays do not reach the image surface.
- The example 4 trace reports a real intercept of `1.9581080012923289 mm` from three of five finite rays. This is pipeline trace evidence, not the published `IMGHT=4.85 mm`; neither value substitutes for the other. The staging candidate is not formal intake and carries no expert backing.

## Raster review boundary

- The contact sheet and original-resolution pages 3 and 15-20 were reviewed. Pages 3-12 are drawing sheets; pages 15-19 contain source tables; page 15 contains the asphere equation and TABLE 1; pages 19-20 contain claims.
- No enhancement, raster-cell transcription, drawing measurement, coordinate recovery or related-family numeric borrowing was performed. The HTML remains the authoritative numeric source, with the original PDF used only to cross-check printed layout.

## Deterministic replay and global state

- Append-only result attempts 2 and 3 used identical 180-second conversion timeout and 1,500-second patent budget. After normalizing only attempt sequence and explicitly segregated runtime lifecycle/diagnostic fields, their business-result semantic SHA-256 is `353f276808ab14acfb8cd9e4b81e4521eb6d496cfe4283d0ad4db59965d46340`.
- Requests, responses, successful candidate ZMX, timeout partial ZMX and stdout are byte-identical. Example 3's second stderr contains one additional duplicated two-line Optiland warning at the cutoff, and process-reaping PIDs differ; those raw diagnostic differences are retained in the determinism artifact and have no outcome effect.
- Final family state is mixed nonterminal: one `converted_pending_intake` item and four terminal items (`metadata_unpublished` x1, `trace_timeout` x2, `trace_failed` x1). There are no formal intake artifacts.
- Strict audit is `619/619`, missing `0`, corrupt `0`; result-set SHA-256 is `95b6f817d78a357f8c1c7bbfbb627117fc7bd81773dd947d440a2f0c42606702`. Two generic residual censuses are byte-identical at 79 roots/items.
- Global saturation remains incomplete. Stable minimum-layout ordering selects Family `21816074`, root/publication `US-4249805` / `US-4249805-A`, next.
