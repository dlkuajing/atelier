# Family 51743335 source audit

## Identity and source boundary

The frozen cohort contains one root, `US-9360657`, whose retained publication is
`US-9360657-B2`. The exact USPTO source identifies application `14/520589`, Family ID
`51743335`, inventor Liao Kuo-Yu, applicant and assignee Ability Opto-Electronics Technology
Co., Ltd., filing date 2014-10-22, Taiwanese priority `102139518 A` dated 2013-10-31, and prior
publication `US-20150116847-A1` dated 2015-04-30. Raw and parser-normalized B2 hashes are pinned
independently.

The A1 is live at USPTO and independently reports the same family/application identity, but it is
outside the frozen 619-root cohort. Its HTML and PDF probes are recorded only as source
availability. It is not a parser input and supplies no borrowed coordinate, cell, metadata value,
paragraph boundary or raster truth to the B2 classification.

## Complete source denominator

The B2 contains nine Background/Summary paragraphs and 41 Description paragraphs. Description
paragraphs 1-17 declare FIGS. 1-16; paragraphs 18-27 define the common four-lens architecture,
nine optical conditions and the even-asphere sag equation; paragraphs 28-30, 31-33 and 34-36
bind the first, second and third preferred embodiments; paragraphs 37-41 close the disclosure.
Seven claims and one MathML object are individually hash-bound. The apparent second `(2)` after
paragraph 40 is equation-range prose, not a 42nd paragraph; the classifier finds each section-local
paragraph sequentially and rejects any missing or reordered number.

The HTML contains zero tagged tables. The source instead declares seven image-only tables:
FIGS. 4/5 for the first embodiment, 9/10 for the second, 14/15 for the third, and FIG. 16 for the
three-embodiment comparison. The official PDF has 21 pages, one 2560×3300 raster on every page,
16 drawing sheets on pages 2-17 and no text layer. All 21 decoded raster hashes and the seven key
table-page hashes are pinned. A repeat official wrapper and the Google citation wrapper have
different container bytes yet reproduce all 21 official decoded rasters exactly. The Google
wrapper is missing text on pages 5, 6 and 11, so an independent RapidOCR label pass was also run
on all seven official table rasters; OCR digits are not parser input.

## Three optical items

Each preferred embodiment has four aspheric lens elements in object-to-image order with powers
positive, positive, negative and negative, plus a fixed stop at the first object-side surface and
a filter. The third also has cover glass. FIGS. 4, 9 and 14 publish 10, 10 and 12 ordered
stop/lens/filter/cover surface rows. FIGS. 5, 10 and 15 publish `k` and `A` through `G` for eight
aspheric lens surfaces per embodiment. FIG. 16 directly publishes:

| Embodiment | TL (mm) | Dg (mm) | f (mm) |
|---|---:|---:|---:|
| first | 3.10 | 3.672 | 2.23 |
| second | 3.68 | 4.400 | 2.67 |
| third | 2.49 | 2.876 | 1.75 |

The same table publishes `ct1`-`ct4`, `TL/Dg`, `TL/f`, two thickness ratios, `Nd2`, `Nd3`,
`Vd2` and `Vd3`. `Dg` is explicitly a length of the diagonal line of a maximum viewing angle on
the imaging plane; it is not an angular value.

## Fail-closed representability decision

The complete B2 HTML, all 21 official rasters, the pixel-identical Google text view and the
independent seven-page OCR label census contain no `FNO`, F-number, `F/#`, `FOV`, `HFOV`, field
of view, angle of view or image-height label. A focal length and `Dg` length are not divided or
passed through trigonometry to manufacture an unpublished F-number or angular field. Simulation
plots are likewise not digitized.

The root therefore expands from one generic document failure into three exact-source
`metadata_unpublished.prescription_specific_f_number_and_angular_field_absent` terminal items.
No conversion request, worker receipt, prescription fingerprint, staging/candidate ZMX, formal
intake or CODE V call exists. Any HTML, identity, section, paragraph, claim, figure binding,
MathML, PDF container, page count, page raster or key-table-page drift fails closed to parser
review.

## Replay and queue

Attempts 2 and 3 are append-only and semantic-equal after excluding only `result_attempt`; their
shared semantic SHA-256 is `7c8d31db94e42b39371ef25ec2bb8c649905ee214f0099f46ba83a1cfb8ff199`.
Strict replay remains 619/619 with zero missing and zero corrupt results. Generic summary metadata
falls from 99 roots/items to 98/98, and two fresh after-census builds are byte-identical at
`e922d2d8b004d070b57fb1b22b44f3fbd689d324d48b75dee429eba91661987f`.

Generic remains the largest executable nonterminal root bucket. Stable layout/root ordering
selects Family `89620688`, root `US-20240272407`, publication `US-20240272407-A1` next. Parent
patent saturation remains incomplete.

## Verification

The five focused Family 51743335 tests pass 5/5, the complete `test_patent_to_zmx.py` sweep
passes 563/563, the nine offline patent support files pass 94/94, and the no-real-CODE-V guard
passes 5/5; this is 657 offline patent tests plus five guard tests. Ruff, Python compilation, 37
changed JSON parses, 54 evidence files/469 referenced-record hashes, byte-identical after
censuses, strict 619/619 replay audit, 18 null formal fields, six empty coverage mappings, four
zero-contamination scopes and `git diff --check` pass. Final CODE V process inventory is zero.

The new replay changed the global summary/report hashes. All 24 prior evidence files that refer
to those global artifacts were mechanically relinked before the first complete 563-test main
sweep, which passed without a stale-evidence retry.
