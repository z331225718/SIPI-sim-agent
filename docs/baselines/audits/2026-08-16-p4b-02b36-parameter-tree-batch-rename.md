# P4B-02b36 AMI Parameter Tree Batch Rename Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b36 (one-pass batch rename of leaves in an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_batch_rename_v1.rs` in `sipi-ami-text`: `rename_parameter_tree_leaves_v1`
renames leaves of an `AmiParameterTreeV1` (P4B-02b7) in one pass from a caller-supplied
old-name -> new-name map, returning a new tree under the same root name. Renaming is two-phase per
branch (remove renamed leaves, then insert them under their new names), so sibling swaps succeed.
Fail-closed: empty map (`EmptyRenameMap`), old name not a leaf (`MissingLeaf`), new name not a valid
tree identifier (`InvalidNewName`), and any rename creating same-named siblings in one branch
(`SiblingNameCollision`) are strictly rejected. New names follow the tree identifier rule; the
stricter parameter-name rule is enforced downstream by the typed-form gate (P4B-02b34). An independent
Python reference replicates the tokenize/build/rename pipeline over 4 test cases.

## Result

- 9 Rust unit tests green (batch rename; unrequested leaves unchanged; empty map; missing old name;
  invalid new name; sibling collision; sibling swap; same name at other depth is legal; nested rename
  keeps ancestor branches).
- Cross-check: 4 test cases (simple rename, sibling collision, missing leaf, sibling swap) driven
  through product runner `p4b_02b36_parameter_tree_batch_rename_runner`; independent Python reference
  matches 100% on valid flags, root names, renamed tree structures, and error contexts;
  4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b36_parameter_tree_batch_rename.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b36-parameter-tree-batch-rename-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b36-parameter-tree-batch-rename-stage.v1.yaml`; source map
  `p4b-02b36-mit-source-map.v1.yaml`.
- PLAN **P4B-02b36**; ledger note/gate P4B-02; coverage gates 202 -> 203.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Renames leaves only (not branches); path-based single rename lives in P4B-02b24.
- No release certification, no acceptance evidence.
