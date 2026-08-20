# P4A-03az Typed IBIS Series Pin Mapping Model Selector Binding Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03az (typed IBIS [Series Pin Mapping] Model Selector binding record core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_selector_v1.rs` in `sipi-ibis`: `TypedSeriesPinSelectorRecordV1`
holds validated ASCII pin names (`pin_first`, `pin_second`), `model_selector_name`, and an optional `function_table_group`.
`lift_series_pin_selector_record_v1` validates inputs and returns
`Result<TypedSeriesPinSelectorRecordV1, SeriesPinTableSelectorErrorV1>`.
Fail-closed: empty pin names (`EmptyPinName`), empty selector names (`EmptySelectorName`),
non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`), or identical pin pairs (`IdenticalPins`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full selector record; valid minimal selector record;
  empty pin name rejection; identical pins rejection).
- Cross-check: 3 test cases (full selector record, minimal selector record, identical pins)
  driven through product runner `p4a_03az_series_pin_table_selector_runner`; independent Python reference
  matches 100% on valid flags, pin names, selector names, function table groups, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03az_series_pin_table_selector.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03az-series-pin-table-selector-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03az-series-pin-table-selector-stage.v1.yaml`; source map
  `p4a-03az-mit-source-map.v1.yaml`.
- PLAN **P4A-03az**; ledger note/gate P4A-03; coverage gates 181 -> 182.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
