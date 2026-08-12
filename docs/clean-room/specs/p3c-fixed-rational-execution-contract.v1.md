# P3C Fixed-Rational Execution Contract v1

## Purpose

This owner-approved contract closes the product execution semantics for the
selected P3C fixed-pole route before any external S4P intake or waveform
runtime exists. It does not upgrade the existing unconstrained complex-residue
fit into a real model: a later hardening implementation must construct the
real-constrained pair representation specified here.

## Real Model and Fit

The selected profile permanently uses the fixed allowlisted orders 8, 12, and
16. It does not require relocating vector fitting. The canonical model stores
only positive-imaginary pole/residue members in ascending imaginary frequency;
the negative member is its exact conjugate. Fitting must use a real-constrained
basis, and may not average, project, or discard imaginary components after a
complex fit. Every pole is strictly in the left half plane, nonfinite or
unpaired models reject, and the output is the sum of `2*Re` of pair states.

The existing fixed-pole fit gates remain model admission gates: relative RMS at
most 0.5%, maximum normalized absolute error at most 3%, and DC relative error
at most 0.5%. A fit failure rejects without an alternate algorithm. Direct,
derivative, and explicit-delay terms remain prohibited.

## Product Execution Semantics

Above 40 GHz, the product uses global strictly-proper rational continuation.
This is product extrapolation, not ADS behavior or an ADS-equivalence claim;
there is no band-limit filter or phase-delay extraction.

PRBS9 differential levels use a product-defined 100 as linear ramp on each
changing UI interval `[boundary, boundary + 100 as)`, followed by a plateau.
Unchanged symbols hold the preceding level. This is not inferred from ADS
`EdgeShape` behavior. The model starts from zero state. The first symbol is
effective at `t=0` without inventing a preceding bit or first ramp. The first
two PRBS periods are explicit input warmup only.

The output is `y(n*dt)` for `n=0..49055`, with `dt=0.9765625 ps`, covering the
half-open three-period interval. At a UI boundary the output is recorded before
the new source segment advances. Each conjugate pair uses an analytic,
piecewise-affine input recurrence with fixed complex exponential and `expm1`
primitives. Generic matrix exponential, numeric ODE solving, adaptive steps,
resampling, alignment, gain/DC/polarity fitting, passivity repair, and
pole/residue repair are prohibited; nonfinite or imaginary-residual failure
rejects.

## Boundary

This contract adds no Rust API, S4P reader, artifact, coefficient record,
waveform, CLI, or external invocation. The current fit is still not a
real-model-admitted runtime. Candidate/reference binding, metric acceptance,
receiver acceptance, P4B, and release remain blocked.
