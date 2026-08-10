# P6-05a Command Manifest v1

`sipi.command-manifest.v1` is the single product-owned discovery source for
the current command surface. Every entry fixes a command id, token route,
availability, transport, optional request/response schema ids, unavailable
reason, and an explicit nonclaim. Entries are deterministic static data and
contain no filesystem paths, external asset identifiers, legacy names, or
roadmap claims.

Only routes with existing product handlers are `available`. The current
available surface remains the exact TRAN and causal-FIR runs, structural IBIS
inspection, and static version/doctor/capabilities/schema/validation/inspect
commands. The `commands --json` command returns this manifest.

Recognized but unavailable routes include channel, AMI, COM, project, compare,
and report workflows. They return the normal protocol's unsupported exit code
with a `sipi.command-unavailable.v1` result containing only the command id and
stable reason. They do not consume stdin, read a file, create an artifact,
start a runtime, or invoke an oracle.

The manifest validates route/id uniqueness, supported transport values, and
the invariant that an available route has a handler while an unavailable route
does not. Capabilities derive their limited TRAN/channel status from manifest
availability. This does not implement project execution, channel resolution,
AMI/COM runtime, comparison, or report viewing.
