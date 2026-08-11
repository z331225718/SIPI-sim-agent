# P3A-10 Matched S2P CLI Current-Evidence Rebinding

## Scope

The historical P3A-09 CLI attestation remains unchanged. Commit
`d875433d07a58e3f8821b2eeaa5af5ca25f5caf2` changed the `sipi-cli` tree, so
the historical executable identity cannot silently represent the current CLI.

The current evidence record binds a clean archive build of that commit, the
five product source trees consumed by `channel run`, `Cargo.lock`, and a new
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
