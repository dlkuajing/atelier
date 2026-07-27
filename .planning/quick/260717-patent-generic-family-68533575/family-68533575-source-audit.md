# Family 68533575 source audit

## Bound source and identity

- Frozen root: `US-20230418018`; exact classification publication: `US-20230418018-A1`.
- Retained USPTO source: `data/patent-lake/uspto-ppubs-html/US-PGPUB/9a102bfef5cf345b/US-20230418018-A1.html`, 63,517 bytes, SHA-256 `9a102bfef5cf345b7b9325fce5915f82664a8db583b31f1f03175ed3b235de57`.
- Application `18/139799`, Family ID `68533575`, filed 2023-04-26 and published 2023-12-28.
- Title: *Imaging-Based Transmitter for Free-Space Optical Communications*.
- Applicant: University of Central Florida Research Foundation, Inc.; inventors: Christopher Kyle Renshaw and Sajad Saghaye Polkoo.
- Related-data chain: continuation of application `16/417464` (later `US-11668893-B2`), which claims provisional `62/673410`; this application's later grant is `US-12147086-B2`.

The exact-source classifier binds both the raw document hash and normalized-text hash. It also binds title, application, family, applicant, inventors, related-data markers and section hashes; any drift fails closed as six parser-review items rather than preserving stale terminal classifications.

## Complete denominator

The official source has contiguous paragraphs `[0001]` through `[0077]`: background/summary 1-10, drawing description 11-25, and detailed description 26-77. Claims 1-20 are cancelled and claims 21-33 are active. The HTML has no table block. It contains exactly three MathML objects (`MATH-US-00001`, `MATH-US-00001-2`, `MATH-US-00001-3`) and declares 20 panels: FIGS. 1, 2, 3A-3C, 4-9, 10A-10B, 11-12, 13A-13C and 14A-14B.

The 29-page publication PDF contains one cover page, 20 drawing sheets (PDF pages 2-21) and eight specification pages (22-29). Two official downloads and the exact Google wrapper PDF decode to the same raster at every page position (29/29). All three containers are raster-only. The contact sheet and full-resolution pages 11, 12 and 15-21 are retained. The exact page hashes and container hashes are recorded in `family-68533575-raster-audit.json`.

## Six disclosed items

1. Paragraphs 26-52, FIGS. 1-7 and active claims 21-33 disclose emitter/detector arrays, electronic and optical pixel controllers, beam splitter, fast-steering mirror, waveguide and grating variants around a generic imaging lens assembly. They disclose no ordered optical surface coordinates.
2. Paragraphs 54-55 and FIGS. 8-9 disclose an OLED/monocentric performance model. Targeted OCR and visual review of PDF page 11 confirms `EFL = 12 mm`, `F/# = 1.5`, and a power budget (48 μW electrical, 6 μW optical, 225 nW received, 11 nW background, 90 pW noise). This is a performance table, not a prescription: surface radii, thicknesses, glass identities and ordered surfaces are absent.
3. Paragraphs 56-59 and FIGS. 10A-10B disclose row/column addressing and beam/iFOV pixel clustering electronics only.
4. Paragraphs 60-61 and FIGS. 11-12 report a laboratory demonstration with an unidentified commercial 50 mm camera lens and measured divergence. No commercial lens model or coordinates are published.
5. Paragraphs 62-67 and FIGS. 13A-13C report results for a comparable 50 mm F/1.8 rectilinear model. The source expressly states that the prototype Canon prescription was unavailable and that lens 6 of `US-8427762-B2` supplied the model. That other-family source is retained only to audit provenance; none of its coordinates is imported into this publication.
6. Paragraphs 68-75 and FIGS. 14A-14B report a scaled fish-eye performance model from an unnamed ZEMAX database entry. The source prints `an example 1000 FOV` and `EFL=0.732-50 mm`; both anomalies are retained verbatim. No recoverable database identity or ordered coordinates are published.

Paragraph 53 merely introduces the examples; paragraphs 76-77 are closing boilerplate. Thus every substantive detailed-description paragraph and every figure panel is mapped once, with no synthetic coordinate, drawing-derived value or cross-publication prescription borrowing.

## Outcome and replay proof

All six items are source-proven `confirmed_no_prescription` terminals with distinct reason codes. Replay attempts 2 and 3 are append-only, byte-distinct only because `result_attempt` differs, and have the same canonical semantic SHA-256 `661aa6905be1abf88cedb0582ccd830f88070e203c93e44b9f5c23e3af75fe30`. They create no conversion request, receipt, fingerprint or candidate ZMX.

The strict ledger audit reports 619/619 roots, no missing or corrupt results, result-set SHA-256 `7da144baddc8b5dade06f31fd89e0dac674ac7f2f16ba16a71c0005185152187`. The generic residual census moves from 132 to 131 roots/items and is byte-identical across two after snapshots. The deterministic next group is Family `79728600`, root `US-20230132659`, publication `US-20230132659-A1`.

This closes only the frozen Family 68533575 root. Related publications outside the frozen cohort, the remaining parser buckets, staging intake, macro replay support and global patent/source saturation remain open.
