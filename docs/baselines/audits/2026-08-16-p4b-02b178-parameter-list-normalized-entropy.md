# P4B-02b178 Parameter List Normalized Entropy Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b178 (value-level evenness on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_normalized_entropy_v1.rs` in `sipi-ami-text`:
`parameter_list_normalized_entropy_v1` returns the normalized Shannon entropy (evenness) of
the frequency distribution of the trimmed items of a validated List-typed
`AmiParameterValueV1` value under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): computes the 02b176 Shannon entropy in bits divided by `log2(len)` (raw
byte equality, per the P4B-02b0 raw-byte binding), returned as f64 in \[0, 1\] (0 for an
all-equal list, 1 for an all-distinct list; a single-item list yields 0, the
limit of H / log2(len) as the distribution concentrates, resolving the 0/0
quotient). This is the evenness (Pielou J') companion of
02b176 Shannon entropy and of 02b177 Gini impurity. Fail-closed: the value not declared List
yields `NotAList`; the token not matching the List shape yields `MalformedList` (unreachable
for values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the evenness rule over 4 test cases, comparing
12-decimal formatted strings bit-for-bit.

## Result

- 6 Rust unit tests green (all equal zero, all distinct one, two-item balanced one, single
  item zero, unbalanced below one, non-list).
- Cross-check: 4 test cases (all equal, all distinct, unbalanced, non-list) driven through
  product runner `p4b_02b178_parameter_list_normalized_entropy_runner`; independent Python
  reference matches 100% on 12-decimal evenness strings and error keys; 4/4
  matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b178_parameter_list_normalized_entropy.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b178-parameter-list-normalized-entropy-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b178-parameter-list-normalized-entropy-stage.v1.yaml`; source map
  `p4b-02b178-mit-source-map.v1.yaml`.
- PLAN **P4B-02b178**; ledger note/gate P4B-02; coverage gates 347 -> 348.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes normalized entropy on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
