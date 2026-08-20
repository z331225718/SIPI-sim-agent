# P4B-02b91 Parameter Tree Leaf Value Validity Report Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b91 (declared-type value validity report over an AmiParameterTreeV1)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_value_validity_v1.rs` in `sipi-ami-text`:
`check_parameter_tree_leaf_value_validity_v1` reports the value validity of every typed-form leaf
of an `AmiParameterTreeV1` using the document's own declared types: walks every leaf and, for
leaves whose value tokens are a well-formed typed form (exactly two tokens whose first token is a
known type token Float/Integer/Boolean/String/List), validates the value token via
`AmiParameterValueV1::try_new` (02b1) and reports each invalid leaf with its canonical path,
declared type token, value token, and typed error. This is the declared-type companion of 02b32
value validation (which needs an external name -> type map) and the value-semantics complement of
02b58 typed-form conformance (form shape). Leaves that are not typed forms are skipped (no declared
type to validate against) and counted separately. Note: quoted List spellings fail raw try_new (a
List token must start with an open paren per 02b1; quotes are kept raw per 02b0). Fail-closed: the
report is total (no error path); issues come back in deterministic sorted (canonical traversal)
order; `valid()` is true exactly when no invalid leaf was found. An independent Python reference
replicates the tree build and validation over 4 test cases.

## Result

- 6 Rust unit tests green (all valid, invalid with error, non-typed skipped, nested paths, mixed
  valid/invalid including quoted-List invalidity, unknown type token not typed).
- Cross-check: 4 test cases (all valid, mixed invalid, nested, non-typed skipped) driven through
  product runner `p4b_02b91_parameter_tree_leaf_value_validity_runner`; independent Python
  reference matches 100% on counts and invalid issue lists (path/type/value/error); 4/4
  matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b91_parameter_tree_leaf_value_validity.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b91-parameter-tree-leaf-value-validity-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b91-parameter-tree-leaf-value-validity-stage.v1.yaml`; source map
  `p4b-02b91-mit-source-map.v1.yaml`.
- PLAN **P4B-02b91**; ledger note/gate P4B-02; coverage gates 260 -> 261.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Validates typed-form values via raw 02b1 rules; non-typed leaves skipped, not rejected.
- No release certification, no acceptance evidence.
