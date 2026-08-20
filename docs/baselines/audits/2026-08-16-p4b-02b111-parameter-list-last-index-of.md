# P4B-02b111 Parameter List Item Last Index-Of Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b111 (last-position item lookup on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_last_index_of_v1.rs` in `sipi-ami-text`:
`last_index_of_parameter_list_item_v1` locates the last position of a query item in a validated
List-typed `AmiParameterValueV1` under the P4B-02b1 list rule (`(item, item, ...)`, items
trimmed, non-empty): returns the 0-based index of the last trimmed item that equals the query
item exactly (raw byte equality, per the P4B-02b0 raw-byte binding; the query itself is not
trimmed). This is the reverse-position companion of 02b110 first-position lookup and of 02b108
occurrence counting. Fail-closed: a non-List value yields `NotAList`; a token that does not
match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking); an absent item yields
`ItemNotFound` (never conflated with the valid index 0). An independent Python reference
replicates the lookup rule over 4 test cases.

## Result

- 6 Rust unit tests green (last occurrence, single occurrence, absent item, raw query vs trimmed
  items, non-list, occurrence-count-tail consistency).
- Cross-check: 4 test cases (last occurrence, single occurrence, absent item, non-list) driven
  through product runner `p4b_02b111_parameter_list_last_index_of_runner`; independent Python
  reference matches 100% on indices and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b111_parameter_list_last_index_of.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b111-parameter-list-last-index-of-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b111-parameter-list-last-index-of-stage.v1.yaml`; source map
  `p4b-02b111-mit-source-map.v1.yaml`.
- PLAN **P4B-02b111**; ledger note/gate P4B-02; coverage gates 280 -> 281.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Looks up list items on validated values only; non-List inputs fail closed.
- No release certification, no acceptance evidence.
