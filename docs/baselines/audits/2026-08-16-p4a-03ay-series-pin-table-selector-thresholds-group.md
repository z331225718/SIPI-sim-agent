# P4A-03ay Typed IBIS Series Pin Mapping Model Selector Group Threshold Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ay (typed IBIS [Series Pin Mapping] Model Selector group threshold table binding core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_selector_thresholds_group_v1.rs` in `sipi-ibis`: `TypedSeriesPinSelectorGroupThresholdRecordV1`
holds validated ASCII pin names (`pin_first`, `pin_second`), `model_selector_name`, optional `group_name`, and threshold parameters (`vthreshold_v`, `rseries_ohm`, `cseries_farad`, `lseries_henry`).
`lift_series_pin_selector_group_threshold_record_v1` validates inputs and returns
`Result<TypedSeriesPinSelectorGroupThresholdRecordV1, SeriesPinTableSelectorThresholdsGroupErrorV1>`.
Fail-closed: empty pin names (`EmptyPinName`), empty selector names (`EmptySelectorName`), empty group names (`EmptyGroupName`),
non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`), identical pin pairs (`IdenticalPins`),
non-finite values (`NonFiniteValue`), or negative R/C/L threshold parameters (`NegativeThresholdParameter`) are strictly rejected.
An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full selector group threshold record; valid minimal selector group threshold record;
  empty pin name rejection; negative rseries rejection).
- Cross-check: 3 test cases (full selector group threshold record, minimal selector group threshold record, empty pin name)
  driven through product runner `p4a_03ay_series_pin_table_selector_thresholds_group_runner`; independent Python reference
  matches 100% on valid flags, pin names, selector names, group names, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ay_series_pin_table_selector_thresholds_group.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ay-series-pin-table-selector-thresholds-group-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ay-series-pin-table-selector-thresholds-group-stage.v1.yaml`; source map
  `p4a-03ay-mit-source-map.v1.yaml`.
- PLAN **P4A-03ay**; ledger note/gate P4A-03; coverage gates 180 -> 181.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
