# P4B-02b162 Parameter List Nth-Smallest Item Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b162 (value-level order statistic on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_nth_smallest_item_v1.rs` in `sipi-ami-text`:
`parameter_list_nth_smallest_item_v1` returns the item at zero-based rank `nth` in sorted
order of the trimmed items of a validated List-typed `AmiParameterValueV1` value under the
P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty), ordered by raw byte
equality and byte lexicographic order (per the P4B-02b0 raw-byte binding; for valid UTF-8
this order equals code-point order), with duplicates counted as separate positions. This is
the order-statistic companion of 02b161 min-max item (rank 0 is the minimum, rank len-1 the
maximum). Fail-closed: the value not declared List yields `NotAList`; the token not matching
the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); a rank beyond the item
count yields `IndexOutOfRange` with the requested index and item count (never confused with
a legal rank 0). An independent Python reference replicates the order-statistic rule over 4
test cases.

## Result

- 6 Rust unit tests green (middle rank, rank zero min, duplicates as separate positions,
  single item, rank out of range, spacing canonicalized, non-list).
- Cross-check: 4 test cases (middle rank, rank zero, duplicates, rank out of range) driven
  through product runner `p4b_02b162_parameter_list_nth_smallest_item_runner`; independent
  Python reference matches 100% on items, error keys, index and item_count; 4/4
  matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b162_parameter_list_nth_smallest_item.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b162-parameter-list-nth-smallest-item-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b162-parameter-list-nth-smallest-item-stage.v1.yaml`; source map
  `p4b-02b162-mit-source-map.v1.yaml`.
- PLAN **P4B-02b162**; ledger note/gate P4B-02; coverage gates 331 -> 332.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes nth-smallest on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
