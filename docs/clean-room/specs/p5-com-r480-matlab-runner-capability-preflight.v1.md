# P5 COM R480 MATLAB Runner Capability Preflight v1

## Purpose

This is an observer-only capability probe for a locally supplied MATLAB
executable. It asks MATLAB built-ins for a version sentinel from an empty,
worktree-external directory. It never receives an `agent-com` path, a MATLAB
source file, a workbook, fixture data, R480 parameter material, or a product
request.

## Isolation and Evidence

The probe clears `MATLABPATH`, creates a temporary external preference
directory, starts the supplied executable without a shell, and has a fixed
30-second timeout. On timeout it terminates the process tree. The external
report stores only logical identity, executable byte hash and size, fixed probe
template hash, bounded outcome fields, and hashes of captured streams. It
contains no executable path, temporary path, license key, server identity, or
stream contents.

MATLAB startup isolation is not proven by these controls. Therefore a probe
result remains `indeterminate` even if a version sentinel is observed. It can
only establish that a particular runner candidate was observed under a bounded
probe; it cannot establish a right to use MATLAB, R480 runner availability,
or a COM reference result.

## Non-Claims

This preflight does not execute an oracle, read external COM material, create a
product API, define defaults, produce a golden, or reduce any of the blocked
authoritative-reference requirements.
