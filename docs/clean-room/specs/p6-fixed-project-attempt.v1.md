# P6-04b Fixed Composite Project Attempt v1

This specification defines exactly one project-scoped execution route:
`tran-rc-pulse-v1` source voltage to a DirectLaunch causal-FIR receiver. It is
not a generic project executor and it introduces no route for any other
domain, worker, artifact, retry, cache, or CLI command.

The declarative plan must first satisfy `sipi.project.v1`. It must then be
exactly one `project.tran-rc-pulse-to-causal-fir` node named `run`, one
project input named `binding`, one input edge to that node, and one requested
`received` output. The binding is an in-memory product value containing only
the fixed TRAN request and an explicit causal-FIR policy. Extra nodes, edges,
inputs, or outputs are rejected.

The caller supplies the cooperative `RunContext`; the project does not create
or replace it. Its run id must exactly equal the project id, and its timeout,
work-unit budget, and accounted-byte budget must exactly equal the plan policy.
The attempt invokes the existing context-aware fixed TRAN-to-causal-FIR edge
once. A successful result is attempt index `1` plus the plan digest, binding
digest, edge record, and received waveform. Cancellation, deadline, resource,
validation, or numerical failure returns no completed project result.

This boundary does not define generic node dispatch, multi-edge scheduling,
retry, cache, persistent history, artifact publication, project JSON request,
CLI `project run`, or AMI/IBIS/COM/S2P/RFM integration.
