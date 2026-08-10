# P6-02a Fixed TRAN-to-Link Edge Acceptance

Implementation commit: `d3c7bea`.

`sipi-pipeline` now admits one typed, in-process cross-domain edge:
`tran-rc-pulse-v1` source `voltage_in` to a DirectLaunch causal-FIR Link
stimulus. The admission boundary requires the fixed explicit four-sample time
axis (`0`, `1`, `2`, `3` microseconds) and preserves the four voltage samples
without interpolation, padding, trimming, delay, sign, or unit changes. The
caller must supply an existing causal FIR whose interval is exactly one
microsecond; Link remains DirectLaunch with CTLE/FFE bypass.

The composition invokes only the existing fixed TRAN solver and causal-FIR
convolution. It adds no project executor, CLI command, artifact publisher,
worker, S2P periodic-kernel handoff, RFM/IBIS/AMI/COM route, or profile
certification.

The single Orca review (`msg_2cda7f7d7177`) found `0 P1 / 0 P2`. It verified
source selection, exact axis/interval admission, no I/O route, resource-limit
failure behavior, clean-room material integrity, and P0 coverage.

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
