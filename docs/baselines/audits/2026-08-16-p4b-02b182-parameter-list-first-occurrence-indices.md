# P4B-02b182 Parameter List First-Occurrence Indices Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b182 (value-level first-occurrence indices on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_first_occurrence_indices_v1.rs` in `sipi-ami-text`:
`parameter_list_first_occurrence_indices_v1` returns the `(item, first_occurrence_index)` pairs of
the distinct trimmed items of a validated List-typed `AmiParameterValueV1` value under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty), in first-occurrence order, by
raw byte equality (per the P4B-02b0 raw-byte binding). `first_occurrence_index` is the 0-based
position of the item's first appearance, consistent with the 0-based convention of 02b110 item
index-of. This is the positional companion of 02b181 normalized frequency (which returns
`(item, count / total)`): the two slices share the same first-occurrence ordering, differing only
in the paired value. Fail-closed: the value not declared List yields `NotAList`; the token not
matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the rule over 4 test cases, comparing the `(item, index)` arrays for
bit-exact equality per distinct item.

## Result

- 6 Rust unit tests green (mixed first-occurrence, all equal single entry, all distinct contiguous
  indices, single item index zero, spacing canonicalized, non-list).
- Cross-check: 4 test cases (mixed, all equal, all distinct, non-list) driven through product runner
  `p4b_02b182_parameter_list_first_occurrence_indices_runner`; independent Python reference matches
  100% on first-occurrence-index arrays and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b182_parameter_list_first_occurrence_indices.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b182-parameter-list-first-occurrence-indices-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b182-parameter-list-first-occurrence-indices-stage.v1.yaml`; source map
  `p4b-02b182-mit-source-map.v1.yaml`.
- PLAN **P4B-02b182**; ledger note/gate P4B-02; coverage gates 351 -> 352.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes first-occurrence indices on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
