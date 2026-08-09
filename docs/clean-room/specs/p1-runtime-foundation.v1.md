# P1 Runtime Foundation Specification v1

## Scope

This specification covers `crates/sipi-runtime/**` for P1-06. It defines a
synchronous, cooperative run-control core and deterministic cache-key
calculation. It does not define a task executor, a cache store, a worker, or a
domain simulation.

## Allowed Materials

The implementation may use this independently authored specification, the
Rust standard library, and the declared SHA-256 dependency. It must not
consume legacy source, legacy runtime behavior, oracle output, external
engine, vendor asset, or a domain algorithm.

## Observable Behavior

Every run has a validated identifier and a non-empty explicit policy for a
monotonic deadline, work-unit budget, and accounted-byte budget. A run starts
in `Running` and finishes exactly once as `Succeeded`, `Failed`, `Cancelled`,
`TimedOut`, `ResourceExceeded`, or `Aborted`; terminal states are immutable.
Cancellation is an idempotent request observed by the task at an explicit
checkpoint. Deadline and budgets are likewise checked at explicit
checkpoints. A task result maps only to either success or a structured
`task_failed` result; arbitrary task error text is not part of the runtime
error contract. An unwinding task marks the run `Aborted` without converting
the panic into a successful or structured task result.

Work units and accounted bytes are caller-declared cooperative counters with
checked arithmetic. They are not CPU time, RSS, allocator, process, thread,
or OS-job limits. A deterministic cache key uses a fixed domain/version tag
and length-delimited ordered typed fields. It rejects invalid labels and
malformed SHA-256 values and does not accept unordered maps, paths, wall-clock
time, environment, run identifiers, or float-text fields implicitly.

## Non-Claims

This specification does not provide hard cancellation, hard timeout, process
termination, CPU/RSS enforcement, Windows Job Objects, child cleanup,
concurrency scheduling, cache storage or cache correctness, artifacts,
provenance semantics, CLI/stdin behavior, domain output, legacy compatibility,
profile accuracy, platform certification, release readiness, or strict
clean-room process.
