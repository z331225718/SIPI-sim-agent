# P4A-03n Typed IBIS Node Declaration Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03n (typed IBIS [Node Declarations] core)
- Status: delivered and cross-checked against an independent reference;
  P4A-03 main item stays open (full IBIS parser integration pending)

## Method

Implement `node_declaration_v1.rs` in `sipi-ibis`: `TypedNodeDeclarationV1`
holds a validated ASCII internal node name (`[A-Za-z0-9_.-]+`) and an optional
associated signal name (`signal_name`). `lift_node_declaration_v1` validates inputs and
returns `Result<TypedNodeDeclarationV1, NodeDeclarationErrorV1>`.
Fail-closed: empty node names (`EmptyNodeName`), non-ASCII characters (`NonAsciiNodeName`), or
invalid name spellings (`InvalidNodeName`) are strictly rejected. An independent Python reference
recomputes lifting rules over 3 test cases.

## Result

- 6 Rust unit tests green (policy fixed; valid full node declaration; valid minimal node declaration;
  empty node name rejection; non-ASCII name rejection; invalid name characters rejection).
- Cross-check: 3 test cases (valid full node declaration, minimal node declaration, empty node name)
  driven through product runner `p4a_03n_node_declaration_runner`; independent Python reference
  matches 100% on valid flags, node names, signal names, and error strings; 3/3 matched_hash_bound.

## Binding

- Verifier `verify_p4a_03n_node_declaration.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4a-03n-node-declaration-crosscheck-evidence.v1.yaml`.
- Charter `p4a-03n-node-declaration-stage.v1.yaml`; source map
  `p4a-03n-mit-source-map.v1.yaml`.
- PLAN **P4A-03n**; ledger note/gate P4A-03; coverage gates 126 -> 127.

## Scope / Non-Claims

- Not a full IBIS file parser; no internal node electrical connectivity simulation.
- No release certification, no acceptance evidence.
