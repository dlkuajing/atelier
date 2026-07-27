# Family 85177416 source audit

## Identity and retained authority

- Frozen root: `US-12498545`; primary publication: `US-12498545-B2`; prior
  publication: `US-20230048740-A1`; application: `17/813265`; Korean priority:
  `10-2021-0098990` dated 2021-07-28; Family ID: `85177416`.
- The retained USPTO B2 HTML is 86,790 bytes / 83,120 characters at SHA-256
  `db9ea5f722c47ae3cf3b90ee77f8862813d2e410fffd9f7929cff4dba2f561ab`.
  Its normalized 68,164-character representation is
  `36f7edb358a323333a32d072441047c10a3ae0b056218eed7e88284ee555198b`.
- The grant's own Prior Publication Data binds `US 20230048740 A1` to the same
  application. Both official USPTO PDFs were retained independently: B2 is
  1,269,840 bytes at `44a3a3a1…8842c`; A1 is 1,282,773 bytes at
  `fbc82001…fea32c`.
- Both PDFs contain 25 image-only pages, exactly one raster per page and no text
  layer. Their canonical decoded-raster-set hashes are `f378196d…17bef` (B2)
  and `e02da3ff…b59a` (A1). Pages 2-13 in each file cover the twelve declared
  figures. The B2 table pages are 16-24; the A1 table pages are 17-24.

## Complete denominator

The source audit reconciles all 20 Background/Summary numbered paragraphs, all
125 Description numbered paragraphs, claims 1-7, FIGS. 1-12, ten tagged HTML
tables, nine MathML objects and five disclosed optical prescriptions. Description
paragraphs 37-55, 56-72, 73-88, 89-104 and 105-121 bind the first through fifth
prescriptions respectively. Odd TABLES 1/3/5/7/9 each publish the ordered
`Object, 1, 2, Stop, 4..15, Image` surface rows. Even TABLES 2/4/6/8/10 each
publish Qcon Y radius, normalization radius, conic and fourth-through-thirtieth
Qcon coefficients for surfaces `2, Stop, 4..13`.

The Qcon equation is directly defined, but Forbes Qcon coefficients are not
monomial CODE V XASPHERE coefficients. No basis conversion is attempted. More
importantly, every item reaches a source-proven upstream terminal before that
implementation boundary: four prescriptions lack one unique official radius set,
and the remaining prescription lacks all required system metadata.

## Radius reconciliation

The surface tables print four decimal places. The paired Qcon tables print at
least five, so `0.0000501 mm` is the accepted ordinary nearest-rounding envelope.
The following differences exceed that envelope or are nonnumeric:

| Item | Surface | Odd surface table | Even Qcon table | Exact-source result |
|---|---:|---:|---:|---|
| 1 | 8 | `1.6411` | `1.84110E+00` | conflict |
| 1 | 11 | `-0.6224` | `-8.22449E-01` | conflict |
| 1 | 12 | `-3.9286` | `-3.92882E+00` | conflict |
| 2 | 10 | `34.2167` | `3.42157E+01` | `0.0010 mm` conflict |
| 3 | 4 | `1.6720` | `1.57195E+00` | `0.10005 mm` conflict |
| 5 | 6 | `-2.7664` | `-2.76644.8+00` | Qcon token is nonnumeric |
| 5 | 7 | `Infinity` | `1.00000E+03` | plane/numeric conflict |
| 5 | 10 | `-35.6526` | `-3.56528E+01` | `0.0002 mm` conflict |

These are not HTML layout artifacts. Original-resolution B2 and A1 scans repeat
the same values: item 1 on B2 pages 16-17 and A1 page 17; item 2 on B2 pages
18-19 and A1 pages 18-19; item 3 on page 20 of both; item 5 on page 23 of both.
Item 4 TABLES 7/8 are internally consistent in both publications.

## Required metadata and terminal mapping

The complete normalized source contains zero occurrences of `effective focal
length`, `focal length`, `F-number`, `F number`, `Fno`, `field of view`, `angle
of view` and `FOV`. It contains image-height and `TOPL/Himg` values, but neither
is used to derive EFL, F/# or angular field. The source therefore does not publish
the system metadata required by the conversion contract for any prescription.

The ledger schema has no `source_conflict` terminal. A source conflict proves
that a unique required prescription field was not published, so items 1/2/3/5
use conflict-specific `metadata_unpublished.*` reason codes. Item 4 uses
`metadata_unpublished.required_system_efl_f_number_and_angular_field_absent`.
All five classifications are based on the complete same-application source set;
no value is repaired, averaged, inferred or borrowed.

## Replay and downstream boundary

Append-only attempts 2 and 3 are semantically identical after removing only
`result_attempt`, at SHA-256 `c58c7db8608ef0c05a7d2d5462d3ccc43630c80a5c11b24278f5d302f762a99e`.
They contain five terminal items and no conversion request, receipt, prescription
fingerprint, candidate or staging ZMX. Strict replay remains 619/619 with zero
missing and zero corrupt results. The generic residual falls from 96 to 95 roots
and items; the next stable exact group is Family `23219584`, root `US-6292306`,
publication `US-6292306-B1`. Global patent saturation remains incomplete.
