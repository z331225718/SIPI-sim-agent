# P3C Product Rational Candidate Policy Preflight v1

## Purpose

The selected product route is a fixed scalar differential transfer followed by
a deterministic rational/state-space candidate. This charter deliberately stops
before fitting or executing it. It separates a future product model from the
external ADS controller observation and records the decisions still required
before a waveform can exist.

## Fixed Route

Only the P3C selected four-port static bench may provide the scalar input:
`Hdiff = (S21 - S23 - S41 + S43) / 4` on its original S4P frequency nodes.
The intended canonical model is a continuous-time, real SISO, strictly-proper
pole-residue transfer, `H(s) = sum(r_k / (s - p_k))`, with `s = j*2*pi*f`.
State-space is a deterministic derived representation rather than an identity
authority.

The ADS `N=2048` explicit controller result is not a product fit grid, model,
or time-step policy. ADS waveforms and adaptive output cannot supply product
coefficients.

## Required Decisions Before Runtime

The product must explicitly freeze a fit algorithm and its numerical identity:
frequency scaling, DC constraint, weights, initial poles, order ladder,
iteration/relocation, least-squares solver and rank tolerance, convergence,
fit metrics/tolerances, stability/conjugate rules, near-cancellation policy,
and threading identity. Failed convergence or fit admission must reject; no
fallback or pole reflection is permitted.

It must also choose the 40 GHz out-of-band policy and the continuous input
between OSR32 strobes. The existing 100 as ADS source declaration does not by
itself define either. First-symbol handling, UI boundary ownership, initial
state, strobe mapping, analytic recurrence, finite handling, and imaginary
residual policy are likewise required before direct stepping. Adaptive steps,
resampling, alignment, gain fitting, DC removal, and polarity changes remain
forbidden.

## Non-Claims

This is neither a reproduction of an ADS proprietary algorithm nor a product
fitter, executor, coefficient record, waveform, CLI, or acceptance result.
It does not promote the external reference, receiver, P4B, or release gates.
