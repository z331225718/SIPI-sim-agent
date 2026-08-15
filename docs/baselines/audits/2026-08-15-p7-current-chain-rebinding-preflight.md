# P7 Current-Chain Rebinding Preflight

The clean Git archive for candidate `b775dde6d242e687eb71a30b9a83a87d8b31ba55`
was built twice with the P7-01 Windows x86_64 locked/offline twin-build gate.
The two `sipi.exe` outputs were byte-identical: SHA-256
`a3059d052df54c0f3ebbd727bd2f71760ff33f73af82e1e2f29c0ec35b8c882d`,
3,908,608 bytes. The external twin report hash is
`c36b01389230e14bece2eecdcfb438be2ad1f3bfbda64616c27f7ced3932be62`.

The admitted stage was then checked by a `sipi-layout-verify` binary built
from the same clean archive with an independent external target directory.
The retained policy identity was
`a0ac8e7efd9d2c35a69aa6f48f8cb063cb837b779d18be0a21f39e0132e11ce2`.
It rejected the current executable with the fixed JSON result
`rejected/pe_rejected` (exit 2). The stage executable hash was unchanged
before and after the check. Only the 86-byte JSON result hash is recorded;
the executable, policy path, stage path, and any external reports remain out
of the repository.

Therefore the current chain stops before P7-02 composition, P7-03 archive,
P7-04 isolated install, P7-06 measurement, and P7-06 candidate evaluation.
This is a rejected preflight observation, not a diagnosis of the PE, a static
dependency-closure result, a policy change, or a release candidate. The older
P7-01 through P7-07a records remain historical and cannot be inherited by
this candidate.

## OMP Audit

The existing OMP reviewer re-read the staged verifier and tests after the
external layout-policy and stage-executable bindings were added. It found no
Critical or High findings. Its read-only checks covered the clean-archive
twin identity, the fail-closed downstream stop, mutation coverage for the
candidate/archive/external evidence/promotion paths, and synchronized
boundary, license-manifest, and source-map hashes. It also confirmed that the
user's uncommitted Rust files and `uv.lock` were outside the staged scope.
