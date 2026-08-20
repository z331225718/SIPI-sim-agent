#![forbid(unsafe_code)]

//! Clean-room bounded structural parsing for AMI-like text forms.
//!
//! This crate intentionally has no AMI parameter, model, ABI, file, or runtime
//! semantics. It retains only bounded UTF-8 structural text and source spans.

mod ami_runtime_params_v1;
mod parameter_extractor_v1;
mod parameter_trees_v1;
mod parameter_tree_query_v1;
mod parameter_tree_formatter_v1;
mod parameter_tree_validator_v1;
mod parameter_tree_diff_v1;
mod parameter_tree_merge_v1;
mod parameter_tree_pruning_v1;
mod parameter_tree_visitor_v1;
mod parameter_tree_transformer_v1;
mod parameter_tree_index_v1;
mod parameter_tree_diff_patch_v1;
mod parameter_tree_filter_v1;
mod parameter_tree_serde_v1;
mod parameter_tree_diff_stats_v1;
mod parameter_tree_diff_filter_v1;
mod parameter_tree_diff_summary_v1;
mod parameter_tree_subtree_v1;
mod parameter_tree_rename_v1;
mod parameter_tree_detect_cycles_v1;
mod parameter_tree_compose_v1;
mod parameter_tree_replace_v1;
mod parameter_tree_toposort_v1;
mod parameter_tree_depth_stats_v1;
mod parameter_tree_leaf_index_v1;
mod parameter_tree_token_stats_v1;
mod parameter_tree_validate_values_v1;
mod parameter_tree_infer_types_v1;
mod parameter_tree_typed_form_v1;
mod parameter_tree_project_v1;
mod parameter_tree_batch_rename_v1;
mod parameter_tree_decode_values_v1;
mod parameter_tree_apply_defaults_v1;
mod parameter_tree_set_value_v1;
mod parameter_tree_search_v1;
mod parameter_tree_inferred_decode_v1;
mod parameter_tree_typed_form_multi_v1;
mod parameter_tree_reserved_check_v1;
mod parameter_profile_assembly_v1;
mod parameter_tree_path_string_v1;
mod parameter_tree_expected_check_v1;
mod parameter_profile_diff_v1;
mod parameter_profile_merge_v1;
mod parameter_tree_allowed_check_v1;
mod parameter_tree_flatten_v1;
mod ami_text_document_stats_v1;
mod parameter_tree_token_remap_v1;
mod parameter_tree_set_values_batch_v1;
mod parameter_tree_duplicate_check_v1;
mod parameter_profile_completeness_v1;
mod parameter_tree_path_join_v1;
mod parameter_tree_sections_v1;
mod parameter_tree_typed_form_report_v1;
mod parameter_tree_leaf_occurrences_v1;
mod parameter_tree_token_frequencies_v1;
mod ami_text_form_heads_v1;
mod parameter_tree_required_check_v1;
mod parameter_tree_distinct_leaf_names_v1;
mod parameter_profile_select_v1;
mod parameter_tree_path_relation_v1;
mod parameter_tree_relative_path_v1;
mod parameter_tree_longest_common_prefix_v1;
mod parameter_tree_path_prefixes_v1;
mod parameter_tree_profile_apply_v1;
mod parameter_value_equivalence_v1;
mod parameter_profile_equivalence_v1;
mod parameter_profile_tree_coverage_v1;
mod parameter_profile_type_stats_v1;
mod parameter_profile_typed_merge_v1;
mod parameter_value_spelling_normalization_v1;
mod parameter_profile_override_merge_v1;
mod parameter_profile_canonicalization_v1;
mod parameter_tree_leaf_canonicalization_v1;
mod parameter_profile_typed_diff_v1;
mod parameter_profile_value_lookup_v1;
mod parameter_profile_serialization_v1;
mod parameter_profile_deserialization_v1;
mod parameter_list_item_count_v1;
mod parameter_list_item_access_v1;
mod parameter_list_contains_v1;
mod parameter_profile_names_by_type_v1;
mod parameter_tree_leaf_type_map_v1;
mod parameter_tree_leaf_type_resolution_v1;
mod parameter_tree_leaf_typed_diff_v1;
mod parameter_profile_typed_subset_v1;
mod parameter_tree_leaf_value_validity_v1;
mod parameter_profile_canonical_spelling_groups_v1;
mod parameter_tree_typed_leaf_type_counts_v1;
mod parameter_tree_leaf_canonical_spelling_check_v1;
mod parameter_profile_canonical_spelling_check_v1;
mod parameter_profile_fingerprint_v1;
mod parameter_tree_typed_leaf_fingerprint_v1;
mod parameter_list_dedup_v1;
mod parameter_list_replace_v1;
mod parameter_list_remove_v1;
mod parameter_list_append_v1;
mod parameter_list_insert_v1;
mod parameter_list_swap_v1;
mod parameter_list_reverse_v1;
mod parameter_list_sort_v1;
mod parameter_list_join_v1;
mod parameter_list_first_occurrence_map_v1;
mod parameter_list_last_occurrence_map_v1;
mod parameter_list_occurrence_indices_map_v1;
mod parameter_list_last_occurrence_indices_v1;
mod parameter_list_frequency_map_v1;
mod parameter_list_pairwise_equal_adjacent_v1;
mod parameter_list_relative_frequency_map_v1;
mod parameter_list_prevalence_map_v1;
mod parameter_list_is_balanced_v1;
mod parameter_list_distinct_count_v1;
mod parameter_list_occurrence_count_v1;
mod parameter_list_slice_v1;
mod parameter_list_index_of_v1;
mod parameter_list_last_index_of_v1;
mod parameter_list_remove_all_v1;
mod parameter_list_keep_only_v1;
mod parameter_list_split_v1;
mod parameter_list_rotate_v1;
mod parameter_list_chunk_v1;
mod parameter_list_head_tail_v1;
mod parameter_list_window_v1;
mod parameter_list_run_length_encode_v1;
mod parameter_list_longest_run_v1;
mod parameter_list_frequency_v1;
mod parameter_list_most_frequent_v1;
mod parameter_list_least_frequent_v1;
mod parameter_list_is_sorted_v1;
mod parameter_list_is_strictly_sorted_v1;
mod parameter_list_is_palindrome_v1;
mod parameter_list_contains_sublist_v1;
mod parameter_list_sublist_index_v1;
mod parameter_list_last_sublist_index_v1;
mod parameter_list_longest_common_prefix_v1;
mod parameter_list_longest_common_suffix_v1;
mod parameter_list_interleave_v1;
mod parameter_list_inversion_count_v1;
mod parameter_list_equal_adjacent_count_v1;
mod parameter_list_distinct_pair_count_v1;
mod parameter_list_unique_item_count_v1;
mod parameter_list_duplicate_item_count_v1;
mod parameter_list_first_duplicate_index_v1;
mod parameter_list_last_duplicate_index_v1;
mod parameter_list_multi_remove_all_v1;
mod parameter_list_multi_keep_only_v1;
mod parameter_list_longest_common_subsequence_length_v1;
mod parameter_list_edit_distance_v1;
mod parameter_list_has_subsequence_v1;
mod parameter_list_hamming_distance_v1;
mod parameter_list_starts_with_v1;
mod parameter_list_ends_with_v1;
mod parameter_list_intersection_v1;
mod parameter_list_symmetric_difference_v1;
mod parameter_list_union_v1;
mod parameter_list_relative_complement_v1;
mod parameter_list_multiset_equal_v1;
mod parameter_list_contains_multiset_v1;
mod parameter_list_jaccard_index_v1;
mod parameter_list_dice_index_v1;
mod parameter_list_overlap_coefficient_v1;
mod parameter_list_contains_sequence_v1;
mod parameter_list_tversky_index_v1;
mod parameter_list_longest_common_subsequence_v1;
mod parameter_list_all_equal_v1;
mod parameter_list_min_max_item_v1;
mod parameter_list_nth_smallest_item_v1;
mod parameter_list_nth_largest_item_v1;
mod parameter_list_median_item_v1;
mod parameter_list_mode_items_v1;
mod parameter_list_anti_mode_items_v1;
mod parameter_list_dedup_keep_last_v1;
mod parameter_list_run_count_v1;
mod parameter_list_sorted_rank_v1;
mod parameter_list_longest_run_item_v1;
mod parameter_list_longest_run_start_index_v1;
mod parameter_list_adjacent_change_count_v1;
mod parameter_list_total_equal_pair_count_v1;
mod parameter_list_majority_item_v1;
mod parameter_list_is_alternating_v1;
mod parameter_list_entropy_v1;
mod parameter_list_gini_impurity_v1;
mod parameter_list_normalized_entropy_v1;
mod parameter_list_mode_frequency_v1;
mod parameter_list_prevalence_ratio_v1;
mod parameter_list_frequency_normalized_v1;
mod parameter_list_first_occurrence_indices_v1;
mod parameter_list_run_boundaries_v1;
mod parameter_list_pairwise_distinct_adjacent_v1;
mod catalog_default_v1;
mod parameter_catalog_v1;
mod parameter_form_binding_v1;
mod parameter_value_v1;
pub use parameter_tree_diff_summary_v1::{
    generate_parameter_tree_diff_summary_v1, AmiParameterTreeDiffSummaryReportV1,
    ParameterTreeDiffSummaryErrorV1, PARAMETER_TREE_DIFF_SUMMARY_POLICY_V1,
};
pub use parameter_tree_subtree_v1::{
    extract_parameter_tree_subtree_v1, ParameterTreeSubtreeErrorV1,
    PARAMETER_TREE_SUBTREE_POLICY_V1,
};
pub use parameter_tree_rename_v1::{
    rename_parameter_tree_node_v1, ParameterTreeRenameErrorV1,
    PARAMETER_TREE_RENAME_POLICY_V1,
};
pub use parameter_tree_detect_cycles_v1::{
    detect_parameter_tree_cycles_v1, ParameterTreeCycleScanV1,
    ParameterTreeDetectCyclesErrorV1, PARAMETER_TREE_DETECT_CYCLES_POLICY_V1,
};
pub use parameter_tree_compose_v1::{
    compose_parameter_tree_subtree_v1, ParameterTreeComposeErrorV1,
    PARAMETER_TREE_COMPOSE_POLICY_V1,
};
pub use parameter_tree_replace_v1::{
    replace_parameter_tree_node_v1, ParameterTreeReplaceErrorV1,
    PARAMETER_TREE_REPLACE_POLICY_V1,
};
pub use parameter_tree_toposort_v1::{
    toposort_parameter_tree_paths_v1, ParameterTreeToposortErrorV1,
    PARAMETER_TREE_TOPOSORT_POLICY_V1,
};
pub use parameter_tree_depth_stats_v1::{
    compute_parameter_tree_depth_stats_v1, ParameterTreeDepthStatsV1,
    ParameterTreeDepthStatsErrorV1, PARAMETER_TREE_DEPTH_STATS_POLICY_V1,
};
pub use parameter_tree_leaf_index_v1::{
    build_parameter_tree_leaf_index_v1, ParameterTreeLeafIndexV1,
    ParameterTreeLeafIndexErrorV1, PARAMETER_TREE_LEAF_INDEX_POLICY_V1,
};
pub use parameter_tree_token_stats_v1::{
    compute_parameter_tree_token_stats_v1, ParameterTreeTokenStatsV1,
    ParameterTreeTokenStatsErrorV1, PARAMETER_TREE_TOKEN_STATS_POLICY_V1,
};
pub use parameter_tree_validate_values_v1::{
    validate_parameter_tree_values_v1, ParameterTreeValueValidationV1,
    ParameterTreeValueValidationErrorV1, PARAMETER_TREE_VALUE_VALIDATION_POLICY_V1,
};
pub use parameter_tree_infer_types_v1::{
    infer_parameter_tree_leaf_types_v1, ParameterTreeTypeInferenceV1,
    ParameterTreeTypeInferenceErrorV1, PARAMETER_TREE_VALUE_TYPE_INFERENCE_POLICY_V1,
};
pub use parameter_tree_typed_form_v1::{
    extract_typed_parameter_forms_v1, ParameterTreeTypedFormsV1,
    ParameterTreeTypedFormErrorV1, PARAMETER_TREE_TYPED_FORM_POLICY_V1,
};
pub use parameter_tree_project_v1::{
    project_parameter_tree_leaves_v1, ParameterTreeProjectErrorV1,
    PARAMETER_TREE_LEAF_PROJECTION_POLICY_V1,
};
pub use parameter_tree_batch_rename_v1::{
    rename_parameter_tree_leaves_v1, ParameterTreeBatchRenameErrorV1,
    PARAMETER_TREE_BATCH_RENAME_POLICY_V1,
};
pub use parameter_tree_decode_values_v1::{
    decode_parameter_tree_leaf_values_v1, DecodedLeafValueV1,
    ParameterTreeLeafValueDecodingV1, ParameterTreeLeafValueDecodingErrorV1,
    PARAMETER_TREE_LEAF_VALUE_DECODING_POLICY_V1,
};
pub use parameter_tree_apply_defaults_v1::{
    apply_parameter_tree_defaults_v1, ParameterTreeDefaultsAppliedV1,
    ParameterTreeDefaultsErrorV1, PARAMETER_TREE_APPLY_DEFAULTS_POLICY_V1,
};
pub use parameter_tree_set_value_v1::{
    set_parameter_tree_leaf_value_v1, ParameterTreeValueSetErrorV1,
    PARAMETER_TREE_LEAF_VALUE_SET_POLICY_V1,
};
pub use parameter_tree_search_v1::{
    find_parameter_tree_leaves_by_token_v1, ParameterTreeSearchErrorV1,
    PARAMETER_TREE_LEAF_SEARCH_POLICY_V1,
};
pub use parameter_tree_inferred_decode_v1::{
    decode_parameter_tree_with_inferred_types_v1, ParameterTreeInferredDecodingV1,
    ParameterTreeInferredDecodingErrorV1, PARAMETER_TREE_INFERRED_DECODE_POLICY_V1,
};
pub use parameter_tree_typed_form_multi_v1::{
    extract_typed_parameter_forms_multi_v1, ParameterTreeMultiTypedFormsV1,
    ParameterTreeMultiFormErrorV1, PARAMETER_TREE_TYPED_FORM_MULTI_POLICY_V1,
};
pub use parameter_tree_reserved_check_v1::{
    check_parameter_tree_reserved_names_v1, ParameterTreeReservedNameCheckV1,
    ParameterTreeReservedNameErrorV1, PARAMETER_TREE_RESERVED_NAME_CHECK_POLICY_V1,
};
pub use parameter_profile_assembly_v1::{
    assemble_parameter_profile_v1, ParameterProfileAssemblyV1,
    ParameterProfileAssemblyErrorV1, PARAMETER_PROFILE_ASSEMBLY_POLICY_V1,
};
pub use parameter_tree_path_string_v1::{
    parse_parameter_tree_path_string_v1, ParameterTreePathParseErrorV1,
    PARAMETER_TREE_PATH_STRING_POLICY_V1,
};
pub use parameter_tree_expected_check_v1::{
    check_parameter_tree_against_expected_v1, ParameterTreeExpectedCheckV1,
    ParameterTreeExpectedCheckErrorV1, ParameterTreeValueMismatchV1,
    PARAMETER_TREE_EXPECTED_CHECK_POLICY_V1,
};
pub use parameter_profile_diff_v1::{
    diff_parameter_profiles_v1, ParameterProfileDiffV1, ParameterValueChangeV1,
    PARAMETER_PROFILE_DIFF_POLICY_V1,
};
pub use parameter_profile_merge_v1::{
    merge_parameter_profiles_v1, ParameterProfileMergeV1, ParameterProfileMergeErrorV1,
    PARAMETER_PROFILE_MERGE_POLICY_V1,
};
pub use parameter_tree_allowed_check_v1::{
    check_parameter_tree_allowed_names_v1, ParameterTreeAllowedNameCheckV1,
    ParameterTreeAllowedNameErrorV1, PARAMETER_TREE_ALLOWED_NAME_CHECK_POLICY_V1,
};
pub use parameter_tree_flatten_v1::{
    flatten_parameter_tree_v1, ParameterTreeNodeKindV1, ParameterTreeNodeRecordV1,
    PARAMETER_TREE_FLATTEN_POLICY_V1,
};
pub use ami_text_document_stats_v1::{
    compute_ami_text_document_stats_v1, AmiTextDocumentStatsV1, AmiTextStatsErrorV1,
    AMI_TEXT_DOCUMENT_STATS_POLICY_V1,
};
pub use parameter_tree_token_remap_v1::{
    remap_parameter_tree_tokens_v1, ParameterTreeTokenRemapV1,
    ParameterTreeTokenRemapErrorV1, PARAMETER_TREE_TOKEN_REMAP_POLICY_V1,
};
pub use parameter_tree_set_values_batch_v1::{
    set_parameter_tree_leaf_values_v1, ParameterTreeValueSetBatchV1,
    ParameterTreeBatchValueSetErrorV1, PARAMETER_TREE_BATCH_VALUE_SET_POLICY_V1,
};
pub use parameter_tree_duplicate_check_v1::{
    check_parameter_tree_duplicate_consistency_v1, ParameterTreeDuplicateCheckV1,
    PARAMETER_TREE_DUPLICATE_CHECK_POLICY_V1,
};
pub use parameter_profile_completeness_v1::{
    check_parameter_profile_completeness_v1, ParameterProfileCompletenessV1,
    ParameterProfileCompletenessErrorV1, PARAMETER_PROFILE_COMPLETENESS_POLICY_V1,
};
pub use parameter_tree_path_join_v1::{
    join_parameter_tree_path_v1, ParameterTreePathJoinErrorV1,
    PARAMETER_TREE_PATH_JOIN_POLICY_V1,
};
pub use parameter_tree_sections_v1::{
    list_parameter_tree_sections_v1, ParameterTreeSectionKindV1, ParameterTreeSectionV1,
    ParameterTreeSectionsErrorV1, PARAMETER_TREE_SECTIONS_POLICY_V1,
};
pub use parameter_tree_typed_form_report_v1::{
    check_parameter_tree_typed_form_conformance_v1, ParameterTreeTypedFormReportEntryV1,
    ParameterTreeTypedFormReportV1, TypedFormViolationV1,
    PARAMETER_TREE_TYPED_FORM_CONFORMANCE_POLICY_V1,
};
pub use parameter_tree_leaf_occurrences_v1::{
    count_parameter_tree_leaf_occurrences_v1, ParameterTreeLeafOccurrencesV1,
    PARAMETER_TREE_LEAF_OCCURRENCES_POLICY_V1,
};
pub use parameter_tree_token_frequencies_v1::{
    compute_parameter_tree_token_frequencies_v1, ParameterTreeTokenFrequenciesV1,
    PARAMETER_TREE_TOKEN_FREQUENCIES_POLICY_V1,
};
pub use ami_text_form_heads_v1::{
    count_ami_text_form_heads_v1, AmiTextFormHeadsErrorV1, AMI_TEXT_FORM_HEADS_POLICY_V1,
};
pub use parameter_tree_required_check_v1::{
    check_parameter_tree_required_names_v1, ParameterTreeRequiredNameCheckV1,
    ParameterTreeRequiredNameErrorV1, PARAMETER_TREE_REQUIRED_NAME_CHECK_POLICY_V1,
};
pub use parameter_tree_distinct_leaf_names_v1::{
    list_parameter_tree_distinct_leaf_names_v1, ParameterTreeDistinctLeafNamesV1,
    PARAMETER_TREE_DISTINCT_LEAF_NAMES_POLICY_V1,
};
pub use parameter_profile_select_v1::{
    select_parameter_profile_v1, ParameterProfileSelectionV1,
    ParameterProfileSelectionErrorV1, PARAMETER_PROFILE_SELECTION_POLICY_V1,
};
pub use parameter_tree_path_relation_v1::{
    classify_parameter_tree_path_relation_v1, ParameterTreePathRelationErrorV1,
    ParameterTreePathRelationV1, PARAMETER_TREE_PATH_RELATION_POLICY_V1,
};
pub use parameter_tree_relative_path_v1::{
    relative_parameter_tree_path_v1, ParameterTreeRelativePathErrorV1,
    PARAMETER_TREE_RELATIVE_PATH_POLICY_V1,
};
pub use parameter_tree_longest_common_prefix_v1::{
    longest_common_path_prefix_v1, ParameterTreeLcpErrorV1,
    PARAMETER_TREE_LONGEST_COMMON_PREFIX_POLICY_V1,
};
pub use parameter_tree_path_prefixes_v1::{
    enumerate_parameter_tree_path_prefixes_v1, ParameterTreePathPrefixErrorV1,
    PARAMETER_TREE_PATH_PREFIXES_POLICY_V1,
};
pub use parameter_list_occurrence_count_v1::{
    count_parameter_list_item_occurrences_v1, ParameterListOccurrenceCountErrorV1,
    PARAMETER_LIST_OCCURRENCE_COUNT_POLICY_V1,
};
pub use parameter_list_slice_v1::{
    slice_parameter_list_items_v1, ParameterListSliceErrorV1,
    PARAMETER_LIST_SLICE_POLICY_V1,
};
pub use parameter_list_index_of_v1::{
    index_of_parameter_list_item_v1, ParameterListIndexOfErrorV1,
    PARAMETER_LIST_INDEX_OF_POLICY_V1,
};
pub use parameter_list_last_index_of_v1::{
    last_index_of_parameter_list_item_v1, ParameterListLastIndexOfErrorV1,
    PARAMETER_LIST_LAST_INDEX_OF_POLICY_V1,
};
pub use parameter_list_remove_all_v1::{
    remove_all_parameter_list_items_v1, ParameterListRemoveAllErrorV1,
    PARAMETER_LIST_REMOVE_ALL_POLICY_V1,
};
pub use parameter_list_keep_only_v1::{
    keep_only_parameter_list_items_v1, ParameterListKeepOnlyErrorV1,
    PARAMETER_LIST_KEEP_ONLY_POLICY_V1,
};
pub use parameter_list_split_v1::{
    split_parameter_list_at_index_v1, ParameterListSplitErrorV1,
    PARAMETER_LIST_SPLIT_POLICY_V1,
};
pub use parameter_list_rotate_v1::{
    rotate_parameter_list_left_v1, ParameterListRotateErrorV1,
    PARAMETER_LIST_ROTATE_POLICY_V1,
};
pub use parameter_list_chunk_v1::{
    chunk_parameter_list_v1, ParameterListChunkErrorV1,
    PARAMETER_LIST_CHUNK_POLICY_V1,
};
pub use parameter_list_head_tail_v1::{
    parameter_list_head_tail_v1, ParameterListHeadTailErrorV1,
    PARAMETER_LIST_HEAD_TAIL_POLICY_V1,
};
pub use parameter_list_window_v1::{
    window_parameter_list_v1, ParameterListWindowErrorV1,
    PARAMETER_LIST_WINDOW_POLICY_V1,
};
pub use parameter_list_run_length_encode_v1::{
    run_length_encode_parameter_list_v1, ParameterListRunLengthEncodeErrorV1,
    PARAMETER_LIST_RUN_LENGTH_ENCODE_POLICY_V1,
};
pub use parameter_list_longest_run_v1::{
    longest_run_parameter_list_v1, ParameterListLongestRunErrorV1,
    PARAMETER_LIST_LONGEST_RUN_POLICY_V1,
};
pub use parameter_list_frequency_v1::{
    parameter_list_item_frequencies_v1, ParameterListFrequencyErrorV1,
    PARAMETER_LIST_FREQUENCY_POLICY_V1,
};
pub use parameter_list_most_frequent_v1::{
    most_frequent_parameter_list_item_v1, ParameterListMostFrequentErrorV1,
    PARAMETER_LIST_MOST_FREQUENT_POLICY_V1,
};
pub use parameter_list_least_frequent_v1::{
    least_frequent_parameter_list_item_v1, ParameterListLeastFrequentErrorV1,
    PARAMETER_LIST_LEAST_FREQUENT_POLICY_V1,
};
pub use parameter_list_is_sorted_v1::{
    parameter_list_is_sorted_v1, ParameterListIsSortedErrorV1,
    PARAMETER_LIST_IS_SORTED_POLICY_V1,
};
pub use parameter_list_is_strictly_sorted_v1::{
    parameter_list_is_strictly_sorted_v1, ParameterListIsStrictlySortedErrorV1,
    PARAMETER_LIST_IS_STRICTLY_SORTED_POLICY_V1,
};
pub use parameter_list_is_palindrome_v1::{
    parameter_list_is_palindrome_v1, ParameterListIsPalindromeErrorV1,
    PARAMETER_LIST_IS_PALINDROME_POLICY_V1,
};
pub use parameter_list_contains_sublist_v1::{
    parameter_list_contains_sublist_v1, ParameterListContainsSublistErrorV1,
    PARAMETER_LIST_CONTAINS_SUBLIST_POLICY_V1,
};
pub use parameter_list_sublist_index_v1::{
    sublist_index_parameter_list_v1, ParameterListSublistIndexErrorV1,
    PARAMETER_LIST_SUBLIST_INDEX_POLICY_V1,
};
pub use parameter_list_last_sublist_index_v1::{
    last_sublist_index_parameter_list_v1, ParameterListLastSublistIndexErrorV1,
    PARAMETER_LIST_LAST_SUBLIST_INDEX_POLICY_V1,
};
pub use parameter_list_longest_common_prefix_v1::{
    list_longest_common_prefix_v1, ParameterListLongestCommonPrefixErrorV1,
    PARAMETER_LIST_LONGEST_COMMON_PREFIX_POLICY_V1,
};
pub use parameter_list_longest_common_suffix_v1::{
    list_longest_common_suffix_v1, ParameterListLongestCommonSuffixErrorV1,
    PARAMETER_LIST_LONGEST_COMMON_SUFFIX_POLICY_V1,
};
pub use parameter_list_interleave_v1::{
    interleave_parameter_list_values_v1, ParameterListInterleaveErrorV1,
    PARAMETER_LIST_INTERLEAVE_POLICY_V1,
};
pub use parameter_list_inversion_count_v1::{
    parameter_list_inversion_count_v1, ParameterListInversionCountErrorV1,
    PARAMETER_LIST_INVERSION_COUNT_POLICY_V1,
};
pub use parameter_list_equal_adjacent_count_v1::{
    parameter_list_equal_adjacent_count_v1, ParameterListEqualAdjacentCountErrorV1,
    PARAMETER_LIST_EQUAL_ADJACENT_COUNT_POLICY_V1,
};
pub use parameter_list_distinct_pair_count_v1::{
    parameter_list_distinct_pair_count_v1, ParameterListDistinctPairCountErrorV1,
    PARAMETER_LIST_DISTINCT_PAIR_COUNT_POLICY_V1,
};
pub use parameter_list_unique_item_count_v1::{
    parameter_list_unique_item_count_v1, ParameterListUniqueItemCountErrorV1,
    PARAMETER_LIST_UNIQUE_ITEM_COUNT_POLICY_V1,
};
pub use parameter_list_duplicate_item_count_v1::{
    parameter_list_duplicate_item_count_v1, ParameterListDuplicateItemCountErrorV1,
    PARAMETER_LIST_DUPLICATE_ITEM_COUNT_POLICY_V1,
};
pub use parameter_list_first_duplicate_index_v1::{
    parameter_list_first_duplicate_index_v1, ParameterListFirstDuplicateIndexErrorV1,
    PARAMETER_LIST_FIRST_DUPLICATE_INDEX_POLICY_V1,
};
pub use parameter_list_last_duplicate_index_v1::{
    parameter_list_last_duplicate_index_v1, ParameterListLastDuplicateIndexErrorV1,
    PARAMETER_LIST_LAST_DUPLICATE_INDEX_POLICY_V1,
};
pub use parameter_list_multi_remove_all_v1::{
    remove_all_parameter_list_items_multi_v1, ParameterListMultiRemoveAllErrorV1,
    PARAMETER_LIST_MULTI_REMOVE_ALL_POLICY_V1,
};
pub use parameter_list_multi_keep_only_v1::{
    keep_only_parameter_list_items_multi_v1, ParameterListMultiKeepOnlyErrorV1,
    PARAMETER_LIST_MULTI_KEEP_ONLY_POLICY_V1,
};
pub use parameter_list_longest_common_subsequence_length_v1::{
    list_longest_common_subsequence_length_v1, ParameterListLongestCommonSubsequenceLengthErrorV1,
    PARAMETER_LIST_LONGEST_COMMON_SUBSEQUENCE_LENGTH_POLICY_V1,
};
pub use parameter_list_edit_distance_v1::{
    list_edit_distance_v1, ParameterListEditDistanceErrorV1,
    PARAMETER_LIST_EDIT_DISTANCE_POLICY_V1,
};
pub use parameter_list_has_subsequence_v1::{
    parameter_list_has_subsequence_v1, ParameterListHasSubsequenceErrorV1,
    PARAMETER_LIST_HAS_SUBSEQUENCE_POLICY_V1,
};
pub use parameter_list_hamming_distance_v1::{
    list_hamming_distance_v1, ParameterListHammingDistanceErrorV1,
    PARAMETER_LIST_HAMMING_DISTANCE_POLICY_V1,
};
pub use parameter_list_starts_with_v1::{
    list_starts_with_v1, ParameterListStartsWithErrorV1,
    PARAMETER_LIST_STARTS_WITH_POLICY_V1,
};
pub use parameter_list_ends_with_v1::{
    list_ends_with_v1, ParameterListEndsWithErrorV1,
    PARAMETER_LIST_ENDS_WITH_POLICY_V1,
};
pub use parameter_list_intersection_v1::{
    list_intersection_v1, ParameterListIntersectionErrorV1,
    PARAMETER_LIST_INTERSECTION_POLICY_V1,
};
pub use parameter_list_symmetric_difference_v1::{
    list_symmetric_difference_v1, ParameterListSymmetricDifferenceErrorV1,
    PARAMETER_LIST_SYMMETRIC_DIFFERENCE_POLICY_V1,
};
pub use parameter_list_union_v1::{
    list_union_v1, ParameterListUnionErrorV1,
    PARAMETER_LIST_UNION_POLICY_V1,
};
pub use parameter_list_relative_complement_v1::{
    list_relative_complement_v1, ParameterListRelativeComplementErrorV1,
    PARAMETER_LIST_RELATIVE_COMPLEMENT_POLICY_V1,
};
pub use parameter_list_multiset_equal_v1::{
    list_multiset_equal_v1, ParameterListMultisetEqualErrorV1,
    PARAMETER_LIST_MULTISET_EQUAL_POLICY_V1,
};
pub use parameter_list_contains_multiset_v1::{
    list_contains_multiset_v1, ParameterListContainsMultisetErrorV1,
    PARAMETER_LIST_CONTAINS_MULTISET_POLICY_V1,
};
pub use parameter_list_jaccard_index_v1::{
    list_jaccard_index_v1, ParameterListJaccardIndexErrorV1,
    PARAMETER_LIST_JACCARD_INDEX_POLICY_V1,
};
pub use parameter_list_dice_index_v1::{
    list_dice_index_v1, ParameterListDiceIndexErrorV1,
    PARAMETER_LIST_DICE_INDEX_POLICY_V1,
};
pub use parameter_list_overlap_coefficient_v1::{
    list_overlap_coefficient_v1, ParameterListOverlapCoefficientErrorV1,
    PARAMETER_LIST_OVERLAP_COEFFICIENT_POLICY_V1,
};
pub use parameter_list_contains_sequence_v1::{
    list_contains_sequence_v1, ParameterListContainsSequenceErrorV1,
    PARAMETER_LIST_CONTAINS_SEQUENCE_POLICY_V1,
};
pub use parameter_list_tversky_index_v1::{
    list_tversky_index_v1, ParameterListTverskyIndexErrorV1,
    PARAMETER_LIST_TVERSKY_INDEX_POLICY_V1,
};
pub use parameter_list_longest_common_subsequence_v1::{
    list_longest_common_subsequence_v1, ParameterListLongestCommonSubsequenceErrorV1,
    PARAMETER_LIST_LONGEST_COMMON_SUBSEQUENCE_POLICY_V1,
};
pub use parameter_list_all_equal_v1::{
    parameter_list_all_equal_v1, ParameterListAllEqualErrorV1,
    PARAMETER_LIST_ALL_EQUAL_POLICY_V1,
};
pub use parameter_list_min_max_item_v1::{
    parameter_list_min_item_v1, parameter_list_max_item_v1,
    ParameterListMinMaxItemErrorV1, PARAMETER_LIST_MIN_MAX_ITEM_POLICY_V1,
};
pub use parameter_list_nth_smallest_item_v1::{
    parameter_list_nth_smallest_item_v1, ParameterListNthSmallestItemErrorV1,
    PARAMETER_LIST_NTH_SMALLEST_ITEM_POLICY_V1,
};
pub use parameter_list_nth_largest_item_v1::{
    parameter_list_nth_largest_item_v1, ParameterListNthLargestItemErrorV1,
    PARAMETER_LIST_NTH_LARGEST_ITEM_POLICY_V1,
};
pub use parameter_list_median_item_v1::{
    parameter_list_median_item_v1, ParameterListMedianItemErrorV1,
    PARAMETER_LIST_MEDIAN_ITEM_POLICY_V1,
};
pub use parameter_list_mode_items_v1::{
    parameter_list_mode_items_v1, ParameterListModeItemsErrorV1,
    PARAMETER_LIST_MODE_ITEMS_POLICY_V1,
};
pub use parameter_list_anti_mode_items_v1::{
    parameter_list_anti_mode_items_v1, ParameterListAntiModeItemsErrorV1,
    PARAMETER_LIST_ANTI_MODE_ITEMS_POLICY_V1,
};
pub use parameter_list_dedup_keep_last_v1::{
    parameter_list_dedup_keep_last_v1, ParameterListDedupKeepLastErrorV1,
    PARAMETER_LIST_DEDUP_KEEP_LAST_POLICY_V1,
};
pub use parameter_list_run_count_v1::{
    parameter_list_run_count_v1, ParameterListRunCountErrorV1,
    PARAMETER_LIST_RUN_COUNT_POLICY_V1,
};
pub use parameter_list_sorted_rank_v1::{
    parameter_list_sorted_rank_v1, ParameterListSortedRankErrorV1,
    PARAMETER_LIST_SORTED_RANK_POLICY_V1,
};
pub use parameter_list_longest_run_item_v1::{
    parameter_list_longest_run_item_v1, ParameterListLongestRunItemErrorV1,
    PARAMETER_LIST_LONGEST_RUN_ITEM_POLICY_V1,
};
pub use parameter_list_longest_run_start_index_v1::{
    parameter_list_longest_run_start_index_v1, ParameterListLongestRunStartIndexErrorV1,
    PARAMETER_LIST_LONGEST_RUN_START_INDEX_POLICY_V1,
};
pub use parameter_list_adjacent_change_count_v1::{
    parameter_list_adjacent_change_count_v1, ParameterListAdjacentChangeCountErrorV1,
    PARAMETER_LIST_ADJACENT_CHANGE_COUNT_POLICY_V1,
};
pub use parameter_list_total_equal_pair_count_v1::{
    parameter_list_total_equal_pair_count_v1, ParameterListTotalEqualPairCountErrorV1,
    PARAMETER_LIST_TOTAL_EQUAL_PAIR_COUNT_POLICY_V1,
};
pub use parameter_list_majority_item_v1::{
    parameter_list_majority_item_v1, ParameterListMajorityItemErrorV1,
    PARAMETER_LIST_MAJORITY_ITEM_POLICY_V1,
};
pub use parameter_list_is_alternating_v1::{
    parameter_list_is_alternating_v1, ParameterListIsAlternatingErrorV1,
    PARAMETER_LIST_IS_ALTERNATING_POLICY_V1,
};
pub use parameter_list_entropy_v1::{
    parameter_list_entropy_v1, ParameterListEntropyErrorV1,
    PARAMETER_LIST_ENTROPY_POLICY_V1,
};
pub use parameter_list_gini_impurity_v1::{
    parameter_list_gini_impurity_v1, ParameterListGiniImpurityErrorV1,
    PARAMETER_LIST_GINI_IMPURITY_POLICY_V1,
};
pub use parameter_list_normalized_entropy_v1::{
    parameter_list_normalized_entropy_v1, ParameterListNormalizedEntropyErrorV1,
    PARAMETER_LIST_NORMALIZED_ENTROPY_POLICY_V1,
};
pub use parameter_list_mode_frequency_v1::{
    parameter_list_mode_frequency_v1, ParameterListModeFrequencyErrorV1,
    PARAMETER_LIST_MODE_FREQUENCY_POLICY_V1,
};
pub use parameter_list_prevalence_ratio_v1::{
    parameter_list_prevalence_ratio_v1, ParameterListPrevalenceRatioErrorV1,
    PARAMETER_LIST_PREVALENCE_RATIO_POLICY_V1,
};
pub use parameter_list_frequency_normalized_v1::{
    parameter_list_frequency_normalized_v1, ParameterListFrequencyNormalizedErrorV1,
    PARAMETER_LIST_FREQUENCY_NORMALIZED_POLICY_V1,
};
pub use parameter_list_first_occurrence_indices_v1::{
    parameter_list_first_occurrence_indices_v1, ParameterListFirstOccurrenceIndicesErrorV1,
    PARAMETER_LIST_FIRST_OCCURRENCE_INDICES_POLICY_V1,
};
pub use parameter_list_run_boundaries_v1::{
    parameter_list_run_boundaries_v1, ParameterListRunBoundariesErrorV1,
    PARAMETER_LIST_RUN_BOUNDARIES_POLICY_V1,
};
pub use parameter_list_pairwise_distinct_adjacent_v1::{
    parameter_list_pairwise_distinct_adjacent_v1, ParameterListPairwiseDistinctAdjacentErrorV1,
    PARAMETER_LIST_PAIRWISE_DISTINCT_ADJACENT_POLICY_V1,
};
pub use parameter_list_first_occurrence_map_v1::{
    parameter_list_first_occurrence_map_v1, ParameterListFirstOccurrenceMapErrorV1,
    PARAMETER_LIST_FIRST_OCCURRENCE_MAP_POLICY_V1,
};
pub use parameter_list_last_occurrence_map_v1::{
    parameter_list_last_occurrence_map_v1, ParameterListLastOccurrenceMapErrorV1,
    PARAMETER_LIST_LAST_OCCURRENCE_MAP_POLICY_V1,
};
pub use parameter_list_occurrence_indices_map_v1::{
    parameter_list_occurrence_indices_map_v1, ParameterListOccurrenceIndicesMapErrorV1,
    PARAMETER_LIST_OCCURRENCE_INDICES_MAP_POLICY_V1,
};
pub use parameter_list_last_occurrence_indices_v1::{
    parameter_list_last_occurrence_indices_v1, ParameterListLastOccurrenceIndicesErrorV1,
    PARAMETER_LIST_LAST_OCCURRENCE_INDICES_POLICY_V1,
};
pub use parameter_list_frequency_map_v1::{
    parameter_list_frequency_map_v1, ParameterListFrequencyMapErrorV1,
    PARAMETER_LIST_FREQUENCY_MAP_POLICY_V1,
};
pub use parameter_list_pairwise_equal_adjacent_v1::{
    parameter_list_pairwise_equal_adjacent_v1, ParameterListPairwiseEqualAdjacentErrorV1,
    PARAMETER_LIST_PAIRWISE_EQUAL_ADJACENT_POLICY_V1,
};
pub use parameter_list_relative_frequency_map_v1::{
    parameter_list_relative_frequency_map_v1, ParameterListRelativeFrequencyMapErrorV1,
    PARAMETER_LIST_RELATIVE_FREQUENCY_MAP_POLICY_V1,
};
pub use parameter_list_prevalence_map_v1::{
    parameter_list_prevalence_map_v1, ParameterListPrevalenceMapErrorV1,
    PARAMETER_LIST_PREVALENCE_MAP_POLICY_V1,
};
pub use parameter_list_is_balanced_v1::{
    parameter_list_is_balanced_v1, ParameterListIsBalancedErrorV1,
    PARAMETER_LIST_IS_BALANCED_POLICY_V1,
};
pub use parameter_list_distinct_count_v1::{
    count_distinct_parameter_list_items_v1, ParameterListDistinctCountErrorV1,
    PARAMETER_LIST_DISTINCT_COUNT_POLICY_V1,
};
pub use parameter_list_join_v1::{
    join_parameter_list_values_v1, ParameterListJoinErrorV1,
    PARAMETER_LIST_JOIN_POLICY_V1,
};
pub use parameter_list_sort_v1::{
    sort_parameter_list_items_v1, ParameterListSortErrorV1,
    PARAMETER_LIST_SORT_POLICY_V1,
};
pub use parameter_list_reverse_v1::{
    reverse_parameter_list_items_v1, ParameterListReverseErrorV1,
    PARAMETER_LIST_REVERSE_POLICY_V1,
};
pub use parameter_list_swap_v1::{
    swap_parameter_list_items_v1, ParameterListSwapErrorV1,
    PARAMETER_LIST_SWAP_POLICY_V1,
};
pub use parameter_list_insert_v1::{
    insert_parameter_list_item_v1, ParameterListInsertErrorV1,
    PARAMETER_LIST_INSERT_POLICY_V1,
};
pub use parameter_list_append_v1::{
    append_parameter_list_item_v1, ParameterListAppendErrorV1,
    PARAMETER_LIST_APPEND_POLICY_V1,
};
pub use parameter_list_remove_v1::{
    remove_parameter_list_item_v1, ParameterListRemoveErrorV1,
    PARAMETER_LIST_REMOVE_POLICY_V1,
};
pub use parameter_list_replace_v1::{
    replace_parameter_list_item_v1, ParameterListReplaceErrorV1,
    PARAMETER_LIST_REPLACE_POLICY_V1,
};
pub use parameter_list_dedup_v1::{
    deduplicate_parameter_list_items_v1, ParameterListDedupErrorV1,
    PARAMETER_LIST_DEDUP_POLICY_V1,
};
pub use parameter_tree_typed_leaf_fingerprint_v1::{
    fingerprint_parameter_tree_typed_leaves_v1, PARAMETER_TREE_TYPED_LEAF_FINGERPRINT_POLICY_V1,
};
pub use parameter_profile_fingerprint_v1::{
    hash_parameter_profile_v1, PARAMETER_PROFILE_FINGERPRINT_POLICY_V1,
};
pub use parameter_profile_canonical_spelling_check_v1::{
    check_parameter_profile_spellings_canonical_v1, ParameterProfileCanonicalSpellingCheckV1,
    ParameterProfileCanonicalSpellingIssueV1, PARAMETER_PROFILE_CANONICAL_SPELLING_CHECK_POLICY_V1,
};
pub use parameter_tree_leaf_canonical_spelling_check_v1::{
    check_parameter_tree_leaf_spellings_canonical_v1,
    ParameterTreeLeafCanonicalSpellingCheckV1, ParameterTreeLeafCanonicalSpellingIssueV1,
    PARAMETER_TREE_LEAF_CANONICAL_SPELLING_CHECK_POLICY_V1,
};
pub use parameter_tree_typed_leaf_type_counts_v1::{
    count_parameter_tree_typed_leaves_by_type_v1, ParameterTreeTypedLeafTypeCountsV1,
    PARAMETER_TREE_TYPED_LEAF_TYPE_COUNTS_POLICY_V1,
};
pub use parameter_profile_canonical_spelling_groups_v1::{
    group_parameter_profile_names_by_canonical_spelling_v1,
    ParameterProfileCanonicalSpellingGroupsV1, ParameterProfileCanonicalSpellingGroupV1,
    PARAMETER_PROFILE_CANONICAL_SPELLING_GROUPS_POLICY_V1,
};
pub use parameter_tree_leaf_value_validity_v1::{
    check_parameter_tree_leaf_value_validity_v1, ParameterTreeLeafValueValidityReportV1,
    ParameterTreeLeafValueValidityIssueV1, PARAMETER_TREE_LEAF_VALUE_VALIDITY_POLICY_V1,
};
pub use parameter_profile_typed_subset_v1::{
    check_parameter_profile_typed_subset_v1, ParameterProfileTypedSubsetV1,
    ParameterProfileTypedSubsetMismatchV1, PARAMETER_PROFILE_TYPED_SUBSET_POLICY_V1,
};
pub use parameter_tree_leaf_typed_diff_v1::{
    diff_parameter_tree_leaves_typed_v1, ParameterTreeLeafTypedDiffV1,
    ParameterTreeLeafTypedChangeV1, PARAMETER_TREE_LEAF_TYPED_DIFF_POLICY_V1,
};
pub use parameter_tree_leaf_type_resolution_v1::{
    resolve_parameter_tree_leaf_type_v1, ParameterTreeLeafTypeResolutionErrorV1,
    PARAMETER_TREE_LEAF_TYPE_RESOLUTION_POLICY_V1,
};
pub use parameter_tree_leaf_type_map_v1::{
    extract_parameter_tree_leaf_type_map_v1, ParameterTreeLeafTypeMapV1,
    PARAMETER_TREE_LEAF_TYPE_MAP_POLICY_V1,
};
pub use parameter_profile_names_by_type_v1::{
    list_parameter_profile_names_by_type_v1, ParameterProfileNamesByTypeV1,
    ParameterProfileNamesByTypeErrorV1, PARAMETER_PROFILE_NAMES_BY_TYPE_POLICY_V1,
};
pub use parameter_list_contains_v1::{
    parameter_list_contains_item_v1, ParameterListContainsErrorV1,
    PARAMETER_LIST_CONTAINS_POLICY_V1,
};
pub use parameter_list_item_access_v1::{
    get_parameter_list_item_v1, ParameterListItemAccessErrorV1,
    PARAMETER_LIST_ITEM_ACCESS_POLICY_V1,
};
pub use parameter_list_item_count_v1::{
    count_parameter_list_items_v1, ParameterListItemCountErrorV1,
    PARAMETER_LIST_ITEM_COUNT_POLICY_V1,
};
pub use parameter_profile_deserialization_v1::{
    deserialize_parameter_profile_v1, ParameterProfileDeserializationV1,
    ParameterProfileDeserializationErrorV1, PARAMETER_PROFILE_DESERIALIZATION_POLICY_V1,
};
pub use parameter_profile_serialization_v1::{
    serialize_parameter_profile_v1, PARAMETER_PROFILE_SERIALIZATION_POLICY_V1,
};
pub use parameter_profile_value_lookup_v1::{
    find_parameter_profile_names_by_value_v1, ParameterProfileValueLookupV1,
    ParameterProfileValueLookupErrorV1, PARAMETER_PROFILE_VALUE_LOOKUP_POLICY_V1,
};
pub use parameter_profile_typed_diff_v1::{
    diff_parameter_profiles_typed_v1, ParameterProfileTypedDiffV1,
    ParameterProfileTypedChangeV1, PARAMETER_PROFILE_TYPED_DIFF_POLICY_V1,
};
pub use parameter_tree_leaf_canonicalization_v1::{
    canonicalize_parameter_tree_leaf_spellings_v1, ParameterTreeLeafCanonicalizationV1,
    PARAMETER_TREE_LEAF_CANONICALIZATION_POLICY_V1,
};
pub use parameter_profile_canonicalization_v1::{
    canonicalize_parameter_profile_v1, ParameterProfileCanonicalizationV1,
    PARAMETER_PROFILE_CANONICALIZATION_POLICY_V1,
};
pub use parameter_profile_override_merge_v1::{
    merge_parameter_profiles_with_override_v1, ParameterProfileOverrideMergeV1,
    PARAMETER_PROFILE_OVERRIDE_MERGE_POLICY_V1,
};
pub use parameter_value_spelling_normalization_v1::{
    canonicalize_parameter_value_spelling_v1,
    PARAMETER_VALUE_SPELLING_NORMALIZATION_POLICY_V1,
};
pub use parameter_profile_typed_merge_v1::{
    merge_parameter_profiles_typed_v1, ParameterProfileTypedMergeV1,
    ParameterProfileTypedMergeErrorV1, PARAMETER_PROFILE_TYPED_MERGE_POLICY_V1,
};
pub use parameter_profile_type_stats_v1::{
    compute_parameter_profile_type_stats_v1, ParameterProfileTypeStatsV1,
    PARAMETER_PROFILE_TYPE_STATS_POLICY_V1,
};
pub use parameter_profile_tree_coverage_v1::{
    check_parameter_profile_tree_coverage_v1, ParameterProfileTreeCoverageV1,
    PARAMETER_PROFILE_TREE_COVERAGE_POLICY_V1,
};
pub use parameter_profile_equivalence_v1::{
    parameter_profiles_equivalent_v1, ParameterProfileEquivalenceV1,
    ParameterProfileInequivalenceV1, ParameterProfileValueMismatchV1,
    PARAMETER_PROFILE_EQUIVALENCE_POLICY_V1,
};
pub use parameter_value_equivalence_v1::{
    parameter_values_equivalent_v1, ParameterValueEquivalenceV1,
    ParameterValueInequivalenceReasonV1, PARAMETER_VALUE_EQUIVALENCE_POLICY_V1,
};
pub use parameter_tree_profile_apply_v1::{
    apply_parameter_profile_to_tree_v1, ParameterTreeProfileApplyErrorV1,
    ParameterTreeProfileApplyV1, PARAMETER_TREE_PROFILE_APPLY_POLICY_V1,
};
pub use parameter_tree_diff_filter_v1::{
    filter_parameter_tree_diffs_v1, ParameterTreeDiffFilterErrorV1,
    PARAMETER_TREE_DIFF_FILTER_POLICY_V1,
};
pub use parameter_tree_diff_stats_v1::{
    compute_parameter_tree_diff_stats_v1, AmiParameterTreeDiffStatsV1,
    ParameterTreeDiffStatsErrorV1, PARAMETER_TREE_DIFF_STATS_POLICY_V1,
};
pub use parameter_tree_serde_v1::{
    deserialize_parameter_trees_v1, serialize_parameter_trees_v1,
    ParameterTreeSerdeErrorV1, PARAMETER_TREE_SERDE_POLICY_V1,
};
pub use parameter_tree_filter_v1::{
    filter_parameter_trees_v1, ParameterTreeFilterErrorV1,
    PARAMETER_TREE_FILTER_POLICY_V1,
};
pub use parameter_tree_diff_patch_v1::{
    apply_parameter_tree_diff_patch_v1, apply_parameter_tree_diff_patch_with_context_v1, ParameterTreeDiffPatchErrorV1,
    PARAMETER_TREE_DIFF_PATCH_POLICY_V1,
};
pub use parameter_tree_index_v1::{
    build_parameter_tree_index_v1, AmiParameterTreeIndexV1,
    ParameterTreeIndexErrorV1, PARAMETER_TREE_INDEX_POLICY_V1,
};
pub use parameter_tree_transformer_v1::{
    transform_parameter_trees_v1, ParameterTreeTransformerErrorV1,
    PARAMETER_TREE_TRANSFORMER_POLICY_V1,
};
pub use parameter_tree_visitor_v1::{
    traverse_parameter_trees_v1, ParameterTreeVisitorErrorV1, VisitorEventV1,
    PARAMETER_TREE_VISITOR_POLICY_V1,
};
pub use parameter_tree_pruning_v1::{
    prune_parameter_tree_v1, ParameterTreePruningErrorV1,
    PARAMETER_TREE_PRUNING_POLICY_V1,
};
pub use parameter_tree_merge_v1::{
    merge_parameter_trees_v1, ParameterTreeMergeErrorV1,
    PARAMETER_TREE_MERGE_POLICY_V1,
};
pub use parameter_tree_diff_v1::{
    diff_parameter_trees_v1, ParameterTreeDiffErrorV1, TreeDiffEntryV1,
    PARAMETER_TREE_DIFF_POLICY_V1,
};
pub use parameter_tree_validator_v1::{
    validate_parameter_trees_v1, ParameterTreeValidatorErrorV1,
    TreeValidationLimitsV1, PARAMETER_TREE_VALIDATOR_POLICY_V1,
};
pub use parameter_tree_formatter_v1::{
    format_parameter_trees_v1, ParameterTreeFormatterErrorV1,
    PARAMETER_TREE_FORMATTER_POLICY_V1,
};
pub use parameter_tree_query_v1::{
    query_parameter_tree_v1, ParameterTreeQueryErrorV1, QueryResultV1,
    PARAMETER_TREE_QUERY_POLICY_V1,
};
pub use parameter_trees_v1::{
    build_parameter_trees_v1, AmiParameterTreeNodeV1, AmiParameterTreeV1,
    ParameterTreesErrorV1, PARAMETER_TREES_POLICY_V1,
};
pub use parameter_extractor_v1::{
    extract_parameter_values_v1, ParameterExtractorErrorV1,
    PARAMETER_EXTRACTOR_POLICY_V1,
};
pub use ami_runtime_params_v1::{
    build_ami_runtime_params_v1, AmiRuntimeParamsV1, RuntimeParamV1, RuntimeParamsErrorV1,
    AMI_RUNTIME_PARAMS_POLICY_V1,
};
pub use catalog_default_v1::{
    materialize_default_v1, token_valid_for_type_v1, validate_catalog_defaults_v1,
    CatalogDefaultErrorV1, CATALOG_DEFAULT_POLICY_V1,
};
pub use parameter_catalog_v1::{
    validate_candidate_set_v1, AmiUsageV1, CatalogEntryV1, CatalogErrorV1, ParameterCatalogV1,
    PARAMETER_CATALOG_POLICY_V1,
};
pub use parameter_form_binding_v1::{
    bind_parameter_value_v1, ParameterFormBindingErrorV1, ParameterFormBindingV1,
    PARAMETER_FORM_BINDING_POLICY_V1,
};
pub use parameter_value_v1::{
    AmiParameterTypeV1, AmiParameterValueErrorV1, AmiParameterValueV1,
    PARAMETER_VALUE_POLICY_V1,
};

