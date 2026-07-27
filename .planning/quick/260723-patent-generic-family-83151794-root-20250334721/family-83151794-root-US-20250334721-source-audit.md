# Family 83151794 / US-20250334721 source audit

## Scope and isolation

- This shovel covers only root `US-20250334721`, publication
  `US-20250334721-A1`, application `19/260917`.
- The retained A1 identifies itself as a continuation of application `17/820604`
  (grant `US-12379524`), with provisional `63/239434` and Taiwan priority
  `111129234`.
- The parent grant was closed by an earlier shovel, but no value, item boundary,
  classification or outcome from that grant is used here. Every conclusion below is
  independently bound to this exact retained A1.

## Exact source lock

- Retained HTML:
  `data/patent-lake/uspto-ppubs-html/US-PGPUB/b60f9d0e106d0592/US-20250334721-A1.html`
- Raw source: 139,967 bytes / 139,114 characters / SHA-256
  `b60f9d0e106d05922a0c06b41e71fd6f7db784d718d9cda036a1cc56090db4e7`.
- Normalized text: 122,240 characters / SHA-256
  `9fd0a70475d04392eb1d6cc068db85d67fb7300fec92e00d1cb23b6c5b964071`.
- Exact structural hashes for the three sections, all numbered-paragraph sets,
  every item-bearing description span, all 19 table payloads, the ordered 80
  `figref` values and all 13 MathML objects are frozen in the denominator artifact
  and classifier profile. Any raw-source or structural drift reopens all 26 items.

## Complete section denominator

- Background/Summary: paragraphs `[0001]-[0007]`.
- Description: paragraphs `[0008]-[0165]`, continuous.
- Claims: 18, with only claim 1 dependency-free under the exact dependency parser.
- Figures: 19 declared panels (`1` through `6`, `7A`, `7B`, `8`, `9A`, `9B`,
  `9C`, `10`, `11`, `12A`, `12B`, `13A`, `13B`, `13C`) and 80 `figref` tags.
- Equations: 13 MathML objects (`MATH-US-00001` through `MATH-US-00013`) and
  one inline-formula lead/tail pair.
- Tables: 19 machine-readable `TABLE-US` blocks. There are no native HTML table,
  row or cell tags and no embedded images.

The retained machine-readable HTML completely settles the category, table and item
boundaries. An official PDF or raster review was therefore not required or used.
No OCR, enhancement, repair, measurement, raster numeric transcription or numeric
inference was performed.

## Source-item denominator

The exact denominator is 26 items:

1. Thirteen optical/coating architecture datasets (embodiments 1-13; tables 1-13).
   They publish lens composition/order, which lens receives a coating, FOV, TD,
   SDmax, and coating/material/property scalars, but no ordered optical prescription.
2. Six independently identified coating experiments (three comparative and three
   embodiment experiments; tables 14-19; figures 2-7). They publish coating stacks,
   reflectance or oxidation-test data, not an ordered optical prescription.
3. One long-wavelength absorbing/filtering architecture (Background paragraph 7;
   Description paragraphs 50-51).
4. One camera-module wrapper (Description paragraphs 147-149; claim 17; figure 8).
5. Five electronic-device wrappers (Description paragraphs 150-160; claim 18 for
   the vehicle wrapper; figures 9A-13C).

The A1 contains no published scalar focal length, F-number, absolute image height,
radius, curvature, conic, asphere coefficient set, surface-number sequence, optical
prescription or lens prescription. The 250 occurrences of `EFL` occur in ratios or
labels and do not provide a prescription-specific scalar system focal length.

## Classification and safety outcome

All 26 items are exact `confirmed_no_prescription` terminals, split across five
existing reason namespaces: 13 optical/coating architecture, 6 coating experiment,
1 long-wave architecture, 1 camera-module wrapper and 5 electronic-device wrapper.
The classifier launches no conversion worker and creates no request, receipt,
prescription fingerprint, candidate ZMX, formal intake or CODE V call.

The machine-readable denominator and every item binding are recorded in
`family-83151794-root-US-20250334721-denominator.json`. Append-only attempts 2 and 3
both emit the same 26 terminal items and preserve the original attempt 1. After
removing only `result_attempt`, their canonical semantic SHA-256 is identical at
`604c85d75ecdd0c3988ff7f4ec5ae612f6093e5523b5da442e73eeb596cb36ac`.
Strict replay remains 619/619 with zero missing or corrupt results. The generic
residual falls from 6 to 5 at result set
`f295cb3cbb289be12dfdab410a7fb31e7db00339a148f90c43805412c9c68613`;
the two after-census files are byte-identical at SHA-256
`7a5ddea88c97702f732b1bd2e26fa7328933d3c1fff668aff13334bc9767ae92`.
Stable ordering selects Family `51536052` / `US-9835833-B2` next, so parent
saturation remains incomplete.
