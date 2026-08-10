# P4B-04a Private AMI Worker Acceptance

Implementation commit: `7fb39e0c2c799c7cea42b3e9e5ca74319de95c97`.

`sipi-ami-worker` is a Windows x64, one-job private worker. A versioned job
contains only job-root-relative, hash-pinned sidecars and bundle entries. The
worker revalidates every identity, raw AMI binding, f64le sidecar, and ABI
revision, then invokes only the P4B-03a host boundary. It checks cancellation
and deadline before Init, before GetWave, and before publication.

Successful output is published through `sipi-artifacts` staging/seal/publish.
Failure, cancellation, bad identities, and supervisor timeout never publish a
success artifact. The test-only supervisor pins the worker executable hash and
AMD64 PE identity before spawning it; on timeout it kills and waits for the
worker process.

Orca audit `msg_48d12a7e2af8` reported **0 P1 / 0 P2**. Verification passed:

```text
cargo clippy -p sipi-ami-worker --all-targets -- -D warnings
cargo test -p sipi-ami-worker
cargo test --workspace
python -B tools/verify_product_boundary.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_release_license_preflight.py
python -B tools/verify_rust_candidate_source_map.py
python -B tools/verify_acceptance_profiles.py
```

Accepted claim: hash-pinned worker process, declared input/bundle closure,
cooperative cancellation, parent timeout recovery, and atomic successful
artifact mechanics conform against a product-owned mock DLL on Windows x64.
This is not a sandbox, a complete dynamic dependency closure, proof that Close
runs after forced termination, vendor interoperability, AMI/IBIS parity, or a
public CLI/default runtime route.
