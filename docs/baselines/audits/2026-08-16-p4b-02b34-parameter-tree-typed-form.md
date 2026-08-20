# P4B-02b34 AMI Parameter Tree Typed-Form Extraction Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b34 (typed-form extraction from an AMI parameter tree)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_tree_typed_form_v1.rs` in `sipi-ami-text`: `extract_typed_parameter_forms_v1`
walks an `AmiParameterTreeV1` (P4B-02b7) and requires every leaf to be an AMI parameter form
`(name Type value)` — exactly two value tokens: a type token and one value token — producing typed
`AmiParameterValueV1` entries (P4B-02b1) keyed by name. This is the tree-level counterpart of the
AST scanner (P4B-02b6) and the bridge a profile feed consumes. Fail-closed: empty value tokens
(`EmptyValueTokens`), single-token leaves (`NotTypedForm`), multi-token leaves (`MultiTokenForm` with
token count), unknown type tokens (`UnknownTypeToken`), values violating their type rule
(`InvalidValue` wrapping the P4B-02b1 error), invalid parameter names (`InvalidParameterName`), and
duplicate parameter names (`DuplicateParameter`) are strictly rejected. An independent Python
reference replicates the tokenize/build/extract pipeline over 4 test cases.

## Result

- 8 Rust unit tests green (valid typed leaves; multi-token form; single token; empty tokens;
  unknown type token; invalid value for type; invalid parameter name; duplicate names across depths).
- Cross-check: 4 test cases (valid typed tree, multi-token form, unknown type token, invalid value
  for type) driven through product runner `p4b_02b34_parameter_tree_typed_form_runner`; independent
  Python reference matches 100% on valid flags, consumed counts, parameter maps, and error contexts;
  4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b34_parameter_tree_typed_form.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b34-parameter-tree-typed-form-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b34-parameter-tree-typed-form-stage.v1.yaml`; source map
  `p4b-02b34-mit-source-map.v1.yaml`.
- PLAN **P4B-02b34**; ledger note/gate P4B-02; coverage gates 200 -> 201.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Every leaf must be a typed form; untyped trees are handled by P4B-02b33 inference instead.
- No release certification, no acceptance evidence.
