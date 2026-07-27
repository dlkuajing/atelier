# Family 60001556 source audit

## Identity and relationship

- `US-10725279-B2` and `US-20190162945-A1` are the same application `16/092071`, Family ID
  `60001556`, and title `Systems and methods for extended depth-of-field microscopy`. The B2
  Prior Publication Data names the A1 record; both identify provisional application `62/320275`.
- The owner is Arizona Board of Regents on Behalf of the University of Arizona. Its exact name
  occurs twice in the B2 applicant/assignee front matter and once in A1 applicant front matter.
- Retained official HTML SHA-256 values are
  `df938fc2c5990798bf030f1da721c9fa4896aa031470b01c576ccba18299f91b` (B2) and
  `eb7cb67e831cc1c63467fbd8c93e1d2583395048fc8e78bbb764ffcd88095bbc` (A1).
  Parser-normalized hashes are
  `4f33518c76f6b68854991c1d9b474f45d448b68c726b57f132071414915fa35c` and
  `ec772f1c1b8a1ce6f1664c0c782d8466d5b9f9ccf5108593d54cea7d2660484f`.

## Source denominator and binding

Both publications declare exactly five formal examples:

1. theoretical analysis of deconvolution-free EDOF microscopy;
2. infinity-corrected EDOF microscope architecture;
3. an object-space telecentric varifocal microscope objective with an electrically tunable lens;
4. EDOF microdeflectometry results; and
5. an experimental EDOF structured-illumination microscopy demonstration.

The brief drawing section declares FIGS. 1-42 with 72 panels. The official PDFs contain 23 drawing
sheets each. The panel drawings reconcile the theory, ray/system layouts, experimental apparatus,
and measured results; they do not add a second optical prescription.

The complete publication contains exactly one PPUBS table, `TABLE-US-00001` / TABLE 1. Its
normalized table-only SHA-256 is
`d7b844bdf21ef1792cb616673cd828e2a56a9800f15b8ab464aa46260149b1fc` in both records. The text
explicitly binds it to Example III as a design specification of EDOF microscope 200 implementing
microscope objective 2900. It publishes the ordered focusing plane, fixed lens assembly, quarter
wave plate, Optotune EL-10-30 electrically tunable lens, beamsplitter, imaging lens assembly, and
imaging plane, with radii, thicknesses, materials, and semi-diameters. No asphere is declared.

Example III also publishes a 2 mm object-space field diameter, 0.24 NA, 550 nm working wavelength,
10 mm clear aperture, symbolic `F_obj`, and a 2 mm focus scan range. None is a direct numeric EFL,
F-number, or angular field bound to TABLE 1. The source has zero numeric assignment matching those
three required system fields, and the values are not derived from its formula or prescription.
Examples IV and V reuse a 2 mm diameter field, 0.25 NA, and 530 nm prototype context but publish
results, not independent ordered prescriptions; those values are not rebound to Example III.

## Official-raster reconciliation

Both official PDFs are image-only, have 47 pages, contain one decoded grayscale image per page,
and have no text layer. Every page was decoded and hashed in order. All-page contact sheets and
full-resolution pages 36-41 were inspected. TABLE 1 appears in full on PDF page 39 in each record;
no hidden prescription table, numeric EFL, F-number, or angular field appears elsewhere.

| Publication | Drawing pages | Retained PDF SHA-256 | Second live-wrapper SHA-256 | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---|---|---|---|---|
| B2 | 3-25 | `d4cc48cb4433a49318d8f873833132d6d876e6d973bf8de4454d3a8cfb1c6fdd` | `b95ca8c59ecefe16e74a326e743498e584dd6a1bf5f98a41f9a299d3e7e6846b` | `c842c7fa38bd5c0efbcf23d5ee03a1c3acaaad11f18f4b50b68d0a600b682788` | `71f04d6531ac319dd4c095334ed6195a86ac9638efadee5b4393525f81ec0cd0` |
| A1 | 2-24 | `2de46a473238bf54c71529a819d04b92b19fc92c74520f23dc9f4835c3b27a96` | `d67d2411a1a1fddf1c9abce881d23453af475118dfb32a6c1e0e0070ef78a930` | `4936d8c6875d14de91b3c98f2dfafbcdfdeded65ca5f335ea004ef29594235b5` | `8388f0107919338f30a47448a25c318ba234eaf4d8827e1e4eeaa5f3d3cdbf02` |

The two live wrapper byte streams differ for each publication, while every decoded page raster is
identical within that publication. Wrapper equality is not claimed. Tests independently rehash
both wrappers, all 47 page rasters, and both contact sheets.

## Fail-closed outcome

Each exact source yields five terminal items. Examples I, II, IV, and V are respectively terminal
as theoretical analysis, microscope architecture, metrology results, and microscopy experimental
results without an independent prescription. Example III is
`metadata_unpublished.prescription_specific_efl_f_number_and_angular_field_absent`: it has a real
surface prescription, but the required direct system metadata is absent. No item receives a
conversion worker, request, receipt, prescription fingerprint, candidate, or ZMX.

Raw/normalized identity, family, application, owner, relationship markers, five headings, one exact
table digest and anchor rows, all 42 numbered figure expressions/72 panels, source phrase counts,
and the absence of direct numeric EFL/F-number/angular-field assignments are fail-closed. Any drift
returns all five items to parser review.

Attempts 2 and 3 are append-only and byte-distinct only because of `result_attempt`; their
canonical semantic SHA-256 values are
`10038ecf92115e5850980d76febd4b050ef5584eb10440c3bd39937cf366a2bd` (B2) and
`5d5cbbef3915cd76f326d40d659d69520b82b21a09acd60cc195423ba9fccddc` (A1).
