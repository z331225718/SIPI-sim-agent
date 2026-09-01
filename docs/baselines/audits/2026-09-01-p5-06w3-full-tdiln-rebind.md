# P5-06w3 Full TDILN Rebind

## Scope

This record rebinds the named TDILN intermediate checkpoint to candidate
`b456e9d57b2449787e22cdefdad6c0edc70d69dc`, which includes the sparse
PAM-PDF production optimization. It uses the same pinned Agent-COM source
archive and the original 13-workbook corpus as the preceding checkpoint.

## Evidence

Two fresh immutable archive replays are recorded in:

- `docs/baselines/p5-06-tdiln-array-current-replay-01.v1.json`
- `docs/baselines/p5-06-tdiln-array-current-replay-02.v1.json`
- `docs/baselines/p5-06-tdiln-array-current-replay-aggregate.v1.json`

The aggregate requires exact Rust semantic repeatability, two fresh replay
records, and Rust no-slower-than-MATLAB timing for every workbook and in
total. It accepts all 28 TDILN package cases for `time_s` as exact f64 little
endian bytes and the other five named vectors at `5e-12 + 1e-9 relative`.

The best MATLAB source-core total was `1753.3723475s`; the worst Rust
production-process total was `195.89563529996667s`, a floor of
`8.950543205391662x`. The slowest per-workbook floor was
`5.785408685678222x`.

## Boundaries

The Rust channel path remains raw FD-to-TD impulse processing and does not fit
S-parameters. This is a named intermediate-array and performance checkpoint;
it does not claim full result-graph parity, complete warning parity, a public
TDILN-sidecar wire, release readiness, or IEEE certification.
