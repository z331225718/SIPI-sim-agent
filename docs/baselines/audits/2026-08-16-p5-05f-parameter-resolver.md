# P5-05f COM Parameter Surface Resolver Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-05 sub-slice 05f (COM parameter surface resolver core)
- Status: delivered and cross-checked against an independent reference;
  P5-05 main item stays open (full COM parameter ingestion pipeline pending)

## Method

Implement `com_parameter_resolver_v1.rs` in `sipi-com`: `resolve_com_parameter_controls_v1`
resolves a merged `ComParametersV1` DTO (P5-05e) into typed COM execution controls
(`ComChainControlsV1`, P5-06f), extracting required keys (`samples_per_ui`, `levels`,
`bin_size`, `spec_ber`, `A_v`, `R_LM`, `SNR_TX`, `sigma_X`, `sigma_RJ`, `h_J`, `sigma_N`, `A_DD`)
and supporting alias spellings.
Fail-closed: empty DTO (`EmptyDto`), missing required keys (`MissingKey`), unexpected value types
(`InvalidType`), or invalid control bounds (`ChainControls`) are strictly rejected. An independent
Python reference recomputes control resolution over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; resolves valid DTO to controls; empty DTO rejection;
  missing key rejection; invalid type rejection; out-of-range scalar rejection).
- Cross-check: 3 test cases (valid DTO map, missing required key, invalid type) driven through
  product runner `p5_05f_parameter_resolver_runner`; independent Python reference matches 100% on
  valid flags, consumed counts, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p5_05f_parameter_resolver.py` + 6 tests; crosscheck evidence
  `docs/baselines/p5-05f-parameter-resolver-crosscheck-evidence.v1.yaml`.
- Charter `p5-05f-parameter-resolver-stage.v1.yaml`; source map
  `p5-05f-mit-source-map.v1.yaml`.
- PLAN **P5-05f**; ledger note/gate P5-05; coverage gates 120 -> 121.

## Scope / Non-Claims

- Not a workbook file parser; no cross-implementation COM parity, no release evidence,
  no acceptance evidence.
