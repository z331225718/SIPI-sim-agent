# P4B-02b59 Parameter Tree Leaf Occurrence Counts Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b59 (leaf name occurrence counts of an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_occurrences_v1.rs` in `sipi-ami-text`:
`count_parameter_tree_leaf_occurrences_v1` counts the occurrences of every leaf name of an
`AmiParameterTreeV1` (P4B-02b7), producing the name -> count landscape (including cross-depth
duplicates) plus the total leaf count. This is the direct input view for ambiguity-protected
name-addressed operations (P4B-02b53) and the duplicate-name landscape companion of the consistency
check (P4B-02b54). Result-based: any tree can be counted. An independent Python reference replicates
the tokenize/build/count pipeline over 4 test cases.

## Result

- 4 Rust unit tests green (cross-depth duplicates; unique names; root-leaf tree; deep nesting
  counts only leaves).
- Cross-check: 4 test cases (cross-depth duplicates, unique names, root leaf, deep nesting) driven
  through product runner `p4b_02b59_parameter_tree_leaf_occurrences_runner`; independent Python
  reference matches 100% on valid flags, total counts, and occurrence maps; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b59_parameter_tree_leaf_occurrences.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b59-parameter-tree-leaf-occurrences-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b59-parameter-tree-leaf-occurrences-stage.v1.yaml`; source map
  `p4b-02b59-mit-source-map.v1.yaml`.
- PLAN **P4B-02b59**; ledger note/gate P4B-02; coverage gates 228 -> 229.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Counting only; no consistency classification (P4B-02b54) or ambiguity rejection (P4B-02b53).
- No release certification, no acceptance evidence.
