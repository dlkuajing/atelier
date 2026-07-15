# Frozen local patent-pool replay

## Result

- cohort_sha256: `e809823c709de93f49eb9b2103c4ebcdd9cf7e34d88f45a4953aaa21fd7bb42b`
- frozen_roots: 619
- roots_with_results: 128
- missing_roots: 491
- corrupt_results: 0
- cohort_replay_complete: `false`
- saturation_complete: `false`
- next_missing_index: 128

The replay-complete flag means every frozen local root has one strict current replay result. It
does not mean source saturation, formal intake, production usability, or an expert verdict.

## Root states

- `converted_pending_intake`: 1
- `terminal`: 3
- `parser_review_required`: 94
- `source_retry_required`: 3
- `source_exhausted_pending_alternates`: 0
- `conversion_retry_required`: 0
- `mixed_nonterminal`: 27

## Item states

- `converted_pending_intake`: 48
- `terminal`: 171
- `parser_review_required`: 322
- `conversion_retry_required`: 1

## Terminal statuses proven by replay receipts

- `intaken`: 0
- `duplicate`: 0
- `quality_rejected`: 0
- `confirmed_no_prescription`: 0
- `fulltext_unavailable`: 0
- `parser_family_missing`: 0
- `metadata_unpublished`: 0
- `trace_failed`: 139
- `trace_timeout`: 32
- `externally_blocked`: 0

## Root reason codes

- `parser_review_required.all_disclosed_items_rejected`: 94
- `mixed_nonterminal.multiple_item_states`: 27
- `source_retry_required.uspto_ppubs_fetch_incomplete`: 3
- `terminal.all_disclosed_items_terminal`: 3
- `converted_pending_intake.all_disclosed_items_converted`: 1

## Item reason codes

- `parser_review_required.deterministic_parser_rejected`: 322
- `terminal.process_receipt_classified`: 171
- `converted_pending_intake.process_isolated_zmx_ready`: 48
- `conversion_retry_required.patent_budget_exhausted`: 1

## Source attempts

- `retained`: 125
- `http_error`: 2
- `transport_error`: 7

## Parser failure signatures

- `aac_raytech_summary_metadata_missing`: 63
- `sunny_embodiment_metadata_missing`: 63
- `generic_numeric_token_rejected`: 42
- `generic_summary_metadata_missing`: 41
- `asphere_section_missing`: 27
- `generic_surface_radius_not_numeric`: 24
- `sunny_surface_value_not_numeric`: 21
- `generic_surface_table_index_break`: 15
- `sekonix_radius_not_numeric`: 12
- `asphere_surface_header_missing`: 5
- `sekonix_surface_row_incomplete`: 5
- `ocr_corrupted_exponent`: 2
- `other_aspheric_row_k_has_more_numeric_values_than_surfaces_extra_token`: 1
- `other_sunny_asphere_row_s1_has_more_values_than_headers_token`: 1
