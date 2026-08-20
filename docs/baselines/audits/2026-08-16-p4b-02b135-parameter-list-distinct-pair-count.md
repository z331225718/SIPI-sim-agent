# P4B-02b135 Parameter List Distinct-Pair Count Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b135 (distinct unordered pair counting on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_distinct_pair_count_v1.rs` in `sipi-ami-text`:
`parameter_list_distinct_pair_count_v1` counts the distinct unordered pairs of the trimmed
items of a validated List-typed `AmiParameterValueV1` under the P4B-02b1 list rule
(`(item, item, ...)`, items trimmed, non-empty): returns the number of index pairs `(i, j)`
with `i < j` whose items are unequal (raw byte equality and inequality, per the P4B-02b0
raw-byte binding). The total number of unordered pairs is `n*(n-1)/2`; the equal unordered pair
count is that total minus the distinct pair count. This is the pair-level companion of 02b133
inversion counting (same iteration domain) and of 02b107 distinct counting. Fail-closed: a
non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept
defensive instead of panicking). An independent Python reference replicates the pair rule over 4
test cases.

## Result

- 6 Rust unit tests green (all distinct max, all equal zero, partial distinct, four items six
  pairs, non-list, single item).
- Cross-check: 4 test cases (all distinct, all equal, partial distinct, non-list) driven through
  product runner `p4b_02b135_parameter_list_distinct_pair_count_runner`; independent Python
  reference matches 100% on counts and error keys; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b135_parameter_list_distinct_pair_count.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b135-parameter-list-distinct-pair-count-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b135-parameter-list-distinct-pair-count-stage.v1.yaml`; source map
  `p4b-02b135-mit-source-map.v1.yaml`.
- PLAN **P4B-02b135**; ledger note/gate P4B-02; coverage gates 304 -> 305.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts pairs on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
