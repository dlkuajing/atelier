# Family 94050343 source audit

`US-20260072245-A1` is application `19/023962`, filed 2025-01-16 with priority to
`CN202411281039.5` on 2024-09-12. The exact USPTO HTML identifies Takashi Sugiyama as inventor
and Jiangxi OFILM Optical Co., Ltd. as applicant. The retained document has 131 sequential
paragraphs, claims 1-20, FIGS. 1-18, 17 tagged table blocks and eight four-lens prescriptions.

## Prescription reconciliation

TABLES 1a/1b through 8a/8b bind one-to-one to the eight lens/aberration figure pairs. Each
surface table publishes F, FNO, FOV and TTL, an object row, numbered surfaces 1-14, materials,
refractive indices and Abbe numbers. TABLE 9 reconciles system ratios across all eight examples.
The source uses a 588 nm reference for index/Abbe values, 950 nm for lens focal lengths, and
925/950/975 nm for the reported aberration plots.

Surfaces 1, 2, 6, 7, 8 and 9 are aspheric. Every coefficient table publishes nonzero A3, A5 and
A7 on surfaces 8 and 9. Paragraph 82 calls A3 cubic, A4 quadratic, A5 quintic and A6 sextic;
paragraph 83 defines Ai as the coefficient of the ith high-order term. The official PDF visibly
prints the summation from i=3 through i=20. These are therefore genuine odd powers, not an
even-order label convention. `PatentSurfaceInput` and the current CODE V XASPHERE mapping admit
only even powers, so converting them would silently change the published sag function.

The first embodiment has a second independent block: both exact HTML and official PDF page 19
print em dashes rather than Y radii for numbered surfaces 6 and 7. No numeric value is inferred
from the lens drawing and no foreign-family coordinate is borrowed. The other seven surface
tables are complete but remain nonterminal parser reviews until an odd-power surface model and
converter exist.

## Independent source checks

Two official PDF containers have 31 raster-only pages, one embedded image per page. Their
container hashes differ, but all 31 canonical decoded rasters match; the full raster set is
`4f9faea5cc5337619de54ae2a6feed4db2e8724a25408c3940ee8e89389d2b16`.
The nine drawing sheets occupy PDF pages 2-10. Prescription tables occupy pages 19-28 and claims
occupy pages 29-31. The exact Google wrapper restores the summation symbol omitted by the USPTO
MathML but still omits its limits; the official page image supplies those visible limits. Google
exposes no PDF link for this publication.

Google family metadata queues `CN-119200145-A/B` and `EP-4550019-A2/A3`. They are outside the
frozen US cohort and were used only to record the recovery queue. No coordinate, radius,
coefficient, material or system value was imported from them.

## Replay outcome

Append-only attempts 2 and 3 each contain eight `parser_review_required` items and are canonical
semantic-equal after removing only `result_attempt`. No conversion request, worker receipt,
prescription fingerprint, candidate ZMX or formal case was created. The generic summary bucket
falls from 130 to 129 roots/items; strict replay remains 619/619 with zero missing or corrupt
results. This shovel does not make patent/source saturation complete.
