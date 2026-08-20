# P4A-03p Typed IBIS Series Switch Groups Mapping Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03p (typed IBIS standalone [Series Switch Groups] mapping table core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_switch_mapping_v1.rs` in `sipi-ibis`: `TypedSeriesSwitchRecordV1`
holds validated ASCII group names (`on_group_name`, `off_group_name`).
`lift_series_switch_record_v1` validates inputs and returns
`Result<TypedSeriesSwitchRecordV1, SeriesSwitchMappingTableErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), non-ASCII characters (`NonAsciiName`),
invalid name spellings (`InvalidName`), or identical ON/OFF groups (`IdenticalGroups`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid record; empty group name rejection;
  non-ASCII name rejection; identical groups rejection).
- Cross-check: 3 test cases (valid record, empty group name, identical groups)
  driven through product runner `p4a_03p_series_switch_mapping_runner`; independent Python reference
  matches 100% on valid flags, ON/OFF group names, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03p_series_switch_mapping.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03p-series-switch-mapping-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03p-series-switch-mapping-stage.v1.yaml`; source map
  `p4a-03p-mit-source-map.v1.yaml`.
- PLAN **P4A-03p**; ledger note/gate P4A-03; coverage gates 129 -> 130.

## Scope / Non-Claims

- Not a full IBIS file parser; no series switch simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
