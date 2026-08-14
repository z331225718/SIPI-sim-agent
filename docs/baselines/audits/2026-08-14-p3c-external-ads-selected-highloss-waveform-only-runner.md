# P3C-04ad External Waveform-Only Runner Audit

- Reviewer: reused Orca OpenCode reviewer
  `term_095ff00a-2548-477e-8dba-ea6e6f010974`.
- Scope: v3 external ADS reference/candidate comparison runner preparation.
- Method: read-only custody, v3 isolation, report-boundary, clean-room,
  dependency, and staged-worktree review.
- Result: **0 P1 / 0 P2 findings**.

The reviewer confirmed independent S4P and ADS identity checks, separate v3
artifact and CLI contracts, two fresh manifests per run, and a report limited
to hashes, counts, NRMSE bit patterns, and acceptance booleans. The runner
does not emit paths, source bytes, waveform arrays, eye/TIE values, or CLI
diagnostics, and it does not promote receiver, physical, or release gates.

The initial review found the release-boundary hash stale after the inventory
update. The hash in `license-manifest.v2.yaml` was updated to the exact current
`product-boundary.v1.yaml` bytes; the release-license preflight and its test
suite then passed. `uv.lock` and pre-existing user changes remain unstaged.
