# P3A Matched S2P Acceptance Contract v1

This project-owned acceptance policy fixes one external-only comparison target
for the selected `channel_16ghz_3db` asset. It is an observer/comparator
contract, not a product input format or a source of implementation material.

The only observable is a discrete voltage-gain kernel `g[n]`. The observer
uses a matched launched-voltage DFT probe: `x[0] = 1 V` and all remaining
periodic samples are zero. Thus `y[n] = g[n]` in volts and `g[n]` has units
V/V. This is not a claim about a continuous-time impulse.

The kernel uses the independently specified two-port, real-50-ohm matched
`S21` contract. Its 201-bin one-sided table is Hermitian-completed to
`N = 400`; `dt = 25 ps`; the forward sign is negative and the inverse has
`1/N` normalization. Comparison is strictly index-aligned, finite, and has no
shift, trimming, resampling, windowing, conditioning, or interpolation. Each
sample permits `1e-9 + 1e-5 * max(abs(candidate), abs(observer))` V/V.

Before a numerical conclusion, an external clean observer must identify its
implementation and environment, run twice from fresh materializations, and
obtain identical kernel hashes. Reports retain hashes and error metrics only.
The historical M5B PyBERT handoff lane is explicitly excluded because its
configuration applies transformations outside this policy.

The Rust implementation side receives only the independent matched-S2P
specification. It may not read the external asset, invoke Python, or use this
observer output as a fixture or fallback.
