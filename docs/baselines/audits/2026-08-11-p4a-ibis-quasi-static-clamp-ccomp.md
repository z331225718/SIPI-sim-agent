# P4A-04e IBIS Quasi-Static Clamp Plus C_comp Audit

Date: 2026-08-11

## Scope

Commit `ba7f913` adds a product-owned, memoryless relation that combines the
selected typed ground/power DC clamp tables with an ideal continuous `C_comp`
current. The caller supplies both independent clamp drives and an explicit
SIG-to-REF voltage derivative.

## Reviewer Result

Orca review `msg_dfb46e7cfa64` reported zero P1 and zero P2 findings.

## Verified Boundary

- `C_comp` must be finite and non-negative. The state derivative must be
  finite; derived capacitive and total-current overflow reject fail-closed.
- DC table evaluation occurs first, so an out-of-domain clamp drive rejects
  before a capacitive or total response is returned.
- The response is the signed sum of the two memoryless clamp currents and
  `C_comp*d(V(SIG)-V(REF))/dt`. It neither derives supply/REF/PVT data nor
  derives a slope from samples.
- The existing external profile remains a DC-only six-point comparison. It is
  not used as transient evidence.

## Verification

`cargo fmt -p sipi-ibis -- --check`, `cargo clippy -p sipi-ibis --all-targets
--locked -- -D warnings`, `cargo test -p sipi-ibis --locked`, and all five P0
verifiers passed. The 18 library tests include zero-capacitance DC equivalence,
capacitive sign/linearity, independent clamp drives, and invalid/overflow/DC-
first rejection paths.

## Limits

No time step, state, integration method, waveform, supply derivation, package,
pin network, PVT, V-T, ramp, AMI, file I/O, CLI, or external transient parity
is included.
