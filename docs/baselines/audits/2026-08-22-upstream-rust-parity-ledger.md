# Upstream Rust Parity Ledger Audit

Date: 2026-08-22

Evidence: `docs/baselines/upstream-rust-parity-ledger.v1.yaml`

## Decision

This ledger is a workflow-parity state machine, not a parity acceptance
claim. It records the fifteen pinned Agent-Spice, PyBERT, and Agent-COM rows
after process-external integration and before direct Rust replacement.

The current ledger proves only `source_identity_bound_pre_admission` for every
row. The source authority is an exact Git commit/tree and an entrypoint blob
bound to the existing migration inventory and candidate coverage records. The
reachable module lists are copied as references to the existing
candidate-coverage inventory; they are not a claim that every reachable branch
is already enumerated. Per-path license approval is intentionally still
pending, so no row is yet `source_admitted`.
The external root license records remain separate from any future candidate
crate metadata: PyBERT's BSD-3-Clause source authority is not replaced by a
Rust native crate's Cargo license, and a local `crates/` file cannot serve as
per-path upstream license evidence.

All rows stop at `source_admitted`. `branch_frozen`, `oracle_bound`,
`direct_port_present`, `parity_observed`, and `completion` remain blocked.
The existing external adapters and product CLI routes are deliberately not
direct Rust routes and do not move a row through this state machine.

## State Requirements

The states are ordered:

`source_admitted -> branch_frozen -> oracle_bound -> direct_port_present -> parity_observed -> completion`

The pre-admission identity state is not a state-machine completion state. The
verifier rejects a later verified state when an earlier state is not verified.
A blocked state must name its missing evidence. A row may close only
with one of these explicit outcomes:

- `rust_parity_accepted`
- `retained_external_runtime`
- `excluded_by_owner`

`rust_parity_accepted` is intentionally stricter than the current adapter
evidence. It requires exact source blobs and a non-empty per-path license
record, a branch/default/error/artifact inventory with zero unknowns, a clean
pinned two-fresh-run oracle/runtime attestation, tolerance frozen before
observation, candidate source hashes, a direct Rust route that does not call
an adapter, and mutation coverage.

The other two terminal outcomes also require explicit authority evidence.
An open row has no terminal evidence and cannot be represented as accepted by
changing only its summary or completion string.

## Current Row Status

| Rows | Source admitted | Branch frozen | Oracle bound | Direct Rust | Parity observed | Completion |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| AS-01..AS-06 | 0 | 0 | 0 | 0 | 0 | 0 |
| PB-01..PB-05 | 0 | 0 | 0 | 0 | 0 | 0 |
| COM-01..COM-04 | 0 | 0 | 0 | 0 | 0 | 0 |

All fifteen rows are instead `source_identity_bound_pre_admission`; the
entrypoint and reachable-module identities are known, but per-path license
approval is not yet complete.

PB-02 and COM-03 have reserved evidence interfaces in the ledger. These
interfaces describe future required fields only; neither row is promoted.

## Non-Claims

- No row has Rust numerical parity.
- No caller-selected Python or external executable is source-attested.
- No process-external adapter is treated as a direct Rust implementation.
- Existing bounded profiles, self-tests, generic comparators, and candidate
  kernels are not upstream workflow completion.
- This file does not add a numerical API, alter the migration inventory, or
  change PLAN, release gates, source maps, or license conclusions.

## Verification

`tools/verify_upstream_rust_parity_ledger.py` checks the ledger hash bindings,
all fifteen row identities, exact pinned source metadata, reachable inventory
references, ordered transitions, reserved interfaces, and terminal acceptance
requirements. Its mutation tests prove that source drift, stage promotion,
missing per-path licenses, missing two-fresh oracle evidence, adapter-backed
direct routes, tolerance drift, and missing owner authority fail closed.
