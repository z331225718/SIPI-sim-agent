# P5-04e Combined Noise PDF Stage — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-04 sub-slice 04e (combined R480 noise PDF)
- Status: delivered and mechanically bound

## Deliverable

- `crates/sipi-com/src/combined_noise_pdf_v1.rs`:
  `combine_r480_noise_pdf_v1` ported from agent-com
  `noise/discrete_pdf.py` (MIT): ordered Eq. 93A-45 combination (fext
  chain, next chain, CCI, ISI+crosstalk, Gaussian+jitter, combined,
  CDF, peak interference via first_quantile) over the ported
  convolution/quantile core; common bin-size check; spec_ber in (0,1].
- MIT source map `p5-04e-mit-source-map.v1.yaml` (2 mappings;
  sampled_signal_pdf / residual_channel_pdf not ported).
- 5 Rust tests: all-delta -> delta, Gaussian combination, bin mismatch,
  invalid spec_ber, policy. sipi-com now 27 tests green.

## Stage chain so far

ingest (04a/04b) -> PDF core (04d) -> combined noise PDF (04e) -> scalar
metrics (04c) are all ported; sampled_signal_pdf, residual_channel_pdf,
channel selection and equalizer search remain.

## Binding

- Charter `p5-04e-combined-noise-pdf-stage.v1.yaml`; source map;
- Verifier `verify_p5_04e_combined_noise_pdf.py` + 5 tests;
- PLAN **P5-04e**; ledger note/gate; coverage gates 94 -> 95.
