# Batch Test-Import Repair and Evidence-Drift Classification

Module-style test discovery (`python -m unittest tools.test_*`) exposed a
systemic import defect: 14 test files imported `verify_*` modules without
adding `tools/` to `sys.path`, which worked under `run_all_tests.py`
(cwd=tools) but failed as modules. All 14 were repaired this round; a
full scan confirms all 37 `from verify_*` test files now carry the
sys.path insertion.

## Repaired Files (14)

- test_m1_artifacts.py, test_m1_backend_execution_envelopes.py,
  test_m1_runtime_validation.py, test_clean_room_templates.py,
  test_m1_run_envelopes.py,
  test_verify_channel_s2p_matched_preflight.py,
  test_verify_p3c_external_ads_selected_highloss_waveform_only_historical_source_drift.py,
  test_verify_p3c_ieee_bsd_inline_causality_direct_port.py,
  test_verify_p3c_ieee_bsd_inline_causality_source_preflight.py,
  test_verify_p3c_ieee_bsd_truncation_direct_port.py,
  test_verify_p3c_selected_s4p_causality_observation_evidence.py,
  test_verify_p3c_selected_oob_zero_extension_diagnostic_core.py,
  test_verify_p3c_selected_s4p_raw_periodic_observation_evidence.py,
  test_verify_p3c_selected_s4p_truncation_observation_evidence.py.
Verified: all 14 suites pass (47 tests) under module discovery.

## Full Verify Run (534 tests)

- 17 failures/errors remain, ALL classified as evidence-binding drift
  (verifiers correctly fail closed):
  - P7 candidate drift (6): bcryptprimitives/pe_diagnosis/processprng
    positive tests bind candidate `b775dde` to current HEAD;
  - channel evidence drift (3): matched external-compare v1/v2 bind to
    product inputs that have since changed;
  - P3C observation drift (8): ADS/s4p/residual evidence binds external
    source sets that have drifted.
- No import/assertion defects remain; no golden/evidence rewriting; no
  tolerance widening. All drift failures require external-chain rebind
  (P7/channel) or fresh external observation (P3C ADS) to restore.

## Scope

- This repair improves test portability; it changes no verifier semantics
  and no product behavior.
