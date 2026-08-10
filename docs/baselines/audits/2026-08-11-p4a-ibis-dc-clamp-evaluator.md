# P4A-04b IBIS DC Clamp Evaluator Audit

## Scope

Reviewed commit `3950047`, which adds the product-owned typed DC clamp
evaluator to `sipi-ibis`. It evaluates two caller-supplied signed I-V tables
through explicit ground and power drives. It neither reads nor decodes IBIS
text or any external asset.

## Result

Orca reviewer message `msg_6c7ff9ccc63f` reported **0 P1 / 0 P2**.

The reviewer confirmed strictly increasing finite table construction, exact
knot/interior linear evaluation, branch-specific out-of-domain rejection, and
non-finite result rejection. The core makes no supply, polarity, or power-drive
offset inference. Product tests use only synthetic data.

## Verification

```
cargo fmt --check -p sipi-ibis
cargo test -p sipi-ibis --locked
cargo clippy -p sipi-ibis --all-targets --locked -- -D warnings
.venv\Scripts\python.exe -B tools\verify_p4a_ibis_input_typ_static_acceptance.py
.venv\Scripts\python.exe -B tools\verify_product_boundary.py
.venv\Scripts\python.exe -B tools\verify_clean_room_register.py
.venv\Scripts\python.exe -B tools\verify_release_license_preflight.py
.venv\Scripts\python.exe -B tools\verify_rust_candidate_source_map.py
.venv\Scripts\python.exe -B tools\verify_acceptance_profiles.py
```

All checks passed. This is not an IBIS text decoder, package/pin/PVT/V-T/ramp
implementation, external profile comparison, AMI integration, or runtime
capability.
