# P4A-03ai Typed IBIS Test Data Complete Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ai (typed IBIS [Test Data] / [Test Load] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `test_data_keywords_v1.rs` in `sipi-ibis`: `TypedTestDataBlockV1`
holds a validated `TypedTestDataDeclarationV1` (`fixture_declaration`).
`lift_test_data_block_v1` validates inputs and returns `Result<TypedTestDataBlockV1, TestDataKeywordsErrorV1>`.
Fail-closed: invalid test fixture declarations are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 2 Rust unit tests green (policy fixed; valid test data block).
- Cross-check: 3 test cases (full test data block, minimal test data block, negative R_fixture)
  driven through product runner `p4a_03ai_test_data_keywords_runner`; independent Python reference
  matches 100% on valid flags, fixture declarations, R/C/L/V parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ai_test_data_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ai-test-data-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ai-test-data-keywords-stage.v1.yaml`; source map
  `p4a-03ai-mit-source-map.v1.yaml`.
- PLAN **P4A-03ai**; ledger note/gate P4A-03; coverage gates 161 -> 162.

## Scope / Non-Claims

- Not a full IBIS file parser; no test load circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