use std::{error::Error, fmt, num::NonZeroUsize};

/// A byte and physical source location in an input document.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SourceSpanV1 {
    byte_start: usize,
    byte_end: usize,
    line: usize,
    column_start: usize,
}

impl SourceSpanV1 {
    const fn new(byte_start: usize, byte_end: usize, line: usize, column_start: usize) -> Self {
        Self {
            byte_start,
            byte_end,
            line,
            column_start,
        }
    }

    pub const fn byte_start(self) -> usize {
        self.byte_start
    }

    pub const fn byte_end(self) -> usize {
        self.byte_end
    }

    pub const fn line(self) -> usize {
        self.line
    }

    pub const fn column_start(self) -> usize {
        self.column_start
    }
}

/// Original token spelling and its byte-based source span.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextTokenV1 {
    spelling: String,
    span: SourceSpanV1,
}

impl AmiTextTokenV1 {
    pub fn spelling(&self) -> &str {
        &self.spelling
    }

    pub const fn span(&self) -> SourceSpanV1 {
        self.span
    }
}

/// One balanced list in the structural document.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextListV1 {
    open_span: SourceSpanV1,
    close_span: SourceSpanV1,
    items: Vec<AmiTextNodeV1>,
}

impl AmiTextListV1 {
    pub const fn open_span(&self) -> SourceSpanV1 {
        self.open_span
    }

