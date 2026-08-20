# P4B-02b39 AMI Parameter Tree Leaf Value Set Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b39 (path-addressed typed leaf value set for an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_set_value_v1.rs` in `sipi-ami-text`: `set_parameter_tree_leaf_value_v1`
sets the value tokens of one leaf of an `AmiParameterTreeV1` (P4B-02b7), addressed by a canonical
path (`[root_name, ..., leaf_name]`), to a single new value token validated against the leaf's
declared type (caller-supplied type map keyed by leaf name) via the exact P4B-02b1
`AmiParameterValueV1::try_new` rules. Returns a new tree; the source tree is never mutated.
Fail-closed: empty path (`EmptyPath`), root mismatch (`RootMismatch`), unresolved segment
(`PathNotFound`), branch target (`TargetNotLeaf`), missing type (`MissingType`), invalid value
(`InvalidValue` wrapping the P4B-02b1 error), and invalid leaf name (`InvalidLeafName`) are strictly
rejected. An independent Python reference replicates the tokenize/build/resolve/set pipeline over
4 test cases.

## Result

- 9 Rust unit tests green (root-level set; nested set; source tree untouched; empty path; root
  mismatch; path not found; branch target; missing type; invalid value; invalid leaf name).
- Cross-check: 4 test cases (set float value, set nested value, missing type, invalid value for
  type) driven through product runner `p4b_02b39_parameter_tree_leaf_value_set_runner`; independent
  Python reference matches 100% on valid flags, root names, resulting tree structures, and error
  contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b39_parameter_tree_leaf_value_set.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b39-parameter-tree-leaf-value-set-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b39-parameter-tree-leaf-value-set-stage.v1.yaml`; source map
  `p4b-02b39-mit-source-map.v1.yaml`.
- PLAN **P4B-02b39**; ledger note/gate P4B-02; coverage gates 205 -> 206.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Sets exactly one value token (AMI single-value form); multi-token writes are not supported.
- No release certification, no acceptance evidence.
