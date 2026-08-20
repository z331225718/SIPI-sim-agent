# P4A-03e Typed [Pin] Declaration Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03e (typed [Pin] declaration core)
- Status: delivered and cross-checked against an independent observer.
  Extends the P4A-03d typed Model declarations with [Pin] section typing.

## Method

Implement lift_pin_declarations_v1 in sipi-ibis pin_declaration_v1.rs: find the
[Pin] Keyword section, collect its Data rows (pin_name signal_name model_name),
reject rows with <3 tokens. Cross-check the product against an independent
observer on the authorized as4c512m16md4v-053bin.ibs.

## Result

- pin_count 200 = 200 observer (matched_hash_bound); first 5 pins agree
  (A1 DNU NC ...).
- sipi-ibis unit suite 50 tests green (4 new pin_declaration tests).

## Binding

- Verifier verify_p4a_03e_pin_declaration.py + 6 tests; crosscheck evidence
  docs/baselines/p4a-03e-pin-declaration-crosscheck-evidence.v1.yaml.
- Charter p4a-03e-pin-declaration-stage.v1.yaml; source map
  p4a-03e-mit-source-map.v1.yaml.
- PLAN **P4A-03e**; ledger note/gate P4A-03; coverage gates 103 -> 104.
