# P7-02a Release Composition Preflight

This slice records a provisional composition and static-PE observation for an
external Windows x86_64 stage. The stage executable is bound to a P7-01a twin
report by exact size and SHA-256, and to a P1 layout report that observed AMD64
normal imports with no delay-import directory.

The observed stage for commit `e0bfbb74a590c3edbacb87b02a72fc63c540f9bb`
matched the twin-build executable: 691712 bytes and SHA-256
`cf36303e8997124c8bc1f9d53ea410eb09a6b17431453ef1dd2fb0cca73adfd8`.
The static layout observation admitted normal imports and reported no delay
imports. Dynamic-load and runtime dependency closure remain `not_assessed`.

The locked dependency inventory was intentionally `incomplete`: the current
license manifest has pending direct reviews and unclassified locked packages.
The generated external report therefore fixes `promotion_status: blocked`.
It is neither an SPDX/CycloneDX SBOM nor an authorized NOTICE, compatibility
finding, PE runtime closure, or release decision.

An independent Orca audit reviewed the staged verifier, contract, tests, and
external observation. It reported no P1 or P2 findings. The remaining private
cross-script coupling is fail-closed: an unavailable license preflight rejects
the observation rather than allowing promotion.
