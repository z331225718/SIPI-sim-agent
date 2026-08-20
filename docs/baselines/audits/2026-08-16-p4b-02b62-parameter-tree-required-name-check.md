# P4B-02b62 Parameter Tree Required-Name Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b62 (required-name leaf presence check on an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_required_check_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_required_names_v1` checks every caller-supplied required name against an
`AmiParameterTreeV1` (P4B-02b7): a required name is present when it occurs as a leaf anywhere in the
tree; the check reports required/present counts, the sorted missing names, and a completeness flag.
This is the tree-level counterpart of the profile-level completeness check (P4B-02b55) and completes
the name-policy trio with the reserved blacklist (P4B-02b43) and the allowed whitelist
(P4B-02b49): forbidden / allowed / required. The check reports in the result; an incomplete tree is
not itself an error. Fail-closed: an empty required-name set (`EmptyRequired`) is strictly rejected.
An independent Python reference replicates the tokenize/build/presence pipeline over 4 test cases.

## Result

- 4 Rust unit tests green (all required present; missing names sorted; nested leaves satisfy
  required; empty required fails closed).
- Cross-check: 4 test cases (complete, missing sorted, nested satisfies, empty required) driven
  through product runner `p4b_02b62_parameter_tree_required_name_check_runner`; independent Python
  reference matches 100% on valid flags, counts, missing lists, and error contexts;
  4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b62_parameter_tree_required_name_check.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b62-parameter-tree-required-name-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b62-parameter-tree-required-name-check-stage.v1.yaml`; source map
  `p4b-02b62-mit-source-map.v1.yaml`.
- PLAN **P4B-02b62**; ledger note/gate P4B-02; coverage gates 231 -> 232.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Presence check only; no value or type semantics.
- No release certification, no acceptance evidence.
