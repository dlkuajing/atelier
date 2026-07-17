# Family 61244801 source audit

## Identity and publication relationship

- The frozen root is `US-11287601`; its retained classification publication is
  `US-11287601-B2`, titled `Imaging lens assembly`, Family ID `61244801`.
- The exact application is `16/483973`, filed as PCT application `PCT/US2018/017252` on
  2018-02-07. The source names `WO2018/148301`, US prior publication
  `US 20200096726 A1`, and provisional application `US 62455983`.
- Applicant and assignee are Snap Inc.; inventor is Robert Matthew Bates. The raw official
  PPUBS HTML SHA-256 is
  `7910d5bca19dc438a5ca8b159eb45327adc1e3aff91670babfde68745c4e8fd3`.
- Same-application, national-stage, and continuation publications are outside the frozen
  619-root cohort and remain queued. No outcome or optical value is transferred from them.

## Complete text, figure, table, example, and item denominator

The parser-normalized exact HTML has 55,558 characters. Its complete sections are:

| Section | Normalized position | Length | SHA-256 | Declared range |
|---|---:|---:|---|---|
| Background/Summary | 4,043 | 4,162 | `07a6a280a41ba266a6658838fab14c2ce617112e7fc46a201180861cafb6c256` | paragraphs 1-6 |
| Brief Description | 8,205 | 1,251 | `fd4c69521ac3c8516c4017d1dd46f588a8e1ec8c8fc3bc8b6bbdbbd631bf0d92` | paragraphs 1-7 |
| Detailed Description | 9,456 | 37,264 | `99a04e2c683920b2f36c590e5ce61b97e13505ee2986dda618a76f2391be50f6` | paragraphs 8-87 |
| Claims | 46,720 | 8,838 | `fe21b454dadb02043cdd8ba450c1d843f120542f177c79b693592841cba9d353` | claims 1-18 |

The source declares FIGS. 1-8 and the official PDF contains eight drawing sheets. PPUBS HTML
contains zero formal table blocks because the five numeric/data tables are drawing rasters:

1. FIG. 3: relative-power ranges for the optional six-element architecture;
2. FIG. 4: Sample Design 1 ordered surface/material table;
3. FIG. 5: Sample Design 1 conic/asphere table;
4. FIG. 6: Sample Design 2 ordered surface/material table; and
5. FIG. 7: Sample Design 2 conic/asphere table.

FIG. 8 is a mobile-device/camera-module block diagram. The complete ledger denominator is three
items: two source-named sample designs plus one device wrapper.

The source also declares exactly 37 uppercase `EXAMPLE` records in detailed-description
paragraphs 51-87. They are claim-style dependency chains rather than 37 independently
parameterized prescriptions:

- Examples 1-9 and 10-18 are two alternative independent/dependent formulations of a six-element
  lens assembly. They contain power/material/stop/filter constraints but no additional ordered
  coordinate table, so they reconcile under Sample Design 2's six-element item without moving
  any constraint into its coordinates.
- Examples 19-27 and 28-36 are the analogous two formulations of a five-element lens assembly.
  They contain no additional ordered coordinate table and reconcile under Sample Design 1's
  five-element item without coordinate synthesis.
- Example 37 is the processor/memory/digital-image-storage mobile-device wrapper and maps to the
  third terminal item.
- Issued claims 1-18 repeat six-element constraint groups and mobile-device claims; they do not
  publish another surface sequence and are not counted again.

The exact source contains two internally suspicious statements: Example 24 prints one `dn/dT`
exponent as `10.sup.6`, and Example 36 refers to a sixth element inside its five-element chain.
They are retained as source facts and are not repaired or used as coordinates.

## Prescription and metadata boundary

Sample Design 1 explicitly omits the optional second lens and therefore has five lens elements.
Its raster prescription uses surfaces 1-15 plus the IR filter; aspheres are identified on
surfaces 1, 2, and 6-13. Its conic/A4-A14 grid contains 60 expected exponent-bearing coefficient
cells. The exact-raster Google text view exposes 51 exponent markers, RapidOCR exposes 51, and
RapidOCR joins 15 multi-cell tokens. The official text publishes no Design-1-specific EFL,
F-number, angular field, or image height.

Sample Design 2 includes the optional second lens and therefore has six lens elements. Its raster
prescription also uses surfaces 1-15 plus the IR filter; its conic/A4-A12 grid contains 50 expected
exponent-bearing coefficient cells. The exact-raster Google text view exposes 48 exponent
markers, RapidOCR exposes 33, and RapidOCR joins 10 multi-cell tokens. The exact text directly
publishes EFL `1.57 mm`, assembly length `6.71 mm`, diagonal FOV `115°`, image-circle FOV `120°`,
F-number `2.4`, image height `1.98 mm`, and maximum half field `57.5°`.

Neither design is converted. Joined/missing OCR cells are not split, guessed, interpolated, or
manually transcribed. Both remain
`parser_review_required.deterministic_parser_rejected`. The device wrapper is
`confirmed_no_prescription.electronic_device_wrapper_only`. Thus the root is
`mixed_nonterminal`, with no worker, conversion request, receipt, prescription fingerprint,
candidate, or ZMX.

## Official PDF and independent raster reconciliation

Two independently fetched official containers and the Google container each contain 19 pages,
one embedded 3300×2560 raster per page, and the same 19 decoded raster hashes. The official PDFs
have no text layer; Google's text layer is used only as an OCR view over pixel-identical official
rasters. Page roles are cover 1, references 2, drawing sheets 3-10, and two-up
specification/claims pages 11-19. Claims start on PDF page 17.

All 19 pages were decoded; pages 5-9 were retained separately and inspected at full resolution.
The complete per-page evidence is in `family-61244801-raster-audit.json`. No drawing geometry was
used to derive optical values, and no mirror-only value became source truth.

## Replay outcome and saturation boundary

Attempts 4 and 5 are append-only and semantic-equal after excluding only `result_attempt`, at
SHA-256 `38c9258455e5aba43e85f9a1a235ea1c9d148e47a8234c198ac43a5785331b35`.
Strict audit is 619/619 with zero missing or corrupt results. The generic residual falls from
133 to 132 roots/items; two fresh after censuses are byte-identical.

This shovel closes the document-level generic failure but does not close either optical
prescription. Parent patent saturation, source expansion, deterministic coordinate recovery,
conversion, formal intake, routing, independent review, PR, and CI remain incomplete.
