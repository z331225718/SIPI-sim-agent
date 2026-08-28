schema: sipi.pb-01-02-candidate-matrix-formal-audit.v1
status: blocked
gate_commit: b738e983a430f98b04da066f3e9c42b8f3ee58e6
prep_commit: 176956771a0d24255b427c0243d3dabc4e3fdeca
report_01_sha256: 79f1afb739a4691e691dfc4ec01628129b3fa2ebbbbe5859416cc16b31585a72
report_02_sha256: eb33e774b72ec6561e9167eed58442bec6c72037c6de6cd07d0ce9ca0924c27f
aggregate_sha256: a1f4c86c988cf5bea9d50db8c8772311487b8bbcba954a5791331f985b1d1a91
blockers: ["pb02_duo_binary_impulse:complete_metadata_drift", "pb02_impulse_analytic_ctle:complete_array_payload_drift", "pb02_impulse_analytic_ctle:complete_metadata_drift", "pb02_impulse_analytic_ctle:local_ctle_impulse_extension_not_in_pinned_native_schema", "pb02_impulse_jitter_bathtub_analysis:candidate_or_oracle_process_failed", "pb02_impulse_jitter_bathtub_analysis:candidate_output_missing", "pb02_impulse_jitter_bathtub_analysis:jitter_span_invalid_for_16_bit_prbs7_fixture", "pb02_impulse_jitter_bathtub_analysis:oracle_output_missing", "pb02_impulse_tx_rx_equalization:candidate_artifact_invalid", "pb02_impulse_tx_rx_equalization:oracle_artifact_invalid", "pb02_impulse_tx_rx_equalization:strict_native_npz_member_set_drift", "pb02_nrz_impulse:complete_metadata_drift", "pb02_pam4_impulse:complete_metadata_drift"]
claims: {"global_branch_parity": false, "pb01_duo_selected_array_parity": true, "pb02_complete_typed_output_parity": false, "product_capability_admission": false, "release_acceptance": false, "whole_payload_parity": false}
non_claims: ["PB-01 selected-array parity does not claim full PyBertData class-pickle or whole-branch parity.", "PB-02 metadata, artifact, CTLE schema, and jitter-span blockers are preserved; no blocked case is promoted.", "This aggregate is not a license decision, product capability admission, release approval, or global parity claim."]
