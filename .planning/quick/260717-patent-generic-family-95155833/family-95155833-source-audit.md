# Family 95155833 source audit

## Frozen identity and retained source

- Frozen replay root: `US-12671891`; retained publication: `US-12671891-B2`;
  application: `18/781667`; Family ID: `95155833`.
- Title: `User interfaces integrating hardware buttons`; applicant and assignee:
  Apple Inc.; filed July 23, 2024; patent date June 30, 2026.
- The B2 identifies same-application prior publication `US-20250110574-A1`,
  published April 3, 2025, and provisional application `63/541755`, filed
  September 29, 2023.
- Retained classifier input:
  `data/patent-lake/uspto-ppubs-html/USPAT/8883f36f994bd453/US-12671891-B2.html`;
  1,039,010 bytes; 1,037,639 raw characters; raw SHA-256
  `8883f36f994bd4534c66df17defcff1dc536d69cf2fe8bcf136bacd27364cfc5`.
- The exact normalized text is 702,782 characters with SHA-256
  `78a5ad905c09991b31b00c8c3fa182fa574d1193c5e4bc05b7b32dbffca266cd`;
  layout signature is
  `309c64184a88291e285d86d370dd049212208cb380959eb04fea3496b564964d`.

## Complete textual denominator

The classifier freezes the complete normalized document as seven ordered,
independently hashed sections: preamble, abstract, references, combined
background/summary, figure description, detailed description and claims. The
background/summary section contains one related-application paragraph, one
FIELD paragraph, one BACKGROUND paragraph and BRIEF SUMMARY paragraphs 3-36.
The figure description is paragraphs 1-20; detailed description is the
continuous range 21-356; claims are the continuous range 1-42.

BRIEF SUMMARY paragraphs 5-34 declare five technical groups. Each group has six
method/storage/system/means/product wrappers, so those wrappers are not counted
as independent optical designs. Detailed description maps the five groups
without gaps to paragraphs 173-220, 221-260, 261-297, 298-319 and 320-348.
Paragraphs 21-172 are the generic device, event-handling, touch-input and API
framework; paragraphs 349-356 are implementation and privacy boilerplate.

The 19 textual drawing declarations expand to 86 panels: `1A`, `1B`, `2`,
`3A-3G`, `4A-4B`, `5A-5H`, `6A-6X`, `7`, `8`, `9A-9Z`, `10`, `11`,
`12A-12K` and `13`. There are zero tagged HTML tables and zero MathML objects.
Claims 1-20 form the computer-system family; claim 21 plus claims 23-32 form
the storage-medium family; claim 22 plus claims 33-42 form the method family.
All three claim families map to the configurable-settings interaction in item 4.

Three published label-discrepancy types are retained rather than silently
repaired: paragraph 320 refers to undeclared `FIG. 14`; paragraphs 326-327 say
`FIG. 10D` within the `FIG. 12` sequence; paragraph 348 copies the method-1100
reference after method 1300. They supply no numeric optical evidence and do not
change the five-item mapping.

## Disclosed-item reconciliation

The source declares exactly five techniques, all mapped to one ledger item and
none omitted:

1. Paragraphs 173-220, FIGS. 6A-6X and method 700: different hardware buttons
   route media capture and synthetic depth-of-field display behavior.
2. Paragraphs 221-260 and method 800: button press types remove, add or expose
   camera touch controls.
3. Paragraphs 261-297, FIGS. 9A-9Z and method 1000: button behavior depends on
   camera/application context and provides camera launch, crop, zoom or camera
   switching controls.
4. Paragraphs 298-319 and method 1100: a hardware button exposes configurable
   settings, setting associations and multiple-press behavior. All 42 issued
   claims recast this interaction.
5. Paragraphs 320-348, FIGS. 12A-12K and method 1300: press types route between
   a synthetic depth-of-field operation and media capture.

Each item is terminal `confirmed_no_prescription` with its own exact reason
code. No wrapper is promoted into a prescription and no disclosed technique is
collapsed into an unmapped document-level terminal.

## Prescription and representability boundary

The normalized source contains 843 `camera`, 12 `focal length`, 59 `f-stop`,
222 `synthetic depth-of-field`, 32 `field-of-view`, 50 `lens`, 13
`lens selection`, 21 `optical sensor`, 16 `depth camera`, 36 `zoom`, seven
`telephoto` and seven `wide-angle` occurrences. The focal-length occurrences
describe the definition of a simulated f-stop or the UI's 22/24/28 mm crop,
digital-simulation and camera-switching choices. The f-stop values are expressly
simulated depth-of-field settings. Field-of-view occurrences describe a preview
or user/XR view, not an angular prescription.

Conversely, the retained source contains no effective focal length, physical
F-number/FNO/F/# field, image height/IMH, curvature-radius row, thickness row,
glass/refractive-index/Abbe row, conic, asphere coefficient, aperture stop,
entrance pupil, surface number or ordered surface/lens/optical prescription. It
publishes no complete `PatentSurfaceInput` surface sequence or required system
metadata. Converting any item would require inventing an optical design.

No drawing coordinate is transcribed, no raster number is promoted to design
truth, no value is borrowed from A1, no conversion worker is invoked, no
request, receipt, fingerprint, candidate or staging ZMX is created, formal
intake remains zero, and CODE V is not used.

## Official PDF/raster cross-check

The official B2 image PDF contains 150 image-only pages: cover page 1,
22 reference pages at 2-23, 56 drawing sheets at 24-79, and specification/claims
at 80-150. Its cover directly states `42 Claims, 56 Drawing Sheets`. The
same-application A1 image PDF contains 130 image-only pages: cover page 1,
56 drawing sheets at 2-57, and specification/claims at 58-130.

Every page in both PDFs was decoded as one RGB raster and hashed from its pixel
bytes. Both complete contact sheets and 18 original-resolution critical pages
were visually reviewed. The two 280-page decoded raster sets have zero page
hashes in common, so neither publication was silently substituted for the
other. A1 prints claims 1-135 as cancelled and retains claims 136-157; B2 issues
claims 1-42. That prosecution difference narrows the issued interaction claims
but supplies no optical surface or system prescription.

## Replay and saturation state

Append-only attempts 2 and 3 each contain the same five terminal items. Removing
only `result_attempt` produces canonical semantic SHA-256
`cbbae9b9ae453b601e80467db78abfadfc6da189d9ca7d09285c7c2af5304847`.
There are no conversion requests, receipts, prescription fingerprints or
staging ZMX files.

Strict replay remains complete at 619/619 roots with zero missing or corrupt
results. The generic residual falls from 112 to 111 roots/items and two final
after censuses are byte-identical. Global saturation is still incomplete. The
largest executable bucket remains `generic_summary_metadata_missing`; stable
layout/family ordering selects Family `97107726`, root `US-12425721`,
publication `US-12425721-B1`, next.
