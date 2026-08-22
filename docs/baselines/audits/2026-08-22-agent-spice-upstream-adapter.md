# Agent-Spice upstream-first adapter audit

Date: 2026-08-22

## Scope

This audit covers the six public Agent-Spice workflows recorded in
docs/baselines/as-upstream-adapter-contracts.v1.yaml:

* fit-sparam
* fit-sparam-cascade
* fit-yparam
* tune-yparam-tran
* run-hspice
* run-rfm

The source authority is the external Git object
agent-spice@2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5, tree
b6bde97128030d6cea0d68b2f0a35d807be8c402. The adapter does not copy
Agent-Spice source, fixtures, Python payloads, model data, or simulator
artifacts into SIPI.

## Adapter behavior

crates/sipi-agent-spice-adapter supplies one typed request for each public
entry point and one owned result envelope. Each request owns the exact
argument vector after the command name. The production constructor defaults
to the python -m agent_spice.cli <command> shape; a visible launcher override
exists for compiled fake-process tests. The adapter does not parse, rewrite,
or replace workflow arguments.

run-hspice and run-rfm are different from the fitting commands because the
upstream CLI has a backend selector. Their constructors reject a missing,
duplicate, malformed, or unsupported --backend value. They do not insert the
upstream default native. `execute` reparses the exact run argv and rejects a
stored backend that is absent from or disagrees with argv, so public request
fields cannot bypass this invariant. Fitting requests have no synthetic
backend field.

The process boundary has bounded stdout and stderr readers, a wall-clock
deadline, a secondary reader-drain deadline, cooperative cancellation with
bounded child reaping, and stable error codes. On Windows, target-only
process-wrap 9.1.0 (`std` plus `job-object`, MIT OR Apache-2.0) creates the
child suspended, assigns it to a Job Object, and resumes it only after the
assignment succeeds. A wrapper below the Job Object owns the suspended child,
so Job creation or assignment failure attempts to terminate that child and returns
`process_isolation_failed` without a raw-child fallback. Job termination
failure is surfaced as `process_termination_failed`; successful Job
termination still reaches descendants when the parent has already exited.
Before publishing any normally exited result, the adapter terminates the
retained Job as well, preventing a detached descendant with closed pipes from
escaping a clean parent exit.
Non-Windows execution only claims direct-child termination.
The caller supplies a working directory and an artifact root. Every workflow
must explicitly provide its primary output root/path; optional output paths
are checked as well. Relative output paths resolve from the canonical working
directory and must remain below the canonical artifact root. Missing default
outputs, output symlinks (including dangling links), symlink parents that
resolve outside the root, and outside-root paths fail closed.
Every admitted output target must be absent before spawn, so a stale target
cannot satisfy the current invocation's success postcondition.

An exit code of zero is not sufficient by itself. The adapter retains each
admitted required target and validates that exact path after the child exits:
fit-sparam and fit-yparam require their `--output` file; cascade, run-hspice,
and run-rfm require their `--output-root` directory; tune-yparam-tran requires
both its `--output-rfm` file and `--work-dir` directory. Missing targets,
wrong file/directory kinds, symlinks or Windows reparse points, and targets whose canonical path escaped
the artifact root return `required_artifact_missing`. Unrelated files already
present elsewhere in the artifact root cannot satisfy this postcondition.

The adapter hashes regular files below the artifact root after execution,
refuses symlinks and Windows reparse points, and enforces byte, file-count,
directory-count, depth, and relative-path-length limits on files and
directories. The complete UTF-8 invocation has a byte budget. Pipe read
errors are not accepted as a clean end of stream.
Non-UTF-8 paths and invocation arguments are rejected rather than lossy
encoded. The result records the declared `contract_source` migration commit,
command, backend, invocation hash, and artifact-manifest hash. It explicitly
reports `runtime_identity: caller_supplied_unverified` and
`runtime_source_authenticated: false`: the process boundary does not prove
that a caller-selected interpreter or its installed package matches the
pinned Git object.

## Direct CLI contract inventory

The YAML record lists the public positional and option surface directly
declared by the pinned src/agent_spice/cli.py. It also records the reachable
dispatch branches and the source modules that the dispatch calls. The
following dependencies and assets are observations, not hidden adapter
defaults:

* S/Y fitting reaches NumPy, SciPy, scikit-rf, and optional CVXPY/KYP paths.
  It consumes caller-owned Touchstone files, cascade manifests, tuning
  profiles, and output paths.
* TRAN tuning reaches an external HSPICE process and license endpoint for
  every trial selected by the upstream optimizer.
* HSPICE execution reaches native, ngspice, Xyce, or XDM paths only when the
  caller explicitly selects that backend. Includes, probes, measurements,
  native engine files, and RFM files remain upstream-owned assets.
* RFM execution parses a Cadence Broadband SPICE model, verifies sampled
  frequency response, then prepares the explicit native or ngspice route.

The adapter maps process launch, timeout, cancellation, bounded output, and
artifact custody failures. It intentionally leaves upstream semantic errors
and non-zero exit codes visible in the result rather than hiding them behind a
fallback.

## Status by migration row

| Row | Adapter | Rust candidate | Workflow parity |
| --- | --- | --- | --- |
| AS-01 | typed transport implemented | candidate exists | not evaluated |
| AS-02 | typed transport implemented | candidate exists | not evaluated |
| AS-03 | typed transport implemented | candidate exists | not evaluated |
| AS-04 | typed transport implemented | candidate exists | not evaluated |
| AS-05 | typed transport with explicit backend | fixed-profile candidate | profile-only, not workflow parity |
| AS-06 | typed transport with explicit backend | candidate exists | not evaluated |

## Verification

Focused Rust tests use a compiled fake interpreter. They cover exact argument
preservation, explicit backend admission, non-zero child status, bounded
stdout, timeout, cancellation, artifact hashing, and pre-spawn validation.
They also cover outside-root output rejection, dangling output symlinks, argv
limits, artifact structure limits, positive and missing-output cases for all
six workflows, wrong artifact kinds, both tune-yparam-tran targets, and
Windows descendants that inherit the output pipe. The Windows coverage
includes a child that exits first while its descendant remains alive; the
normal-exit cleanup terminates the retained Job Object before reader drain. A separate
output-overflow descendant test exercises the same Job termination path. Both
tests verify the descendant PID is gone. Cancellation and clean parent exit
have their own descendant-PID regressions; nested Windows junction traversal
is rejected.
cargo test, cargo fmt --check, and cargo clippy --all-targets -- -D warnings
are required for this isolated candidate crate.

tools/verify_as_upstream_adapters.py always validates the repository-owned
contract, pinned source-index digest, audit hash, six request types, output
postconditions, dependency policy, and adapter safety/test markers. `--source`
is optional: when explicitly supplied, the verifier additionally recomputes
the exact source tree and every hash-bound Git blob and reports
`source_git_objects_checked: true`. Session-health verification therefore
does not depend on a machine-specific external worktree.

## Deliberate blockers

This slice does not claim numerical parity, oracle-corpus coverage, upstream
runtime availability, vendor or HSPICE licensing, or product workspace
integration. It also does not claim authentication of the runtime Python
package. Exact-source smoke runs remain ignored and external. A later
Rust replacement must first bind each row to an upstream branch-complete
oracle matrix; the presence of this transport adapter or an existing
clean-room Rust helper is not sufficient.
