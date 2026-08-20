# CRLF Test-Import Repair (7 Files)

A second wave of module-style discovery found 7 more P3C test files
importing `verify_*` modules without sys.path setup. These files use
CRLF line endings, which broke LF-based edit operations; the repair was
performed with line-level, newline-preserving Python scripts.

## Repaired Files (7)

- test_verify_p3c_external_ads_reference_metric_observation_evidence.py
- test_verify_p3c_external_ads_reference_metric_rejection_reason_evidence.py
- test_verify_p3c_external_ads_selected_highloss_waveform_only_observation_evidence.py
- test_verify_p3c_selected_highloss_prbs9_waveform_only_v3.py
- test_verify_p3c_selected_oob_zero_extension_sensitivity_observation_evidence.py
- test_verify_p3c_selected_s4p_candidate_observation_evidence.py
- test_verify_p3c_selected_truncation_waveform_sensitivity_core.py

All 7 suites pass under module discovery (23 tests). One file also
required adding `from pathlib import Path`.

## Final Scan

A comprehensive scan across all three import forms (`from X import`,
`import X as`, `import X`) over all tools test files reports 0 missing
sys.path setups: every sibling-module import is now importable as a
module. Combined with the earlier 14-file repair, the repository test
suite is fully portable between `run_all_tests.py` (cwd execution) and
`python -m unittest` (module execution).

## Scope

- No verifier semantics or product behavior changed; no evidence or
  tolerance modified.
