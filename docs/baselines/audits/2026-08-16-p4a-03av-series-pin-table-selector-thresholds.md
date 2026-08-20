# P4A-03av Typed IBIS Series Pin Mapping Model Selector Threshold Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03av (typed IBIS [Series Pin Mapping] Model Selector threshold table binding core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_selector_thresholds_v1.rs` in `sipi-ibis`: `TypedSeriesPinSelectorThresholdRecordV1`
holds validated ASCII pin names (`pin_first`, `pin_second`), `model_selector_name`, and threshold parameters (`vthreshold_v`, `rseries_ohm`, `cseries_farad`, `lseries_henry`).
`lift_series_pin_selector_threshold_record_v1` validates inputs and returns
`Result<TypedSeriesPinSelectorThresholdRecordV1, SeriesPinTableSelectorThresholdsErrorV1>`.
Fail-closed: empty pin names (`EmptyPinName`), empty selector names (`EmptySelectorName`),
non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`), identical pin pairs (`IdenticalPins`),
non-finite values (`NonFiniteValue`), or negative R/C/L threshold parameters (`NegativeThresholdParameter`) are strictly rejected.
An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full selector threshold record; valid minimal selector threshold record;
  empty pin name rejection; negative rseries rejection).
- Cross-check: 3 test cases (full selector threshold record, minimal selector threshold record, empty pin name)
  driven through product runner `p4a_03av_series_pin_table_selector_thresholds_runner`; independent Python reference
  matches 100% on valid flags, pin names, selector names, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03av_series_pin_table_selector_thresholds.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03av-series-pin-table-selector-thresholds-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03av-series-pin-table-selector-thresholds-stage.v1.yaml`; source map
  `p4a-03av-mit-source-map.v1.yaml`.
- PLAN **P4A-03av**; ledger note/gate P4A-03; coverage gates 177 -> 178.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
