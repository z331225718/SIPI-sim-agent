# P7 ProcessPrng Layout Policy v2

P7-06e established that the fixed candidate imports exactly the named Windows API `ProcessPrng` from `bcryptprimitives.dll`, while preserving the existing no-delay-import and forbidden-token boundaries. Under the delegated owner authority, this v2 policy selects the Rust Windows MSVC target floor of Windows 10 or Windows Server 2016 desktop and adds only `bcryptprimitives.dll` to the prior normal-import allowlist.

The policy continues to use the existing `sipi.release-layout-policy.v1` schema. It does not define cross-device API-set behavior, dynamic loader closure, static dependency closure, product callsite provenance, security review, fresh-machine evidence, or release readiness.

An external exact candidate stage passed the new static layout policy, including the four fixed smoke commands. Composition, archive admission, installation, performance, and candidate evaluation deliberately remain pending and require a fresh P7 chain replay.

## OMP Audit

The existing OMP reviewer terminal `term_fa7831f5-ec22-4b3d-8737-25a919226b8b` reviewed the staged v2 policy scope. Result: 0 High / 0 Critical / 0 Medium findings. It confirmed the one-DLL additive delta, target boundary, exact external layout binding, downstream gates, and P0 metadata synchronization.
