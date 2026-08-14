# P3C-04u Selected S4P Causality Observation Audit

- Reviewer: reused Orca OpenCode reviewer (`term_095ff00a-2548-477e-8dba-ea6e6f010974`)
- Scope: staged P3C-04u external custody runner and hash-only evidence.
- Method: read-only replay of report identities, clean-archive inventory,
  fail-closed gates, registry/license boundary, and staged-file boundary.
- Result: **0 P1 / 0 P2 findings**.

The reviewer independently reconstructed the runner report and observation
report hashes, confirmed two distinct sealed ArtifactRoots and matching source
identity checks, and verified that all output is hash-only. The 32-iteration
successive-error-difference result is bounded-causality observation only.
Causal impulse/FIR, delay, passivity, truncation, convolution, candidate
waveform, reference, receiver, and release gates remain false. The repository
inventory check uses the same `git archive` byte convention as the observation;
`uv.lock` and all user changes remain outside the staged set.
