# P4A-03m Typed IBIS Circuit Call & Port Mapping Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03m (typed IBIS [Circuit Call] & Port-Node Mapping core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `circuit_call_declaration_v1.rs` in `sipi-ibis`: `TypedCircuitCallDeclarationV1`
holds a validated ASCII circuit name (`[A-Za-z0-9_.-]+`) and a list of `PortMapV1`
(port_name, node_name). `lift_circuit_call_declaration_v1` validates inputs and returns
`Result<TypedCircuitCallDeclarationV1, CircuitCallDeclarationErrorV1>`.
Fail-closed: empty circuit names (`EmptyCircuitName`), non-ASCII characters (`NonAsciiName`),
invalid name spellings (`InvalidName`), empty port mapping lists (`EmptyPortMappings`), or
duplicate port names (`DuplicatePortName`) are strictly rejected. An independent Python reference
recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid circuit call; empty circuit name rejection;
  empty port mappings rejection; non-ASCII name rejection; duplicate port name rejection).
- Cross-check: 3 test cases (valid circuit call, single port mapping, duplicate port name)
  driven through product runner `p4a_03m_circuit_call_runner`; independent Python reference
  matches 100% on valid flags, circuit names, port mapping counts/items, and error strings;
  3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03m_circuit_call.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03m-circuit-call-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03m-circuit-call-stage.v1.yaml`; source map
  `p4a-03m-mit-source-map.v1.yaml`.
- PLAN **P4A-03m**; ledger note/gate P4A-03; coverage gates 125 -> 126.

## Scope / Non-Claims

- Not a full IBIS file parser; no subcircuit netlist simulation or electrical transient semantics.
- No release certification, no acceptance evidence.
