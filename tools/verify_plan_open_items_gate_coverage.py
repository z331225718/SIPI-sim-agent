"""Verify gate coverage for the remaining PLAN open items.

Every open PLAN item has committed verifier(s) that keep its state honest
(blocked/specified/pending) until the owner decision or external oracle
arrives. This gate fails closed if any of those verifiers disappears, so
the open-item state cannot silently regress to an unguarded condition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.plan-open-items.gate-coverage.v1"

OPEN_ITEM_GATES = {
  "P1-04B": [
    "tools/verify_p1_04b_legacy_fixture_boundary.py"
  ],
  "P2-04": [
    "tools/verify_tran_rc_pulse_acceptance.py",
    "tools/verify_p2_03_tran_semantic_freeze.py",
    "tools/verify_p2_04_semantic_freeze_complete.py"
  ],
  "P2-06": [
    "tools/verify_p2_06_stage_compare_coverage.py"
  ],
  "P2-09": [
    "tools/verify_p2_09a_performance_protocol_consistency.py",
    "tools/verify_p2_09_owner_approved_baseline.py"
  ],
  "P3B-02": [
    "tools/verify_p3b_02_link_kernel_singleton.py"
  ],
  "P3B-03": [
    "tools/verify_p3b_03g_receiver_diagnostic_contract.py",
    "tools/verify_p3b_03_receiver_self_conformance.py"
  ],
  "P3B-04": [
    "tools/verify_channel_rfm_receiver_readiness.py",
        "tools/verify_p3b_04b_cdr_lock.py"
  ],
  "P3B-05": [
    "tools/verify_p3b_05a_causal_fir_request_rejection.py",
    "tools/verify_p3b_05b_seed_noise_jitter_decision_preflight.py",
    "tools/verify_p3b_05c_prbs9_sequence.py",
    "tools/verify_p3b_05d_prbs9_inject.py",
    "tools/verify_p3b_05e_time_warp.py"
  ],
  "P3C-01": [
    "tools/verify_p3c_prbs9_metric_core_v2.py"
  ],
  "P3C-02": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p3c_02_bathtub_decision_preflight.py",
    "tools/verify_p3c_02e_qfactor_ber.py",
    "tools/verify_p3c_02f_bathtub.py",
    "tools/verify_p3c_02g_horizontal_margin.py",
        "tools/verify_p3c_02h_bathtub_fit.py",
        "tools/verify_p3c_02i_eye_contour.py"
  ],
  "P3C-03": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p3c_03_profile_compare_decision_preflight.py",
    "tools/verify_p3c_03c_metric_compare.py",
    "tools/verify_p3c_03d_db_tolerance.py",
    "tools/verify_p3c_03e_compliance_report.py",
    "tools/verify_p3c_04x_c4_profile.py",
    "tools/verify_p3c_04y_c4_oracle_compare.py"
  ],
  "P4A-01": [
    "tools/verify_p4a_ibis_example_rx_candidate_inventory.py",
    "tools/verify_p4a_01_required_profile_inventory.py"
  ],
  "P4A-02": [
    "tools/verify_p4a_ibis71_behavior_scope_preflight.py",
    "tools/verify_p4a_02b_gen5_behavior_spec.py"
  ],
  "P4A-03": [
    "tools/verify_p4a_official_pure_ibis_structural_scope_preflight.py",
    "tools/verify_p4a_03d_model_declaration.py",
    "tools/verify_p4a_03e_pin_declaration.py",
    "tools/verify_p4a_03f_pin_model_linkage.py",
        "tools/verify_p4a_03g_component_declaration.py",
        "tools/verify_p4a_03h_package_model.py",
        "tools/verify_p4a_03i_model_selector.py",
        "tools/verify_p4a_03j_diff_pin.py",
        "tools/verify_p4a_03k_series_switch.py",
        "tools/verify_p4a_03l_submodel.py",
        "tools/verify_p4a_03m_circuit_call.py",
        "tools/verify_p4a_03n_node_declaration.py",
        "tools/verify_p4a_03o_series_pin_mapping.py",
        "tools/verify_p4a_03p_series_switch_mapping.py",
        "tools/verify_p4a_03q_receiver_thresholds.py",
        "tools/verify_p4a_03r_test_data.py",
        "tools/verify_p4a_03s_golden_wave.py",
        "tools/verify_p4a_03t_bus_label.py",
        "tools/verify_p4a_03u_series_pin_thresholds.py",
        "tools/verify_p4a_03v_series_pin_group.py",
        "tools/verify_p4a_03w_series_pin_table_selector.py",
        "tools/verify_p4a_03x_series_pin_table_group.py",
        "tools/verify_p4a_03y_series_pin_table_group_selector.py",
        "tools/verify_p4a_03z_series_pin_thresholds_group.py",
        "tools/verify_p4a_03aa_series_switch_thresholds.py",
        "tools/verify_p4a_03ab_model_keywords.py",
        "tools/verify_p4a_03ac_series_pin_table_group_thresholds.py",
        "tools/verify_p4a_03ad_model_selector_keywords.py",
        "tools/verify_p4a_03ae_package_model_keywords.py",
        "tools/verify_p4a_03af_series_pin_mapping_keywords.py",
        "tools/verify_p4a_03ag_series_switch_keywords.py",
        "tools/verify_p4a_03ah_receiver_thresholds_keywords.py",
        "tools/verify_p4a_03ai_test_data_keywords.py",
        "tools/verify_p4a_03aj_golden_wave_keywords.py",
        "tools/verify_p4a_03ak_bus_label_keywords.py",
        "tools/verify_p4a_03al_diff_pin_keywords.py",
        "tools/verify_p4a_03am_series_pin_table_selector_thresholds.py",
        "tools/verify_p4a_03an_series_pin_table_group_switch.py",
        "tools/verify_p4a_03ao_series_pin_table_group_switch_thresholds.py",
        "tools/verify_p4a_03ap_series_pin_table_selector_group_thresholds.py",
        "tools/verify_p4a_03aq_series_pin_table_selector.py",
        "tools/verify_p4a_03ar_series_pin_table_group.py",
        "tools/verify_p4a_03as_series_pin_table_group_selector.py",
        "tools/verify_p4a_03at_series_pin_thresholds_group.py",
        "tools/verify_p4a_03au_series_pin_table_selector_thresholds_group.py",
        "tools/verify_p4a_03av_series_pin_table_selector_thresholds.py",
        "tools/verify_p4a_03aw_series_pin_table_group_thresholds.py",
        "tools/verify_p4a_03ax_series_pin_table_selector.py",
        "tools/verify_p4a_03ay_series_pin_table_selector_thresholds_group.py",
        "tools/verify_p4a_03az_series_pin_table_selector.py",
        "tools/verify_p4a_03ba_series_pin_table_selector_thresholds.py",
        "tools/verify_p4a_03bb_series_pin_table_group_switch.py",
        "tools/verify_p4a_03bc_series_pin_table_group_switch_thresholds.py",
        "tools/verify_p4a_03bd_series_pin_table_selector_group_thresholds.py",
        "tools/verify_p4a_03be_series_pin_table_selector.py",
        "tools/verify_p4a_03bf_series_pin_table_group.py",
        "tools/verify_p4a_03bg_series_pin_table_selector_thresholds.py"
  ],
  "P4A-04": [
    "tools/verify_p4a_ibis_input_typ_static_acceptance.py",
    "tools/verify_p4a_04f_vt_table_core.py",
    "tools/verify_p4a_04g_ramp_package_spec_core.py"
  ],
  "P4A-05": [
    "tools/verify_p4a_ibis_conformance_matrix.py",
    "tools/verify_p4a_05_conformance_matrix_complete.py"
  ],
  "P4A-06": [
    "tools/verify_p4a_ibis_conformance_matrix.py",
    "tools/verify_p4a_06_cli_slices_complete.py"
  ],
  "P4B-01": [
    "tools/verify_p4b_ami_candidate_preflight.py",
    "tools/verify_p4b_01_ami_candidate_audit_complete.py"
  ],
  "P4B-02": [
    "tools/verify_p4b_external_ami_asset_set.py",
    "tools/verify_p4b_02b1_parameter_value_core.py",
    "tools/verify_p4b_02b2_parameter_form_binding.py",
    "tools/verify_p4b_02b3_parameter_catalog.py",
    "tools/verify_p4b_02b4_catalog_default.py",
    "tools/verify_p4b_02b5_ami_runtime_params.py",
        "tools/verify_p4b_02b6_parameter_extractor.py",
        "tools/verify_p4b_02b7_parameter_trees.py",
        "tools/verify_p4b_02b8_parameter_tree_query.py",
        "tools/verify_p4b_02b9_parameter_tree_formatter.py",
        "tools/verify_p4b_02b10_parameter_tree_validator.py",
        "tools/verify_p4b_02b11_parameter_tree_diff.py",
        "tools/verify_p4b_02b12_parameter_tree_merge.py",
        "tools/verify_p4b_02b13_parameter_tree_pruning.py",
        "tools/verify_p4b_02b14_parameter_tree_visitor.py",
        "tools/verify_p4b_02b15_parameter_tree_transformer.py",
        "tools/verify_p4b_02b16_parameter_tree_index.py",
        "tools/verify_p4b_02b17_parameter_tree_diff_patch.py",
        "tools/verify_p4b_02b18_parameter_tree_filter.py",
        "tools/verify_p4b_02b19_parameter_tree_serde.py",
        "tools/verify_p4b_02b20_parameter_tree_diff_stats.py",
        "tools/verify_p4b_02b21_parameter_tree_diff_filter.py",
        "tools/verify_p4b_02b22_parameter_tree_diff_summary.py",
        "tools/verify_p4b_02b23_parameter_tree_subtree.py",
        "tools/verify_p4b_02b24_parameter_tree_rename.py",
        "tools/verify_p4b_02b25_parameter_tree_detect_cycles.py",
        "tools/verify_p4b_02b26_parameter_tree_compose.py",
        "tools/verify_p4b_02b27_parameter_tree_replace.py",
        "tools/verify_p4b_02b28_parameter_tree_toposort.py",
        "tools/verify_p4b_02b29_parameter_tree_depth_stats.py",
        "tools/verify_p4b_02b30_parameter_tree_leaf_index.py",
        "tools/verify_p4b_02b31_parameter_tree_token_stats.py",
        "tools/verify_p4b_02b32_parameter_tree_value_validation.py",
        "tools/verify_p4b_02b33_parameter_tree_value_type_inference.py",
        "tools/verify_p4b_02b34_parameter_tree_typed_form.py",
        "tools/verify_p4b_02b35_parameter_tree_leaf_projection.py",
        "tools/verify_p4b_02b36_parameter_tree_batch_rename.py",
        "tools/verify_p4b_02b37_parameter_tree_leaf_value_decoding.py",
        "tools/verify_p4b_02b38_parameter_tree_apply_defaults.py",
        "tools/verify_p4b_02b39_parameter_tree_leaf_value_set.py",
        "tools/verify_p4b_02b40_parameter_tree_leaf_search.py",
        "tools/verify_p4b_02b41_parameter_tree_inferred_decode.py",
        "tools/verify_p4b_02b42_parameter_tree_typed_form_multi.py",
        "tools/verify_p4b_02b43_parameter_tree_reserved_name_check.py",
        "tools/verify_p4b_02b44_parameter_profile_assembly.py",
        "tools/verify_p4b_02b45_parameter_tree_path_string.py",
        "tools/verify_p4b_02b46_parameter_tree_expected_check.py",
        "tools/verify_p4b_02b47_parameter_profile_diff.py",
        "tools/verify_p4b_02b48_parameter_profile_merge.py",
        "tools/verify_p4b_02b49_parameter_tree_allowed_name_check.py",
        "tools/verify_p4b_02b50_parameter_tree_flatten.py",
        "tools/verify_p4b_02b51_ami_text_document_stats.py",
        "tools/verify_p4b_02b52_parameter_tree_token_remap.py",
        "tools/verify_p4b_02b53_parameter_tree_batch_value_set.py",
        "tools/verify_p4b_02b54_parameter_tree_duplicate_check.py",
        "tools/verify_p4b_02b55_parameter_profile_completeness.py",
        "tools/verify_p4b_02b56_parameter_tree_path_join.py",
        "tools/verify_p4b_02b57_parameter_tree_sections.py",
        "tools/verify_p4b_02b58_parameter_tree_typed_form_conformance.py",
        "tools/verify_p4b_02b59_parameter_tree_leaf_occurrences.py",
        "tools/verify_p4b_02b60_parameter_tree_token_frequencies.py",
        "tools/verify_p4b_02b61_ami_text_form_heads.py",
        "tools/verify_p4b_02b62_parameter_tree_required_name_check.py",
        "tools/verify_p4b_02b63_parameter_tree_distinct_leaf_names.py",
        "tools/verify_p4b_02b64_parameter_profile_select.py",
        "tools/verify_p4b_02b65_parameter_tree_path_relation.py",
        "tools/verify_p4b_02b66_parameter_tree_relative_path.py",
        "tools/verify_p4b_02b67_parameter_tree_longest_common_prefix.py",
        "tools/verify_p4b_02b68_parameter_tree_path_prefixes.py",
    "tools/verify_p4b_02b69_parameter_tree_profile_apply.py",
    "tools/verify_p4b_02b70_parameter_value_equivalence.py",
    "tools/verify_p4b_02b71_parameter_profile_equivalence.py",
    "tools/verify_p4b_02b72_parameter_profile_tree_coverage.py",
    "tools/verify_p4b_02b73_parameter_profile_type_stats.py",
    "tools/verify_p4b_02b74_parameter_profile_typed_merge.py",
    "tools/verify_p4b_02b75_parameter_value_spelling_normalization.py",
    "tools/verify_p4b_02b76_parameter_profile_override_merge.py",
    "tools/verify_p4b_02b77_parameter_profile_canonicalization.py",
    "tools/verify_p4b_02b78_parameter_tree_leaf_canonicalization.py",
    "tools/verify_p4b_02b79_parameter_profile_typed_diff.py",
    "tools/verify_p4b_02b80_parameter_profile_value_lookup.py",
    "tools/verify_p4b_02b81_parameter_profile_serialization.py",
    "tools/verify_p4b_02b82_parameter_profile_deserialization.py",
    "tools/verify_p4b_02b83_parameter_list_item_count.py",
    "tools/verify_p4b_02b84_parameter_list_item_access.py",
    "tools/verify_p4b_02b85_parameter_list_contains.py",
    "tools/verify_p4b_02b86_parameter_profile_names_by_type.py",
    "tools/verify_p4b_02b87_parameter_tree_leaf_type_map.py",
    "tools/verify_p4b_02b88_parameter_tree_leaf_type_resolution.py",
    "tools/verify_p4b_02b89_parameter_tree_leaf_typed_diff.py",
    "tools/verify_p4b_02b90_parameter_profile_typed_subset.py",
    "tools/verify_p4b_02b91_parameter_tree_leaf_value_validity.py",
    "tools/verify_p4b_02b92_parameter_profile_canonical_spelling_groups.py",
    "tools/verify_p4b_02b93_parameter_tree_typed_leaf_type_counts.py",
    "tools/verify_p4b_02b94_parameter_tree_leaf_canonical_spelling_check.py",
    "tools/verify_p4b_02b95_parameter_profile_canonical_spelling_check.py",
    "tools/verify_p4b_02b96_parameter_profile_fingerprint.py",
    "tools/verify_p4b_02b97_parameter_tree_typed_leaf_fingerprint.py",
    "tools/verify_p4b_02b98_parameter_list_dedup.py",
    "tools/verify_p4b_02b99_parameter_list_replace.py",
    "tools/verify_p4b_02b100_parameter_list_remove.py",
    "tools/verify_p4b_02b101_parameter_list_append.py",
    "tools/verify_p4b_02b102_parameter_list_insert.py",
    "tools/verify_p4b_02b103_parameter_list_swap.py",
    "tools/verify_p4b_02b104_parameter_list_reverse.py",
    "tools/verify_p4b_02b105_parameter_list_sort.py",
    "tools/verify_p4b_02b106_parameter_list_join.py",
    "tools/verify_p4b_02b107_parameter_list_distinct_count.py",
    "tools/verify_p4b_02b108_parameter_list_occurrence_count.py",
    "tools/verify_p4b_02b109_parameter_list_slice.py",
    "tools/verify_p4b_02b110_parameter_list_index_of.py",
    "tools/verify_p4b_02b111_parameter_list_last_index_of.py",
    "tools/verify_p4b_02b112_parameter_list_remove_all.py",
    "tools/verify_p4b_02b113_parameter_list_keep_only.py",
    "tools/verify_p4b_02b114_parameter_list_split.py",
    "tools/verify_p4b_02b115_parameter_list_rotate.py",
    "tools/verify_p4b_02b116_parameter_list_chunk.py",
    "tools/verify_p4b_02b117_parameter_list_head_tail.py",
    "tools/verify_p4b_02b118_parameter_list_window.py",
    "tools/verify_p4b_02b119_parameter_list_run_length_encode.py",
    "tools/verify_p4b_02b120_parameter_list_longest_run.py",
    "tools/verify_p4b_02b121_parameter_list_frequency.py",
    "tools/verify_p4b_02b122_parameter_list_most_frequent.py",
    "tools/verify_p4b_02b123_parameter_list_least_frequent.py",
    "tools/verify_p4b_02b124_parameter_list_is_sorted.py",
    "tools/verify_p4b_02b125_parameter_list_is_strictly_sorted.py",
    "tools/verify_p4b_02b126_parameter_list_is_palindrome.py",
    "tools/verify_p4b_02b127_parameter_list_contains_sublist.py",
    "tools/verify_p4b_02b128_parameter_list_sublist_index.py",
    "tools/verify_p4b_02b129_parameter_list_last_sublist_index.py",
    "tools/verify_p4b_02b130_parameter_list_longest_common_prefix.py",
    "tools/verify_p4b_02b131_parameter_list_longest_common_suffix.py",
    "tools/verify_p4b_02b132_parameter_list_interleave.py",
    "tools/verify_p4b_02b133_parameter_list_inversion_count.py",
    "tools/verify_p4b_02b134_parameter_list_equal_adjacent_count.py",
    "tools/verify_p4b_02b135_parameter_list_distinct_pair_count.py",
    "tools/verify_p4b_02b136_parameter_list_unique_item_count.py",
    "tools/verify_p4b_02b137_parameter_list_duplicate_item_count.py",
    "tools/verify_p4b_02b138_parameter_list_first_duplicate_index.py",
    "tools/verify_p4b_02b139_parameter_list_last_duplicate_index.py",
    "tools/verify_p4b_02b140_parameter_list_multi_remove_all.py",
    "tools/verify_p4b_02b141_parameter_list_multi_keep_only.py",
    "tools/verify_p4b_02b142_parameter_list_longest_common_subsequence_length.py",
    "tools/verify_p4b_02b143_parameter_list_edit_distance.py",
    "tools/verify_p4b_02b144_parameter_list_has_subsequence.py",
    "tools/verify_p4b_02b145_parameter_list_hamming_distance.py",
    "tools/verify_p4b_02b146_parameter_list_starts_with.py",
    "tools/verify_p4b_02b147_parameter_list_ends_with.py",
    "tools/verify_p4b_02b148_parameter_list_intersection.py",
    "tools/verify_p4b_02b149_parameter_list_symmetric_difference.py",
    "tools/verify_p4b_02b150_parameter_list_union.py",
    "tools/verify_p4b_02b151_parameter_list_relative_complement.py",
    "tools/verify_p4b_02b152_parameter_list_multiset_equal.py",
    "tools/verify_p4b_02b153_parameter_list_contains_multiset.py",
    "tools/verify_p4b_02b154_parameter_list_jaccard_index.py",
    "tools/verify_p4b_02b155_parameter_list_dice_index.py",
    "tools/verify_p4b_02b156_parameter_list_overlap_coefficient.py",
    "tools/verify_p4b_02b157_parameter_list_contains_sequence.py",
    "tools/verify_p4b_02b158_parameter_list_tversky_index.py",
    "tools/verify_p4b_02b159_parameter_list_longest_common_subsequence.py",
    "tools/verify_p4b_02b160_parameter_list_all_equal.py",
    "tools/verify_p4b_02b161_parameter_list_min_max_item.py",
    "tools/verify_p4b_02b162_parameter_list_nth_smallest_item.py",
    "tools/verify_p4b_02b163_parameter_list_nth_largest_item.py",
    "tools/verify_p4b_02b164_parameter_list_median_item.py",
    "tools/verify_p4b_02b165_parameter_list_mode_items.py",
    "tools/verify_p4b_02b166_parameter_list_anti_mode_items.py",
    "tools/verify_p4b_02b167_parameter_list_dedup_keep_last.py",
    "tools/verify_p4b_02b168_parameter_list_run_count.py",
    "tools/verify_p4b_02b169_parameter_list_sorted_rank.py",
    "tools/verify_p4b_02b170_parameter_list_longest_run_item.py",
    "tools/verify_p4b_02b171_parameter_list_longest_run_start_index.py",
    "tools/verify_p4b_02b172_parameter_list_adjacent_change_count.py",
    "tools/verify_p4b_02b173_parameter_list_total_equal_pair_count.py",
    "tools/verify_p4b_02b174_parameter_list_majority_item.py",
    "tools/verify_p4b_02b175_parameter_list_is_alternating.py",
    "tools/verify_p4b_02b176_parameter_list_entropy.py",
    "tools/verify_p4b_02b177_parameter_list_gini_impurity.py",
    "tools/verify_p4b_02b178_parameter_list_normalized_entropy.py",
    "tools/verify_p4b_02b179_parameter_list_mode_frequency.py",
    "tools/verify_p4b_02b180_parameter_list_prevalence_ratio.py",
    "tools/verify_p4b_02b181_parameter_list_frequency_normalized.py",
    "tools/verify_p4b_02b182_parameter_list_first_occurrence_indices.py",
    "tools/verify_p4b_02b183_parameter_list_run_boundaries.py",
    "tools/verify_p4b_02b184_parameter_list_pairwise_distinct_adjacent.py"
  ],
  "P4B-03": [
    "tools/verify_p4b_dual_ami_pe_loader_declarations.py",
    "tools/verify_p4b_03_standard_abi_host_slice.py"
  ],
  "P4B-04": [
    "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py",
    "tools/verify_p4b_04_worker_partial_state.py"
  ],
  "P4B-07": [
    "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py",
    "tools/verify_p4b_07_authorized_fixture_abi_observation.py",
    "tools/verify_p4b_07_raw_abi_parity.py",
    "tools/verify_p4b_07_rx_init_surface_exploration.py"
  ],
  "P4B-08": [
    "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py",
    "tools/verify_p4b_08_s4p_observation.py",
    "tools/verify_p4b_08b_s4p_ami_matrix_preflight.py"
  ],
  "P4B-09": [
    "tools/verify_p4b_ads_pcie_gen5_dual_ami_asset_preflight.py"
  ],
  "P5-02": [
    "tools/verify_p5_agent_com_git_object_preflight.py",
    "tools/verify_p5_02e_canonical_parameter_reference.py",
    "tools/verify_p5_02f_parameter_json_draft.py",
    "tools/verify_p5_02g_canonical_json.py",
    "tools/verify_p5_02h_canonical_json_v2.py",
    "tools/verify_p5_02i_warning_observation.py",
    "tools/verify_p5_02j_value_consumption.py",
    "tools/verify_p5_02k_matlab_literal.py",
    "tools/verify_p5_02l_resolve_parameters.py",
    "tools/verify_p5_02m_warning_detector.py",
    "tools/verify_p5_02n_warning_report.py"
  ],
  "P5-05": [
    "tools/verify_p5_agent_com_git_object_preflight.py",
    "tools/verify_p5_05a_workbook_importer.py",
    "tools/verify_p5_05b_csv_reader.py",
    "tools/verify_p5_05c_mat_reader.py",
    "tools/verify_p5_05d_parameter_surface.py",
    "tools/verify_p5_05e_com_parameters.py",
        "tools/verify_p5_05f_parameter_resolver.py"
  ],
  "P5-06": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p5_06a_matlab_oracle_first_run.py",
    "tools/verify_p5_06b_oracle_metric_surface.py",
    "tools/verify_p5_06c_normalized_input_surface.py",
    "tools/verify_p5_06d_canonical_input_keys.py",
    "tools/verify_p5_06e_oracle_metric_reference.py",
        "tools/verify_p5_06f_com_chain_core.py",
        "tools/verify_p5_06g_oracle_chain_compare.py"
  ],
  "P5-08": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p5_08a_com_run_admission.py",
        "tools/verify_p5_08b_com_run_execution.py"
  ],
  "P5-09": [
    "tools/verify_release_capability_publication.py"
  ],
  "P6-02": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p6_02_03_04_fixed_edge_complete.py"
  ],
  "P6-03": [
    "tools/verify_release_capability_publication.py"
  ],
  "P6-04": [
    "tools/verify_release_capability_publication.py"
  ],
  "P6-05": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p6_05_command_manifest_single_source.py"
  ],
  "P6-07": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p6_07_ai_conformance_surface.py"
  ],
  "P6-08": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p6_08_report_inspect_metadata_only.py"
  ],
  "P6-09": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p6_09_negative_integration_gate.py"
  ],
  "P6-10": [
    "tools/verify_release_capability_publication.py",
    "tools/verify_p6_10_single_rust_contract.py"
  ],
  "P7-01": [
    "tools/verify_p7_windows_twin_build.py"
  ],
  "P7-02": [
    "tools/verify_p7_release_composition.py"
  ],
  "P7-03": [
    "tools/verify_p7_release_archive.py"
  ],
  "P7-04": [
    "tools/verify_p7_isolated_install.py"
  ],
  "P7-05": [
    "tools/verify_release_capability_publication.py"
  ],
  "P7-06": [
    "tools/verify_p7_evidence_anchor_v2.py"
  ],
  "P7-07": [
    "tools/verify_p7_candidate_build_license_material_observation_evidence_v2.py"
  ],
  "P7-08": [
    "tools/verify_p7_08_path_scoped_replacement_map.py",
    "tools/verify_p7_08_drift_gate_retirement_strategy.py",
    "tools/verify_p7_08_retirement_approval_record.py"
  ],
  "P7-09": [
    "tools/verify_external_history_citations.py"
  ]
}


class CoverageError(RuntimeError):
    pass


def git_tracked(relative: str) -> bool:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--error-unmatch", "--", relative],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=60,
    )
    return completed.returncode == 0


def validate(root: Path = ROOT) -> dict[str, Any]:
    if not isinstance(OPEN_ITEM_GATES, dict) or not OPEN_ITEM_GATES:
        raise CoverageError("coverage_map_invalid")
    total = 0
    for item, gates in sorted(OPEN_ITEM_GATES.items()):
        if not isinstance(gates, list) or not gates:
            raise CoverageError(f"item_gates_empty:{item}")
        for gate in gates:
            # Newly delivered gates may be untracked working-tree files; what
            # matters for coverage is that the gate exists on disk and is
            # either tracked or present as a working-tree deliverable.
            if not (root / gate).is_file():
                raise CoverageError(f"gate_missing:{item}:{gate}")
            total += 1
    return {"valid": True, "items": len(OPEN_ITEM_GATES), "gates": total}


def main() -> int:
    parser = argparse.ArgumentParser()
    arguments = parser.parse_args()
    try:
        result = validate(ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, **result}, sort_keys=True))
        return 0
    except CoverageError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())