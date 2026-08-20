# P4B-02b17 AMI Parameter Tree Structural Diff Patch Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b17 (AMI parameter tree structural diff patch & application core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_diff_patch_v1.rs` in `sipi-ami-text`: `apply_parameter_tree_diff_patch_v1`
and `apply_parameter_tree_diff_patch_with_context_v1` apply atomic `TreeDiffEntryV1` entries (P4B-02b11) to a typed `AmiParameterTreeV1`
hierarchy (P4B-02b7).
Fail-closed: empty diff lists (`EmptyDiffList`), invalid target paths (`InvalidPath`), or node kind mismatches
(`NodeKindMismatch`) are strictly rejected. An independent Python reference recomputes diff patch application over 3 test cases.

## Result

- 3 Rust unit tests green (policy fixed; applies value mismatch patch; rejects empty diff list).
- Cross-check: 3 test cases (value mismatch patch, structural node patch, empty left document)
  driven through product runner `p4b_02b17_parameter_tree_diff_patch_runner`; independent Python reference
  matches 100% on valid flags, patched S-expression formatted text, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b17_parameter_tree_diff_patch.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b17-parameter-tree-diff-patch-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b17-parameter-tree-diff-patch-stage.v1.yaml`; source map
  `p4b-02b17-mit-source-map.v1.yaml`.
- PLAN **P4B-02b17**; ledger note/gate P4B-02; coverage gates 145 -> 146.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
