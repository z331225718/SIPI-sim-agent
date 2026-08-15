# P2 Fixed TRAN Current-Evidence Rebinding v4

The bounded RC/PWL route changed the product candidate without changing the
fixed `tran-rc-pulse-v1` contract, fixture, comparison policy, or tolerance.
This additive v4 observation rebuilds the fixed product harness from clean
archive `538b5dd08f734e5558b1179083c3d24a95aba02f` and the oracle from the
immutable Agent-Spice object `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`.

The detached oracle build explicitly recorded its checked revision and clean
state through the source-supported build metadata inputs. It replayed the
external fixture twice with identical four-sample f64le identities. The clean
product harness passed the frozen time, `v(in)`, and `v(out)` comparisons. The
hash-only external report is `854e34fd85bc5cef8018fb4387c6ecb8ecbb102dda9f14b872279bc0b05b84ce`;
fixture bytes, waveforms, executable bytes, report bytes, and absolute paths
remain outside the repository.

v1 through v3 remain historical. v3 must now reject with the exact
`evidence_product_source_drift` token. v4 restores external acceptance only
for the Windows x86_64 fixed RC/PULSE indexed comparison. It does not accept
the RC/PWL route, generic TRAN or netlist support, OP, AC, cross-platform
behavior, legal clearance, or release readiness.
