# P3B-02 Equalizer Semantics Gap Audit

## Result

P3B-02 remains blocked at `semantics_not_implemented`. The reconciled owner
decision supplies the receiver chain (`RX CTLE -> RX FFE`), explicit per-stage
selection or bypass, and the prohibition on auto-tuning and silent defaults. It
does not supply executable CTLE or FFE equations.

The current product surface is still deliberately bypass-only:

- `sipi.link-plan.v1` contains only `bypass` variants for CTLE and FFE.
- `sipi-contracts` contains only `CtleStageV1::Bypass` and
  `FfeStageV1::Bypass`.
- The existing singleton gate keeps the causal-FIR kernel single-source and
  rejects non-bypass stage implementations.

The additive evidence record is
`docs/baselines/p3b-02-equalizer-semantics-gap.v1.yaml`. Its verifier checks the
owner decision hash, the live schema and Rust enum stage sets, the existing
singleton gate, and the explicit non-admission status.

## Missing Inputs

Before a non-bypass profile can be added, the owner must specify CTLE transfer
representation/normalization/state, FFE tap order/cursor/units/sign/state,
stage output and timebase binding, numeric/bounds behavior, independent
reference and tolerance, and runtime provenance/publication policy.

Implementing a guessed stage would widen the product API and invalidate the
owner's explicit `additive_profile_only` boundary. No production crate or
historical evidence was changed by this slice.

## Verification

```text
python -B tools/verify_p3b_02_equalizer_semantics_gap.py
python -B -m unittest tools.test_verify_p3b_02_equalizer_semantics_gap -v
```
