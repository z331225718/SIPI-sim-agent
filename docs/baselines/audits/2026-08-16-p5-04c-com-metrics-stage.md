# P5-04c COM/VEC/VEO Scalar Metrics Stage — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-04 sub-slice 04c (COM scalar metrics stage)
- Status: delivered and mechanically bound

## Deliverable

- `crates/sipi-com/src/com_metrics_v1.rs`: `calculate_com_metrics_v1`
  ported from agent-com `metrics/com.py` (MIT): interference from first
  CDF > spec_ber; threshold DER; C2C branch (vec argument, com, veo) and
  t_o_s C2M branch (VEO = 1000*eye, VEC = 20log10(max(2A/eye, eps)));
  errors BER-RANGE / THRESHOLD-RANGE / C2M-EYE-REQUIRED.
- MIT source map `p5-04c-mit-source-map.v1.yaml` (3 mappings; DiscretePdf
  construction explicitly not ported).
- 5 Rust tests (scalar math, invalid controls, C2M eye required, VEO/VEC
  values, policy). sipi-com now 17 tests green.

## Scope discipline

PDF support/CDF arrays are caller-supplied; discrete-PDF construction,
full metric surface (ERL/ICN/etc.), and release evidence remain
non-claims.

## Binding

- Charter `p5-04c-com-metrics-stage.v1.yaml`; source map;
- Verifier `verify_p5_04c_com_metrics_stage.py` + 5 tests;
- PLAN **P5-04c**; ledger note/gate; coverage gates 92 -> 93.
