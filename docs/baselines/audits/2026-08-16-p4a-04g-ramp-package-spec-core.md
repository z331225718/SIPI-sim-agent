# P4A-04g Typed Ramp/Package Declaration Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-04 sub-slice 04g (Ramp/Package declaration semantics)
- Status: delivered and mechanically bound; P4A-04 completed via
  `2026-08-16-p4a-04-semantic-cores-complete.md`

## Deliverable

`crates/sipi-ibis/src/ramp_package_spec_v1.rs` (wired into `sipi-ibis`,
re-exported):

- `RampSpecV1::try_new` — `[Ramp]` declaration (dV/dt_r, dV/dt_f in V/s,
  R_load in ohms): finite strictly positive typed fields;
  `NonPositiveSlopeRise` / `NonPositiveSlopeFall` / `NonPositiveLoad`
  reject zero or negative values.
- `PackageSpecV1::try_new` — `[Package]` declaration (R_pin in ohms,
  L_pin in henries, C_pin in farads): finite strictly positive typed
  fields; `NonPositiveResistance` / `NonPositiveInductance` /
  `NonPositiveCapacitance` reject zero or negative values.
- `RAMP_PACKAGE_SCOPE_POLICY_V1` — fixed policy string
  `sipi.p4a-04g.ramp-package-spec-v1.declaration-only`.
- New SI unit types added to `sipi-types`: `Henries`, `Farads`,
  `VoltsPerSecond` (pure additive).

## Scope discipline

Declaration validation only. No waveform construction, no initial-slope
model, no terminal network solve, no IBIS text decoding, no profile
acceptance. The terminal network / termination solve stays unsupported in
the conformance matrix (`package-pin-vt-ramp-network`).

## Mechanical binding

- Charter `docs/baselines/p4a-04g-ramp-package-spec-core.v1.yaml` (schema
  `sipi.p4a-04g.ramp-package-spec-core.v1`).
- Verifier `tools/verify_p4a_04g_ramp_package_spec_core.py` cross-binds
  charter fields (slice scope, validation rules, units, scope policy,
  implementation, admission, non_claims) against the Rust source tokens
  and the PLAN `**P4A-04g` row.
- Tests `tools/test_verify_p4a_04g_ramp_package_spec_core.py`: 7 tests.
- Rust unit tests in `ramp_package_spec_v1.rs`: positive declarations,
  zero/negative rejection per field, fixed policy string.
  `cargo test -p sipi-types -p sipi-ibis`: all passed.

## Non-claims

not_waveform_construction; not_initial_slope_model;
not_terminal_network_solve; not_ibis_text_decoding;
not_profile_acceptance.
