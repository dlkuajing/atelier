# Family 90360259 source audit

## Identity and denominator

The exact retained official source is `US-12554108-B2`, application `18/535096`,
Family ID `90360259`, titled *Encapsulated optical imaging camera*. It contains nine
numbered Background/Summary paragraphs, 103 numbered Description paragraphs, 21 claims,
31 declared figure panels, two flattened table objects, and five source-declared items:
optical system 300 plus Examples A, B, C, and D. Claim 1 is the only claim that does not
refer to another claim; claim 20 expressly operates the camera according to claim 1.

## Prescription boundary

Paragraphs 40-48 and Tables 1-2 publish the only ordered optical prescription. Table 1
identifies object surface 0, shell surfaces 1-2, four internal lens elements on surfaces
3-8 and 10-11, aperture stop surface 9, and image surface 12. The same table directly
publishes reference wavelength 525 nm, spectral range 450-600 nm, infinite-conjugate EFL
0.6061 mm and F/NO 4.3708, used-conjugate finite F/NO 4.5005, 10.0000 mm object distance,
and 88-degree semi-field. Table 2 publishes five-wavelength indices for four named Schott
glasses and acrylic.

This is not converted. The used prescription includes `DECENTER(1)`, which establishes a
new coordinate system with X=Y=0, Z=3.5000 mm and zero rotations. `PatentSurface` and
`PatentSurfaceInput` have no coordinate-break fields, while the readout builder always
creates ANG fields for infinity-conjugate replay. Replacing the finite object, deleting the
coordinate break, or folding it into an inferred spacing would alter source geometry.
System 300 therefore remains an exact `parser_review_required` item with no worker call.

Examples A-D publish only lens-holder, traction-cord, controller, tether, wire-loop,
method, or electromagnetic packaging around the already disclosed lens 114/system 300.
Example D explicitly says lens 2124 may reuse lens 114 properties; it supplies no new
ordered prescription. All four wrappers are source-proven `confirmed_no_prescription`.

## Original-raster review

The official 3,029,713-byte PDF has 37 image-only pages: one cover, one reference page,
17 drawing sheets, and 18 specification/claim pages. Original 2560×3300 rasters were
retained losslessly. Pages 25-27 confirm the printed Table 1/Table 2 layout and the
transition to Example A. No enhancement, drawing measurement, numeric raster
transcription, or raster-derived inference was used; HTML remains the numeric authority.

## Replay and residual census

Append-only replay attempts 2 and 3 are semantic-equal after removing only
`result_attempt`, at
`3eba8d05770ceac2c14d26f772d7a3ef3692de22835e461f4ed0338cc5430e64`.
The latest result has one parser-review item and four confirmed-no-prescription terminals,
with zero conversion requests, receipts, fingerprints, candidates, staging outputs, formal
intake, or CODE V calls. Strict replay passes 619/619 with zero missing/corrupt roots. The
byte-identical repeated generic censuses reduce the residual from 73 to 72 at result set
`80a90c22445f45e69a987dad0aeda4fb2c7c32ac0d6944d0aedda81281dc0ad5`.

Global patent saturation remains incomplete. Stable ordering selects Family `96807780`,
root/publication `US-20250389925` / `US-20250389925-A1`, next.
