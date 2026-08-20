# P4B-02b12 AMI Parameter Tree Structural Merge Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b12 (AMI parameter tree structural merge core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_merge_v1.rs` in `sipi-ami-text`: `merge_parameter_trees_v1`
merges two typed `AmiParameterTreeV1` hierarchies (P4B-02b7) into a unified tree, where right-side
branch nodes augment left-side branches and right-side leaf nodes override left-side leaves.
Fail-closed: root node name mismatch (`RootMismatch`) or node kind conflict (`KindConflict`)
are strictly rejected. An independent Python reference recomputes tree structural merge rules over 3 test cases.

## Result

- 4 Rust unit tests green (policy fixed; merges complementary branches and overrides leaves;
  rejects kind conflict; rejects root mismatch).
- Cross-check: 3 test cases (complementary and override, kind conflict, root mismatch)
  driven through product runner `p4b_02b12_parameter_tree_merge_runner`; independent Python reference
  matches 100% on valid flags, merged S-expression formatted text, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b12_parameter_tree_merge.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b12-parameter-tree-merge-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b12-parameter-tree-merge-stage.v1.yaml`; source map
  `p4b-02b12-mit-source-map.v1.yaml`.
- PLAN **P4B-02b12**; ledger note/gate P4B-02; coverage gates 138 -> 139.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