    pub const fn close_span(&self) -> SourceSpanV1 {
        self.close_span
    }

    pub fn items(&self) -> &[AmiTextNodeV1] {
        &self.items
    }
}

/// A structural node. Quoted spelling includes its surrounding quotes and any
/// escape characters; this layer deliberately does not decode it.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiTextNodeV1 {
    List(AmiTextListV1),
    Atom(AmiTextTokenV1),
    Quoted(AmiTextTokenV1),
}

/// A complete successful parse. It contains no semantic validation result.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextDocumentV1 {
    forms: Vec<AmiTextListV1>,
}

/// Caller-provided AMI text retained byte-for-byte after a successful parse.
/// It has no path, origin, model, DLL, or semantic metadata.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RawAmiTextV1 {
    bytes: Vec<u8>,
}

impl RawAmiTextV1 {
    pub fn bytes(&self) -> &[u8] {
        &self.bytes
    }

    pub const fn byte_len(&self) -> usize {
        self.bytes.len()
    }
}

/// Exact in-memory association of retained raw bytes and their structural AST.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmiTextBindingV1 {
    raw: RawAmiTextV1,
    document: AmiTextDocumentV1,
}

impl AmiTextBindingV1 {
    pub fn raw(&self) -> &RawAmiTextV1 {
        &self.raw
    }

