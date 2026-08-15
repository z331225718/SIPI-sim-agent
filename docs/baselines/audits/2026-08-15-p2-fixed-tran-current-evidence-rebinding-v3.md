# P2-06e Fixed TRAN Current-Evidence Rebinding v3

P2-06e replays the fixed `tran-rc-pulse-v1` profile against clean product
archive `d0c7efac8f237c8565417a5824d789347053b157` and the immutable external
Agent-Spice object `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`. It is an
additive evidence rebinding: the fixed profile, contract, tolerance, product
implementation, and public request surface do not change.

The operator built the oracle from a detached clean external worktree with
locked offline Cargo resolution. The documented build metadata inputs named
the independently verified detached revision and clean state; the resulting
`build-info` record is hash-bound in the external report. A separate clean Git
archive built the product RC/PULSE harness with locked offline Cargo
resolution, excluding the user's working-tree edits and `uv.lock`.

The oracle ran twice from fresh materializations of the pinned external fixture
and produced identical four-sample time, `v(in)`, and `v(out)` f64le digests.
The product comparison passed all frozen gates. The greatest `v(out)` absolute
error was `9.963737488231927e-7 V`, below its
`2.9990006823819e-6 V` allowed error; the maximum relative error was
`4.986852193371661e-4`. The external report remains outside this repository;
its SHA-256 is
`063ab0c69be24216844dccceb8ff81b2946978caa906cf6b530b2521578c53e4`.
No fixture bytes, waveforms, external report bytes, or absolute paths are
tracked.

The v3 record binds the product RC/PULSE/runtime/type trees, `Cargo.lock`,
both executables, the external object, and the hash-only report. The prior v2
record is immutable historical evidence and must continue to reject with the
exact `evidence_product_source_drift` token. v3 restores acceptance only for
this Windows x86_64 fixed RC/PULSE indexed comparison. It does not establish
general TRAN or netlist support, OP, AC, cross-platform behavior, legal
clearance, or release readiness.

## Verification

- `python -B tools/verify_tran_rc_pulse_current_external_compare_evidence_v3.py --report <external report>` passed.
- `python -B tools/verify_tran_rc_pulse_current_external_compare_evidence_v2.py` returned the expected `evidence_product_source_drift` rejection.
- `python -B -m unittest tools.test_verify_tran_rc_pulse_current_external_compare_evidence` passed.
- `python -B -m unittest tools.test_verify_release_capability_publication` passed, including the real product command-manifest check.

## Independent Audit

The existing Orca OMP reviewer terminal
`term_fa7831f5-ec22-4b3d-8737-25a919226b8b` performed a read-only audit of the
staged P2-06e scope. Result: **0 High / 0 Critical findings; no mandatory
fixes**. The reviewer confirmed the historical v2 source-drift boundary, v3
clean-build/report binding, fixed-profile-only publication scope, and that
neither `uv.lock` nor the user's uncommitted Rust changes were touched.
