# P3C IEEE BSD Interpolation Direct-Port v1

## Scope

This is the first and only implementation scope enabled by the user's
2026-08-13 policy decision for the selected IEEE 802-COM direct-port lane. It
permits a BSD-3-Clause translation of exactly `src/interp_Sparam.m` at the
source identity recorded below. It does not admit `s21_to_impulse_DC.m` or the
named-author causality helper.

## Fixed Product Policy

- Input: `SelectedP3cStaticDifferentialTransferV1`; no file, artifact, path,
  port-map, interpolation branch, or debug option is caller supplied.
- Time interval: `9.765625e-13` seconds. Nyquist is exactly `512000000000` Hz.
- Source spacing is `fin[1]-fin[0]`. For positive values, output count minus
  one is `floor(512000000000 / source_spacing + 0.5)`, matching MATLAB's
  positive `round`; output frequency `k` is `k * 512000000000 / M`.
- The only magnitude branch is `linear_trend_to_DC_log_trend_to_inf`; the only
  phase branch is `trend_and_shift_to_DC`.
- Phase unwrap and the source anti-causal mean-phase-slope reject are enabled.
  There is no DEBUG warning mode or repair bypass.
- The output limit is 1,048,576 bins. Nonfinite values, too few samples,
  non-increasing axes, undefined high-frequency log trend, and empty strict
  group-delay inliers reject.

## Boundary

Uniform-grid interpolation is not causalization. This scope does not implement
IFFT, `s21_to_impulse_DC`, delay estimation, causality enforcement, passivity
repair, truncation, convolution, waveform generation, ADS comparison, a
receiver, or release admission. Its out-of-band values are product-owned
IEEE-port semantics, not measured-bandwidth, ADS, or passivity claims.

## Source Binding

- Upstream: `https://opensource.ieee.org/802-com/com_code.git`
- Commit: `d4ecd4597a98782887933b5df4c4796da2474195`
- Object: `src/interp_Sparam.m`
- Blob: `85b52ff25dbb5bb91f032a03d7cdd311e33af432`
- SHA-256: `259762276a3711eb6e9186993ae1cf38b9cb60d4819f263dc7770788a7f90e27`
- License: BSD-3-Clause, retained in the crate source and NOTICE.

The implementation source map must name this object. It must not name or
depend on Agent-COM code, MATLAB execution, oracle outputs, or the excluded
IEEE source objects.
