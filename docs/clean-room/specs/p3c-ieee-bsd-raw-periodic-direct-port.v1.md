# P3C IEEE BSD Raw Periodic Direct-Port v1

## Scope

This scope permits a BSD-3-Clause translation of exactly the Hermitian layout,
inverse-transform, and time-base leaf of `src/s21_to_impulse_DC.m` at the
recorded immutable source identity. It consumes only the fixed
`SelectedP3cUniformSpectrumV1` output of the prior interpolation scope.

## Fixed Product Policy

- Require at least two one-sided bins. Set `N = 2 * (M - 1)` with checked
  arithmetic. The result retains all `N` samples.
- Construct `X[0] = Re(H[0])`, `X[k] = H[k]` for `1 <= k < M-1`,
  `X[N/2] = Re(H[M-1])`, and `X[N-k] = conj(X[k])`.
- Before endpoint projection, require the maximum endpoint imaginary residue to
  be at most `1e-12 + 1e-10 * max(abs(H[k]))`. Otherwise reject.
- Use rustfft 6.4.1 inverse with explicit `1/N` normalization, equivalent to
  `x[n] = (1/N) sum(X[k] * exp(+j*2*pi*k*n/N))`.
- Before retaining real samples, require inverse imaginary residue no greater
  than `1e-12 + 1e-10 * max(abs(Re(x[n])))`. Otherwise reject.
- `dt = 1 / (N * df)` and `t[n] = n * dt` over `[0, N)`. No fftshift, time
  shift, delay removal, alignment, padding, window, or truncation is allowed.

## Boundary

The output is named `SelectedP3cRawPeriodicResponseV1`. It is not a causal
impulse, FIR, or input to convolution. Causality enforcement, delay estimation,
passivity repair, source interpolation, zero-value replacement, pulse
construction, truncation, external S4P observation, and candidate waveform
generation stay outside this scope.

## Source Binding

- Upstream: `https://opensource.ieee.org/802-com/com_code.git`
- Commit: `d4ecd4597a98782887933b5df4c4796da2474195`
- Object: `src/s21_to_impulse_DC.m`
- Blob: `f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3`
- SHA-256: `b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0`
- License: BSD-3-Clause, retained by SPDX and NOTICE.

The named-author `calculate_delay_CausalityEnforcement.m` is expressly not an
implementation input.
