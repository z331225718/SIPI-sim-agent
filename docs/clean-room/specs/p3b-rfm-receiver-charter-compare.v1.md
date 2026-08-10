# P3B RFM Receiver Charter Compare v1

This oracle-only gate runs the approved independent receiver evaluator and the
sole product receiver implementation on each of two fresh, hash-verified RFM
handoff replays. It is not a product CLI, artifact route, FFI, or legacy
receiver adapter.

Before evaluating receiver semantics, both sides must consume the same 1024
sample f64le receive-voltage sidecar and 128-byte direct reference-bit sidecar.
The RFM, engine, observer, sidecar, charter, evaluator, product source, lock,
and runner identities are recorded only as hashes and immutable anchors in an
external report. No waveform, bit, decision, fixture, RFM, or external source
bytes enter the SIPI tree or report.

For accepted results, phase, lock status, decision and erasure sequence, error
count, and BER numerator and denominator compare exactly. Center, signed
amplitude, and five frozen taps compare with absolute tolerance `1e-9 V` plus
relative tolerance `1e-6`. A malformed result, provenance mismatch, result
rejection, discrete mismatch, or continuous drift is fail-closed. A rejection
on either side records `receiver_rejected`; even matching rejections never
establish equivalence.

Only two accepted and matching fresh replays may report
`accepted_charter_equivalence_observed`. That conclusion is limited to this
charter and this externally RFM-generated input. It is not retained-receiver
parity, RFM solver parity, general Link/DFE/CDR/BER parity, or a product route.
