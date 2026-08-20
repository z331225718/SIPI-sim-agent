# P4B-02b103 Parameter List Item Swap Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b103 (positional list item swap on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_swap_v1.rs` in `sipi-ami-text`:
`swap_parameter_list_items_v1` swaps two items of a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical
list token whose items at the two 0-based indices are exchanged (equal indices leave the token
unchanged; items re-joined with `", "`). This extends the list-edit family (02b84 access, 02b98
dedup, 02b99 replace, 02b100 remove, 02b101 append, 02b102 insert) with positional exchange.
Fail-closed: a non-List value yields `NotAList`; a token that does not match the List shape yields
`MalformedList` (unreachable for values built via `AmiParameterValueV1::try_new`, kept defensive
instead of panicking); either index at or beyond the item count yields `IndexOutOfRange` carrying
the offending index and the actual item count. An independent Python reference replicates the swap
rule over 4 test cases.

## Result

- 6 Rust unit tests green (swap two indices, middle pair, equal indices unchanged, out of range,
  non-list, spacing canonicalized).
- Cross-check: 4 test cases (swap middle, swap ends, equal indices, out of range) driven through
  product runner `p4b_02b103_parameter_list_swap_runner`; independent Python reference matches
  100% on swapped tokens and error keys with index/count; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b103_parameter_list_swap.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b103-parameter-list-swap-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b103-parameter-list-swap-stage.v1.yaml`; source map
  `p4b-02b103-mit-source-map.v1.yaml`.
- PLAN **P4B-02b103**; ledger note/gate P4B-02; coverage gates 272 -> 273.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Swaps list items on validated values only; out-of-range and non-List inputs fail closed.
- No release certification, no acceptance evidence.
