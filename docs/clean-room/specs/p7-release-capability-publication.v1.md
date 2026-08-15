# P7 Release Capability Publication v1

This provisional ledger is a pre-release evidence index, not a release
declaration. It joins the product command manifest to explicit acceptance
states, safe baseline-report references, blockers, and non-claims.

Every command has exactly one row. The row's product surface must match the
current product manifest exactly. `available` only says a product handler is
present; it does not imply external acceptance or release certification. In
v1, every manifest-`unavailable` command is ledger-`blocked`; an unavailable
surface cannot be represented as accepted, specified, or not evaluated.
`blocked` rows require a stable blocker. All global publication states remain
`release_ready: false` and `promotion_status: blocked`.

The consumed command manifest has the exact v1 descriptor fields, unique
stable ids and routes, approved transport values, and consistent availability
and unavailable-reason fields. Missing or additional descriptor fields are
rejected before the publication rows are bound.

Only repository-relative references below `docs/baselines` are admitted. The
publication contains no external asset paths or bytes, user paths, executable
identities, waveform data, legal conclusion, or release approval.
