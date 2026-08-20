# P4A-03ao Typed IBIS Series Pin Mapping Group Switch Threshold Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ao (typed IBIS [Series Pin Mapping] group switch threshold table binding core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_group_switch_thresholds_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupSwitchThresholdRecordV1`
holds validated ASCII group names (`group_name`, `on_group_name`, `off_group_name`) and threshold parameters (`vthreshold_v`, `rseries_ohm`, `cseries_farad`, `lseries_henry`).
`lift_series_pin_group_switch_threshold_record_v1` validates inputs and returns
`Result<TypedSeriesPinGroupSwitchThresholdRecordV1, SeriesPinTableGroupSwitchThresholdsErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), empty state group names (`EmptyStateGroupName`),
non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`), identical ON/OFF state groups (`IdenticalStateGroups`),
non-finite values (`NonFiniteValue`), or negative R/C/L threshold parameters (`NegativeThresholdParameter`) are strictly rejected.
An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid full group switch threshold record; valid minimal group switch threshold record;
  empty group name rejection; identical state groups rejection; negative rseries rejection).
- Cross-check: 3 test cases (full group switch threshold record, minimal group switch threshold record, identical state groups)
  driven through product runner `p4a_03ao_series_pin_table_group_switch_thresholds_runner`; independent Python reference
  matches 100% on valid flags, group names, ON/OFF state group names, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ao_series_pin_table_group_switch_thresholds.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ao-series-pin-table-group-switch-thresholds-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ao-series-pin-table-group-switch-thresholds-stage.v1.yaml`; source map
  `p4a-03ao-mit-source-map.v1.yaml`.
- PLAN **P4A-03ao**; ledger note/gate P4A-03; coverage gates 169 -> 170.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
