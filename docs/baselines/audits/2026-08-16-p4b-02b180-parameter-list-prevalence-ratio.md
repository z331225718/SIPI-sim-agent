# P4B-02b180 Parameter List Prevalence Ratio Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b180 (value-level prevalence ratio on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_prevalence_ratio_v1.rs` in `sipi-ami-text`:
`parameter_list_prevalence_ratio_v1` returns the prevalence ratio (max count / total) of
the distinct trimmed items of a validated List-typed `AmiParameterValueV1` value under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty), by raw byte equality
(per the P4B-02b0 raw-byte binding), as f64 in (0, 1] (1.0 for an all-equal list, 1/n for
an all-distinct list of n items). This is the ratio companion of 02b179 mode frequency (the
prevalence ratio is the mode frequency divided by the list length) and of 02b121 frequency
(the prevalence ratio is the maximum entry count over the length). Fail-closed: the value
not declared List yields `NotAList`; the token not matching the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the rule over 4
test cases, comparing 12-decimal formatted strings bit-for-bit.

## Result

- 6 Rust unit tests green (all equal one, all distinct reciprocal, unbalanced three fifths,
  single item one, spacing canonicalized, non-list).
- Cross-check: 4 test cases (all equal, all distinct, unbalanced, non-list) driven through
  product runner `p4b_02b180_parameter_list_prevalence_ratio_runner`; independent Python
  reference matches 100% on 12-decimal prevalence-ratio strings and error keys; 4/4
  matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b180_parameter_list_prevalence_ratio.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b180-parameter-list-prevalence-ratio-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b180-parameter-list-prevalence-ratio-stage.v1.yaml`; source map
  `p4b-02b180-mit-source-map.v1.yaml`.
- PLAN **P4B-02b180**; ledger note/gate P4B-02; coverage gates 349 -> 350.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes prevalence ratio on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
