# P3C-04t IEEE BSD Inline Causality Direct-Port Audit

- Reviewer: reused Orca OpenCode reviewer (`term_095ff00a-2548-477e-8dba-ea6e6f010974`)
- Scope: implementation commit `64bac6e` and its bounded corrective diff.
- Method: read-only source-port, policy, license-boundary, gate, verifier, and
  staged-file review.
- Result: initial review found one P2 zero-window off-by-one; the corrective
  review found **0 P1 / 0 P2 findings**.

The correction translates the IEEE source's one-based
`floor(L/2):end` suffix exactly to zero-based `[floor(L/2)-1,L)`, preserving
its overlap with the first-half window. A focused boundary test protects that
endpoint. The reviewer confirmed the fixed user-authorized tolerances, bounded
iteration failure, rejection paths, source pre-projection stop output, BSD
source map and continued exclusion of the named-author delay helper. Causal
impulse admission, delay, passivity, truncation, convolution, candidate
waveform, external acceptance, and release gates remain false. Neither
`uv.lock` nor pre-existing user changes are included.
