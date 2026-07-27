# Family 90040110 source audit

## Scope and identity

The frozen 619-root cohort contains two roots from Family ID `90040110`:
`US-12386154` (`US-12386154-B2`, application `18/362008`) and its continuation root
`US-20250327997` (`US-20250327997-A1`, application `19/259670`). Both identify Samsung
Electro-Mechanics and the same three Korean priority applications. The B2 names prior publication
`US-20240168265-A1`; the continuation A1 carries the normalized parent/child markers linking it to
application `18/362008` and grant `US-12386154`. The prior A1 and all retained KR/TW family records
are queue-only because they are outside the frozen cohort.

## Exact source denominator

The continuation A1 contains paragraphs 1-175, claims 1-9, FIGS. 1-20 (24 actual panels because
FIGS. 5A-5E are distinct panels), 15 tagged HTML tables and four MathML objects. Its official PDF
has 33 image-only pages: cover page 1, 18 drawing sheets on pages 2-19 and specification pages
20-33. The B2 uses grant-style paragraph-number resets: Background 1-22, drawing-description
paragraphs 1-19 and detailed-description paragraphs 20-169, followed by claims 1-9. It declares
the same 20 figures/24 panels and 15 tables. Its 33-page official PDF has cover page 1, references
page 2, 18 drawing sheets on pages 3-20 and specification pages 21-33.

Each PDF page has zero extractable text and exactly one embedded page image. The retained A1 and
B2 raster sets hash independently to
`7241833a92e68c78fed1e28ddf5e2c17d18944593cba2dcd209b63ded1e2468f` and
`6972325da0cebecad662f50b946977d13f6c93a05b8ff564ac36ede36e100fa6`.
All-page contact sheets and both page-32 table pages were inspected. The PDF rasters are visual
corroboration only; no coordinate or missing system value was transcribed or derived from them.

## Prescription and metadata boundary

Tables 1/2 through 11/12 disclose six complete four-lens folded-path surface/asphere table pairs.
The surface sequences are S1-S19, S1-S17, S1-S17, S1-S15, S1-S19 and S1-S19. Every coefficient
table has two header groups and publishes `K,A,B,C,D,E,F,G,H,J`, where the source formula binds
`A-H,J` to even radial powers 4 through 20. Tables 1-13 have byte-stable common numeric payloads
between the B2 and continuation A1. Table 13 directly publishes overall `f`, lens focal lengths,
TTL, BFL and ImgHT for all six embodiments; Tables 14-15 publish condition ratios.

Neither exact official HTML contains `F-number`, `FNO`, `F/#`, `F/No`, numerical aperture,
`HFOV`, `FOV`, field-of-view, angle-of-view, angular-field, field-angle or vision-field metadata.
The two page-32 rasters visibly confirm that Tables 13-15 add no such values. F-number is not
computed from any aperture geometry, and angular field is not derived from focal length and image
height. Therefore each root yields six
`metadata_unpublished.prescription_specific_f_number_and_angular_field_absent` terminals. The
FIG. 20 electronic-device description only mounts the already disclosed imaging system and image
sensor, so each root also yields one
`confirmed_no_prescription.electronic_device_wrapper_only` terminal. There is no seventh optical
prescription.

## Replay result

Append-only attempts 2 and 3 are semantic-equal per root after removing only `result_attempt`.
Each attempt contains seven terminal items: six metadata-unpublished prescriptions and one
confirmed-no-prescription wrapper. No conversion worker, request, receipt, prescription
fingerprint, candidate or ZMX exists for either root.

Strict replay remains 619/619 with zero missing and zero corrupt results. The result-set hash is
`3cebf1af8fdca1a2b6163da8c257a5538268bdf8f897714532745ccc36f06926`; root counts are 316
parser review, 146 mixed, 132 terminal and 25 converted, while item counts are 1407 parser review,
1122 terminal, 551 staging and 28 conversion retry. The generic bucket falls from 129 to 127
roots/items, and two independent after-census builds are byte-identical. Family `91069629`, root
`US-20240168282`, is the next stable exact group. Patent/source saturation remains incomplete.
