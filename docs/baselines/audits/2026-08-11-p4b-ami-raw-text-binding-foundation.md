# P4B-02b0 AMI Raw Text Binding Foundation Audit

## Scope

Reviewed commit `a741a85`, which adds an in-memory binding between exact
caller-provided raw AMI UTF-8 bytes and their bounded structural AST.
`parse_and_bind_v1` is the only public construction path. `verify_binding_v1`
first requires byte-for-byte equality, then reparses with explicit limits and
requires structural identity.

## Result

Orca reviewer message `msg_957a50f186b6` reported **0 P1 / 0 P2**.

The reviewer confirmed that the raw bytes and AST fields remain private, CRLF
versus LF drift is rejected, and a forged AST is rejected. The crate remains
std-only and continues to expose `RulesUnavailable` for semantics.

## Verification

```
cargo fmt --check -p sipi-ami-text
cargo test -p sipi-ami-text --locked
cargo clippy -p sipi-ami-text --all-targets --locked -- -D warnings
.venv\Scripts\python.exe -B tools\verify_product_boundary.py
.venv\Scripts\python.exe -B tools\verify_clean_room_register.py
.venv\Scripts\python.exe -B tools\verify_release_license_preflight.py
.venv\Scripts\python.exe -B tools\verify_rust_candidate_source_map.py
.venv\Scripts\python.exe -B tools\verify_acceptance_profiles.py
```

All checks passed. This is only an exact raw-text binding boundary. It does
not provide a provenance hash or file identity, AMI parameter/default/reserved
or model-specific semantics, IBIS binding, DLL/ABI hosting, runtime execution,
or external compatibility.
