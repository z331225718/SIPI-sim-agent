# P5-08e bounded COM artifact execution

P5-08e adds one product-owned composition consumer. It consumes exactly one
sealed `pulse.f64le` payload through `ArtifactRoot::consume_exact_verified_v1`,
uses the DTO and consumption report already produced by P5-05g, executes the
existing P5-08b COM core, publishes one `result.json` artifact at the existing
request root/id binding, and verifies that output through the unchanged P5-08d
metadata report path.

The input identity carries an artifact id and exact lowercase manifest
SHA-256 outside the legacy request. This preserves `sipi.com.run-request.v1`
and `sipi.com.run-result.v1` byte contracts. The pulse payload is little-endian
finite `f64`, is the only admitted file in the input artifact, and is limited
to 524288 bytes. The request is limited to 65536 bytes before JSON parsing or
artifact access; an oversized request is rejected with no artifact I/O and no
output. The result payload is limited to 16384 bytes. Admission and
input verification complete before any output artifact is created. Every
request `params` scalar must also exactly match the corresponding consumed
P5-05g DTO value, so request metadata cannot disagree with execution inputs.
Publication uses the existing immutable `publish_new` behavior.

The emitted product report states
`product_owned_bounded_execution_complete`, while behavioral replication is
`not_claimed` and external acceptance remains
`blocked_missing_authoritative_reference`. This is a real local semantics
consumer, not an IEEE certification, external COM oracle comparison, metric
tolerance result, hostile-writer boundary, ownership/signature proof, release
evidence, or public `com.run` CLI admission.

Focused checks cover the successful pulse-to-COM-to-result path, request-budget
rejection before artifact I/O, exact manifest rejection, non-finite pulse rejection, request/DTO disagreement,
invalid/unadmitted requests, identity validation, the unchanged P5-08d
verifier, and `sipi-com` clippy/tests.
