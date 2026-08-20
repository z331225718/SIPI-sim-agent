# P4A-03u Typed IBIS Series Pin Thresholds Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03u (typed IBIS [Series Pin Mapping] threshold parameters core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_thresholds_v1.rs` in `sipi-ibis`: `TypedSeriesPinThresholdsV1`
holds validated `vthreshold_v`, `rseries_ohm`, `cseries_farad`, and `lseries_henry`
`.lift_series_pin_thresholds_v1` validates inputs and returns `Result<TypedSeriesPinThresholdsV1, SeriesPinThresholdsErrorV1>`.
Fail-closed: non-finite values (`NonFiniteValue`) or negative R/C/L threshold parameters (`NegativeThresholdParameter`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full thresholds; valid minimal thresholds;
  negative rseries rejection; non-finite value rejection).
- Cross-check: 3 test cases (full thresholds, minimal thresholds, negative rseries)
  driven through product runner `p4a_03u_series_pin_thresholds_runner`; independent Python reference
  matches 100% on valid flags, threshold parameters, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03u_series_pin_thresholds.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03u-series-pin-thresholds-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03u-series-pin-thresholds-stage.v1.yaml`; source map
  `p4a-03u-mit-source-map.v1.yaml`.
- PLAN **P4A-03u**; ledger note/gate P4A-03; coverage gates 144 -> 145.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
