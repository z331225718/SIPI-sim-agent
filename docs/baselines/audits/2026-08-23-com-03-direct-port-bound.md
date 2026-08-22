# COM-03 immutable candidate bound audit

## Scope

This is additive evidence for the frozen 23-scenario COM-03 compare corpus.
It does not replace the preparation observation in
`docs/baselines/com-03-direct-port.v1.yaml`, promote a product capability, or
close the global migration row.

The candidate is commit
`81d19e7fab6621f57890cf6ac6a72bd64fc56b9a` with tree
`a950a66b15f0349b3bda72fc0ef022cdb931f07a`. Each fresh run materialized that
commit from a clean Git archive into an independent temporary source root,
built with an independent `CARGO_TARGET_DIR`, and executed the resulting
comparator binary. Bound mode rejects caller-supplied `--rust-binary`.

## Build identity

The bound report freezes the direct-crate archive inventory SHA, Cargo.lock
SHA, toolchain selector, reproducibility flags, candidate binary SHA, actual
`cargo -Vv` and `rustc -Vv` outputs, and stable-category hashes of build
stdout/stderr. Build logs are reduced to event-category counts before hashing,
so local usernames, temporary directories, and elapsed-time noise cannot enter
committed evidence. The two independent builds produced the same binary and
build identity.

Each bound invocation also creates a fresh 256-bit cryptographic nonce. The
nonce is recorded in the report and manifest but is excluded from the semantic
scenario projection, so it cannot affect the parity result. The aggregate
runner rejects the same path, run ID, nonce, or complete report SHA-256 being
used twice; the bound verifier checks the same bindings in both reports and in
the aggregate.

## Oracle evidence

`tools/run_com_03_direct_bound_oracle.py` invokes the pinned Agent-COM Python
function and CLI plus the binary built from the candidate archive. Two fresh
reports and an additive v2 aggregate contain 23/23 CLI contract matches and
identical scenario outcomes. Reports retain only SHA-256 digests, stable
diagnostic categories, redacted isolation labels, and per-run freshness
nonces; no golden/result payloads or local filesystem paths are committed.

`tools/verify_com_03_direct_bound_port.py --candidate-root ... --rebuild`
recomputes the candidate Git tree, crate inventory, Cargo.lock, source-date
epoch, toolchain, and binary/build identity from a fresh archive build. The
verifier also checks both report hashes, aggregate identity, scenario-set
digest, upstream archive identity, path redaction, and all 23 scenario IDs.

## Non-claims

This evidence is scoped comparator parity only. It does not claim full COM
numeric acceptance, workbook/run/public API behavior, complete argparse or
`dict()` branch coverage, product promotion, global ledger closure, or release
readiness.
