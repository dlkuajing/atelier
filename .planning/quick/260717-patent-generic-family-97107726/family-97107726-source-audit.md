# Family 97107726 source audit

## Frozen identity and retained source

- Frozen root: `US-12425721`; retained publication: `US-12425721-B1`; application:
  `18/540492`; Family ID: `97107726`.
- Title: `Optical lens characterization and calibration`; applicant/assignee: Amazon
  Technologies, Inc.; filed December 14, 2023; patent date September 23, 2025.
- Kind code B1 and the absence of a related-application/priority section establish that the
  retained record has no pre-grant publication or claimed continuity document in this source.
- Retained USPTO HTML is 106,178 bytes, raw SHA-256
  `ced8908e46d666e070d1f9776d6a3bf9865bd446f3acd7687116603843a8a7a2`; normalized text
  is 92,125 characters with SHA-256
  `3b2e515f42acc51458889f01b5c0a34b2216ebcd145812d2263312432e1e07d2`.

## Complete text denominator

- Background: paragraph 1.
- Brief Description of the Drawings: paragraphs 1-9, declaring FIGS. 1-8.
- Detailed Description: paragraphs 10-98. Paragraphs 10-14 are common overview; FIG.1 maps
  to 15-30, FIG.2 to 31-33, FIG.3 to 34-35, FIG.4 to 36-48, FIG.5 to 49-55, FIG.6 to 56-67,
  FIG.7 to 68-81 and FIG.8 to 82-92. Paragraphs 93-98 are closing boilerplate.
- Claims: 1-20. Claims 1-4 are a setting-space/database-selection method; claims 5-13 are a
  machine-learning setting-selection method; claims 14-20 are an image-acquisition/computer
  system family.
- The source contains zero tagged HTML tables and zero MathML objects.

## Eight disclosed items

1. FIG.1 setting-analysis process: send camera settings, image the target, decode barcodes,
   score performance, update a model and issue settings.
2. FIG.2 motorized calibration system: camera rail, target, focus/aperture gears, motors and
   controller.
3. FIG.3 stepped barcode target: five depth steps with radially arranged barcode sets.
4. FIG.4 iterative setting-space exploration process.
5. FIG.5 database selection of a lens and settings by decode performance.
6. FIG.6 machine-learning setting-selection process.
7. FIG.7 setting-analysis computer/user-device/camera-controller architecture.
8. FIG.8 generic web-service computing environment.

All eight are distinct architecture/process/target items. None publishes an ordered sequence of
optical surfaces, radii, spacings, materials, conics or asphere coefficients.

## Optical-term and numeric reconciliation

- The sole `f/2.8` and `f/1.8` occurrences are paragraph-14 aperture values in first/second
  sampled camera-setting vectors. They are not a prescribed lens F-number tied to surface data.
- All six `radius` occurrences describe the calibration target radius or fractions of it.
- Four `field of view` occurrences describe barcode decode-performance coverage across a camera
  field, not an angular optical prescription.
- The source names first/second lenses and selects between them by measured decode performance,
  but publishes no coordinates for either lens.
- Marker census: lens 96, camera 179, aperture 29, field of view 4, radius 6, focus distance 30,
  working distance 9, barcode 177, optical axis 12 and depth of field 5.
- Exact zero markers include focal/effective focal length, F-number/Fno/F/#, surface, curvature
  radius, refractive index, Abbe, conic, asphere, coefficient, lens element, image height,
  aperture stop and entrance pupil.

## Drawing-source availability

- The repository-recorded USPTO PDF endpoint returned HTTP 404 and no PDF file was retained.
- The USPTO Official Gazette week-38 page returned HTTP 200 and supplied one exemplary GIF.
  The retained 290x400 grayscale image was visually reviewed: it is FIG.1's
  setting/decode/machine-learning flow and contains no optical table.
- Google Patents identified the grant as a B1 with no pre-grant publication, exposed nine full
  drawing-image links and no PDF link. Direct image probes returned HTTP 403, so zero Google
  drawings were retained and no claim of all-sheet visual review is made.
- Classification truth remains the complete retained USPTO HTML. The Gazette image is scope-only;
  no drawing transcription, numeric derivation or mirror numeric borrowing is permitted.

## Replay and boundary

- Attempts 2 and 3 each produce eight `confirmed_no_prescription` terminals. Excluding only
  `result_attempt`, semantic SHA-256 is
  `557877eeef5e47568ec42e0480340de46bb1b03e7feb51024347147cf3583979` for both.
- No conversion worker, request, receipt, fingerprint, candidate, staging ZMX, formal intake or
  CODE V operation is produced.
- Generic census moves 111 to 110 roots/items. Strict audit remains 619/619 with corrupt=0.
- Parent/global patent saturation remains active and incomplete.
