# Family 90454980 source audit

## Exact identity and provider boundary

- The retained classifier source is `US-12669686-B2`, application `18/370671`, applicant
  `SAMSUNG ELECTRONICS CO., LTD.`, and PPUBS Family ID `90454980`.
- Its title is *Camera module with reflective and refractive member and electronic device
  including the same*. The same application was previously published as `US-20240094515-A1`
  under the shorter title *Camera module and electronic device including the same*.
- The official B2 source claims Korean priorities `10-2022-0118722` (2022-09-20) and
  `10-2022-0153925` (2022-11-16), and identifies parent application
  `PCT/KR2023/014316`.
- Google's A1 page displays provider-local Family ID `90244971`, whereas the retained PPUBS B2
  displays Family ID `90454980`. Neither identifier is rewritten or asserted equal; the replay
  ledger remains bound to the exact PPUBS value and root `US-12669686`.

## Complete source denominator

The raw official HTML SHA-256 is
`1f70d988271192e12f7ca1c6f557cea92a571323fed6f1550da08bad050c32c1`; normalized text SHA-256
is `9122a77ce59e2a85b5e504053ee02b488f28024aab02f42369c1985b783f9002`.
The source contains background paragraphs 1-5, summary paragraphs 6-9, drawing-description
paragraphs 1-23, detailed-description paragraphs 24-169, and claims 1-13, all contiguous. It has
zero PPUBS tables. The 22 actual figure panels are `1`, `2A`, `2B`, `3-11`, `12A`, `12B`, and
`13-20`.

The detailed description explicitly closes two main embodiments: FIGS. 1-10 use reflective and
refractive member 300 with separate incident and exit surfaces and a parallelogram section;
FIGS. 11-20 use member 400 with incident and exit portions on the same first surface and a
trapezoidal section. Each main embodiment contains four architecture/simulation pairs: 3/4, 5/6,
7/8, and 9/10 for the first; 13/14, 15/16, 17/18, and 19/20 for the second. Thus all eight
stray-light simulations are covered by two source-declared main terminal items rather than being
silently discarded.

## Official PDF denominator

The B2 official PDF was fetched independently twice. Both 40-page wrappers have distinct
container hashes but all 40 canonical decoded page rasters agree. PDF page 1 is the cover, page 2
contains references, pages 3-24 are the 22 consecutive drawing sheets, pages 25-39 contain the
specification, and claims begin on logical page 30 within PDF page 39 and end on PDF page 40.

The same-application A1 official PDF and Google-hosted PDF also have distinct container hashes and
all 40 decoded page rasters agree within that publication. A1 page 1 is the cover, pages 2-23 are
the 22 drawings, pages 24-38 contain the specification, and claims begin on internal page 15
within PDF page 38 and end on page 40. The B2 and A1 canonical rasters differ at all 40 page
positions. Their page boundaries, text, claim counts, and numeric content are therefore retained
separately; A1 is identity/family/visual cross-check evidence only.

## Prescription determination

The lens group is described as one lens or a configurable plurality, illustrated with L1-L4.
There is no ordered surface row, radius, thickness, material assignment, asphere coefficient,
exact system EFL, or F-number. The single `effective focal length` occurrence is folded-path
background. The remaining focal-length and FOV occurrences explain generic wide/tele packaging
and a device-level 5-35 degree range.

Formulas 1-3 constrain cutting-plane angles, formula 4 constrains dispersion/Abbe of the
reflective/refractive member itself, formula 5 constrains device/lens-assembly FOV, and formulas
6-9 constrain cutting-plane length relative to sensor image height. The two `refractive index`,
three `Abbe`, two `curvature`, and three `dispersion` occurrences are member-material or aberration
narrative, not lens prescription rows. Full PDF inspection found only symbolic lens groups,
member/cutting-plane geometry, and stray-light simulation maps. Both main embodiments are
therefore source-locked `confirmed_no_prescription` architecture terminals; no conversion request,
receipt, fingerprint, candidate, or ZMX may be created.
