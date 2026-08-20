# P4B-02b16 AMI Parameter Tree Fast Leaf Path Index Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b16 (AMI parameter tree fast leaf path index core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_index_v1.rs` in `sipi-ami-text`: `build_parameter_tree_index_v1`
builds flat path-indexed lookup tables (`AmiParameterTreeIndexV1`) mapping full parameter paths
to value tokens from typed `AmiParameterTreeV1` hierarchies (P4B-02b7).
Fail-closed: empty tree lists (`EmptyTreeList`) or duplicate leaf paths (`DuplicateLeafPath`)
are strictly rejected. An independent Python reference recomputes flat path indexing over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; indexes tree leaves; rejects empty tree list).
- Cross-check: 3 test cases (standard tree indexing, nested branches indexing, empty document)
  driven through product runner `p4b_02b16_parameter_tree_index_runner`; independent Python reference
  matches 100% on valid flags, leaf counts, flat path index maps, and error strings; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b16_parameter_tree_index.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b16-parameter-tree-index-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b16-parameter-tree-index-stage.v1.yaml`; source map
  `p4b-02b16-mit-source-map.v1.yaml`.
- PLAN **P4B-02b16**; ledger note/gate P4B-02; coverage gates 142 -> 143.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
