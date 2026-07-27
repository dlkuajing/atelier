# Family 84563102 exact-source audit

## Authority and identity

The classification authority is retained official USPTO PPUBS publication
`US-20260086334-A1` at
`data/patent-lake/uspto-ppubs-html/US-PGPUB/a105d7ac7697b802/US-20260086334-A1.html`.
The 82,331-byte HTML hashes to
`a105d7ac7697b802df58d94dd93fd1902e0409c3577bbfbdc5e6e09d7fd21883`;
its normalized 70,029-character text hashes to
`b9698b1824790c4399985b245474e3bad480423eb2eb5ca791dabcc05286f010`.
It directly binds application `19/409065`, Family ID `84563102`, Samsung
Electro-Mechanics applicant/assignee, four named inventors, Korean priority
`10-2022-0038054` dated 2022-03-28, and parent application `17/866683`.

The parent publication `US-20230305271-A1` was checked only to determine whether the
continuation repaired the source conflict. It repeats the same equation/table
conflict. No parent or external number, coefficient meaning or optical conclusion is
imported into the classifier.

## Complete source denominator

- Paragraphs `[0001]`-`[0105]`: four Background, eighteen Summary, fifteen drawing
  declarations, and 68 Detailed Description paragraphs.
- Fourteen claims, with claims 1 and 8 independent.
- Sixteen tagged tables, three MathML objects, FIGS. 1-14, fourteen official drawing
  sheets, and exactly seven optical examples.
- Examples 1-7 occupy `[0067]`-`[0071]`, `[0072]`-`[0076]`, `[0077]`-`[0081]`,
  `[0082]`-`[0086]`, `[0087]`-`[0091]`, `[0092]`-`[0096]`, and
  `[0097]`-`[0101]`. They bind respectively to FIGS. 1-2 through 13-14 and TABLES
  1-2 through 13-14. TABLES 15-16 and paragraphs `[0102]`-`[0105]` are common.

Each odd table publishes an ordered S1-S18 prescription with seven lenses, stop S5,
filter and imaging plane. TABLE 15 directly publishes system focal length, F-number,
ImgHT, FOV, TTL and BFL for all seven examples. These direct metadata values are
retained as denominator evidence, but they do not cure the asphere-definition defect.

## Exact asphere conflict and terminal boundary

Equation 1 and paragraph `[0064]` define only `A` through `J` as aspherical surface
constants: `A*r^4`, `B*r^6`, `C*r^8`, `D*r^10`, `E*r^12`, `F*r^14`, `G*r^16`,
`H*r^18`, and `J*r^20`. Every even prescription table publishes additional nonzero
rows `I`, `M`, `N`, `O`, and `P`. The exact A1 gives no power, ordering, basis or
other semantics for those five rows. TABLE 12 additionally leaves the S15 cell blank
for each of those five undefined rows; the original official page raster shows the
same blanks.

Assigning powers to `I/M/N/O/P` would therefore be an invented coordinate repair.
All seven examples close as
`metadata_unpublished.asphere_high_order_coefficient_semantics_absent`. No worker,
request, receipt, prescription fingerprint, candidate ZMX, staging ZMX, formal intake
record, expert verdict or CODE V call is created.

## Official raster audit

The official 30-page PDF endpoint was downloaded twice. The 1,309,921-byte wrappers
have distinct container hashes, while all 30 decoded page rasters agree in order at
raster-set SHA-256
`deae0c787f687c0087fe667c5c039f13e687c23a0f7eb547502c486bb071ced1`.
Every page has exactly one raster and no text layer. Pages 18-20 are 2550x3300; all
others are 2560x3300. The full contact sheet and original-resolution pages 20, 21,
22, 26, 27 and 29 were reviewed. Page 20 prints Equation 1 and the A-J definition;
page 27 prints TABLE 12's five blank S15 cells; page 29 prints TABLE 15.

Only lossless decoding and contact-sheet downscaling were used. There was no image
enhancement, OCR repair, drawing measurement, numeric transcription, raster inference,
coefficient inference or related-publication numeric borrowing.
