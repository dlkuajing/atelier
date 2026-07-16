# Family 74060373 source audit

## Scope and identity

The frozen generic bucket contained exactly three roots from official USPTO PPUBS sources. All
three share the retained `Family ID: 74060373` binding.

| Root | Publication | Application | Official HTML SHA-256 | Outcome |
|---|---|---|---|---|
| `US-12092800` | `US-12092800-B2` | `17/622393` | `162be98ab26d3e96a81dddd8350a4c2ec1588133fd4751719ca8b31fbb1a3335` | `confirmed_no_prescription.panoramic_opto_mechanical_architecture_only` |
| `US-12313825` | `US-12313825-B2` | `17/622463` | `f39a32f7a1eb5004447f43fc12e3bd60c06a55f4f4c50d26e4375e61b17bd154` | source-specific parser review |
| `US-20250284103` | `US-20250284103-A1` | `19/217645` | `449f9a8e066cb4625dd38d76d737a711f216fb45195668f98c25f9c32cebabf4` | source-specific parser review |

`US-12313825-B2` names `US-20220252848-A1` as its prior publication. The later
`US-20250284103-A1` identifies the grant as its continuation parent. These links are recorded as
application/publication provenance only; they do not license copying numerical values between
documents.

## Mechanical member: US-12092800-B2

- Title: *Opto-mechanics of panoramic capture devices with abutting cameras*.
- The complete `BRIEF DESCRIPTION OF THE DRAWINGS` contains the exact ordered paragraph sequence
  `(1)` through `(28)`, covering FIGS. 1–21 and their subfigures.
- PPUBS HTML contains zero structured patent-table blocks. The drawing-description body contains
  no `table`, `prescription`, `optical data`, or `lens data` marker.
- The full normalized disclosure contains no `lens prescription`, `optical data`, `lens data`,
  `surface radii`, or `aspherical surface coefficients` marker. Generic prose about aspheric
  surfaces and lens-element thicknesses/curvatures is retained as architecture guidance, not
  promoted to prescription data.
- The official image PDF contains 56 image-only pages. Every page was included in the retained
  contact-sheet review (`us12092800-pages-1-56-contact.png`); no hidden prescription table was
  observed.
- The classifier is locked to the exact raw and normalized source hashes, application number,
  28-entry drawing sequence, zero-table layout, and measured architecture phrase counts. Any
  source drift returns parser review instead of a terminal result.

## Seven-lens members: US-12313825-B2 and US-20250284103-A1

Both official texts explicitly bind FIGS. 8C-1 and 8C-2 to the FIG. 8A camera-lens prescription.
The disclosed system facts are seven lens elements, three aspheric lens elements, Zeonex E48R
conic elements, F/2.0, nominal focal length 2.57 mm, aperture-stop diameter 1.42 mm, track length
50 mm, image width 3.9 mm, and design wavelengths 450/587/656 nm. FIGS. 9–12 describe alternate
architecture without publishing an additional prescription.

| Evidence | US-12313825-B2 | US-20250284103-A1 |
|---|---|---|
| Official PDF pages | 66 | 66 |
| Prescription PDF pages | 17–18 | 16–17 |
| Parser-input SHA-256 | `1caf5531155757b94117e96d89ee3af199f47a2e3048689b29086aa92441c28d` | `9a5b1f08106420b3944adece909abfac7dfb508f3a463a7ecce702f5da78eb11` |
| Recovery-manifest SHA-256 | `d9dca8b16ba1747ee2c3eb5347f99c21d07fbdfe0de2d957743075a2104bbc77` | `0604ee54b0ceeab04d01475ea3c345461b7a5aa98302cee3bebae55b19265ded` |
| Key-page OCR token counts | 35 / 33 | 64 / 39 |
| Table-region numeric tokens at confidence >= 0.99 | 0 | 0 |

The B2 Google OCR PDF and official USPTO PDF decode to pixel-identical rasters on all 66 pages.
The A1 has no retained independent overlay and therefore uses official decoded rasters only. Raw
USPTO PDF container bytes can vary between requests, so the durable identity is the decoded page
raster set and canonical parser input, not the container hash. Both append-only replays produced
identical parser-input and recovery-manifest hashes.

RapidOCR 1.4.4 runs only after a deterministic 90-degree clockwise rotation. Each key page must
have its exact FIG label above 0.95; FIG. 8C-1 must additionally have exactly one `Lens
Prescription` label, while FIG. 8C-2 must have none. The numeric gate remains 0.99. Because zero
table-region numeric tokens meet that gate in both publications, no radius, thickness, material,
conic, or asphere coefficient is accepted and no ZMX is generated.

## Replay result

- Frozen cohort: 619 roots, SHA-256
  `e809823c709de93f49eb9b2103c4ebcdd9cf7e34d88f45a4953aaa21fd7bb42b`.
- Two append-only replays are semantically identical for every selected root after excluding only
  `result_attempt`; exact hashes are in `family-74060373-replay-determinism.json`.
- Full replay audit: 619/619 results, zero missing, zero corrupt.
- Generic bucket: 192 items/roots before, 189 items/roots after. The rebuilt after artifact is
  byte-identical across two runs, SHA-256
  `d638c3c548ac5bca9bbc088a9dc5aaf06e204beea004e00373f70d7932f81db5`.
- Parent patent saturation remains incomplete. This family audit closes only the three selected
  generic roots and does not claim expert design usability.
