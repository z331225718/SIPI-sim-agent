# P4B-02 production parameter adapter selection

The current product AMI route has one parameter representation: bounded raw AMI
text validated as `AmiTextBindingV1`. `sipi-ami-worker::run_one_job` reads the
identity-bound parameter sidecar and calls `parse_and_bind_v1`.
`sipi-ami-host::AmiHostV1::initialize` calls `verify_binding_v1`, rejects an
interior NUL through `CString`, and passes the same bytes to `AMI_Init`.

No current host or worker path consumes any of the 193 feature-quarantined
parameter semantic helper modules. Consequently the production selection is
an empty typed-helper set, not a missing implementation. The existing selection
charter remains authoritative at 0 `keep_for_product`, 34
`quarantine_pending_requirement`, and 159 `delete_candidate` modules.

The 34 quarantined modules remain blocked on an authorized AMI profile with
explicit parameter requirements and an independent oracle. The 159 delete
candidates are recorded for a separate deletion batch; this audit performs no
bulk deletion and does not alter historical evidence. Vendor rights, dynamic
dependency closure, isolated runtime execution, and external waveform parity
remain outside this selection result.