    pub fn document(&self) -> &AmiTextDocumentV1 {
        &self.document
    }
}

impl AmiTextDocumentV1 {
    pub fn forms(&self) -> &[AmiTextListV1] {
        &self.forms
    }
}

/// Explicit limits for one parse operation.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ParseLimitsV1 {
    max_input_bytes: NonZeroUsize,
    max_nesting_depth: NonZeroUsize,
    max_nodes: NonZeroUsize,
    max_token_bytes: NonZeroUsize,
}

impl ParseLimitsV1 {
    pub fn try_new(
        max_input_bytes: usize,
        max_nesting_depth: usize,
        max_nodes: usize,
        max_token_bytes: usize,
    ) -> Result<Self, LimitErrorV1> {
        Ok(Self {
            max_input_bytes: NonZeroUsize::new(max_input_bytes).ok_or(LimitErrorV1::Zero)?,
            max_nesting_depth: NonZeroUsize::new(max_nesting_depth).ok_or(LimitErrorV1::Zero)?,
            max_nodes: NonZeroUsize::new(max_nodes).ok_or(LimitErrorV1::Zero)?,
            max_token_bytes: NonZeroUsize::new(max_token_bytes).ok_or(LimitErrorV1::Zero)?,
        })
    }

    pub const fn max_input_bytes(self) -> NonZeroUsize {
        self.max_input_bytes
    }

