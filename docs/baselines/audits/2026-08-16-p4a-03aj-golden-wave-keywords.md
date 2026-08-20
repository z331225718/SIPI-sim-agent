# P4A-03aj Typed IBIS Golden Waveforms Complete Block Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03aj (typed IBIS [Golden Waveforms] block composite keywords core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `golden_wave_keywords_v1.rs` in `sipi-ibis`: `TypedGoldenWaveBlockV1`
holds a validated `TypedGoldenWaveDeclarationV1` (`waveform_declaration`).
`lift_golden_wave_block_v1` validates inputs and returns `Result<TypedGoldenWaveBlockV1, GoldenWaveKeywordsErrorV1>`.
Fail-closed: invalid golden waveform declarations are strictly rejected. An independent Python reference recomputes composite block lifting rules over 3 test cases.

## Result

- 2 Rust unit tests green (policy fixed; valid golden wave block).
- Cross-check: 3 test cases (full golden wave block, minimal golden wave block, invalid name characters)
  driven through product runner `p4a_03aj_golden_wave_keywords_runner`; independent Python reference
  matches 100% on valid flags, waveform declarations, DUT names, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03aj_golden_wave_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03aj-golden-wave-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03aj-golden-wave-keywords-stage.v1.yaml`; source map
  `p4a-03aj-mit-source-map.v1.yaml`.
- PLAN **P4A-03aj**; ledger note/gate P4A-03; coverage gates 162 -> 163.

## Scope / Non-Claims

- Not a full IBIS file parser; no golden waveform comparison simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
