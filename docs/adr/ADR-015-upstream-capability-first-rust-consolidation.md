# ADR-015: Upstream-Capability-First Rust Consolidation

- Status: Accepted
- Date: 2026-08-22
- Decision maker: project owner
- Scope: migration order, compatibility boundaries, Rust replacement, and feature work

## Context

The project has accumulated useful Rust foundations, narrow product-owned
profiles, evidence gates, and release controls.  The owner clarified that the
current objective is not to invent additional SIPI functionality.  It is to
integrate the already implemented product workflows of Agent-Spice, PyBERT,
and Agent-COM, then replace those workflows with one Rust implementation.

The former profile-by-profile plan made locally useful progress, but it could
also create product-owned semantics that did not close an upstream workflow.
That is no longer the active completion model.

## Decision

1. The three authoritative migration inputs are fixed Git objects:
   Agent-Spice `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, PyBERT
   `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, and Agent-COM
   `5272ffe74702cd585054d975559b06f8afae7b6e`.
2. The first integration boundary is each repository's stable public CLI/API
   workflow, not every research script, GUI action, benchmark, or generated
   output.
3. A workflow is integrated first through a strict process-external adapter.
   The adapter may map transport and errors, seal artifacts, and record the
   exact backend.  It may not change defaults, align or resample data, tune a
   model, hide fallback, or rewrite numerical semantics.
4. Rust replacement proceeds one migration row at a time.  Existing SIPI Rust
   code is only a candidate until the row binds its reachable upstream branch
   inventory, input/output contract, source and license scope, oracle corpus,
   and independent parity evidence.
5. A row is complete only as `rust_parity_accepted`,
   `retained_external_runtime`, or `excluded_by_owner`.  A self-test or a
   similar-looking implementation is not completion evidence.
6. New domain functionality is frozen.  A new public API or numerical policy
   is allowed only when it is required to integrate or replace a named
   upstream migration row.
7. Duplicate algorithms are not consolidated until the participating rows
   have parity.  Migration, mechanical Rust translation, consolidation, and
   numerical improvement remain separate reviews and commits.
8. Existing evidence, release controls, and v0.2 records remain immutable
   history.  Release replay is deferred until a new consolidated candidate is
   frozen.

## Initial workflow scope

- Agent-Spice: `fit-sparam`, `fit-sparam-cascade`, `fit-yparam`,
  `tune-yparam-tran`, `run-hspice`, and `run-rfm`.
- PyBERT: `sim`, `sim-native`, `sim-rust`, `sim-auto`, and `sim-compare`,
  including their actually reachable numerical branches.  Web, GUI, Redis,
  and service operations remain an accounted operational track, not a first
  numerical migration completion condition.
- Agent-COM: `config validate`, `run`, `compare`, and the public Python API
  composed by `load_config`, `run_com`, and `write_artifacts`.

Research commands and external MATLAB, workbook, golden, solver, or vendor
assets are not silently imported.  They require an explicit later inventory
revision and their own rights/custody record.

## Consequences

- `upstream-migration-inventory.v1` is the active implementation ledger.
- The old 19-item ledger is retained as a v0.2 historical blocker snapshot.
- Release blockers are tracked separately and do not drive implementation
  order before the consolidated candidate is frozen.
- Existing Rust work remains available as candidates and regression material;
  this decision does not delete or automatically accept it.

## Non-claims

- This decision is not a license conclusion for every path in the three roots.
- It does not make Python a permanent release dependency.
- It does not accept current SIPI self-tests as upstream parity.
- It does not authorize new functionality, numerical correction, or release.
