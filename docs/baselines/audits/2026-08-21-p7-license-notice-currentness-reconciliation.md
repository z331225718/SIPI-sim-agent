# P7 License/NOTICE Currentness Reconciliation

## Result

This additive record is **historical/source-drifted and blocked**. It does not
make a legal conclusion or a release decision.

The current baseline is commit `805ebb6bbaf588dec08685be4eb78a8ce2fff563`,
tree `5a378052ea8fdadb8754f22d0a0150088cec6332`. The bound P7-07c report was
recorded for candidate commit `f49849998a9b53fcf56be4a45b2f1fa0418d2588`,
tree `eb14221de2e742f88dcf18ec26e6790c1fb1005b`. The candidate's archived
`Cargo.lock` identity is
`d10679ecbb0884cc3325f9b67afaf9a8d61a9f826c262f6fefd437538df34e99`, while
the current baseline archive is
`12a9656214b2c5cefc4547a83ed9b2ce57eb629e8dbb062fa1d35724a758ce21`.
The toolchain archive remains identical at
`512bedfbbe3c4ef614fbb901b3661f40b4adb701d26c94664e79ca765aa3d109`.

The observer implementation bytes are unchanged at
`addcee98d164d64f36f7179ebb4544f22507b129267bd368014d4910b3b9cbd6`, but its
bound source commit is the historical `02fffadab6cce468d95d404baf89d6b62a6756cc`.
Byte identity alone does not make the old candidate report current.

## Historical closure summary

The P7-07c evidence binds two fresh `--release --locked --offline` builds for
`x86_64-pc-windows-msvc` and package-set digest
`ff34e43289a5ba721ac8f5487894d7afd64481f0e71a795ece822a1fe229e927` with 86
packages: 73 registry and 13 workspace. P7-07d records 86 normalized records:
73 `declared_string_unparsed` and 13 `conflicting_or_unbound`; the other
recorded category counts are zero. These values are retained only as the
hash-bound historical summary.

The referenced build report is 57,976 bytes with SHA-256
`3a5da5b5ec1a64eb523eb1cd4d586156b9d326237d3615afe024078f3542bd29`; the
referenced normalization report is 1,209 bytes with SHA-256
`d023d4680dda293bc2df746f2f2a24b9e40978504b4acaaa5d4b0cb480e15017`. Neither
external byte payload is available to this reconciliation. Therefore the
per-package member list, literal metadata fields, `license-file` material
hashes/lengths, and NOTICE candidate identities cannot be re-inspected. The
record does not infer absence or `not-required` from that gap.

## Verification

The task-specific verifier checks the immutable candidate/tree/lock/toolchain
bindings, the unchanged observer byte identity, the two historical evidence
file hashes, the normalization category counts, and blocked-gate invariants:

```text
python -B tools/verify_p7_license_notice_currentness_reconciliation.py
{"currentness_state": "historical_source_drift_and_external_bytes_missing", "external_inputs_verified": false, "schema": "sipi.p7-license-notice-currentness-reconciliation.v1", "valid": true}
```

The historical evidence verifiers remain separate and no external report was
substituted. `git diff --check` also passes for the task files.

## Exact next inputs for T17

T17 needs a fresh external current-build report for baseline commit/tree
`805ebb6...` (or a later explicitly selected candidate), with its bytes,
SHA-256, byte length, package identities, registry lock checksums, manifest
license/license-file declarations, and per-file `LICENSE*`, `COPYING*`,
`NOTICE*`, and `COPYRIGHT*` SHA-256/length identities. It then needs a fresh
normalization report bound to that report's bytes and package-set hash.

Separately, T17 needs owner/legal inputs for first-party product-path scope,
dependency distribution rights, and NOTICE/distribution review. Cargo license
strings remain declared metadata only; no dependency, first-party path,
NOTICE item, SBOM, or release is approved here.
