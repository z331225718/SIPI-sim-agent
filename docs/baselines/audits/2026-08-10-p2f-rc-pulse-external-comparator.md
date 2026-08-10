# P2-06a RC/PULSE External Comparator Audit

## Scope

Commit `ed776264e5f43d66db6dfcfb7e9e084d9f827757` adds a feature-gated,
non-default product result exporter and an observer-side external comparator
for the fixed `tran-rc-pulse-v1` profile.

The comparator materializes `rc.cir` only from the accepted external Git
object, verifies executable hashes and oracle build identity, requires two
fresh oracle runs with equal f64le array hashes, and writes an external report
containing hashes and comparison metrics only. It does not route through the
`sipi` CLI, parse netlist text in product code, retain the fixture, or create a
legacy fallback.

## Live Gate Evidence

Windows x86_64 external report:
`%TEMP%\\sipi-p2-tran-rc-pulse-compare-ed776264.json`

- Oracle: `agent-spice-sim` SHA-256
  `3acd577da5b1539bf072792af3c97687926b7489d1d3406e3b675ceb577125c`,
  build identity `agent-spice@2cc92316`, release, clean,
  `x86_64-pc-windows-msvc`.
- Product harness: SHA-256
  `1288ac03d3db94ac415ded0bcdfc254c7160930c74f9f12ce8eb15023557bd7c`,
  product commit `ed776264e5f43d66db6dfcfb7e9e084d9f827757`.
- Oracle fresh-run hashes matched exactly for time, `v(in)`, and `v(out)`.
- Time and `v(in)` maximum error were zero. `v(out)` maximum absolute error
  was `9.963737488231927e-07 V`; maximum relative error was
  `4.986852193371661e-04`, both within the frozen policy.

This is acceptance only for the four indexed samples of this fixed RC/PULSE
profile. It does not claim netlist parsing, `.op`, `.ac`, general TRAN/SPICE,
or release readiness.

## Verification

- `cargo fmt --all -- --check`
- `cargo clippy -p sipi-tran --all-targets --features rc-pulse-harness --locked -- -D warnings`
- `cargo test --workspace --locked`
- `python -m unittest tools.test_compare_tran_rc_pulse tools.test_verify_tran_rc_pulse_acceptance`
- P0 boundary, clean-room, release-preflight, and Rust source-map verifiers

## Independent Audit

OMP request `msg_e1caf6bfff5f`; conclusion `msg_12289cf75afd`: **0 P1 / 0
P2**.
