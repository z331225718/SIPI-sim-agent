# P6-04c/P6-05b Fixed Project CLI Acceptance

`sipi project run --stdin --artifact-root <root> --artifact-id <id>` exposes
exactly one product-owned composite: fixed RC/PULSE `voltage_in` into a
DirectLaunch causal-FIR consumer. The request is versioned, rejects unknown
fields, and is admitted by the existing fixed project topology and policy
checks before execution.

On success the command atomically publishes `request.json`, `received-waveform.json`,
`edge-record.json`, and `provenance.json`. It returns only the opaque artifact
identity, declared digests, and manifest summary. A failed admission, attempt,
or publication has no successful artifact result.

The single Orca review found one P2 schema-list ordering drift. It was corrected
so `schema list` follows the registered schema inventory, then the focused
contracts and CLI tests and lint checks were rerun. The review found no P1
issues.

Verification passed:

```text
cargo fmt --all -- --check
cargo test -p sipi-contracts -p sipi-cli
cargo clippy -p sipi-contracts -p sipi-cli --all-targets -- -D warnings
```

This is not a generic project executor, DAG scheduler, retry/cache system,
multi-edge workflow, S2P channel route, or IBIS/AMI/COM integration.
