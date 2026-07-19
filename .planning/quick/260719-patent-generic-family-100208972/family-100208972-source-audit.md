# Family 100208972 source audit

## Identity and authority

The retained USPTO Patent Public Search publication is `US-12663617-B2`,
application `18/786504`, Family ID `100208972`, titled *Folded camera lens
designs*. It names Rudnick, Dror, Goldenberg, Shabtay and Bachar as inventors
and Corephotonics Ltd. as applicant and assignee. The 170,886-byte official
HTML is the content authority and is pinned at
`7659bdaf0b85b0754e4d388e51a81dcb525e8048781ce1855007962f0927e696`.
The patent is a continuation of application `16/604009`, which entered from
`PCT/IB2019/053662`; the metadata also identifies parent patent `US-12078868`
and prior publication `US-20260029623-A1`. No numerical value was borrowed
from a related application or publication.

## Complete source denominator

The source has 122 numbered paragraphs. Background/Summary contains one
cross-reference paragraph `(1)` followed by its own `(1)` through `(14)`, an
explicit section-local duplicate rather than a missing or silently repaired
number. Description then runs continuously from `(1)` through `(107)`:
paragraphs 1-21 declare the figures and paragraphs 22-107 form Detailed
Description. Claims are numbered 1-21, with claim 1 the sole independent
claim. Description paragraphs 2-21 declare 20 panels: FIGS. 1A-D, 2A-B,
3A-B, 4-13 and 14A-B. The HTML contains 33 flattened `TABLE-US` objects,
zero HTML `<table>` tags and nine outer MathML objects. Every section, source
span, claim, figure declaration, table payload and MathML object is pinned in
the exact derived profile and `family-100208972-source-facts.json`.

Paragraph 54 explicitly says that detailed optical and surface data are
given for ten lens/lens-assembly examples, Ex1-Ex10, mapped respectively to
FIGS. 2, 6, 7, 8, 9, 10, 11, 12, 13 and 14. That explicit source statement is
the item denominator. FIGS. 1A-D and camera 100 / dual-camera 170 are known or
context wrappers, not extra current lens examples. FIGS. 3A-B, 4 and 5 define
clear-height/clear-aperture geometry. All are mapped, but none inflates the
ten-item denominator. No paragraph, claim, declared panel, table, MathML
object or disclosed item is left unmapped.

## Prescription and metadata boundary

Each example has a direct three-table block: system summary, ordered surface
table and coefficient table. Ex1 uses Tables 1-3, Ex2 Tables 4-6, through Ex10
Tables 28-30. Tables 31-33 are comparisons and characteristics. The ten
surface tables contain 134 ordered source rows and the coefficient tables
contain 92 coefficient rows. Every example directly publishes EFL, TTL, F/#,
SDL/2 and BFL. Ex1, Ex9 and Ex10 use the published even-asphere equation with
A1-A7 coefficients. Ex2-Ex8 use the published QED_TYPE_1/Q0-Q5 equation with
A0-A5 coefficients. Published basis definitions therefore match their
coefficient orders; no external convention or coefficient repair is needed.

The complete publication contains no prescription-specific numeric angular
field: `HFOV` and `degrees` occur zero times, while the field-of-view/FOV
language is relational Wide/Tele language. A field angle is deliberately not
derived from SDL/2 and EFL. Ex2-Ex8 publish an explicit stop row. Ex1, Ex9 and
Ex10 publish no stop row or axial stop coordinate, and no stop is synthesized.
Consequently Ex2-Ex8 terminate as
`metadata_unpublished.prescription_specific_angular_field_absent`; Ex1, Ex9
and Ex10 terminate as
`metadata_unpublished.system_stop_and_prescription_specific_angular_field_absent`.
No conversion request, receipt, prescription fingerprint, candidate ZMX,
staging ZMX or formal intake item is created.

## Original-raster corroboration

Two official PDF fetches each contain 2,020,213 bytes but have different
container hashes. Each has 34 pages, one raster per page and no text layer;
all decoded page records match exactly at
`b29f8bac77cf96664cc2943a99a0cf9cc2bf4fc5ae3b52e4a4f9790014901221`.
Page 1 is the title page, pages 2-4 references, pages 5-20 drawing sheets and
pages 21-34 specification/claims. Pages 25-33 contain the tables and page 34
contains the claims. All original page rasters and four contact sheets were
retained; original pages 24-34 were visually inspected. They corroborate the
formula boundary, table layout, printed stop evidence and claims. No image
enhancement, drawing measurement, OCR repair or numeric transcription was
used; HTML remains content authority. Exact records are in
`family-100208972-raster-audit.json`.

## Replay and residual queue

Append-only attempts 2 and 3 each produce ten terminal
`metadata_unpublished` items and are business-semantically identical after
removing only `result_attempt`. Strict audit is 619/619 roots with zero
missing or corrupt results. The generic residual falls from 67 to 66
roots/items and both after censuses are byte identical. Stable ordering
selects the minimum remaining exact layout signature for the next family.
Global patent saturation remains incomplete.
