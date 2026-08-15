# P7 IBIS Quasi-Static Publication Binding

The `ibis.quasi-static-evaluate` command is a caller-input, memoryless
constitutive route. Its publication row is therefore fixed as
`available/specified`, non-oracle, and bound to the live command descriptor:
the exact route, stdin transport, request and response schemas, and
`caller_input_quasi_static_constitutive_only` non-claim.

The row is also bound to the existing P4A conformance matrix entry
`input-typ-quasi-static-evaluate-stdin`. That entry must remain
`implemented_self_tested`; it cannot inherit the matrix's separate selected
external static-DC acceptance. The row retains both blockers:
`caller_input_unattested` and `external_transient_not_evaluated`.

This is a P7 consistency repair only. It adds no external asset, transient
solver, time integration, PVT/package/network behavior, AMI composition, or
release acceptance.

## OMP Audit

The existing OMP reviewer audited the staged descriptor, ledger row, evidence
index, matrix status guard, hash binding, and mutation tests. It reported
zero High and zero Critical findings. Its read-only verification also reran
the P4A matrix, P0 metadata gates, and the full publication suite, while
confirming that the user's uncommitted Rust files and `uv.lock` were not
staged.
