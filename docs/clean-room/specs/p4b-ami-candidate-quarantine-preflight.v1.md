# P4B AMI Candidate Quarantine Preflight v1

## Scope

This preflight inventories the current tracked `sipi-ami` candidate and the
tracked `sipi-circuit` files that carry its explicit candidate transport. It
uses only Git-object identity, locked Cargo metadata, and bounded exposure
labels.

## Required Evidence

- Every in-scope path has an immutable Git blob and SHA-256 record.
- Every entry remains `quarantine` and `unknown` in the Rust source map.
- Each Cargo lock closure records package identity and keeps license and NOTICE
  resolution pending P0-06 review.
- Exposures are labels only: dynamic loading and candidate lifecycle transport.
- Public standards are reference metadata only, never implementation material.

## Rejection Rules

The verifier rejects missing or extra paths, hash drift, promotion fields,
non-quarantine source-map entries, unrecorded lock packages, unsafe paths, and
vendor or build-output suffixes. It does not scan sibling repositories, load
assets, or execute a candidate host.

## Non-Claims

This is not an implementation, runtime, ABI, or release gate. It neither
promotes the candidate nor establishes any product capability.
