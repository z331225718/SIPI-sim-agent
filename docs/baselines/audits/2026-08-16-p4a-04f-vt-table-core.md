# P4A-04f Typed V-T Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-04 sub-slice 04f (V-T table semantics + explicit interpolation/extrapolation policy)
- Status: delivered and mechanically bound; P4A-04 main item stays open (ramp/package pending)

## Deliverable

`crates/sipi-ibis/src/vt_table_v1.rs` (wired into `sipi-ibis` lib as
`vt_table_v1` module, re-exported):

- `VtKnotV1` — one finite (time_seconds, voltage_volts) knot.
- `VtTableV1::try_new` — strictly time-ascending, finite, at least two
  knots; single-knot tables and non-strict/descending time are rejected
  (`TooFewKnots`, `TimeNotStrictlyIncreasing`).
- `evaluate_vt_v1` — piecewise-linear interpolation within the closed
  table domain `[first, last]`; any requested time outside the domain is
  rejected (`OutOfDomain`); no extrapolation is ever performed.
- `VT_EVALUATION_POLICY_V1` — fixed policy string
  `sipi.p4a-04f.vt-table-v1.linear-within-domain.reject-out-of-domain`.

## Scope discipline

- Product-owned, caller-supplied data only. No IBIS text decoding, no
  electrical evaluation, no profile acceptance, no CLI route.
- Ramp semantics, package semantics, decoder and CLI stay
  `not_in_this_slice` per the charter
  `docs/baselines/p4a-04f-vt-table-core.v1.yaml`.
- I-V DC clamp semantics remain delivered by P4A-04b/04d (unchanged).

## Mechanical binding

- Charter `docs/baselines/p4a-04f-vt-table-core.v1.yaml` (schema
  `sipi.p4a-04f.vt-table-core.v1`).
- Verifier `tools/verify_p4a_04f_vt_table_core.py` cross-binds charter
  fields (slice scope, evaluation policy, table rules, units,
  implementation, admission, non_claims) against the Rust source tokens
  and the PLAN `**P4A-04f` row; any drift fails closed.
- Tests `tools/test_verify_p4a_04f_vt_table_core.py`: 8 tests.
- Rust unit tests: 8 new tests in `vt_table_v1.rs` (linear midpoint,
  second segment, endpoint hits, out-of-domain rejection, single-knot
  rejection, duplicate/descending time rejection, domain, policy string).
  `cargo test -p sipi-ibis`: 32 passed, 0 failed.

## Non-claims (unchanged for P4A-04 main item)

ramp semantics; package semantics; IBIS text decoding; profile
acceptance; electrical evaluation; external reference binding remains
`not_evaluated`. P4A-04 remains open in the ledger with blocker
`semantics_not_implemented` until ramp/package semantics are delivered.
