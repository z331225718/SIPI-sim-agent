# P4B-02b164 Parameter List Median Item Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b164 (value-level central order statistic on AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_median_item_v1.rs` in `sipi-ami-text`:
`parameter_list_median_item_v1` returns the item at zero-based rank `(len - 1) / 2` (floor
division) in ascending sorted order of the trimmed items of a validated List-typed
`AmiParameterValueV1` value under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty), ordered by raw byte equality and byte lexicographic order (per the
P4B-02b0 raw-byte binding; for valid UTF-8 this order equals code-point order), with
duplicates counted as separate positions; for an odd item count this is the middle item, for
an even count the lower median. This is the central order statistic of 02b162 nth-smallest
and 02b163 nth-largest. Fail-closed: the value not declared List yields `NotAList`; the
token not matching the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the median rule over 4 test cases.

## Result

- 6 Rust unit tests green (odd count middle, even count lower median, single item, duplicates
  as separate positions, spacing canonicalized, non-list).
- Cross-check: 4 test cases (odd count, even count lower median, duplicates, non-list) driven
  through product runner `p4b_02b164_parameter_list_median_item_runner`; independent Python
  reference matches 100% on items and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b164_parameter_list_median_item.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b164-parameter-list-median-item-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b164-parameter-list-median-item-stage.v1.yaml`; source map
  `p4b-02b164-mit-source-map.v1.yaml`.
- PLAN **P4B-02b164**; ledger note/gate P4B-02; coverage gates 333 -> 334.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computes the median item on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
