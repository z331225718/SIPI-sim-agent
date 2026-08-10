# P6-03a Fixed TRAN-to-Link Edge Record Acceptance

Implementation commit: `4aea715`.

`sipi-pipeline` now records and recomputes the identity of its sole typed,
in-process edge: `tran-rc-pulse-v1` `voltage_in` to the causal-FIR
DirectLaunch input. The specialized record fixes the producer and consumer
ports, the single-ended-voltage-to-common-reference map, seconds/volts units,
and the admitted four-sample axis (`t0=0`, `dt=1 microsecond`, `N=4`).

All digest inputs use a domain-separated binary SHA-256 encoding with ordered
finite `f64` bit patterns. The record binds the launch identity, DirectLaunch
plus bypass policy, FIR interval/coefficients and limits, and the full
received waveform. Verification recomputes every field from the typed producer,
consumer policy, and output. It is not a generic edge system, published
artifact, executor, cache, or code-provenance record.

The single Orca review (`msg_1430e8a7b3a3`) found `0 P1 / 0 P2`. It verified
the canonical encoding (including `-0.0` identity), producer/consumer digest
binding, policy/output coverage, axis rejection, lack of I/O or external
assets, record-tampering rejection, and the clean-room/P0 registrations.

Verification passed:

```text
cargo test --workspace
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
python -B tools/verify_product_boundary.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_release_license_preflight.py
python -B tools/verify_rust_candidate_source_map.py
python -B tools/verify_acceptance_profiles.py
```
