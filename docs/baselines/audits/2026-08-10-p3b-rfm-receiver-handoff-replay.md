# P3B RFM Receiver Handoff Replay

Commit `f6d5a33` supplies the Windows-only, external-only replay gate for
`channel-rfm-block-2-current-drive-v1`.

The gate ran from a clean PyBERT `199696a` checkout and materialized the pinned
`f6ba031` `block_2.rfm` Git object. It verified the locked Agent-Spice release
executable SHA-256 `111ff6e...928dc` and build-info, then performed two fresh
1024-sample, 1 ps, port-1-to-port-2, current-sign-minus-one observer runs.
The external receive-voltage waveform hash was identical in both runs:
`e1c18a491d4fd90cfae3ddae0532ab9f3ca529127365cca9fb04357581bff4e3`.
The separately attested 128-byte reference-bit sidecar hash was likewise
identical: `aebf405592dd2d2a2e5b4a256e4a7167b6189b5272cd5cbced17a8ba139c2616`.

The temporary sidecars were decoded only by the ignored
`receiver_observer_runner` Rust test target. It accepted the strict
`ReceiverInputV1` boundary (1024 finite V samples, `t0=0`, `dt=1 ps`, 8
samples/UI) and `ReferenceBitsV1` boundary (128 direct 0/1 bytes). The test
target is not a SIPI CLI, FFI, artifact, default route, or external-engine
dependency.

Orca read-only audit `msg_a114c0ed5901` found `0 P1 / 0 P2`. The audit also
verified source/RFM/engine/product identities, sidecar containment, exact
observer metadata, no bit inference or handoff transform, and that no retained
receiver comparison occurred.

This accepted evidence is only
`handoff_accepted_pending_receiver_execution_and_charter_equivalence`.
It does not execute the fixed receiver, compare it with retained Python or old
Rust behavior, establish charter-scoped receiver equivalence, or certify RFM,
Link, DFE, CDR, BER, or a product route. The next receiver stage requires an
independent observer-side evaluator for the approved charter.
