# Frozen local patent-pool replay

## Result

- cohort_sha256: `e809823c709de93f49eb9b2103c4ebcdd9cf7e34d88f45a4953aaa21fd7bb42b`
- frozen_roots: 619
- roots_with_results: 619
- result_file_count: 619
- result_set_sha256: `427df235546c80de9d61f28bd8ce76d56fa6320a859f47706e7464142f29bd7a`
- missing_roots: 0
- corrupt_results: 0
- cohort_replay_complete: `true`
- saturation_complete: `false`
- next_missing_index: None

The replay-complete flag means every frozen local root has one strict current replay result. It
does not mean source saturation, formal intake, production usability, or an expert verdict.

## Root states

- `converted_pending_intake`: 20
- `terminal`: 42
- `parser_review_required`: 418
- `source_retry_required`: 0
- `source_exhausted_pending_alternates`: 0
- `conversion_retry_required`: 0
- `mixed_nonterminal`: 139

## Item states

- `converted_pending_intake`: 518
- `terminal`: 734
- `parser_review_required`: 1366
- `conversion_retry_required`: 28

## Terminal statuses proven by replay receipts

- `intaken`: 0
- `duplicate`: 0
- `quality_rejected`: 0
- `confirmed_no_prescription`: 3
- `fulltext_unavailable`: 0
- `parser_family_missing`: 0
- `metadata_unpublished`: 17
- `trace_failed`: 607
- `trace_timeout`: 107
- `externally_blocked`: 0

## Root reason codes

- `parser_review_required.all_disclosed_items_rejected`: 418
- `mixed_nonterminal.multiple_item_states`: 139
- `terminal.all_disclosed_items_terminal`: 42
- `converted_pending_intake.all_disclosed_items_converted`: 20

## Item reason codes

- `parser_review_required.deterministic_parser_rejected`: 1366
- `terminal.process_receipt_classified`: 714
- `converted_pending_intake.process_isolated_zmx_ready`: 518
- `conversion_retry_required.patent_budget_exhausted`: 28
- `terminal.metadata_unpublished.stop_axial_coordinate_absent`: 10
- `terminal.metadata_unpublished.system_f_number_absent`: 6
- `terminal.confirmed_no_prescription.surface_texture_acquisition_architecture_only`: 2
- `terminal.confirmed_no_prescription.ir_filter_coating_tables_only`: 1
- `terminal.metadata_unpublished.system_f_fno_fov_values_absent`: 1

## Source attempts

- `retained`: 619
- `http_error`: 0
- `transport_error`: 0

## Parser failure signatures

