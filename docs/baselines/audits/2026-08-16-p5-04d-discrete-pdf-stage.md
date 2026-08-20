# P5-04d Discrete PDF Core Stage — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-04 sub-slice 04d (discrete PDF core)
- Status: delivered and mechanically bound

## Deliverable

- `crates/sipi-com/src/discrete_pdf_v1.rs`: `DiscretePdfV1` (normalized
  construction, x support, cdf, first_quantile), `normal_pdf_v1`
  (r4.80 +/- 2Q support rule, exp(-x^2/(2 sigma^2 + eps))),
  `convolve_v1` (exact full convolution with single-bin shortcuts,
  MATLAB half-away-from-zero rounding).
- MIT source map `p5-04d-mit-source-map.v1.yaml` (6 mappings;
  combine_r480_noise_pdf / sampled_signal_pdf / residual_channel_pdf
  explicitly not ported).
- 5 Rust tests: symmetry/normalization, quantile, delta identity,
  two-pulse convolution, policy. sipi-com now 22 tests green.

## Scope discipline

Combined noise PDF composition (Eq. 93A-45), sampled signal PDF, and
release evidence remain non-claims; channel selection and equalizer
search stages are still pending.

## Binding

- Charter `p5-04d-discrete-pdf-stage.v1.yaml`; source map;
- Verifier `verify_p5_04d_discrete_pdf_stage.py` + 5 tests;
- PLAN **P5-04d**; ledger note/gate; coverage gates 93 -> 94.
