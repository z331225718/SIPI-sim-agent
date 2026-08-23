# AS-03 `fit-yparam` direct-port audit

The pinned MIT source is Agent-Spice commit
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`; source bytes remain external.

Reachable upstream entry paths are `src/agent_spice/cli.py`,
`src/agent_spice/sparam/yparam.py`, `native_vf.py`, `pole_relocation.py`,
`z_metrics.py`, `rational_lft.py`, `y_pr.py`, and `artifacts.py`; exact
delivery in the authority uses Python NumPy/SciPy/scikit-rf/CVX tooling. The
Rust leaf ports the portable matrix/control path with a native real KYP-LMI
feasibility route: it obtains a candidate P from the equivalent continuous-time
Riccati invariant subspace, audits the full symmetric KYP LMI and P eigenvalue,
and, when needed, corrects C/D along a bounded feasible path. It does not use
sampled passivity or a D-only/Hamiltonian heuristic as the exact certificate.

The Rust leaf admits bounded Touchstone 1.x `.sNp` input through 32 ports,
supports RI/MA/DB conversion with a shared real reference, remaps Touchstone
column-major data into row-major matrices, evaluates the matrix S-to-Y
transform with an explicit condition gate, and fits converted samples with
bounded native vector-fitting pole relocation and residue refits. It checks
sampled Y positive-realness and writes Y SPICE, JSON/log, HTML, and derived S
Touchstone artifacts. Y SPICE poles/residues are de-normalized by
`frequency_scale_hz`; complex-pole residues are emitted as separate real and
imaginary paths. On the explicit `--no-fit-proportional` path, a proper
rational Y-to-S state-space LFT can publish exact S Touchstone/RFM/wrapper
artifacts only after the native continuous KYP-LMI P/C/D certificate and
stability gate pass. A failed exact gate returns before exact artifacts are
written. Auto-order trials retry higher orders rather than publishing a fake
artifact, and `passivity=enforce` is rejected because a sampled check is not
silently promoted to enforcement.

Proportional/descriptor exact delivery (the pinned CLI rejects that input
combination) and upstream NumPy/SciPy numeric parity remain open evidence; the
portable KYP certificate itself is implemented locally. The v1 replay reports
include a three-port exact and HTML case only as unbound preparation
observations, with no immutable source binding or tolerance claim. An additive
v2 is reserved until after the preparation commit.
