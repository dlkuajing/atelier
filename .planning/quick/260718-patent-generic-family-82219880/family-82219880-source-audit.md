# Family 82219880 source audit

## Identity and retained sources

- Frozen root: `US-20220214515`; exact publication: `US-20220214515-A1`.
- Application `17/567768`, Korean priority `10-2021-0001170`, Family ID `82219880`.
- Applicant and assignee: SEKONIX CO., LTD.; title: `SELF-ALIGNING CAMERA LENS ASSEMBLY`.
- Retained USPTO HTML is 35,331 bytes with SHA-256
  `ea78c079f9603bb02ea061a2ddf1174f686f4e48d2e5c8a0184b5c307ed390dd`.
  Its normalized 29,572-character text hashes to
  `0508bcaa9996a3bb71f81b763e1445d844768ae9d31a9e710a459c957ab10f7a`.
- The retained official USPTO PDF is 619,049 bytes, 11 image-only pages and one 2560x3300
  raster per page. Five drawing sheets on PDF pages 2-6 contain FIGS.1-10. Repeated downloads
  regenerate container metadata but preserve every decoded raster.

## Complete textual denominator

The HTML contains one related-application paragraph `[0001]`, one field paragraph `[0002]`,
12 background paragraphs `[0003]-[0014]`, 11 summary paragraphs `[0015]-[0025]`, six brief
drawing paragraphs `[0026]-[0031]`, 40 detailed paragraphs `[0032]-[0071]`, ten claims in one
claim family, zero tagged tables and zero MathML objects. Brief paragraphs 27-31 declare
FIGS.1-10. Detailed paragraph 61 contains `FIGS. 8 to 19` once but immediately identifies the
actual embodiment as `FIGS. 8 to 10`; the brief declaration and official sheets both contain only
FIGS.8, 9 and 10, so 19 is a source typo rather than an eleven-figure denominator extension.

Five non-overlapping source items cover every substantive embodiment and dependent feature:

1. Paragraphs 32-54 and claims 1-3, 7 and 10: the primary front/rear-lens point-contact alignment
   structure.
2. Paragraphs 55-60 and claim 4: repetition of the coupling through the third/fourth or all lenses.
3. Paragraphs 61-63 and claim 5: the circular annular coupling variant of FIG.8.
4. Paragraphs 64-66 and claim 6: one or more discrete symmetric coupling positions of FIGS.9-10.
5. Paragraphs 67-71 and claims 8-9: barrel fitting, optical-path blocking film and balanced
   assembly force.

FIG.1 is related-art context; FIGS.2-3 map the primary pair, FIGS.4-7 the cascading couplings,
FIG.8 the annular variant, and FIGS.9-10 the discrete variants. Every claim and declared figure is
therefore reconciled without borrowing another family.

## Prescription and representability decision

The only published numeric geometry is the point-contact coupling constraint outside the optical
effective diameter: coupling-portion curvature radius `R > 0.05 mm` and coupling-groove apex
angle `60° < V < 120°`. All ten `radius`/`curvature` occurrences repeat that mechanical constraint;
the sole `thickness` occurrence concerns matching the barrel to lens-flange shapes. The source
mentions non-spherical plastic lenses, refractive power, distortion and aberration generically but
publishes no ordered optical surface row, material/index/Abbe value, conic/asphere coefficient,
stop, focal length, F-number, image height or field. None of the five source items can form a
`PatentSurfaceInput` or a ZMX prescription. They are therefore five distinct exact-source
`confirmed_no_prescription` terminals.

No drawing coordinate was transcribed, no raster value was derived, no related publication or
family member supplied numeric data, and no worker/request/receipt/fingerprint/candidate/staging
ZMX/formal intake was created. CODE V was not called.

## Replay and residual queue

Append-only attempts 2 and 3 are semantic-equal after removing only `result_attempt`, at SHA-256
`e5cb1a5fa40cd56c2c07eaa56b2ecf966a7e6b975f1dd6b5fb6b571bd0e26a8f`. Strict replay remains
619/619 with missing=0 and corrupt=0. The generic bucket moves from 103 to 102 roots/items, and
both after censuses hash to
`4989892e5a5073094c11a13377a63dba9d8baf1eb24cac52707be0857de37ee1`.

The preceding Family 92715390 queue artifact incorrectly paired this publication ID with another
root's `USPAT/1887...` path and hash. This shovel corrects it to the census- and attempt-proven
`US-PGPUB/ea78...` source above and refreshes the referencing evidence hash. Stable ordering now
selects Family `65634646`, root `US-20220413251`, publication `US-20220413251-A1` next. Parent and
global patent saturation remain active and incomplete.
