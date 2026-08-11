# P3A Matched-S2P Evidence Reconciliation

The selected `channel_16ghz_3db` profile's policy and observation records
remain historical preflight documents. They intentionally retain
`specified_not_executed` and pending wording rather than changing the meaning
of their v1 schema.

For product source commit `a2a67328241d383f74a88f66a5841cb4e1c33865`, the
external-only comparator re-materialized the pinned Git blob and used a
two-run standard DFT observer. The independently archived product runner
returned the matching 400-sample periodic V/V kernel. The retained external
report digest is bound by
`channel-s2p-matched-external-compare-evidence.v1.yaml`; no S2P text, kernel
array, executable, or absolute path is tracked.

The largest error was `9.796444254764336e-15 V/V` at index 365, and the
all-sample maximum normalized error ratio was `7.78280821086894e-6`, within the
frozen `1e-9 V/V + 1e-5 relative` gate. This promotes only the required
external matched-kernel core to profile-scoped acceptance. `channel run`
continues to label all caller input unattested, and this record does not claim
CLI end-to-end acceptance, general Touchstone, Link behavior, or release
readiness.
