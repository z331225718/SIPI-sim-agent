# P4A-03ak Typed IBIS Bus Label Complete Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ak (typed IBIS [Bus Label] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `bus_label_keywords_v1.rs` in `sipi-ibis`: `TypedBusLabelBlockV1`
holds a validated `TypedBusLabelDeclarationV1` (`bus_label_declaration`).
`lift_bus_label_block_v1` validates inputs and returns `Result<TypedBusLabelBlockV1, BusLabelKeywordsErrorV1>`.
Fail-closed: invalid bus label declarations are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 2 Rust unit tests green (policy fixed; valid bus label block).
- Cross-check: 3 test cases (full bus label block, empty member pins, duplicate member pin)
  driven through product runner `p4a_03ak_bus_label_keywords_runner`; independent Python reference
  matches 100% on valid flags, bus label declarations, member pin lists, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ak_bus_label_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ak-bus-label-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ak-bus-label-keywords-stage.v1.yaml`; source map
  `p4a-03ak-mit-source-map.v1.yaml`.
- PLAN **P4A-03ak**; ledger note/gate P4A-03; coverage gates 163 -> 164.

## Scope / Non-Claims

- Not a full IBIS file parser; no bus simulation or bus-level timing analysis.
- No release certification, no acceptance evidence.
