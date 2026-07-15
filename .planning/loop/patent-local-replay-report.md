# Frozen local patent-pool replay

## Result

- cohort_sha256: `e809823c709de93f49eb9b2103c4ebcdd9cf7e34d88f45a4953aaa21fd7bb42b`
- frozen_roots: 619
- roots_with_results: 228
- missing_roots: 391
- corrupt_results: 0
- cohort_replay_complete: `false`
- saturation_complete: `false`
- next_missing_index: 228

The replay-complete flag means every frozen local root has one strict current replay result. It
does not mean source saturation, formal intake, production usability, or an expert verdict.

## Root states

- `converted_pending_intake`: 2
- `terminal`: 7
- `parser_review_required`: 165
- `source_retry_required`: 3
- `source_exhausted_pending_alternates`: 0
- `conversion_retry_required`: 0
- `mixed_nonterminal`: 51

## Item states

- `converted_pending_intake`: 85
- `terminal`: 303
- `parser_review_required`: 661
- `conversion_retry_required`: 1

## Terminal statuses proven by replay receipts

- `intaken`: 0
- `duplicate`: 0
- `quality_rejected`: 0
- `confirmed_no_prescription`: 0
- `fulltext_unavailable`: 0
- `parser_family_missing`: 0
- `metadata_unpublished`: 0
- `trace_failed`: 243
- `trace_timeout`: 60
- `externally_blocked`: 0

## Root reason codes

- `parser_review_required.all_disclosed_items_rejected`: 165
- `mixed_nonterminal.multiple_item_states`: 51
- `terminal.all_disclosed_items_terminal`: 7
- `source_retry_required.uspto_ppubs_fetch_incomplete`: 3
- `converted_pending_intake.all_disclosed_items_converted`: 2

## Item reason codes

- `parser_review_required.deterministic_parser_rejected`: 661
- `terminal.process_receipt_classified`: 303
- `converted_pending_intake.process_isolated_zmx_ready`: 85
- `conversion_retry_required.patent_budget_exhausted`: 1

## Source attempts

- `retained`: 225
- `http_error`: 2
- `transport_error`: 7

## Parser failure signatures

- `sunny_embodiment_metadata_missing`: 202
- `sunny_surface_value_not_numeric`: 81
- `generic_summary_metadata_missing`: 72
- `aac_raytech_summary_metadata_missing`: 63
- `generic_numeric_token_rejected`: 48
- `asphere_section_missing`: 37
- `sekonix_radius_not_numeric`: 32
- `other_sunny_s1_row_has_unexpected_extra_values_n_n_n`: 29
- `generic_surface_radius_not_numeric`: 25
- `generic_surface_table_index_break`: 16
- `asphere_surface_header_missing`: 10
- `ocr_corrupted_exponent`: 6
- `other_sunny_s3_row_has_unexpected_extra_values_n_n_n`: 6
- `sekonix_surface_row_incomplete`: 6
- `other_sunny_sto_value_is_not_numeric_surface`: 5
- `other_validationerror_n_validation_error_for_patentsurfaceinput_thickness_mm_input_should_be_a_finite_number_type_a33fea814b08`: 5
- `other_sekonix_glass_code_cannot_be_split_deterministically_bk7_schott`: 4
- `other_sunny_asphere_row_s7_has_more_values_than_headers_token`: 3
- `other_sunny_asphere_row_s5_has_more_values_than_headers_token`: 2
- `other_unsupported_nonzero_aac_raytech_asphere_term_r4_a2_n`: 2
- `other_aspheric_row_k_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_sunny_asphere_row_s12_has_more_values_than_headers_token`: 1
- `other_sunny_asphere_row_s1_has_more_values_than_headers_token`: 1
- `other_sunny_s15_row_has_unexpected_extra_values_n_n_n_n`: 1
- `other_sunny_s7_row_has_unexpected_extra_values_n_n_n_n`: 1
- `other_sunny_sto_value_is_not_numeric_s7_aas`: 1
- `other_surface_n_material_nd_vd_outside_physical_bounds_nd_n_allowed_n_n_vd_n_allowed_n_n`: 1
