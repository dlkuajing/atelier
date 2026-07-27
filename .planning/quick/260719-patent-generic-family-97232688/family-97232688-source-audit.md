# Family 97232688 source audit

## Scope and identity

The frozen generic bucket contains one retained root, `US-20250314947`, whose exact official
publication is `US-20250314947-A1`, application `19/239600`, titled *Mounting Systems for
Multi-Camera Imagers*. The text binds `Family ID: 97232688` and Circle Optics, Inc. It identifies
application `17/908158` and grant `US-12332549` as continuation lineage only; no parent content or
numeric value is used here.

The retained official HTML is 239,216 bytes at SHA-256
`650093e2071264d9eaf88d76aa8518c033095250c2f73321c019d0656d29a546`; its normalized text is
214,181 characters at SHA-256
`6ad25d418ce82889e3beab1d61a9b937b1bff84581055c3656ff6ae9ecf40a2a`.

## Complete textual denominator

- The official source has 201 distinct numbered paragraphs: `[0001]` and `[0003]` through
  `[0202]`. The publication itself has no `[0002]`; this is retained as a source fact rather than
  repaired.
- Paragraphs 9–39 contain 31 drawing declarations covering 34 panels: FIG. 1; 2A–2B; 3–4;
  5A–5E; 6–12; 13A–13B; 14A–14B; 15–17; 18A, 18B-1 and 18B-2; 19–21; 22A–22B; 23–24.
- The source has 20 claims. Claim 1 is the sole independent imaging-device claim; claims 2–20
  all depend on that claim family and refine datums, linkages, supports, sensors or low-parallax
  behavior.
- The official HTML has 273 `figref` tags, zero patent-table blocks, zero HTML table/image/MathML/
  SVG/figure tags, and zero equation placeholders.
- Section hashes and eleven paragraph-span hashes cover the entire normalized disclosure. They
  are recorded in `family-97232688-source-facts.json` and enforced by the exact-source classifier.

## Optical and mechanical content

Every disclosed configuration was reviewed. FIGS. 1–7 describe baseline polygonal camera,
low-parallax, field and distortion architecture. FIG. 13A shows a split-compressor lens form and
paragraph 101 gives example glass/index/Abbe context. FIGS. 8–10, 13B, 16–20, 22A–23 describe
sensor adjustment, datums, seams, housings, supports, central frames and cooling. FIGS. 11–12 and
14A–14B cover masks, fiducials, baffles and protective structures. FIGS. 21 and 24 describe relay
and annular system alternatives; FIG. 15 describes electronics and thermal/tunable-lens control.

The text contains generic focal-length/EFL, F-number, FOV, 1:1/2.75:1 relay, lens-design program,
glass and aspheric-surface statements. It contains no ordered surface-radius sequence, ordered
axial spacings, ordered material sequence, conic constants, asphere coefficients or prescription
table. None of those generic values is promoted to a reconstructable prescription.

## Official raster audit

The verified USPTO image endpoint returned two 6,083,694-byte PDF containers with different
container hashes. Both decode to the same 64 page rasters. Every page contains exactly one
1-bit, 2560×3300 raster and no text layer. The decoded raster-set SHA-256 is
`db3343adfe90ccf5910cfb702344a823ddf72291092b745079c1045eb966a34f` for both fetches.

Pages 2–34 are exactly 33 drawing sheets. All drawing sheets, the cover, the first specification
page and the claim boundaries were viewed at original resolution; eight nearest-neighbor contact
sheets were used only for navigation. No enhancement, coordinate measurement, raster numeric-cell
transcription or numeric derivation was performed. The full page records and retained artifact
hashes are in `family-97232688-raster-audit.json`.

## Source-item decision and replay

The denominator is one complete imaging-device claim family, matching the repository's existing
Circle Optics mechanical-only precedent. Individual drawing panels and mechanical subassemblies
are implementations of that device family, not independent numerical optical prescriptions. The
single item is therefore terminal
`confirmed_no_prescription.multi_camera_mounting_and_opto_mechanical_architecture_only`.

Append-only attempts 2 and 3 are semantic-equal after removing only `result_attempt`, at SHA-256
`44bf46e8d0f3d4e5473993eb31297c51526418b741080483d88a8f728740c30d`. Neither attempt created a
worker request, receipt, prescription fingerprint, candidate/staging ZMX or formal intake output.
The strict replay remains 619/619 with zero missing and zero corrupt results; the generic bucket
moved from 59 roots/items to 58 roots/items.

Parent patent saturation remains incomplete.
