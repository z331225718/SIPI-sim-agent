# P3B-02 Named FIR Prerequisite Audit

## Result

P3B-02 remains blocked at `semantics_not_implemented`. The reconciled owner
decision supplies the receiver chain (`RX CTLE -> RX FFE`), explicit per-stage
selection or bypass, and the prohibition on auto-tuning and silent defaults. It
does not supply executable CTLE or FFE equations.

The admitted product profile is still deliberately bypass-only:

- `sipi.link-plan.v1` contains only `bypass` variants for CTLE and FFE.
- `sipi-contracts` contains only `CtleStageV1::Bypass` and
  `FfeStageV1::Bypass`.
- The existing singleton gate keeps the causal-FIR kernel single-source and
  the v1 wire/contract stages bypass-only.

One additive prerequisite now exists in `sipi-link`: two explicitly selected
named slots, evaluated in CTLE-name then FFE-name order, each either bypassed or
backed by finite sample-spaced causal-FIR taps. Tap zero is aligned to the input
origin, prehistory is zero, output is full-linear, and cumulative sample/MAC
budgets fail closed. Both slots delegate to the existing
`convolve_causal_fir_v1` kernel.

Those names establish only ordering. The prerequisite does not define a CTLE
transfer function, UI-spaced FFE cursor convention, coefficient synthesis, or
auto-tuning, so it is not an admitted equalizer profile and does not close
P3B-02.

The current gap/prerequisite evidence record is
`docs/baselines/p3b-02-named-fir-prerequisite.v2.yaml`. Its verifier checks the
owner decision hash, the live schema and Rust enum stage sets, the existing
singleton gate, the named-FIR source hash/markers, and the explicit
non-admission status.

## Missing Inputs

Before a non-bypass profile can be added, the owner must specify CTLE transfer
representation/normalization/state, FFE tap order/cursor/units/sign/state,
stage output and timebase binding, numeric/bounds behavior, independent
reference and tolerance, and runtime provenance/publication policy.

The v1 wire contract remains unchanged. A later additive profile still needs
the missing transfer/grid/state semantics and independent compare evidence.

## Verification

```text
python -B tools/verify_p3b_02_named_fir_prerequisite.py
python -B -m unittest tools.test_verify_p3b_02_named_fir_prerequisite -v
```
