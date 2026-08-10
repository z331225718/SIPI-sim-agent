# P6-04a Fixed TRAN-to-Link Cooperative Attempt v1

This specification covers exactly one in-memory attempt over the admitted
`tran-rc-pulse-v1` `voltage_in` to DirectLaunch causal-FIR edge. It does not
define a project executor, a retry policy, a cache, artifact publication, or a
CLI route.

`run_fixed_tran_to_causal_fir_with_context_v1` accepts the caller-owned
`RunContext`. It first reserves a checked, explicit estimate for the fixed
TRAN work plus direct convolution and their retained f64 samples. The fixed
TRAN solver and causal-FIR convolution then share that same context. Both
operations checkpoint at their pre-existing deterministic boundaries; the FIR
checks before each output sample without changing its numerical accumulation
order.

A successful attempt has schema `sipi.edge-attempt.tran-rc-pulse-to-causal-fir.v1`,
attempt index `1`, the complete received waveform, and the P6-03a edge record.
The runtime alone marks success. Any cancellation, deadline, resource failure,
validation failure, or numerical failure returns no attempt result and no edge
record. Attempt index one is the only valid index in this version.

No retry, cache lookup/insert, persistent run history, artifact, worker,
external asset, S2P/RFM/IBIS/AMI/COM route, or project scheduling semantics are
introduced by this boundary.
