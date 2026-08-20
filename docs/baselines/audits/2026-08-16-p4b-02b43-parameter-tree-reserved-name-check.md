# P4B-02b43 AMI Parameter Tree Reserved-Name Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b43 (reserved-name check over an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_reserved_check_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_reserved_names_v1` checks every distinct leaf name of an `AmiParameterTreeV1`
(P4B-02b7) against a caller-supplied reserved-name set and reports the sorted, deduplicated
violations plus a clean flag and the count of distinct leaf names checked. This is the mechanism the
future reserved-name catalog will drive; the catalog itself remains profile-owned data and is not
part of this slice. A tree with reserved names is not itself an error — the report is the deliverable.
Fail-closed: an empty reserved-name set (`EmptyReservedSet`) is strictly rejected. An independent
Python reference replicates the tokenize/build/intersect pipeline over 4 test cases.

## Result

- 5 Rust unit tests green (clean tree; reserved leaf reported; violations sorted and deduplicated;
  duplicate depth names deduplicate in violations; empty reserved set fails closed).
- Cross-check: 4 test cases (clean tree, single violation, multiple sorted violations, empty
  reserved set) driven through product runner `p4b_02b43_parameter_tree_reserved_name_check_runner`;
  independent Python reference matches 100% on valid flags, checked counts, clean flags, violation
  lists, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b43_parameter_tree_reserved_name_check.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b43-parameter-tree-reserved-name-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b43-parameter-tree-reserved-name-check-stage.v1.yaml`; source map
  `p4b-02b43-mit-source-map.v1.yaml`.
- PLAN **P4B-02b43**; ledger note/gate P4B-02; coverage gates 209 -> 210.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog (mechanism only, catalog is data), no
  defaults, no document decoding.
- Checks distinct leaf names only; branch names are not checked.
- No release certification, no acceptance evidence.
