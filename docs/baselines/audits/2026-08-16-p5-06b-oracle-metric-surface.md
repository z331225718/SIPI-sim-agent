# P5-06b Oracle Metric Surface — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06b (oracle metric surface observation)
- Status: delivered and mechanically bound; compare matrix pending

## Method

Parsed the P5-06a summary.json (kept verbatim in the first-run evidence)
into its structured surface: network roles and keys, output metric keys,
per-case checkpoint keys, case count; hash-bound to summary.json.

## Observed surface

- Network: THRU / FEXT1 / NEXT1 with sdd21 -10 / -40 / -40 dB at 26.56
  GHz (consistent with the synthetic fixture names).
- Output metrics (14): FOM, COM_dB, VEC_dB, VEO_mV, ERL, ERL11 (inf),
  ERL22, IL_dB_channel_only_at_Fnq, fitted_IL_dB_at_Fnq, ICN_mV,
  Peak_ISI_XTK_and_Noise_interference_at_BER_mV, CTLE_DC_gain_dB,
  g_DC_HP, itick.
- Cases: 2; internal checkpoints: TXLE_taps, DFE_taps, tail_RSS, sigma_N,
  sgm_Ani__isi_xt_noise, itick (selection evidence surface).

## Scope discipline

No comparison, normalization, or product derivation; the compare matrix
and normalized-input verification remain later P5-06 slices.

## Binding

- Surface `p5-06-oracle-metric-surface.v1.yaml`;
- Verifier `verify_p5_06b_oracle_metric_surface.py` + 5 tests;
- PLAN **P5-06b**; ledger note/gate; coverage gates 84 -> 85.
