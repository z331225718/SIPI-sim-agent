# P4A-03ab Typed IBIS Model Required Sub-Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ab (typed IBIS [Model] required sub-keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `model_declaration_keywords_v1.rs` in `sipi-ibis`: `validate_model_keywords_v1`
validates sub-keyword completeness for an IBIS `[Model]` according to its `ModelTypeV1`
(e.g., Output / IO / 3-state requiring `[Pullup]` and `[Pulldown]`).
Fail-closed: missing required sub-keywords (`MissingRequiredSubKeyword`) are strictly rejected.
An independent Python reference recomputes sub-keyword validation rules over 3 test cases.

## Result

- 4 Rust unit tests green (policy fixed; valid output model keywords; rejects missing pullup;
  rejects missing pulldown).
- Cross-check: 3 test cases (valid output keywords, missing pullup output, missing pulldown output)
  driven through product runner `p4a_03ab_model_keywords_runner`; independent Python reference
  matches 100% on valid flags, model_type strings, and error messages; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ab_model_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ab-model-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ab-model-keywords-stage.v1.yaml`; source map
  `p4a-03ab-mit-source-map.v1.yaml`.
- PLAN **P4A-03ab**; ledger note/gate P4A-03; coverage gates 152 -> 153.

## Scope / Non-Claims

- Not a full IBIS file parser; no transient driver I-V curve simulation.
- No release certification, no acceptance evidence.
