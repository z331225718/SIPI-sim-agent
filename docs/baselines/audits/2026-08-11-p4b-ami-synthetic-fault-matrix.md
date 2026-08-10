# P4B-06 Synthetic AMI ABI Fault Matrix Acceptance

Implementation commit: `dd6a3cc`.

The Windows x64 product-owned mock DLL now records its private lifecycle only
inside the integration test. The table-driven matrix covers Init failure,
GetWave writing partial data before failure, a non-finite clock result, and a
Close failure. Each row checks the exact Init/GetWave/Close sequence and that
no success artifact is published.

The existing supervisor timeout row remains a process-recovery check only. It
does not assert that a killed worker calls Close.

Verification passed:

```text
cargo test -p sipi-ami-worker
cargo clippy -p sipi-ami-worker --all-targets -- -D warnings
cargo fmt --check
python -B tools/verify_product_boundary.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_release_license_preflight.py
python -B tools/verify_rust_candidate_source_map.py
python -B tools/verify_acceptance_profiles.py
```

One Orca reviewer reported 0 P1 and 0 P2 in `msg_d112bb0dddbb`.

This accepts mock-only failure atomicity. It does not establish real vendor DLL
fault coverage, a security sandbox, complete closure, AMI numerical parity, or
any default runtime route.
