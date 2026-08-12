# P3C PRBS9 Metric Artifact CLI v1

`sipi compare prbs9-metrics --stdin --artifact-root <root>` is a narrow
product route for the fixed PRBS9 v2 metric profile. Its stdin is only the
versioned request schema, the fixed contract digest, and two opaque published
artifact identities. It accepts no waveform values, paths, URLs, axis, seed,
tolerance, alignment, or profile override.

Each selected artifact must be an already-published SIPI artifact with exactly
`success.json`, `waveform.json`, and `waveform.f64le`. The product consumes the
two payload files once into owned memory and verifies that same read against
the requested manifest digest. The root remains a caller-selected SIPI
published root with the P1 v1 no-hostile-concurrent-writer assumption; it is
not a hostile-writer or provenance boundary.

`waveform.json` freezes the v2 contract hash, differential-voltage quantity,
unit, timebase profile, 49056 samples, little-endian binary64 encoding and
the exact 392448-byte payload identity. Both complete sealed artifacts must
verify before the existing strict-grid waveform, sampled-eye, and TIE core is
called. Any extra, missing, hash-mismatched, oversized, nonfinite, or malformed
input is rejected without a partial report.

The response exposes only opaque artifact identities, manifest and payload
digests, core metric values and fixed non-claims. It never returns a root,
internal file name, or waveform sample. Local integrity does not bind ADS,
external reference provenance, a candidate acceptance, receiver stage, AMI
runtime, statistical-eye contour, release, or promotion.
