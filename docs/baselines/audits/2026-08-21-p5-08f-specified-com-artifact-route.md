# P5-08f specified COM artifact route

P5-08f adds one additive product-owned CLI/API prerequisite for a
caller-specified parameter partition. It consumes one sealed `pulse.f64le`,
runs the existing bounded COM core, and publishes one sealed `result.json`
under explicit output root/id bindings. The historical P5-08e source and its legacy
`sipi.com.run-request.v1` / `sipi.com.run-result.v1` wire are unchanged.

The request schema requires explicit request and pulse identities, consumed
keys, provided values, defaults, and retained unconsumed keys. Values outside
the consumed partition and provided/default overlap are rejected. The route
does not read a workbook, infer a profile, or auto-tune. Its explicit caller
partition is independent of the P5-05g workbook-to-DTO consumer and does not
claim to reuse that path. The response is byte-identical to the published
result payload and reports the input identity plus the explicit consumption
partition.

The response scope is product-owned bounded execution only:
`behavioral_replication=not_claimed`, `agent_com_parity=not_claimed`,
`external_acceptance=blocked`, `ieee_certification=false`, and
`release_evidence=false`. It is not Agent-COM parity, an IEEE certification,
an oracle comparison, a metric tolerance result, or release evidence.

This does not close P5-08. Focused verification binds the new modules, CLI
route, request/result contract, old P5-08e/P5-08d evidence hashes, legacy route
unavailability, and mutation tests.
