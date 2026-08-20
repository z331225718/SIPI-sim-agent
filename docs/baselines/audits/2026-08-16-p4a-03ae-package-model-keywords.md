# P4A-03ae Typed IBIS Package Model Required Keywords Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03ae (typed IBIS [Package Model] required keywords & sections core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `package_model_keywords_v1.rs` in `sipi-ibis`: `TypedPackageModelKeywordsV1`
holds a validated ASCII package model name (`[A-Za-z0-9_.-]+`), pin count (`number_of_pins`), and list of pin numbers (`pin_numbers`).
`lift_package_model_keywords_v1` validates inputs and returns `Result<TypedPackageModelKeywordsV1, PackageModelKeywordsErrorV1>`.
Fail-closed: empty package model names (`EmptyPackageModelName`), non-ASCII characters (`NonAsciiName`),
invalid name spellings (`InvalidName`), zero pin count (`InvalidNumberOfPins`), empty pin number lists (`EmptyPinNumbers`),
or duplicate pin numbers (`DuplicatePinNumber`) are strictly rejected. An independent Python reference recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid package model keywords; empty package model name rejection;
  zero number of pins rejection; empty pin numbers rejection; duplicate pin number rejection).
- Cross-check: 3 test cases (valid package model keywords, zero number of pins, duplicate pin number)
  driven through product runner `p4a_03ae_package_model_keywords_runner`; independent Python reference
  matches 100% on valid flags, package model names, pin counts, pin number lists, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03ae_package_model_keywords.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03ae-package-model-keywords-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03ae-package-model-keywords-stage.v1.yaml`; source map
  `p4a-03ae-mit-source-map.v1.yaml`.
- PLAN **P4A-03ae**; ledger note/gate P4A-03; coverage gates 156 -> 157.

## Scope / Non-Claims

- Not a full IBIS file parser; no package RLC matrix crosstalk simulation.
- No release certification, no acceptance evidence.
