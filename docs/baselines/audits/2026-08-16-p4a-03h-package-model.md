# P4A-03h Typed IBIS Package Model Declaration Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03h (typed IBIS package model declaration core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `package_model_declaration_v1.rs` in `sipi-ibis`: `TypedPackageModelDeclarationV1`
holds a validated ASCII package model name (`[A-Za-z0-9_.-]+`), optional R_pkg, L_pkg, C_pkg
finite non-negative `FiniteF64` global parameters. `lift_package_model_declaration_v1` validates
inputs and returns `Result<TypedPackageModelDeclarationV1, PackageModelDeclarationErrorV1>`.
Fail-closed: empty name (`EmptyName`), non-ASCII characters (`NonAsciiName`), invalid name
spellings (`InvalidName`), non-finite values (`NonFiniteValue`), or negative values (`NegativeValue`)
are strictly rejected. An independent Python reference recomputes the lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid full package model; valid minimal package model;
  empty name rejection; non-ASCII rejection; negative/non-finite RLC rejection).
- Cross-check: 3 test cases (full package model, minimal package model, negative R_pkg)
  driven through product runner `p4a_03h_package_model_runner`; independent Python reference
  matches 100% on valid flags, name/R_pkg/L_pkg/C_pkg fields, and error codes; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03h_package_model.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03h-package-model-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03h-package-model-stage.v1.yaml`; source map
  `p4a-03h-mit-source-map.v1.yaml`.
- PLAN **P4A-03h**; ledger note/gate P4A-03; coverage gates 118 -> 119.

## Scope / Non-Claims

- Not a full IBIS file parser; no pin-by-pin RLC package matrices or electrical semantics.
- No release certification, no acceptance evidence.
