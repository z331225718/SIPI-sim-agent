# P4B-02b184 Parameter List Pairwise-Distinct Adjacent Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b184 (value-level pairwise-distinct adjacent pairs on AMI
  parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_pairwise_distinct_adjacent_v1.rs` in `sipi-ami-text`:
`parameter_list_pairwise_distinct_adjacent_v1` returns, for every adjacent index `i` at which
the two trimmed items differ, the `(item[i], item[i + 1])` pair of a validated List-typed
`AmiParameterValueV1` value under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty), in list order keeping duplicate pairs at distinct positions (raw byte equality, per
the P4B-02b0 raw-byte binding). The pair count therefore equals the 02b172 adjacent-change
count, and every returned pair is a length-2 window of the 02b157 contains-sequence semantics.
The result is empty for a single-item list or an all-equal list; an empty result is a legal
value, mirroring the 02b40 empty-search result. Fail-closed: the value not declared List
yields `NotAList`; the token not matching the List shape yields `MalformedList` (unreachable
for values built via `AmiParameterValueV1::try_new`, kept defensive instead of panicking). An
independent Python reference replicates the rule over 4 test cases, comparing the `(left,
right)` arrays for bit-exact equality per position.

## Result

- 6 Rust unit tests green (mixed pairs in order with duplicates, duplicate pair kept at each
  position, all distinct emit every adjacent pair, all equal single pair empty result, single
  item empty result, non-list).
- Cross-check: 4 test cases (mixed, duplicate pairs, all equal empty, non-list) driven through
  product runner `p4b_02b184_parameter_list_pairwise_distinct_adjacent_runner`; independent
  Python reference matches 100% on pair arrays and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b184_parameter_list_pairwise_distinct_adjacent.py` + 6 tests;
  crosscheck evidence
  `docs/baselines/p4b-02b184-parameter-list-pairwise-distinct-adjacent-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b184-parameter-list-pairwise-distinct-adjacent-stage.v1.yaml`; source map
  `p4b-02b184-mit-source-map.v1.yaml`.
- PLAN **P4B-02b184**; ledger note/gate P4B-02; coverage gates 353 -> 354.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes pairwise-distinct adjacent pairs on validated values only; non-List inputs fail
  closed.
- No release certification, no acceptance evidence.
