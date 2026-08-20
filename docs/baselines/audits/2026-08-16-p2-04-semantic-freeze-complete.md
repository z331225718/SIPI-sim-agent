# P2-04 TRAN Semantic Freeze Complete

P2-04 requires fixing time integration, initial condition, tolerance,
step control, output sampling, and measurement semantics. This audit
records the mechanical gate confirming all six are frozen on the current
fixed-profile surface, and marks P2-04 complete.

## Freeze Facts

- Integration: f64 backward Euler (P2-03 freeze + acceptance contract);
- Initial condition: explicit only (`explicit_without_op`, 0.0 V);
- Tolerance (acceptance contract): time 1e-15 s abs / 0 rel; v(in)
  1e-9 V abs / 1e-9 rel; v(out) 2e-6 V abs / 5e-4 rel;
- Step control: fixed breakpoint-union (requested times + pulse
  corners), no adaptive stepping;
- Output sampling: reported at requested axis only,
  index-aligned no interpolation;
- Measurement semantics: explicitly frozen as `not_implemented`
  (P2-03 freeze; acceptance contract out_of_scope includes measurements).

## Delivered Gate

- `tools/verify_p2_04_semantic_freeze_complete.py` — verifier for schema
  `sipi.p2-04.semantic-freeze-complete.v1`. It fails closed if the P2-03
  freeze drifts on any of the five policy semantics, or if the acceptance
  contract drifts on acceptance_ready, alignment, any tolerance, IC mode,
  or integration method.
- `tools/test_verify_p2_04_semantic_freeze_complete.py` — 5 tests: live
  validity, freeze policy semantics, frozen tolerances, alignment/IC, and
  tolerance-drift rejection.

## Verification

`python -B tools/verify_p2_04_semantic_freeze_complete.py` returned
`{"elements": 6, "schema": "sipi.p2-04.semantic-freeze-complete.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p2_04_semantic_freeze_complete` passed 5/5.

## Artifact Hashes (SHA-256)

- verifier: `10145028F586149800C6DF38DC0F28ADB8536AE742BD9D32094B9FF7A18B75E6`
- tests: `DD8176052CF6C07707CF4DCD11C7F4B9A8AB18CE981A9FAF147D092E4EFA293D`

## Scope and Non-Claims

- This completion covers the current fixed one-node RC/PULSE/PWL profile
  surface. General netlist TRAN tolerance policy (multi-device,
  measurements, engine CLI route) remains out of scope per the acceptance
  contract and remains open in PLAN as generalized TRAN work.
- The gate does not certify TRAN generality, netlist support, OP/AC, or
  release readiness; acceptance remains `specified_not_executed` until
  the external oracle comparison runs.
