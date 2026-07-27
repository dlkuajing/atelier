# Family 65634646 source audit

## Identity and retained source

The exact retained USPTO Patent Public Search publication is `US-20220413251-A1`,
application `17/900484`, Family ID `65634646`, titled **CAMERA MODULE AND METHOD FOR
ASSEMBLING SAME**, filed 2022-08-31 by NINGBO SUNNY OPOTECH CO., LTD. It is a continuation
of application `16/643194`, which is a national-stage continuation of `PCT/CN2018/083923`,
and claims Chinese priority `201710814250.2` dated 2017-09-11.

The retained HTML is 78,516 bytes with raw SHA-256
`19ef45fc80889ee6e941038e0834f98fb708320c896d3f26fd681c1aedd30ae1`. Its normalized
text is 69,983 characters with SHA-256
`2478106de3096573507fef005d43109c8f96054ff700317f78710c2c65ea397e`.

## Complete denominator

The publication contains 142 consecutive numbered paragraphs: one cross-reference paragraph,
one technical-field paragraph, five background paragraphs, 56 summary paragraphs, 23 brief
drawing paragraphs, and 56 detailed-description paragraphs. It has 19 claims in two independent
claim families, FIGS.1-22, zero tagged HTML tables, and zero MathML objects.

The detailed disclosure reconciles to eight non-overlapping source items:

1. split-lens preparation, non-active pre-assembly and six-degree positioning;
2. image-derived MTF/defocus measurement and staged in-plane/tilt alignment;
3. adhesive, laser, ultrasonic and intermediate-member fixation variants;
4. axial target-surface and measured field-curvature matching;
5. paired-target inclination-vector compensation;
6. iterative reduced-range translation/tilt readjustment;
7. the assembled split-lens camera-module architecture; and
8. motor-on autofocus/reed-deformation compensation.

All 19 claims and all 22 declared figures map to these eight items, with no unmapped source item,
claim, or figure.

## Optical representability boundary

The one `radius of curvature`, two `refractive index`, and four `thickness` occurrences are
background examples of lens-fabrication deviations, not a prescription. The nine `optical
surface` occurrences define effective-light surfaces versus structural surfaces or discuss
assembly deviations. The 80% field is an image-based MTF test position, not a published optical
field of view. The +/-5 micrometre range, 0-to-15 micrometre axis stagger, sub-0.5-degree tilt,
10-to-50 micrometre clearance and sub-10-mm diameter are measurement tolerances or package
geometry.

No item publishes an ordered radius, spacing, material, refractive-index, Abbe, conic, asphere,
stop, focal-length, F-number, image-height, or field-of-view prescription. All eight items are
therefore exact-source `confirmed_no_prescription` terminals. No worker request, receipt,
prescription fingerprint, candidate, staging ZMX, formal intake, coordinate synthesis, raster
numeric derivation, or related-family borrowing is permitted or produced.

## Official PDF and drawing audit

The anonymous USPTO image endpoint independently returned HTTP 200 and `application/pdf`. The
retained wrapper is 1,621,127 bytes with SHA-256
`d95e5ada6f747f2175f04197c3a662f0517763803ee89a9ad0170aeb45c00e26`. It has 22
image-only pages, exactly one 2560x3300 raster per page, and no PDF text layer. Pages 2-11 are ten
drawing sheets containing FIGS.1-22; page 1 is front matter and pages 12-22 are specification and
claims. Every page raster and the complete contact sheet were reviewed.

A second independent retrieval produced a different container SHA-256,
`6a460b9a8ab777cc340e3e557938dc808f5a017df8e4064252b353eff8fe34c4`, while every
decoded raster remained identical. The canonical decoded-raster-set SHA-256 is
`f7cf7109d57fc0861b8c4b9de851ded3d249ff49faef97cf39f1ce43338f6589`.

## Replay and next queue

Append-only attempts 2 and 3 each emit the same eight terminal items. After removing only the
append-only `result_attempt` field, both canonical payloads hash to
`cdc804e1835498452a87df11ffdfa337d4ed8a55427efd35d19cb688f3dd0fdd`.

Strict replay remains 619/619 with missing=0 and corrupt=0. The result-set SHA-256 is
`17d539a5275d1fa9d38022b0f46a107bc12c1cbf916232d2b50899887e925cd5`. The generic
bucket changes deterministically from 102 to 101 roots/items; both after-census artifacts hash to
`81e75b6926ff7629c1e256f9bd241ba53a23a5a38b8969d5b32d510947c0fb4f`.

Generic remains the largest executable bucket at 101 roots/items, ahead of AAC Raytech at 55
roots/174 items and Sunny at 49 roots/177 items. Stable exact ordering selects Family `84785926`,
root `US-20230000344`, publication `US-20230000344-A1` next. Parent/global patent saturation
remains active and incomplete.

## Verification gates

Focused Family 65634646 tests pass 5/5. The complete main patent parser suite passes 548/548,
the nine exact offline patent support files pass 94/94, and the no-real-CODE-V guard passes 5/5;
this is 642 offline patent tests plus five guard tests. Ruff, Python compilation, 33 changed JSON
parses, 22 evidence files/288 referenced-record hashes, byte-identical after censuses, strict
619/619 replay audit, 48 null formal fields, four zero-contamination scopes and `git diff --check`
all pass. Final CODE V process inventory is zero.

One overbroad diagnostic `-k patent` selection also collected three `real_machine` CODE V smoke
tests. All three stopped at the stale-lock recovery gate before engine startup; the other 1,380
selected tests passed and CODE V inventory remained zero. That diagnostic is not counted in the
offline patent gate above, and no stale-lock recovery or engine control was attempted.
