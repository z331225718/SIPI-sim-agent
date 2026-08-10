# P4A IBIS 7.1 Behavior-Scope Preflight Audit

## Scope

Independent Orca review of `42a2e81` (`P4A-02a`), which records a bounded
public-standard observation basis and the existing `example_rx` candidate
facts.

## Result

Orca message `msg_7a27909d2342` reported **0 P1 / 0 P2**.

The reviewer confirmed that the record contains only the official IBIS 7.1
document listing and seven presence-only candidate facts. No standard body,
table/curve values, or asset bytes were introduced. Git-object replay checked
the existing asset identity and structural markers, while the declared Windows
x64 DLL identity blocker kept the black-box lane `not_run`.

## Accepted Boundary

`P4A-02a` is accepted as an observer-only behavior-scope preflight. It does
not provide a parser, table evaluation, package/PVT semantics, AMI runtime, or
IBIS-plus-AMI composition. The next P4A behavior work still needs a required
asset/profile and an independent product semantic contract.

## Verification

- `tools/verify_p4a_ibis71_behavior_scope_preflight.py --pybert-root <external Git root>`
- `tools/test_verify_p4a_ibis71_behavior_scope_preflight.py` (3 tests)
- product-boundary, clean-room-register, release-license-preflight, and Rust
  candidate-source-map verifiers

All checks passed before review. The legacy candidate remains external-only.
