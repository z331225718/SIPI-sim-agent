# P4A Electrical and IBIS Discovery v1

## Purpose

This observer and governance record preserves the requested differential
electrical-load values and records safe IBIS/AMI discovery leads. It implements
no electrical model, parser, host, asset loader, or CLI route.

## Electrical Boundary

The candidate has one 100 ohm resistor directly between differential terminals
`P` and `N`. That connection is unambiguous.

`Cload=1 pF` is deliberately unresolved. The approved next choice must name
exactly one of: a capacitor across `P` and `N`; one 1 pF capacitor from each
leg to a named reference net; or a declared total differential-equivalent 1 pF
model. These are different electrical topologies. In particular, two equal
leg-to-reference capacitors do not have the same differential capacitance or
common-mode behavior as one P-to-N capacitor.

Until the placement and, where applicable, reference net, stimulus, observable,
and comparison policy are frozen, this candidate is not required and cannot be
passed to a solver or an acceptance gate.

## Asset Discovery Boundary

The pinned external `example_rx` IBIS/AMI/DLL record remains oracle-only and
keeps its declared Windows x64 DLL-name mismatch blocker. The local `minimal`
IBIS file is a synthetic test fixture, not an external acceptance asset.

The IBIS Open Forum model-supplier directory is recorded only as a public
discovery lead. A particular downloaded `.ibs` file remains unverified until
its exact URL, bytes hash, license/notice, model selector, and permitted use
are separately recorded. No external bytes or user-machine paths are copied
into the product or this record.

## Rejection Rules

The verifier rejects a missing Cload placement, an implicit reference net, an
attempt to promote a candidate, external bytes or absolute paths, an automatic
IBIS/AMI composition, or an unverified public asset marked usable.

## Non-Claims

This record does not support RC loading, IBIS parsing, AMI hosting, electrical
termination solving, or any composed receive chain.
