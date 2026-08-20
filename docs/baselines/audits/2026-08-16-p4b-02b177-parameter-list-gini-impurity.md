# P4B-02b177 Parameter List Gini Impurity Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b177 (value-level Gini impurity on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_gini_impurity_v1.rs` in `sipi-ami-text`:
`parameter_list_gini_impurity_v1` returns the Gini impurity of the frequency distribution
of the trimmed items of a validated List-typed `AmiParameterValueV1` value under the P4B-02b1
list rule (`(item, item, ...)`, items trimmed, non-empty): computes `1 - sum(p_i^2)` over
the distinct trimmed items with empirical probabilities `p_i = count_i / len` (raw byte
equality, per the P4B-02b0 raw-byte binding), returned as f64 in \[0, 1 - 1/len\] (0 for an
all-equal list; the probability that two independent draws pick different items). This is the
quadratic companion of 02b176 Shannon entropy and of 02b121 frequency. Fail-closed: the value
not declared List yields `NotAList`; the token not matching the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the Gini rule
over 4 test cases, comparing 12-decimal formatted strings bit-for-bit.

## Result

- 6 Rust unit tests green (all equal zero, two-item balanced half, unbalanced, single item
  zero, spacing canonicalized, non-list).
- Cross-check: 4 test cases (all equal, balanced, unbalanced, non-list) driven through
  product runner `p4b_02b177_parameter_list_gini_impurity_runner`; independent Python
  reference matches 100% on 12-decimal Gini strings and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b177_parameter_list_gini_impurity.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b177-parameter-list-gini-impurity-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b177-parameter-list-gini-impurity-stage.v1.yaml`; source map
  `p4b-02b177-mit-source-map.v1.yaml`.
- PLAN **P4B-02b177**; ledger note/gate P4B-02; coverage gates 346 -> 347.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes Gini impurity on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
