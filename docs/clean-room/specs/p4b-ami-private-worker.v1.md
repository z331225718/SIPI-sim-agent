# P4B Private AMI Worker v1

`sipi-ami-worker` runs one versioned job and exits. It is not part of the
public `sipi` CLI and does not implement AMI parameters, IBIS binding, vendor
runtime support, or a sandbox.

The job has only job-root-relative, hash-pinned sidecars and bundle entries.
The worker revalidates each identity, raw parameter binding, bounded f64le
sidecar, and host ABI revision. It checks cancellation and deadline before
Init, before GetWave, and before publication. A foreign call cannot be
interrupted safely.

Success is published only through the immutable artifact staging primitive.
Errors publish no success artifact. The test-only supervisor verifies the
worker executable hash before spawning it and kills it after a hard parent
deadline. Killing the worker does not prove Close, process-tree cleanup,
dependency closure, or sandboxing.
