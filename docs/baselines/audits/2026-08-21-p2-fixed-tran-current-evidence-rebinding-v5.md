# P2 Fixed TRAN Current-Evidence Rebinding V5

Date: 2026-08-21

## Preflight

The v3 and v4 records remain historical: each now rejects with the exact
`evidence_product_source_drift` token after the current product candidate moved
past its recorded source tree. Neither historical evidence file was rewritten.

The required Agent-Spice object was available in the external repository at
commit `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`, with fixture blob
`f9c29055902fe8aa2b268b4375a5bdbbf67df9da` and fixture content SHA-256
`bcdbd81a40dde01f0e72a8c36be928b6a7325fabbc25f83f72073757154dcefc`.

## Clean Builds And Compare

The product harness was built from committed clean archive
`805ebb6bbaf588dec08685be4eb78a8ce2fff563` with Rust 1.97.0 and
`--locked --offline`. The bound product trees are:

- `sipi-tran`: `6583a013c17931cbf79e2c0cf339c781e0273537`
- `sipi-types`: `a3ab7197e85eef6064f691ae0af5654d52060bda`
- `sipi-runtime`: `fa32fba371af288b03a2ce24ca03ccd409f85178`
- `Cargo.lock`: `9d91af3e623f024b47c62471c22b308496205ba3`
- product harness SHA-256: `92551eb90557917c91e42fe9e9f169d435a4ddcdc78f3a6c00cd3a7396b5dd61`

The oracle was built in a clean detached worktree at the pinned external
commit with locked offline Cargo resolution. Its build-info identified
`gitDirty: false`, target `x86_64-pc-windows-msvc`, and release profile. The
oracle executable SHA-256 is
`b7a695089e518efd560e4fbb7b92a48d6ef487534a83196d1be5065440ca4a41`; its
comparator-selected build-info identity SHA-256 is
`baf9e0a6e4de54f4b99a2ed8896f98d6be8984dcc1d43d4a4fd7817f38cd6f43`.

The existing comparator materialized the exact external fixture in two fresh
temporary custody directories and ran the oracle twice. Both oracle runs had
the same four-index f64le identities. The clean product harness passed all
frozen gates:

- time: absolute tolerance `1.0e-15`, maximum absolute error `0.0`;
- `v(in)`: absolute/relative tolerances `1.0e-9`/`1.0e-9`, maximum absolute error `0.0`;
- `v(out)`: absolute/relative tolerances `2.0e-6`/`5.0e-4`, maximum absolute error
  `9.963737488231927e-7`, maximum relative error `4.986852193371661e-4`,
  allowed error at the worst index `2.9990006823819e-6`.

The hash-only external report remains outside this repository at operator
custody. Its SHA-256 is
`9891142f1075cf37a86ece8d8de8bd1eecec3dde2dcf8983615d4e1b870a44fa`.
Fixture bytes, waveform arrays, executable bytes, report bytes, and absolute
paths are not tracked.

## Boundary And Follow-Up

The additive v5 record restores only the Windows x86_64 fixed
`tran-rc-pulse-v1` indexed time/`v(in)`/`v(out)` observation. It does not
accept RC/PWL, general TRAN, netlist parsing, OP, AC, cross-platform behavior,
legal clearance, or release readiness.

The parent release/publication owner must make the separate publication
decision: retain v1-v4 as historical, validate v5 and its mutation tests, and
only then replace the stale v4 evidence reference in the release publication
record if the broader release gates allow it. Until that explicit publication
edit, the existing `specified` / non-oracle / source-drift-blocked state is
unchanged.

## Verification

```text
python -B tools/verify_tran_rc_pulse_current_external_compare_evidence_v5.py
python -B -m unittest tools.test_verify_tran_rc_pulse_current_external_compare_evidence_v5 -v
git diff --check
```
