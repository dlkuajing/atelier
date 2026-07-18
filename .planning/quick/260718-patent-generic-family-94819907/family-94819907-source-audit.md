# Family 94819907 source audit

## Identity and denominator

The retained USPTO Patent Public Search publication is `US-20260189780-A1`,
application `19/549670`, Family ID `94819907`, filed 2026-02-25 and published
2026-07-02 for Samsung Electronics. It claims Korean priorities
`10-2023-0111980` (2023-08-25) and `10-2023-0157729` (2023-11-14) through
`PCT/KR2024/011471` (2024-08-05).

The exact normalized source contains 134 consecutive numbered paragraphs, 20
claims, FIGS.1-8, zero tagged optical tables, one MathML object and zero HTML image
tags. The MathML object is the Lucas–Kanade optical-flow equation referenced by
paragraph 72 for estimating animal pixel motion; it is not an optical lens
prescription. Paragraphs 1-7 cover lineage, field/background and three summary
items; paragraphs 8-16 declare the eight figures; paragraphs 17-49 give a generic
electronic-device and camera-module environment; paragraphs 50-126 disclose and
restate the three source items; paragraphs 127-134 are closing boilerplate.

## Optical boundary

Paragraph 35 says only that a generic camera module may include lenses, image
sensors, an ISP and flashes. Paragraph 45 says a generic lens assembly may have
attributes such as view angle, focal length, autofocus, F number or optical zoom.
Paragraph 47 says stabilization may move a lens or image sensor. None binds an
ordered optical surface sequence or publishes a prescription-specific radius,
spacing, material, refractive index, Abbe number, conic, asphere coefficient, stop
location, effective focal length, F-number, image height or angular field.

The official PDF is an exact 2,039,812-byte, 25-page image-only wrapper with one
raster per page. Pages 2-9 are the eight declared drawing sheets; pages 10-23 are
the specification and pages 24-25 are the claims. The all-page contact sheet and
FIG.2 at original resolution were visually reviewed. FIG.2 contains only a
`LENS ASSEMBLY (210)` block inside the camera module; it has no lens cross-section,
surface table or coordinate data. No number was transcribed or measured from a
raster.

## Item reconciliation

1. Paragraphs 5 and 50-115 with claims 1-10 disclose the electronic-device
   animal-motion exposure-control architecture.
2. Paragraphs 6 and 116-125 with claims 11-19 disclose the corresponding operating
   method.
3. Paragraphs 7 and 126 with claim 20 disclose only the computer-readable-medium
   wrapper for that method.

All three are distinct `confirmed_no_prescription` terminals. No coordinate or
metadata is inferred, no related-family value is borrowed, and no worker request,
receipt, fingerprint, candidate/staging ZMX, formal intake or CODE V call exists.

## Replay and queue

Append-only attempts 2 and 3 are semantic-equal after removing only
`result_attempt`. One intervening retry failed during USPTO token acquisition with
`httpx.ConnectError` before an attempt directory was created; it did not alter the
ledger. The final strict audit is 619/619 roots with no missing or corrupt result.
The generic residual falls from 94 to 93 roots/items and the two after censuses are
byte-identical. Global saturation remains incomplete; stable queue ordering selects
Family `44259669`, root `US-8504328`, next.
