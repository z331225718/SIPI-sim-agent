# P4A-03aa Typed IBIS Series Switch Groups Threshold Parameters Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03aa (typed IBIS [Series Switch Groups] threshold parameters core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_switch_thresholds_v1.rs` in `sipi-ibis`: `TypedSeriesSwitchThresholdsV1`
holds validated `vthreshold_v`, `rseries_ohm`, `cseries_farad`, and `lseries_henry` for series switch groups.
`lift_series_switch_thresholds_v1` validates inputs and returns `Result<TypedSeriesSwitchThresholdsV1, SeriesSwitchThresholdsErrorV1>`.
Fail-closed: non-finite values (`NonFiniteValue`) or negative R/C/L threshold parameters (`NegativeThresholdParameter`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full switch thresholds; valid minimal switch thresholds;
  negative rseries rejection; non-finite value rejection).
- Cross-check: 3 test cases (full switch thresholds, minimal switch thresholds, negative rseries)
  driven through product runner `p4a_03aa_series_switch_thresholds_runner`; independent Python reference
  matches 100% on valid flags, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03aa_series_switch_thresholds.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03aa-series-switch-thresholds-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03aa-series-switch-thresholds-stage.v1.yaml`; source map
  `p4a-03aa-mit-source-map.v1.yaml`.
- PLAN **P4A-03aa**; ledger note/gate P4A-03; coverage gates 151 -> 152.

## Scope / Non-Claims

- Not a full IBIS file parser; no series switch circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
