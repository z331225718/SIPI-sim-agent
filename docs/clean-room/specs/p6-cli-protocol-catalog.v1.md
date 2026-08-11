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
either one `product-owned-minimal-v1` example constructed from validated Rust
wire types, or explicit caller-owned admission bindings when a runnable example
would need a local artifact root. No example is copied from fixtures or result
snapshots.

For an AI client, a `constructible` request is only a request that passes the
product schema and cross-field admission. It becomes `admitted` only after all
catalogued caller bindings have been supplied; TRAN and Link require the
explicit invocation bindings `/invocation/artifact_root` and
`/invocation/artifact_id`. It is `executed` only after the ordinary runtime
path succeeds. Neither an example nor a constructible request promises that a
machine-local artifact destination is usable.

`sipi protocols --json` returns the catalog. `sipi example <command-id> --json`
returns only the corresponding request body and its identity metadata. It never
creates an artifact, starts a runtime, accesses a file or URL, or returns a
simulation result. TRAN and Link examples still require the caller to supply
an external artifact root and artifact id when invoking their actual run
commands.

`report.inspect` has no self-contained example because it must name a
caller-owned, already-published artifact root. Its catalog profile exposes the
required `/artifact_root` and `/artifact_id` bindings and request-schema digest,
but does not make a root or artifact executable by default. Only the verified
integrity metadata projection is available; payload preview, external
provenance, and report export remain unavailable.

The catalog is fail-closed: every available manifest entry must have exactly
one profile; every stdin request must have a registered request schema plus an
example or explicit caller bindings; every profile must point back to an
available command; and request schema hashes are recomputed from the contract
authority. Unknown commands, static commands, and unavailable commands do not
have examples.

The catalog also publishes the finite diagnostic-code registry. Every process
diagnostic carries a stable `code`, `stage`, optional JSON `pointer`, and
`rule_id`; clients can branch on those fields without parsing the human message
or an operating-system error. The registry deliberately does not include
arbitrary paths, external runtime output, input echoes, or foreign error text.

This is a discoverable protocol contract, not a generic schema service, file or
URL API, project executor, external comparator, payload viewer, or a claim
that Channel, AMI, COM, general reporting, or project workflows are available.
