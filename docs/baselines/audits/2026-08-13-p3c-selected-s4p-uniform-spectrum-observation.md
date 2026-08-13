# P3C Selected S4P Uniform-Spectrum Observation Audit

- Reviewer: Orca OpenCode read-only reviewer, reused existing terminal
- Commits reviewed: `5cca95c`, `9611e2e`
- Date: 2026-08-13
- Scope: P3C-04p two-fresh sealed custody and frozen interpolation observation;
  user-owned `uv.lock` excluded
- Result: 0 P1 / 0 P2

## Confirmed

- The runner creates two independent temporary `ArtifactRoot` instances, binds
  the exact source before, during, and after staging, and removes each root.
- The report is hash-only and external: it binds the source, runner, clean
  archive, two distinct manifests, and admitted uniform-spectrum summary without
  retaining paths, source bytes, or spectrum values.
- The evidence permits only static admission and interpolation observation. IFFT,
  raw periodic response, causality, delay, passivity repair, truncation,
  convolution, candidate waveform, reference/receiver/P4B/P5, and release
  gates remain false.
- The historical raw exact-grid diagnostic remains unmodified, and both reviewed
  commits exclude `uv.lock`.

## Residual Risk

The repository preserves external-custody identity facts but cannot recompute
this observation without an authorized replay of the external selected S4P.
The next route is therefore an explicit raw-IFFT policy decision, not a causal
or waveform implementation.
