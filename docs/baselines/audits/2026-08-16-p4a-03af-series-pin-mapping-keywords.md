# P4A-03af Typed IBIS Series Pin Mapping Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03af (typed IBIS [Series Pin Mapping] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_keywords_v1.rs` in `sipi-ibis`: `TypedSeriesPinMappingBlockV1`
holds a validated `TypedSeriesPinRecordV1` (`pin_record`) and optional `TypedSeriesPinThresholdsV1` (`thresholds`).
`lift_series_pin_mapping_block_v1` validates inputs and returns `Result<TypedSeriesPinMappingBlockV1, SeriesPinMappingKeywordsErrorV1>`.
Fail-closed: invalid series pin records or threshold parameter errors are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 2 Rust unit tests green (policy fixed; valid series pin mapping block).
- Cross-check: 3 test cases (full series pin block, minimal series pin block, negative rseries threshold)
  driven through product runner `p4a_03af_series_pin_mapping_keywords_runner`; independent Python reference
  matches 100% on valid flags, pin records, thresholds, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03af_series_pin_mapping_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03af-series-pin-mapping-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03af-series-pin-mapping-keywords-stage.v1.yaml`; source map
  `p4a-03af-mit-source-map.v1.yaml`.
- PLAN **P4A-03af**; ledger note/gate P4A-03; coverage gates 157 -> 158.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
