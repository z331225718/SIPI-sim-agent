# P3A Matched S2P Acceptance Policy

Commits `e6a75e9` and `91b2a25` freeze the observer-only numerical policy for
the selected `channel_16ghz_3db` profile. Its sole future observable is the
400-sample, 25 ps discrete matched-S21 V/V kernel produced by a one-volt
launched DFT probe. The policy fixes Hermitian completion, inverse DFT sign
and scaling, strict index alignment, and `1e-9 + 1e-5 relative` tolerance.

The historical M5B PyBERT handoff is explicitly excluded because it includes
conditioning outside this raw matched-S2P policy. A future external observer
must run twice from fresh Git-object materializations and report identical
kernel hashes; a product result is still not run. No external array, asset,
resolver, or Python fallback enters product code.

The audit initially found two P2 issues: Windows drive-letter paths were not
rejected consistently, and the observation status lagged the selected profile.
`91b2a25` fixed both. The final audit `msg_871668794ab2` reports **0 P1 / 0
P2**. It verified the real PyBERT Git-object anchor, all four P0 verifiers,
and 8 focused Python tests.

## Non-Claims

This accepts an external policy only. It does not implement Touchstone parsing,
an S2P resolver, numerical parity, a Channel CLI, Link stages, or general
Channel support.
