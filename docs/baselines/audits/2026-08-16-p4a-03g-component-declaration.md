# P4A-03g Typed IBIS Component Declaration Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03g (typed IBIS component declaration core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `component_declaration_v1.rs` in `sipi-ibis`: `IbisComponentV1` holds
a validated ASCII component name (`[A-Za-z0-9_.-]+`), optional trimmed manufacturer,
and optional trimmed package model name. `lift_component_declaration_v1` validates
inputs and returns `Result<IbisComponentV1, ComponentDeclarationErrorV1>`.
Fail-closed: empty name (`EmptyName`), non-ASCII characters (`NonAsciiName`), or invalid
name characters (`InvalidName`) are strictly rejected. An independent Python reference
recomputes the lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid full component; valid minimal component;
  empty name rejection; non-ASCII rejection; invalid character rejection).
- Cross-check: 3 test cases (full component, minimal component, invalid component name)
  driven through product runner `p4a_03g_component_declaration_runner`; independent
  Python reference matches 100% on valid flags, name/manufacturer/package_name fields,
  and error codes; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03g_component_declaration.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03g-component-declaration-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03g-component-declaration-stage.v1.yaml`; source map
  `p4a-03g-mit-source-map.v1.yaml`.
- PLAN **P4A-03g**; ledger note/gate P4A-03; coverage gates 117 -> 118.

## Scope / Non-Claims

- Not a full IBIS file parser; no electrical, PVT, or pin-to-model linkage semantics.
- No release certification, no acceptance evidence.
