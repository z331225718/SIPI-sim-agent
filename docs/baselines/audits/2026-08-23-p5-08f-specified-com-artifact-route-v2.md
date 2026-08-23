# P5-08f specified COM artifact route (current source rebind)

Date: 2026-08-23

Evidence: `docs/baselines/p5-08f-specified-com-artifact-route.v2.yaml`
Predecessor: `docs/baselines/p5-08f-specified-com-artifact-route.v1.yaml`

This additive successor retains the historical P5-08f route contract and
non-claims while rebinding the live `sipi-com` public surface after the
preparation wave changed its source bytes. The parameter and execution
modules, CLI and contract surfaces, P5-08a/08b/08d/08e bindings, route schema,
budgets, and audit boundary remain unchanged.

The route is still a caller-owned, bounded, non-oracle
`com.run-artifact` prerequisite. It does not read the workbook, infer a
profile, auto-tune, claim Agent-COM parity, provide external acceptance, or
constitute release evidence. `p5_08_closed` remains false and the legacy
`com.run` route remains unavailable.

The v1 evidence and verifier are retained as historical records. This v2
record is the current source-drift successor used by the release publication
gate; it does not promote or certify the route.
