# P4A-06 Structural IBIS Inspect Audit

Date: 2026-08-11

## Scope

Commit `1982a22` adds the product-owned `sipi ibis inspect --stdin` path. It
accepts exactly one `sipi.ibis.inspect.request.v1` JSON request containing a
UTF-8 text value, then invokes only the bounded structural parser and typed
semantic envelope.

## Reviewer Result

Orca review `msg_361f39539b9c` reported zero P1 and zero P2 findings.

## Verified Boundary

- The request has no file, URL, base64, profile, evaluation, external-asset,
  or oracle field. Unknown fields, unsupported encoding, empty input, and
  malformed or rejected text fail closed.
- The successful report exposes only the input byte length and hash, lexical
  version, and declaration/block counts. It always reports electrical behavior
  and external-profile acceptance as `not_evaluated`.
- The command uses the existing one-response JSON, diagnostics, and exit-code
  process contract. Other `ibis` command shapes reject as unsupported.
- The schema baseline and inventory are synchronized. The P4A conformance
  matrix records this as a self-tested structural surface, not electrical or
  general IBIS acceptance.

## Verification

`cargo test -p sipi-ibis -p sipi-contracts -p sipi-cli` passed: 20 IBIS
library tests, 21 contract tests, and 13 CLI unit/integration tests. The P4A
matrix verifier and all five P0 verifiers passed. The reviewer also exercised
the process route: valid input returned exit 0; a binary encoding or unknown
field returned exit 3; and `--file` returned exit 4.

## Limits

This is an in-memory structural inspection surface. It does not read an IBIS
file or URL, select/decode a profile, evaluate electrical behavior, access an
external asset, invoke an oracle, support AMI, or alter the default route.
