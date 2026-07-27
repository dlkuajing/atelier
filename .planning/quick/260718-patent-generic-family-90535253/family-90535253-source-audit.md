# Family 90535253 source audit

## Identity and denominator

The retained USPTO Patent Public Search publication is `US-20240118520-A1`,
application `18/306676`, Family ID `90535253`, filed 2023-04-25 and published
2024-04-11 for Samsung Electronics, with CHO Yongsik as inventor. It claims
priority to Korean application `10-2022-0127936` filed 2022-10-06.

The exact normalized source contains 100 consecutive numbered paragraphs and 20
claims. Paragraphs 9-17 declare FIGS. 1-8, 9A and 9B: nine nominal figure numbers
and ten panels. The source contains 21 numbered tables, one MathML object for
Equation 4, three inline equations represented by six processing-instruction
delimiters and zero HTML image tags. Paragraphs 1-7 cover priority, background and
summary; paragraphs 8-17 declare the figures; paragraphs 18-41 disclose the
generic seven-lens architecture; paragraphs 42-68 disclose numerical systems
100a-100d; paragraphs 69-93 disclose electronic-device, camera-module and mobile
device wrappers; paragraphs 94-100 close the description.

## Prescription and representability boundary

Tables 1-5 disclose system 100a, Tables 6-10 system 100b, Tables 11-15 system
100c and Tables 16-20 system 100d; Table 21 adds a comparison for system 100d.
The four systems publish ordered radius and thickness rows, refractive index and
Abbe number, per-surface `Y Aperture`, focal length, A-J asphere coefficients, EFL,
Fno, HFOV, `2*IH`, TTL and FBL. Paragraphs 37 and 68 explicitly define HFOV as a
half field of view, so the published HFOV values are retained without division.

The exact normalized source contains neither the word `stop` nor `diaphragm`.
None of the 21 tables has an aperture-stop row, and no paragraph or claim gives a
stop axial coordinate. The exact FIGS. 1-5 rasters contain lens cross-sections and
ray bundles but no `STO` or stop-plane label. FIG. 1 labels lens surfaces and uses
`Aperture` for transverse effective lens size; the table column `Y Aperture` is a
per-surface effective aperture, not an axial stop coordinate. Fno does not identify
a unique axial stop position under the current contract. No stop coordinate was
inferred from Fno, measured from a raster drawing or borrowed from another family.
Consequently all four otherwise numerical prescriptions are fail-closed
`metadata_unpublished` terminals and no formal ZMX is permitted.

The official PDF is an exact retained 1,266,189-byte, 23-page image-only wrapper
with one raster per page. All rasters are 2560x3300 except page 13 at 2550x3300.
Pages 2-10 contain nine drawing sheets and ten declared panels; pages 11-21 contain
the specification, with page 21 transitioning to the claims; pages 21-23 contain
claims. The all-page contact sheet, FIGS. 1-5 and representative table pages were
reviewed at original raster resolution. No enhancement, geometry measurement or
numeric raster transcription was used.

## Item reconciliation

1. Paragraphs 18-41, FIG. 1 and claims 1-10 disclose a generic seven-lens
   architecture and constraints, not a single ordered numerical prescription.
2. Paragraphs 42-49, FIG. 2 and Tables 1-5 disclose system 100a, but no stop axial
   coordinate.
3. Paragraphs 50-54, FIG. 3 and Tables 6-10 disclose system 100b, but no stop axial
   coordinate.
4. Paragraphs 55-59, FIG. 4 and Tables 11-15 disclose system 100c, but no stop
   axial coordinate.
5. Paragraphs 60-68, FIG. 5 and Tables 16-21 disclose system 100d, but no stop
   axial coordinate.
6. Paragraph 32 and claims 11-15 disclose only a generic optional eight-lens
   architecture.
7. Paragraphs 69-93, FIGS. 6-9B and claims 16-20 disclose only electronic-device,
   camera-module and mobile-device wrappers.

Items 1, 6 and 7 are distinct `confirmed_no_prescription` terminals. Items 2-5 are
distinct `metadata_unpublished` terminals. No worker request, receipt, conversion
attempt, prescription fingerprint, candidate/staging ZMX, formal intake or CODE V
call exists.

## Replay and queue

Append-only attempts 2 and 3 are semantic-equal after removing only
`result_attempt`. The final strict audit is 619/619 roots with no missing or corrupt
result. The generic residual falls from 88 to 87 roots/items and the two final
census builds are byte-identical. Root-first queue ordering keeps generic ahead of
AAC Raytech at 55 roots/174 items and Sunny at 49 roots/177 items, and selects
Family `98695135`, root `US-20260086429`, next. Global saturation remains
incomplete.
