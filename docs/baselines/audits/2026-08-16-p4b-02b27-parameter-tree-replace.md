# P4B-02b27 AMI Parameter Tree Node Replace Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b27 (AMI parameter tree node replace core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_replace_v1.rs` in `sipi-ami-text`: `replace_parameter_tree_node_v1`
replaces the node rooted at a dot-separated canonical path inside a typed `AmiParameterTreeV1` hierarchy (P4B-02b7)
with a replacement subtree node, returning a new tree.
Fail-closed: empty paths (`EmptyPath`), root replacement (`RootReplaceForbidden`),
empty/invalid replacement names (`EmptyNodeName`, `InvalidNodeName`), root-name mismatches (`RootMismatch`),
missing path segments (`MissingPath`, canonical path), or replacement-name collisions with a sibling
(`SiblingNameCollision`) are strictly rejected.
An independent Python reference recomputes node replace over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; replaces leaf node; replaces branch node;
  rejects root replace; rejects sibling name collision; rejects missing path).
- Cross-check: 3 test cases (replace leaf node, replace branch node, sibling name collision)
  driven through product runner `p4b_02b27_parameter_tree_replace_runner`; independent Python reference
  matches 100% on valid flags, replaced tree canonical JSON, and error strings; 3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b27_parameter_tree_replace.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b27-parameter-tree-replace-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b27-parameter-tree-replace-stage.v1.yaml`; source map
  `p4b-02b27-mit-source-map.v1.yaml`.
- PLAN **P4B-02b27**; ledger note/gate P4B-02; coverage gates 193 -> 194.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
