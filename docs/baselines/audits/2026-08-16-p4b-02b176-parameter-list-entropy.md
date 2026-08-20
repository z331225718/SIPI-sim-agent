# P4B-02b176 Parameter List Shannon Entropy Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b176 (value-level Shannon entropy on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_entropy_v1.rs` in `sipi-ami-text`:
`parameter_list_entropy_v1` returns the Shannon entropy in bits of the frequency
distribution of the trimmed items of a validated List-typed `AmiParameterValueV1` value
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): computes
`-sum(p_i * log2(p_i))` over the distinct trimmed items with empirical probabilities
`p_i = count_i / len` (raw byte equality, per the P4B-02b0 raw-byte binding), returned as
f64 in \[0, log2(len)\] (0 for an all-equal list, log2(len) for an all-distinct list). This
is the information-theoretic companion of 02b121 frequency and of 02b165 mode items (a
single-mode distribution has entropy 0). Fail-closed: the value not declared List yields
`NotAList`; the token not matching the List shape yields `MalformedList` (unreachable for
values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the entropy rule over 4 test cases, comparing
12-decimal formatted strings bit-for-bit.

## Result

- 6 Rust unit tests green (all equal zero, all distinct log len, two-item balanced one,
  single item zero, spacing canonicalized, non-list).
- Cross-check: 4 test cases (all equal, all distinct, unbalanced, non-list) driven through
  product runner `p4b_02b176_parameter_list_entropy_runner`; independent Python reference
  matches 100% on 12-decimal entropy strings and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b176_parameter_list_entropy.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b176-parameter-list-entropy-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b176-parameter-list-entropy-stage.v1.yaml`; source map
  `p4b-02b176-mit-source-map.v1.yaml`.
- PLAN **P4B-02b176**; ledger note/gate P4B-02; coverage gates 345 -> 346.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes Shannon entropy on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
