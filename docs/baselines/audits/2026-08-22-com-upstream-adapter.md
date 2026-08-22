# Agent-COM upstream-first adapter audit

## Scope

This audit covers only the four stable Agent-COM workflows named by ADR-015:
`config validate`, `run`, `compare`, and the public Python sequence
`load_config -> run_com -> write_artifacts`. The upstream source is pinned to
Git commit `5272ffe74702cd585054d975559b06f8afae7b6e`; no source, workbook,
MATLAB, golden, or result bytes are copied into SIPI.

## Adapter boundary

`crates/sipi-agent-com-adapter` starts an external executable without a shell.
It forwards profile, reader, fix IDs, overrides, channel paths, workbook path,
and output paths as individual arguments or bridge JSON values. A missing
option is omitted instead of replaced by a SIPI default, so the upstream CLI
or public API remains the owner of defaults, numerical behavior, checkpoints,
alignment, tolerance, and fallback decisions.

The caller supplies a working directory when constructing the adapter. It is
accepted only when it resolves to an existing directory and neither it nor an
existing ancestor is a symlink or Windows reparse-point junction. The adapter
stores that canonical directory, sets it with `Command::current_dir`, and
resolves every relative request path against it before CLI or bridge
transport. Relative artifact paths returned by the backend use the same base
before containment checks, so no request path inherits the SIPI process cwd.

For the public API bridge, an omitted profile is passed as `None` to upstream
`load_config`, leaving default selection upstream-owned. A supplied profile
must name either an enabled preset or `custom`; `custom` requires an explicit
reader. Empty profile objects and custom profiles that would require the
bridge to invent `r480` reader semantics are rejected before process launch.

The process layer bounds stdout, stderr, public-bridge stdin, wall time,
cancellation, and output-directory bytes. Artifact paths returned by the
backend must be regular files inside the requested output directory. Result
payloads are not parsed or recomputed by Rust. Compare exit code `3` is
returned as a typed non-match report; other non-zero codes use the upstream
stable exit-code mapping.

On Windows, the target-specific `process-wrap` 9.1.0 dependency (`std` and
`job-object` features, declared `MIT OR Apache-2.0`) creates the child
suspended, assigns it to a Job Object, and only then resumes it. A small outer
wrapper directly kills the still-suspended child if Job Object creation,
assignment, or resume fails, so setup cannot fall back to a running bare
process. Timeout, cancellation, stdout/stderr overflow, and normal parent exit
all terminate the Job Object, then use bounded job wait and pipe joins. This
also terminates a long-lived descendant when its parent exits first while the
descendant retains inherited pipes. Non-Windows builds retain only the stated
bounded direct-child fallback.

The total argv byte bound includes the executable, fixed backend arguments,
and the complete operation-specific final argv. The requested artifact root
and every existing ancestor are rejected when they are a symlink or Windows
reparse-point junction; artifact scans also reject any symlink, junction,
special file, or other non-regular entry and enforce a caller-visible hard
entry-count limit as well as byte/depth bounds.

## Reachability and external assets

| Row | Reachable upstream surface | External inputs | Deliberately not reached |
| --- | --- | --- | --- |
| COM-01 | `cli._validate`, `ComConfig.from_path`, materialization and consumption report | workbook path and bytes | MATLAB execution, golden result |
| COM-02 | `cli._run`, `load_config`/materialization, `run_com`, reporting | workbook, THRU/FEXT/NEXT, optional calibration noise | MATLAB execution, golden result |
| COM-03 | `cli.compare`, `read_result_json`, `compare_result_json` | golden/result JSON | workbook, MATLAB execution |
| COM-04 | public `load_config`, `run_com`, `write_artifacts` sequence | workbook, channels, optional calibration noise | MATLAB execution, golden result |

The workbook and channel files remain caller-owned external assets. The
upstream `CONFIG_CONSUMPTION_AUDIT.md` classification is preserved as a
reporting fact (`implemented`, `report_only`, `unimplemented`, `obsolete`,
`unverified`); it is not converted into Rust parity. The current observed
summary is 196/26/1/15/0, with `Do_White_Noise` the recorded unimplemented
field. Runtime reads, mutation coverage, MATLAB source failures, and golden
corpora remain upstream evidence and are not fabricated by this adapter.

The explicit `--log-file` and `--progress-jsonl` outputs must remain below the
caller-selected `--output-dir`; parent traversal and link/reparse ancestors
fail before spawn. This is designated-output containment only. The external
runtime is not source-attested, no filesystem sandbox or hostile-writer
custody is claimed, COM overwrite/freshness semantics remain upstream-owned,
and CPU, memory, and process-count isolation are outside this adapter.

## Verification

`tools/verify_com_upstream_adapter.py` binds the source commit, tree, per-file
Git blob identity, adapter markers, workflow inventory, and non-claims. Its
mutation tests prove that source drift, workflow deletion, and accidental
parity/release claims fail closed. Rust fake-backend tests exercise argument
transport, final argv budgeting, artifact containment, symlink rejection,
working-directory ownership and relative path resolution, artifact entry
counting, compare mismatch handling, timeout, cancellation, output limits,
parent-first-exit descendant PID termination and pipe drain, and the public
API sequence without adding external bytes.

## Status

The four process adapters are implemented and independently bounded. All four
remain `adapter_implemented_parity_pending`: this audit does not close COM-01
through COM-04 in the upstream migration inventory, and it does not authorize
Rust replacement or release promotion.
