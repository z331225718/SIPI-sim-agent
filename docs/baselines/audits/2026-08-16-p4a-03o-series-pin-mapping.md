# P4A-03o Typed IBIS Series Pin Mapping Table Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03o (typed IBIS standalone [Series Pin Mapping] table core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_v1.rs` in `sipi-ibis`: `TypedSeriesPinRecordV1`
holds validated ASCII pin names (`pin_first`, `pin_second`), `model_name`, and an optional
`function_table_group`. `lift_series_pin_record_v1` validates inputs and returns
`Result<TypedSeriesPinRecordV1, SeriesPinMappingTableErrorV1>`.
Fail-closed: empty pin names (`EmptyPinName`), empty model names (`EmptyModelName`),
non-ASCII characters (`NonAsciiName`), invalid name spellings (`InvalidName`), or identical pin pairs
(`IdenticalPins`) are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 7 Rust unit tests green (policy fixed; valid full record; valid minimal record;
  empty pin name rejection; empty model name rejection; identical pins rejection).
- Cross-check: 3 test cases (full record, minimal record, empty model name)
  driven through product runner `p4a_03o_series_pin_mapping_runner`; independent Python reference
  matches 100% on valid flags, pin names, model name, function table group, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03o_series_pin_mapping.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03o-series-pin-mapping-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03o-series-pin-mapping-stage.v1.yaml`; source map
  `p4a-03o-mit-source-map.v1.yaml`.
- PLAN **P4A-03o**; ledger note/gate P4A-03; coverage gates 128 -> 129.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
