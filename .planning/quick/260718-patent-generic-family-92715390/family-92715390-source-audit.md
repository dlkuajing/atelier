# Family 92715390 Source Audit

## Identity and retained sources

The frozen root is `US-12663695`, publication `US-12663695-B2`, application `18/587176`, Family
ID `92715390`, titled `Camera module`. The retained USPTO Patent Public Search HTML is 144,586
bytes with SHA-256
`344973b24234452b0a0178358d493bac58dfa26f48b5b7281f52d296782fd19e`. It identifies SAMSUNG
ELECTRO-MECHANICS CO., LTD. as applicant and Samsung Electro-Mechanics Co., Ltd. as assignee,
filing date 2024-02-26 and patent date 2026-06-23. It binds same-application prior publication
US 20240310694 A1 and Korean priorities 10-2023-0034108 and 10-2023-0117213. No PCT application
is declared in the retained source.

The normalized 119,486-character text has SHA-256
`98e14b06e59e9f83872ced3317013cc8575d844e0b858dcd13188d663c445c81`. Exact section and
paragraph-span hashes bind Background/Summary paragraphs 1-34, figure-description paragraphs
1-30, Detailed Description paragraphs 31-378 and claims 1-22. The source contains three claim
families, 29 figure-declaration paragraphs naming 30 figures, zero tagged tables and zero MathML
objects.

The anonymous-token USPTO image endpoint returned a 43-page raster-only PDF. The retained
2,608,048-byte container has SHA-256
`b37eaa8fa35e054a46a6e44fb2d41ab7523caea7cba799867fae469fee2a247d`. A repeat request
regenerated different container metadata but produced the same 43 decoded page rasters. Their
ordered set SHA-256 is
`f1a90812378ea669b063966ec2e914e95e9e34e4999823119f4af4be1398988a`. PDF pages 3-26 are
24 drawing sheets; every declared label from FIG. 1 through FIG. 30 is located exactly once. All
43 pages and all three contact sheets were reviewed.

## Complete disclosed-item denominator

The Detailed Description has two large camera-module embodiments, one separately developed
first connection-substrate architecture and two explicitly illustrated modified connection-
substrate layouts. Splitting the first large embodiment at its source transitions yields six
non-overlapping ledger items that together cover every substantive paragraph 46-377:

1. First camera-module and aperture-module architecture, paragraphs 46-178.
2. Camera-actuator, lens-barrel, focus/shake motion and sensor architecture, paragraphs 179-308.
3. First connection-substrate support architecture, paragraphs 309-334.
4. Second camera module with dual aperture-substrate extensions and RF-PCB support,
   paragraphs 335-368.
5. FIG. 29 split support-bridge connection-substrate variant, paragraphs 369-372.
6. FIG. 30 crossed coupling-layout connection-substrate variant, paragraphs 373-377.

Paragraphs 31-45 are common explanation and figure orientation, while paragraph 378 is closing
boilerplate. The three independent claim families (1-14, 15-19 and 20-22) bind combinations of
these already counted camera, actuator, aperture and connection-substrate architectures; they do
not declare unaccounted embodiments. Paragraph 29 of the figure section declares both FIGS. 29
and 30, so 29 declaration statements reconcile to 30 distinct figure labels.

## Prescription boundary

The first item publishes blades, a base, rotating body, aperture driver, magnet/coil portions,
rolling members, guide grooves and yokes. The second publishes a hollow lens barrel that may
contain at least one generic lens, plus focus/shake carriers, magnets, coils, balls, stoppers and
an image sensor. The remaining items publish moving/fixed/support portions, flexible and rigid
printed-circuit structures, solder connections, bends, bridges and coupling layouts.

Five `radius` occurrences describe rotating-body or guide-groove geometry. Ten `curvature`
occurrences describe those guide grooves or a support/bent portion of a connection substrate.
The sole `thickness` occurrence describes a support protrusion relative to a bonding groove.
These are mechanical dimensions, not optical prescription fields. Across the complete HTML and
all official rasters there is no focal length, F-number, field of view, angle of view, lens
element, optical-surface radius, axial spacing, refractive index, Abbe number, conic, aspheric
coefficient, aperture stop, image height, millimetre or nanometre prescription value.

All six source items are therefore exact-source `confirmed_no_prescription` terminals. No
drawing coordinate, mechanical radius/curvature/thickness, generic lens wording, priority value
or prior-publication value is substituted for missing optical design data.

## Replay boundary

Attempts 2 and 3 each contain the same six terminal items and no conversion request, receipt,
fingerprint, candidate or staging ZMX. Removing only `result_attempt` yields semantic SHA-256
`1c830bb25f439f7c4c5c2a89c61f60d6c1c011b669e0377eb0f4899edefe5129` for both attempts.
Strict replay remains 619/619 with zero missing and zero corrupt results. The final result set is
`54db919907e7d97e7dd778ff2d0d72c6112d729ece4bf8b6c291eb428043ed01`; generic metadata falls
from 104 to 103 roots/items. Parent/global patent saturation remains incomplete.
