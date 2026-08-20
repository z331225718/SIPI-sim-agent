# P4B-02b67 Parameter Tree Longest Common Prefix Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b67 (longest common prefix of two canonical paths)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_longest_common_prefix_v1.rs` in `sipi-ami-text`:
`longest_common_path_prefix_v1` computes the longest common prefix of two canonical paths
(`[root_name, ...]`) of an `AmiParameterTreeV1` (P4B-02b7): the leading segments shared by both
paths. This is the common-ancestor primitive for diff/compose and path algebra. Fail-closed: an
empty path (`EmptyPath`) is strictly rejected; a totally disjoint pair yields an empty prefix (a
valid result). An independent Python reference replicates the shared-prefix computation over
4 test cases.

## Result

- 5 Rust unit tests green (shared prefix; identical paths full prefix; disjoint empty prefix;
  one path contained; empty path fails closed).
- Cross-check: 4 test cases (shared prefix, identical, disjoint, empty) driven through product
  runner `p4b_02b67_parameter_tree_longest_common_prefix_runner`; independent Python reference
  matches 100% on valid flags, prefix segments, and error contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b67_parameter_tree_longest_common_prefix.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b67-parameter-tree-longest-common-prefix-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b67-parameter-tree-longest-common-prefix-stage.v1.yaml`; source map
  `p4b-02b67-mit-source-map.v1.yaml`.
- PLAN **P4B-02b67**; ledger note/gate P4B-02; coverage gates 236 -> 237.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Computation only; no resolution against a tree.
- No release certification, no acceptance evidence.
