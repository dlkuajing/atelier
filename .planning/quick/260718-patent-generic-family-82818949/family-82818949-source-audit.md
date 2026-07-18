# Family 82818949 source audit

## Identity and retained source

The exact retained USPTO Patent Public Search publication is `US-20230296863-A1`,
application `18/154079`, Family ID `82818949`, titled **LENS ELEMENT, IMAGING LENS
ASSEMBLY, CAMERA MODULE AND ELECTRONIC DEVICE**, filed 2023-01-13 by Largan Precision
Co., Ltd. It claims Taiwanese priority `111107139` dated 2022-02-25.

The retained HTML is 88,334 bytes with raw SHA-256
`f596732d311d4d244cc22d4181af268d6aa9ed9823e6afa587436d4d703e3bbb`. Its normalized
text is 71,408 characters with SHA-256
`ade58492e6841201a8866fc7cdc5eca0eebb2af874a0c025aac3da77ac8d8003`.

## Complete denominator

The publication contains 132 consecutive numbered paragraphs: one related-application
paragraph, one technical-field paragraph, one related-art paragraph, eight summary paragraphs,
23 brief-drawing paragraphs, and 98 detailed-description paragraphs. It has 25 claims in two
independent lens-element claim families, 23 declared figure panels, zero tagged HTML tables,
five flattened `TABLE-US` text tables, and 11 MathML objects. The MathML objects encode only
the claimed DS/DE, t/CT, DS/psi, S1/S2 and alpha mechanical conditions.

The detailed disclosure reconciles to eight source items:

1. a first lens-element example with spiral protruding structures and TABLE 1;
2. a second lens-element example with spiral protruding structures and TABLE 2;
3. a third lens-element example with spiral protruding structures and TABLE 3;
4. a fourth lens-element example with spiral protruding structures and TABLE 4;
5. a fifth lens-element example with spiral protruding structures and TABLE 5;
6. a multi-camera smartphone wrapper with ultra-wide, high-resolution and telephoto modules;
7. a folded-telephoto smartphone wrapper with generic TOF modules; and
8. a vehicle camera-placement wrapper with coverage visual angles.

The five lens examples occupy paragraphs 59-111. The three device wrappers occupy paragraphs
112-131. Common lens-element and imaging-assembly architecture occupies paragraphs 35-58, and
paragraph 132 closes the disclosure. The union of item mappings covers all 25 claims. Each of
the 23 declared figure panels maps exactly once, and each flattened table maps to its numbered
lens example. No source item, claim, figure panel, table or MathML object is unmapped.

## Optical representability boundary

TABLES 1-5 publish DS, DE, S1, S2, alpha, t, CT and psi values for peripheral protrusion,
spiral-path, molding and center-thickness geometry. They are not ordered surface rows. The five
`aspheric` occurrences state only that one or both named lens-element surfaces can be optical
aspheric surfaces; no radius, conic or coefficient is published. The sole `focal length`
occurrence says that image-processing zooming can cooperate with different camera-module focal
lengths but gives no values or constituent design.

No item publishes a complete ordered sequence of surface radius, inter-surface spacing,
material, refractive index, Abbe number, conic, asphere coefficients, stop, effective focal
length, F-number, image height or optical angular field. The 40-to-90-degree quantity in the
vehicle example is camera placement coverage, not a prescription. All eight items are therefore
exact-source `confirmed_no_prescription` terminals. No worker request, receipt, prescription
fingerprint, candidate, staging ZMX, formal intake, coordinate synthesis, raster numeric
derivation or related-family borrowing is permitted or produced.

## Official PDF and drawing audit

The anonymous USPTO image endpoint independently returned HTTP 200 and `application/pdf`. The
retained wrapper is 1,908,885 bytes with SHA-256
`e165cca0842ee3fb81461e6a83aa3b195a2d4e38098060379871e2a9f028b3ed`. It has 35
image-only pages, exactly one 2560x3300 raster per page, and no PDF text layer. Page 1 is front
matter, pages 2-24 are 23 drawing sheets, and pages 25-35 are specification and claims. Every
drawing sheet contains exactly its declared FIG. 1A-8C panel; every page raster and the complete
contact sheet were reviewed.

A second independent retrieval produced a different container SHA-256,
`d2c62579c352886a4535f3c6485afb687fe463a6e34422045bf746d2e2be6cfa`, while every
decoded raster remained identical. The canonical decoded-raster-set SHA-256 is
`acbf9220ab511c4998f5f2dfbe7d80341a1e05857db0991c432d6f139099515b`.

## Replay and next queue

Append-only attempts 2 and 3 each emit the same eight terminal items. After removing only the
`result_attempt` field, both canonical payloads hash to
`523de60492eda79e65f712e44d63c72766e0510a804ac3da0362846bd88f7ae6`.

Strict replay remains 619/619 with missing=0 and corrupt=0. The result-set SHA-256 is
`95fe1daefb7ea970805324eb77b2376ab57d0dc1a71a8520dc91531c01f3a6ec`. The generic
bucket changes deterministically from 100 to 99 roots/items; both after-census artifacts hash to
`020ba75d1f464c1dcbef80bffab67914776f156f9d911518d39818f502ed7d97`.

Generic remains the largest executable bucket at 99 roots/items, ahead of AAC Raytech at 55
roots/174 items and Sunny at 49 roots/177 items. Stable exact ordering selects Family
`51743335`, root `US-9360657`, publication `US-9360657-B2` next. Parent/global patent
saturation remains active and incomplete.

## Verification gates

Focused Family 82818949 tests pass 5/5. The complete main patent parser suite passes 558/558,
the nine exact offline patent support files pass 94/94, and the no-real-CODE-V guard passes 5/5;
this is 652 offline patent tests plus five guard tests. Ruff, Python compilation, 35 changed JSON
parses, 53 evidence files/452 referenced-record hashes, byte-identical after censuses, strict
619/619 replay audit, 48 null formal fields, 16 empty coverage mappings, four zero-contamination
scopes and `git diff --check` pass. Final CODE V process inventory is zero.

The new replay changed the global summary/report bytes and hashes. All 23 prior evidence files
referencing those two global artifacts were mechanically refreshed before the complete sweep;
old references then measured zero, new references measured 24 including this family, and the
full 558-test main suite passed on its first run. No classifier or test assertion was weakened.
