# P5-06f Fixed-Tap COM Chain Composition Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06f (fixed-tap COM chain composition core)
- Status: delivered and cross-checked against an independent Python
  reference recomputing every stage; product-vs-oracle COM compare remains
  out of scope (external S4P/config assets not materialized).

## Method

`sipi-com` gains `com_chain_v1.rs`: `run_com_chain_v1` composes the
already-ported R480 stage cores — cursor selection (P5-04i, MM CDR),
residual-channel PDF with DFE cancellation and phase sampling (P5-04g),
r4.80 noise-PDF build (P5-04h), combined noise PDF (P5-04e), and
COM/VEC/VEO metrics (P5-04c) — with typed `ComChainControlsV1` and a
per-stage `ComChainReportV1`. Equalizer search (P5-04t), frequency-domain
receiver noise (P5-04o), crosstalk (P5-04p) and TX-FFE synthesis (P5-04j)
are caller-supplied inputs only: never composed, never defaulted, never
guessed. Fail-closed: empty/non-finite pulse, invalid controls, missing
cursor, and any stage rejection are hard errors.

## Result

- 4 Rust unit tests green (policy fixed; chain runs on a synthetic bipolar
  pulse; empty/non-finite pulse rejected; five invalid-control cases).
- Cross-check: 2 synthetic bipolar-pulse cases (0 and 1 DFE taps) driven
  through the product runner; an independent Python reference recomputes
  cursor, residual pulse/PDF, sigma_tx/sigma_rj/sigma_gaussian/ber_q,
  gaussian and dual-Dirac PDFs, combined PDF/CDF, peak interference and
  COM/VEC/VEO — all 16 checkpoints per case match at 1e-12 relative;
  2/2 matched_hash_bound.

## Binding

- Verifier verify_p5_06f_com_chain_core.py + 7 tests; crosscheck evidence
  docs/baselines/p5-06f-com-chain-crosscheck-evidence.v1.yaml.
- Charter p5-06f-com-chain-core.v1.yaml; source map
  p5-06f-mit-source-map.v1.yaml.
- PLAN **P5-06f**; ledger note/gate P5-06; coverage gates 115 -> 116.

## Scope / Non-Claims

- Not a product-vs-oracle COM compare; the oracle normalized inputs
  (S4P/config) remain external assets, hash-bound but not materialized.
- Equalizer search, frequency-domain receiver noise, crosstalk and TX-FFE
  synthesis are not composed in this core.
- No COM parity, no release evidence, no acceptance evidence.
