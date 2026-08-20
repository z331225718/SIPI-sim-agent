# P4B-02b78 Parameter Tree Leaf Canonicalization Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b78 (canonical leaf spellings of an AmiParameterTreeV1)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_leaf_canonicalization_v1.rs` in `sipi-ami-text`:
`canonicalize_parameter_tree_leaf_spellings_v1` produces the canonical form of an
`AmiParameterTreeV1` by applying `canonicalize_parameter_value_spelling_v1` (02b75) to every leaf
that is a well-formed typed parameter form: value token lists of exactly two tokens whose first
token is a known type token (Float/Integer/Boolean/String/List) and whose value passes
`AmiParameterValueV1::try_new` (02b1). Integer spellings become the parsed i64 in decimal
(`007` -> `7`), List spellings get trimmed items joined with `", "` (`(a,b,c)` ->
`(a, b, c)`), Boolean/Float/String stay raw. List values in tree text are quoted tokens (P4B-02b0
raw-byte binding: quotes structural, inner spelling is the value); the canonical List spelling
keeps the quotes. All other leaves (non-typed forms, multi-token leaves, invalid values) are left
untouched. Tree-level companion of 02b75 (value) and 02b77 (profile). Fail-closed: total (no error
path); only valid typed-form leaves are rewritten; canonicalized count reports how many leaves
changed. An independent Python reference replicates the tree build and canonical rules over 4 test
cases.

## Result

- 6 Rust unit tests green (typed integer leaf, typed quoted-list leaf, float/string/boolean raw,
  non-typed and invalid leaves untouched, nested levels, structure preservation).
- Cross-check: 4 test cases (integer+list, raw types, mixed nested, invalid untouched) driven
  through product runner `p4b_02b78_parameter_tree_leaf_canonicalization_runner`; independent
  Python reference matches 100% on leaves/canonicalized counts and canonical trees; 4/4
  product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b78_parameter_tree_leaf_canonicalization.py` + 6 tests; crosscheck
  evidence `docs/baselines/p4b-02b78-parameter-tree-leaf-canonicalization-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b78-parameter-tree-leaf-canonicalization-stage.v1.yaml`; source map
  `p4b-02b78-mit-source-map.v1.yaml`.
- PLAN **P4B-02b78**; ledger note/gate P4B-02; coverage gates 247 -> 248.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Canonicalizes valid typed-form Integer/List leaves only; Float and String stay raw; non-typed,
  multi-token, and invalid leaves untouched.
- No release certification, no acceptance evidence.
