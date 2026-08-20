# P3C-02h Bathtub Curve Fit Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P3C-02 sub-slice 02h (bathtub curve fit in the log10(BER) domain)
- Status: delivered and cross-checked against an independent reference;
  P3C-02 main item stays open (statistical eye contour still pending)

## Method

Implement `bathtub_fit_v1.rs` in `sipi-com`: `fit_bathtub_curve_v1` fits a polynomial curve of
degree 1..=3 to a V-shaped BER-vs-time bathtub in the log10(BER) domain — least-squares polynomial
regression over (time_offset_ui, log10(ber)) samples solved by Gaussian elimination with partial
pivoting (deterministic). The result carries the fit coefficients (constant first), the sample
count, and the maximum absolute residual at the sample points, plus an evaluation method. It builds
on the `BathtubSampleV1` sample model of P3C-02f; the opening-width estimator remains in 02f.
Fail-closed: too few samples (`TooFewSamples`), non-ascending time (`TimeNotAscending`), invalid BER
(`InvalidBer`), fit order zero or above 3 (`InvalidFitOrder`), insufficient samples for the order
(`InsufficientSamplesForOrder`), and a numerically degenerate system (`NumericFailure`) are
strictly rejected. An independent Python reference replicates the same normal equations and
Gaussian elimination (identical arithmetic) over 4 test cases.

## Result

- 9 Rust unit tests green (exact linear fit; exact quadratic fit; evaluate matches fitted values;
  too few samples; invalid fit order; insufficient samples for order; non-ascending time; invalid
  BER).
- Cross-check: 4 test cases (linear fit, quadratic fit, insufficient samples, invalid BER) driven
  through product runner `p3c_02h_bathtub_fit_runner`; independent Python reference matches 100%
  on valid flags, fit orders, coefficient vectors (bit-exact), sample counts, residuals, and error
  contexts; 4/4 matched_hash_bound.

## Binding

- Verifier `verify_p3c_02h_bathtub_fit.py` + 6 tests; crosscheck evidence
  `docs/baselines/p3c-02h-bathtub-curve-fit-crosscheck-evidence.v1.yaml`.
- Charter `p3c-02h-bathtub-curve-fit-stage.v1.yaml`; source map `p3c-02h-mit-source-map.v1.yaml`.
- PLAN **P3C-02h**; ledger note/gate P3C-02; coverage gates 221 -> 222.

## Scope / Non-Claims

- Not a statistical eye contour, no eye folding/bins, no COM parity, no acceptance evidence.
- Fit is a deterministic mechanism; profile/behavior application remains caller-supplied.
