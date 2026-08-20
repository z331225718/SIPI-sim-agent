# P4A-03z Typed IBIS Series Pin Mapping Group Threshold Parameters Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03z (typed IBIS [Series Pin Mapping] group threshold parameters core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_thresholds_group_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupThresholdsV1`
holds validated `vthreshold_v`, `rseries_ohm`, `cseries_farad`, and `lseries_henry` for series groups.
`lift_series_pin_group_thresholds_v1` validates inputs and returns `Result<TypedSeriesPinGroupThresholdsV1, SeriesPinThresholdsGroupErrorV1>`.
Fail-closed: non-finite values (`NonFiniteValue`) or negative R/C/L threshold parameters (`NegativeThresholdParameter`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full group thresholds; valid minimal group thresholds;
  negative rseries rejection; non-finite value rejection).
- Cross-check: 3 test cases (full group thresholds, minimal group thresholds, negative rseries)
  driven through product runner `p4a_03z_series_pin_thresholds_group_runner`; independent Python reference
  matches 100% on valid flags, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03z_series_pin_thresholds_group.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03z-series-pin-thresholds-group-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03z-series-pin-thresholds-group-stage.v1.yaml`; source map
  `p4a-03z-mit-source-map.v1.yaml`.
- PLAN **P4A-03z**; ledger note/gate P4A-03; coverage gates 150 -> 151.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
