# Family 62524045 exact-source audit

## Identity and scope

- Frozen root: `US-10775589`; retained publication: `US-10775589-B2`; application:
  `16/101621`; Family ID: `62524045`.
- Title: *Camera optical lens*. Applicant: AAC Technologies Pte. Ltd.; assignee: AAC Optics
  Solutions Pte. Ltd.; inventor: Rongbao Shi.
- Filed 2018-08-13. The retained B2 identifies `US-20190196146-A1` as its prior publication and
  Chinese application `2017 1 1415992`, filed 2017-12-25, as its foreign priority record.
- Official HTML SHA-256:
  `c6d4c09d9645c9d874c1fea89c865b1b98b4abc40ecc9607fbefa3dffd62a8ac`.
  The raw/normalized/section/table hashes are source-locked in `scripts/patent_to_zmx.py`.

## Complete denominator

- Background paragraphs: 1-2. Drawing-description paragraphs: 1-5. Detailed-description
  paragraphs: 6-62. Claims: 1-5.
- Declared and located figures: FIGS. 1-4 on two drawing sheets. FIG. 1 is the four-lens/filter
  layout; FIGS. 2-4 are longitudinal aberration, lateral color, field curvature and distortion.
- Formal tables: Tables 1-6, all located on official PDF pages 5-6.
- Formal optical embodiments: one. Ledger items: one. There is no second embodiment, exclusion,
  merge or silent remainder.
- Official PDF denominator: six pages: cover page 1, drawing sheets pages 2-3, specification pages
  4-6 with printed column numbers 1-6, and claims on PDF page 6/printed column 6.

## Prescription reconciliation

- Table 1 directly publishes system focal length `2.618 mm`, lens focal lengths `f1`-`f4`, and
  combined focal lengths `f12` and `f123`.
- Table 2 publishes the stop, radii `R1`-`R10`, axial distances/thicknesses `d0`-`d10`, four lens
  refractive-index/Abbe pairs, and the filter refractive-index/Abbe pair. The table contains three
  explicit infinity markers.
- Table 3 publishes `R1`-`R8`, each with conic `k` plus `A4`, `A6`, `A8`, `A10`, `A12`, `A14` and
  `A16` (eight numeric values per row).
- Tables 4 and 5 publish eight inflexion-point rows and eight arrest-point rows. Table 6 publishes
  four focal-length ratios, direct TTL `3.589 mm`, and direct `IH/TTL = 0.682641404`.
- Paragraph 61 directly publishes entrance-pupil diameter `1.247 mm`, full-field image height
  `2.297 mm`, and diagonal vision-field angle `84.00°`.
- The retained official HTML, both official raster containers and their Google-equal page rasters
  contain no `F-number`, `FNO`, `F/#` or numerical-aperture value. Computing `f / pupil diameter`
  would manufacture an optical value and is prohibited. Therefore the sole item is
  `metadata_unpublished.system_f_number_absent`; no conversion request, receipt, fingerprint,
  candidate or ZMX is emitted.

## Raster and mirror audit

- Independent official downloads are 350555 bytes each with different container hashes but
  equal decoded rasters on all 6/6 pages.
- The exact Google PDF is 523032 bytes and has a text layer, while its embedded decoded page
  rasters equal the official publication 6/6. Google is retained only as a discovery/cross-location
  mirror; official HTML and official rasters remain optical truth.
- The all-page contact sheet and full-resolution PDF pages 5 and 6 were visually inspected. Every
  declared figure, table, prescription row and claim is present; there is no image-only additional
  prescription or hidden table.

## Family and saturation boundary

- `US-20190196146-A1`, `CN-108169877-A/B` and `JP-2019113821-A`/`JP-6564113-B2` remain queued
  outside the frozen cohort. They are not borrowed for the B2 terminal outcome.
- Attempts 2 and 3 are append-only and semantic-equal after excluding only `result_attempt`, at
  `5b8491a60d65e84b7dd4d7c28e2ff56a3ebcec71a35f217ccceda863ec36376b`.
- Strict replay is 619/619 with corrupt=0. Generic falls 134→133 roots/items. Deterministic ordering
  selects Family ID `61244801`, root `US-11287601`, next.
- External-family closure, all remaining parser buckets, staging intake, macro replay support and
  global source exhaustion remain open. This shovel is not family/source/global saturation.
