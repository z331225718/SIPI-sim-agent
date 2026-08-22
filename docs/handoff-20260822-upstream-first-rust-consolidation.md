# Handoff: upstream-first Rust consolidation

## Owner correction

The active objective is to integrate the already implemented capabilities of
Agent-Spice, PyBERT, and Agent-COM, then replace them with a unified Rust
implementation.  This phase must not invent additional domain functionality.

ADR-015 and `upstream-migration-inventory.v1.yaml` supersede the former active
profile-by-profile implementation order.  The large v0.2 PLAN body and its
19-item ledger remain historical evidence and are not rewritten.

## Fixed upstream inputs

- Agent-Spice `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`
- PyBERT `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`
- Agent-COM `5272ffe74702cd585054d975559b06f8afae7b6e`

All three local worktrees contain unrelated dirt.  Read source identity from
the fixed Git objects or a clean archive, never from worktree bytes.

## Current integration status

All 15 named rows now have a strict process-external adapter and an exact
unified CLI route under `sipi upstream ... --stdin`:

- `sipi-agent-spice-adapter`: AS-01..AS-06
- `sipi-pybert-adapter`: PB-01..PB-05
- `sipi-agent-com-adapter`: COM-01..COM-04

The adapters bind the pinned contract source, explicit backend selection,
bounded process I/O and artifacts, designated-output containment, and
fail-closed errors. AS/PB require fresh targets; COM preserves upstream
overwrite semantics and makes no general freshness or filesystem-sandbox
claim. On Windows the process boundary uses a Job Object so
timeouts and failures terminate descendants.  This is transport integration,
not numerical Rust parity or a product-capability claim.

All 15 inventory rows remain `completion: open`.  The next active work is the
row-by-row oracle/license/parity phase; no new domain feature should be added.

## Execution order

1. Use the bound reachable inventory for one row to freeze all defaults,
   branches, dependencies, assets, errors, and output artifacts.
2. Reuse its integrated strict process adapter as the external oracle boundary;
   do not create a second adapter or silently change `auto` selection.
3. Bind an independent upstream oracle corpus, per-path license decision, and
   branch-complete parity contract.
4. Reuse an upstream native Rust implementation when eligible; otherwise port
   the missing behavior mechanically to the owning SIPI crate.
5. Accept the Rust replacement only after branch-complete parity.  Consolidate
   duplicate algorithms only in a later commit.
6. Repeat until every row is accepted, retained external, or owner-excluded.
7. Freeze a consolidated candidate, then restart the separate P7 release
   ledger.

## Work that is paused

- New product-owned numerical policies or public routes without an upstream
  inventory row.
- Repeated evidence micro-slices that do not advance adapter or Rust parity.
- P7 currentness replay before the consolidated candidate is frozen.
- P3C ADS diagnostics, P4A generalization, and P4B helper expansion unless a
  named upstream reachable branch requires them.

No historical code or evidence is deleted by this rebaseline.  Existing Rust
modules are candidates and regression material, not automatically accepted
replacements.
