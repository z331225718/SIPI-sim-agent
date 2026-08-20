# P4A-03ag Typed IBIS Series Switch Groups Complete Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ag (typed IBIS [Series Switch Groups] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_switch_groups_keywords_v1.rs` in `sipi-ibis`: `TypedSeriesSwitchBlockV1`
holds a validated `TypedSeriesSwitchRecordV1` (`switch_record`) and optional `TypedSeriesSwitchThresholdsV1` (`thresholds`).
`lift_series_switch_block_v1` validates inputs and returns `Result<TypedSeriesSwitchBlockV1, SeriesSwitchKeywordsErrorV1>`.
Fail-closed: invalid series switch records or threshold parameter errors are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 2 Rust unit tests green (policy fixed; valid series switch block).
- Cross-check: 3 test cases (full series switch block, minimal series switch block, identical groups switch)
  driven through product runner `p4a_03ag_series_switch_keywords_runner`; independent Python reference
  matches 100% on valid flags, switch records, thresholds, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ag_series_switch_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ag-series-switch-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ag-series-switch-keywords-stage.v1.yaml`; source map
  `p4a-03ag-mit-source-map.v1.yaml`.
- PLAN **P4A-03ag**; ledger note/gate P4A-03; coverage gates 158 -> 159.

## Scope / Non-Claims

- Not a full IBIS file parser; no series switch circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
