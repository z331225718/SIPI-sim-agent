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