    pub const fn max_nesting_depth(self) -> NonZeroUsize {
        self.max_nesting_depth
    }

    pub const fn max_nodes(self) -> NonZeroUsize {
        self.max_nodes
    }

    pub const fn max_token_bytes(self) -> NonZeroUsize {
        self.max_token_bytes
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LimitErrorV1 {
    Zero,
}

impl fmt::Display for LimitErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "AMI text parse limits must be nonzero")
    }
}

impl Error for LimitErrorV1 {}

/// Stable fail-closed structural parse diagnostics.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiTextDiagnosticCodeV1 {
    InputLimitExceeded,
    InvalidUtf8,
    NulByte,
    ForbiddenControlCharacter,
    BareCarriageReturn,
    NestingLimitExceeded,
    NodeLimitExceeded,
    TokenLimitExceeded,
    UnexpectedClosingParenthesis,
    TopLevelAtom,
    UnclosedList,
    UnterminatedQuotedText,
}

/// A stable diagnostic with bounded source context.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct AmiTextDiagnosticV1 {
    code: AmiTextDiagnosticCodeV1,
    span: SourceSpanV1,
}

impl AmiTextDiagnosticV1 {
    pub const fn code(self) -> AmiTextDiagnosticCodeV1 {
        self.code
    }

    pub const fn span(self) -> SourceSpanV1 {
        self.span
    }
}

