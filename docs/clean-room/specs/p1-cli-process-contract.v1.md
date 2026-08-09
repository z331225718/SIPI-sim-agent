# P1 CLI Process Contract v1

## Scope

This specification covers the P1-09 process adapter and product-owned
validation request in `crates/sipi-cli/**` and `crates/sipi-contracts/**`.

## Observable Behavior

Each invocation writes exactly one UTF-8 JSON response line to stdout. Failed
commands additionally write one UTF-8 JSON diagnostic line to stderr. No
banner, progress, color, help text, or raw schema bypasses these streams.
Exit codes are fixed: `0` success, `2` usage/input syntax, `3` contract
rejection, `4` recognized unsupported capability, `5` operational failure,
and `6` internal failure.

Only `validate --stdin` reads input. It accepts at most 1,048,576 bytes of one
UTF-8 JSON `sipi.validation-request.v1` document, rejects empty input and a
UTF-8 BOM, and routes its waveform subject through existing P1 contract and
core validation. It does not execute a simulation. Other commands do not read
stdin, files, artifacts, environments, engines, or external assets.

## Non-Claims

This specification does not define NDJSON event streaming, request files,
artifact inspection, run execution, runtime control, domain input, legacy
compatibility, profile accuracy, platform certification, release readiness, or
strict clean-room process.
