# P1 Unsupported CLI Foundation Specification v1

## Scope

This specification covers `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`,
and `crates/**` for the P1-01 product foundation. It covers no simulation
algorithm, external asset, fixture, comparison, or numerical result.

## Allowed Materials

The implementation may use this independently authored specification and
project-authored Rust toolchain metadata. It must not consume legacy source,
external engines, model files, or oracle outputs.

## Observable Behavior

The `sipi` binary accepts `--version`, `version --json`, and
`capabilities --json`. Successful output is one JSON object on stdout. The
capability response lists `tran`, `channel`, `ibis-ami`, and `com`, each with
the status `unsupported` and reason `not_implemented`.

The `run` command exits with code 69, writes one `sipi.cli-error.v1` JSON
object to stderr, and writes no stdout. Unknown input exits with code 64 and
the same error schema.

## Non-Claims

This foundation does not implement a domain, numerical method, file parser,
legacy-example comparison, default route, or platform certification. It does
not establish release eligibility or strict clean-room completion.