- `generic_summary_metadata_missing`: 246
- `sunny_embodiment_metadata_missing`: 199
- `aac_raytech_summary_metadata_missing`: 174
- `sunny_surface_value_not_numeric`: 120
- `generic_surface_radius_not_numeric`: 115
- `asphere_section_missing`: 65
- `sekonix_radius_not_numeric`: 64
- `generic_numeric_token_rejected`: 62
- `generic_surface_table_index_break`: 35
- `other_sunny_s1_row_has_unexpected_extra_values_n_n_n`: 29
- `other_finite_object_state_is_published_but_unsupported_by_the_infinity_conjugate_replay_model_object_distance_n`: 24
- `ocr_corrupted_exponent`: 21
- `asphere_surface_header_missing`: 16
- `other_surface_n_thickness_is_not_numeric_flt`: 11
- `other_folded_macro_tele_system_n_whole_system_focal_token_f_is_not_officially_defined_as_efl`: 9
- `other_sunny_sto_value_is_not_numeric_surface`: 8
- `other_kantatsu_example_n_surface_table_unit_is_nm_not_mm`: 7
- `other_kantatsu_inline_example_n_object_image_rows_are_incomplete`: 7
- `other_surface_n_material_nd_vd_outside_physical_bounds_nd_n_allowed_n_n_vd_n_allowed_n_n`: 7
- `other_folded_zoom_system_n_surface_index_break_expected_s8_found_s7`: 6
- `other_kantatsu_missing_half_field_example_n_published_half_field_value_is_absent_from_the_table_header`: 6
- `other_sunny_s3_row_has_unexpected_extra_values_n_n_n`: 6
- `other_unsupported_nonzero_aac_raytech_asphere_term_r1_a2_n`: 6
- `other_validationerror_n_validation_error_for_patentsurfaceinput_thickness_mm_input_should_be_a_finite_number_type_a33fea814b08`: 6
- `sekonix_surface_row_incomplete`: 6
- `other_unsupported_nonzero_aac_raytech_asphere_term_r1_a36_n`: 5
- `other_ability_pdf_numeric_cell_at_n_n_has_n_values_above_confidence_gate`: 4
- `other_ability_zoom_s15_abbe_number_token_token_confidence_n_is_below_n`: 4
- `other_ability_zoom_surface_label_token_confidence_n_is_below_n`: 4
- `other_kantatsu_damaged_metadata_example_n_published_ih_fno_half_field_labels_are_absent_from_the_table_header`: 4
- `other_r10_thickness_is_not_numeric_d10`: 4
- `other_r4_thickness_is_not_numeric_d4`: 4
- `other_sekonix_glass_code_cannot_be_split_deterministically_bk7_schott`: 4
- `other_aspheric_row_a4_has_more_numeric_values_than_surfaces_extra_token`: 3
- `other_folded_zoom_system_n_uses_unsupported_published_qtyp_nr_a0_a6_surfaces`: 3
- `other_kantatsu_example_n_surface_sequence_must_be_n_n`: 3
- `other_sekonix_glass_code_cannot_be_split_deterministically_bsc7_hoya`: 3
- `other_sunny_asphere_row_s7_has_more_values_than_headers_token`: 3
- `other_unsupported_nonzero_fujifilm_asphere_terms_s3_a3_n_s4_a3_n_s14_a3_n_s15_a3_n`: 3
- `other_ability_two_five_lens_surface_row_sequence_mismatch_s1_s2_s3_s4_s5_s6_s7_s8_s9_s10_s11_s12_s13_s14`: 2
- `other_kantatsu_example_n_lens_n_first_surface_row_is_malformed`: 2
- `other_kantatsu_ih_first_example_n_source_surface_sequence_is_unsupported_or_damaged_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n`: 2
- `other_newmax_a_row_has_nonnumeric_data_token_positive`: 2
- `other_optical_table_surface_n_has_n_exact_ocr_label_tokens_asphere_table_surface_confidence_n_is_below_n`: 2
- `other_r2_thickness_is_not_numeric_d2`: 2
- `other_sekonix_glass_code_cannot_be_split_deterministically_token`: 2
- `other_stop_thickness_is_not_numeric_d0`: 2
- `other_sunny_asphere_row_s1_has_more_values_than_headers_token`: 2
- `other_sunny_asphere_row_s5_has_more_values_than_headers_token`: 2
- `other_unsupported_nonzero_aac_raytech_asphere_term_r4_a2_n`: 2
- `other_ability_ol1_asphere_cells_are_not_independently_classified_fail_closed`: 1
- `other_ability_three_lens_row_s3_has_incomplete_material_data`: 1
- `other_asphere_table_has_n_exact_surface_headers`: 1
- `other_aspheric_row_a14_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_a24_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_a26_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_a8_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_aspheric_row_k_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_kantatsu_ih_first_example_n_header_is_source_damaged`: 1
- `other_kantatsu_ih_first_example_n_source_surface_sequence_is_unsupported_or_damaged_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n`: 1
- `other_kantatsu_inline_example_n_coefficient_a20_for_source_surface_n_is_missing`: 1
- `other_kantatsu_inline_example_n_coefficient_label_expected_a4_found_n`: 1
- `other_kantatsu_inline_example_n_source_surface_sequence_is_unsupported_or_damaged_n_n_n_n_n_n_n_n_n_n_n_n_n_n`: 1
- `other_kantatsu_inline_example_n_source_surface_sequence_is_unsupported_or_damaged_n_n_n_n_n_n_n_n_n_n_n_n_n_n_n`: 1
- `other_kantatsu_inline_example_n_stop_row_is_malformed`: 1
- `other_kantatsu_six_lens_example_n_coefficient_a14_for_source_surface_n_is_malformed_e_n`: 1
- `other_kantatsu_six_lens_example_n_coefficient_label_expected_a16_found_end`: 1
- `other_largan_surface_label_token_confidence_n_is_below_n`: 1
- `other_largan_surface_n_radius_token_token_confidence_n_is_below_n`: 1
- `other_largan_surface_n_thickness_token_token_confidence_n_is_below_n`: 1
- `other_mobile_imaging_lens_example_n_surface_n_coefficient_a12_is_malformed_e_n`: 1
- `other_optical_table_has_n_accepted_radius_headers_asphere_coefficient_label_a10_confidence_n_is_below_n`: 1
- `other_optical_table_has_n_accepted_radius_headers_asphere_coefficient_label_a4_has_n_exact_ocr_tokens`: 1
- `other_optical_table_surface_confidence_n_is_below_n_asphere_coefficient_label_a6_confidence_n_is_below_n`: 1
- `other_optical_table_surface_confidence_n_is_below_n_asphere_table_has_n_exact_surface_headers`: 1
- `other_optical_table_surface_confidence_n_is_below_n_asphere_table_surface_confidence_n_is_below_n`: 1
- `other_optical_table_surface_header_token_token_does_not_equal_token_confidence_n_asphere_coefficient_label_a4_con_602028eaba4f`: 1
- `other_optical_table_surface_header_token_token_does_not_equal_token_confidence_n_asphere_coefficient_label_a4_con_91e338c1d9f8`: 1
- `other_optical_table_surface_n_confidence_n_is_below_n_asphere_table_surface_n_confidence_n_is_below_n`: 1
- `other_r6_radius_is_not_numeric_n`: 1
- `other_samsung_even_order_embodiment_n_asphere_headers_must_be_s1_s8_and_s9_s16`: 1
- `other_sunny_asphere_row_s12_has_more_values_than_headers_token`: 1
- `other_sunny_s15_row_has_unexpected_extra_values_n_n_n_n`: 1
- `other_sunny_s7_row_has_unexpected_extra_values_n_n_n_n`: 1
- `other_sunny_sto_value_is_not_numeric_s7_aas`: 1
- `other_unsupported_nonzero_aac_raytech_asphere_term_r1_a32_n`: 1
- `other_unsupported_nonzero_aac_raytech_asphere_term_r2_a32_n`: 1
- `other_unsupported_nonzero_fujifilm_asphere_terms_s5_a3_n_s6_a3_n_s16_a3_n_s17_a3_n`: 1
