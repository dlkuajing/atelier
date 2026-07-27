# Family 71121572 source audit

## Identity and publication boundary

- The frozen cohort contains root `US-11467375`, publication `US-11467375-B2`, application
  `16/675252`, and Family ID `71121572`. The retained official source identifies AAC Optics
  Solutions Pte. Ltd. and the two Chinese priorities dated 2018-12-27.
- `US-20200209560-A1` is the same-application prior publication but is outside the frozen 619-root
  cohort. JP, WO, and Chinese priority records are also queued outside the cohort. Their metadata
  and rasters are cross-check evidence only; no external numeric value is borrowed into the B2
  parser.

## Complete source denominator

The exact raw and normalized B2 hashes bind Background paragraphs 1-2, drawing-description
paragraphs 1-13, detailed-description paragraphs 14-147, claims 1-19, FIGS. 1-12, and TABLES
1-13. Three seven-lens embodiments are disclosed. Each ordered prescription has one aperture row,
fourteen lens surfaces, two optical-filter surfaces, and one image row. TABLES 1/5/9 contain the
surface prescriptions, TABLES 2/6/10 the conic and A4-A16 coefficients, TABLES 3/7/11 inflexion
data, TABLES 4/8/12 arrest data, and TABLE 13 direct system and lens-condition values.

The three direct `(EFL, FNO, full FOV, entrance pupil, image height)` tuples are
`(4.925, 1.55, 77.08, 3.177, 4.0)`, `(4.762, 1.55, 78.86, 3.072, 4.0)`, and
`(4.981, 1.55, 76.65, 3.213, 4.0)`. Full FOV is halved only for the parser's explicit HFOV field.
The published aperture spacings are `-0.552`, `-0.513`, and `-0.546` mm; they are preserved
without sign repair or surface reordering.

## PDF closure

Two independent USPTO B2 downloads and the Google B2 wrapper contain 18 pages. The PDF-container
hashes differ, while all 18 decoded page rasters agree. Pages 1-2 are cover/reference pages,
pages 3-9 are seven drawing sheets containing FIGS. 1-12, and pages 10-18 are specification pages.
Tables occupy PDF pages 12-16; claims 1-19 begin in the right column of page 16 and end on page 18.

The same-application A1 wrappers contain 17 pages and agree on all 17 decoded rasters. B2 and A1
have zero equal same-position rasters across the first 17 pages, so pages or numeric cells are not
cross-borrowed between publication wrappers. Full contact sheets plus table and claims-boundary
sheets were visually inspected.

## Replay outcome

The exact parser recovers all three prescriptions with complete surface and asphere coverage.
Process-isolated worker attempts then fail identically because full-field real rays do not reach the
image surface. Both append-only replays therefore classify three `trace_failed` terminal items and
emit no candidate or staging ZMX. Result semantics, request bytes, worker responses, and empty
stdout/stderr artifacts are identical after removing only retry identity/path fields. This records
the deterministic replay result; it is not an expert judgment that the published optical designs
are unusable.
