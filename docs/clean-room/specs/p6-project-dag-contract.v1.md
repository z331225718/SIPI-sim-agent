# P6 Project DAG Contract Specification v1

## Scope

This specification defines `sipi.project.v1` and its non-executing validation
planner. It covers only a declarative project graph: stable node kinds,
versioned artifact-contract identifiers, named input and output ports, an
explicit resource policy, a 32-byte deterministic seed, requested outputs,
canonical topological order, and a deterministic plan digest.

The initial product catalog contains only `tran.rc_pulse` and
`link.causal_fir`. Both descriptors state their request/result contract IDs;
they do not execute the corresponding domain implementation.

## Validation

Every plan has a fixed schema identifier and canonical ASCII identifiers. A
resource policy has nonzero timeout, work-unit, and accounted-byte limits. The
seed is exactly 32 bytes of lowercase hexadecimal text. Node kinds and all
input/output ports are resolved only through the closed product catalog.

An edge binds exactly one producer to exactly one required consumer port and
must carry the exact artifact-contract identifier declared on both ends.
Project inputs are explicit producers. Duplicate IDs, duplicate edges,
duplicate bindings, unknown ports/kinds/inputs, contract mismatch, missing
node inputs, invalid requested outputs, cycles, and nodes that cannot reach a
requested output are rejected.

The planner produces only a lexicographically tie-broken topological order and
a domain-separated SHA-256 digest over the validated declaration. It does not
publish the process-local `TypeId` metadata from the P1 generic DAG.

## Non-Claims

This specification does not execute nodes; call domain libraries; create
artifacts; start workers; read files, URLs, or external assets; run Python,
MATLAB, or vendor binaries; schedule/retry/cancel work; implement cache
storage; provide a `sipi project` CLI command; define cross-domain edges; or
certify TRAN, Channel, IBIS/AMI, COM, profile accuracy, release readiness, or
AI project execution.
