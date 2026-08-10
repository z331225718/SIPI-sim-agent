# P3B Link Unsupported Boundary

Commit `a0dfdac` freezes the current `sipi.link.causal-fir-request.v1`
capability boundary in a machine-verified ledger. Direct launch, causal FIR,
and explicitly selected CTLE/FFE bypass are the only executable Link stages.

The CLI tests inject seed, PRBS, noise, jitter, DFE, CDR, BER, and a non-bypass
CTLE stage into an otherwise valid Link request. Every case rejects at the wire
boundary with exit code 3 and creates no success artifact. The slice adds no
RNG, seed, PRBS, noise, jitter, DFE, CDR, or BER product API or default.

The fixed receiver remains a library-only, profile-scoped capability blocked by
`blocked_cdr_ambiguous_under_approved_charter`; it is not a Link CLI stage or
required-profile acceptance.

Orca read-only audit `msg_347c9ee94237` found `0 P1 / 0 P2`. It verified the
ledger/verifier coverage, fail-closed CLI behavior, absence of new runtime
semantics, and P0 boundary integrity.

This completes P3B-05a only. Real deterministic seed, noise, jitter, and
receiver-stage semantics remain blocked until an owner supplies a required
profile, injection location, units/distribution or time-warp model, seed/replay
contract, observables, and tolerances.
