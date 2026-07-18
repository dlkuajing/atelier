# Family 97226532 source audit

## Identity and retained sources

- Root/publication: `US-20260063870` / `US-20260063870-A1`
- Application: `19/085529`; Family ID: `97226532`
- Title: `IMAGING LENS SYSTEM`
- Applicant/assignee: Samsung Electro-Mechanics Co., Ltd.
- Inventors: KIM Hyuk Joo, SON Ju Hwa, CHAE Kyu Min, JO Yong Joo
- Priority: KR `10-2024-0121066`, 2024-09-05
- Retained USPTO HTML: 85,686 bytes, SHA-256 `200d56a3a5dbf4913e37af18d64f3ea90dbf8c9e738cd9fb93af19a316a16b34`
- Official PDF: 1,209,670 bytes, SHA-256 `767eb5435ef8860b0932c85328f7469071426da5776788ee5630806aa456ed12`

## Complete source denominator

The retained HTML has 119 consecutive numbered paragraphs, 20 claims in three independent claim families, FIGS. 1–14, 17 tagged tables, 24 MathML objects, and no embedded image tags. Paragraphs 82–116 bind seven optical prescriptions to TABLES 1–14 and FIGS. 1–14. TABLES 15–17 contain consolidated system values and conditional-expression data; they do not disclose an eighth prescription.

Each prescription contains exactly S1–S19. S9 is the stop, S17/S18 are the filter faces, and S19 is the imaging plane. Material rows are S1, S3, S5, S7, S10, S12, S13, S15 and S17. TABLES 2/4/6/8/10/12/14 bind the asphere coefficients to their corresponding surface tables. Equation 1 directly defines K and A–H as the conic and even-order r4–r18 terms.

TABLE 15 directly publishes seven values each for focal length, F-number, image height, full FOV and TTL. Full FOV is 138.4 degrees for all seven prescriptions, so the pipeline half-field is exactly 69.2 degrees. Published image height is 9.252 mm for all seven. No system value is inferred from a raster, another family or a different prescription.

The surface-thickness sums close to each published TTL within 0.0002 mm. The fifth and sixth prescriptions retain source-published S19 spacings of -0.0257 mm and -0.0097 mm; these values are not repaired or clamped.

## PDF/raster reconciliation

The official PDF has 28 image-only pages with one decoded raster per page. Pages 2–15 are drawing sheets, page 20 carries Equation 1, and pages 21–27 contain the prescription/system tables. The ordered decoded-raster-set SHA-256 is `5255d947d50c94f9aa3df2b8fbaa67ec18737edc49a0a1454288cccedd636581`.

The 28-page contact sheet and original-resolution pages 3, 20 and 21–27 were reviewed. No enhancement, geometry measurement, numeric derivation or raster-cell transcription was used. The 18/36/54/72 degree labels in the FIG. 2 performance plot remain plot sampling labels and do not replace TABLE 15 metadata.

## Parser and conversion boundary

The source-locked parser verifies the exact raw and normalized documents, identity markers, section hashes, paragraph spans, all table payload hashes, claim/figure/MathML denominators, Equation 1 and the absence of embedded images before parsing an item. Any source drift fails all seven items closed.

With an explicit 1,500-second patent budget and 180-second per-worker hard limit, replay attempts 3 and 4 produce the same outcome:

- Embodiments 1, 5, 6 and 7: `converted_pending_intake`, with receipt-backed candidate ZMX files.
- Embodiments 2, 3 and 4: terminal `trace_failed`; full-field real rays did not reach the image surface.

All seven request JSON files, all seven response JSON files, all available candidate ZMX files, stdout logs and stderr logs are byte-identical between the two runs. Result semantics are equal after normalizing only append-only attempt identifiers/paths and receipt runtime fields (`retry_number`, `elapsed_seconds`). No outcome or request/response field is removed.

The four generated ZMX files are candidates only. Their pipeline-reported real intercepts are not substituted for the source-published 9.252 mm image height, and none is formal intake or expert-backed production evidence. The other three items remain receipt-backed trace failures; no coordinate repair or alternate tracing convention is introduced.

## Ledger outcome

- Root state: `mixed_nonterminal`
- Source items: 7/7 represented
- Candidate conversions pending intake: 4
- Terminal trace failures: 3
- Formal intake: 0
- Generic residual census: 83 → 82 roots/items
- Strict replay: 619/619 roots, corrupt results 0
- Result-set SHA-256: `a3ea07b45a20998531cfbde9489f387a47e819bc9d3dc5e10e5ae24adbdc8a4a`
- Next stable generic group: Family `82818661`, root `US-20260056353`, publication `US-20260056353-A1`
- Global saturation remains incomplete.
