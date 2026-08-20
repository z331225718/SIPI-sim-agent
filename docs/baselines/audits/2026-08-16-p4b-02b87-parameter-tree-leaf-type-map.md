# P4B-02b87 Parameter Tree Leaf Declared-Type Map Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b87 (declared-type inventory of an AmiParameterTreeV1)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_type_map_v1.rs` in `sipi-ami-text`:
`extract_parameter_tree_leaf_type_map_v1` extracts the declared-type inventory of an
`AmiParameterTreeV1`: walks every leaf and, for leaves whose value tokens are a well-formed typed
form (exactly two tokens whose first token is a known type token Float/Integer/Boolean/String/List),
records leaf name -> declared type in a map. This is the declared-type companion of 02b33 type
inference (which guesses types from values) and builds exactly the name -> type map that 02b37 leaf
decoding consumes. Leaves that are not typed forms (single-token, multi-token, unknown type token)
are counted as skipped, not rejected: the map carries only what the document declares.
Fail-closed: the extraction is total (no error path); traversal is deterministic (sorted children,
canonical order); a leaf name appearing at multiple depths takes its last canonical occurrence
(document; duplicate consistency is 02b54's concern). An independent Python reference replicates
the tree build and extraction over 4 test cases.

## Result

- 6 Rust unit tests green (typed form types, non-typed skipped, nested leaves, duplicate last
  occurrence, mixed counts, tree without typed leaves).
- Cross-check: 4 test cases (typed forms, mixed skipped, nested, duplicate) driven through product
  runner `p4b_02b87_parameter_tree_leaf_type_map_runner`; independent Python reference matches
  100% on type maps and all counts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b87_parameter_tree_leaf_type_map.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b87-parameter-tree-leaf-type-map-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b87-parameter-tree-leaf-type-map-stage.v1.yaml`; source map
  `p4b-02b87-mit-source-map.v1.yaml`.
- PLAN **P4B-02b87**; ledger note/gate P4B-02; coverage gates 256 -> 257.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Records declared types only; non-typed leaves are skipped, not rejected.
- No release certification, no acceptance evidence.
