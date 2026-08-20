# P4B-02b145 Parameter List Hamming Distance Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b145 (position-wise Hamming distance on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_hamming_distance_v1.rs` in `sipi-ami-text`:
`list_hamming_distance_v1` computes the Hamming distance of two validated List-typed
`AmiParameterValueV1` values under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns the number of positions at which the two values' trimmed items differ (raw
byte equality, per the P4B-02b0 raw-byte binding). This is the position-wise companion of 02b143
edit distance (the Hamming distance is an upper bound on the edit distance for equal-length
sequences). Fail-closed: either value not declared List yields `NotAList`; either token not
matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); differing item counts
yield `LengthMismatch` (the Hamming distance is undefined without position alignment). An
independent Python reference replicates the Hamming rule over 4 test cases.

## Result

- 6 Rust unit tests green (Hamming distance, identical zero, all different max, length
  mismatch, non-list, spacing canonicalized).
- Cross-check: 4 test cases (Hamming, identical, length mismatch, non-list) driven through
  product runner `p4b_02b145_parameter_list_hamming_distance_runner`; independent Python
  reference matches 100% on distances and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b145_parameter_list_hamming_distance.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b145-parameter-list-hamming-distance-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b145-parameter-list-hamming-distance-stage.v1.yaml`; source map
  `p4b-02b145-mit-source-map.v1.yaml`.
- PLAN **P4B-02b145**; ledger note/gate P4B-02; coverage gates 314 -> 315.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes Hamming distances on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
