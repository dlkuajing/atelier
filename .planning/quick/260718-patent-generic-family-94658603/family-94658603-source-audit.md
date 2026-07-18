# Family 94658603 official-source audit

## Scope

- Root/publication: `US-20260118635` / `US-20260118635-A1`
- Application/family: `19/281010` / `94658603`
- Official retained views: one USPTO Patent Public Search HTML and one USPTO image-service PDF.
- Full source denominator: 115 consecutive numbered paragraphs, 20 claims, 14 declared figures, 13 tagged tables, 23 MathML objects, and 8 disclosed ledger items.

## Reconciliation

The detailed description publishes six seven-lens prescriptions. Each prescription has a 19-row surface table and an eight-row S13/S14 asphere-coefficient table. Each also directly publishes effective focal length, F-number, and full field of view. Paragraph 112 / TABLE 7 compares the six embodiments through ratios including `TTL/ImgH` and `ImgH/F`, but neither official view directly publishes an absolute image height.

The saturation contract forbids deriving missing prescription metadata from ratios. Consequently, prescription items 1-6 are source-proven `metadata_unpublished`; they do not enter conversion, tracing, staging ZMX, candidate ZMX, or formal intake. The image-module wrapper in paragraph 113 / FIG. 13 / claim 19 and terminal-device wrapper in paragraph 114 / FIG. 14 / claim 20 publish no additional optical prescriptions, so items 7-8 are `confirmed_no_prescription`.

TABLE 3a directly publishes fourth-lens `nd=1.437` and `Vd=1.95`. That Abbe value lies outside the repository's existing physical range. It is retained verbatim in the evidence and produces a distinct terminal reason; it is not repaired, inferred, or borrowed from another embodiment.

## Raster audit

The official PDF contains 28 image-only pages with exactly one raster per page and no text layer. Pages 2-8 are seven drawing sheets covering FIGS. 1-14; pages 19-25 are the official table pages; pages 26-28 contain the claims. All 28 decoded page rasters were retained at original resolution, hashed, and included in a full-page contact review. Original-resolution checks covered the cover, drawing/wrapper sheet, representative specification/formula pages, and every table page used for classification.

The raster view independently confirms the source facts relevant to classification: page 21 visibly retains `Vd=1.95`, while pages 24-25 contain TABLE 7's ratio comparison rather than a direct absolute image height. No raster cell was transcribed into a prescription, no geometry was measured, and no enhancement was applied.

## Malformed official expressions

The first asphere expression is malformed in the retained HTML MathML and visibly malformed on PDF page 18. Paragraph 38's `TTL/CT4` inequality is also visibly malformed on PDF page 12. Both are recorded as official-source discrepancies and left untouched; neither is repaired or used to synthesize a candidate.

## Terminal conclusion

The complete eight-item source denominator is classified without inferred optics: six `metadata_unpublished` prescription items and two `confirmed_no_prescription` wrappers. Candidate and formal-output counts remain zero, and CODE V is not invoked.
