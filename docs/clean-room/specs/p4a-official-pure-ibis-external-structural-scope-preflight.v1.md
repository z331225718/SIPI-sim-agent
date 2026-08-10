# P4A Official Pure-IBIS External Structural-Scope Preflight v1

## Scope

This observer-only process may read the owner-authorized external byte object
without copying it into the worktree. It emits only identity-bound structural
facts, counts, source-span digests, and hashes. It never emits file content,
numeric tables, curve values, model identifiers, or a local path.

## Allowed Observation

The scanner recognizes line and bracket-header structure only. It reports the
presence/count of an IBIS header, component sections, model sections, model
selector sections, and `Input` model-type declarations. Model/selector names
are represented only by canonical digests. A fixed indicator set is scanned
for declared algorithmic/AMI/dynamic-library/include markers; a zero count
means only that the marker was not observed in this bounded scan.

## Forbidden Observation

The scanner does not parse or retain numerical table data, I-V/V-T/ramp
curves, component parameters, package/PVT values, interpolation behavior,
semantics, AMI/DLL data, or any simulator result. It never invokes a product
parser or product runtime.

## Result Boundary

An identity-matched structural result can make this external asset eligible
for a later owner model-selection review. It does not choose a model, make the
asset required, prove absence of all AMI/binary dependencies, establish a
license, or authorize product/release use.

## Owner Policy Boundary

The owner may authorize the exact external object for oracle and acceptance
selection review while third-party rights remain `unverified`. That limited
policy permits retained external operator custody only. It explicitly excludes
Git assets, product fixtures/source, release bundles, default runtime use, and
redistribution. It is not third-party license evidence.
