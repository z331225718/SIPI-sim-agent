# P4B-02b42 AMI Parameter Tree Multi-Tree Typed-Form Extraction Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b42 (profile-shaped multi-tree typed-form extraction)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_typed_form_multi_v1.rs` in `sipi-ami-text`:
`extract_typed_parameter_forms_multi_v1` extracts typed `AmiParameterValueV1` entries from every
tree of a tree list (each tree in `(name Type value)` leaf form, per the P4B-02b34 rules, reused
verbatim per tree) and merges them into one name-keyed map. This is the profile-shaped consumption
path: an AMI profile consists of multiple parameter trees. Fail-closed: an empty tree list
(`EmptyTreeList`), any per-tree typed-form violation wrapped with the tree index (`TreeError`), and
a parameter name appearing in more than one tree (`DuplicateAcrossTrees`) are strictly rejected.
An independent Python reference replicates the tokenize/build/extract/merge pipeline over 4 test
cases.

## Result

- 5 Rust unit tests green (merge across trees; duplicate across trees; empty tree list; per-tree
  error wrapped with index; nested leaves in later trees extracted).
- Cross-check: 4 test cases (two trees merge, duplicate across trees, error in second tree, empty
  list) driven through product runner `p4b_02b42_parameter_tree_typed_form_multi_runner`;
  independent Python reference matches 100% on valid flags, consumed counts, merged parameter
  maps, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b42_parameter_tree_typed_form_multi.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b42-parameter-tree-typed-form-multi-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b42-parameter-tree-typed-form-multi-stage.v1.yaml`; source map
  `p4b-02b42-mit-source-map.v1.yaml`.
- PLAN **P4B-02b42**; ledger note/gate P4B-02; coverage gates 208 -> 209.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Merges by leaf name; same-name leaves in different trees are rejected rather than overridden.
- No release certification, no acceptance evidence.
