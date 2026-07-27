# Family 44972265 source audit

## Scope and relationships

- Frozen root: `US-8287129`; exact classification publication: `US-8287129-B2`;
  application: `12/784523`; Family ID: `44972265`.
- The B2 identifies same-application prior publication `US-20110285963-A1`. It is not a
  frozen 619-cohort root, so this shovel identifies the relationship but does not claim a second
  root closure.
- Cross-references to `US-20110288824-A1` and `US-20110292505-A1` are sibling publications in
  different families. No conclusion, paragraph, table, system value or coordinate was borrowed
  from them.

## Exact official sources

- Official PPUBS HTML:
  `data/patent-lake/uspto-ppubs-html/USPAT/4b55105484abed1d/US-8287129-B2.html`
  (`165109` bytes), SHA-256
  `4b55105484abed1dba7679fb42270888ef06cbc6362aeefed0db92d5112ab647`.
- Normalized text: `151356` characters, SHA-256
  `b054e605872fb431ef155c206b68c85220440526a3571c79216c424408b4d2df`.
- Official PDF:
  `data/patent-lake/uspto-ppubs-pdf/fd396e2147b34601/US-8287129-B2.pdf`
  (`3346072` bytes), SHA-256
  `fd396e2147b34601029577285fa4396255bf334e163647c56fa9b5c3503e38ee`.
  It has 61 image-only pages, one 2560×3300 raster per page, no text layer and 39 drawing
  sheets on PDF pages 3–41. The ordered decoded-raster-set SHA-256 is
  `ce3c93ccfecf8926ef2f9ba8b42c9d88b9f5ea69436bad4d3cabeb2f28275af2`.

## Complete denominator

The exact text contains 40 Background/Summary paragraphs, 164 Description paragraphs,
25 claims, three independent claim families, 42 declared figure panels, 12 declared table
panels, five equation placeholders and 11 ledger items. The HTML has zero tagged tables,
zero image tags and zero MathML objects; the tables are present only in the official drawing
rasters. All 42 panels reconcile to the 39 drawing sheets and all 12 table panels are located.

The 11 items are defined without circular discovery:

1. First exemplary projection lens: FIGS. 6A/6B and stress table 9A.
2. First exemplary relay lens: FIGS. 6C/6D and stress table 9B.
3. Second exemplary projection lens: FIGS. 10A/10B and stress table 11A.
4. Second exemplary relay lens: FIGS. 10C/10D and stress table 11B.
5. Third exemplary projection lens: FIGS. 12A/12B, stress table 13A and prescription 14A.
6. Third exemplary relay lens: FIGS. 12C/12D, stress table 13B and prescription 14B.
7. Merit-function lens-design method: paragraphs 118–130 and FIG. 15.
8. Glass-substitution lens-design method: paragraphs 131–144 and FIG. 16.
9. Stop-adjacent lens-group imaging system: claims 1–19.
10. Highest-power-density lens-group imaging system: claim 20.
11. Laser projection system: claims 21–25.

Projector/prior-art context, beam profiles and glass tables are support, not independent
prescriptions. MTF/stress panels are bound to the corresponding lens example. The tested
projector of paragraphs 116–117 uses the already-counted third lens pair and supplies no new
prescription. Generalized lens forms and dependent asphere, DOE, compensator, coated-mirror,
cooling, F-theta and zoom features remain within the applicable method or independent claim
family and are not double counted.

## Raster review and terminal boundary

The 61-page contact sheet was inspected. Original-resolution pages 11, 13, 25, 27, 31 and 33
confirm source-labeled lens schematics without any coordinate measurement. Original pages 37
and 38 confirm:

- FIG. 14A contains only `Surface / Radius / Thickness / Aperture / Glass`, object `SCREEN`,
  a stop and image `INT IMG`.
- FIG. 14B contains only `Surface / Radius / Thickness / Aperture / Glass`, object `DLP`,
  an `APERTURE STOP` and `INT IMAGE`.
- Neither prescription sheet contains EFL, FNO, FOV or HFOV labels.

Original pages 39 and 40 contain only the FIG. 15/16 design-method flowcharts. Original page 41
contains the FIG. 17 coated-mirror system layout and no independent prescription metadata.
Page 2 was separately checked and is a cited-reference page, so the drawing-sheet denominator is
pages 3–41, exactly 39 sheets.

The first four examples publish lens counts, shapes, named glasses and performance/stress
evidence, but no ordered surface radii and spacings. They are four distinct
`confirmed_no_prescription` items. FIGS. 14A/14B publish the two complete spherical surface
tables, but the exact HTML and raster sheets publish no prescription-specific effective focal
length, exact system F-number or angular field. The general relay F/6 context, projection
about-F/3 preference and F/2.5-or-faster variant are not exact bindings and are not substituted;
the two prescriptions are distinct `metadata_unpublished` items.

The two flowcharts describe design methods whose outputs would specify designs, while the three
independent claim families describe system architectures; none publishes another numerical
prescription. These five items are distinct `confirmed_no_prescription` items. No raster numeric
cell was transcribed, no coordinate was measured or synthesized, no sibling-family value was
borrowed, and no worker, conversion request, fingerprint, ZMX, intake or CODE V operation was
created.