impl fmt::Display for AmiTextDiagnosticV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "AMI text structural parse {:?} at line {}, column {}",
            self.code, self.span.line, self.span.column_start
        )
    }
}

impl Error for AmiTextDiagnosticV1 {}

/// Fail-closed errors for an exact raw-text binding check.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AmiTextBindingErrorV1 {
    Parse(AmiTextDiagnosticV1),
    RawBytesMismatch,
    StructuralIdentityMismatch,
}

impl fmt::Display for AmiTextBindingErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Parse(error) => write!(formatter, "raw AMI text binding parse error: {error}"),
            Self::RawBytesMismatch => write!(formatter, "raw AMI text bytes do not match binding"),
            Self::StructuralIdentityMismatch => {
                write!(
                    formatter,
                    "raw AMI text structural identity does not match binding"
                )
            }
        }
    }
}

impl Error for AmiTextBindingErrorV1 {}

/// Semantic validation is intentionally unavailable in this structural layer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiTextSemanticStatusV1 {
    RulesUnavailable,
}

pub const fn semantic_validation_status_v1() -> AmiTextSemanticStatusV1 {
    AmiTextSemanticStatusV1::RulesUnavailable
}

/// Parses bounded UTF-8 parenthesized forms without AMI parameter semantics.
pub fn parse_ami_text_v1(
    bytes: &[u8],
    limits: ParseLimitsV1,
) -> Result<AmiTextDocumentV1, AmiTextDiagnosticV1> {
    if bytes.len() > limits.max_input_bytes.get() {
        return Err(diagnostic(
            AmiTextDiagnosticCodeV1::InputLimitExceeded,
            0,
            0,
            1,
            1,
        ));
    }
    let source = std::str::from_utf8(bytes).map_err(|error| {
        diagnostic(
            AmiTextDiagnosticCodeV1::InvalidUtf8,
            error.valid_up_to(),
            error.valid_up_to(),
            1,
            1,
        )
    })?;
    validate_characters(source)?;

    let mut parser = Parser {
        source,
        limits,
        offset: 0,
        line: 1,
        column: 1,
        nodes: 0,
    };
    let mut forms = Vec::new();
    parser.skip_ignorable()?;
    while !parser.at_end() {
        if parser.peek_char() == Some(')') {
            return Err(
                parser.current_diagnostic(AmiTextDiagnosticCodeV1::UnexpectedClosingParenthesis, 1)
            );
        }
        if parser.peek_char() != Some('(') {
            return Err(parser.current_diagnostic(AmiTextDiagnosticCodeV1::TopLevelAtom, 1));
        }
        forms.push(parser.parse_list(1)?);
        parser.skip_ignorable()?;
    }
    Ok(AmiTextDocumentV1 { forms })
}

