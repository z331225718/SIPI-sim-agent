# P6-09a Current-Topology Negative Gate v1

This test gate covers only the current product-owned, in-process topology:
the fixed `tran-rc-pulse-v1` `voltage_in` handoff, the DirectLaunch
causal-FIR attempt and P6 edge record, followed by P1 immutable artifact
verification and the `report inspect` metadata projection.

The gate uses a test-only publication bridge because P6 deliberately has no
project executor or P6 artifact writer. That bridge is test code only: it is
not a CLI route, a project runtime, a retry/cache mechanism, or a producer of
product artifacts.

The scenario matrix is fixed:

| Scenario | Required terminal outcome |
| --- | --- |
| A declared TRAN-result to Link-request project edge | planner rejects the contract mismatch before execution |
| Consumer-policy digest drift | the original record rejects the drifted policy/output pair |
| Pre-cancelled or under-budget attempt | no completed attempt, record, or publication state |
| Unsealed staged artifact | `report inspect` returns only the normal failure envelope and diagnostic |
| Published artifact with changed payload | re-verification fails before any report projection |
| Untampered control | record verifies and the report exposes only allowlisted integrity metadata |

The negative report path must not emit a successful report schema, partial
metadata, payload text, file name, local root, or external-asset information.
The positive report must hide the test payload schema, filename, and local
root as well.

Worker crash is explicitly `not_applicable_current_topology`: P6 currently
does not dispatch a worker. P4B mock-worker termination remains separately
tested and cannot be promoted as P6 integration evidence. This gate therefore
does not claim project execution, multi-edge recovery, worker supervision,
retry/cache behavior, AMI/COM integration, external comparison, or a generic
fault framework.
