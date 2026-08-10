# P6-04a Fixed TRAN-to-Link Cooperative Attempt Acceptance

Implementation commit: `567a76f`.

The admitted fixed TRAN-to-Link edge can now execute one cooperative attempt
within a caller-owned `RunContext`. It shares the existing TRAN and causal-FIR
numerical cores, checks cancellation/deadline boundaries throughout, and
reserves checked work plus retained-sample byte estimates before simulation.
Only a completed runtime success returns attempt `1`, its received waveform,
and the P6-03a edge record.

Cancellation, deadline, resource, validation, or numerical failure returns no
attempt result or record. This adds no retry, cache, artifact publication,
worker, project executor, CLI route, or external asset path.

The single Orca review (`msg_2803c41ee620`) found `0 P1 / 0 P2`. It verified
result construction only after success, shared numerical cores, terminal runtime
state propagation, pre-computation resource admission, absence of broader
execution features, and clean-room/P0 registrations.

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
