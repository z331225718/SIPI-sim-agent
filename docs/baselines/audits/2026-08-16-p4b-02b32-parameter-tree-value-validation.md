# P4B-02b32 AMI Parameter Tree Leaf Value Validation Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b32 (typed validation of all leaf value tokens in an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_validate_values_v1.rs` in `sipi-ami-text`: `validate_parameter_tree_values_v1`
walks an `AmiParameterTreeV1` (P4B-02b7) and validates every leaf value token against a caller-supplied
type map (leaf name -> `AmiParameterTypeV1`), reusing the exact product-owned rules of
`AmiParameterValueV1::try_new` (P4B-02b1) per token. Fail-closed: leaves without a declared type
(`MissingType`), leaves with no value tokens (`EmptyValueTokens`), invalid leaf names (`InvalidLeafName`),
and any token violating its type rule (Float/Integer/Boolean/String/List) are strictly rejected with
leaf+token context. An independent Python reference replicates the tree build and the value rules over
4 test cases.

## Result

- 9 Rust unit tests green (mixed types; nested branches; missing type; invalid float/integer/boolean;
  empty tokens; List rule incl. valid list token; invalid leaf name).
- Cross-check: 4 test cases (mixed valid types, missing type fails closed, invalid float token,
  invalid boolean token) driven through product runner `p4b_02b32_parameter_tree_value_validation_runner`;
  independent Python reference matches 100% on valid flags, counts, echoed type maps, and error contexts;
  4/4 matched_hash_bound.

## Binding

- Verifier `verify_p4b_02b32_parameter_tree_value_validation.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b32-parameter-tree-value-validation-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b32-parameter-tree-value-validation-stage.v1.yaml`; source map
  `p4b-02b32-mit-source-map.v1.yaml`.
- PLAN **P4B-02b32**; ledger note/gate P4B-02; coverage gates 198 -> 199.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Type map is caller-supplied; no inference of types.
- No release certification, no acceptance evidence.
