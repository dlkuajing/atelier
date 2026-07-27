# Family 97520644 exact-source audit

## Authority and identity

The classification authority is retained official USPTO PPUBS publication
`US-20260086330-A1` at
`data/patent-lake/uspto-ppubs-html/US-PGPUB/f75c482ad2f0af84/US-20260086330-A1.html`.
The 67,679-byte HTML hashes to
`f75c482ad2f0af84f8b2c744a1261bdce9790723188a0b17ad762fea0db05e40`;
its normalized 50,074-character text hashes to
`d7462ed9f68cc4a762e829a58bad5566ebebceaae7527b9104a11e8614b8829a`.
It directly binds application `19/091567`, Family ID `97520644`, inventors Ju
Yeon Jo and Ju Hwa Son, Samsung Electro-Mechanics Co., Ltd. as applicant and
assignee, and Korean priority application `10-2024-0128342` dated 2024-09-23.
The exact A1 lists no parent application or pre-grant family member; no external
family member supplies classification data.

## Complete source denominator

- Twenty-six Background/Summary paragraphs `[0001]`-`[0026]`.
- Seventy Description paragraphs `[0027]`-`[0096]`: eleven brief drawing
  paragraphs `[0027]`-`[0037]` and 59 detailed paragraphs `[0038]`-`[0096]`.
- Twenty claims, with claims 1 and 10 independent.
- Twelve `TABLE-US` objects, 19 ordered MathML objects, 35 `figref` tags,
  FIGS. 1-10 and ten official drawing sheets.
- Exactly five source items. Paragraph groups `[0070]`-`[0074]`, `[0075]`-
  `[0079]`, `[0080]`-`[0084]`, `[0085]`-`[0089]` and `[0090]`-`[0095]`
  bind embodiments 1-5 to FIGS. 1-10 and prescription pairs TABLES 1/2, 3/4,
  5/6, 7/8 and 9/10 respectively. The general disclosure and claims describe
  those systems and are not additional prescriptions.

The five surface tables publish 79 ordered non-object optical rows. TABLES 1,
3, 7 and 9 each contain S0-S16; TABLE 5 contains S0-S15. The five asphere
tables each bind eight named surfaces and ten rows `K/A/B/C/D/E/F/G/H/J`, for
40 asphere surfaces and 400 published coefficient cells. Equation 1 directly
maps A-H/J to powers r4/r6/r8/r10/r12/r14/r16/r18/r20. TABLE 11 publishes f,
f1-f5, TTL, f-number, IMGHT and FOV for all five embodiments; TABLE 12 publishes
twelve condition rows for all five.

## Published prescription and terminal boundary

S0 directly publishes finite object distances `(580, 580, 600, 580, 600)` mm;
none is infinity. Embodiments 1, 2, 4 and 5 publish Stop S3. TABLE 5 for
embodiment 3 publishes no stop row, while paragraph `[0083]` states only that
the stop may be on the object side of the first lens and gives no axial
coordinate.

TABLE 11 directly prints FOV values `(57.5, 56.6, 57.6, 57.5, 57.4)` degrees,
but the exact publication defines FOV only as “a field of view of an imaging
lens system.” It never states whether FOV is a half, semi or full angular field.
The drawings and official rasters add no such printed semantic declaration.
FOV therefore cannot be divided by two or replaced by an angle derived from f
and IMGHT.

All five source prescriptions close as `metadata_unpublished`: items 1, 2, 4
and 5 lack half/full angular-field semantics; item 3 additionally lacks an
exact stop coordinate. No value is derived, repaired, interpolated, synthesized,
borrowed from another publication, transcribed from a raster or substituted at
infinity. No worker, conversion request, receipt, prescription fingerprint,
candidate ZMX, staging ZMX, formal intake record, expert verdict or CODE V call
is created.

## Official raster audit

The official 21-page PDF endpoint was downloaded twice. Both 968,559-byte
wrappers decode to the same ordered page-raster set at canonical SHA-256
`99e11db3aaeb7740f5d4023eab505030d024c8aa7c1d7da0bf4b6e8a5989654f`.
Every page has exactly one raster and no text layer. Pages 14, 15, 20 and 21 are
2550x3300; all others are 2560x3300. The complete contact sheet and original
pages 15-19 were reviewed for printed table boundaries and the FOV/stop
terminal issue.

Only lossless decoding and contact-sheet downscaling were used. There was no
image enhancement, OCR repair, drawing measurement, numeric transcription,
plot sampling, coordinate inference or related-publication borrowing.
