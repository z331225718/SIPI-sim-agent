# P3A-11 Matched S2P CLI Current-Evidence Rebinding

## Scope

P3A-10 remains an immutable historical attestation for its candidate. Commit
`4bdd4d7b2c6b60c06f8721e70608896ab90f8222` changes the whole `sipi-cli`
tree, so P3A-10 cannot represent this executable without a fresh replay.

The v2 evidence record binds a clean archive build of that commit, the five
product source trees consumed by `channel run`, `Cargo.lock`, and a new
external-only report. The report records two fresh custody replays of the
pinned `channel_16ghz_3db.s2p` Git blob through the standard-DFT observer and
the bounded CLI process contract.

## Result

Both observer replays produced the same 400-sample kernel at 25 ps. The clean
CLI build returned one successful JSON response with empty stderr; its input
identity, 201-point 100 MHz real-50-ohm metadata, and kernel comparison all
met the frozen tolerance. The report and evidence store hashes and aggregate
metrics only.

## Non-Claims

This restores evidence only for the exact Windows `channel_16ghz_3db` matched
periodic-kernel CLI path. Ordinary caller input remains unattested. It does not
establish general Touchstone/S-parameter handling, reflection, termination,
Link, eye/BER, artifact, or release behavior.

## Review

One Orca OpenCode reviewer examined the staged P3A-11 diff. Its final result
was 0 P1, 0 P2, and one staging-hygiene P3: the direct-import test change had
not yet been staged. That change is included before this record is committed.
The reviewer also confirmed that the current TRAN row remains conservatively
specified because its current external evidence is stale and the locked oracle
executable was unavailable for a fresh rebind.
