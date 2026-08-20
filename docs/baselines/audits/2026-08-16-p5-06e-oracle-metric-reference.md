# P5-06e COM Oracle Metric Reference Binding - Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06e (COM oracle metric reference binding)
- Status: delivered and digest-verified against the machine-verified P5-06a
  MATLAB oracle first-run evidence.

## Method

The owner B4 decision authorized MATLAB oracle comparison. The authoritative
reference values were already produced by the P5-06a first run and stored in
the machine-verified evidence (summary.json with recorded SHA-256 in
output_file_hashes). This slice binds those values to the owner C4 metric
profile (COM_dB / ICN_mV / ERL): the aggregate reference is extracted from
the evidence summary_content (summary_case_index=1), a canonical digest is
independently recomputed over the sorted key=repr(value) lines, and the
bound reference document is required to carry the exact same values and
digest. Per-case references (case_index 1 and 2) are also recorded. No
re-run of MATLAB is needed: the authoritative values are already in the
verified evidence; this slice makes them machine-bindable.

## Result

- Aggregate oracle reference: COM_dB = 5.190191599808681, ICN_mV =
  4.601554213273623, ERL = 16.742740133561476.
- Digest f7b30359cecf9958952caf7b7081c2e78e6057dd3336d84ae87e1d8dbda1bae7
  independently recomputed and matched.
- Per-case references recorded for case_index 1 and 2.
- Bound to C4 profile policy sipi.p3c-03c.c4-profile.v1.com-icn-erl-1pct.

## Binding

- Verifier verify_p5_06e_oracle_metric_reference.py + 7 tests; reference
  docs/baselines/p5-06e-com-oracle-metric-reference.v1.yaml.
- Evidence docs/baselines/p5-06-matlab-oracle-first-run-evidence.v1.yaml.
- PLAN **P5-06e**; ledger note/gate P5-06; coverage gates 113 -> 114.