/// Parses and retains exactly one caller-provided raw AMI text byte sequence.
/// No newline, Unicode, case, or token-spelling normalization is performed.
pub fn parse_and_bind_v1(
    bytes: &[u8],
    limits: ParseLimitsV1,
) -> Result<AmiTextBindingV1, AmiTextDiagnosticV1> {
    let document = parse_ami_text_v1(bytes, limits)?;
    Ok(AmiTextBindingV1 {
        raw: RawAmiTextV1 {
            bytes: bytes.to_vec(),
        },
        document,
    })
}

/// Verifies that supplied bytes exactly match a binding and reconstruct the
/// same structural document under explicit limits.
pub fn verify_binding_v1(
    bytes: &[u8],
    binding: &AmiTextBindingV1,
    limits: ParseLimitsV1,
) -> Result<(), AmiTextBindingErrorV1> {
    if bytes != binding.raw.bytes() {
        return Err(AmiTextBindingErrorV1::RawBytesMismatch);
    }
    let document = parse_ami_text_v1(bytes, limits).map_err(AmiTextBindingErrorV1::Parse)?;
    if document != binding.document {
        return Err(AmiTextBindingErrorV1::StructuralIdentityMismatch);
    }
    Ok(())
}

struct Parser<'a> {
    source: &'a str,
    limits: ParseLimitsV1,
    offset: usize,
    line: usize,
    column: usize,
    nodes: usize,
}

