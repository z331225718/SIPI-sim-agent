//! Consolidated external-only dispatcher for historical P4B-02b self-crosschecks.
//!
//! The selected runner is fixed by `SIPI_P4B_RUNNER`. This binary is excluded
//! from `cargo test`; external tooling must invoke an explicit runner and inputs.

#[path = "../../tests/p4b_02b100_parameter_list_remove_runner.rs"]
mod p4b_02b100_parameter_list_remove_runner;
#[path = "../../tests/p4b_02b101_parameter_list_append_runner.rs"]
mod p4b_02b101_parameter_list_append_runner;
#[path = "../../tests/p4b_02b102_parameter_list_insert_runner.rs"]
mod p4b_02b102_parameter_list_insert_runner;
#[path = "../../tests/p4b_02b103_parameter_list_swap_runner.rs"]
mod p4b_02b103_parameter_list_swap_runner;
#[path = "../../tests/p4b_02b104_parameter_list_reverse_runner.rs"]
mod p4b_02b104_parameter_list_reverse_runner;
#[path = "../../tests/p4b_02b105_parameter_list_sort_runner.rs"]
mod p4b_02b105_parameter_list_sort_runner;
#[path = "../../tests/p4b_02b106_parameter_list_join_runner.rs"]
mod p4b_02b106_parameter_list_join_runner;
#[path = "../../tests/p4b_02b107_parameter_list_distinct_count_runner.rs"]
mod p4b_02b107_parameter_list_distinct_count_runner;
#[path = "../../tests/p4b_02b108_parameter_list_occurrence_count_runner.rs"]
mod p4b_02b108_parameter_list_occurrence_count_runner;
#[path = "../../tests/p4b_02b109_parameter_list_slice_runner.rs"]
mod p4b_02b109_parameter_list_slice_runner;
#[path = "../../tests/p4b_02b10_parameter_tree_validator_runner.rs"]
mod p4b_02b10_parameter_tree_validator_runner;
#[path = "../../tests/p4b_02b110_parameter_list_index_of_runner.rs"]
mod p4b_02b110_parameter_list_index_of_runner;
#[path = "../../tests/p4b_02b111_parameter_list_last_index_of_runner.rs"]
mod p4b_02b111_parameter_list_last_index_of_runner;
#[path = "../../tests/p4b_02b112_parameter_list_remove_all_runner.rs"]
mod p4b_02b112_parameter_list_remove_all_runner;
#[path = "../../tests/p4b_02b113_parameter_list_keep_only_runner.rs"]
mod p4b_02b113_parameter_list_keep_only_runner;
#[path = "../../tests/p4b_02b114_parameter_list_split_runner.rs"]
mod p4b_02b114_parameter_list_split_runner;
#[path = "../../tests/p4b_02b115_parameter_list_rotate_runner.rs"]
mod p4b_02b115_parameter_list_rotate_runner;
#[path = "../../tests/p4b_02b116_parameter_list_chunk_runner.rs"]
mod p4b_02b116_parameter_list_chunk_runner;
#[path = "../../tests/p4b_02b117_parameter_list_head_tail_runner.rs"]
mod p4b_02b117_parameter_list_head_tail_runner;
#[path = "../../tests/p4b_02b118_parameter_list_window_runner.rs"]
mod p4b_02b118_parameter_list_window_runner;
#[path = "../../tests/p4b_02b119_parameter_list_run_length_encode_runner.rs"]
mod p4b_02b119_parameter_list_run_length_encode_runner;
#[path = "../../tests/p4b_02b11_parameter_tree_diff_runner.rs"]
mod p4b_02b11_parameter_tree_diff_runner;
#[path = "../../tests/p4b_02b120_parameter_list_longest_run_runner.rs"]
mod p4b_02b120_parameter_list_longest_run_runner;
#[path = "../../tests/p4b_02b121_parameter_list_frequency_runner.rs"]
mod p4b_02b121_parameter_list_frequency_runner;
#[path = "../../tests/p4b_02b122_parameter_list_most_frequent_runner.rs"]
mod p4b_02b122_parameter_list_most_frequent_runner;
#[path = "../../tests/p4b_02b123_parameter_list_least_frequent_runner.rs"]
mod p4b_02b123_parameter_list_least_frequent_runner;
#[path = "../../tests/p4b_02b124_parameter_list_is_sorted_runner.rs"]
mod p4b_02b124_parameter_list_is_sorted_runner;
#[path = "../../tests/p4b_02b125_parameter_list_is_strictly_sorted_runner.rs"]
mod p4b_02b125_parameter_list_is_strictly_sorted_runner;
#[path = "../../tests/p4b_02b126_parameter_list_is_palindrome_runner.rs"]
mod p4b_02b126_parameter_list_is_palindrome_runner;
#[path = "../../tests/p4b_02b127_parameter_list_contains_sublist_runner.rs"]
mod p4b_02b127_parameter_list_contains_sublist_runner;
#[path = "../../tests/p4b_02b128_parameter_list_sublist_index_runner.rs"]
mod p4b_02b128_parameter_list_sublist_index_runner;
#[path = "../../tests/p4b_02b129_parameter_list_last_sublist_index_runner.rs"]
mod p4b_02b129_parameter_list_last_sublist_index_runner;
#[path = "../../tests/p4b_02b12_parameter_tree_merge_runner.rs"]
mod p4b_02b12_parameter_tree_merge_runner;
#[path = "../../tests/p4b_02b130_parameter_list_longest_common_prefix_runner.rs"]
mod p4b_02b130_parameter_list_longest_common_prefix_runner;
#[path = "../../tests/p4b_02b131_parameter_list_longest_common_suffix_runner.rs"]
mod p4b_02b131_parameter_list_longest_common_suffix_runner;
#[path = "../../tests/p4b_02b132_parameter_list_interleave_runner.rs"]
mod p4b_02b132_parameter_list_interleave_runner;
#[path = "../../tests/p4b_02b133_parameter_list_inversion_count_runner.rs"]
mod p4b_02b133_parameter_list_inversion_count_runner;
#[path = "../../tests/p4b_02b134_parameter_list_equal_adjacent_count_runner.rs"]
mod p4b_02b134_parameter_list_equal_adjacent_count_runner;
#[path = "../../tests/p4b_02b135_parameter_list_distinct_pair_count_runner.rs"]
mod p4b_02b135_parameter_list_distinct_pair_count_runner;
#[path = "../../tests/p4b_02b136_parameter_list_unique_item_count_runner.rs"]
mod p4b_02b136_parameter_list_unique_item_count_runner;
#[path = "../../tests/p4b_02b137_parameter_list_duplicate_item_count_runner.rs"]
mod p4b_02b137_parameter_list_duplicate_item_count_runner;
#[path = "../../tests/p4b_02b138_parameter_list_first_duplicate_index_runner.rs"]
mod p4b_02b138_parameter_list_first_duplicate_index_runner;
#[path = "../../tests/p4b_02b139_parameter_list_last_duplicate_index_runner.rs"]
mod p4b_02b139_parameter_list_last_duplicate_index_runner;
#[path = "../../tests/p4b_02b13_parameter_tree_pruning_runner.rs"]
mod p4b_02b13_parameter_tree_pruning_runner;
#[path = "../../tests/p4b_02b140_parameter_list_multi_remove_all_runner.rs"]
mod p4b_02b140_parameter_list_multi_remove_all_runner;
#[path = "../../tests/p4b_02b141_parameter_list_multi_keep_only_runner.rs"]
mod p4b_02b141_parameter_list_multi_keep_only_runner;
#[path = "../../tests/p4b_02b142_parameter_list_longest_common_subsequence_length_runner.rs"]
mod p4b_02b142_parameter_list_longest_common_subsequence_length_runner;
#[path = "../../tests/p4b_02b143_parameter_list_edit_distance_runner.rs"]
mod p4b_02b143_parameter_list_edit_distance_runner;
#[path = "../../tests/p4b_02b144_parameter_list_has_subsequence_runner.rs"]
mod p4b_02b144_parameter_list_has_subsequence_runner;
#[path = "../../tests/p4b_02b145_parameter_list_hamming_distance_runner.rs"]
mod p4b_02b145_parameter_list_hamming_distance_runner;
#[path = "../../tests/p4b_02b146_parameter_list_starts_with_runner.rs"]
mod p4b_02b146_parameter_list_starts_with_runner;
#[path = "../../tests/p4b_02b147_parameter_list_ends_with_runner.rs"]
mod p4b_02b147_parameter_list_ends_with_runner;
#[path = "../../tests/p4b_02b148_parameter_list_intersection_runner.rs"]
mod p4b_02b148_parameter_list_intersection_runner;
#[path = "../../tests/p4b_02b149_parameter_list_symmetric_difference_runner.rs"]
mod p4b_02b149_parameter_list_symmetric_difference_runner;
#[path = "../../tests/p4b_02b14_parameter_tree_visitor_runner.rs"]
mod p4b_02b14_parameter_tree_visitor_runner;
#[path = "../../tests/p4b_02b150_parameter_list_union_runner.rs"]
mod p4b_02b150_parameter_list_union_runner;
#[path = "../../tests/p4b_02b151_parameter_list_relative_complement_runner.rs"]
mod p4b_02b151_parameter_list_relative_complement_runner;
#[path = "../../tests/p4b_02b152_parameter_list_multiset_equal_runner.rs"]
mod p4b_02b152_parameter_list_multiset_equal_runner;
#[path = "../../tests/p4b_02b153_parameter_list_contains_multiset_runner.rs"]
mod p4b_02b153_parameter_list_contains_multiset_runner;
#[path = "../../tests/p4b_02b154_parameter_list_jaccard_index_runner.rs"]
mod p4b_02b154_parameter_list_jaccard_index_runner;
#[path = "../../tests/p4b_02b155_parameter_list_dice_index_runner.rs"]
mod p4b_02b155_parameter_list_dice_index_runner;
#[path = "../../tests/p4b_02b156_parameter_list_overlap_coefficient_runner.rs"]
mod p4b_02b156_parameter_list_overlap_coefficient_runner;
#[path = "../../tests/p4b_02b157_parameter_list_contains_sequence_runner.rs"]
mod p4b_02b157_parameter_list_contains_sequence_runner;
#[path = "../../tests/p4b_02b158_parameter_list_tversky_index_runner.rs"]
mod p4b_02b158_parameter_list_tversky_index_runner;
#[path = "../../tests/p4b_02b159_parameter_list_longest_common_subsequence_runner.rs"]
mod p4b_02b159_parameter_list_longest_common_subsequence_runner;
#[path = "../../tests/p4b_02b15_parameter_tree_transformer_runner.rs"]
mod p4b_02b15_parameter_tree_transformer_runner;
#[path = "../../tests/p4b_02b160_parameter_list_all_equal_runner.rs"]
mod p4b_02b160_parameter_list_all_equal_runner;
#[path = "../../tests/p4b_02b161_parameter_list_min_max_item_runner.rs"]
mod p4b_02b161_parameter_list_min_max_item_runner;
#[path = "../../tests/p4b_02b162_parameter_list_nth_smallest_item_runner.rs"]
mod p4b_02b162_parameter_list_nth_smallest_item_runner;
#[path = "../../tests/p4b_02b163_parameter_list_nth_largest_item_runner.rs"]
mod p4b_02b163_parameter_list_nth_largest_item_runner;
#[path = "../../tests/p4b_02b164_parameter_list_median_item_runner.rs"]
mod p4b_02b164_parameter_list_median_item_runner;
#[path = "../../tests/p4b_02b165_parameter_list_mode_items_runner.rs"]
mod p4b_02b165_parameter_list_mode_items_runner;
#[path = "../../tests/p4b_02b166_parameter_list_anti_mode_items_runner.rs"]
mod p4b_02b166_parameter_list_anti_mode_items_runner;
#[path = "../../tests/p4b_02b167_parameter_list_dedup_keep_last_runner.rs"]
mod p4b_02b167_parameter_list_dedup_keep_last_runner;
#[path = "../../tests/p4b_02b168_parameter_list_run_count_runner.rs"]
mod p4b_02b168_parameter_list_run_count_runner;
#[path = "../../tests/p4b_02b169_parameter_list_sorted_rank_runner.rs"]
mod p4b_02b169_parameter_list_sorted_rank_runner;
#[path = "../../tests/p4b_02b16_parameter_tree_index_runner.rs"]
mod p4b_02b16_parameter_tree_index_runner;
#[path = "../../tests/p4b_02b170_parameter_list_longest_run_item_runner.rs"]
mod p4b_02b170_parameter_list_longest_run_item_runner;
#[path = "../../tests/p4b_02b171_parameter_list_longest_run_start_index_runner.rs"]
mod p4b_02b171_parameter_list_longest_run_start_index_runner;
#[path = "../../tests/p4b_02b172_parameter_list_adjacent_change_count_runner.rs"]
mod p4b_02b172_parameter_list_adjacent_change_count_runner;
#[path = "../../tests/p4b_02b173_parameter_list_total_equal_pair_count_runner.rs"]
mod p4b_02b173_parameter_list_total_equal_pair_count_runner;
#[path = "../../tests/p4b_02b174_parameter_list_majority_item_runner.rs"]
mod p4b_02b174_parameter_list_majority_item_runner;
#[path = "../../tests/p4b_02b175_parameter_list_is_alternating_runner.rs"]
mod p4b_02b175_parameter_list_is_alternating_runner;
#[path = "../../tests/p4b_02b176_parameter_list_entropy_runner.rs"]
mod p4b_02b176_parameter_list_entropy_runner;
#[path = "../../tests/p4b_02b177_parameter_list_gini_impurity_runner.rs"]
mod p4b_02b177_parameter_list_gini_impurity_runner;
#[path = "../../tests/p4b_02b178_parameter_list_normalized_entropy_runner.rs"]
mod p4b_02b178_parameter_list_normalized_entropy_runner;
#[path = "../../tests/p4b_02b179_parameter_list_mode_frequency_runner.rs"]
mod p4b_02b179_parameter_list_mode_frequency_runner;
#[path = "../../tests/p4b_02b17_parameter_tree_diff_patch_runner.rs"]
mod p4b_02b17_parameter_tree_diff_patch_runner;
#[path = "../../tests/p4b_02b180_parameter_list_prevalence_ratio_runner.rs"]
mod p4b_02b180_parameter_list_prevalence_ratio_runner;
#[path = "../../tests/p4b_02b181_parameter_list_frequency_normalized_runner.rs"]
mod p4b_02b181_parameter_list_frequency_normalized_runner;
#[path = "../../tests/p4b_02b182_parameter_list_first_occurrence_indices_runner.rs"]
mod p4b_02b182_parameter_list_first_occurrence_indices_runner;
#[path = "../../tests/p4b_02b183_parameter_list_run_boundaries_runner.rs"]
mod p4b_02b183_parameter_list_run_boundaries_runner;
#[path = "../../tests/p4b_02b184_parameter_list_pairwise_distinct_adjacent_runner.rs"]
mod p4b_02b184_parameter_list_pairwise_distinct_adjacent_runner;
#[path = "../../tests/p4b_02b185_parameter_list_is_balanced_runner.rs"]
mod p4b_02b185_parameter_list_is_balanced_runner;
#[path = "../../tests/p4b_02b186_parameter_list_first_occurrence_map_runner.rs"]
mod p4b_02b186_parameter_list_first_occurrence_map_runner;
#[path = "../../tests/p4b_02b187_parameter_list_last_occurrence_map_runner.rs"]
mod p4b_02b187_parameter_list_last_occurrence_map_runner;
#[path = "../../tests/p4b_02b188_parameter_list_occurrence_indices_map_runner.rs"]
mod p4b_02b188_parameter_list_occurrence_indices_map_runner;
#[path = "../../tests/p4b_02b189_parameter_list_last_occurrence_indices_runner.rs"]
mod p4b_02b189_parameter_list_last_occurrence_indices_runner;
#[path = "../../tests/p4b_02b18_parameter_tree_filter_runner.rs"]
mod p4b_02b18_parameter_tree_filter_runner;
#[path = "../../tests/p4b_02b190_parameter_list_frequency_map_runner.rs"]
mod p4b_02b190_parameter_list_frequency_map_runner;
#[path = "../../tests/p4b_02b191_parameter_list_pairwise_equal_adjacent_runner.rs"]
mod p4b_02b191_parameter_list_pairwise_equal_adjacent_runner;
#[path = "../../tests/p4b_02b192_parameter_list_relative_frequency_map_runner.rs"]
mod p4b_02b192_parameter_list_relative_frequency_map_runner;
#[path = "../../tests/p4b_02b193_parameter_list_prevalence_map_runner.rs"]
mod p4b_02b193_parameter_list_prevalence_map_runner;
#[path = "../../tests/p4b_02b19_parameter_tree_serde_runner.rs"]
mod p4b_02b19_parameter_tree_serde_runner;
#[path = "../../tests/p4b_02b20_parameter_tree_diff_stats_runner.rs"]
mod p4b_02b20_parameter_tree_diff_stats_runner;
#[path = "../../tests/p4b_02b21_parameter_tree_diff_filter_runner.rs"]
mod p4b_02b21_parameter_tree_diff_filter_runner;
#[path = "../../tests/p4b_02b22_parameter_tree_diff_summary_runner.rs"]
mod p4b_02b22_parameter_tree_diff_summary_runner;
#[path = "../../tests/p4b_02b23_parameter_tree_subtree_runner.rs"]
mod p4b_02b23_parameter_tree_subtree_runner;
#[path = "../../tests/p4b_02b24_parameter_tree_rename_runner.rs"]
mod p4b_02b24_parameter_tree_rename_runner;
#[path = "../../tests/p4b_02b25_parameter_tree_detect_cycles_runner.rs"]
mod p4b_02b25_parameter_tree_detect_cycles_runner;
#[path = "../../tests/p4b_02b26_parameter_tree_compose_runner.rs"]
mod p4b_02b26_parameter_tree_compose_runner;
#[path = "../../tests/p4b_02b27_parameter_tree_replace_runner.rs"]
mod p4b_02b27_parameter_tree_replace_runner;
#[path = "../../tests/p4b_02b28_parameter_tree_toposort_runner.rs"]
mod p4b_02b28_parameter_tree_toposort_runner;
#[path = "../../tests/p4b_02b29_parameter_tree_depth_stats_runner.rs"]
mod p4b_02b29_parameter_tree_depth_stats_runner;
#[path = "../../tests/p4b_02b30_parameter_tree_leaf_index_runner.rs"]
mod p4b_02b30_parameter_tree_leaf_index_runner;
#[path = "../../tests/p4b_02b31_parameter_tree_token_stats_runner.rs"]
mod p4b_02b31_parameter_tree_token_stats_runner;
#[path = "../../tests/p4b_02b32_parameter_tree_value_validation_runner.rs"]
mod p4b_02b32_parameter_tree_value_validation_runner;
#[path = "../../tests/p4b_02b33_parameter_tree_value_type_inference_runner.rs"]
mod p4b_02b33_parameter_tree_value_type_inference_runner;
#[path = "../../tests/p4b_02b34_parameter_tree_typed_form_runner.rs"]
mod p4b_02b34_parameter_tree_typed_form_runner;
#[path = "../../tests/p4b_02b35_parameter_tree_leaf_projection_runner.rs"]
mod p4b_02b35_parameter_tree_leaf_projection_runner;
#[path = "../../tests/p4b_02b36_parameter_tree_batch_rename_runner.rs"]
mod p4b_02b36_parameter_tree_batch_rename_runner;
#[path = "../../tests/p4b_02b37_parameter_tree_leaf_value_decoding_runner.rs"]
mod p4b_02b37_parameter_tree_leaf_value_decoding_runner;
#[path = "../../tests/p4b_02b38_parameter_tree_apply_defaults_runner.rs"]
mod p4b_02b38_parameter_tree_apply_defaults_runner;
#[path = "../../tests/p4b_02b39_parameter_tree_leaf_value_set_runner.rs"]
mod p4b_02b39_parameter_tree_leaf_value_set_runner;
#[path = "../../tests/p4b_02b3_param_catalog_runner.rs"]
mod p4b_02b3_param_catalog_runner;
#[path = "../../tests/p4b_02b40_parameter_tree_leaf_search_runner.rs"]
mod p4b_02b40_parameter_tree_leaf_search_runner;
#[path = "../../tests/p4b_02b41_parameter_tree_inferred_decode_runner.rs"]
mod p4b_02b41_parameter_tree_inferred_decode_runner;
#[path = "../../tests/p4b_02b42_parameter_tree_typed_form_multi_runner.rs"]
mod p4b_02b42_parameter_tree_typed_form_multi_runner;
#[path = "../../tests/p4b_02b43_parameter_tree_reserved_name_check_runner.rs"]
mod p4b_02b43_parameter_tree_reserved_name_check_runner;
#[path = "../../tests/p4b_02b44_parameter_profile_assembly_runner.rs"]
mod p4b_02b44_parameter_profile_assembly_runner;
#[path = "../../tests/p4b_02b45_parameter_tree_path_string_runner.rs"]
mod p4b_02b45_parameter_tree_path_string_runner;
#[path = "../../tests/p4b_02b46_parameter_tree_expected_check_runner.rs"]
mod p4b_02b46_parameter_tree_expected_check_runner;
#[path = "../../tests/p4b_02b47_parameter_profile_diff_runner.rs"]
mod p4b_02b47_parameter_profile_diff_runner;
#[path = "../../tests/p4b_02b48_parameter_profile_merge_runner.rs"]
mod p4b_02b48_parameter_profile_merge_runner;
#[path = "../../tests/p4b_02b49_parameter_tree_allowed_name_check_runner.rs"]
mod p4b_02b49_parameter_tree_allowed_name_check_runner;
#[path = "../../tests/p4b_02b4_catalog_default_runner.rs"]
mod p4b_02b4_catalog_default_runner;
#[path = "../../tests/p4b_02b50_parameter_tree_flatten_runner.rs"]
mod p4b_02b50_parameter_tree_flatten_runner;
#[path = "../../tests/p4b_02b51_ami_text_document_stats_runner.rs"]
mod p4b_02b51_ami_text_document_stats_runner;
#[path = "../../tests/p4b_02b52_parameter_tree_token_remap_runner.rs"]
mod p4b_02b52_parameter_tree_token_remap_runner;
#[path = "../../tests/p4b_02b53_parameter_tree_batch_value_set_runner.rs"]
mod p4b_02b53_parameter_tree_batch_value_set_runner;
#[path = "../../tests/p4b_02b54_parameter_tree_duplicate_check_runner.rs"]
mod p4b_02b54_parameter_tree_duplicate_check_runner;
#[path = "../../tests/p4b_02b55_parameter_profile_completeness_runner.rs"]
mod p4b_02b55_parameter_profile_completeness_runner;
#[path = "../../tests/p4b_02b56_parameter_tree_path_join_runner.rs"]
mod p4b_02b56_parameter_tree_path_join_runner;
#[path = "../../tests/p4b_02b57_parameter_tree_sections_runner.rs"]
mod p4b_02b57_parameter_tree_sections_runner;
#[path = "../../tests/p4b_02b58_parameter_tree_typed_form_report_runner.rs"]
mod p4b_02b58_parameter_tree_typed_form_report_runner;
#[path = "../../tests/p4b_02b59_parameter_tree_leaf_occurrences_runner.rs"]
mod p4b_02b59_parameter_tree_leaf_occurrences_runner;
#[path = "../../tests/p4b_02b5_ami_runtime_params_runner.rs"]
mod p4b_02b5_ami_runtime_params_runner;
#[path = "../../tests/p4b_02b60_parameter_tree_token_frequencies_runner.rs"]
mod p4b_02b60_parameter_tree_token_frequencies_runner;
#[path = "../../tests/p4b_02b61_ami_text_form_heads_runner.rs"]
mod p4b_02b61_ami_text_form_heads_runner;
#[path = "../../tests/p4b_02b62_parameter_tree_required_name_check_runner.rs"]
mod p4b_02b62_parameter_tree_required_name_check_runner;
#[path = "../../tests/p4b_02b63_parameter_tree_distinct_leaf_names_runner.rs"]
mod p4b_02b63_parameter_tree_distinct_leaf_names_runner;
#[path = "../../tests/p4b_02b64_parameter_profile_select_runner.rs"]
mod p4b_02b64_parameter_profile_select_runner;
#[path = "../../tests/p4b_02b65_parameter_tree_path_relation_runner.rs"]
mod p4b_02b65_parameter_tree_path_relation_runner;
#[path = "../../tests/p4b_02b66_parameter_tree_relative_path_runner.rs"]
mod p4b_02b66_parameter_tree_relative_path_runner;
#[path = "../../tests/p4b_02b67_parameter_tree_longest_common_prefix_runner.rs"]
mod p4b_02b67_parameter_tree_longest_common_prefix_runner;
#[path = "../../tests/p4b_02b68_parameter_tree_path_prefixes_runner.rs"]
mod p4b_02b68_parameter_tree_path_prefixes_runner;
#[path = "../../tests/p4b_02b69_parameter_tree_profile_apply_runner.rs"]
mod p4b_02b69_parameter_tree_profile_apply_runner;
#[path = "../../tests/p4b_02b6_parameter_extractor_runner.rs"]
mod p4b_02b6_parameter_extractor_runner;
#[path = "../../tests/p4b_02b70_parameter_value_equivalence_runner.rs"]
mod p4b_02b70_parameter_value_equivalence_runner;
#[path = "../../tests/p4b_02b71_parameter_profile_equivalence_runner.rs"]
mod p4b_02b71_parameter_profile_equivalence_runner;
#[path = "../../tests/p4b_02b72_parameter_profile_tree_coverage_runner.rs"]
mod p4b_02b72_parameter_profile_tree_coverage_runner;
#[path = "../../tests/p4b_02b73_parameter_profile_type_stats_runner.rs"]
mod p4b_02b73_parameter_profile_type_stats_runner;
#[path = "../../tests/p4b_02b74_parameter_profile_typed_merge_runner.rs"]
mod p4b_02b74_parameter_profile_typed_merge_runner;
#[path = "../../tests/p4b_02b75_parameter_value_spelling_normalization_runner.rs"]
mod p4b_02b75_parameter_value_spelling_normalization_runner;
#[path = "../../tests/p4b_02b76_parameter_profile_override_merge_runner.rs"]
mod p4b_02b76_parameter_profile_override_merge_runner;
#[path = "../../tests/p4b_02b77_parameter_profile_canonicalization_runner.rs"]
mod p4b_02b77_parameter_profile_canonicalization_runner;
#[path = "../../tests/p4b_02b78_parameter_tree_leaf_canonicalization_runner.rs"]
mod p4b_02b78_parameter_tree_leaf_canonicalization_runner;
#[path = "../../tests/p4b_02b79_parameter_profile_typed_diff_runner.rs"]
mod p4b_02b79_parameter_profile_typed_diff_runner;
#[path = "../../tests/p4b_02b7_parameter_trees_runner.rs"]
mod p4b_02b7_parameter_trees_runner;
#[path = "../../tests/p4b_02b80_parameter_profile_value_lookup_runner.rs"]
mod p4b_02b80_parameter_profile_value_lookup_runner;
#[path = "../../tests/p4b_02b81_parameter_profile_serialization_runner.rs"]
mod p4b_02b81_parameter_profile_serialization_runner;
#[path = "../../tests/p4b_02b82_parameter_profile_deserialization_runner.rs"]
mod p4b_02b82_parameter_profile_deserialization_runner;
#[path = "../../tests/p4b_02b83_parameter_list_item_count_runner.rs"]
mod p4b_02b83_parameter_list_item_count_runner;
#[path = "../../tests/p4b_02b84_parameter_list_item_access_runner.rs"]
mod p4b_02b84_parameter_list_item_access_runner;
#[path = "../../tests/p4b_02b85_parameter_list_contains_runner.rs"]
mod p4b_02b85_parameter_list_contains_runner;
#[path = "../../tests/p4b_02b86_parameter_profile_names_by_type_runner.rs"]
mod p4b_02b86_parameter_profile_names_by_type_runner;
#[path = "../../tests/p4b_02b87_parameter_tree_leaf_type_map_runner.rs"]
mod p4b_02b87_parameter_tree_leaf_type_map_runner;
#[path = "../../tests/p4b_02b88_parameter_tree_leaf_type_resolution_runner.rs"]
mod p4b_02b88_parameter_tree_leaf_type_resolution_runner;
#[path = "../../tests/p4b_02b89_parameter_tree_leaf_typed_diff_runner.rs"]
mod p4b_02b89_parameter_tree_leaf_typed_diff_runner;
#[path = "../../tests/p4b_02b8_parameter_tree_query_runner.rs"]
mod p4b_02b8_parameter_tree_query_runner;
#[path = "../../tests/p4b_02b90_parameter_profile_typed_subset_runner.rs"]
mod p4b_02b90_parameter_profile_typed_subset_runner;
#[path = "../../tests/p4b_02b91_parameter_tree_leaf_value_validity_runner.rs"]
mod p4b_02b91_parameter_tree_leaf_value_validity_runner;
#[path = "../../tests/p4b_02b92_parameter_profile_canonical_spelling_groups_runner.rs"]
mod p4b_02b92_parameter_profile_canonical_spelling_groups_runner;
#[path = "../../tests/p4b_02b93_parameter_tree_typed_leaf_type_counts_runner.rs"]
mod p4b_02b93_parameter_tree_typed_leaf_type_counts_runner;
#[path = "../../tests/p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner.rs"]
mod p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner;
#[path = "../../tests/p4b_02b95_parameter_profile_canonical_spelling_check_runner.rs"]
mod p4b_02b95_parameter_profile_canonical_spelling_check_runner;
#[path = "../../tests/p4b_02b96_parameter_profile_fingerprint_runner.rs"]
mod p4b_02b96_parameter_profile_fingerprint_runner;
#[path = "../../tests/p4b_02b97_parameter_tree_typed_leaf_fingerprint_runner.rs"]
mod p4b_02b97_parameter_tree_typed_leaf_fingerprint_runner;
#[path = "../../tests/p4b_02b98_parameter_list_dedup_runner.rs"]
mod p4b_02b98_parameter_list_dedup_runner;
#[path = "../../tests/p4b_02b99_parameter_list_replace_runner.rs"]
mod p4b_02b99_parameter_list_replace_runner;
#[path = "../../tests/p4b_02b9_parameter_tree_formatter_runner.rs"]
mod p4b_02b9_parameter_tree_formatter_runner;

