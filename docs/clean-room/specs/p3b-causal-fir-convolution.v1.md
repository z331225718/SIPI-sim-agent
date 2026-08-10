# P3B Causal FIR Convolution v1

## Status

This project-owned specification defines the first executable Link primitive.
It consumes only a validated `sipi.link-plan.v1` and does not introduce an
equalizer, clock, decision, parser, oracle, or CLI route.

## Calculation

For direct-launch samples `x` and causal FIR gain `g`, calculate each output
in increasing index order with increasing kernel index order:

```text
y[n] = sum(k = 0 .. min(n, L - 1)) x[n - k] * g[k]
x[n < 0] = 0
```

The output is finite voltage relative to common ground, has exactly
`Nx + L - 1` samples, and uses a zero-origin uniform time axis with the plan
sample interval. It is direct linear convolution: no FFT, circular wrapping,
padding, trimming, window, time shift, resampling, source/load calculation,
or channel resolution is permitted.

## Limits and Failure

Before allocation, check output length and `Nx * L` multiply-accumulates with
checked arithmetic. Both must be within explicit nonzero limits. A non-finite
product or intermediate sum fails at its output index and returns no partial
result. The accumulation order is fixed; parallel reductions and FMA-specific
alternative paths are outside v1.

## Explicit Exclusions

The only accepted stages remain direct launch, causal FIR, CTLE bypass, and
FFE bypass. The P3A finite-band periodic DFT kernel cannot enter this API. No
Touchstone/S2P input, causalization, reflection, CTLE, FFE, DFE, CDR, PRBS,
jitter, slicer, BER, eye, AMI, COM, artifact publication, or legacy route is
implemented.

## Non-Claims

This is a product-owned causal FIR primitive, not Link/profile parity, an
equalizer implementation, selected S2P-to-Link integration, or a certified
runtime.
