# P7-05a Release Capability Publication

P7-05a publishes a machine-verifiable, pre-release evidence ledger. It is
bound to the product command manifest so a command cannot be described as
available or unavailable differently from the product itself.

The ledger distinguishes product surface availability from acceptance evidence.
For example, the fixed RC/PULSE TRAN command is available while its external
acceptance compare remains specified but unexecuted. Channel, AMI, COM, project
execution, and external comparison remain unavailable or blocked as recorded.

The ledger is deliberately not release notes, an SBOM/NOTICE substitute, a
legal determination, a fresh-machine certification, or profile certification.
Its global `release_ready` value is false and its promotion status is blocked.

For the current product command manifest capture, the command-response SHA-256
was `15c1e6f0ebf420c0e6928bc00f8ff36fe3abf0fa2f6bd80ded3091570ba07847`.
The deterministic rendered publication had SHA-256
`2355357d7c388e26d16b64b63290df901ef4fa95cfd6f2320d76a71a88d3a5bd`.

One Orca read-only review found no P1 or P2 findings. Its descriptor-shape
P3 observation was closed by requiring the exact command-manifest v1 field
set, validated route/id uniqueness, approved transports, and consistent
availability/reason fields before ledger binding. The publication remains
provisional and blocked.
