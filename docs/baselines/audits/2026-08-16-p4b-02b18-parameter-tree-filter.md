# P4B-02b18 AMI Parameter Tree Predicate Filtering Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b18 (AMI parameter tree predicate filtering core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_filter_v1.rs` in `sipi-ami-text`: `filter_parameter_trees_v1`
filters typed `AmiParameterTreeV1` hierarchies (P4B-02b7) by applying predicate closures
over node path and node properties.
Fail-closed: empty tree lists (`EmptyTreeList`) or empty filtered tree result (`EmptyFilteredResult`)
are strictly rejected. An independent Python reference recomputes tree predicate filtering rules over 3 test cases.

## Result

- 4 Rust unit tests green (policy fixed; filters tree by path predicate; rejects empty tree list;
  rejects empty filtered result).
- Cross-check: 3 test cases (filter leaf node, filter branch node, empty document)
  driven through product runner `p4b_02b18_parameter_tree_filter_runner`; independent Python reference
  matches 100% on valid flags, filtered S-expression formatted text, and error strings; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b18_parameter_tree_filter.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b18-parameter-tree-filter-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b18-parameter-tree-filter-stage.v1.yaml`; source map
  `p4b-02b18-mit-source-map.v1.yaml`.
- PLAN **P4B-02b18**; ledger note/gate P4B-02; coverage gates 146 -> 147.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
