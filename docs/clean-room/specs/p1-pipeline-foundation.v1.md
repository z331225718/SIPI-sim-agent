# P1 Pipeline Foundation Specification v1

## Scope

This specification covers `crates/sipi-pipeline/**` for P1-07. It defines an
immutable, non-executing typed plan DAG. It does not define dataflow execution,
artifacts, runtime scheduling, or domain operations.

## Allowed Materials

The implementation may use this independently authored specification and the
Rust standard library. It must not consume legacy source, external engine,
oracle output, vendor asset, artifact format, runtime behavior, or domain
algorithm.

## Observable Behavior

A builder declares sources, unary stages, binary joins, and sinks. The output
handle has a private producer and Rust static type, so ordinary callers can
only connect compatible outputs to typed inputs. The completed plan contains
no values and no callbacks.

Node identifiers are canonical ASCII tokens, unique in a plan. Build validates
node shape, input producer existence, exact in-process type identity, duplicate
edges, source/sink presence, reachability from a source and to a sink, and
acyclic topology. It returns an immutable plan with a lexicographically
tie-broken topological node order. Any invalid graph is rejected rather than
given an arbitrary schedule.

The `TypeId` metadata is a process-local defensive invariant only. It is not
serialized, included in an artifact or cache key, or claimed to be a stable
cross-process type tag.

## Non-Claims

This specification does not execute nodes, store values, schedule work, run in
parallel, call callbacks, start a runtime, publish artifacts, compute cache
keys, provide transactions, define retry/cancel semantics, define domain
operations, support legacy inputs, certify profile accuracy, certify a
platform, authorize a release, or establish strict clean-room process.
