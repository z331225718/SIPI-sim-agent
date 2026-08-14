# Selected IEEE 802-COM Source Map

This crate is a source-specific BSD-3-Clause direct port, not an Agent-COM or
MATLAB import.

- Upstream repository: `https://opensource.ieee.org/802-com/com_code.git`
- Commit: `d4ecd4597a98782887933b5df4c4796da2474195`
- Source: `src/interp_Sparam.m`
- Git blob: `85b52ff25dbb5bb91f032a03d7cdd311e33af432`
- SHA-256: `259762276a3711eb6e9186993ae1cf38b9cb60d4819f263dc7770788a7f90e27`
- License: BSD-3-Clause; full notice: `NOTICE-IEEE-802-COM.md`

`src/interp_sparam_v1.rs` ports only the source function's magnitude setup,
phase unwrap/anti-causal reject, `linear_trend_to_DC_log_trend_to_inf`, and
`trend_and_shift_to_DC` branches. The Rust file fixes those branches as the
P3C policy and rejects every other branch, debug bypass, and undefined source
branch. It does not port `s21_to_impulse_DC.m` or
`calculate_delay_CausalityEnforcement.m`.

## Fixed Response Truncation

- Source: `src/s21_to_impulse_DC.m`, lines 96--102
- Git blob: `f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3`
- SHA-256: `b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0`
- License: BSD-3-Clause; full notice: `NOTICE-IEEE-802-COM.md`

`src/s21_to_truncated_v1.rs` ports only the last strict peak-relative sample
selection and prefix retention leaf. It fixes the owner-selected `1e-3`
threshold, preserves leading samples and the original `dt`, and reports only a
finite dropped/total L2 ratio plus a structural zero-tail diagnostic. It does
not extract or shift delay, normalize, causalize, repair passivity, convolve,
construct a waveform, or call `calculate_delay_CausalityEnforcement.m`.

## Raw Periodic Inverse Transform

- Source: `src/s21_to_impulse_DC.m`
- Git blob: `f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3`
- SHA-256: `b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0`
- License: BSD-3-Clause; full notice: `NOTICE-IEEE-802-COM.md`

`src/s21_to_raw_periodic_v1.rs` ports only the source's Hermitian spectrum
construction and its unshifted inverse-transform/time-base leaf. The Rust file
adds the fixed P3C endpoint and inverse-imaginary residual rejection gates
before projecting permitted endpoint residue to real values. It does not port
source interpolation, zero-value replacement, causality enforcement, delay
estimation, truncation, rectangular pulse construction, or convolution. It
does not depend on `calculate_delay_CausalityEnforcement.m`.

## Bounded Inline Causality Enforcement

- Source: `src/s21_to_impulse_DC.m`, lines 66--88 and the enabled branch at
  lines 92--94
- Git blob: `f426fb2119dc1cf9c2a2f677e60c3a1f31cb27a3`
- SHA-256: `b2884926b204fdfddc1c309c35d46ed7744c696e19df3abcd7d91157e9e539c0`
- License: BSD-3-Clause; full notice: `NOTICE-IEEE-802-COM.md`

`src/s21_to_causal_v1.rs` ports only the inline Alternating Projections loop.
It fixes causality enabled, `EC_PULSE_TOL=0.05`, `EC_REL_TOL=0.006`,
`EC_DIFF_TOL=1e-4`, and a 256-iteration fail-closed cap. The product's frozen
zero windows are `[0, start]` and `[floor(L/2)-1, L)` in zero-based indexing;
the latter is the exact translation of MATLAB's one-based `floor(L/2):end`.
All-zero input or window, absent first-half threshold crossing, non-positive or
non-finite error denominator, non-finite arithmetic, residual excess, and
iteration exhaustion reject. The stop result remains the source loop's
pre-projection zero-window response. This port does not include the source's
all-zero epsilon substitution, interpolation, delay estimation, truncation,
passivity repair, pulse construction, convolution, or
`calculate_delay_CausalityEnforcement.m`.
