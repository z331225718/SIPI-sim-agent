# P4A-03bb Typed IBIS Series Pin Mapping Group Switch Association Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03bb (typed IBIS [Series Pin Mapping] group switch association core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_group_switch_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupSwitchRecordV1`
holds validated ASCII group names (`group_name`, `on_group_name`, `off_group_name`) and an optional `function_table_group`.
`lift_series_pin_group_switch_record_v1` validates inputs and returns
`Result<TypedSeriesPinGroupSwitchRecordV1, SeriesPinTableGroupSwitchErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), empty state group names (`EmptyStateGroupName`),
non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`), or identical ON/OFF state groups
(`IdenticalStateGroups`) are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full group switch record; valid minimal group switch record;
  empty group name rejection; identical state groups rejection).
- Cross-check: 3 test cases (full group switch record, minimal group switch record, identical state groups)
  driven through product runner `p4a_03bb_series_pin_table_group_switch_runner`; independent Python reference
  matches 100% on valid flags, group names, ON/OFF state group names, function table groups, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03bb_series_pin_table_group_switch.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03bb-series-pin-table-group-switch-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03bb-series-pin-table-group-switch-stage.v1.yaml`; source map
  `p4a-03bb-mit-source-map.v1.yaml`.
- PLAN **P4A-03bb**; ledger note/gate P4A-03; coverage gates 183 -> 184.

## Scope / Non-Claims

- Not a full IBIS file parser; no series switch circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
