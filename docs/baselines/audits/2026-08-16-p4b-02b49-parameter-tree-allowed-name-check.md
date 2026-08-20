# P4B-02b49 AMI Parameter Tree Allowed-Name Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b49 (allowed-name whitelist check over an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_allowed_check_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_allowed_names_v1` checks every distinct leaf name of an `AmiParameterTreeV1`
(P4B-02b7) against a caller-supplied allowed-name set and reports the sorted, deduplicated
violations (leaf names NOT in the allowed set) plus a clean flag and the count of distinct leaf
names checked. This is the whitelist mirror of the reserved-name check (P4B-02b43, blacklist) — a
mechanism the future reserved-name catalog will drive; the catalog itself remains profile-owned
data and is not part of this slice. A tree with disallowed names is not itself an error — the report
is the deliverable. Fail-closed: an empty allowed-name set (`EmptyAllowedSet`) is strictly
rejected. An independent Python reference replicates the tokenize/build/difference pipeline over
4 test cases.

## Result

- 5 Rust unit tests green (all allowed clean; unknown name violation; violations sorted; duplicate
  depth names deduplicate; empty allowed set fails closed).
- Cross-check: 4 test cases (all allowed, unknown name, multiple sorted violations, empty allowed
  set) driven through product runner `p4b_02b49_parameter_tree_allowed_name_check_runner`;
  independent Python reference matches 100% on valid flags, checked counts, clean flags, violation
  lists, and error contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b49_parameter_tree_allowed_name_check.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b49-parameter-tree-allowed-name-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b49-parameter-tree-allowed-name-check-stage.v1.yaml`; source map
  `p4b-02b49-mit-source-map.v1.yaml`.
- PLAN **P4B-02b49**; ledger note/gate P4B-02; coverage gates 215 -> 216.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog (mechanism only, catalog is data), no
  defaults, no document decoding.
- Checks distinct leaf names only; branch names are not checked.
- No release certification, no acceptance evidence.
