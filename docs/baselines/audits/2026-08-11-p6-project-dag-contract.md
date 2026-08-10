# P6-01 Declarative Project DAG Contract Acceptance

Implementation commit: `4fca0a3`.

`sipi.project.v1` is a product-owned, declarative wire contract. Its planner
accepts only the closed `tran.rc_pulse` and `link.causal_fir` node catalog,
requires exact named-port contract identifiers, a nonzero resource policy, an
explicit 32-byte seed, and at least one requested output. It rejects duplicate
or missing bindings, unknown ports and kinds, contract drift, cycles, and
nodes that do not reach a requested output. It returns only a deterministic
topological order and a domain-separated SHA-256 declaration digest.

The first Orca review (`msg_85c7d1f95680`) found two release-gate defects:
the product inventory had not yet been refreshed and the newly exported schema
was missing its tracked baseline/inventory entry. This acceptance changeset
refreshes the P0 inventory and adds `sipi.project.v1` to the same schema
baseline/inventory/discovery path used by the existing contract schemas. The
CLI exposes schema discovery only; it does not add a `sipi project` command.

The remediation review (`msg_230ba8b48887`) also found a pre-existing P1-11
schema-registry drift: discovery exposed the causal-FIR request in the slot
whose tracked baseline is `sipi.link-plan.v1`, and four older inventory hashes
included the terminal LF despite the gate correctly hashing exported bytes.
This changeset restores the registry to the inventory's stable IDs and updates
those four hashes to the documented no-final-LF convention. The causal-FIR
request remains an internal run-input contract; this does not add execution or
a project CLI route.

The P1-11 locked Windows build/install/schema-drift gate then passed for
`74ea2fcf3b62abd32ccc36388413fb97396b20c4`. Its external report records the
locked toolchain, installed executable, all six schema exports, and smoke
commands; it remains provisional release evidence rather than a release claim.

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

This accepts a contract and validation planner only. It does not establish
project execution, cross-domain edges, artifacts, cancellation/retry/cache,
AI project execution, profile accuracy, a default route, or release readiness.
