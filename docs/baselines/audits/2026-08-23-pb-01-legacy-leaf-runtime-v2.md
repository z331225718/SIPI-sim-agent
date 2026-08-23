# PB-01 Current Legacy Leaf Audit

Date: 2026-08-23  
Status: **open / scoped successor**

This successor record binds the current Rust PB-01 legacy leaf without
rewriting the historical `pb-01-legacy-leaf.v1.yaml` record or its audit.
The leaf is the bounded `sim` path through
`crates/sipi-pybert-direct/src/legacy_runtime.rs` and the explicit Rust CLI.
It uses a restricted data-only YAML/pickle projection and emits the canonical
Python-readable dictionary shape; it does not restore Python classes or start
a Python runtime.

Current bindings:

- runtime SHA-256: `ef1b492feb9d0f18f37862f4690084856c97fa87214e76dd283497a095412ace`
- CLI SHA-256: `8428a01ea6920b6853938cb0627d6e05af7743a80b0ae3ac5e236908c84c16a1`
- boundary SHA-256: `c190daba96a71ebb9b8d60af1c3deb56e76b812a95d73d9c6fa3219ecb7e9eba`
- successor branch inventory: `docs/baselines/pb-01-portable-branch-coverage.v1.yaml`

The current leaf remains open for immutable candidate binding and exact
Python parity. Pure-data portable branches are tracked by the successor
inventory; AMI/IBIS/DLL/GetWave services and exact `PyBertData` class
restoration remain external or quarantined blockers. This audit is not a
license decision, redistribution authorization, promotion, or release claim.
