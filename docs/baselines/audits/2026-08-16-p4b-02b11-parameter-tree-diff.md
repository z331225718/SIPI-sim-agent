# P4B-02b11 AMI Parameter Tree Structural Comparison Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b11 (AMI parameter tree structural comparison & diff core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_diff_v1.rs` in `sipi-ami-text`: `diff_parameter_trees_v1`
compares two typed `AmiParameterTreeV1` hierarchies (P4B-02b7) and yields atomic structural differences:
`MissingNode { path }`, `ExtraNode { path }`, `KindMismatch { path }`, and `ValueMismatch { path, left, right }`.
Fail-closed: root node name mismatch (`RootMismatch`) is strictly rejected. An independent Python reference recomputes tree structural diff rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; diffs identical trees as empty; detects missing and extra nodes;
  detects value and kind mismatches; rejects root mismatch).
- Cross-check: 3 test cases (identical trees, missing and extra nodes, root mismatch)
  driven through product runner `p4b_02b11_parameter_tree_diff_runner`; independent Python reference
  matches 100% on valid flags, diff counts, structural diff items, and error strings; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b11_parameter_tree_diff.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b11-parameter-tree-diff-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b11-parameter-tree-diff-stage.v1.yaml`; source map
  `p4b-02b11-mit-source-map.v1.yaml`.
- PLAN **P4B-02b11**; ledger note/gate P4B-02; coverage gates 137 -> 138.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
