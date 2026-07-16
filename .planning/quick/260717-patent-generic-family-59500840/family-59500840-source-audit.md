# Family 59500840 source audit

## Identity and publication boundary

- The retained classifier source is official PPUBS HTML for `US-11118059-B2`, application
  `16/052051`, Family ID `59500840`, assigned to FUJIFILM Corporation.
- It names prior US publication `US-20180340070-A1`, Japanese priority application
  `JP2016-019130` dated 2016-02-03, and parent `PCT/JP2017/003587`.
- The A1 is a same-application cross-check only. Its text, page boundaries, and numeric content are
  not borrowed into the B2 classification. Seven non-US family publications are queued outside the
  frozen 619-root cohort.

## Complete source denominator

The exact raw and normalized source hashes bind the full document. Structural parsing separately
confirms one cross-reference paragraph, Background paragraphs 1-3, Summary paragraphs 4-52, one
brief-drawing paragraph, detailed-description paragraphs 2-733, and claims 1-29. The apparent
paragraph-number resets are intentional and audited by section; they are not merged into one
synthetic sequence.

Six PPUBS tables are present:

1. Table 1 gives eight colorant-ratio combinations.
2. Table 2 gives film Examples 1-38.
3. Table 3 gives film Examples 39-57.
4. Table 4 gives Comparative Examples 1-18.
5. Table 5 gives properties/structures for Resins 1-6.
6. Table 6 gives properties/structures for Resins 7-19.

Thus the experimental denominator is 57 Examples plus 18 Comparative Examples, or 75 formal
experimental rows. Exact whole-block and formal-table digests bind every cell, including dye,
formula, film-forming process, aggregation step, resin/polymerizable compound, particle size,
light fastness, heat resistance, and defect-evaluation fields. The source also binds 78 chemical
structure tokens (`STR00001`-`STR00077` and claim token `STR00090`).

## Figure and optical interpretation

The disclosure declares only FIG. 1. It is an infrared-sensor layer stack: solid image pickup
element 110, infrared cut filter 111, color filter 112, infrared transmitting filter 114,
microlens 115, and planarizing layer 116. It is not a lens surface prescription.

The three `refractive index` occurrences describe high/low-index antireflection-film layers and a
low-index pixel partition wall. Across the complete source there are zero focal-length,
F-number/FNO, field-of-view/FOV, radius, curvature, Abbe, asphere, prescription, and surface-number
occurrences. The material evaluation rows likewise publish no ordered surface, thickness, glass,
conic, or aspheric-coefficient sequence from which an optical design could be reconstructed.

## PDF closure and terminal decision

Two independent B2 downloads decode to identical rasters on all 78 pages. The official and Google
A1 wrappers decode to identical rasters on all 79 pages. B2 and A1 have zero equal same-position
rasters across the first 78 pages, so all evidence remains publication-scoped. Complete contact and
boundary review shows one drawing sheet followed by chemical structures, material/process tables,
and claims; neither publication contains a hidden optical prescription table.

The 75 material experiments are variants within one document-scoped film/filter materials
disclosure, not 75 distinct optical prescriptions. The exact source therefore emits one
`confirmed_no_prescription.dye_aggregate_film_and_optical_filter_materials_only` terminal item.
Any source, section, paragraph, claim, table, experiment-number, figure, or marker drift fails
closed as a parser error.
