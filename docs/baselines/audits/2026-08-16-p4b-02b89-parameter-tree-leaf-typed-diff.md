# P4B-02b89 Parameter Tree Leaf Typed Diff Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b89 (typed leaf diff between two AmiParameterTreeV1 trees)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_typed_diff_v1.rs` in `sipi-ami-text`:
`diff_parameter_tree_leaves_typed_v1` diffs the leaves of two `AmiParameterTreeV1` trees at
matching canonical dot-separated paths under typed value semantics: leaves at the same path whose
value tokens are typed-equivalent (02b70, both leaves well-formed typed forms with valid values)
count as matched; typed-inequivalent leaves are reported as changed with both token lists and the
typed reason; leaves where either side is not a typed form fall back to raw token equality (matched
when tokens are byte-equal, changed with reason None otherwise); left-only paths are removed and
right-only paths are added. This is the tree-pair typed companion of 02b11 raw tree diff and of
02b79 profile typed diff, at leaf-path granularity. Fail-closed: the diff is total (no error path);
all lists come back in deterministic sorted (path) order. An independent Python reference replicates
the tree builds and leaf diff over 4 test cases.

## Result

- 6 Rust unit tests green (identical trees, spelling variants, added/removed paths, typed change
  with reason, raw fallback, nested changes by path).
- Cross-check: 4 test cases (identical, spelling variants, added/removed, typed changed) driven
  through product runner `p4b_02b89_parameter_tree_leaf_typed_diff_runner`; independent Python
  reference matches 100% on matched counts, sorted path lists, and changed entries with reasons;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b89_parameter_tree_leaf_typed_diff.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b89-parameter-tree-leaf-typed-diff-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b89-parameter-tree-leaf-typed-diff-stage.v1.yaml`; source map
  `p4b-02b89-mit-source-map.v1.yaml`.
- PLAN **P4B-02b89**; ledger note/gate P4B-02; coverage gates 258 -> 259.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Diffs validated trees only; typed equivalence via 02b70 with documented raw fallback.
- No release certification, no acceptance evidence.
