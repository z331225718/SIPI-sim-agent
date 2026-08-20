# P5-03a Typed Stage-Output Envelope — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-03 sub-slice 03a (sipi-com crate + typed stage-output
  envelope)
- Status: delivered and mechanically bound; stage computation pending
  behavior profile

## Deliverable

- New workspace crate `crates/sipi-com` (MIT, forbid unsafe):
  - `ComMetricValueV1` - finite or infinity metric value;
  - `ComOutputMetricsV1` - the fourteen observed oracle output metrics;
  - `ComNetworkMetricV1` - THRU/FEXT1/NEXT1 network rows (finite
    scalars, non-empty roles);
  - `ComCaseCheckpointV1` - TXLE/DFE taps (finite), tail_RSS, sigma_N,
    sgm_ani_isi_xt_noise, itick >= 0;
  - policy constant sipi.p5-03a.com-stage-output-envelope-v1.typed-
    structure-only.
- Basis: the P5-06b oracle metric surface (observed structure only).
- 5 Rust tests green.

## Scope discipline

Structure only: no COM computation, no behavior profile, no compare, no
profile acceptance, no release evidence. The envelope types are the
typed carrier for future stage outputs; computation semantics wait for
the owner-approved behavior profile.

## Binding

- Charter `p5-03a-com-stage-output-envelope.v1.yaml`;
- Verifier `verify_p5_03a_com_stage_output_envelope.py` + 5 tests;
- PLAN **P5-03a**; ledger note/gate; coverage gates 89 -> 90.
