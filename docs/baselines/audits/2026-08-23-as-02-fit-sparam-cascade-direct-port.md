# AS-02 `fit-sparam-cascade` direct-port audit

Source authority is the external MIT Agent-Spice Git object
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5` with tree
`b6bde97128030d6cea0d68b2f0a35d807be8c402`. No upstream Python payload or
fixture is copied into SIPI.

Reachable upstream entry paths are `src/agent_spice/cli.py`,
`src/agent_spice/sparam/cascade.py`, `fitting.py`, `native_vf.py`,
`pole_relocation.py`, `target_fit.py`, `passivity.py`, and `artifacts.py`; the
authority path depends on the Python NumPy/SciPy/scikit-rf stack. The Rust
leaf reuses the lane-local matrix and artifact primitives, but executes its
own bounded native vector-fitting relocation/refit loop instead of presenting
a fixed-pole residue solve as vector fitting.

The Rust leaf validates the version-1 manifest, admits the pinned ordered
two-port cascade contract, renormalizes each block to the delivery Z0, carries
priority-band/full-band gate selection into each block target, and executes
bounded native vector-fitting pole relocation followed by residue refits. It
samples the common frequency intersection, cascades row-major ABCD matrices,
computes the largest sampled singular value, and runs passivity enforcement
from Hamiltonian crossover probes plus adaptive violation bands. Candidate
updates independently optimize constant terms, conjugate-paired residues, and
pole damping; each candidate is rechecked against adaptive samples and no
uniform contraction is used as a substitute. The adjustment branch evaluates
single-block and all-block candidates, checks every enabled block gate plus the
optional cascade RMS target, and records accepted/rejected history. The refit
branch ranks hybrid raw/fitted cascade impact, tries increasing orders with
previous/candidate artifact history, accepts only an improving target-met
candidate, and restores rejected artifacts. Priority-only mode retains a
non-blocking full-band postcheck. The leaf publishes post-adjustment block
Touchstone/RFM/wrapper/SPICE/HTML artifacts, with RFM poles/residues expressed
in physical rad/s and Touchstone delivery remapped from internal row-major
matrices to column-major tokens. Zero forward transmission, invalid manifests,
unsupported ports, and non-finite data fail closed.

The pinned upstream cascade CLI itself admits only two-port `.s2p` blocks;
arbitrary n-port support is therefore not a missing AS-02 branch. Continuous
Hamiltonian trajectory parity and numerical parity against the upstream
SciPy/scikit-rf implementation remain open evidence, not a portability gap or
a parity claim. The v1 runner records two independent unbound preparation
observations, not immutable source binding. An additive v2 is reserved after
the preparation commit; no v1 mismatch is closed by this record.
