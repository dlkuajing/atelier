# Family 89620713 source audit

## Frozen identity and retained source

- Frozen replay root: `US-20240272406`; retained publication:
  `US-20240272406-A1`; application: `18/642955`; Family ID: `89620713`.
- Title: `OPTICAL IMAGING MODULE, CAMERA MODULE AND ELECTRONIC DEVICE`;
  applicant: LARGAN PRECISION CO., LTD.; filed April 23, 2024; published
  August 15, 2024.
- The retained HTML states that this application continues application
  `18/413330`, published as `US-20240241352-A1`, and claims priority through
  provisional `63/480111` and Taiwan application `112135457`.
- Retained classifier input:
  `data/patent-lake/uspto-ppubs-html/US-PGPUB/b299af6070ba4f93/US-20240272406-A1.html`;
  97,011 bytes; raw SHA-256
  `b299af6070ba4f9342cf8a79e5f5cf806cd5d93695b6f2f867b0307239e546f9`.
- The exact normalized text is 79,576 characters with SHA-256
  `f46a725345908f1253f4b832dea934b6e209a6f0593f9c000e9bf861c43be104`;
  layout signature is
  `309c64184a88291e285d86d370dd049212208cb380959eb04fea3496b564964d`.

## Complete textual denominator

The classifier freezes all five ordered source sections, including their exact
normalized boundaries and hashes: abstract; combined related-applications,
background and summary; brief drawing description; detailed description; and
claims. Paragraphs are continuous with no gap: combined background/summary
`[0001]-[0007]`, brief description `[0008]-[0038]`, and detailed description
`[0039]-[0112]`. The four summary aspects, every detailed span, all 16 claims,
30 textual figure declarations, zero tagged HTML tables and both MathML objects
are independently hashed in `family-89620713-denominator.json`.

The 30 declared figure panels are exactly `1A-1C`, `2A-2D`, `3A-3C`,
`4A-4C`, `5A-5C`, `6A-6B`, `7A-7C`, `8A-8E`, `9`, and `10A-10C`.
Both MathML objects are mechanical distance inequalities involving the
light-blocking-element distance `D`; neither is a lens prescription equation.
Claims 1-14 form the folded optical-imaging-module family, claim 15 adds the
camera-module wrapper, and claim 16 adds the electronic-device wrapper.

## Disclosed-item reconciliation

The detailed description declares exactly ten examples, all mapped to one
ledger item and none omitted:

1. Paragraphs 59-63: first folded optical-imaging module; membrane
   nanostructure size `BS = 99.5 nm`.
2. Paragraphs 64-68: second folded optical-imaging module; membrane
   nanostructure size `RS = 235.3 nm`.
3. Paragraphs 69-74: third folded optical-imaging module; membrane
   nanostructure size `BS = 66.1 nm`.
4. Paragraphs 75-79: fourth folded optical-imaging module; membrane
   nanostructure size `RS = 173.5 nm`.
5. Paragraphs 80-84: fifth folded optical-imaging module; membrane
   nanostructure size `BS = 110.7 nm`.
6. Paragraphs 85-89: sixth folded optical-imaging module; membrane
   nanostructure size `BS = 56.6 nm`.
7. Paragraphs 90-94: seventh folded optical-imaging module; membrane
   nanostructure size `RS = 218.0 nm`.
8. Paragraphs 95-103: smartphone multi-camera placement and image-processing
   digital zoom across unspecified focal lengths.
9. Paragraphs 104-107: smartphone ultra-wide, wide, telephoto and time-of-flight
   camera placement.
10. Paragraphs 108-111: six vehicle-camera positions and a 40-to-90-degree
    placement field range.

The first seven examples specify folded-path, light-blocking-membrane and
nanostructure architecture. Their `BS`/`RS` values are coating microstructure
sizes, not radii, spacings or optical surface coordinates. Examples 8-10 are
device-placement wrappers that reuse examples 1-7 without publishing an
independent lens prescription.

## Prescription and representability boundary

The exact source contains 30 `optical lens element`, 171 `light path folding
element`, 60 `anti-reflective light blocking membrane layer`, 80
`nanostructure`, and 33 `image sensor` occurrences. It contains nine `focal
length` occurrences, eight of which are the mechanical phrase `back focal
length`; the remaining occurrence belongs to digital-zoom camera selection.
The four `refractive index` occurrences describe membrane/coating behavior.
The two `field of view` occurrences describe device/camera placement rather
than a complete prescribed optical state.

Conversely, the retained source contains no effective focal length, F-number,
FNO, F/#, Abbe number, aspheric/aspherical prescription, curvature radius,
thickness, aperture stop, conic, ordered surface, surface prescription, lens
prescription, or optical prescription marker. It publishes no ordered radius,
spacing, material, conic or asphere-coefficient rows and no complete set of
required system metadata. Therefore no disclosed item is representable as a
`PatentSurfaceInput` prescription without inventing values.

All ten items are consequently terminal
`confirmed_no_prescription`: examples 1-7 use the folded-module
light-blocking/nanostructure architecture reason; examples 8-9 use the
electronic-device multi-camera-placement reason; example 10 uses the
vehicle-camera-placement reason. No drawing coordinate was transcribed, no
numeric value was derived from a raster, no value was borrowed from the parent
application, no conversion worker was invoked, no ZMX was written, no formal
intake occurred, and CODE V was not used.

## Official PDF/raster cross-check

Official USPTO image PDFs for both `US-20240272406-A1` and parent publication
`US-20240241352-A1` are retained under `source-review/`. Each contains 40
image-only pages: cover page 1, 27 drawing sheets on pages 2-28, and
specification/claims on pages 29-40. Every page was decoded as exactly one RGB
raster and hashed from its decoded pixel bytes. Contact sheets and the current
publication's complete specification/claims pages 29-40 were visually reviewed;
parent cover and claim-boundary pages 29, 39 and 40 were also reviewed.

The two decoded raster sets have zero page hashes in common, so neither
publication was silently substituted for the other. The current continuation
has 16 claims; the parent has 30 claims arranged as two module families plus
camera/device wrappers. This claim-set change does not supply an ordered
optical prescription and is not used to fill any current-publication field.
Page-level hashes, PDF hashes, contact hashes and critical-page PNG hashes are
frozen in `family-89620713-raster-audit.json`.

## Replay and saturation state

Attempt 2 and attempt 3 are append-only result files with distinct file hashes
because `result_attempt` differs. Removing only that runtime identity field
produces the same canonical semantic SHA-256,
`d98edb65ef802d540bfcec962f3d8bc9446b09755d30685ddb677f1eb61c3682`.
Both attempts contain ten terminal `confirmed_no_prescription` items, no
conversion request/receipt, no prescription fingerprint and no staging ZMX.

The strict replay remains complete at 619/619 roots with zero missing or corrupt
results. The generic residual falls deterministically from 113 to 112 roots/items
and two after censuses are byte-identical. Global saturation is still incomplete.
The largest executable bucket remains `generic_summary_metadata_missing`; stable
layout/family ordering selects next Family `95155833`, root `US-12671891`,
publication `US-12671891-B2`.
