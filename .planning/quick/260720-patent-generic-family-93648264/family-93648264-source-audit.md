# Family 93648264 source audit

## Scope and identity

The frozen 619-root cohort contains root `US-20250231379`, publication
`US-20250231379-A1`, application `18/651427`, Family ID `93648264`, titled
`IMAGING OPTICAL LENS SYSTEM, IMAGE CAPTURING UNIT AND ELECTRONIC DEVICE`. The retained
official source identifies inventors Kuan-Ting Yeh and Cheng-Yu Tsai and applicant/assignee
Largan Precision. It claims provisional priority to `US63/620296`, filed 2024-01-12. The exact
Google wrapper lists the US application as pending and identifies TW, CN and EP records outside
the frozen cohort. Those records remain queue-only and supply no numeric truth.

## Exact source denominator

The official HTML has 361,259 bytes, 356,220 raw characters and 303,017 normalized characters.
Its raw and normalized SHA-256 values are
`828212012a1d69a52bc19c066023460def0268ac62b3f5f36c2b358bb3eb3984` and
`f6b4724f51c929476d6daad8ab388c87b083555d94ba98c4616b88141107c9f5`.
Numbered paragraphs are consecutive 1-375: related application 1, background 2-4, summary 5-18,
drawing description 19-85 and detailed description 86-375. The source declares claims 1-36,
with independent claims 1, 14, 22 and 31; FIGS. 1-69; 69 drawing sheets; 51 MathML objects; and
43 tagged tables. The ordered MathML-ID digest is
`ce20fc8a599fddd53d5e3dad65a5a178861b5c245965238cd42e78da68c61d5f`.

TABLES 1A/1B/1C and 2A/2B/2C/2D through 11A/11B/11C/11D account for every tagged table.
FIGS. 1-34 bind eleven prescription embodiments and their focus states; FIG. 35 binds the image
capturing unit wrapper; FIGS. 36-41 bind three electronic-device wrappers; and FIGS. 42-69
define lens geometry, aperture shapes, reflective elements and folded paths. No numbered
paragraph, claim, declared figure, MathML object, tagged table or disclosed item is left unmapped.

## Prescription and state boundary

The eleven prescription embodiments publish 23 optical states: two each for embodiments 1-8,
three for embodiment 9, and two each for embodiments 10-11. The first state of every prescription
is an infinity-conjugate state, as is the ninth embodiment's third state, yielding twelve directly
convertible states. The eleven second states explicitly publish finite object distances. The
current replay model is infinity-conjugate, so each finite state is retained as a specific
`parser_review_required` item containing its source object distance; none is collapsed into a
terminal or hidden document-level failure.

TABLE A publishes the ordered surface prescription, TABLE B publishes per-state `f`, `Fno`,
`HFOV`, object distance and variable gaps, and TABLE C publishes the asphere coefficients.
Embodiments 1-10 contain five lenses and 17 sequential rows; embodiment 11 contains four lenses
and 15 rows. Published aspheres extend through A24 in most prescriptions and A26 in embodiment 7.
All source values are taken from the exact A1 HTML. The PDF is used only to corroborate printed
table topology and highest displayed orders.

Several source tables place a zero-power stop inside a signed axial segment. The converter orders
those rows by their published axial coordinates while preserving material spans and without
repairing or synthesizing any number. Embodiment 9's third state publishes `D1=0`; stable source
order therefore preserves `Stop` followed by `L1 S1` at zero gap. Every converted path has
nonnegative sequential thicknesses. No coordinate is measured from a drawing or borrowed from a
related publication.

Embodiments 12-15 add no optical prescription. Embodiment 12 is an image-capturing-unit wrapper
around the disclosed systems, and 13-15 are electronic-device arrangements. They are four
source-proven `confirmed_no_prescription` terminals. The complete ledger denominator is therefore
27 items: twelve staging conversions, eleven explicit finite-object nonterminals and four
wrapper terminals.

## Official raster and replay evidence

Two independent official PDF downloads contain 123 raster-only pages, each with one image and no
extractable text: cover page 1, 69 drawing sheets on pages 2-70 and specification pages 71-123.
The two decoded raster sequences are identical. Their canonical raster-set SHA-256 is
`3dc58099d18b4cd0de4e8ba38a4a3521ef3612e624685835bcebbe8882c33d9d`.
The all-page contact sheet, three table-range contacts and selected original table pages were
visually inspected; pages 87-116 visibly carry TABLES 1A-11D. No numeric value or coordinate was
transcribed, enhanced, measured or inferred from a raster.

Append-only result attempts 2 and 3 each contain twelve `converted_pending_intake` items, eleven
finite-object parser-review items and four terminals. After normalizing only result/worker attempt
identity and receipt runtime paths, retry number and elapsed time, both results have semantic
SHA-256 `6b3aea918004bfc9ea3a499ef336bcd0fd6e038c1712b925e922d66be0002ea5`.
Every request JSON, response JSON and candidate ZMX is byte-identical across retries, and no
outcome field is removed. The twelve converted states produce twelve staging ZMX files with two
to five finite final rays. Formal intake remains zero and CODE V is not used.

Strict replay remains 619/619 with zero missing and zero corrupt results. The final result-set
hash is `4b9cc81951c636135575720182197c0d5c5d994b3bc403baf62a6f225fe1ebc6`;
root counts are 248 parser review, 155 mixed, 189 terminal and 27 converted, while item counts are
1,361 parser review, 1,566 terminal, 603 staging and 28 conversion retry. The generic bucket falls
from 58 to 57 roots/items, and its two final censuses are byte-identical. Family `63252479`, root
`US-20250284086`, publication `US-20250284086-A1`, is the next stable exact group. Patent/source
saturation and formal intake remain incomplete.
