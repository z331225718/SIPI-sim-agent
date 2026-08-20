# P4B-02b23 AMI Parameter Tree Subtree Extraction Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b23 (AMI parameter tree subtree extraction core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_subtree_v1.rs` in `sipi-ami-text`: `extract_parameter_tree_subtree_v1`
extracts the subtree rooted at a dot-separated canonical path inside a typed `AmiParameterTreeV1` hierarchy (P4B-02b7),
returning an owned clone of the subtree node.
Fail-closed: empty paths (`EmptyPath`), root-name mismatches (`RootMismatch`),
or missing path segments (`MissingPath`, reported with the canonical requested path) are strictly rejected.
An independent Python reference recomputes subtree extraction over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; extracts root subtree; extracts nested subtree;
  rejects empty path; rejects root mismatch; rejects missing path segment).
- Cross-check: 3 test cases (root subtree, nested subtree, missing path)
  driven through product runner `p4b_02b23_parameter_tree_subtree_runner`; independent Python reference
  matches 100% on valid flags, subtree canonical JSON, and error strings; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b23_parameter_tree_subtree.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b23-parameter-tree-subtree-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b23-parameter-tree-subtree-stage.v1.yaml`; source map
  `p4b-02b23-mit-source-map.v1.yaml`.
- PLAN **P4B-02b23**; ledger note/gate P4B-02; coverage gates 189 -> 190.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
