# P4A-01e Selected Differential R-C Load Audit

Date: 2026-08-11

## Scope

Commit `f2017bb` adds `sipi-rx-load`, a product-owned continuous constitutive
relation for the selected P/N/REF receive load: a 100 ohm P-to-N resistor and
one 1 pF capacitor from each leg to REF.

## Reviewer Result

Orca review `msg_d07c5640bbd1` reported zero P1 and zero P2 findings.

## Verified Boundary

- Inputs are caller-supplied, finite P-to-REF and N-to-REF voltages and
  continuous derivatives. The evaluator does not derive slopes from samples.
- Terminal-current signs are explicit and KCL-balanced. The resistor branch is
  passive and the two capacitor branches retain their independent REF paths.
- Derived non-finite values reject without returning a partial result.
- The crate has no integration method, state, channel return binding, network
  resolver, generic R/C builder, IBIS, AMI, file I/O, CLI route, or default
  route.

## Verification

`cargo fmt -p sipi-rx-load -- --check`, `cargo clippy -p sipi-rx-load
--all-targets --locked -- -D warnings`, `cargo test -p sipi-rx-load --locked`,
and all five P0 verifiers passed. The crate's five unit tests cover DC,
common-mode and differential ramps, linearity, KCL, finite input rejection,
and derived overflow rejection.

## Limits

This is not an electrical-load solve or channel termination. A separate
profile must still bind REF, choose transient integration, and establish an
acceptance comparison before any channel or RX runtime claim.
