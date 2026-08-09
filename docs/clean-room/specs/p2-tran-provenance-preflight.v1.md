# P2 TRAN Provenance Preflight Specification v1

## Scope

This observer-side preflight records Git-object provenance for the quarantined
`native/crates/sipi-circuit/**` candidate and a fixed external `agent-spice`
source anchor. It does not define, implement, build, run, or compare a TRAN
solver.

## Observable Behavior

Every candidate path is bound to its SIPI commit, blob object, content hash,
file kind, and quarantine status. A `direct_mit_exact` assessment is valid only
when the external source path, Git blob, and byte hash exactly match and root
license evidence is also object-bound. Missing source paths, absent NOTICE,
unresolved Cargo dependencies, and missing clean-room evidence remain explicit
unknown or pending facts.

The preflight separately records target Cargo.toml/Cargo.lock object identities,
direct dependency declarations, and locked package metadata. It runs only
Git-object inspection and TOML parsing; it does not copy external source into
the product tree or construct a target directory.

## Non-Claims

The result does not promote a quarantine path, decide supply-chain or NOTICE
compliance, establish a clean-room implementation, grant redistribution rights,
define a TRAN profile, prove numerical behavior, or certify a release.
