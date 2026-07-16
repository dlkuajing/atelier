# Family 39526858 source audit

## Identity and relationship

- `US-20160088216-A1` and `US-9699370-B2` are the same application `14/958173`,
  Family ID `39526858`, and title `Apparatus and method comprising deformable lens element`.
  B2 Prior Publication Data names A1. Both records identify provisional applications
  `60/961036` and `60/875245` and the same continuation/divisional chain through applications
  `13/964801`, `12/901242`, and `11/897924`.
- `Hand Held Products, Inc.` occurs twice in A1 (applicant plus the Example 1 IT5000 vendor
  reference) and three times in B2 (applicant, assignee, and the same Example 1 vendor reference).
  Retained official HTML SHA-256 values are
  `041e2e327a607a20c6f625fa2ae0564e01ba97eb619c0a1dc58ca74a3e97c38f` (A1) and
  `88d9daf89b28d35136db8a275cfa6928e7d7ed2f80e1eae72635ded465457d96` (B2).
  Parser-normalized hashes are
  `1c68002ba8e35f10315564a2800c913f8175704ecf28d18988bf878c529aa3f1` and
  `3d8a5f8e677dc57ee70f3a8090ed6e2fee8f6ead1f42460f3d0c2f247e070189`.
- Cross-reference paragraph `[0001]` names the three parent applications, their A1 publications,
  and grants. None of those six roots is in the frozen 619-root cohort; they are retained in
  `family-39526858-external-family-members.json` for post-frozen intake. Later paragraphs name
  incorporated but non-chain applications and are not silently promoted into this family queue.

## Source denominator and binding

The publication has one formal heading, `Example 1`, and one matching `End of Example 1` boundary.
The other uses of “example” or “embodiment” describe components, material samples, force profiles,
or terminal-control variants, not separately declared optical prescriptions. The one terminal item
therefore accounts for the formal example and the complete unnumbered actuator/imaging-terminal
architecture instead of manufacturing artificial prescription items.

The generic census reported zero tables because these sources label their four PPUBS tables with
letters rather than numbers. Exact inspection establishes the complete denominator:

1. TABLE A lists four silicone materials and sample properties such as refractive index, Young's
   modulus, temperature range, elongation, and Shore hardness.
2. TABLE B compares force-impartation profiles, directions, contact patterns, and push/pull effects.
3. TABLE C reports Example 1 actuator voltage, actuator/pressure-element movement, and best-focus
   distance.
4. TABLE D maps exposure periods to lens settings for seven terminal-control configurations.

The table-only normalized SHA-256 values are source-locked separately because A1/B2 wrappers and
the A/B column order differ. TABLE C is
`298c7208ed2077f62f7ec40481e6cfe5c5627cc28f8ecdb65d12a6c8d880fe85` and TABLE D is
`3d9f239b2926c84f8e066144894dff87dda8eeeb09e6a9494348fec386586188` in both records.
TABLE A/B hashes are `f9098ad5...59cc` / `3aafdbc4...eac9` in A1 and
`ba57630b...f4e3` / `a5314a30...ab7b5` in B2; the audit JSON retains every full digest.

Example 1 fits the deformable focus apparatus to an existing IT5000 Image Engine lens triplet and
states that external assembly's 5.88 mm focal length, F# 6.6, and nominal 36-inch best focus. TABLE C
then measures the fitted actuator's focus response. No radius, thickness, glass/Abbe sequence,
asphere coefficient, surface number, or angular field is published for the triplet or the deformable
element. The later L1-L7 values are focus distances/control states, and the prose merely says each
setting may have a different “half FOV” angle without publishing a numeric angle.

The drawing description contains 25 declaration rows expanding to FIGS. 1-28. They cover exploded
assemblies, cutaways, force-contact patterns, lens-assembly placement, electronics, timing, autofocus
flow, and a handheld terminal. They do not supply an ordered surface prescription.

## Official-raster reconciliation

Both official PDFs are image-only, contain one decoded 2560x3300 grayscale image per page, and have
no text layer. Two independently downloaded wrappers were retained per publication. Wrapper bytes
differ, while every decoded page raster is identical within each publication. All 37 A1 pages and
all 39 B2 pages were decoded, hashed in order, and inspected through all-page contact sheets plus
full-resolution table/result pages.

| Publication | Drawing pages | Table pages | Retained PDF SHA-256 | Second wrapper SHA-256 | Stable raster-set SHA-256 | Contact SHA-256 |
|---|---|---|---|---|---|---|
| A1 | 2-17 | 23-24, 26-27, 31 | `5cca82a96d0dfe454c1d6029eaec19eb5b63e026527c8eee5ab4314b7d7e09b7` | `20c8cc0063952e41bfb8cf4c007626e01edc3386eae6bd2548bcc313d5d8c6ca` | `a5bbf2230633d036bf8efd8f36ba0f0668edc1ebbef6ca5111f0aaccf905a67e` | `2af3972cab071bdd0cd5b3bae28451fcf03fa4328c717af30f1203c251908788` |
| B2 | 5-20 | 26, 29-30, 34 | `2a631c8fe45b5caf21a901a49f7762db7e51774fd14dad9f368fe9c890fd3d09` | `36b63b5a2f01e3b8a8361a077908f8d985153d873a008462c797e5bf1e23b913` | `ff10088b31f40a1d83ea1d391ee485d6f2ef9800c5c465daafd3a3ddfa56e4df` | `0c86355307bf27db6f4a4fae73ef9dd985c59dec16a29f2eb9627f10827c55d2` |

## Fail-closed outcome

Each exact source yields one `confirmed_no_prescription` item with reason
`confirmed_no_prescription.deformable_lens_actuator_and_imaging_terminal_architecture_only`.
It receives no conversion worker, request, receipt, prescription fingerprint, candidate, or ZMX.

Raw/normalized identity, title, family, application, owner, relationship markers, the single formal
example boundary, all four table digests and roles, all 28 figures, and key Example 1/control phrases
are fail-closed. Source drift, table drift, drawing drift, or a newly published surface-prescription
marker returns the item to parser review.

Attempts 2 and 3 are append-only and byte-distinct only because of `result_attempt`; their canonical
semantic SHA-256 values are
`f49fe18bb830166ea266dad48716e09036eb5c790017735495286ce25a571102` (A1) and
`a7eae05d7901b15cc1ed74c7ca0c54341b2fc82eb5cd6416df670bfb77635a2a` (B2).
The resulting strict 619-root set is
`d1e244e12272e9752d3771da5e2d9ac1b193eae8e85983635054b4f5b0029981`, with no missing or
corrupt result. The generic census moves 165 to 163 roots/items; the independently repeated after
artifact is `334d9fb747e3f9c2adb3f2003a6f41291b109dab0c8f06ead8b96c1a5dfb7ce5`.
