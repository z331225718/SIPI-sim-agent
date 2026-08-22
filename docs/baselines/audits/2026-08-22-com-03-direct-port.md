# COM-03 direct-port audit

## Scope

This audit covers only the pinned Agent-COM `compare` workflow at commit
`5272ffe74702cd585054d975559b06f8afae7b6e`. The lane-local Rust crate reads
two caller-owned result JSON files, validates the upstream result-v1 contract,
removes exactly the upstream non-comparable timing/platform metadata, and
performs the upstream absolute-tolerance recursive comparison. It does not run
COM, load a workbook, create a golden file, or promote a product capability.

## Per-path MIT provenance

The translated behavior is sourced only from `src/agent_com/reporting.py`
(reader, validation, comparable projection, recursive compare),
`src/agent_com/cli.py` (default `atol` and exit mapping), and
`schemas/result-v1.schema.json` (artifact contract). Each path's Git blob ID,
content SHA-256, byte length, and MIT classification are frozen in
`docs/baselines/com-03-direct-port.v1.yaml`; the required attribution and
derived-file map are in `crates/sipi-agent-com-direct/NOTICE-AGENT-COM-MIT.md`
and `SOURCE-MAP.md`.

No upstream source, workbook, MATLAB file, golden payload, or result payload is
vendored into the lane.

## Implemented contract

- Required top-level result keys and optional `input_manifest`/
  `report_manifest` are checked exactly as the pinned reader's narrow runtime
  validator.
- Python-compatible `schema_version` equality accepts JSON `1`, `1.0`, and
  `true`; the exercised provenance object, empty sequence, and string-key
  pair sequence forms are converted with the same `dict()` semantics before
  non-comparable keys are removed.
- `schema_version=1`, `source_revision=r480`, profile revision, non-empty
  contiguous case indices, metric map, nonnegative `A_s`/`available_signal_v`,
  integer optimization cursor, and `EW_UI` shape checks are preserved.
- `timings_s`, `provenance.platform`, and `provenance.python_version` are
  removed before compare; all other fields remain comparable.
- Dictionaries report key-set mismatch and recursively compare common keys;
  arrays report length mismatch or recursively compare aligned values; scalar
  numbers use absolute-only `atol` with `rtol=0`; mismatch messages retain the
  upstream `$...` path format.
- CLI output uses the upstream `matched`/`mismatches` shape. Match exits 0,
  mismatch exits 3, malformed JSON exits 2, schema/tolerance errors exit 3,
  and file I/O errors exit 1.

## Oracle evidence

`tools/run_com_03_direct_oracle.py` materializes a clean archive from the
pinned Git object when the external COM worktree contains unrelated changes.
It invokes both the upstream Python function and the upstream CLI entry point,
then invokes the lane-local Rust binary over a 23-scenario scoped corpus.
The corpus includes malformed JSON, schema, negative-tolerance, both
missing-file I/O exits, Python's `True`/`1.0` schema-version equality, and
`dict()`-compatible empty and string-key pair-list provenance sequences.
Two fresh process invocations produced unbound observation reports with
`all_cli_contracts_match: true`, and the aggregate report proves identical
scenario outcomes across those runs. The reports also carry a deterministic
upstream archive inventory digest and scenario-set digest, but deliberately do
not claim an immutable candidate commit/tree, crate inventory, Cargo.lock,
toolchain, or binary binding before the preparation commit. Diagnostic stderr
and exception messages are reduced to stable categories, and report paths are
redacted so local usernames and temporary directories never enter committed
evidence.
The temporary JSON inputs were deleted after each run; only their SHA-256
digests and outcomes remain in the reports.

The Rust port intentionally follows Python's permissive schema-version numeric
equality and `dict()` conversion for the exercised provenance sequence forms;
non-string pair keys and other unexercised conversion failures remain open.

CLI exit codes and stdout result documents are the frozen contract. Human
diagnostic stderr text is intentionally not a contract: Python and Rust may
describe malformed or missing-file errors differently, while both preserve the
same error class and exit code. This establishes parity for the frozen scoped
corpus and independent pinned-oracle invocation; it is not a branch-complete
claim. The corpus does not cover the full argparse invalid-argument matrix or
every Python `dict()` conversion shape. It also does not prove full COM numerical parity, runtime source authentication,
workbook/run/public-API behavior, or release readiness.

After the preparation commit, the same runner can be invoked with a candidate
root exposing the explicit candidate commit, toolchain, and Cargo executable;
it then materializes the candidate Git archive into an independent temporary
source root, builds with an independent `CARGO_TARGET_DIR`, and executes that
fresh binary. Passing `--rust-binary` in this bound mode is rejected. That
second phase verifies the immutable candidate bindings before a bound evidence
status is considered.
