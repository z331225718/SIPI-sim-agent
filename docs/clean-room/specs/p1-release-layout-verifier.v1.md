# P1 Release Layout Verifier Specification v1

## Scope

This specification covers `crates/sipi-layout/**`. It verifies an externally
constructed Windows x86_64 stage directory against a caller-provided,
versioned layout policy. It does not build, copy, archive, install, sign, or
promote a release.

## Allowed Materials

The implementation may use this independently authored specification, the
Rust standard library, and declared parser, JSON, and SHA-256 dependencies.
It must not read legacy source, Python, an engine bundle, a vendor asset, or a
sibling worktree.

## Observable Behavior

The verifier accepts only an explicit stage directory and policy path. The
policy has schema `sipi.release-layout-policy.v1`, an expected `sipi.exe`, a
closed list of required and optional relative paths, normal-import allowlist,
and fixed static smoke commands. The stage is scanned without following
symlinks or reparse points. Extra files, unsafe names, case collisions,
missing files, and non-regular entries are rejected.

The verifier hashes every admitted file, parses the executable with a PE
parser, requires AMD64, validates normal imports against the policy, and
rejects any delay-import directory. It runs only the policy's static commands
from a fresh external current directory with a scrubbed environment. Each
smoke command must follow the P1 process response contract and leave the stage
inventory unchanged.

The machine-readable report contains policy and inventory digests, executable
digest, import names, smoke result digests, status, and limitations. A current
provisional product boundary can produce only `layout_conformant`; it never
produces `release_ready`.

## Non-Claims

This specification does not prove that arbitrary future commands cannot start
children or dynamically load code. It does not establish hostile-filesystem
containment, package/archive correctness, clean twin builds, signatures,
installation, release readiness, legacy compatibility, profile accuracy, or
platform certification.
