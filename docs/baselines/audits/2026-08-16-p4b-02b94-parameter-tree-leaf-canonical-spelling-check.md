# P4B-02b94 Parameter Tree Leaf Canonical Spelling Check Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b94 (canonical leaf spelling check of an AmiParameterTreeV1)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_canonical_spelling_check_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_leaf_spellings_canonical_v1` checks whether every try_new-valid typed-form
leaf of an `AmiParameterTreeV1` already carries its canonical value spelling
(`canonicalize_parameter_value_spelling_v1`, 02b75): walks every leaf and, for leaves whose value
tokens are a well-formed typed form (exactly two tokens whose first token is a known type token)
whose value passes `AmiParameterValueV1::try_new` (02b1), compares the raw value token to its
canonical spelling (Integer `007` -> `7`, List item spacing normalization) and reports each
non-canonical leaf with its path, declared type, raw value, and canonical value. This is the pure
check companion of 02b78 tree leaf canonicalization (which rewrites) and the tree-level gate before
canonicalizing. Leaves that are not try_new-valid typed forms (non-typed forms, quoted List
spellings that fail raw try_new) are skipped. Fail-closed: the check is total (no error path);
non-canonical entries come back in deterministic sorted (path) order; `canonical()` is true exactly
when no non-canonical leaf was found. An independent Python reference replicates the check over 4
test cases.

## Result

- 6 Rust unit tests green (canonical tree, non-canonical integer, nested, quoted List skipped,
  invalid value skipped, mixed canonical/non-canonical).
- Cross-check: 4 test cases (canonical tree, non-canonical integer, nested, no typed) driven
  through product runner `p4b_02b94_parameter_tree_leaf_canonical_spelling_check_runner`;
  independent Python reference matches 100% on typed counts, canonical flags, and issue lists;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b94_parameter_tree_leaf_canonical_spelling_check.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b94-parameter-tree-leaf-canonical-spelling-check-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b94-parameter-tree-leaf-canonical-spelling-check-stage.v1.yaml`; source map
  `p4b-02b94-mit-source-map.v1.yaml`.
- PLAN **P4B-02b94**; ledger note/gate P4B-02; coverage gates 263 -> 264.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Checks canonical spelling of try_new-valid typed-form leaves only; others skipped.
- No release certification, no acceptance evidence.
