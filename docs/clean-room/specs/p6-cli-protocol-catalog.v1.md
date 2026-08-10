# P6-06a CLI Protocol Catalog v1

`sipi.command-protocol-catalog.v1` refines the command manifest into a
table-driven contract for every currently available route. It is derived from
the same static command descriptors as `commands --json`; it cannot make an
unavailable route executable.

Each catalog record has the command id, transport, request-schema identifier,
SHA-256 of the product-owned request schema bytes when there is a request,
response kind, optional minimal example id, required command options, expected
success exit code, and the applicable diagnostic contract. Static discovery
commands explicitly have no request example. Every `stdin_json_v1` route has
exactly one `product-owned-minimal-v1` example, constructed from validated Rust
wire types rather than copied fixtures or result snapshots.

`sipi protocols --json` returns the catalog. `sipi example <command-id> --json`
returns only the corresponding request body and its identity metadata. It never
creates an artifact, starts a runtime, accesses a file or URL, or returns a
simulation result. TRAN and Link examples still require the caller to supply
an external artifact root and artifact id when invoking their actual run
commands.

The catalog is fail-closed: every available manifest entry must have exactly
one profile; every stdin request must have a registered request schema and
example; every profile must point back to an available command; and request
schema hashes are recomputed from the contract authority. Unknown commands,
static commands, and unavailable commands do not have examples.

This is a discoverable protocol contract, not a generic schema service, file or
URL API, project executor, external comparator, artifact viewer, or a claim
that Channel, AMI, COM, report, or project workflows are available.
