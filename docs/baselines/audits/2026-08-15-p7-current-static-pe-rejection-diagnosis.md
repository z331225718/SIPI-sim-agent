# P7 Current Static-PE Rejection Diagnosis

The rejected P7-06c candidate was observed again through two distinct
hash-pinned executable materializations and the same retained layout policy.
The PE parsed as AMD64, had no delay-import directory, and had the expected
allowed imports plus `bcryptprimitives.dll`. That DLL is outside the fixed
allowlist, so the observation classifies the existing rejection as
`normal_import_disallowed`.

This is a static, external-only diagnosis. It neither changes the layout
policy nor expands its allowlist, and it does not establish static or dynamic
dependency closure. Composition, archive, installation, performance, and
candidate evaluation remain uninvoked; promotion remains blocked.

## OMP Audit

The existing OMP reviewer performed a read-only audit of the staged observer,
evidence binding, and P0 scope. It reported zero High and zero Critical
findings after the PE diagnosis tests, the retained P7-06c preflight verifier,
and the metadata verifiers passed.
