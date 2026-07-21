# Family 40641507 exact-source audit

## Exact source and lineage

This shovel is bound only to retained official grant `US-8134609-B2`
(application `12/270586`, Family ID `40641507`). The grant names Kazuya Yoneyama
as inventor and Fujinon Corporation as assignee. Its own bibliographic block prints
prior publication `US-20090128665-A1` dated May 21, 2009, and Japanese priority
application `JP-P2007-298146` dated November 16, 2007. Neither related source supplies
any coordinate or system number to this result.

The retained HTML is 178,194 bytes at SHA-256
`80cac521fccd012f58f16b3081c61c203021dd6a6c6e77e58ef2cc0b83e2c22f`.
Its normalized text is 162,619 characters at SHA-256
`bad86e90c4970f2174acb5b65863be103db9615eb5c8e859ecc01e1ee03fc3be`.
The source has 55 Background/Summary paragraphs, 321 Description paragraphs,
17 claims, nine inline `TABLE-US` blocks, no HTML table tag, no MathML object and no
`figref` tag. Original HTML `<p>/<br>` boundaries, rather than an unrestricted
parenthesized-number regex, establish the paragraph sequence: conditional-expression
and manufacturing-step numerals otherwise create false paragraph matches.

## Source denominator

The 26 brief-drawing paragraphs declare 39 panels across FIGS. 1-24 and the official
PDF prints 22 drawing sheets. The detailed disclosure contains exactly nine source
items:

1. the restoration imaging-system/manufacturing architecture, including systems
   100/100-prime/100-double-prime and restoration-coefficient apparatus variants
   70A/70B/70C;
2. the generic imaging-apparatus wrapper;
3. the onboard wrapper;
4. the portable-terminal wrapper;
5. the medical/endoscope wrapper;
6. ordered four-lens prescription 10A, Example 1, Tables 1-3;
7. ordered three-lens prescription 10B, Example 2, Tables 4-6;
8. ordered three-lens prescription 10C, Example 3, Tables 7-9; and
9. comparative four-lens architecture 10H.

Claims 1, 8 and 13 are independent imaging-system claims. Claims 14-17 map to the
generic, portable-terminal, onboard and medical wrappers. They add neither another
source item nor a separate ordered prescription. Paragraph 157's printed reference to
FIG. 11 while discussing the FIG. 22 automobile remains unrepaired and is recorded as
a source conflict, not silently normalized.

Examples 1-3 directly publish ordered radii, spacings, material index/Abbe values,
asphere coefficients, a diaphragm row, focal length and F-number. Example 2 Table 5
prints surfaces 3-8 and coefficients `K`, `A3` through `A20` (114 numeric coefficient
cells); those printed labels are retained without reindexing. Tables 3, 6 and 9 publish
restoration-performance data but no numeric angular field. The generic system,
four apparatus wrappers and comparative lens publish architecture only and therefore
close as six `confirmed_no_prescription` items.

## Raster-only boundary

Two independently downloaded official PDF wrappers have distinct container hashes but
the same 47 decoded 2560-by-3300 one-bit page rasters. Page 1 is the cover, pages 2-23
are the 22 drawing sheets, pages 24-47 are specification pages, and claims occupy pages
46-47. The 47-page decoded raster-set SHA-256 is
`a161b949c457b8f7a0fce2a20dc172a7991a7740cc4e79059c26103f1f6e3206`.

The complete contact sheet was used only for navigation. Original-resolution pages
11, 13 and 15 confirm the three qualitative lens layouts; page 20 confirms the
comparative layout; pages 39, 42 and 44 confirm printed table boundaries; pages 17-19
show aberration sheets with numeric axis labels. No raster was enhanced, measured,
sampled, OCR-repaired or numerically transcribed. In particular, H/h labels are not
treated as numeric image height and raster labels are not combined with focal length to
derive a field. The exact text publishes only “maximum angle of view” and a symbolic
half-angle variable, with no prescription-specific numeric half/full angular field.
Therefore each of Examples 1-3 closes precisely as
`metadata_unpublished.prescription_specific_angular_field_absent`.

## Replay outcome

Append-only attempts 2 and 3 each contain the same nine terminal items: six
`confirmed_no_prescription` and three `metadata_unpublished`. Removing only
`result_attempt` gives identical canonical business semantics at SHA-256
`dbe0b573e65951e54d49170cb501e3fd321481bb712d41adf4a621a68ade9ac1`.
No conversion worker, request, receipt, prescription fingerprint, candidate/staging
ZMX, formal intake item or CODE V call was created. Strict replay still covers all 619
frozen roots with zero missing or corrupt result. The twice-rebuilt generic residual is
42 roots/items at result-set SHA-256
`23d7eb627685922ade629409ee52569fa196d06332010afbb91b68a2505e3c5a`;
global saturation remains incomplete.
