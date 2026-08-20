# P4B-02b63 Parameter Tree Distinct Leaf Names Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b63 (sorted distinct leaf name enumeration)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_distinct_leaf_names_v1.rs` in `sipi-ami-text`:
`list_parameter_tree_distinct_leaf_names_v1` enumerates the distinct leaf names of an
`AmiParameterTreeV1` (P4B-02b7) sorted byte-wise, deduplicated across depths. This is the
name-view companion of the occurrence counts (P4B-02b59) and the direct input for the name-policy
checks (P4B-02b43/02b49/02b62). Result-based: any tree can be enumerated (including root-leaf
trees; branch-only trees yield an empty list). An independent Python reference replicates the
tokenize/build/enumerate pipeline over 4 test cases.

## Result

- 4 Rust unit tests green (cross-depth dedup; byte-wise sort; root-leaf tree; branch-only tree).
- Cross-check: 4 test cases (cross-depth dedup, sorted names, root leaf, branch only) driven
  through product runner `p4b_02b63_parameter_tree_distinct_leaf_names_runner`; independent Python
  reference matches 100% on valid flags, distinct counts, and name lists; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b63_parameter_tree_distinct_leaf_names.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b63-parameter-tree-distinct-leaf-names-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b63-parameter-tree-distinct-leaf-names-stage.v1.yaml`; source map
  `p4b-02b63-mit-source-map.v1.yaml`.
- PLAN **P4B-02b63**; ledger note/gate P4B-02; coverage gates 232 -> 233.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Name enumeration only; no counts (P4B-02b59) or policy classification.
- No release certification, no acceptance evidence.
