# Family 23219584 source audit

## Identity and source closure

- Root `US-6292306`, publication `US-6292306-B1`, application `09/314343`,
  Family `23219584`, assignee Optical Gaging Products, Inc.
- Classification truth is the retained USPTO Patent Public Search HTML at raw SHA-256
  `79baca6bd83e0d395aedfb916b7af7afa388706a6030b2706f6ef1c112430ba6`
  plus the official seven-page image PDF at container SHA-256
  `bc113bc6e9130fea7a05ca4cc5d7be394923dbc1fdebe73c75242227a8a81d8b`.
- The HTML contains 10 numbered Background/Summary paragraphs, 19 numbered
  Description paragraphs, five declared figures, 17 claims, zero tagged tables, zero
  MathML objects and zero image tags. Two optical tables are flattened into Description
  paragraphs 14 and 16. All sections, paragraph spans, tables and claims are hash-bound.
- The PDF has seven image-only pages, one 2320x3408 raster per page and no text layer.
  Pages 2-3 contain the two declared drawing sheets; the Lens Table spans pages 5-6 and
  the Magnification Table is on page 6. The decoded raster-set SHA-256 is
  `6baf8536ec8d590fd70816b35081847c41a5911af359826ecfc29d5fe37caebb`.

## Numerical disclosure

The source discloses one telecentric zoom system, not four independent prescriptions.
The common Lens Table publishes 27 radii from S2 through S30 (with S9, the stop, and S18,
the first image plane, implicit) and 17 glass-element thickness/material entries. The
Magnification Table publishes four system states:

| Magnification | stop diameter (mm) | X (mm) | Y (mm) | Z (mm) |
|---:|---:|---:|---:|---:|
| 0.8x | 2.6 | 58.8 | 3.9 | 25.2 |
| 1.8x | 6.0 | 44.0 | 0.5 | 43.4 |
| 4.8x | 16.0 | 16.6 | 4.6 | 66.7 |
| 8.0x | 27.0 | 1.3 | 12.9 | 73.7 |

X binds the field group 25 to moving group 33, Y binds groups 33 and 34, and Z binds
group 34 to final image plane P2. The source also publishes a constant image F/20 and the
range notation 0.8x F/25 through 8x F/2.5.

## Fail-closed representability finding

The source does not publish the fixed sequential air spacings S5-S6, S8-stop,
stop-S10, S12-S13, S14-S15, S24-S25, S26-S27 or S28-S29. Qualitative language such as
"slightly spaced" and "spaced confronting" does not provide coordinates. S2 is expressly
aspheric, but the source publishes no conic or asphere coefficients. It also publishes no
system effective focal length, image height or prescription-specific angular field. The
published F-number data do not supply those missing quantities.

Paragraphs 3, 4 and 19 mention five dependent variants: an achromatic retardation-plate
and air-spaced objective, commercial infinity-corrected objectives, changed fixed-group
powers, non-cam motion, and a changed/additional rear group. None is an independent
numerical prescription, so all remain mapped within the same source item.

The retained terminal is therefore:

`metadata_unpublished.required_fixed_air_spacings_asphere_coefficients_and_system_focal_length_field_absent`

No drawing measurement, coordinate synthesis, asphere substitution or related-family
numeric borrowing was used. No worker request, prescription fingerprint, candidate ZMX,
staging ZMX, intake record or CODE V call was created.

## Replay and queue

Append-only attempts 2 and 3 are semantically identical after removing only
`result_attempt`; their canonical semantic SHA-256 is
`0e5314f3793453d4414ed0551ec7d6c529c346a3174a615f708a5f64eabe737c`.
The strict replay remains 619/619 roots with no missing or corrupt result. Two independent
generic residual censuses agree at 94 roots/items and result-set SHA-256
`10baa7c069cf8619b947e5ccffaaee58299c09c52569659ed65ba7cba6ca0540`.
The deterministic next exact group is Family `94819907`, root `US-20260189780`,
publication `US-20260189780-A1`. Global saturation remains incomplete.
