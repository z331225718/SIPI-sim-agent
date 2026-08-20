# P4B-02b93 Parameter Tree Typed-Leaf Type Counts Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b93 (typed-leaf type counts of an AmiParameterTreeV1)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_typed_leaf_type_counts_v1.rs` in `sipi-ami-text`:
`count_parameter_tree_typed_leaves_by_type_v1` counts the typed-form leaves of an
`AmiParameterTreeV1` by declared type: walks every leaf and counts those whose value tokens are a
well-formed typed form (exactly two tokens whose first token is a known type token
Float/Integer/Boolean/String/List) per declared type, plus skipped leaves (not typed forms). This
is the tree-level companion of 02b73 profile type statistics and the count view over 02b87's leaf
type map. Fail-closed: the counting is total (no error path); traversal is deterministic (sorted
children, canonical order); the per-type counts sum to `total_typed` and `total_typed + skipped`
equals the total leaf count. An independent Python reference replicates the tree build and
per-type counting over 4 test cases.

## Result

- 6 Rust unit tests green (each declared type, non-typed skipped, nested leaves, sum invariant,
  quoted List counted as List, tree without typed leaves).
- Cross-check: 4 test cases (typed forms, mixed skipped, nested, no typed) driven through product
  runner `p4b_02b93_parameter_tree_typed_leaf_type_counts_runner`; independent Python reference
  matches 100% on all per-type counts and skipped; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b93_parameter_tree_typed_leaf_type_counts.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b93-parameter-tree-typed-leaf-type-counts-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b93-parameter-tree-typed-leaf-type-counts-stage.v1.yaml`; source map
  `p4b-02b93-mit-source-map.v1.yaml`.
- PLAN **P4B-02b93**; ledger note/gate P4B-02; coverage gates 262 -> 263.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counts typed-form leaves by declared type only; non-typed leaves counted as skipped.
- No release certification, no acceptance evidence.
