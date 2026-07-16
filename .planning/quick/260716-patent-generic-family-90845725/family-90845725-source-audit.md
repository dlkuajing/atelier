# Family 90845725 source audit

## Identity and family boundary

- Frozen root `US-20250271635` resolves to application publication
  `US-20250271635-A1`, application `18/731404`, Family ID `90845725`, owned by
  Changzhou AAC Raytech Optronics Co., Ltd., with priority
  `CN202410202541.6` dated 2024-02-23.
- Google Patents reports the US application as pending and records an allowance notice, not a US
  grant publication. The frozen US publication denominator therefore remains one root.
- `CN-117970643-A`, `JP-7610062-B1`, and `JP-2025129108-A` are outside the frozen 619-root cohort
  and are retained in `family-90845725-external-family-members.json`. Current replay completeness
  is not extended to those publications.

## Text, embodiments, figures, and tables

- Exact official HTML SHA-256
  `36dafd2330f060721180c55b169135401815d1dc73e39af434b2912e2037957b` and normalized SHA-256
  `f0f9d8e1b241c27ff4508d009b9eb09b76e0bb320ce28f3e34b8de59e9730d9d` bind the source profile.
- The source declares exactly `First Embodiment [0052]` and `Second Embodiment [0093]`, plus
  FIGS. 1-10. FIGS. 1/6 show the two optical configurations; FIGS. 2-4 and 7-9 show dot-column,
  lateral-color, field-curvature, and distortion results, while FIGS. 5/10 show the corresponding
  film structures. None is declared as an additional embodiment.
- TABLES 1/3 publish the two folded, repeated reflective surface/path prescriptions. Their
  negative path increments are preserved exactly; no sequential positive-spacing repair is made.
- TABLES 2/4 publish R1-R6 conic and A4-A16 coefficients. TABLE 5 publishes direct `f2/f`, radius
  ratios, SDmax, eyebox, TL, TTL, image height, and diagonal FOV for both embodiments.
- The source directly publishes ENPD 4.00 mm for both embodiments, image heights 11.500/11.200 mm,
  and diagonal FOV 89.94/94.95 degrees. It defines its d-line as 540 nm; that source value is
  retained rather than silently normalized to a conventional wavelength.

## Required metadata and raster denominator

- Neither the official HTML nor any page raster publishes a direct numeric system EFL or system
  F-number. Symbolic `f2/f`, the pupil diameter, track lengths, image height, and reflective path
  are not used to derive either missing value.
- Two independently fetched official wrappers each contain 14 image-only pages. Every decoded
  raster agrees across the two wrappers at raster-set SHA-256
  `de04138e3144763f019e056ac4a4889a6ca32e9f96edd9fb73a2a6b278f1977f`.
- Pages 2-7 are the six drawing sheets containing FIGS. 1-10; TABLES 1-5 span pages 11-14. Page 1
  is the cover and pages 8-14 contain the description/tables. All pages were included in the
  retained contact sheet and raster audit.

## Outcome

- Both disclosed prescriptions are source-proven
  `metadata_unpublished.prescription_specific_efl_and_f_number_absent` terminals.
- Any raw/normalized source, identity, embodiment heading, table digest/role, reflected path,
  system row, figure denominator, or required-metadata drift reopens both items to parser review.
- Attempts 2/3 contain no conversion request, worker receipt, prescription fingerprint,
  candidate, or ZMX. The near-eye design is not asserted to be production-validated.
