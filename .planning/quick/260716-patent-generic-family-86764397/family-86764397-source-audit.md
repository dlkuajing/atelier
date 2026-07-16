# Family 86764397 source audit

## Scope and publication relationships

- The frozen roots are `US-12470822` and `US-20260039960`. Their retained official
  publications are `US-12470822-B2` and `US-20260039960-A1`, both titled `SHIFTABLE CIRCUIT
  ELEMENT, SHIFTABLE IMAGE SENSOR MODULE, CAMERA MODULE AND ELECTRONIC DEVICE` and both bound
  to Family ID `86764397`.
- `US-12470822-B2` is application `18/337472`. Its official Prior Publication Data names
  `US-20240007748-A1` (2024-01-04), and its related data names provisional `63/357070` plus
  Taiwan priority `112106819` (2023-02-23).
- `US-20260039960-A1` is application `19/353732`. Its official related-application data states
  that it is a continuation of application `18/337472`, names parent grant `US-12470822`, and
  retains the same provisional and Taiwan priority.
- `US-20240007748-A1` is not a frozen root in this shovel. The exact continuation/grant
  relationship is recorded, but no title similarity is used to transfer facts or create a
  terminal.

## Exact official HTML sources

| Publication | Application | Raw SHA-256 | Normalized-text SHA-256 |
|---|---:|---|---|
| `US-12470822-B2` | `18/337472` | `3086bf4acc39aeeae39659b5bebc51c39b46b1eed93c89bce69f572c087d0b30` | `2c1bc5322a375ec0c247ac1c595e78063ed76ffe8c1fb6ddd262dd4a30d85313` |
| `US-20260039960-A1` | `19/353732` | `ae90751842fc7ce931d7f1302fe801b5f709fa7702ce52473cc129997e546044` | `d9976c5a5c704c92fe98d703c232357dd1632aedbca1d029e6af1bd5469dcfc8` |

The source-locked structural denominator is identical in both publications:

- four detailed sections, headed `1st Embodiment` through `4th Embodiment`, with no fifth
  detailed-section heading;
- three explicitly numbered examples inside the first embodiment and no example belonging to
  any other embodiment;
- exactly three `TABLE-US` records: `TABLE 1A`, `TABLE 1B`, and `TABLE 1C`, respectively bound
  to the first, second, and third examples of the first embodiment;
- 15 ordered drawing declarations/panels: FIGS. 1A-1F, 2A-2E, 3, and 4A-4C;
- exactly six ledger items per publication: the three first-embodiment examples plus one item
  for each of embodiments 2, 3, and 4.

The first-embodiment common camera/sensor/circuit narrative is not a seventh item. It is the
shared context for the three explicitly numbered variants and publishes no fourth table, example,
or independently parameterized configuration. Counting it separately would duplicate the same
source section rather than reconcile another declared item. Nothing is silently excluded or
merged: the other three embodiments each have one dedicated detailed section and one item.

## Tables, embodiments, and terminal boundary

The three complete tables are:

| Item | Dc (mm) | We (mm) | Wc (mm) | He (mm) | Dc/Wc | We/He | N |
|---:|---:|---:|---:|---:|---:|---:|---:|
| First example / TABLE 1A | 0.14 | 0.07 | 0.04 | 0.25 | 3.5 | 0.28 | 28 |
| Second example / TABLE 1B | 0.18 | 0.05 | 0.03 | 0.30 | 6.0 | 0.167 | 36 |
| Third example / TABLE 1C | 0.10 | 0.08 | 0.04 | 0.20 | 2.5 | 0.40 | 32 |

Every column is explicitly defined as conductive-wire spacing/width/count or elastic-connector
cross-sectional geometry. None is an optical radius, thickness, material, stop, field, or
asphere value. These three items therefore terminate as
`confirmed_no_prescription.shiftable_image_sensor_wire_geometry_only`.

The remaining sections disclose:

- embodiment 2: a smartphone with ultra-wide, high-resolution, and telephoto camera modules,
  captured-image examples, and image-processing-assisted switching/zoom;
- embodiment 3: a smartphone with ultra-wide, wide, telephoto, and TOF modules; two telephoto
  modules are said to fold light, but no fold coordinate or lens prescription is published;
- embodiment 4: a vehicle with six camera modules and their placement around the vehicle.

The sole `focal length` occurrence is the nonnumeric phrase `different focal lengths` in the
embodiment-2 device narrative. The vehicle section states `40 degrees < theta < 90 degrees` for
the side-camera regions covered by the vehicle system; it does not bind a lens field, EFL, image
height, sensor format, or prescription and is not converted into an optical field value.

Both normalized sources have zero word-bounded occurrences of `effective focal length`, `EFL`,
`F-number`, `Fno`, `field of view`, `radius of curvature`, `curvature radius`, `aspheric data`,
`aspheric coefficients`, `refractive index`, `Abbe`, `Surface No./#`, `optical data`, `lens data`,
or `prescription`. Embodiments 2-4 therefore terminate as the existing
`confirmed_no_prescription.camera_module_device_architecture_only`. Any exact-source hash,
relationship, heading, example, table, drawing, architecture-count, vehicle-angle, or
prescription-marker drift fails closed into six parser-review items.

## Official PDF and raster reconciliation

| Publication | Official PDF SHA-256 | Pages | Drawing sheets/pages | Text/reference pages | Canonical raster-set SHA-256 |
|---|---|---:|---|---|---|
| `US-12470822-B2` | `5e60904838b5a373ae08665af6c1212b34d8759795f1be0aea50556558afb265` | 25 | 15 sheets, PDF pages 3-17 | cover 1, references 2, text 18-25 | `4c34144293074a9b23e49155cbb7ebca2d8ee65622207575bc1ee67cddffd850` |
| `US-20260039960-A1` | `103c55f519fbd9ae554456e3aa9aebf850e9ffba48770619dca4a7d0cd773bd7` | 24 | 15 sheets, PDF pages 2-16 | cover 1, text 17-24 | `970198ad495e6d26393760d8d722e31186e20427921aeaf01d8b6433dcc0f205` |

Every official PDF page contains exactly one embedded one-bit source image and no PDF text
layer. The raster-set hash is SHA-256 over canonical compact JSON containing the ordered page
hashes produced by the repository's `decoded-page-raster-v1` domain. Google citation-PDF
availability is zero for both publications, so there is no independent mirror pair and no
cross-mirror pixel-equality claim.

All four retained contact sheets were visually inspected. They contain the declared 15
mechanical/device drawings, followed only by the three wire-geometry tables, narrative, and
claims. They show no hidden surface sequence, image-only prescription table, asphere table,
fold-coordinate table, or additional example/embodiment. Contact-sheet SHA-256 values are:

- B2 pages 1-12: `28ee35568e8b066c9b946b93324c0b624fd3194d125f59d2536c090796d49fb0`;
- B2 pages 13-25: `8cf191bd14b77702b37456ff2f9118f0d03a160ac343b1a7dad244b795202abf`;
- A1 pages 1-12: `a2a3dbf5ad7cfe54fc78be4bfd3af53d561f3e13b32b5c4d454bb0800b66d0f7`;
- A1 pages 13-24: `47cf337196a7455191ef0ff3dde749f498f4bfd3799bd6a1704960e112acf37e`.

No worker, conversion receipt, prescription fingerprint, or ZMX is expected for these terminals.
This source audit makes no optical-quality, formal-intake, manufacturing, or production claim.
