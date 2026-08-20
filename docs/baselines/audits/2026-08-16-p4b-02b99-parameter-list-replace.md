# P4B-02b99 Parameter List Item Replace Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b99 (indexed list item replacement on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_replace_v1.rs` in `sipi-ami-text`:
`replace_parameter_list_item_v1` replaces one item of a validated List-typed `AmiParameterValueV1`
under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed, non-empty): returns the canonical
list token whose item at the 0-based index is replaced by the trimmed new item (re-joined with
`", "`). This is the write companion of 02b84 item access (read) and the list-edit primitive
complementing 02b98 dedup. Fail-closed: a non-List value yields `NotAList`; a token that does not
match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); an index at or beyond the
item count yields `IndexOutOfRange` carrying both the requested index and the actual item count.
An independent Python reference replicates the replace rule over 4 test cases.

## Result

- 6 Rust unit tests green (replace at index, first and last, new item trimmed, out of range with
  counts, non-list, single item).
- Cross-check: 4 test cases (replace middle, replace last, out of range, non-list) driven through
  product runner `p4b_02b99_parameter_list_replace_runner`; independent Python reference matches
  100% on replaced tokens and error keys with index/count; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b99_parameter_list_replace.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b99-parameter-list-replace-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b99-parameter-list-replace-stage.v1.yaml`; source map
  `p4b-02b99-mit-source-map.v1.yaml`.
- PLAN **P4B-02b99**; ledger note/gate P4B-02; coverage gates 268 -> 269.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Replaces list items on validated values only; non-List and out-of-range inputs fail closed.
- No release certification, no acceptance evidence.
