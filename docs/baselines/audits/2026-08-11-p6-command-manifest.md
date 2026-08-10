# P6-05a Command Manifest Acceptance

Implementation commit: `a17e486`.

`sipi.command-manifest.v1` now owns the discoverable command surface. Existing
product handlers remain available; capabilities derive their limited TRAN and
channel state from that manifest. Recognized channel, AMI, COM, project,
compare, and report routes are unavailable by policy, return a structured
`capability_unavailable` result, and do not consume stdin or touch runtime,
artifacts, or external assets.

The change does not add project execution, a channel resolver, AMI/COM runtime,
comparison, report viewing, file/URL input, or any default fallback.

The single Orca review (`msg_b50de33a645f`) found `0 P1 / 0 P2`. It verified
the manifest/dispatcher invariants, unavailable short circuit, retained handler
coverage, nonclaims, CLI tests, and clean-room/P0 registrations.

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
