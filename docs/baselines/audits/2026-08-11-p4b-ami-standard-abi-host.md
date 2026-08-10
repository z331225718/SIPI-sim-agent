# P4B-03a AMI Standard ABI Host Acceptance

Implementation commit: `b51c0251014a4eb23e2569a1ccff50f63c2a523c`.

This slice adds the clean-room `sipi-ami-host` Windows x64 ABI boundary. It
requires an absolute caller DLL path, a SHA-256 identity, an AMD64 PE header,
and required `AMI_Init`/`AMI_Close` exports before loading. It accepts only a
revalidated `AmiTextBindingV1`, uses strict `status == 1`, bounds matrix and
waveform buffers, and requires an explicit clock sentinel.

The product-owned mock DLL test covers a normal Init/GetWave/Close lifecycle,
hash and relative-path rejection, missing exports, Init/GetWave failure,
invalid output clocks, invalid output waveform, missing sentinel, and Close
failure. No vendor DLL, IBIS asset, AMI semantic input, or external output is
used or recorded.

Orca audit `msg_dea46936dffa` reported **0 P1 / 0 P2**. Verification passed:

```text
cargo clippy -p sipi-ami-host --all-targets -- -D warnings
cargo test -p sipi-ami-host
cargo test --workspace
python -B tools/verify_product_boundary.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_release_license_preflight.py
python -B tools/verify_rust_candidate_source_map.py
python -B tools/verify_acceptance_profiles.py
```

Accepted claim: clean-room Windows x64 standard ABI host mechanics and
product-owned mock-DLL conformance are ready. This is not a claim of vendor
interoperability, AMI parameter semantics, IBIS+AMI composition, numeric
parity, worker isolation, Linux/macOS support, or a default CLI route.
