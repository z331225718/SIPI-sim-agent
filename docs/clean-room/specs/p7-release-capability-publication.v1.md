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

An `accepted` row also requires a route-specific v1 acceptance authority in
the verifier. Availability, an external-oracle label, or an observed report
alone cannot authorize acceptance. New accepted routes require a dedicated
evidence verifier and an explicit authority-list update.

The consumed command manifest has the exact v1 descriptor fields, unique
stable ids and routes, approved transport values, and consistent availability
and unavailable-reason fields. Missing or additional descriptor fields are
rejected before the publication rows are bound.

The product-owned unavailable catalog routes `project.validate` and
`report.show` are additionally bound to their current descriptors: exact route,
unavailable reason, nonclaim, `transport: none`, and null request/response
schemas. Their ledger rows remain blocked with the matching blocker/nonclaim,
`external_oracle: false`, and the P6 command-manifest contract; this binding
does not make the historical P6 audit a current manifest snapshot.

The available `link.receiver.run` route is separately bound as a
product-owned diagnostic. Its live descriptor, three ledger blockers, receiver
non-claim, link-stage ledger, and pinned diagnostic contract remain exact. This
does not turn a caller-supplied diagnostic into external RFM parity, clock lock,
required-profile acceptance, or a release gate.

The available `compare.run` route is separately bound as a caller-owned
aligned-array comparison. Its descriptor, explicit alignment/profile blockers,
non-oracle ledger row, and two pinned product contracts remain exact. This does
not create profile semantics, eye/jitter/bathtub/BER evaluation, external
comparison, or release acceptance.

The available `project.run` route is separately bound to its one fixed
TRAN-to-causal-FIR composite. Its descriptor, fixed-topology blocker, nonclaim,
and pinned P6 capability contract remain exact. This does not create a generic
project executor, a second topology, retry/cache semantics, external-profile
acceptance, or release evidence.

The available `link.run` route is separately bound to its direct-launch
causal-FIR-only profile. Its descriptor, blocked required-link-profile state,
nonclaim, and pinned P3B capability ledger remain exact. This does not create
an external oracle, S2P channel support, receiver parity, PRBS/equalization,
noise/jitter, DFE/CDR/BER, or release acceptance.

The available `report.inspect` route is separately bound to its sealed-artifact
integrity metadata projection. Its descriptor, metadata-only blocker/nonclaim,
historical install observation, and pinned P6 capability contract remain exact.
This does not make `verified` an ownership, signature, authorization, payload,
or external-provenance claim; `report.show` remains unavailable and blocked.

The available `tran.one-node-rc-pulse` route is separately bound to its bounded
product-owned one-node RC/PULSE contract. This does not create an external
oracle, general TRAN/netlist or SPICE parity, multi-node/MNA/nonlinear support,
or release acceptance.

Only repository-relative references below `docs/baselines` are admitted. The
publication contains no external asset paths or bytes, user paths, executable
identities, waveform data, legal conclusion, or release approval.
