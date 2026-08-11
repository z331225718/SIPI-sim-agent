# P3A-12 Matched S2P CLI Current-Evidence Rebinding

## Scope

P3A-11 remains an immutable attestation for commit
`4bdd4d7b2c6b60c06f8721e70608896ab90f8222`. Commit
`58802b6d4ec74fc653e2a294821006aa4312b196` changes the `sipi-cli` and
`sipi-contracts` trees, so that record cannot silently attest to the current
command-line executable.

The v3 record binds a clean archive build of the current commit, its five
channel-run product source trees and `Cargo.lock`. The external-only report
replays the pinned Git-object S2P input in two fresh custody directories with
the independent standard-DFT observer, then checks the bounded CLI process
contract and every kernel sample against the frozen tolerance.

## Result

Both observer runs produced the same 400-sample, 25 ps kernel. The clean
Windows CLI build returned one successful JSON response with empty stderr; its
input identity, 201-point 100 MHz real-50-ohm metadata, and per-sample kernel
comparison passed. The evidence stores only identity hashes and aggregate
error metrics.

## Non-Claims

This is evidence only for the exact Windows `channel_16ghz_3db` matched
periodic-kernel CLI path. Ordinary caller input remains unattested. It does not
establish general Touchstone/S-parameter handling, reflection, termination,
Link, eye/BER, artifact, or release behavior.
