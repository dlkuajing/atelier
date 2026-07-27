# Family 62052738 source audit

## Identity and publication boundary

- The frozen cohort contains two roots from application `16/101656`: grant
  `US-10739565-B2` and application publication `US-20190154990-A1`. Both official PPUBS sources
  report Family ID `62052738`, inventor Jianming Wang, and Chinese priority
  `CN201711143573.X` dated 2017-11-17.
- The B2 lists AAC Acoustic Technologies (Shenzhen) Co., Ltd. as applicant and AAC Communication
  Technologies (Changzhou) Co., Ltd. as assignee. The A1 lists the former as applicant.
- Each publication is independently hash-bound and independently classified. Shared application
  identity does not authorize borrowing text, paragraph numbering, claim content, table spacing,
  numeric values, page boundaries, or raster truth across publications.
- Four CN/JP publications are outside the frozen 619-root cohort and remain queued.

## Complete source denominator

The B2 contains Background paragraphs 1-2, drawing paragraphs 1-9, detailed-description
paragraphs 10-117, and claims 1-9. The A1 uses a different numbering sequence: Background
paragraphs 0001-0002, drawing paragraphs 0003-0011, detailed-description paragraphs 0012-0107,
and claims 1-10. Exact normalized section and whole-document digests bind both denominators.

Each publication declares FIGS. 1-8 and twelve PPUBS tables. Per publication, Tables 1-6 bind
embodiment 1 and Tables 7-12 bind embodiment 2:

1. direct system and five element focal lengths;
2. aperture stop, five lenses, optical filter, and image-space surface prescription;
3. conic plus A4-A16 coefficients for R1-R10;
4. R1-R10 inflexion-point positions;
5. R1-R10 arrest-point positions; and
6. eight evaluated design conditions.

The same six-role sequence repeats for the second embodiment. Whole-block and formal-table
digests bind every cell. Structural checks additionally require twelve ordered surface rows after
the stop, five lens materials plus one filter material, ten eight-value asphere rows, ten
inflexion rows, and ten arrest rows per embodiment.

## Published system metadata and missing exact F-number

Embodiment 1 directly publishes system focal length 3.833 mm, pupil diameter 1.92 mm, full-field
image height 3.261 mm, and diagonal vision-field angle 79.23 degrees. Embodiment 2 directly
publishes 3.821 mm, 1.91 mm, 3.261 mm, and 79.46 degrees respectively. The text also states a
35 cm object-distance narrative and a system TTL upper bound of 4.4 mm.

Neither publication gives an exact embodiment F-number. The only two F-number occurrences in
each source are the narrative and claim inequality that the aperture F-number is less than or
equal to 2.0. No `FNO`, `F/#`, numerical-aperture, or table-level exact F-number appears. The
published pupil diameters are not substituted into focal-length/pupil arithmetic because that
would manufacture a value the source does not state and would erase the distinction between an
inequality and an exact embodiment setting.

## PDF closure and terminal decision

Both B2 official downloads contain 12 pages and decode to identical rasters page-for-page. The
official and Google A1 wrappers also contain 12 pages and decode identically within that
publication. B2 and A1 have zero equal same-position page rasters. Each publication has one cover,
five drawing sheets on PDF pages 2-6, specification text/tables on pages 7-11, and claims beginning
on shared boundary page 11 and ending on page 12. Visual contact and boundary review confirms all
FIGS. 1-8, all twelve tables, and the publication-specific 9/10-claim denominators.

Each root therefore expands from one generic document parser item into two source-locked
`metadata_unpublished.system_f_number_absent` terminal items. No worker, conversion request,
receipt, prescription fingerprint, candidate, or ZMX is created. Any source, identity, section,
paragraph, claim, figure, table, prescription, system-metadata, or F-number-marker drift fails
closed for both items of that publication.
