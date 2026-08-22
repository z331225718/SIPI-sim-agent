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

## Execution order

1. For one inventory row, enumerate the complete reachable upstream call
   graph and all defaults, branches, dependencies, assets, errors, and output
   artifacts.
2. Add a strict process adapter without changing numerical semantics.  Record
   the actual backend; `auto` fallback may never be silent.
3. Bind an independent upstream oracle corpus and parity contract.
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
