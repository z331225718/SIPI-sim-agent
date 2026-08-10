# P5 COM R480 Oracle Invocation-Surface Preflight v1

## Purpose

This observer-only preflight statically scans one hash-pinned external runner
tool to learn its declared invocation surface. It is not an oracle invocation:
the scanner uses Python's `ast` parser only and never imports the target module,
loads a workbook, resolves an input, starts Python/MATLAB, or evaluates COM.

## Boundary

The scanner runs only on the `tools/run_matlab_oracle.py` Git blob from a clean,
external clone of `agent-com@5272ffe`. It records only option tokens and bounded
structural categories: parser construction, observed launch/file-I/O APIs, and
whether help or dry-run behavior can be established without execution. It does
not record code fragments, formulas, default values, file paths, MATLAB/workbook
bytes, fixtures, or numerical output.

## Result

The only successful observation status is
`runner_interface_partially_observed`. Dynamic execution remains prohibited
until a separate execution amendment supplies an exact normalized input and
parameter bundle, authorized runtime/toolchain identity, enforceable isolation,
timeout/tree cleanup, a writable external output boundary, and an explicit
tolerance/alignment policy.

## Non-Claims

This preflight does not authorize execution, establish a runnable MATLAB
oracle, define product defaults, produce a reference bundle, or reduce the
R480 authoritative-reference gate.
