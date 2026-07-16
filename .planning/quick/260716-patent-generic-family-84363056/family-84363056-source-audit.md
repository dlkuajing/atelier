# Family 84363056 source audit

## Scope and publication relationship

- The frozen roots are `US-12235418` and `US-20230067508`. Their retained official
  publications are `US-12235418-B2` and `US-20230067508-A1`, both titled `Telephoto Lens for
  Compact Long Range Barcode Reader` and both bound to Family ID `84363056`.
- Both publications are the same application, `17/873058`, filed 2022-07-25. The B2 official
  Prior Publication Data names `US-20230067508-A1` (2023-03-02). Both official records name
  provisional application `63/239348` (2021-08-31).
- The application/publication relationship is reconciled explicitly. No fact or terminal is
  transferred by title similarity, layout signature, or family membership.

## Exact official HTML sources

| Publication | Application | Raw SHA-256 | Normalized-text SHA-256 |
|---|---:|---|---|
| `US-12235418-B2` | `17/873058` | `90b705c9b510a7885abdc379a345e6765fbfbb85f3bdcfa63c41e1abbb18f59c` | `4e4ead6863537320d55b5b21cda40bbc7a62f1d6008c2d4d9b69ebddd21e857e` |
| `US-20230067508-A1` | `17/873058` | `c13c69020e466001c3a6bb09584a7b5e09385c31b301fcb0ed9accc7d85d6bdd` | `41f761a66657fa8d6c040dc3fdcaf74a3326c5c973995e7eb1634ca099a79589` |

The complete source denominator is identical in both publications:

- zero PPUBS table blocks and zero `TABLE-US` records;
- one actual `DETAILED DESCRIPTION` heading and no formally numbered example or embodiment
  heading;
- five ordered drawing declarations, FIGS. 1-5, and five corresponding drawing sheets;
- one detailed four-lens telephoto architecture, with FIGS. 2-3 illustrating the same L1-L4
  sequence and FIG. 3 attaching one system-level numeric bundle;
- two independent claim groups, claims 1 and 11, both repeating the same imaging-engine/four-lens
  architecture rather than declaring separately parameterized optical examples;
- exactly one document-scoped ledger item per publication.

The prose occurrences `for example 1.52` and `for example 1.66` are refractive-index examples,
not example headings. Variations such as a robotic arm, aperture ranges, or avoiding sensor
contact change device/use constraints around the same architecture and do not publish another
surface sequence. Counting either the repeated claims or each prose variation as a separate
prescription item would duplicate one source design rather than reconcile another declared
optical example.

## Published optical architecture and terminal boundary

The source publishes the following four-element order along one optical axis:

| Lens | Published material / power | Published index / Abbe | Published surface statement |
|---|---|---|---|
| L1 | Crown-type glass, positive | index about 1.51-1.62, example 1.52; Abbe about 59 | two surfaces, no radii |
| L2 | Flint-type plastic asphere | index about 1.65; Abbe about 22 | two aspheric surfaces, no coefficients |
| L3 | Flint-type glass, negative | index about 1.57-1.75, example 1.66; Abbe about 24 | two surfaces, no radii |
| L4 | Crown-type plastic asphere | index about 1.53; Abbe about 56 | two aspheric surfaces, no coefficients |

The aperture stop is between L1 and L2. The particular FIG. 3 architecture publishes exactly:

- total first-lens-to-sensor length `10.34 mm`;
- effective focal length `11.8 mm`;
- telephoto ratio `0.876`;
- `19-degree FOV` with a `1/4 inch` sensor;
- `2 mm` aperture.

The broader prose and claims also publish bounds such as EFL at least `11 mm`, total length at
most `11 mm`, each lens central thickness at least `1 mm`, and aperture at least `1.5 mm`.
These values are retained as source facts, not promoted into a prescription. Neither publication
provides any surface radius, signed axial thickness/air spacing sequence, conic constant,
asphere coefficient, specific glass catalog code, or complete prescription table. The drawings
show qualitative lens shapes but carry no numeric surface annotations. Even the exact FIG. 3
system bundle therefore cannot determine the missing surface geometry.

Both normalized sources have zero strong prescription markers: `radius of curvature`,
`curvature radius`, aspheric/asphere `data`, `coefficient`, or `parameter`, `conic constant` or
`coefficient`, `Surface No./#`, `Fno`, `F-number`, `optical data`, `lens data`, and
`prescription`. The one item per publication therefore terminates as
`confirmed_no_prescription.compact_barcode_telephoto_architecture_only`. Any exact-source hash,
application/relationship, title, section, figure, claim, architecture phrase, material anchor,
system-value anchor, table, or prescription-marker drift fails closed to parser review.

## Official PDF and raster reconciliation

| Publication | Official PDF SHA-256 | Pages | Drawing sheets/pages | Other pages | Canonical raster-set SHA-256 |
|---|---|---:|---|---|---|
| `US-12235418-B2` | `cb7b91bd89ca04b97ca7371df00bb26b065b1459cc084fc589efdcc64a818961` | 14 | 5 sheets, PDF pages 3-7 | cover 1, references 2, text 8-14 | `ba7fb5b97172fef9d5212cc5edf6827a681e99bed1c1ee23a2fc8e900d5e5193` |
| `US-20230067508-A1` | `aa98052dbb454bd10d44713abdb233276ca672fa62b74f2c61a700c63ec1044a` | 13 | 5 sheets, PDF pages 2-6 | cover 1, text 7-13 | `3e97e63ab9732b646b21116dc300c7f9327b0b0b4eb73c7fda13be0f9fd2d5aa` |

Every official PDF page contains exactly one embedded source image and no PDF text layer. The
raster-set hash is SHA-256 over canonical compact JSON containing ordered page hashes produced by
the repository's `decoded-page-raster-v1` domain. No independent mirror was used, so no
cross-mirror pixel-equality claim is made.

Both all-page contact sheets were visually inspected. FIG. 1 shows the imaging engine, FIG. 2
the four-lens ray layout, FIG. 3 the same four-lens schematic without numeric annotations, FIG. 4
the reader, and FIG. 5 the device block diagram. The remaining pages contain narrative and
claims only. There is no hidden image-only surface table, asphere table, alternate optical
example, or additional drawing sheet. Contact-sheet SHA-256 values are:

- B2 all pages: `e7070a29660741dc646d850c4c022daf708e0f39bac30f2a0207ed2fe8be4556`;
- A1 all pages: `15d68a802436758d74680001fd469f586553818623da49e741b432093371c412`.

No worker, conversion receipt, prescription fingerprint, or ZMX is expected for these terminals.
This source audit makes no optical-quality, formal-intake, manufacturing, or production claim.
