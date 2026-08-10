# P2-03a RC Pulse Semantic Contract Audit

Date: 2026-08-10

## Slice

Commit `8184303` turns the selected RC pulse profile into an executable
product-owned semantic and comparison policy. The scope fixes four
index-aligned points `0..3 us`, finite `v(in)` and `v(out)`, explicit zero
capacitor initial voltage without OP/UIC, a piecewise-linear PULSE source, and
f64 backward Euler with endpoint source evaluation and mandatory output/pulse
corner breakpoints.

The comparison policy fixes time tolerance at `1e-15 s`; input voltage at
`1e-9 V + 1e-9 relative`; and output voltage at
`2e-6 V + 5e-4 relative`. It remains `specified_not_executed`: a policy is
ready, but neither oracle reproducibility nor a product result has been
accepted.

## Verification

- The external Git-object contract validated against the fixed source anchor,
  including its ready-policy lane.
- Focused fail-closed tests and the Python tool suite (116 tests) passed.
- Product-boundary, clean-room-register, release-license-preflight, and
  Rust-candidate-source-map verifiers remain valid and provisional.

## Independent Audit

OMP request `msg_031567fac89d` reviewed the committed slice. Conclusion
`msg_f4af5d613f6c`: 0 P1 / 0 P2.

## Scope Limits

This is a contract only. It does not execute an oracle, create a golden,
implement the typed request or solver, establish parity, accept a result,
parse a netlist, implement OP/AC/general MNA/nonlinear devices, promote a
candidate, or grant release or platform-certification status.
