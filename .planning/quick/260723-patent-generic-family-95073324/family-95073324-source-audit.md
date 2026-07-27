# Family 95073324 source audit

## Frozen publication and lineage

This shovel is source-locked to `US-20260147257-A1` (root
`US-20260147257`, application `19/450317`, Family `95073324`). The retained
official HTML has 117,393 bytes and SHA-256
`32fba3c3e5d4aeb736896604e6feddee077b8cc13b4d7f52fcff31fea9fe5026`;
its normalized text has 94,046 characters and SHA-256
`30721c69736e6659886f44be73cffca671f1e5e6ec7b074f9ede7bc83a700dbb`.
The A1 identifies itself as a continuation of `PCT/CN2023/119853`, filed
2023-09-19. No value is borrowed from that parent or any layout/title peer.

The exact bibliography, section hashes, paragraphs, claims, figures, MathML
objects and all 25 tables are frozen in `family-95073324-denominator.json`.
Background/Summary paragraphs `[0001]-[0009]` and Description paragraphs
`[0010]-[0111]` are each consecutive. Claims are exactly 1-20; independent
claims are 1 (imaging lens assembly), 15 (camera module) and 19 (imaging
device). The ordered figure-reference inventory has 62 occurrences, while the
brief description declares 20 panels: FIGS. 1, 2, 3A-3D, 4, 5, 6A-6B,
7A-7B and 8-15. FIGS. 3A-3D are shared prism-surface alternatives, not four
new numerical examples.

## Exact item denominator

The source directly discloses five numbered numerical examples. Example 1
publishes two independently parameterized optical states, WIDE and TELE, in
Table 3 and binds them to FIGS. 6A/7A and 6B/7B respectively. Examples 2-5
each publish one fixed-focus state. Those six prescription states remain
distinct. The camera-module and imaging-device disclosures are two additional
wrapper items because independent claims 15 and 19 and their corresponding
description/figure scopes add apparatus structure but no new surface
prescription. Dependent-claim variations and generic prism alternatives do not
create an unbounded item set.

The frozen denominator is therefore eight items:

1. Example 1 WIDE, paragraphs 76-80, FIGS. 6A/7A, Tables 1-5.
2. Example 1 TELE, paragraphs 76-80, FIGS. 6B/7B, Tables 1-5.
3. Example 2 fixed focus, paragraphs 81-85, FIGS. 8/9, Tables 6-10.
4. Example 3 fixed focus, paragraphs 86-90, FIGS. 10/11, Tables 11-15.
5. Example 4 fixed focus, paragraphs 91-94, FIGS. 12/13, Tables 16-20.
6. Example 5 fixed focus, paragraphs 95-98, FIGS. 14/15, Tables 21-25.
7. Camera-module/filter/sensor wrapper, paragraphs 32, 50 and 71, FIG. 1,
   claims 15-18.
8. Imaging-device/housing/OIS/lens-driver wrapper, paragraphs 32-33, 43-49
   and 71, FIGS. 2/4/5, claims 19-20.

Every numerical example has a five-table group: ordered surface prescription,
element focal lengths, system metadata, inequality evaluation and asphere
coefficients. Table groups bind at paragraphs 78, 84, 89, 93 and 97. The
source's `Di` definition is the optical-axis distance from surface i to surface
i+1 in millimetres; material indices and Abbe numbers are at the d-line
(587.6 nm). The source asphere equation explicitly permits powers `n >= 3`.

## Lossless conversion boundary

Example 1 Table 1 directly publishes the aperture stop as surface 7 with
`D7=-1.000`. Both WIDE and TELE use that same ordered surface table. The
current safe scalar sequential conversion contract rejects negative thickness;
moving the stop to make the sequence positive would invent a new coordinate
ordering. Both states therefore remain precise, nonterminal
`parser_review_required` outcomes.

Examples 2-5 directly publish nonzero odd radial coefficients on L6 surfaces
14 and 15 in Tables 10, 15, 20 and 25. The exact published decimal strings are
retained in the denominator. Current `PatentSurface`/CODE V `XASPHERE`
conversion supports even radial powers only, so dropping or approximating the
odd terms would lose source truth. These four states also remain precise,
nonterminal `parser_review_required` outcomes.

The camera-module and imaging-device wrappers close as
`confirmed_no_prescription.camera_module_wrapper_only` and
`confirmed_no_prescription.imaging_device_wrapper_only`. The family root is
therefore `mixed_nonterminal`: six nonterminal prescription items plus two
terminal wrappers. No worker request, conversion receipt, ZMX, formal intake or
CODE V call is allowed for this family.

## Official PDF review

Two downloads from the official USPTO URL are distinct PDF containers but
decode to the same 36-page raster sequence, canonical SHA-256
`351e901e52200b2977524874b6993bf2ab076a3d1e5463b750e11310bb6a280a`.
Pages 2-18 are 17 drawing sheets, pages 19-34 are specification pages and
pages 35-36 are claims. The contact sheet was used only for navigation.
Official original pages 22 and 23 were visually inspected only to corroborate
Table 1 topology and the placement of the aperture-stop row; all numerical
evidence comes from exact machine-readable HTML. No OCR, enhancement, repair,
measurement, numeric transcription or numeric inference was performed.