fn main() {
    let runner = std::env::var("SIPI_P4B_RUNNER").unwrap_or_else(|_| {
        eprintln!("SIPI_P4B_RUNNER is required");
        std::process::exit(2);
    });
    let entry: fn() = match runner.as_str() {
        "p4b_02b10_parameter_tree_validator_runner" => {
            p4b_02b10_parameter_tree_validator_runner::main
        }
        "p4b_02b100_parameter_list_remove_runner" => p4b_02b100_parameter_list_remove_runner::main,
        "p4b_02b101_parameter_list_append_runner" => p4b_02b101_parameter_list_append_runner::main,
        "p4b_02b102_parameter_list_insert_runner" => p4b_02b102_parameter_list_insert_runner::main,
        "p4b_02b103_parameter_list_swap_runner" => p4b_02b103_parameter_list_swap_runner::main,
        "p4b_02b104_parameter_list_reverse_runner" => {
            p4b_02b104_parameter_list_reverse_runner::main
        }
        "p4b_02b105_parameter_list_sort_runner" => p4b_02b105_parameter_list_sort_runner::main,
        "p4b_02b106_parameter_list_join_runner" => p4b_02b106_parameter_list_join_runner::main,
        "p4b_02b107_parameter_list_distinct_count_runner" => {
            p4b_02b107_parameter_list_distinct_count_runner::main
        }
        "p4b_02b108_parameter_list_occurrence_count_runner" => {
            p4b_02b108_parameter_list_occurrence_count_runner::main
        }
        "p4b_02b109_parameter_list_slice_runner" => p4b_02b109_parameter_list_slice_runner::main,
        "p4b_02b11_parameter_tree_diff_runner" => p4b_02b11_parameter_tree_diff_runner::main,
        "p4b_02b110_parameter_list_index_of_runner" => {
            p4b_02b110_parameter_list_index_of_runner::main
        }
        "p4b_02b111_parameter_list_last_index_of_runner" => {
            p4b_02b111_parameter_list_last_index_of_runner::main
        }
        "p4b_02b112_parameter_list_remove_all_runner" => {
            p4b_02b112_parameter_list_remove_all_runner::main
        }
        "p4b_02b113_parameter_list_keep_only_runner" => {
            p4b_02b113_parameter_list_keep_only_runner::main
        }
        "p4b_02b114_parameter_list_split_runner" => p4b_02b114_parameter_list_split_runner::main,
        "p4b_02b115_parameter_list_rotate_runner" => p4b_02b115_parameter_list_rotate_runner::main,
        "p4b_02b116_parameter_list_chunk_runner" => p4b_02b116_parameter_list_chunk_runner::main,
        "p4b_02b117_parameter_list_head_tail_runner" => {
            p4b_02b117_parameter_list_head_tail_runner::main
        }
        "p4b_02b118_parameter_list_window_runner" => p4b_02b118_parameter_list_window_runner::main,
        "p4b_02b119_parameter_list_run_length_encode_runner" => {
            p4b_02b119_parameter_list_run_length_encode_runner::main
        }
        "p4b_02b12_parameter_tree_merge_runner" => p4b_02b12_parameter_tree_merge_runner::main,
        "p4b_02b120_parameter_list_longest_run_runner" => {
            p4b_02b120_parameter_list_longest_run_runner::main
        }
        "p4b_02b121_parameter_list_frequency_runner" => {
            p4b_02b121_parameter_list_frequency_runner::main
        }
        "p4b_02b122_parameter_list_most_frequent_runner" => {
            p4b_02b122_parameter_list_most_frequent_runner::main
        }
        "p4b_02b123_parameter_list_least_frequent_runner" => {
            p4b_02b123_parameter_list_least_frequent_runner::main
        }
        "p4b_02b124_parameter_list_is_sorted_runner" => {
            p4b_02b124_parameter_list_is_sorted_runner::main
        }
        "p4b_02b125_parameter_list_is_strictly_sorted_runner" => {
            p4b_02b125_parameter_list_is_strictly_sorted_runner::main
        }
        "p4b_02b126_parameter_list_is_palindrome_runner" => {
            p4b_02b126_parameter_list_is_palindrome_runner::main
        }
        "p4b_02b127_parameter_list_contains_sublist_runner" => {
            p4b_02b127_parameter_list_contains_sublist_runner::main
        }
        "p4b_02b128_parameter_list_sublist_index_runner" => {
            p4b_02b128_parameter_list_sublist_index_runner::main
        }
        "p4b_02b129_parameter_list_last_sublist_index_runner" => {
            p4b_02b129_parameter_list_last_sublist_index_runner::main
        }
        "p4b_02b13_parameter_tree_pruning_runner" => p4b_02b13_parameter_tree_pruning_runner::main,
        "p4b_02b130_parameter_list_longest_common_prefix_runner" => {
            p4b_02b130_parameter_list_longest_common_prefix_runner::main
        }
        "p4b_02b131_parameter_list_longest_common_suffix_runner" => {
            p4b_02b131_parameter_list_longest_common_suffix_runner::main
        }
        "p4b_02b132_parameter_list_interleave_runner" => {
            p4b_02b132_parameter_list_interleave_runner::main
        }
        "p4b_02b133_parameter_list_inversion_count_runner" => {
            p4b_02b133_parameter_list_inversion_count_runner::main
        }
        "p4b_02b134_parameter_list_equal_adjacent_count_runner" => {
            p4b_02b134_parameter_list_equal_adjacent_count_runner::main
        }
        "p4b_02b135_parameter_list_distinct_pair_count_runner" => {
            p4b_02b135_parameter_list_distinct_pair_count_runner::main
        }
        "p4b_02b136_parameter_list_unique_item_count_runner" => {
            p4b_02b136_parameter_list_unique_item_count_runner::main
        }
        "p4b_02b137_parameter_list_duplicate_item_count_runner" => {
            p4b_02b137_parameter_list_duplicate_item_count_runner::main
        }
        "p4b_02b138_parameter_list_first_duplicate_index_runner" => {
            p4b_02b138_parameter_list_first_duplicate_index_runner::main
        }
        "p4b_02b139_parameter_list_last_duplicate_index_runner" => {
            p4b_02b139_parameter_list_last_duplicate_index_runner::main
        }
        "p4b_02b14_parameter_tree_visitor_runner" => p4b_02b14_parameter_tree_visitor_runner::main,
        "p4b_02b140_parameter_list_multi_remove_all_runner" => {
            p4b_02b140_parameter_list_multi_remove_all_runner::main
        }
        "p4b_02b141_parameter_list_multi_keep_only_runner" => {
            p4b_02b141_parameter_list_multi_keep_only_runner::main
        }
        "p4b_02b142_parameter_list_longest_common_subsequence_length_runner" => {
            p4b_02b142_parameter_list_longest_common_subsequence_length_runner::main
        }
        "p4b_02b143_parameter_list_edit_distance_runner" => {
            p4b_02b143_parameter_list_edit_distance_runner::main
        }
        "p4b_02b144_parameter_list_has_subsequence_runner" => {
            p4b_02b144_parameter_list_has_subsequence_runner::main
        }
        "p4b_02b145_parameter_list_hamming_distance_runner" => {
            p4b_02b145_parameter_list_hamming_distance_runner::main
        }
        "p4b_02b146_parameter_list_starts_with_runner" => {
            p4b_02b146_parameter_list_starts_with_runner::main
        }
        "p4b_02b147_parameter_list_ends_with_runner" => {
            p4b_02b147_parameter_list_ends_with_runner::main
        }
        "p4b_02b148_parameter_list_intersection_runner" => {
            p4b_02b148_parameter_list_intersection_runner::main
        }
        "p4b_02b149_parameter_list_symmetric_difference_runner" => {
            p4b_02b149_parameter_list_symmetric_difference_runner::main
        }
        "p4b_02b15_parameter_tree_transformer_runner" => {
            p4b_02b15_parameter_tree_transformer_runner::main
        }
        "p4b_02b150_parameter_list_union_runner" => p4b_02b150_parameter_list_union_runner::main,
        "p4b_02b151_parameter_list_relative_complement_runner" => {
            p4b_02b151_parameter_list_relative_complement_runner::main
        }
        "p4b_02b152_parameter_list_multiset_equal_runner" => {
            p4b_02b152_parameter_list_multiset_equal_runner::main
        }
        "p4b_02b153_parameter_list_contains_multiset_runner" => {
            p4b_02b153_parameter_list_contains_multiset_runner::main
        }
        "p4b_02b154_parameter_list_jaccard_index_runner" => {
            p4b_02b154_parameter_list_jaccard_index_runner::main
        }
        "p4b_02b155_parameter_list_dice_index_runner" => {
            p4b_02b155_parameter_list_dice_index_runner::main
        }
        "p4b_02b156_parameter_list_overlap_coefficient_runner" => {
            p4b_02b156_parameter_list_overlap_coefficient_runner::main
        }
        "p4b_02b157_parameter_list_contains_sequence_runner" => {
            p4b_02b157_parameter_list_contains_sequence_runner::main
        }
        "p4b_02b158_parameter_list_tversky_index_runner" => {
            p4b_02b158_parameter_list_tversky_index_runner::main
        }
        "p4b_02b159_parameter_list_longest_common_subsequence_runner" => {
            p4b_02b159_parameter_list_longest_common_subsequence_runner::main
        }
        "p4b_02b16_parameter_tree_index_runner" => p4b_02b16_parameter_tree_index_runner::main,
        "p4b_02b160_parameter_list_all_equal_runner" => {
            p4b_02b160_parameter_list_all_equal_runner::main
        }
        "p4b_02b161_parameter_list_min_max_item_runner" => {
            p4b_02b161_parameter_list_min_max_item_runner::main
        }
        "p4b_02b162_parameter_list_nth_smallest_item_runner" => {
            p4b_02b162_parameter_list_nth_smallest_item_runner::main
        }
        "p4b_02b163_parameter_list_nth_largest_item_runner" => {
            p4b_02b163_parameter_list_nth_largest_item_runner::main
        }
        "p4b_02b164_parameter_list_median_item_runner" => {
            p4b_02b164_parameter_list_median_item_runner::main
        }
        "p4b_02b165_parameter_list_mode_items_runner" => {
            p4b_02b165_parameter_list_mode_items_runner::main
        }
        "p4b_02b166_parameter_list_anti_mode_items_runner" => {
            p4b_02b166_parameter_list_anti_mode_items_runner::main
        }
        "p4b_02b167_parameter_list_dedup_keep_last_runner" => {
            p4b_02b167_parameter_list_dedup_keep_last_runner::main
        }
        "p4b_02b168_parameter_list_run_count_runner" => {
            p4b_02b168_parameter_list_run_count_runner::main
        }
        "p4b_02b169_parameter_list_sorted_rank_runner" => {
            p4b_02b169_parameter_list_sorted_rank_runner::main
        }
        "p4b_02b17_parameter_tree_diff_patch_runner" => {
            p4b_02b17_parameter_tree_diff_patch_runner::main
        }
        "p4b_02b170_parameter_list_longest_run_item_runner" => {
            p4b_02b170_parameter_list_longest_run_item_runner::main
        }
        "p4b_02b171_parameter_list_longest_run_start_index_runner" => {
            p4b_02b171_parameter_list_longest_run_start_index_runner::main
        }
        "p4b_02b172_parameter_list_adjacent_change_count_runner" => {
            p4b_02b172_parameter_list_adjacent_change_count_runner::main
        }
        "p4b_02b173_parameter_list_total_equal_pair_count_runner" => {
            p4b_02b173_parameter_list_total_equal_pair_count_runner::main
        }
        "p4b_02b174_parameter_list_majority_item_runner" => {
            p4b_02b174_parameter_list_majority_item_runner::main
        }
        "p4b_02b175_parameter_list_is_alternating_runner" => {
            p4b_02b175_parameter_list_is_alternating_runner::main
        }
        "p4b_02b176_parameter_list_entropy_runner" => {
            p4b_02b176_parameter_list_entropy_runner::main
        }
        "p4b_02b177_parameter_list_gini_impurity_runner" => {
            p4b_02b177_parameter_list_gini_impurity_runner::main
        }
        "p4b_02b178_parameter_list_normalized_entropy_runner" => {
            p4b_02b178_parameter_list_normalized_entropy_runner::main
        }
        "p4b_02b179_parameter_list_mode_frequency_runner" => {
            p4b_02b179_parameter_list_mode_frequency_runner::main
        }
        "p4b_02b18_parameter_tree_filter_runner" => p4b_02b18_parameter_tree_filter_runner::main,
        "p4b_02b180_parameter_list_prevalence_ratio_runner" => {
            p4b_02b180_parameter_list_prevalence_ratio_runner::main
        }
        "p4b_02b181_parameter_list_frequency_normalized_runner" => {
            p4b_02b181_parameter_list_frequency_normalized_runner::main
        }
        "p4b_02b182_parameter_list_first_occurrence_indices_runner" => {
            p4b_02b182_parameter_list_first_occurrence_indices_runner::main
        }
        "p4b_02b183_parameter_list_run_boundaries_runner" => {
            p4b_02b183_parameter_list_run_boundaries_runner::main
        }
        "p4b_02b184_parameter_list_pairwise_distinct_adjacent_runner" => {
            p4b_02b184_parameter_list_pairwise_distinct_adjacent_runner::main
        }
        "p4b_02b185_parameter_list_is_balanced_runner" => {
            p4b_02b185_parameter_list_is_balanced_runner::main
        }
        "p4b_02b186_parameter_list_first_occurrence_map_runner" => {
            p4b_02b186_parameter_list_first_occurrence_map_runner::main
        }
        "p4b_02b187_parameter_list_last_occurrence_map_runner" => {
            p4b_02b187_parameter_list_last_occurrence_map_runner::main
        }
        "p4b_02b188_parameter_list_occurrence_indices_map_runner" => {
            p4b_02b188_parameter_list_occurrence_indices_map_runner::main
        }
        "p4b_02b189_parameter_list_last_occurrence_indices_runner" => {
            p4b_02b189_parameter_list_last_occurrence_indices_runner::main
        }
        "p4b_02b19_parameter_tree_serde_runner" => p4b_02b19_parameter_tree_serde_runner::main,
        "p4b_02b190_parameter_list_frequency_map_runner" => {
            p4b_02b190_parameter_list_frequency_map_runner::main
        }
        "p4b_02b191_parameter_list_pairwise_equal_adjacent_runner" => {
            p4b_02b191_parameter_list_pairwise_equal_adjacent_runner::main
        }
        "p4b_02b192_parameter_list_relative_frequency_map_runner" => {
            p4b_02b192_parameter_list_relative_frequency_map_runner::main
        }
        "p4b_02b193_parameter_list_prevalence_map_runner" => {
            p4b_02b193_parameter_list_prevalence_map_runner::main
        }
        "p4b_02b20_parameter_tree_diff_stats_runner" => {
            p4b_02b20_parameter_tree_diff_stats_runner::main
        }
        "p4b_02b21_parameter_tree_diff_filter_runner" => {
            p4b_02b21_parameter_tree_diff_filter_runner::main
        }
        "p4b_02b22_parameter_tree_diff_summary_runner" => {
            p4b_02b22_parameter_tree_diff_summary_runner::main
        }
        "p4b_02b23_parameter_tree_subtree_runner" => p4b_02b23_parameter_tree_subtree_runner::main,
        "p4b_02b24_parameter_tree_rename_runner" => p4b_02b24_parameter_tree_rename_runner::main,
        "p4b_02b25_parameter_tree_detect_cycles_runner" => {
            p4b_02b25_parameter_tree_detect_cycles_runner::main
        }
        "p4b_02b26_parameter_tree_compose_runner" => p4b_02b26_parameter_tree_compose_runner::main,
        "p4b_02b27_parameter_tree_replace_runner" => p4b_02b27_parameter_tree_replace_runner::main,
        "p4b_02b28_parameter_tree_toposort_runner" => {
            p4b_02b28_parameter_tree_toposort_runner::main
        }
        "p4b_02b29_parameter_tree_depth_stats_runner" => {
            p4b_02b29_parameter_tree_depth_stats_runner::main
        }
        "p4b_02b3_param_catalog_runner" => p4b_02b3_param_catalog_runner::main,
        "p4b_02b30_parameter_tree_leaf_index_runner" => {
            p4b_02b30_parameter_tree_leaf_index_runner::main
        }
        "p4b_02b31_parameter_tree_token_stats_runner" => {
            p4b_02b31_parameter_tree_token_stats_runner::main
        }
        "p4b_02b32_parameter_tree_value_validation_runner" => {
            p4b_02b32_parameter_tree_value_validation_runner::main
        }
        "p4b_02b33_parameter_tree_value_type_inference_runner" => {
            p4b_02b33_parameter_tree_value_type_inference_runner::main
        }
        "p4b_02b34_parameter_tree_typed_form_runner" => {
            p4b_02b34_parameter_tree_typed_form_runner::main
        }
        "p4b_02b35_parameter_tree_leaf_projection_runner" => {
            p4b_02b35_parameter_tree_leaf_projection_runner::main
        }
        "p4b_02b36_parameter_tree_batch_rename_runner" => {
            p4b_02b36_parameter_tree_batch_rename_runner::main
        }
        "p4b_02b37_parameter_tree_leaf_value_decoding_runner" => {
            p4b_02b37_parameter_tree_leaf_value_decoding_runner::main
        }
        "p4b_02b38_parameter_tree_apply_defaults_runner" => {
            p4b_02b38_parameter_tree_apply_defaults_runner::main
        }
        "p4b_02b39_parameter_tree_leaf_value_set_runner" => {
            p4b_02b39_parameter_tree_leaf_value_set_runner::main
        }
        "p4b_02b4_catalog_default_runner" => p4b_02b4_catalog_default_runner::main,
        "p4b_02b40_parameter_tree_leaf_search_runner" => {
            p4b_02b40_parameter_tree_leaf_search_runner::main
        }
        "p4b_02b41_parameter_tree_inferred_decode_runner" => {
            p4b_02b41_parameter_tree_inferred_decode_runner::main
        }
        "p4b_02b42_parameter_tree_typed_form_multi_runner" => {
            p4b_02b42_parameter_tree_typed_form_multi_runner::main
        }
        "p4b_02b43_parameter_tree_reserved_name_check_runner" => {
            p4b_02b43_parameter_tree_reserved_name_check_runner::main
        }
        "p4b_02b44_parameter_profile_assembly_runner" => {
            p4b_02b44_parameter_profile_assembly_runner::main
        }
        "p4b_02b45_parameter_tree_path_string_runner" => {
            p4b_02b45_parameter_tree_path_string_runner::main
        }
        "p4b_02b46_parameter_tree_expected_check_runner" => {
            p4b_02b46_parameter_tree_expected_check_runner::main
        }
        "p4b_02b47_parameter_profile_diff_runner" => p4b_02b47_parameter_profile_diff_runner::main,
        "p4b_02b48_parameter_profile_merge_runner" => {
            p4b_02b48_parameter_profile_merge_runner::main
        }
        "p4b_02b49_parameter_tree_allowed_name_check_runner" => {
            p4b_02b49_parameter_tree_allowed_name_check_runner::main
        }
        "p4b_02b5_ami_runtime_params_runner" => p4b_02b5_ami_runtime_params_runner::main,
        "p4b_02b50_parameter_tree_flatten_runner" => p4b_02b50_parameter_tree_flatten_runner::main,
        "p4b_02b51_ami_text_document_stats_runner" => {
            p4b_02b51_ami_text_document_stats_runner::main
        }
        "p4b_02b52_parameter_tree_token_remap_runner" => {
            p4b_02b52_parameter_tree_token_remap_runner::main
        }
        "p4b_02b53_parameter_tree_batch_value_set_runner" => {
            p4b_02b53_parameter_tree_batch_value_set_runner::main
        }
        "p4b_02b54_parameter_tree_duplicate_check_runner" => {
            p4b_02b54_parameter_tree_duplicate_check_runner::main
        }
        "p4b_02b55_parameter_profile_completeness_runner" => {
            p4b_02b55_parameter_profile_completeness_runner::main
        }
        "p4b_02b56_parameter_tree_path_join_runner" => {
            p4b_02b56_parameter_tree_path_join_runner::main
        }
        "p4b_02b57_parameter_tree_sections_runner" => {
            p4b_02b57_parameter_tree_sections_runner::main
        }
        "p4b_02b58_parameter_tree_typed_form_report_runner" => {
            p4b_02b58_parameter_tree_typed_form_report_runner::main
        }
        "p4b_02b59_parameter_tree_leaf_occurrences_runner" => {
            p4b_02b59_parameter_tree_leaf_occurrences_runner::main
        }
        "p4b_02b6_parameter_extractor_runner" => p4b_02b6_parameter_extractor_runner::main,
        "p4b_02b60_parameter_tree_token_frequencies_runner" => {
            p4b_02b60_parameter_tree_token_frequencies_runner::main
        }
        "p4b_02b61_ami_text_form_heads_runner" => p4b_02b61_ami_text_form_heads_runner::main,
        "p4b_02b62_parameter_tree_required_name_check_runner" => {
            p4b_02b62_parameter_tree_required_name_check_runner::main
        }
        "p4b_02b63_parameter_tree_distinct_leaf_names_runner" => {
            p4b_02b63_parameter_tree_distinct_leaf_names_runner::main
        }
        "p4b_02b64_parameter_profile_select_runner" => {
            p4b_02b64_parameter_profile_select_runner::main
        }
        "p4b_02b65_parameter_tree_path_relation_runner" => {
            p4b_02b65_parameter_tree_path_relation_runner::main
        }
        "p4b_02b66_parameter_tree_relative_path_runner" => {
            p4b_02b66_parameter_tree_relative_path_runner::main
        }
        "p4b_02b67_parameter_tree_longest_common_prefix_runner" => {
            p4b_02b67_parameter_tree_longest_common_prefix_runner::main
        }
        "p4b_02b68_parameter_tree_path_prefixes_runner" => {
            p4b_02b68_parameter_tree_path_prefixes_runner::main
        }
        "p4b_02b69_parameter_tree_profile_apply_runner" => {
            p4b_02b69_parameter_tree_profile_apply_runner::main
        }
        "p4b_02b7_parameter_trees_runner" => p4b_02b7_parameter_trees_runner::main,
        "p4b_02b70_parameter_value_equivalence_runner" => {
            p4b_02b70_parameter_value_equivalence_runner::main
        }
        "p4b_02b71_parameter_profile_equivalence_runner" => {
            p4b_02b71_parameter_profile_equivalence_runner::main
        }
        "p4b_02b72_parameter_profile_tree_coverage_runner" => {
            p4b_02b72_parameter_profile_tree_coverage_runner::main
        }
        "p4b_02b73_parameter_profile_type_stats_runner" => {
            p4b_02b73_parameter_profile_type_stats_runner::main
        }
        "p4b_02b74_parameter_profile_typed_merge_runner" => {
            p4b_02b74_parameter_profile_typed_merge_runner::main
        }
        "p4b_02b75_parameter_value_spelling_normalization_runner" => {
            p4b_02b75_parameter_value_spelling_normalization_runner::main
        }
        "p4b_02b76_parameter_profile_override_merge_runner" => {
            p4b_02b76_parameter_profile_override_merge_runner::main
        }
        "p4b_02b77_parameter_profile_canonicalization_runner" => {
            p4b_02b77_parameter_profile_canonicalization_runner::main
        }
        "p4b_02b78_parameter_tree_leaf_canonicalization_runner" => {
            p4b_02b78_parameter_tree_leaf_canonicalization_runner::main
        }
        "p4b_02b79_parameter_profile_typed_diff_runner" => {
            p4b_02b79_parameter_profile_typed_diff_runner::main
        }
        "p4b_02b8_parameter_tree_query_runner" => p4b_02b8_parameter_tree_query_runner::main,
        "p4b_02b80_parameter_profile_value_lookup_runner" => {
            p4b_02b80_parameter_profile_value_lookup_runner::main
        }
        "p4b_02b81_parameter_profile_serialization_runner" => {
            p4b_02b81_parameter_profile_serialization_runner::main
        }
        "p4b_02b82_parameter_profile_deserialization_runner" => {
            p4b_02b82_parameter_profile_deserialization_runner::main
        }
        "p4b_02b83_parameter_list_item_count_runner" => {
            p4b_02b83_parameter_list_item_count_runner::main
        }
        "p4b_02b84_parameter_list_item_access_runner" => {
            p4b_02b84_parameter_list_item_access_runner::main
        }
        "p4b_02b85_parameter_list_contains_runner" => {
            p4b_02b85_parameter_list_contains_runner::main
        }
        "p4b_02b86_parameter_profile_names_by_type_runner" => {
            p4b_02b86_parameter_profile_names_by_type_runner::main
        }
        "p4b_02b87_parameter_tree_leaf_type_map_runner" => {
            p4b_02b87_parameter_tree_leaf_type_map_runner::main
        }
        "p4b_02b88_parameter_tree_leaf_type_resolution_runner" => {
            p4b_02b88_parameter_tree_leaf_type_resolution_runner::main
        }
        "p4b_02b89_parameter_tree_leaf_typed_diff_runner" => {
            p4b_02b89_parameter_tree_leaf_typed_diff_runner::main
        }
        "p4b_02b9_parameter_tree_formatter_runner" => {
            p4b_02b9_parameter_tree_formatter_runner::main
        }
        "p4b_02b90_parameter_profile_typed_subset_runner" => {
            p4b_02b90_parameter_profile_typed_subset_runner::main
        }
        "p4b_02b91_parameter_tree_leaf_value_validity_runner" => {
            p4b_02b91_parameter_tree_leaf_value_validity_runner::main
        }
        "p4b_02b92_parameter_profile_canonical_spelling_groups_runner" => {
            p4b_02b92_parameter_profile_canonical_spelling_groups_runner::main
        }
        "p4b_02b93_parameter_tree_typed_leaf_type_counts_runner" => {
            p4b_02b93_parameter_tree_typed_leaf_type_counts_runner::main
        }
        "p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner" => {
            p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner::main
        }
        "p4b_02b95_parameter_profile_canonical_spelling_check_runner" => {
            p4b_02b95_parameter_profile_canonical_spelling_check_runner::main
        }
        "p4b_02b96_parameter_profile_fingerprint_runner" => {
            p4b_02b96_parameter_profile_fingerprint_runner::main
        }
        "p4b_02b97_parameter_tree_typed_leaf_fingerprint_runner" => {
            p4b_02b97_parameter_tree_typed_leaf_fingerprint_runner::main
        }
        "p4b_02b98_parameter_list_dedup_runner" => p4b_02b98_parameter_list_dedup_runner::main,
        "p4b_02b99_parameter_list_replace_runner" => p4b_02b99_parameter_list_replace_runner::main,
        _ => {
            eprintln!("unknown SIPI_P4B_RUNNER");
            std::process::exit(2);
        }
    };
    entry();
}
