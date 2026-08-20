# P4A-03ac Typed IBIS Series Pin Mapping Group Threshold Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ac (typed IBIS [Series Pin Mapping] group threshold table binding core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_group_thresholds_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupThresholdRecordV1`
holds validated ASCII group name (`group_name`) and threshold parameters (`vthreshold_v`, `rseries_ohm`, `cseries_farad`, `lseries_henry`).
`lift_series_pin_group_threshold_record_v1` validates inputs and returns
`Result<TypedSeriesPinGroupThresholdRecordV1, SeriesPinTableGroupThresholdsErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), non-ASCII characters (`NonAsciiName`),
invalid name spellings (`InvalidName`), non-finite values (`NonFiniteValue`), or negative R/C/L threshold parameters
(`NegativeThresholdParameter`) are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full group threshold record; valid minimal group threshold record;
  empty group name rejection; negative rseries rejection).
- Cross-check: 3 test cases (full group threshold record, minimal group threshold record, empty group name)
  driven through product runner `p4a_03ac_series_pin_table_group_thresholds_runner`; independent Python reference
  matches 100% on valid flags, group names, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ac_series_pin_table_group_thresholds.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ac-series-pin-table-group-thresholds-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ac-series-pin-table-group-thresholds-stage.v1.yaml`; source map
  `p4a-03ac-mit-source-map.v1.yaml`.
- PLAN **P4A-03ac**; ledger note/gate P4A-03; coverage gates 154 -> 155.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
