# P4A-03ad Typed IBIS Model Selector Keyword Completeness Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ad (typed IBIS [Model Selector] keyword completeness core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `model_selector_keywords_v1.rs` in `sipi-ibis`: `TypedModelSelectorKeywordsV1`
holds a validated ASCII selector name (`[A-Za-z0-9_.-]+`) and a list of `ModelOptionEntryV1` (model_name, description).
`lift_model_selector_keywords_v1` validates inputs and returns `Result<TypedModelSelectorKeywordsV1, ModelSelectorKeywordsErrorV1>`.
Fail-closed: empty selector names (`EmptySelectorName`), non-ASCII characters (`NonAsciiName`),
invalid name spellings (`InvalidName`), empty model option lists (`EmptyModelOptions`), or duplicate model options
(`DuplicateModelOption`) are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid model selector declaration; empty selector name rejection;
  empty model options rejection; duplicate model option rejection).
- Cross-check: 3 test cases (valid model selector, empty model options, duplicate model option)
  driven through product runner `p4a_03ad_model_selector_keywords_runner`; independent Python reference
  matches 100% on valid flags, selector names, model option lists, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ad_model_selector_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ad-model-selector-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ad-model-selector-keywords-stage.v1.yaml`; source map
  `p4a-03ad-mit-source-map.v1.yaml`.
- PLAN **P4A-03ad**; ledger note/gate P4A-03; coverage gates 155 -> 156.

## Scope / Non-Claims

- Not a full IBIS file parser; no dynamic model selection during simulation.
- No release certification, no acceptance evidence.