impl Parser<'_> {
    fn parse_list(&mut self, depth: usize) -> Result<AmiTextListV1, AmiTextDiagnosticV1> {
        if depth > self.limits.max_nesting_depth.get() {
            return Err(self.current_diagnostic(AmiTextDiagnosticCodeV1::NestingLimitExceeded, 0));
        }
        let open_span = self.current_span(1);
        self.consume_char();
        self.take_node()?;
        let mut items = Vec::new();
        loop {
            self.skip_ignorable()?;
            if self.at_end() {
                return Err(diagnostic(
                    AmiTextDiagnosticCodeV1::UnclosedList,
                    open_span.byte_start,
                    open_span.byte_end,
                    open_span.line,
                    open_span.column_start,
                ));
            }
            match self.peek_char() {
                Some(')') => {
                    let close_span = self.current_span(1);
                    self.consume_char();
                    return Ok(AmiTextListV1 {
                        open_span,
                        close_span,
                        items,
                    });
                }
                Some('(') => items.push(AmiTextNodeV1::List(self.parse_list(depth + 1)?)),
                Some('"') => items.push(AmiTextNodeV1::Quoted(self.parse_quoted()?)),
                Some(_) => items.push(AmiTextNodeV1::Atom(self.parse_atom()?)),
                None => unreachable!("at_end is checked above"),
            }
        }
    }

    fn parse_atom(&mut self) -> Result<AmiTextTokenV1, AmiTextDiagnosticV1> {
        self.take_node()?;
        let start = self.offset;
        let line = self.line;
        let column = self.column;
        while let Some(character) = self.peek_char() {
            if character.is_whitespace() || matches!(character, '(' | ')' | '"' | '|') {
                break;
            }
            self.consume_char();
        }
        self.token_from(start, line, column)
    }

    fn parse_quoted(&mut self) -> Result<AmiTextTokenV1, AmiTextDiagnosticV1> {
        self.take_node()?;
        let start = self.offset;
        let line = self.line;
        let column = self.column;
        self.consume_char();
        loop {
            let Some(character) = self.peek_char() else {
                return Err(diagnostic(
                    AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
                    start,
                    self.offset,
                    line,
                    column,
                ));
            };
            if matches!(character, '\n' | '\r') {
                return Err(diagnostic(
                    AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
                    start,
                    self.offset,
                    line,
                    column,
                ));
            }
            self.consume_char();
            if character == '\\' {
                if self.at_end() || matches!(self.peek_char(), Some('\n' | '\r')) {
                    return Err(diagnostic(
                        AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
                        start,
                        self.offset,
                        line,
                        column,
                    ));
                }
                self.consume_char();
            } else if character == '"' {
                return self.token_from(start, line, column);
            }
        }
    }

    fn token_from(
        &self,
        start: usize,
        line: usize,
        column: usize,
    ) -> Result<AmiTextTokenV1, AmiTextDiagnosticV1> {
        let length = self.offset - start;
        if length > self.limits.max_token_bytes.get() {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::TokenLimitExceeded,
                start,
                self.offset,
                line,
                column,
            ));
        }
        Ok(AmiTextTokenV1 {
            spelling: self.source[start..self.offset].to_owned(),
            span: SourceSpanV1::new(start, self.offset, line, column),
        })
    }

    fn take_node(&mut self) -> Result<(), AmiTextDiagnosticV1> {
        self.nodes = self.nodes.checked_add(1).ok_or_else(|| {
            self.current_diagnostic(AmiTextDiagnosticCodeV1::NodeLimitExceeded, 0)
        })?;
        if self.nodes > self.limits.max_nodes.get() {
            return Err(self.current_diagnostic(AmiTextDiagnosticCodeV1::NodeLimitExceeded, 0));
        }
        Ok(())
    }

    fn skip_ignorable(&mut self) -> Result<(), AmiTextDiagnosticV1> {
        loop {
            match self.peek_char() {
                Some(' ' | '\t' | '\n') => self.consume_char(),
                Some('\r') => {
                    if self.source.as_bytes().get(self.offset + 1) != Some(&b'\n') {
                        return Err(
                            self.current_diagnostic(AmiTextDiagnosticCodeV1::BareCarriageReturn, 1)
                        );
                    }
                    self.offset += 2;
                    self.line += 1;
                    self.column = 1;
                }
                Some('|') => {
                    while let Some(character) = self.peek_char() {
                        if matches!(character, '\n' | '\r') {
                            break;
                        }
                        self.consume_char();
                    }
                }
                _ => return Ok(()),
            }
        }
    }

    fn at_end(&self) -> bool {
        self.offset == self.source.len()
    }

    fn peek_char(&self) -> Option<char> {
        self.source[self.offset..].chars().next()
    }

    fn consume_char(&mut self) {
        let character = self.peek_char().expect("consume only within source");
        self.offset += character.len_utf8();
        if character == '\n' {
            self.line += 1;
            self.column = 1;
        } else {
            self.column += 1;
        }
    }

    fn current_span(&self, byte_length: usize) -> SourceSpanV1 {
        SourceSpanV1::new(
            self.offset,
            self.offset.saturating_add(byte_length),
            self.line,
            self.column,
        )
    }

    fn current_diagnostic(
        &self,
        code: AmiTextDiagnosticCodeV1,
        byte_length: usize,
    ) -> AmiTextDiagnosticV1 {
        AmiTextDiagnosticV1 {
            code,
            span: self.current_span(byte_length),
        }
    }
}

fn validate_characters(source: &str) -> Result<(), AmiTextDiagnosticV1> {
    let mut line = 1;
    let mut column = 1;
    let mut previous_was_cr = false;
    for (offset, character) in source.char_indices() {
        if character == '\0' {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::NulByte,
                offset,
                offset + 1,
                line,
                column,
            ));
        }
        if character == '\r' {
            previous_was_cr = true;
            continue;
        }
        if previous_was_cr && character != '\n' {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::BareCarriageReturn,
                offset - 1,
                offset,
                line,
                column,
            ));
        }
        previous_was_cr = false;
        if character.is_control() && !matches!(character, '\t' | '\n') {
            return Err(diagnostic(
                AmiTextDiagnosticCodeV1::ForbiddenControlCharacter,
                offset,
                offset + character.len_utf8(),
                line,
                column,
            ));
        }
        if character == '\n' {
            line += 1;
            column = 1;
        } else {
            column += 1;
        }
    }
    if previous_was_cr {
        return Err(diagnostic(
            AmiTextDiagnosticCodeV1::BareCarriageReturn,
            source.len() - 1,
            source.len(),
            line,
            column,
        ));
    }
    Ok(())
}

const fn diagnostic(
    code: AmiTextDiagnosticCodeV1,
    byte_start: usize,
    byte_end: usize,
    line: usize,
    column_start: usize,
) -> AmiTextDiagnosticV1 {
    AmiTextDiagnosticV1 {
        code,
        span: SourceSpanV1::new(byte_start, byte_end, line, column_start),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> ParseLimitsV1 {
        ParseLimitsV1::try_new(512, 8, 32, 64).expect("limits")
    }

    #[test]
    fn retains_order_spelling_comments_and_spans() {
        let document = parse_ami_text_v1(
            b"| comment\r\n(root alpha (nested \"two words\"))\n(next)",
            limits(),
        )
        .expect("parse");
        assert_eq!(document.forms().len(), 2);
        assert_eq!(document.forms()[0].open_span().line(), 2);
        assert_eq!(document.forms()[0].items().len(), 3);
        let AmiTextNodeV1::Atom(atom) = &document.forms()[0].items()[0] else {
            panic!("atom");
        };
        assert_eq!(atom.spelling(), "root");
        let AmiTextNodeV1::List(nested) = &document.forms()[0].items()[2] else {
            panic!("nested list");
        };
        let AmiTextNodeV1::Quoted(quoted) = &nested.items()[1] else {
            panic!("quoted");
        };
        assert_eq!(quoted.spelling(), "\"two words\"");
    }

    #[test]
    fn rejects_invalid_encoding_structure_and_limits_without_a_partial_document() {
        let cases = [
            (b"(x\0)".as_slice(), AmiTextDiagnosticCodeV1::NulByte),
            (b"(\x80)".as_slice(), AmiTextDiagnosticCodeV1::InvalidUtf8),
            (
                b"(x\r)".as_slice(),
                AmiTextDiagnosticCodeV1::BareCarriageReturn,
            ),
            (b"x".as_slice(), AmiTextDiagnosticCodeV1::TopLevelAtom),
            (
                b")".as_slice(),
                AmiTextDiagnosticCodeV1::UnexpectedClosingParenthesis,
            ),
            (b"(x".as_slice(), AmiTextDiagnosticCodeV1::UnclosedList),
            (
                b"(\"x)".as_slice(),
                AmiTextDiagnosticCodeV1::UnterminatedQuotedText,
            ),
        ];
        for (source, expected) in cases {
            assert_eq!(
                parse_ami_text_v1(source, limits())
                    .expect_err("reject")
                    .code(),
                expected
            );
        }
        let token_limited = ParseLimitsV1::try_new(64, 4, 8, 2).expect("limits");
        assert_eq!(
            parse_ami_text_v1(b"(abc)", token_limited)
                .expect_err("token limit")
                .code(),
            AmiTextDiagnosticCodeV1::TokenLimitExceeded
        );
        let depth_limited = ParseLimitsV1::try_new(64, 1, 8, 8).expect("limits");
        assert_eq!(
            parse_ami_text_v1(b"((x))", depth_limited)
                .expect_err("depth limit")
                .code(),
            AmiTextDiagnosticCodeV1::NestingLimitExceeded
        );
        let node_limited = ParseLimitsV1::try_new(64, 4, 2, 8).expect("limits");
        assert_eq!(
            parse_ami_text_v1(b"(a b)", node_limited)
                .expect_err("node limit")
                .code(),
            AmiTextDiagnosticCodeV1::NodeLimitExceeded
        );
    }

    #[test]
    fn treats_semantics_as_unavailable_and_is_deterministic() {
        let source = b"(future_key value)";
        let first = parse_ami_text_v1(source, limits()).expect("first");
        let second = parse_ami_text_v1(source, limits()).expect("second");
        assert_eq!(first, second);
        assert_eq!(
            semantic_validation_status_v1(),
            AmiTextSemanticStatusV1::RulesUnavailable
        );
        assert_eq!(ParseLimitsV1::try_new(0, 1, 1, 1), Err(LimitErrorV1::Zero));
    }

    #[test]
    fn binds_exact_raw_bytes_without_normalizing_or_accepting_drift() {
        let source = b"(key \"A\\\\B\"\r\n  value)";
        let binding = parse_and_bind_v1(source, limits()).expect("binding");
        assert_eq!(binding.raw().bytes(), source);
        assert_eq!(binding.raw().byte_len(), source.len());
        verify_binding_v1(source, &binding, limits()).expect("exact binding");
        assert_eq!(
            verify_binding_v1(b"(key \"A\\\\B\"\n  value)", &binding, limits()),
            Err(AmiTextBindingErrorV1::RawBytesMismatch)
        );
        let forged = AmiTextBindingV1 {
            raw: binding.raw.clone(),
            document: parse_ami_text_v1(b"(other)", limits()).expect("other document"),
        };
        assert_eq!(
            verify_binding_v1(source, &forged, limits()),
            Err(AmiTextBindingErrorV1::StructuralIdentityMismatch)
        );
    }
}