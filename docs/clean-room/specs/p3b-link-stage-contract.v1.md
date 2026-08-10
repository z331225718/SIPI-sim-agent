# P3B Link Stage Contract v1

## Status

This product-owned independent specification defines a typed Link-stage
boundary only. It does not define a Link executor, a public CLI command, or
an external-oracle adapter.

## Allowed Inputs

Implementation may use this document and project-owned P1 validated types.
It must not consume PyBERT configuration, DTOs, fixtures, source code, or an
external resolver output as an implementation input.

## Plan

`sipi.link-plan.v1` contains exactly:

- a uniform timebase with `t0 = 0`, finite positive `dt`, and a nonzero sample
  count;
- finite launched-voltage samples relative to the common ground, with length
  exactly equal to the timebase count;
- `tx.kind = direct_launch`;
- a `causal_fir` channel with finite, nonempty dimensionless V/V gain samples
  and the same exact `dt` as the timebase;
- `rx.ctle.kind = bypass` and `rx.ffe.kind = bypass`.

`direct_launch` and both bypass stages are identities. They introduce no
source impedance, gain, sign inversion, time shift, resampling, delay, or
hidden state.

## Future Execution Semantics

When an executor is introduced in a later slice, it must use only the linear,
causal convolution below:

```text
y[n] = sum(k = 0 .. min(n, L - 1)) x[n - k] * g[k]
x[n < 0] = 0
```

The result contains exactly `Nx + L - 1` samples and its time axis begins at
zero with the plan interval. It must not circularly wrap, truncate, shift,
window, pad, resample, or reinterpret the gain units.

## Explicit Exclusions

The P3A matched S21 kernel is a finite-band periodic DFT kernel. It is not a
causal FIR and must be rejected by this contract until a separate,
independently specified causalization profile exists. This contract also
rejects non-bypass CTLE/FFE, PRBS, driver models, jitter, CDR, slicers, BER,
eye metrics, source/load reflection, multi-lane/crosstalk, AMI, COM, paths,
legacy wire formats, and unknown fields.

## Non-Claims

This contract does not establish Channel or Link numerical parity, public
S2P/Touchstone input support, a Python replacement, or a certified runtime.
