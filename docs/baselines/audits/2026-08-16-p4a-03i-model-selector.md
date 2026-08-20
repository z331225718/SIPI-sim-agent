# P4A-03i Typed IBIS Model Selector & Series Pin Mapping Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03i (typed IBIS [Model Selector] & [Series Pin Mapping] core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `model_selector_declaration_v1.rs` in `sipi-ibis`: `TypedModelSelectorDeclarationV1`
holds a validated ASCII selector name and non-empty list of `ModelBranchV1` (model_name, optional description).
`TypedSeriesPinMappingV1` holds a validated pair of pin names (`pin_first`, `pin_second`) and target `model_name`.
Fail-closed: empty names (`EmptyName`), non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`),
empty branch lists (`EmptyBranches`), or identical series pins (`IdenticalSeriesPins`) are strictly rejected.
An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid model selector; valid series pin mapping;
  empty selector name rejection; empty branches rejection; identical series pins rejection).
- Cross-check: 3 test cases (model selector, series pin mapping, identical series pins)
  driven through product runner `p4a_03i_model_selector_runner`; independent Python reference
  matches 100% on valid flags, selector/pin mapping fields, and error codes; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03i_model_selector.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03i-model-selector-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03i-model-selector-stage.v1.yaml`; source map
  `p4a-03i-mit-source-map.v1.yaml`.
- PLAN **P4A-03i**; ledger note/gate P4A-03; coverage gates 121 -> 122.

## Scope / Non-Claims

- Not a full IBIS file parser; no dynamic model selector resolution or electrical semantics.
- No release certification, no acceptance evidence.
