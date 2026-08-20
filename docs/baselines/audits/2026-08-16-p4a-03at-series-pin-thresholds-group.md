# P4A-03at Typed IBIS Series Pin Mapping Group Threshold Parameters Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03at (typed IBIS [Series Pin Mapping] group threshold parameters record core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_thresholds_group_v1.rs` in `sipi-ibis`: `TypedSeriesPinTableGroupThresholdsV1`
holds validated ASCII group name (`group_name`) and threshold parameters (`vthreshold_v`, `rseries_ohm`, `cseries_farad`, `lseries_henry`).
`lift_series_pin_table_group_thresholds_v1` validates inputs and returns
`Result<TypedSeriesPinTableGroupThresholdsV1, SeriesPinTableThresholdsGroupErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`),
non-finite values (`NonFiniteValue`), or negative R/C/L threshold parameters (`NegativeThresholdParameter`) are strictly rejected.
An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full group thresholds record; valid minimal group thresholds record;
  empty group name rejection; negative rseries rejection).
- Cross-check: 3 test cases (full group thresholds record, minimal group thresholds record, empty group name)
  driven through product runner `p4a_03at_series_pin_thresholds_group_runner`; independent Python reference
  matches 100% on valid flags, group names, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03at_series_pin_thresholds_group.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03at-series-pin-thresholds-group-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03at-series-pin-thresholds-group-stage.v1.yaml`; source map
  `p4a-03at-mit-source-map.v1.yaml`.
- PLAN **P4A-03at**; ledger note/gate P4A-03; coverage gates 175 -> 176.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
