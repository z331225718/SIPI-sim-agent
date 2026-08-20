# P4B-02b6 AMI Text Document Parameter Extractor Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b6 (AMI text document parameter extractor core)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `parameter_extractor_v1.rs` in `sipi-ami-text`: `extract_parameter_values_v1`
scans structural `AmiTextDocumentV1` AST forms for 3-item parameter list triples
`(name, type_token, value_token)` and lifts them into typed `AmiParameterValueV1` objects
in a `BTreeMap<String, AmiParameterValueV1>`.
Fail-closed: empty documents (`EmptyDocument`), duplicate parameter names (`DuplicateParameter`),
no 3-item parameter forms found (`NoValidParameters`), or invalid value syntax (`InvalidValue`)
are strictly rejected. An independent Python reference recomputes the AST parameter extraction rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; extracts valid triples; empty document rejection;
  no valid parameters rejection; duplicate parameter rejection; invalid value syntax rejection).
- Cross-check: 3 test cases (valid 3-parameter document, nested document, duplicate parameter name)
  driven through product runner `p4b_02b6_parameter_extractor_runner`; independent Python reference
  matches 100% on valid flags, parameter counts, parameter types/values, and error strings;
  3/3 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b6_parameter_extractor.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b6-parameter-extractor-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b6-parameter-extractor-stage.v1.yaml`; source map
  `p4b-02b6-mit-source-map.v1.yaml`.
- PLAN **P4B-02b6**; ledger note/gate P4B-02; coverage gates 119 -> 120.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- No release certification, no acceptance evidence.
