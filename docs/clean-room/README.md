# Clean-Room Registry

`clean-room-register.v1.yaml` records the declared material boundary for a
future Rust clean-room scope. It is a fail-closed provenance gate, not proof
that a person or model has never read a source file.

The current register is `provisional`: every principal is an assignment
placeholder, the only scope is a project-owned process template, and there are
no attestations. It cannot authorize a release or promote any quarantined
native candidate.

For a domain scope, the observer, specification author, implementer,
comparator, and auditor must be assigned before use. The implementer allowlist
may contain only `public_standard`, `mit_source`, or independently-authored,
fully-declared `independent_spec` material. A specification cannot conceal a
prohibited ancestor through `derived_from`.

Run `python -B tools/verify_clean_room_register.py` to validate the registry.
Strict mode additionally requires an assigned identity and signature reference
for each attestation; release mode remains blocked until all scopes are strict,
audited, and mapped to product-candidate paths.
