# P4A-03al Typed IBIS Diff Pin Complete Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03al (typed IBIS [Diff Pin] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `diff_pin_keywords_v1.rs` in `sipi-ibis`: `TypedDiffPinBlockV1`
holds a validated `TypedDiffPinDeclarationV1` (`diff_pin_declaration`).
`lift_diff_pin_block_v1` validates inputs and returns `Result<TypedDiffPinBlockV1, DiffPinKeywordsErrorV1>`.
Fail-closed: invalid differential pin declarations are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 2 Rust unit tests green (policy fixed; valid diff pin block).
- Cross-check: 3 test cases (full diff pin block, minimal diff pin block, identical pins)
  driven through product runner `p4a_03al_diff_pin_keywords_runner`; independent Python reference
  matches 100% on valid flags, differential pin declarations, threshold/delay values, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03al_diff_pin_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03al-diff-pin-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03al-diff-pin-keywords-stage.v1.yaml`; source map
  `p4a-03al-mit-source-map.v1.yaml`.
- PLAN **P4A-03al**; ledger note/gate P4A-03; coverage gates 164 -> 165.

## Scope / Non-Claims

- Not a full IBIS file parser; no differential receiver simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
