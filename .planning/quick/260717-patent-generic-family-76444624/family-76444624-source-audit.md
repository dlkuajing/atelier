# Family 76444624 source audit

## Identity and retained source

- Frozen root: `US-11783729`; retained classification publication:
  `US-11783729-B2`; application: `17/017662`; Family ID: `76444624`.
- The retained USPTO Patent Public Search HTML is 115299 bytes at
  `data/patent-lake/uspto-ppubs-html/USPAT/7a5a9cc3ba92de76/US-11783729-B2.html`,
  SHA-256
  `7a5a9cc3ba92de76af68d8cf0e51d06e5f1c77c0b45feceaf50a5382f7b632ad`.
  Its normalized 100777-character text hashes to
  `3be90bda9dbddf3c5cd071c11fa5cfd008e64e7d195bbd39da63d97a6686eef2`.
- The B2 identifies same-application prior publication `US-20220076590-A1`.
  No foreign-family source or external optical model is used for classification.

## Complete textual denominator

- Background paragraphs: 1-3; Summary paragraphs: 4-7; Brief Description paragraphs:
  1-10; Detailed Description paragraphs: 11-89; retained B2 claims: 1-16.
- Summary paragraphs 4-6 disclose three primary items: a colorblind-accessible
  image-rendering system, an image-rendering method, and a method for generating a color
  vision deficiency transformation model. B2 claims 9-16 add the machine-readable-medium
  wrapper as a fourth distinct source item.
- Ten textual drawing statements contain 19 panel occurrences and 17 unique panels:
  FIGS. 1A/1B (declared twice), 2, 3A-3C, 4A-4C, 5A/5B, 6A-6C, 7, 8 and 9.
- The HTML contains zero tagged tables and zero MathML objects. Detailed Description
  paragraphs 29-52 publish eleven labeled pseudocode listings. Listings 1-4 simulate CVD RGB
  values; 5-8 build RGB/RG/BG simulation and translation tables; 9-11 apply full or scalable
  color translation to pixel arrays. Their numeric values are color-component percentages,
  array dimensions and color-distance calculations, not optical surface coordinates.
- Every numbered paragraph, B2 claim, figure statement/panel occurrence, pseudocode listing and
  disclosed item is mapped. Unmapped counts are zero.

## Optical representability finding

- The retained source contains zero occurrences of focal length, effective focal length,
  F-number/FNO/F/#, refractive index, Abbe value, asphere/aspherical surface, conic, aperture
  stop, lens element, curvature radius, thickness, surface prescription, lens prescription or
  optical prescription.
- Paragraph 44 contains the sole `camera optical lens` phrase and paragraph 46 the sole
  `field of view` phrase. Both describe a mobile-device viewfinder receiving dynamic camera
  imagery; neither provides a lens element sequence or any radius, spacing, glass, conic,
  coefficient, stop or direct numeric optical-system metadata.
- Camera, display-device, source/rendering-image, lookup-table, minimum-color-distance, UI,
  software and generic-machine details are functional image-processing architecture. None is
  representable as a sequential optical prescription without inventing a system.
- All four source items therefore terminate as `confirmed_no_prescription`. No worker,
  conversion request/receipt, prescription fingerprint, candidate, formal intake or staging ZMX
  is created. CODE V is not used.

## Official raster cross-check

- Official `US-11783729-B2` is a 31-page image-only container: cover page 1, references page 2,
  15 drawing sheets on pages 3-17, and specification/claims on pages 18-31. Its file hash is
  `48a2221caf3f70fa22fba4f2ecbd545c1eae08bffaa12a956fd3441366400aa1`; decoded raster-set
  hash is `a90d82de3dc65b61403987a25b97a6cf354e275601fa2f51ec8801d7c96e864a`.
- Same-application `US-20220076590-A1` is a 32-page image-only container: cover page 1,
  15 drawing sheets on pages 2-16, and specification/claims on pages 17-32. Its file hash is
  `e77577da7953152531a426b98c53fddd01f31408bda8330f5662b5891de63c37`; decoded raster-set
  hash is `7f2a7c60c5a0e9adfbc8fda7bb84262170d0dcacab4e78940ed0faf1325593cc`.
- The two raster sets have zero byte-decoded page intersection because publication headers and
  pagination differ. Both all-page contact sheets and retained cover, first-specification,
  pseudocode, camera/viewfinder and claim pages were visually reviewed at original resolution.
- A1 has 20 claims in four independent families: rendering system (1-8), rendering method
  (9-16), machine-readable medium (17), and transformation-model method (18-20). B2 has 16
  claims in two independent families: transformation-model method (1-8) and
  machine-readable medium (9-16). This prosecution consolidation changes legal scope but adds
  no optical numeric truth.
- Raster review is scope verification only. No drawing/pseudocode coordinate is transcribed, no
  value is derived from a raster, and no A1 numeric value is borrowed into the retained B2
  classification.

## Replay and queue

- Attempts 2 and 3 each produce four confirmed-no-prescription terminals and are
  canonical-semantic-equal after removing only `result_attempt`, at
  `029e9f19f2052e8f8e6791d970c6e5ddf1f937f418fdb0566325e6e4433e3a4c`.
- Strict replay remains 619/619 with missing=0 and corrupt=0. Generic metadata falls from
  114 to 113 roots/items; the two after censuses are byte-identical at
  `22a26ac2209fe6e840ec448a99325e48d2a82ef5c68913f88fd00e525139bfac`.
- Root-first queue ordering keeps generic metadata ahead of AAC Raytech and Sunny and selects
  Family `89620713`, root `US-20240272406`, publication `US-20240272406-A1`, next.
  Parent/global patent saturation remains incomplete.
