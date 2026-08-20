# P2-03 TRAN Semantic Freeze

P2-03 freezes the netlist/circuit request rejection surface, the device
support matrix, the solver/convergence policy, and the error taxonomy for
the current TRAN product surface. The freeze is bound to live product
contracts so that any drift fails closed.

## Delivered Freeze

- `docs/baselines/p2-03-tran-semantic-freeze.v1.yaml` — provisional freeze
  (`owner: project`, `scope: current_product_surface_only`) recording:
  - request schemas: `sipi.tran.one-node-rc-pulse-request.v1`,
    `sipi.tran.one-node-rc-pwl-request.v1`, `sipi.tran.rc-pulse-request.v1`;
  - topology identifiers used in provenance;
  - device support matrix (4 supported: ideal PULSE/PWL source, series R,
    C to explicit reference; 8 unsupported/rejected: inductor, diode,
    transistor, transmission line, arbitrary netlist, implicit ground,
    model selection, topology description);
  - solver policy: f64 backward Euler, fixed breakpoint-union stepping,
    no adaptive stepping, no convergence iteration (closed-form),
    explicit-only initial condition, reported at requested axis only,
    measurement semantics frozen as `not_implemented`, tolerance policy frozen
    as `blocked_missing_tolerance_owner_decision`, resource limits 4096 output
    samples / 16384 breakpoints with cooperative checkpoints;
  - error taxonomy: all 20 `TranError` variants;
  - contract refs to the four P2 clean-room specs.
- `tools/verify_p2_03_tran_semantic_freeze.py` — verifier. It fails closed
  if: the freeze document schema/scope/owner drifts; request schemas,
  topology set, device matrix, solver policy, or resource limits change;
  the recorded error taxonomy no longer equals the live `TranError` enum
  variants in `crates/sipi-tran/src/lib.rs`; a recorded request schema is
  missing from `crates/sipi-contracts/src/lib.rs`; a recorded topology is
  missing from the CLI provenance emission; or a referenced clean-room
  contract is untracked or missing.
- `tools/test_verify_p2_03_tran_semantic_freeze.py` — 9 tests: live
  validity, schema/scope, live enum binding, and negative probes for
  schema, taxonomy, device-matrix, resource-limit, and contract drift.

## Verification

`python -B tools/verify_p2_03_tran_semantic_freeze.py` returned
`{"error_variants": 20, "schema": "sipi.p2-03.tran-semantic-freeze.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_p2_03_tran_semantic_freeze` passed 9/9.

## Artifact Hashes (SHA-256)

- freeze: `306622E32F4876F2BC6DA8B1E27173E5B009CF03DA1C8DF98C40297A76402150`
- verifier: `CC43C2515E1CE84E9A173FF7CFAA2D9AFDD42C5F420ACB90A7E92FD785614C71`
- tests: `0FFDC61141BBB64D0CB284A4A7F3246C64215B5F21FA98C9F23715F600F3E643`

## Scope and Non-Claims

- This freeze records the CURRENT product surface only. It does not accept
  a new TRAN profile, generalize the topology, or certify OP/AC/MNA, and
  does not change the fixed `tran-rc-pulse-v1` external acceptance scope.
- The freeze is provisional until owner confirmation; extending the device
  matrix or changing limits requires a new freeze revision.