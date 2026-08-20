# P4A-03ar Typed IBIS Series Pin Mapping Group Model Binding Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ar (typed IBIS [Series Pin Mapping] group model binding record core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_table_group_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupModelRecordV1`
holds validated ASCII group name (`group_name`), `model_name`, and an optional `function_table_group`.
`lift_series_pin_group_model_record_v1` validates inputs and returns
`Result<TypedSeriesPinGroupModelRecordV1, SeriesPinTableGroupModelErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), empty model names (`EmptyModelName`),
non-ASCII characters (`NonAsciiName`), or invalid name spellings (`InvalidName`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full group model record; valid minimal group model record;
  empty group name rejection; empty model name rejection).
- Cross-check: 3 test cases (full group model record, minimal group model record, empty model name)
  driven through product runner `p4a_03ar_series_pin_table_group_runner`; independent Python reference
  matches 100% on valid flags, group names, model names, function table groups, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ar_series_pin_table_group.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ar-series-pin-table-group-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ar-series-pin-table-group-stage.v1.yaml`; source map
  `p4a-03ar-mit-source-map.v1.yaml`.
- PLAN **P4A-03ar**; ledger note/gate P4A-03; coverage gates 173 -> 174.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
