# P4B-02b54 AMI Parameter Tree Duplicate-Name Consistency Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b54 (cross-depth duplicate-name consistency classification)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_duplicate_check_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_duplicate_consistency_v1` checks every leaf name occurring at more than one
depth of an `AmiParameterTreeV1` (P4B-02b7) for value-token consistency: a duplicated name is
consistent when all its occurrences carry identical value tokens, inconsistent otherwise. The result
carries the total leaf occurrences checked, the number of duplicated names, and the sorted
consistent/inconsistent name lists. This is the inspection companion of the duplicate-rejecting
slices (P4B-02b33/02b34/02b37): it reports the situation before those slices fail. The check reports
in the result; an inconsistent tree is not itself an error. Result-based: any tree can be checked.
An independent Python reference replicates the tokenize/build/classify pipeline over 4 test cases.

## Result

- 4 Rust unit tests green (consistent duplicates; inconsistent duplicates; unique names; mixed
  consistency split).
- Cross-check: 4 test cases (consistent, inconsistent, unique, mixed) driven through product
  runner `p4b_02b54_parameter_tree_duplicate_check_runner`; independent Python reference matches
  100% on valid flags and all four report fields; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b54_parameter_tree_duplicate_check.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b54-parameter-tree-duplicate-consistency-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b54-parameter-tree-duplicate-consistency-check-stage.v1.yaml`; source map
  `p4b-02b54-mit-source-map.v1.yaml`.
- PLAN **P4B-02b54**; ledger note/gate P4B-02; coverage gates 220 -> 221.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Classifies by name only; no resolution of which occurrence is authoritative.
- No release certification, no acceptance evidence.
