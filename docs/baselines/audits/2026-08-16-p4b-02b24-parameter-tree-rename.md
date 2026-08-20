# P4B-02b24 AMI Parameter Tree Node Rename Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b24 (AMI parameter tree node rename core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_rename_v1.rs` in `sipi-ami-text`: `rename_parameter_tree_node_v1`
renames the node rooted at a dot-separated canonical path inside a typed `AmiParameterTreeV1` hierarchy (P4B-02b7),
returning a new tree with the renamed node (map keys follow node names).
Fail-closed: empty paths (`EmptyPath`), root renames (`RootRenameForbidden`),
invalid new names (`EmptyNewName`, `InvalidNewName`), root-name mismatches (`RootMismatch`),
or missing path segments (`MissingPath`, reported with the canonical requested path) are strictly rejected.
An independent Python reference recomputes node rename over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; renames leaf node; renames branch node;
  rejects root rename; rejects invalid new name; rejects missing path).
- Cross-check: 3 test cases (rename leaf node, rename branch node, root rename forbidden)
  driven through product runner `p4b_02b24_parameter_tree_rename_runner`; independent Python reference
  matches 100% on valid flags, renamed tree canonical JSON, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b24_parameter_tree_rename.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b24-parameter-tree-rename-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b24-parameter-tree-rename-stage.v1.yaml`; source map
  `p4b-02b24-mit-source-map.v1.yaml`.
- PLAN **P4B-02b24**; ledger note/gate P4B-02; coverage gates 190 -> 191.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
