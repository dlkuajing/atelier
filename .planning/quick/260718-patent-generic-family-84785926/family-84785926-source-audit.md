# Family 84785926 source audit

## Identity and retained source

The exact retained USPTO Patent Public Search publication is `US-20230000344-A1`,
application `17/854607`, Family ID `84785926`, titled **OPHTHALMOLOGY INSPECTION DEVICE
AND PUPIL TRACKING METHOD**, filed 2022-06-30 by Medimaging Integrated Solution, Inc. It
claims Taiwanese priority `110124054` dated 2021-06-30.

The retained HTML is 46,827 bytes with raw SHA-256
`1d6c54415df59f35abb5ed70964fd6c93fdae82c84db869d444ca71037910305`. Its normalized
text is 39,735 characters with SHA-256
`f3b6969ec10743d2ddbb79db58148afe254e082a5dad136637d5edafd6175384`.

## Complete denominator

The publication contains 35 consecutive numbered paragraphs: one technical-field paragraph,
three background paragraphs, four summary paragraphs, nine brief-drawing paragraphs, and 18
detailed-description paragraphs. It has 27 claims in two independent claim families, 12 figure
panels (`1`, `2`, `3`, `4a`-`4d`, `5a`-`5b`, `6`, `7`, `8`), zero tagged HTML tables, and zero
MathML objects.

The detailed disclosure reconciles to eight source items:

1. the fundus-camera illumination, imaging-assembly, sensor and focus-drive architecture;
2. pupil-image resizing, filtering, enhancement, binarization and morphology;
3. contour variance, circle/ellipse fitting and motor alignment;
4. external-display operator alignment indications;
5. an internal-display, display-lens and light-splitter self-alignment path;
6. a tonometer wrapper;
7. a corneal-topography wrapper; and
8. an automatic-refractometer wrapper.

The union of the item mappings covers all 27 claims. Claim 17 legitimately maps to each of the
three device wrappers because that single claim explicitly enumerates the supported device
types. All 12 declared figure panels map once across the architecture and method items; the
internal-display variant has no exclusive panel. No source item, claim, or declared figure panel
is unmapped.

## Optical representability boundary

All 18 `focal length` occurrences describe adjustable focus by moving an image sensor, display,
or lens, or by changing an unspecified liquid-state-lens curvature. The only numeric focus range
is a 10-centimetre-to-infinity equivalent display range in the automatic-refractometer wrapper.
The two `radius` occurrences concern pupil-contour circle geometry, not optical surfaces. The
figures are expressly schematic and not actual size.

No item publishes an ordered optical radius, spacing, material, refractive index, Abbe number,
conic, asphere, stop, effective focal length, F-number, image height, or angular field. All eight
items are therefore exact-source `confirmed_no_prescription` terminals. No worker request,
receipt, prescription fingerprint, candidate, staging ZMX, formal intake, coordinate synthesis,
raster numeric derivation, or related-family borrowing is permitted or produced.

## Official PDF and drawing audit

The anonymous USPTO image endpoint independently returned HTTP 200 and `application/pdf`. The
retained wrapper is 856,098 bytes with SHA-256
`fa4b0a092ec61ada6398b9355e1fcf5e00a8c9a5eac1be183f078e13c152145a`. It has 15
image-only pages, exactly one 2560x3300 raster per page, and no PDF text layer. Pages 2-9 are
eight drawing sheets containing all 12 figure panels; page 1 is front matter and pages 10-15 are
specification and claims. Every page raster and the complete contact sheet were reviewed.

A second independent retrieval produced a different container SHA-256,
`378297ca65250c0060bfe41493fdaa6ea2ec4b25284bbb6c044988823b372701`, while every
decoded raster remained identical. The canonical decoded-raster-set SHA-256 is
`b7f22b32742c50277a8c6b0ad62fa6415aa678f9a79cb1ccc821615e622cb631`.

## Replay and next queue

Append-only attempts 2 and 3 each emit the same eight terminal items. After removing only the
append-only `result_attempt` field, both canonical payloads hash to
`2365f438e26d7bbd82bbc18b7d725ce04652cecd59f6803977b0c2e8196e65f2`.

Strict replay remains 619/619 with missing=0 and corrupt=0. The result-set SHA-256 is
`a29c2d4457752b19044ab2c4e79b00e9cc65195b777c590583a85392badcf523`. The generic
bucket changes deterministically from 101 to 100 roots/items; both after-census artifacts hash to
`3bd6a792774f84c2a9573b35b246ef081ad2c6311bb0ae7fa979b70b39e8d3f2`.

Generic remains the largest executable bucket at 100 roots/items, ahead of AAC Raytech at 55
roots/174 items and Sunny at 49 roots/177 items. Stable exact ordering selects Family
`82818949`, root `US-20230296863`, publication `US-20230296863-A1` next. Parent/global patent
saturation remains active and incomplete.

## Verification gates

Focused Family 84785926 tests pass 5/5. The complete main patent parser suite passes 553/553,
the nine exact offline patent support files pass 94/94, and the no-real-CODE-V guard passes 5/5;
this is 647 offline patent tests plus five guard tests. Ruff, Python compilation, 34 changed JSON
parses, 52 evidence files/436 referenced-record hashes, byte-identical after censuses, strict
619/619 replay audit, 48 null formal fields, four zero-contamination scopes and `git diff --check`
all pass. Final CODE V process inventory is zero.

The first complete main-suite sweep passed 533 tests and failed 20 evidence checks because the
new replay changed the global summary/report bytes and hashes while prior-family evidence still
retained the preceding values. All 23 evidence files referencing those global artifacts were
mechanically refreshed; old references then measured zero, new references measured 23, and the
full 553-test suite passed. No classifier or test assertion was weakened.
