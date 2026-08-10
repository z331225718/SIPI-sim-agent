# P3B RFM Receiver Charter Compare

Commit `bc27624` adds the external-only comparison gate between the independent
fixed-receiver charter evaluator and the sole product receiver implementation.
It requires two fresh, hash-verified RFM handoff replays and records only
immutable anchors, sidecar hashes, result hashes, and comparison metrics in an
external report.

The gate compares accepted results exactly for phase, lock state, decision and
erasure sequence, error count, and BER numerator/denominator. Center, signed
amplitude, and five frozen taps use the approved `1e-9 V + 1e-6 relative`
tolerance. A rejection from either side is explicitly `receiver_rejected`, not
an equivalence pass.

The Windows execution produced external report
`C:\\Users\\z3312\\code\\.sipi-rfm-receiver-charter-compare-report.json` with
status `receiver_rejected`. Both fresh replays had the already accepted,
identical waveform hash `e1c18a491d4fd90cfae3ddae0532ab9f3ca529127365cca9fb04357581bff4e3`
and reference-bit hash
`aebf405592dd2d2a2e5b4a256e4a7167b6189b5272cd5cbced17a8ba139c2616`.
Both independent implementations rejected that input for the charter's unique
phase-margin gate: evaluator `cdr_ambiguous`, product `CdrAmbiguous`.

Orca read-only audit `msg_cb9cc8c74034` found `0 P1 / 0 P2`. It verified the
strict provenance and sidecar validation, result-shape checks, accepted-result
comparison semantics, test-only product runner, and the fact that matching
rejections cannot be reported as equivalence.

The required profile is therefore blocked at
`blocked_cdr_ambiguous_under_approved_charter`. This is not retained Python or
old-Rust receiver parity, RFM solver parity, Link parity, general DFE/CDR/BER
parity, or a product route. Any change to the approved phase-acquisition
semantics needs a separate owner amendment before another acceptance attempt.
