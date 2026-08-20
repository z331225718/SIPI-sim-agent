# P4B-02b181 Parameter List Normalized Frequency Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b181 (value-level normalized frequency on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_frequency_normalized_v1.rs` in `sipi-ami-text`:
`parameter_list_frequency_normalized_v1` returns the `(item, count / total)` pairs of the
distinct trimmed items of a validated List-typed `AmiParameterValueV1` value under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty), in first-occurrence
order, by raw byte equality (per the P4B-02b0 raw-byte binding), as f64 proportions in
(0, 1] summing to 1.0. This is the proportion companion of 02b121 item frequencies (the
normalized map divides each count by the list length) and the per-item companion of 02b180
prevalence ratio (the maximum entry is the prevalence ratio). Fail-closed: the value not
declared List yields `NotAList`; the token not matching the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the rule over 4
test cases, comparing 12-decimal formatted strings bit-for-bit per distinct item.

## Result

- 6 Rust unit tests green (mixed proportions, all equal one, all distinct reciprocal, single
  item one, spacing canonicalized, non-list).
- Cross-check: 4 test cases (mixed, all equal, all distinct, non-list) driven through product
  runner `p4b_02b181_parameter_list_frequency_normalized_runner`; independent Python
  reference matches 100% on 12-decimal normalized-frequency arrays and error keys; 4/4
  product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b181_parameter_list_frequency_normalized.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b181-parameter-list-frequency-normalized-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b181-parameter-list-frequency-normalized-stage.v1.yaml`; source map
  `p4b-02b181-mit-source-map.v1.yaml`.
- PLAN **P4B-02b181**; ledger note/gate P4B-02; coverage gates 350 -> 351.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes normalized frequencies on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
