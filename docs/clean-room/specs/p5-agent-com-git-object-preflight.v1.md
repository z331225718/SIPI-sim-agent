# P5 Agent-COM Git-Object Preflight v1

## Scope

This observer-only preflight classifies every tracked entry at one immutable
external `agent-com` Git commit. It records only repository identity, path,
Git object identity, byte size, content SHA-256, path class, material role,
license-evidence status, and quarantine action. It does not copy source,
open a workbook, execute MATLAB, run a COM oracle, or extract an algorithm.

## Evidence Boundary

The external repository must have the canonical origin, SHA-1 object format,
and a clean worktree. Root `LICENSE` is checked only for an MIT marker and is
recorded as evidence. That root observation does not promote any individual
path to product source, release input, or clean-room material.

`LICENSE-MANIFEST.md`, if present, is likewise only observed evidence. A
missing `NOTICE` is recorded as `absent_at_commit`; a present notice requires a
separate explicit review. Gitlinks and Git-LFS pointers remain unresolved and
external-only.

## Classification Boundary

Python source and test/tool source are `potential_mit_input` but remain
`quarantine_review`. MATLAB source, data, fixtures, benchmarks, workbooks, and
binary material remain external-only or quarantine. Documentation, build
metadata, and unknown paths have no product promotion. No entry may be a
product or release input in this preflight.

## Non-Claims

This is not a COM implementation, MATLAB/workbook compatibility result,
license decision for data, required profile choice, numerical parity result, or
MIT release approval. Later implementation requires independently selected
profiles and clean-room materials.
