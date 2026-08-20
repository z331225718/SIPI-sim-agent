# P4B-02b30 AMI Parameter Tree Leaf Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b30 (AMI parameter tree leaf index core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_index_v1.rs` in `sipi-ami-text`: `build_parameter_tree_leaf_index_v1`
builds a canonical-path index of leaf nodes inside a typed `AmiParameterTreeV1` hierarchy (P4B-02b7),
and `ParameterTreeLeafIndexV1::resolve_leaf` resolves canonical leaf paths to their value token lists.
Fail-closed: empty tree lists (`EmptyTreeList`), empty leaf paths (`EmptyLeafPath`),
branch paths resolved as leaves (`LeafPathNotLeaf`), or missing leaf paths (`MissingLeafPath`)
are strictly rejected. An independent Python reference recomputes the leaf index over 3 test cases.

## Result

- 4 Rust unit tests green (policy fixed; builds leaf index and resolves; rejects branch path;
  rejects missing leaf path).
- Cross-check: 3 test cases (leaf index resolve, branch path rejected, missing leaf path)
  driven through product runner `p4b_02b30_parameter_tree_leaf_index_runner`; independent Python reference
  matches 100% on valid flags, leaf counts, leaf path lists, resolution results, and error strings; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b30_parameter_tree_leaf_index.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b30-parameter-tree-leaf-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b30-parameter-tree-leaf-index-stage.v1.yaml`; source map
  `p4b-02b30-mit-source-map.v1.yaml`.
- PLAN **P4B-02b30**; ledger note/gate P4B-02; coverage gates 196 -> 197.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
