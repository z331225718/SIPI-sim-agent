# P4B-02b66 Parameter Tree Relative Path Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b66 (relative path derivation w.r.t. an ancestor)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_relative_path_v1.rs` in `sipi-ami-text`: `relative_parameter_tree_path_v1`
derives the relative path of a canonical path with respect to one of its ancestors: the suffix
segments after the ancestor prefix. This is the subtree-relative primitive (e.g. addressing inside
an extracted subtree, P4B-02b23). Fail-closed: an empty path (`EmptyPath`), an ancestor that is not
a proper prefix of the path (`NotAncestor`), and an equal path (`EmptySuffix`) are strictly
rejected. An independent Python reference replicates the suffix derivation over 4 test cases.

## Result

- 6 Rust unit tests green (simple suffix; multi-segment suffix; equal paths; non-ancestor; empty
  path; longer ancestor).
- Cross-check: 4 test cases (simple suffix, multi suffix, equal paths, non-ancestor) driven through
  product runner `p4b_02b66_parameter_tree_relative_path_runner`; independent Python reference
  matches 100% on valid flags, relative segments, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b66_parameter_tree_relative_path.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b66-parameter-tree-relative-path-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b66-parameter-tree-relative-path-stage.v1.yaml`; source map
  `p4b-02b66-mit-source-map.v1.yaml`.
- PLAN **P4B-02b66**; ledger note/gate P4B-02; coverage gates 235 -> 236.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Derivation only; no resolution against a tree.
- No release certification, no acceptance evidence.
