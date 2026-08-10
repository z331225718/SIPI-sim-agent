# P2 TRAN Performance Observation Specification v1

## Scope

This external-only measurement gate observes the accepted
`tran-rc-pulse-v1` product-owned CLI request on Windows x86_64. It does not
change solver behavior, select a new workload, or establish a performance
budget.

The executable must be an explicitly supplied installed Rust binary. Each run
uses an empty external working directory and a new artifact root; no cache hit,
legacy engine, Python process, source checkout, or reusable artifact is an
allowed input.

## Measurement Protocol

The gate performs exactly three unreported warmup invocations followed by ten
reported invocations. Each invocation sends the same exact typed request to
`sipi tran run --stdin`, requires the two payload files plus a verified success
manifest, and records its wall-clock duration with `perf_counter_ns`.

On Windows, each reported invocation records `PeakWorkingSetSize` using
`GetProcessMemoryInfo` on the launched child process after it exits. A missing
or nonpositive peak working-set observation invalidates the whole report.
The report binds executable size/SHA-256, commit, Cargo lock SHA-256,
toolchain, request SHA-256, output payload hashes, protocol version, and OS
observation. All ten samples must have a complete and identical output identity.

The only successful report status is `observed_pending_owner_budget`. Median,
minimum, and maximum values are observations, not thresholds.

## Budget Gate

The tracked budget policy begins in `pending` state. A release-oriented check
must fail until an owner supplies a dated approval that binds the exact
workload, report SHA-256, metric definitions, threshold/statistical rule, and
over-limit disposition. No verifier may infer a ratio or a budget from the
observed median.

## Non-Claims

This observation is not a performance pass, an RSS limit, a hard resource
enforcement claim, a benchmark comparison, a cross-machine result, a general
TRAN workload, or Windows certification.
