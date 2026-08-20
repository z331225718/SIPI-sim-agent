# P4B-02b26 AMI Parameter Tree Subtree Compose Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b26 (AMI parameter tree subtree compose core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_compose_v1.rs` in `sipi-ami-text`: `compose_parameter_tree_subtree_v1`
composes a subtree node into a typed `AmiParameterTreeV1` hierarchy (P4B-02b7) at a dot-separated
canonical parent path, returning a new tree with the subtree attached. A path naming only the root
(`root`) attaches directly under the root branch; the resolved parent must be a branch.
Fail-closed: empty paths (`EmptyPath`), empty/invalid node names (`EmptyNodeName`, `InvalidNodeName`),
root-name mismatches (`RootMismatch`), missing parent path segments (`MissingPath`, canonical path),
or duplicate child names at the attachment point (`DuplicateChild`) are strictly rejected.
An independent Python reference recomputes subtree compose over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; composes leaf subtree under branch; composes subtree under
  nested branch; rejects leaf parent path; rejects duplicate child; rejects missing parent path).
- Cross-check: 3 test cases (compose leaf under root, compose leaf under nested branch, duplicate child)
  driven through product runner `p4b_02b26_parameter_tree_compose_runner`; independent Python reference
  matches 100% on valid flags, composed tree canonical JSON, and error strings; 3/3 product_owned_self_crosscheck_unbound.
- Fix in P4B-02b23 `extract_node` recursion (child descent kept the child name segment) validated by
  re-running the 02b23 crosscheck (still 3/3 product_owned_self_crosscheck_unbound).

## Binding

- Verifier `verify_p4b_02b26_parameter_tree_compose.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b26-parameter-tree-compose-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b26-parameter-tree-compose-stage.v1.yaml`; source map
  `p4b-02b26-mit-source-map.v1.yaml`.
- PLAN **P4B-02b26**; ledger note/gate P4B-02; coverage gates 192 -> 193.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
