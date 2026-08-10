# P4B External AMI Asset Set v1

This governance boundary describes an external AMI asset set without storing
its bytes in SIPI. It exists so a future private worker can admit only a
complete, hash-pinned, explicitly scoped set of caller-supplied assets.

Every asset has an immutable identity, a repository-relative source reference,
a role, and a third-party-rights observation. The set is Windows x64 only,
external custody only, and packaging is prohibited. Owner permission for a
limited external observation does not establish redistribution, release, or
MIT compatibility.

`external_worker_candidate` may be admitted only when the IBIS model, AMI text,
primary DLL, and every non-system dependency are listed with identities; their
roles bind without ambiguity; the owner scope covers the exact set; and the
set remains external-only. Any identity, role, closure, or authorization drift
is rejected.

Earlier M5B fixture and closure records are prior observation evidence only.
They cannot independently promote an asset, a worker, an engine route, or a
third-party rights conclusion.

This specification does not define AMI parameter semantics, DLL behavior,
IBIS+AMI composition, an operating-system sandbox, or numerical parity.
