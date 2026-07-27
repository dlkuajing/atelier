# Family 90040108 source audit

The exact retained content authority is `US-12669685-B2`, application
`18/763174`, Family ID `90040108`, titled *Imaging lens system*. The B2 HTML
contains 24 Background/Summary numbered items (the related-application and Field
subsections each have their own item 1), 169 Description paragraphs, 13 flattened
tables, 34 MathML objects, 11 declared figures, and 11 claims. Claims 1 and 11 are
independent. No values are borrowed from continuation parent `18/361662` or either
Korean priority application.

## Source-item reconciliation

The B2 discloses five numerical optical examples plus one electronic-device wrapper.
Examples 1-4 occupy Description paragraphs 59-142 in four 21-paragraph blocks and
bind FIGS. 1-8 to TABLES 1-8. Example 5 occupies paragraphs 143-156 and binds
FIGS. 9-10 to TABLES 9-10. Paragraphs 157-160 bind shared TABLES 11-13 to all five
examples. Paragraphs 161-166 and FIG. 11 describe only a portable electronic device
which mounts one of the preceding systems; they do not disclose a sixth optical
prescription. Paragraphs 1-58 are drawing/common-description material and paragraphs
167-169 are closing material.

TABLES 1, 3, 5, 7, and 9 publish 19, 19, 21, 21, and 15 ordered path rows. The first
four examples have ten lens surfaces and the fifth has eight. TABLES 2, 4, 6, and 8
publish K plus A-J rows for S1-S10; TABLE 10 publishes the same coefficient rows in
S1-S4 and S5-S8 groups. The path tables directly publish lens, prism, filter, image,
refractive-index, Abbe-number, radius, and path-distance values. TABLE 11 directly
publishes five EFL values (`15.000`, `13.992`, `16.420`, `23.000`, `27.188` mm) and
five image heights (`2.00`, `2.00`, `2.00`, `2.00`, `4.20` mm), together with TTL,
BFL, PL, TLG, component focal lengths, and selected radii. Source-printed signs and
digits in TABLE 13 are preserved without arithmetic repair.

The first two systems use four prism reflections, the third and fourth use six, and
the fifth uses two substantially parallel reflective surfaces. Those folds are not
flattened into the sequential `PatentSurface` coordinate contract. More importantly,
the exact B2 has zero matches for stop, aperture, diaphragm, F-number/FNO, numerical
aperture, HFOV/FOV, field-of-view, angle-of-view, angular-field, or field-angle
metadata. The direct `f` and `ImgHT` values are not combined to manufacture an
angular field or F-number. Examples 1-5 therefore terminate as
`metadata_unpublished.system_stop_f_number_and_angular_field_absent`; the device
wrapper terminates as `confirmed_no_prescription.electronic_device_wrapper_only`.
No conversion request, receipt, fingerprint, candidate ZMX, or formal intake is
created.

## Original-raster audit

The B2 original-PDF endpoint and the USPTO endpoint for same-application prior
publication `US-20240353658-A1` returned 404. Two retained Google-delivered copies of
the A1 PDF are byte-identical at
`f5dfc77696fc7e67c2d71578c69000573e43a6028100868ca305d68276b2fa36`.
They contain 27 image-only pages with one raster per page and no text layer. Page 1
is the cover; pages 2-12 are the 11 drawing sheets for FIGS. 1-11; pages 13-27 are
specification/claim pages; TABLES 1-13 occupy pages 19-26 and the claims finish on
page 27.

All table pages and the cover, five system drawings, device-wrapper drawing, and
claim-ending page were reviewed at original raster resolution without enhancement.
They corroborate the same-application layout, multi-reflection diagrams, table
printing, and claim denominator. The reviewed system drawings contain no labeled
stop. No raster numeric cell was transcribed, no drawing geometry was measured, and
the A1 was not used to replace or repair B2 content. Exact hashes and page roles are
recorded in `family-90040108-source-availability.json`,
`family-90040108-source-facts.json`, and `family-90040108-raster-audit.json`.

## Validation

Append-only attempts 2 and 3 each contain the same five metadata-unpublished
prescriptions and one confirmed-no-prescription wrapper. Removing only
`result_attempt` yields identical business semantics at
`4a0f2aa9910202287c393b035637349b8f8d3a236c1bed5a4808bc243e8a5e2c`.
The generic residual falls from 69 to 68 roots/items, and two independent census
builds are byte-identical at
`87016da3edb4a25dd8c4f2f2c272dbe1245b165b9a4e5ff1d23d3dcf191ad153`.
The strict replay audit covers 619/619 roots with no missing or corrupt result.

The full offline run reached 3529 passes before exposing five evidence-test
failures caused by one accidentally renamed historical PDF-test variable and four
live result-set pointers left at the preceding shovel. After those narrow fixes,
all 785 patent tests pass; the other 2749 tests had already passed in the full run,
giving complete composite coverage of 3534 passing tests, one skip, and ten
explicitly deselected real-machine tests. The five CODE V subprocess guards,
focused source/raster/replay tests, Ruff, compilation, changed-JSON, historical
evidence-reference, formal-output, contamination, protected-path, diff,
primary-repository, and read-only CODE V inventory audits pass. The sealed aggregate
evidence manifest is rehashed by a separate post-seal regression test.
