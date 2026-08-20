# P5-04a Network Ingest Mixed-Mode Transform — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-04 sub-slice 04a (network ingest mixed-mode transform)
- Status: delivered and mechanically bound; remaining stages pending

## Deliverable

- `crates/sipi-com/src/mixed_mode_v1.rs`: `com_t_v1()`, `com_mixed_mode_v1`
  (COM_T * s * COM_T^-1 with COM_T^-1 = 0.5*COM_T since COM_T^2 = 2I),
  `sdd21_v1` (mixed[3][1] per the MATLAB/oracle convention).
- MIT source map `p5-04a-mit-source-map.v1.yaml` (3 function mappings,
  apply_r480_pn_skew explicitly not ported).
- 4 Rust tests: identity invariance, differential gain 1, common-mode
  rejection 0, fixed policy string. sipi-com now 9 tests green.

## Scope discipline

Transform only: no file reading, no port-order application, no COM
metric computation. Channel selection / equalizer search / PDF /
metrics stages remain.

## Binding

- Charter `p5-04a-network-ingest.v1.yaml`; source map;
- Verifier `verify_p5_04a_network_ingest.py` + 5 tests;
- PLAN **P5-04a**; ledger note/gate; coverage gates 90 -> 91.
