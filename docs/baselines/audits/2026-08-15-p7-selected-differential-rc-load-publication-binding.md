# P7 Selected Differential R-C Load Publication Binding

The `rx-load.differential-rc-evaluate` command is fixed to the selected
continuous P/N/REF constitutive relation. Its publication row is bound to the
live caller-input descriptor, including its exact route, stdin schemas, and
`selected_continuous_constitutive_relation_only` non-claim.

The row is also bound to the existing P4A matrix entry
`selected-differential-rc-load-evaluate-stdin`. The entry must remain
`implemented_self_tested`; it does not provide a channel integration, an
external load profile, or an IBIS/AMI composition acceptance. The row retains
the channel-integration and external-profile blockers.

This P7 consistency repair adds no topology override, integration solver,
transient state, external asset, or release acceptance.

## OMP Audit

The existing OMP reviewer audited the staged descriptor, row, evidence index,
matrix status guard, hash binding, and mutation tests. It reported zero High
and zero Critical findings after rerunning the P4A matrix, P0 metadata gates,
and the full publication suite. The reviewer also confirmed that no user Rust
file or `uv.lock` change was staged.
