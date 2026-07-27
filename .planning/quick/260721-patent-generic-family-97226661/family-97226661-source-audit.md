# Family 97226661 exact-source audit

## Identity and lineage

The retained classification source is the official USPTO A1 HTML for
`US-20260043988-A1` (application `19/046138`, Family ID `97226661`). It names
Hag Chul Kim and Seong Il Cho as inventors and Samsung Electro-Mechanics Co.,
Ltd. as both applicant and assignee. The header and paragraph `[0001]` directly
identify only Korean application `10-2024-0105343`, filed 2024-08-07, as
priority. The retained source prints no Related U.S. Application Data. No
unprinted continuation, counterpart or numeric disclosure was inferred or
borrowed.

## Complete source denominator

The exact A1 contains six Background/Summary paragraphs (`[0001]-[0006]`), 22
brief-drawing paragraphs (`[0007]-[0028]`), 150 detailed-description paragraphs
(`[0029]-[0178]`), 16 claims, 26 flattened tables, 31 MathML objects, 64
`figref` tags and 31 declared figures. Claims 1 and 9 are the independent
claims. The 31 figures map one-to-one to official PDF pages 2-32; PDF page 1 is
the cover, and pages 33-54 are the 22 specification pages.

The detailed disclosure resolves to exactly eleven source items:

1. Ten imaging-lens-system embodiments: `[0082]-[0091]`, then nine-paragraph
   spans `[0092]-[0100]` through `[0164]-[0172]`. Each item binds to one
   configuration figure, two aberration figures and exactly one surface/asphere
   table pair.
2. One electronic-device/camera-module wrapper in `[0175]-[0176]`, bound to
   FIG. 31. It may contain any of systems 100-1000 but publishes no additional
   prescription.

Paragraphs `[0029]-[0081]` are shared terminology and system architecture;
`[0173]-[0174]` are shared system/conditional tables; `[0177]-[0178]` are
closing paragraphs. None is an additional source item.

## Prescription content and missing metadata

Tables 1, 3, ..., 19 each directly publish ordered rows S1-S22. S1-S2 are the
prism, S3 is unlabeled, S4-S19 are eight lens elements, S20-S21 are the filter,
and S22 is the imaging plane. Separate wide-angle and telephoto axial-distance
columns publish two zoom states per embodiment. Tables 2, 4, ..., 20 each bind
`k` and coefficients `A-H/J` to all sixteen surfaces S4-S19. The ten optical
items therefore contain 220 ordered surface rows, 160 asphere surfaces, 1,600
conic-plus-coefficient cells and 20 directly published zoom states.

Table 21 directly publishes wide `f=18.70 mm` for all ten embodiments, tele
`f=28.00 mm` for embodiments 1-8 and `f=30.00 mm` for embodiments 9-10, plus
the F-number for both states. Tables 22-26 publish ratios and conditional
values. Source typography is retained without repair: paragraph `[0173]` says
“and it is a focal length” where context suggests `ft`; Table 22 prints
`TTL/2lmgHT` and `BFLw/2lmgHT`; Table 19 prints S22 tele distance `-0.0053`.

Paragraph `[0081]` says only that a stop may be disposed between two lenses.
No table labels a stop or aperture, and unlabeled S3 is not inferred to be one.
Paragraph `[0049]` says only that FOV changes continuously; no direct numeric
angular field is published. Paragraph `[0038]` defines `ImgHT` and says the
aberration figures list `IMG HT`, but the numeric plot labels exist only in the
image-only official rasters. The HTML prose/tables publish only definitions and
`TTL/2ImgHT` or `BFLw/2ImgHT` ratios, not a direct absolute value.

The raster labels were not transcribed. Ratios were not inverted, field was not
derived from focal length and image height, and drawing geometry was not
measured. Thus the ten optical items terminate as
`metadata_unpublished.system_stop_angular_field_absent_and_image_height_raster_only`.
The electronic-device wrapper terminates as
`confirmed_no_prescription.electronic_device_wrapper_only`.

## Official PDF audit

Two independent official downloads are both 2,416,124 bytes but have distinct
container SHA-256 values. Each has 54 pages, one 1-bit raster per page and no
text layer. All 54 decoded page rasters are identical across both downloads and
the pinned first download; their ordered raster-set SHA-256 is
`f25ec6472c8d51db25d564faf20cba6d4b608029e59aa3951a6d7aeb2d044202`.

The retained PNGs are lossless RGB serializations whose three channels exactly
equal the decoded embedded page samples. The contact sheet was used only for
navigation. Original pages 2-4, 32, 39, 52-54 were reviewed for configuration,
plot-label, wrapper, table and claim boundaries. No enhancement, OCR repair,
drawing measurement, plot sampling, raster inference or numeric transcription
was used.

## Replay outcome

Append-only attempts 2 and 3 each retain eleven terminal items and have
identical business semantics after removing only `result_attempt`; semantic
SHA-256 is
`92678db524e8ef31630b38898bf530f93e73c95246b04a6150b07b5a3ec8bcdb`.
No conversion worker, request, receipt, prescription fingerprint, candidate
ZMX, staging ZMX, formal intake or CODE V call was created. The strict replay
audit is 619/619 with zero missing and zero corrupt results. The generic
residual moves from 45 to 44 roots/items.
