# P3A Matched S2P Preflight

Commit `236dac8` records the first required Channel profile,
`channel_16ghz_3db`, as an external-only observation and freezes the narrow,
project-owned `sipi.channel.s2p-matched.v1` specification. The product has no
S2P parser, resolver, CLI route, fallback, or imported legacy fixture.

The observer-side preflight reads the exact PyBERT Git object
`f6ba0311350fc67bd90fa13b8d578312f956d7e7:models/sp_file/channel_16ghz_3db.s2p`
(blob `e10bfb4a43731645984f1f5e24bd3fbf2268dedd`, SHA-256
`9d4cfeaad7c971fa45454f639b40e08c538855058f326fbdec64298b8933b5ad`). It
confirmed the specified real 50-ohm, two-port, uniformly sampled S-parameter
shape and records derived structural facts only. The verifier is fail-closed
on source identity, port count/order, reference impedance, grid, and
Hermitian-endpoint prerequisites.

The v1 product contract is deliberately limited to a matched source and load
with launched port voltage as its stimulus and `S21` as the receiver-voltage
transfer. It fixes the power-wave, sign, and IFFT conventions while rejecting
renormalization, interpolation, reflections, mixed-mode/multiport data, and
all legacy schemas. It does not implement any of those operations.

The selected profile is `required_pending_preflight`; its structural preflight
is accepted, but `comparison_ready=false`. A numerical compare remains blocked
until an independently recorded launched stimulus, resolution policy,
alignment, observable set, and tolerance are frozen. Existing M5B bridge
evidence is retained only as an external observation reference, not promoted
to product support.

Verification: the matched-S2P verifier and its contract tests (2/2),
acceptance-profile tests (4/4), all four P0 verifiers, and Rust workspace
format/test/clippy (48 tests) passed.

OMP request `msg_13385e9b1861`; conclusion `msg_fb2b19ade9e7`: **0 P1 / 0 P2**.

## Non-Claims

This does not provide Touchstone parsing, S2P/S4P/RFM resolution, FFT or
impulse generation, Link parity, generalized channel support, a production
`sipi channel` command, or a release/MIT-promotion decision.
