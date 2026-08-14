# P3C-04ac Selected High-Loss Waveform-Only v3 Audit

- Reviewer: reused Orca OpenCode reviewer
  `term_095ff00a-2548-477e-8dba-ea6e6f010974`.
- Scope: selected high-loss PRBS9 strict-grid waveform-NRMSE-only contract,
  core, sealed-artifact CLI route, schema, and release declaration.
- Method: read-only implementation, contract, schema-inventory, gate, and
  test review.
- Result: **0 P1 / 0 P2 findings**.

The reviewer confirmed that v2 remains unchanged, while v3 is bound to the
selected high-loss profile and excludes sampled-eye and crossing-TIE rather
than treating them as passed. The v3 core compares only original third-period
sample indices with strict NRMSE; it performs no alignment, resampling, gain,
DC, or polarity transform. The v3 sealed-artifact route and metadata are
separate from v2, and neither route can select the other profile.

Validation observed: `sipi-compare`, `sipi-contracts`, and `sipi-cli` tests;
the v3 verifier and mutation tests; schema-inventory validation; and the
release-capability verifier against a generated command manifest. The release
row remains `specified` with no external-oracle or receiver/release promotion.
`uv.lock` and pre-existing unrelated worktree changes were not touched.
