# P4B-02b171 Parameter List Longest Run Start Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b171 (value-level longest-run start index on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_longest_run_start_index_v1.rs` in `sipi-ami-text`:
`parameter_list_longest_run_start_index_v1` returns the zero-based start index of the
earliest maximal run achieving the longest length within a validated List-typed
`AmiParameterValueV1` value under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): scans the maximal runs of equal adjacent trimmed items (raw byte
equality, per the P4B-02b0 raw-byte binding) left to right and returns the start index of the
first run whose length equals the maximum run length. The list is non-empty by rule so at
least one run exists (start index 0 for a single-item list). This is the start-index
companion of 02b120 longest-run (length) and of 02b170 longest-run-item (the earliest
longest run's item). Fail-closed: the value not declared List yields `NotAList`; the token
not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the rule over 4 test cases.

## Result

- 6 Rust unit tests green (longest run, earliest tie, all distinct, single item, spacing
  canonicalized, non-list).
- Cross-check: 4 test cases (longest run, tie earliest, all distinct, non-list) driven
  through product runner `p4b_02b171_parameter_list_longest_run_start_index_runner`;
  independent Python reference matches 100% on start indices and error keys; 4/4
  matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b171_parameter_list_longest_run_start_index.py` + 6 tests;
  crosscheck evidence
  `docs/baselines/p4b-02b171-parameter-list-longest-run-start-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b171-parameter-list-longest-run-start-index-stage.v1.yaml`; source map
  `p4b-02b171-mit-source-map.v1.yaml`.
- PLAN **P4B-02b171**; ledger note/gate P4B-02; coverage gates 340 -> 341.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes longest-run start index on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
