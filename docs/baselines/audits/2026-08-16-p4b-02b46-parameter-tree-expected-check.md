# P4B-02b46 AMI Parameter Tree Expected-Value Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b46 (golden/regression expected-value check for an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_expected_check_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_against_expected_v1` checks an `AmiParameterTreeV1` (P4B-02b7) against a
caller-supplied expected map (leaf name -> expected value tokens): reports expected names missing
from the tree (sorted) and names whose value tokens differ (`ParameterTreeValueMismatchV1` with
name/expected/actual, sorted by name), plus expected/matched counts. Extra tree leaves not in the
expected map are ignored — the check is one-directional (does the tree match the expectation).
Fail-closed: an empty expected map (`EmptyExpected`) and a leaf name occurring at more than one
depth (`DuplicateLeaf`, uncheckable unambiguously) are strictly rejected. An independent Python
reference replicates the tokenize/build/compare pipeline over 4 test cases.

## Result

- 6 Rust unit tests green (full match; missing names reported; token mismatch reported; extra
  leaves ignored; empty expected; duplicate leaf name).
- Cross-check: 4 test cases (full match, missing and mismatch, extra leaf ignored, empty expected)
  driven through product runner `p4b_02b46_parameter_tree_expected_check_runner`; independent
  Python reference matches 100% on valid flags, counts, missing lists, mismatch records, and error
  contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b46_parameter_tree_expected_check.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b46-parameter-tree-expected-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b46-parameter-tree-expected-check-stage.v1.yaml`; source map
  `p4b-02b46-mit-source-map.v1.yaml`.
- PLAN **P4B-02b46**; ledger note/gate P4B-02; coverage gates 212 -> 213.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- One-directional: extra tree leaves are not errors; expected names drive the report.
- No release certification, no acceptance evidence.
