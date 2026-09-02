# PB-02 native source-case map

This map binds every successful, reachable configuration from the pinned
native-core simulation test to the Rust direct port. It is an external
pinned-source comparison and does not change the historical PB-02 formal
matrix, its records, or its blocked case definitions.

## Pinned source

PyBERT commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`, remains the only oracle. Its
BSD-3-Clause `LICENSE` and the crate's existing
`NOTICE-PYBERT-LICENSE-BOUNDARY.md` govern this direct-port boundary.

| Pinned path | Git object | Local use |
| --- | --- | --- |
| `native/pybert-core/tests/simulation.rs` | blob `dd06dc7f612ac32a2fd088611c27530ed25762b6` | Source-owned successful native configurations: deterministic linear, additive noise, CTLE, metallic line, jitter/bathtub, statistical eye, DFE, ISI Viterbi, and PAM4-FEC Viterbi. |
| `native/pybert-core/src/simulation.rs` | blob `1f19bff64315e0042bab89d67e9131c289f5e583` | Existing direct-port implementation lineage. |
| `crates/sipi-pybert-direct/fixtures/pb-02-nrz.json` | SIPI-owned typed baseline | Matches the source test's native linear input before the narrowly specified source case mutation. |

## Comparison

`tests/pb02_native_source_cases.rs` requires a clean pinned `native` tree,
its exact commit and test blob, then runs its `sim-native` CLI and the local
release candidate independently. It covers every successful source-native
configuration (the source's pre-cancelled and malformed-noise assertions are
in-process error-path tests, not CLI artifact-producing configurations). It
compares normalized complete metadata, diagnostics, and every NPZ member's
name, dtype, shape, and numeric payload.
The DFE case uses the source test's configured one-tap adaptive receiver.
The statistical-eye case uses its two source contour levels and pre-DFE
sampling configuration.
The ISI and PAM4-FEC cases retain the source test's typed DFE and Viterbi
controls, including the five-sample ISI impulse and bounded sixteen-state
trellis.
The additive-noise cases retain the source's 32-sample host-provided noise,
both before and after the analytic CTLE. The metallic-line case uses the
source's analytic transmission-line parameters and native frequency grid, in
both source-tested raised-cosine-window modes.
The pre-DFE statistical-eye case combines the source's DFE and single-contour
eye controls, checking that the published complete artifact retains that
source-owned stage ordering.

The CTLE case has only the source test's analytic controls; it intentionally
does not use the historical local `impulseResponseVPerV` extension. The jitter
case uses the source test's complete PRBS-7 period length (`nbits=254`) instead
of the invalid historical 16-bit/8-UI span.

The local `CtleConfigV1` serializer omits an absent
`impulseResponseVPerV`, matching the pinned native request model. A populated
value remains confined to its separately documented typed direct-port path;
the native CLI still drops it before execution.
Likewise, an absent local `tapLimits` extension is omitted from the
source-compatible native artifact rather than serialized as a new `null` key.

This does not claim whole PB-02 branch parity, exact build bytes, AMI/IBIS,
GetWave, S2P, external models, Web/GUI results, product admission, or release
acceptance.
