# COM-03 direct-port source map

Scope: only the pinned Agent-COM `compare` workflow. This map is per-path
provenance, not a claim that the caller-selected runtime is authenticated.

| Upstream Git path | Role translated | Git blob | Content SHA-256 | License |
| --- | --- | --- | --- | --- |
| `src/agent_com/reporting.py` | result JSON reader, contract checks, comparable projection, recursive mismatch traversal | see manifest | see manifest | MIT |
| `src/agent_com/cli.py` | compare argument defaults and matched/mismatch exit mapping | see manifest | see manifest | MIT |
| `schemas/result-v1.schema.json` | result artifact field and scalar shape contract | see manifest | see manifest | MIT |

The Rust translation lives in `src/lib.rs` and `src/bin/compare.rs`; tests are
independent transport/semantic checks and do not substitute for the pinned
oracle. No upstream source file is vendored into this crate.
