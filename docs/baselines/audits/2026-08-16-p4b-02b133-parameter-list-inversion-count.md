# P4B-02b133 Parameter List Inversion Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b133 (pairwise inversion counting on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_inversion_count_v1.rs` in `sipi-ami-text`:
`parameter_list_inversion_count_v1` counts the inversions of the trimmed items of a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): returns the number of index pairs `(i, j)` with `i < j` whose items are
in strictly decreasing byte order (raw byte equality and byte comparison, per the P4B-02b0
raw-byte binding). A sorted list has zero inversions; a reversed list of length n has
n*(n-1)/2 inversions. This is the disorder companion of 02b105 sort and of 02b124 sortedness
check. Fail-closed: a non-List value yields `NotAList`; a token that does not match the List
shape yields `MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`,
kept defensive instead of panicking). An independent Python reference replicates the inversion
rule over 4 test cases.

## Result

- 6 Rust unit tests green (sorted zero, reversed max, partial inversions, equal items, non-list,
  single item).
- Cross-check: 4 test cases (sorted zero, reversed max, partial inversions, non-list) driven
  through product runner `p4b_02b133_parameter_list_inversion_count_runner`; independent
  Python reference matches 100% on counts and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b133_parameter_list_inversion_count.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b133-parameter-list-inversion-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b133-parameter-list-inversion-count-stage.v1.yaml`; source map
  `p4b-02b133-mit-source-map.v1.yaml`.
- PLAN **P4B-02b133**; ledger note/gate P4B-02; coverage gates 302 -> 303.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts inversions on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
