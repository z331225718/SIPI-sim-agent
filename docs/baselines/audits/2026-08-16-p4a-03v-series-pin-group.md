# P4A-03v Typed IBIS Series Pin Group Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03v (typed IBIS [Series Pin Mapping] series group core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `series_pin_mapping_group_v1.rs` in `sipi-ibis`: `TypedSeriesPinGroupV1`
holds a validated ASCII group name (`[A-Za-z0-9_.-]+`) and a list of `SeriesPinPairV1` (pin_first, pin_second).
`lift_series_pin_group_v1` validates inputs and returns `Result<TypedSeriesPinGroupV1, SeriesPinMappingGroupErrorV1>`.
Fail-closed: empty group names (`EmptyGroupName`), non-ASCII characters (`NonAsciiName`),
invalid name spellings (`InvalidName`), empty pin pair lists (`EmptyPinPairs`), or duplicate pin pairs (`DuplicatePinPair`)
are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 5 Rust unit tests green (policy fixed; valid group declaration; empty group name rejection;
  empty pin pairs rejection; duplicate pin pair rejection).
- Cross-check: 3 test cases (valid group declaration, empty pin pairs, duplicate pin pair)
  driven through product runner `p4a_03v_series_pin_group_runner`; independent Python reference
  matches 100% on valid flags, group names, pin pair lists, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03v_series_pin_group.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03v-series-pin-group-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03v-series-pin-group-stage.v1.yaml`; source map
  `p4a-03v-mit-source-map.v1.yaml`.
- PLAN **P4A-03v**; ledger note/gate P4A-03; coverage gates 145 -> 146.

## Scope / Non-Claims

- Not a full IBIS file parser; no series model circuit simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
