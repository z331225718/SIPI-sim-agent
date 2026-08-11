# P7 Release Composition Preflight v1

## Scope

This external Windows x86_64 preflight binds an explicit stage to a successful
P7 twin-build report, the current locked Cargo resolution, the provisional
release-license manifest, and a successful P1 static layout report. It creates
a versioned identity-and-gap report only.

## Required Evidence

The staged `sipi.exe` must exactly match both the twin-build and layout-report
size and SHA-256. The current Git commit/tree, `Cargo.lock`, and toolchain
hashes must match the twin-build report. The layout report must be AMD64,
layout-conformant, and observe no delay-import directory. Each locked package
is listed with a sanitized source kind and matched, if possible, to a release
manifest dependency review and NOTICE status.

The output always has `promotion_status: blocked`. In `observe` mode it may
report pending or unclassified gaps. The default `release-gate` mode exits
nonzero even when collection succeeds, because this slice cannot authorize a
release.

## Non-Claims

This is not an SPDX or CycloneDX SBOM, an authorized NOTICE, a license
compatibility finding, a dynamic-loader/runtime dependency closure, a release
archive, or release approval. Paths, source URLs, external assets, report
inputs, and binary bytes are not emitted.
