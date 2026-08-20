# P5-06g Product COM Chain Oracle-Checkpoint Compare — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06g (product COM chain oracle-checkpoint execution & C4 profile compare)
- Status: delivered and cross-checked against an independent reference;
  full compare matrix remains pending oracle artifact custody.

## Method

Drives the product COM chain runner (`p5_06f_com_chain_runner` via `run_com_chain_v1`)
with controls constructed from oracle checkpoint parameters (case_1 and case_2 TXLE/DFE taps,
sigma_N, spec_ber, etc. from P5-06a evidence `summary_content`), then drives the product C4
profile compare runner (`p3c_03c_metric_compare_runner` via `compare_metric_profile_v1`)
using the C4 1% relative metric profile bound to the P5-06e MATLAB oracle reference.
An independent Python reference recomputes the product chain and profile compare.
The cross-check compares per-metric maps and allowed errors, failing closed on any mismatch.

## Result

- 2/2 matched_hash_bound.
- case_1 (candidate TXLE/DFE taps from case_1 checkpoint): product COM chain executes
  and passes C4 profile compare against case_1 oracle reference.
- case_2 (candidate TXLE/DFE taps from case_2 checkpoint): product COM chain executes
  and passes C4 profile compare against case_2 oracle reference.
- Product and independent reference agree on all stage checkpoints, per-metric allowed errors,
  and profile compare verdicts.

## Binding

- Verifier `verify_p5_06g_oracle_chain_compare.py` + 6 tests; crosscheck evidence
  `docs/baselines/p5-06g-oracle-chain-compare-crosscheck-evidence.v1.yaml`.
- Charter `p5-06g-oracle-chain-compare-stage.v1.yaml`; source map
  `p5-06g-mit-source-map.v1.yaml`.
- Oracle reference `docs/baselines/p5-06e-com-oracle-metric-reference.v1.yaml`.
- PLAN **P5-06g**; ledger note/gate P5-06; coverage gates 116 -> 117.

## Scope / Non-Claims

- Not full compare matrix completion; real S4P/config files remain external assets.
- No COM parity across implementations, no release evidence, no acceptance evidence.
