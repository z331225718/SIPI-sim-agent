# P3A Clean-Room Matched Kernel

Commits `9f8e587`, `7dd53fd`, and `0e9399d` add `sipi-channel`, the first
clean-room Channel primitive. It accepts only a product-owned, indexed,
uniform two-port S matrix with one real positive matched impedance and emits
the discrete `S21` V/V kernel defined by the P3A policy.

The resolver Hermitian-completes the one-sided spectrum, applies the specified
inverse FFT sign and `1/N` scaling, and rejects endpoint imaginary residue,
nonpositive inputs, insufficient samples, limits, transform overflow,
non-finite output, and inverse imaginary residue. It uses `rustfft` under the
existing provisional dependency/NOTICE gate; no dependency is promoted for
release.

Self-owned tests cover identity, an integer sample delay, linear scaling,
non-S21 isolation, endpoint policy, resource limit, length overflow, inverse
residue, and non-finite transform output. No external fixture, array golden,
Touchstone parser, file I/O, Python fallback, reflection solver, Link stage,
or CLI route is included.

OpenCode audit `msg_0fcfed97bd52`: **0 P1 / 0 P2**.

## Non-Claims

This is not selected-profile parity, Touchstone support, general S2P/channel
support, a Channel CLI, Link parity, or a release/MIT-promotion decision.
