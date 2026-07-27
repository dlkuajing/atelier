# Family 86240812 source audit

## Binding and denominator

The retained official publication is `US-20260129276-A1`, application
`19/439370`, Family `86240812`, titled `COMPACT DOUBLE FOLDED TELE CAMERAS`
and assigned to Corephotonics Ltd. Paragraph `[0001]` binds continuation
application `18/254858`, PCT application `PCT/IB2022/060175`, and provisional
applications `63/274700` and `63/288047`. No numerical value is borrowed from
those related applications.

The official HTML contains consecutive paragraphs `[0001]`-`[0194]`, claims
1-21 (independent claims 1 and 19), 22 declared figure panels, 13 flattened
tables and eight MathML objects. Every paragraph, claim, declared figure,
table, equation object and source-disclosed optical-system item is mapped. The
known systems 100/120/130 are prior art. Modules/mobile-device wrappers
200/230/250/280 and the AF/OIS material provide context but do not add an
eighth numerical lens prescription. The exact prescription denominator is the
seven disclosed lens systems 300, 320, 350, 400, 500, 600 and 700.

## Prescription reconciliation

Systems 300, 350, 400, 500, 600 and 700 each publish an ordered surface table
and a coefficient table. Paragraph `[0153]` states that system 320 is identical
to system 300 except for the G2 cut, so system 320 inherits Tables 2/3 exactly.
System 350 uses its own Table 4 surface/aperture rows and expressly reuses the
Table 3 surface types and coefficients. The resulting system-300 and system-320
axisymmetric prescriptions therefore have the same fingerprint and ZMX bytes;
the directional cut is retained as a source fact and is not claimed as a
formally represented aperture geometry.

Each surface table publishes a negative distance from the stop to the first
lens surface. Sequential ordering is obtained only by sorting the published
cumulative axial coordinates, using the same deterministic signed-spacing
rule already exercised by the repository. No 2D/3D drawing coordinate is
measured or synthesized. For system 700, paragraphs `[0175]`-`[0180]` and
Table 11 explicitly describe entry into the prism, reflection at its mirror
face and exit from the prism. The unfolded sequential material intervals keep
glass `nd=1.85`, `Vd=23.8` after the entry and fold faces, then return to air
after the exit face.

Prescription-local detailed headers are authoritative when Table 1 conflicts.
Thus system 400 uses Table 5 `EFL=21.480 mm`, `F/2.686`, `HFOV=13.9 deg`, not
Table 1 `F/2.76`; system 500 uses Table 7 `EFL=16.6 mm`, `F/2.77`,
`HFOV=6.16 deg`, not Table 1 `16.63`, `2.93`, `10.20`. The Table 1 sensor
diagonal is not divided or substituted for image height. The existing pipeline
uses its deterministic `EFL * tan(HFOV)` image-height input.

System 600 publishes QT1 norm radii and non-zero A0-A7 values for surfaces
2-9. Its seven retained equation objects define the sag and Q0-Q5 only; Q6 and
Q7 basis definitions are absent. No external Qcon convention is imported and
no coefficient conversion is guessed, so item 6 closes exactly as
`metadata_unpublished.qcon_q6_q7_basis_definitions_absent`.

## Official PDF review

The official 29-page PDF is image-only and contains one lossless raster per
page. Pages 2-14 are drawing sheets, pages 20-27 contain the published tables,
and pages 28-29 contain claims. Page 21 is the sole `2550 x 3300` raster; all
other pages are `2560 x 3300`. The decoded raster-set SHA-256 is
`b57c80f63456407146f29885f970c95fecb0c4efcb42ab7558e7607ec725d9c5`.
The contact sheet and original pages 1, 15, 20-27 and 29 were reviewed only to
confirm source layout and the Table 1/detailed-header discrepancy. No image was
enhanced, no drawing was measured, no raster numeric cell was transcribed, and
no source value was repaired.

## Replay result and remaining boundary

Append-only result attempts 2 and 3 each contain six
`converted_pending_intake` items and the one system-600 terminal. Their
business-semantic SHA-256 is
`c6fcde14a6e59fab93d97fd52f543ee28fb70983e7bb88e0705457d8b61d6061`
after normalizing only append-only attempt sequences and the corresponding
receipt paths/hashes; no outcome, request or response field is removed. All
request, response, candidate ZMX, stdout and stderr payload hashes are exactly
equal across the two runs. CODE V was not called.

The generic residual decreases from 77 to 76, with stable result set
`2fd10d202f3eff06d47e99656510d7eb0035c61a0afd161b788247a450a649a4`.
The six ZMX files remain staging candidates only: no case JSON, case-index
entry, intake manifest or expert backing is created. Stable queue ordering
selects Family `78957411`, root/publication
`US-20250130396` / `US-20250130396-A1` next. Global saturation remains
incomplete.
