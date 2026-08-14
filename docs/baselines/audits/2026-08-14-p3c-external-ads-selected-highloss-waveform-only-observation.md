# P3C-04ag Selected High-Loss Waveform-Only Observation Audit

- Reviewer: Orca OpenCode reviewer, reused terminal `term_095ff00a-2548-477e-8dba-ea6e6f010974`.
- Scope: hash-only v3 external observation evidence, its verifier and mutation
  tests, and the P3C-04af/04ag plan history.
- Result: 0 P1, 0 P2.

The reviewer independently reconstructed the valid clean-archive report as
2,413 bytes with SHA-256
`d1302327ccf2cfa3120905eecb29a0c5719f5d798a6300ecd7db71615de87387`.
It verified the `8302258` tree and runner hash, all 37 source-inventory
entries, the fail-closed verifier and its three mutations. The two fresh runs
both report NRMSE `0.02759256547865314`, above the fixed `0.01` limit.

The prior `e3df411` literal-backslash-n report remains a non-evidence attempt.
Its envelope-fix commit is retained only as historical runner provenance.
No eye, TIE, receiver, acceptance, promotion, or release gate was elevated;
the user-owned `uv.lock` and unrelated working-tree changes were not modified.
