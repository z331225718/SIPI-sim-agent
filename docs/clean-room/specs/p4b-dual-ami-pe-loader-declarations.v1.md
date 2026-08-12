# P4B Dual-AMI PE Loader Declarations v1

This external-only observer reads exactly the two DLLs already identity-bound
by P4B-05b. It makes two independent private copies, verifies the expected
name, byte length and SHA-256 before parsing, and reports only canonical
static PE declaration facts. It never loads a DLL, invokes ADS, runs a worker,
or recursively resolves any system dependency.

For each DLL, the observer records PE machine/DLL flag, normal and delay
import module-to-symbol declarations (name or ordinal), bound-import module
and forwarder declarations, exported forwarders, embedded `RT_MANIFEST`
resource hashes and bounded assembly/dependency/file declarations, TLS/CLR
directory presence, and direct dynamic-loader API import indicators. Any
malformed RVA, truncated table, unsupported delay-import representation,
unsafe manifest XML, or disagreement between the two fresh reports rejects
the observation.

Absence of a declaration is not dependency closure. The result remains
`external_only_static_loader_declarations_observed_dynamic_runtime_closure_and_worker_admission_blocked`.
It does not admit sidecar files, prove loadability, rights, AMI/IBIS
compatibility, GetWave behavior, TX-to-RX composition, numerical parity, or
any release/product/runtime capability.
