# PB-02..PB-05 branch coverage audit

Authority is the pinned PyBERT source at commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`. The machine-readable inventory is
`docs/baselines/pb-02-05-branch-coverage-matrix.v1.yaml`; its source file
hashes are the evidence boundary for this uncommitted preparation pass.

## Result

`portable_missing` is empty. PB-02 typed request branches are exercised
individually against the reused `native/pybert-core` implementation, including
modulation, patterns, both channel forms, TX/RX FFE (including zero-tap
identity), dummy and adaptive DFE/CDR with contiguous limits, Viterbi ISI/FEC,
noise/effective-seed provenance, BER, jitter, bathtub, statistical eye,
cancellation, resource limits, and fail-closed stage contracts.

PB-03 now projects the upstream legacy CLI's pure-code branches for NRZ, PAM-4,
Duo-binary, the upstream CLI PRBS order set, analytic RLGC, S1P/S2P/S4P
Touchstone channel files (including mixed-mode renumbering and option-line R),
two-column step/impulse files, CTLE file input, FFE/DFE/CDR, Viterbi, and
deterministic legacy noise with separate effective seeds. Legacy `thresh` is
projected into `analysis.jitterRelThresh` and changes the native/reference
spectral threshold rather than being silently discarded. The `.pybert_cfg`
state mapping is decoded by a bounded Rust pickle parser without restoring
Python globals or starting a Python runtime; protocol 3 and protocol 4/5 root
identity are both checked. AMI, IBIS, TS4, GetWave, and DLL/service paths remain
explicit external blockers rather than being treated as portable.

PB-04 preserves the upstream `pybert.native-auto-parity.v1` selection contract.
The pinned gate is blocked and upstream selects Python; this Rust-only lane
therefore fails closed with `selected: python` and
`implementation: external_python_reference_required` instead of silently
substituting an independent Rust reference. Unprojectable external controls
remain typed fail-closed errors. The parity gate is still blocked, so the row
remains open for external Python/Web parity; no promotion is claimed.

PB-05 compares arrays (including discrete bits/indices and nested two-dimensional
eye arrays), metrics, recursive metadata, recursive diagnostics, and non-gating
performance timing when an independent reference payload is supplied. The
result adapter retains bool, int64, and float64 dtype markers; decision-named
arrays are exact even when their encoded values look integral, and compare
artifacts write the corresponding dtype/shape in Deflate NPZ members. Candidate
errors retain the complete external reference payload and its array shapes. A
missing reference is rejected as `not_evaluated` and can never produce a
same-crate self-comparison or parity pass; the pinned Python result adapter/oracle
remains an external parity blocker.

The matrix is an inventory/evidence artifact only. No shared governance,
promotion, root license, or root source-map file was changed by this pass;
the lane-local PB-02 source map and hash-bound notices were updated to record
the additive portable CTLE adaptations; the PB-03 threshold projection and
PB-05 typed result-adapter contract are bound by the matrix hashes above.
