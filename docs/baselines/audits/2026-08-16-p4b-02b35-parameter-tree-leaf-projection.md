# P4B-02b35 AMI Parameter Tree Leaf Projection Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b35 (leaf projection of an AMI parameter tree onto a name set)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_project_v1.rs` in `sipi-ami-text`: `project_parameter_tree_leaves_v1`
projects an `AmiParameterTreeV1` (P4B-02b7) onto a caller-supplied `BTreeSet<String>` of leaf names,
returning a new tree that keeps exactly the requested leaves together with their ancestor branches,
under the same root name. Fail-closed: an empty selection (`EmptySelection`) and any requested name
that is not a leaf in the tree (`MissingLeaf`, covering absent names and branch-only names) are
strictly rejected. An independent Python reference replicates the tokenize/build/project pipeline
over 4 test cases.

## Result

- 6 Rust unit tests green (subset projection; nested leaf with ancestor branches; full projection
  identical tree; empty selection; missing leaf; branch name is not a leaf).
- Cross-check: 4 test cases (subset projection, nested projection, empty selection, missing leaf)
  driven through product runner `p4b_02b35_parameter_tree_leaf_projection_runner`; independent
  Python reference matches 100% on valid flags, root names, projected tree structures, and error
  contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b35_parameter_tree_leaf_projection.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b35-parameter-tree-leaf-projection-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b35-parameter-tree-leaf-projection-stage.v1.yaml`; source map
  `p4b-02b35-mit-source-map.v1.yaml`.
- PLAN **P4B-02b35**; ledger note/gate P4B-02; coverage gates 201 -> 202.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Projection is by leaf name only; no path-based or predicate-based selection (P4B-02b13/02b18).
- No release certification, no acceptance evidence.
