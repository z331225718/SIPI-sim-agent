# P4A-03q Typed IBIS Receiver Thresholds Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03q (typed IBIS [Receiver Thresholds] core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `receiver_thresholds_v1.rs` in `sipi-ibis`: `TypedReceiverThresholdsV1`
holds validated `vcross_low_v`, `vcross_high_v`, `vdiff_ac_v`, `vdiff_dc_v`, and `tskew_s`
`.lift_receiver_thresholds_v1` validates inputs and returns `Result<TypedReceiverThresholdsV1, ReceiverThresholdsErrorV1>`.
Fail-closed: non-finite voltage or time values (`NonFiniteValue`) or negative differential thresholds (`NegativeThreshold`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid full thresholds; valid minimal thresholds;
  negative vdiff_ac rejection; non-finite value rejection).
- Cross-check: 3 test cases (full thresholds, minimal thresholds, negative vdiff_ac)
  driven through product runner `p4a_03q_receiver_thresholds_runner`; independent Python reference
  matches 100% on valid flags, threshold/skew values, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03q_receiver_thresholds.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03q-receiver-thresholds-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03q-receiver-thresholds-stage.v1.yaml`; source map
  `p4a-03q-mit-source-map.v1.yaml`.
- PLAN **P4A-03q**; ledger note/gate P4A-03; coverage gates 130 -> 131.

## Scope / Non-Claims

- Not a full IBIS file parser; no receiver threshold simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
