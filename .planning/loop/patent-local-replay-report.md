# Frozen local patent-pool replay

## Result

- cohort_sha256: `e809823c709de93f49eb9b2103c4ebcdd9cf7e34d88f45a4953aaa21fd7bb42b`
- frozen_roots: 619
- roots_with_results: 619
- result_file_count: 619
- result_set_sha256: `18a0a3102b5b3c8fedfff26b1500db893e931b3bd0068893133ce9071ef4f036`
- missing_roots: 0
- corrupt_results: 0
- cohort_replay_complete: `true`
- saturation_complete: `false`
- next_missing_index: None

The replay-complete flag means every frozen local root has one strict current replay result. It
does not mean source saturation, formal intake, production usability, or an expert verdict.

## Root states

- `converted_pending_intake`: 19
- `terminal`: 34
- `parser_review_required`: 437
- `source_retry_required`: 0
- `source_exhausted_pending_alternates`: 0
- `conversion_retry_required`: 0
- `mixed_nonterminal`: 129

## Item states

- `converted_pending_intake`: 488
- `terminal`: 689
- `parser_review_required`: 1288
- `conversion_retry_required`: 28

## Terminal statuses proven by replay receipts

- `intaken`: 0
- `duplicate`: 0
- `quality_rejected`: 0
- `confirmed_no_prescription`: 0
- `fulltext_unavailable`: 0
- `parser_family_missing`: 0
- `metadata_unpublished`: 0
- `trace_failed`: 587
- `trace_timeout`: 102
- `externally_blocked`: 0

## Root reason codes

- `parser_review_required.all_disclosed_items_rejected`: 437
- `mixed_nonterminal.multiple_item_states`: 129
- `terminal.all_disclosed_items_terminal`: 34
- `converted_pending_intake.all_disclosed_items_converted`: 19

## Item reason codes

- `parser_review_required.deterministic_parser_rejected`: 1288
- `terminal.process_receipt_classified`: 689
- `converted_pending_intake.process_isolated_zmx_ready`: 488
- `conversion_retry_required.patent_budget_exhausted`: 28

## Source attempts

- `retained`: 619
- `http_error`: 0
- `transport_error`: 0

## Parser failure signatures

- `generic_summary_metadata_missing`: 278
- `sunny_embodiment_metadata_missing`: 199
- `aac_raytech_summary_metadata_missing`: 174
- `sunny_surface_value_not_numeric`: 120
- `generic_surface_radius_not_numeric`: 112
- `asphere_section_missing`: 65
- `sekonix_radius_not_numeric`: 64
- `generic_numeric_token_rejected`: 62
- `generic_surface_table_index_break`: 33
- `other_sunny_s1_row_has_unexpected_extra_values_n_n_n`: 29
- `ocr_corrupted_exponent`: 21
- `asphere_surface_header_missing`: 16
- `other_surface_n_thickness_is_not_numeric_flt`: 11
- `other_sunny_sto_value_is_not_numeric_surface`: 8
- `other_folded_zoom_system_n_surface_index_break_expected_s8_found_s7`: 6
- `other_sunny_s3_row_has_unexpected_extra_values_n_n_n`: 6
- `other_surface_n_material_nd_vd_outside_physical_bounds_nd_n_allowed_n_n_vd_n_allowed_n_n`: 6
- `other_unsupported_nonzero_aac_raytech_asphere_term_r1_a2_n`: 6
- `other_validationerror_n_validation_error_for_patentsurfaceinput_thickness_mm_input_should_be_a_finite_number_type_a33fea814b08`: 6
- `sekonix_surface_row_incomplete`: 6
- `other_unsupported_nonzero_aac_raytech_asphere_term_r1_a36_n`: 5
- `other_r10_thickness_is_not_numeric_d10`: 4
- `other_r4_thickness_is_not_numeric_d4`: 4
- `other_sekonix_glass_code_cannot_be_split_deterministically_bk7_schott`: 4
- `other_aspheric_row_a4_has_more_numeric_values_than_surfaces_extra_token`: 3
- `other_folded_zoom_system_n_uses_unsupported_published_qtyp_nr_a0_a6_surfaces`: 3
- `other_sekonix_glass_code_cannot_be_split_deterministically_bsc7_hoya`: 3
- `other_sunny_asphere_row_s7_has_more_values_than_headers_token`: 3
- `other_unsupported_nonzero_fujifilm_asphere_terms_s3_a3_n_s4_a3_n_s14_a3_n_s15_a3_n`: 3
- `other_newmax_a_row_has_nonnumeric_data_token_positive`: 2
- `other_r2_thickness_is_not_numeric_d2`: 2
- `other_sekonix_glass_code_cannot_be_split_deterministically_token`: 2
- `other_stop_thickness_is_not_numeric_d0`: 2
- `other_sunny_asphere_row_s1_has_more_values_than_headers_token`: 2
- `other_sunny_asphere_row_s5_has_more_values_than_headers_token`: 2
- `other_unsupported_nonzero_aac_raytech_asphere_term_r4_a2_n`: 2
- `other_aspheric_row_a14_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_a24_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_a26_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_a8_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_k_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_mobile_imaging_lens_example_n_surface_n_coefficient_a12_is_malformed_e_n`: 1
- `other_r6_radius_is_not_numeric_n`: 1
- `other_sunny_asphere_row_s12_has_more_values_than_headers_token`: 1
- `other_sunny_s15_row_has_unexpected_extra_values_n_n_n_n`: 1
- `other_sunny_s7_row_has_unexpected_extra_values_n_n_n_n`: 1
- `other_sunny_sto_value_is_not_numeric_s7_aas`: 1
- `other_unsupported_nonzero_aac_raytech_asphere_term_r1_a32_n`: 1
- `other_unsupported_nonzero_aac_raytech_asphere_term_r2_a32_n`: 1
- `other_unsupported_nonzero_fujifilm_asphere_terms_s5_a3_n_s6_a3_n_s16_a3_n_s17_a3_n`: 1
