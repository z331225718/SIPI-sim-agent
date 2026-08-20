# P4A-03s Typed IBIS Golden Waveforms Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03s (typed IBIS [Golden Waveforms] core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `golden_wave_declaration_v1.rs` in `sipi-ibis`: `TypedGoldenWaveDeclarationV1`
holds a validated ASCII waveform name (`[A-Za-z0-9_.-]+`) and an optional
associated DUT fixture name (`dut_name`). `lift_golden_wave_declaration_v1` validates inputs and
returns `Result<TypedGoldenWaveDeclarationV1, GoldenWaveDeclarationErrorV1>`.
Fail-closed: empty waveform names (`EmptyWaveformName`), non-ASCII characters (`NonAsciiName`), or
invalid name spellings (`InvalidName`) are strictly rejected. An independent Python reference
recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid full golden wave; valid minimal golden wave;
  empty waveform name rejection; non-ASCII name rejection; invalid name characters rejection).
- Cross-check: 3 test cases (full golden wave, minimal golden wave, invalid name characters)
  driven through product runner `p4a_03s_golden_wave_runner`; independent Python reference
  matches 100% on valid flags, waveform names, DUT names, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03s_golden_wave.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03s-golden-wave-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03s-golden-wave-stage.v1.yaml`; source map
  `p4a-03s-mit-source-map.v1.yaml`.
- PLAN **P4A-03s**; ledger note/gate P4A-03; coverage gates 132 -> 133.

## Scope / Non-Claims

- Not a full IBIS file parser; no golden waveform comparison simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
