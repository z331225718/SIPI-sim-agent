# P4B-02b121 Parameter List Frequency Map Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b121 (per-item frequency map on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_frequency_v1.rs` in `sipi-ami-text`:
`parameter_list_item_frequencies_v1` counts the total occurrences of every distinct trimmed
item of a validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns the `(item, count)` pairs in
first-occurrence order (raw byte equality, per the P4B-02b0 raw-byte binding, mirroring the
02b107 distinct-count first-occurrence semantics). The sum of all counts equals the item count;
the number of pairs equals the 02b107 distinct count. This is the total-count companion of 02b108
occurrence counting (per single query) and of 02b119 run-length encoding (whose run lengths sum
to these counts per item). Fail-closed: a non-List value yields `NotAList`; a token that does
not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the frequency rule over 4 test cases.

## Result

- 6 Rust unit tests green (counts every item, first-occurrence order, all distinct, single item,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (repeated items, first-occurrence order, all distinct, non-list)
  driven through product runner `p4b_02b121_parameter_list_frequency_runner`; independent
  Python reference matches 100% on frequency pairs and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b121_parameter_list_frequency.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b121-parameter-list-frequency-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b121-parameter-list-frequency-stage.v1.yaml`; source map
  `p4b-02b121-mit-source-map.v1.yaml`.
- PLAN **P4B-02b121**; ledger note/gate P4B-02; coverage gates 290 -> 291.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes frequency maps on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
