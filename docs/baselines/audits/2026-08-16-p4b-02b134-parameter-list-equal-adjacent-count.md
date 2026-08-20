# P4B-02b134 Parameter List Equal-Adjacent Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b134 (equal adjacent pair counting on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_equal_adjacent_count_v1.rs` in `sipi-ami-text`:
`parameter_list_equal_adjacent_count_v1` counts the equal adjacent pairs of the trimmed items
of a validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns the number of adjacent index pairs
`(i, i + 1)` whose items are equal (raw byte equality, per the P4B-02b0 raw-byte binding). The
number of 02b119 runs equals `item_count - equal_adjacent_count`; a list with no equal adjacent
pairs has item_count runs. This is the adjacency companion of 02b119 run-length encoding and of
02b108 occurrence counting. Fail-closed: a non-List value yields `NotAList`; a token that does
not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the adjacency rule over 4 test cases.

## Result

- 6 Rust unit tests green (equal adjacent, all distinct, all equal, single item, non-list,
  spacing canonicalized).
- Cross-check: 4 test cases (equal adjacent, all distinct, all equal, non-list) driven through
  product runner `p4b_02b134_parameter_list_equal_adjacent_count_runner`; independent Python
  reference matches 100% on counts and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b134_parameter_list_equal_adjacent_count.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b134-parameter-list-equal-adjacent-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b134-parameter-list-equal-adjacent-count-stage.v1.yaml`; source map
  `p4b-02b134-mit-source-map.v1.yaml`.
- PLAN **P4B-02b134**; ledger note/gate P4B-02; coverage gates 303 -> 304.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts adjacent pairs on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
