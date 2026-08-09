# P1 CLI Discovery Specification v1

## Scope

This specification covers the static P1-08 command service in
`crates/sipi-cli/**`. It provides product discovery and self-conformance only.

## Observable Behavior

`version`, `doctor`, `capabilities`, `schema`, `validate self`, `run`, and
`inspect` accept only their fixed command grammar with `--json`. The command
service has no print or process ownership; its thin wrapper is retained only
for manual invocation until P1-09 defines final process behavior.

`capabilities` reports every planned domain as `unsupported`. `schema list`
and `schema show` expose only registered product contract schemas. `validate
self` checks built-in catalog, deterministic serialization, and rule-ledger
availability without accepting caller JSON. `doctor` reports declared internal
checks and external items as `not_checked`. `inspect` only describes built-in
self, schema, or capability identifiers. `run` always rejects as unsupported.

Commands reject unknown identifiers and arguments without reading stdin,
filesystem paths, artifacts, environment state, Python, old engines, vendor
assets, or domain inputs.

## Non-Claims

This specification does not define final stdout/stderr/exit-code behavior,
stdin/file request ingestion, artifact inspection, installation health,
external runtime discovery, run execution, domain validation, legacy support,
profile accuracy, platform certification, release readiness, or strict
clean-room process.
