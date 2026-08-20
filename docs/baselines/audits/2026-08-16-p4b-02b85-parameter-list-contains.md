# P4B-02b85 Parameter List Item Membership Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b85 (list item membership on validated AMI parameter values)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_list_contains_v1.rs` in `sipi-ami-text`:
`parameter_list_contains_item_v1` checks whether a validated List-typed `AmiParameterValueV1`
contains a query item under the P4B-02b1 list rule (`(item, item, ...)`, items trimmed,
non-empty): returns whether any trimmed item equals the query item exactly (raw byte equality, per
the P4B-02b0 raw-byte binding; the query itself is not trimmed). This is the membership companion
of 02b83 item counting and 02b84 item access. Fail-closed: a non-List value yields `NotAList`; a
token that does not match the List shape yields `MalformedList` (unreachable for values built via
`AmiParameterValueV1::try_new`, kept defensive instead of panicking). An independent Python
reference replicates the membership rule over 4 test cases.

## Result

- 6 Rust unit tests green (contains exact item, missing item, items trimmed but query raw, non-list,
  single item list, membership matches typed equivalence items).
- Cross-check: 4 test cases (contains, missing, trimming, non-list) driven through product runner
  `p4b_02b85_parameter_list_contains_runner`; independent Python reference matches 100% on
  contains flags and error keys; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b85_parameter_list_contains.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b85-parameter-list-contains-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b85-parameter-list-contains-stage.v1.yaml`; source map
  `p4b-02b85-mit-source-map.v1.yaml`.
- PLAN **P4B-02b85**; ledger note/gate P4B-02; coverage gates 254 -> 255.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks membership on validated values only; non-List inputs fail closed; query compared raw.
- No release certification, no acceptance evidence.
