# Family 97303742 source audit

## Scope and identity

The frozen 619-root cohort contains root `US-20260063876`, publication
`US-20260063876-A1`, application `18/932225`, Family ID `97303742`, titled
`PHOTOGRAPHING OPTICAL LENS ASSEMBLY, IMAGE CAPTURING UNIT AND ELECTRONIC DEVICE`.
The retained official source identifies Largan Precision and priority to Taiwan application
`113133435`, filed 2024-09-04. Its exact Google wrapper lists the US application as pending and
does not identify a US grant. The Taiwan priority representative and CN/DE/GB DocDB records are
queue-only; none supplies numeric truth to the frozen root.

## Exact source denominator

The official HTML has 225,805 bytes, 222,699 raw characters and 178,538 normalized characters;
its raw and normalized SHA-256 values are
`b86b4e046115223760c4139e60c54ef0b3a14e2d8bfa2334388843d4fb57b68d` and
`a1b4dc0b60b9526b01ceff3a53a193189e6048db230939b1a5eea8f5e6a2c6b9`.
Numbered paragraphs are consecutive 1-266: related application 1, background 2-3, summary 4-12,
drawing description 13-58 and detailed description 59-266. The source declares FIGS. 1-45,
claims 1-28, 61 MathML objects and 29 tagged tables. The ordered MathML-ID digest is
`0546402424df3c0dabdbd840437d7fc956c8dabfa059f731e4b303f7792e7dc5`.

FIGS. 1-30 bind three figures to each of the ten optical prescriptions. FIG. 31 binds the image
capturing unit wrapper; FIGS. 32-37 bind the three electronic-device wrappers. FIGS. 38-40 define
first-embodiment geometry, FIGS. 41-43 aperture geometry and entrance-pupil directions, and
FIGS. 44-45 edge trimming. TABLES 1A/1B and 2A/2B/2C through 10A/10B/10C account for all 29
tagged blocks. No declared paragraph, figure, table, MathML object, claim or embodiment is left
unmapped.

## Prescription and coordinate boundary

TABLES 1A through 10A directly publish `f`, `f/EPDmax`, `HFOV`, 17 ordered surface rows, two
stop positions, material/index/Abbe values and a 587.6-nm reference wavelength. The source
explicitly defines HFOV as half the maximum field and EPDmax as the entrance-pupil diameter in
the maximum-diameter direction, so the converter retains these direct values as half-field and
working F-number. TABLES 1B through 10B publish 12 aspheric surfaces per prescription; the
eighth embodiment reaches A14 and the others A10. TABLES 2C through 10C independently repeat
the direct system metadata and full-field values. The first embodiment has no 1C table, but its
1A header directly publishes all required system fields.

The first optical element is a powered prism represented in the official table by two refracting
path surfaces. The source does not publish a separate powered-mirror row, so none is invented.
Embodiments 2, 3, 7 and 8 each publish one negative axial segment adjacent to the zero-power
first stop: after the stop in 2/7/8 and immediately before it in 3. The retained axial-coordinate
reorder produces a sequential 17-surface path with nonnegative thicknesses while preserving the
material span across the stop. No coordinate is synthesized, measured from a drawing or imported
from another publication.

All ten prescriptions pass process-isolated ingestion and produce ten staging ZMX files. Each
has 17/17 radii and thicknesses, 12 aspheres and four or five finite final rays. Embodiments 11-14
add no new surface prescription: 11 is an image-sensor/control wrapper around the disclosed lens
assemblies, while 12-14 are electronic-device arrangements. They are therefore four explicit
`confirmed_no_prescription` terminal items rather than hidden parser failures.

## Official raster and replay evidence

The official PDF has 69 raster-only pages with exactly one image and zero extractable text per
page: cover page 1, 35 drawing sheets on pages 2-36 and specification pages 37-69. The canonical
raster-set hash is `a7539b4c3813a8c8e58196fab9899874c1ca2e135de779c64f1178adc5311227`.
The all-page contact sheet, page 2 and prescription-table pages 47-65 were visually inspected.
The PDF corroborates the HTML; no numeric value was transcribed or derived from raster geometry.

Append-only result attempts 2 and 3 both contain ten `converted_pending_intake` items and four
terminal items. Conversion retries necessarily advance worker attempt IDs, receipt paths and
receipt-file hashes. After normalizing only those runtime identities, `result_attempt`, receipt
retry numbers/runtime paths and elapsed time, the results have equal semantic SHA-256
`bfc5c64ef647997c292d800167b970eb72e26025e09b0bcfe18d3e3c7a5ffa7d`.
Every request JSON, response JSON and candidate ZMX is byte-identical across the two worker
attempts. No outcome field is removed by normalization, no formal intake occurs, and CODE V is
not used.

Strict replay remains 619/619 with zero missing and zero corrupt results. The final result-set
hash is `18e49565f06f31a676036f4f123381f660c7f5b185ba3f0e12a2190169d4dc21`;
root counts are 313 parser review, 147 mixed, 134 terminal and 25 converted, while item counts are
1406 parser review, 1140 terminal, 561 staging and 28 conversion retry. The generic bucket falls
from 124 to 123 roots/items. The two after censuses differ only in their exact result-set hash and
are otherwise semantic-equal. Family `56417699`, root `US-10782453`, is the next stable exact
group. Patent/source saturation and formal intake remain incomplete.
