# P4A-03as Typed IBIS Series Pin Mapping Group Model Selector Binding Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03as (typed IBIS [Series Pin Mapping] group Model Selector binding record core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_group_selector_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupSelectorRecordV1`
holds validated ASCII group name (`group_name`), `model_selector_name`, and an optional `function_table_group`.
`lift_series_pin_group_selector_record_v1` validates inputs and returns
`Result<TypedSeriesPinGroupSelectorRecordV1, SeriesPinTableGroupSelectorErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), empty selector names (`EmptySelectorName`),
non-ASCII characters (`NonAsciiName`), or invalid name spellings (`InvalidName`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full group selector record; valid minimal group selector record;
  empty group name rejection; empty selector name rejection).
- Cross-check: 3 test cases (full group selector record, minimal group selector record, empty selector name)
  driven through product runner `p4a_03as_series_pin_table_group_selector_runner`; independent Python reference
  matches 100% on valid flags, group names, selector names, function table groups, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03as_series_pin_table_group_selector.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03as-series-pin-table-group-selector-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03as-series-pin-table-group-selector-stage.v1.yaml`; source map
  `p4a-03as-mit-source-map.v1.yaml`.
- PLAN **P4A-03as**; ledger note/gate P4A-03; coverage gates 174 -> 175.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
