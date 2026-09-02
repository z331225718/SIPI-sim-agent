# PB-02 Pinned Native Source Corpus Acceptance

Candidate `d2047cd1977f76aecb81c1674c031672bac5ff13` was materialized from a
Git archive twice. The pinned PyBERT oracle was independently materialized
from `5bf6d7ea0ace261891aaeb611ffc1c267e160afe` twice and run through frozen,
offline `uv` with its native extra. The candidate was built from each candidate
archive rather than accepted from a caller-supplied binary.

Both replays passed the twelve successful configurations owned by pinned
`native/pybert-core/tests/simulation.rs`: linear, additive noise, CTLE noise,
both metallic-line window choices, CTLE, jitter/bathtub, statistical eye, DFE,
DFE plus pre-DFE eye, ISI Viterbi, and PAM4-FEC Viterbi. Each compares complete
metadata and diagnostics after only the runtime input-path and engine-build
normalizations, plus every NPZ member name, dtype, shape and value using
`rtol=1e-9`, `atol=1e-12`.

The source-owned malformed additive-noise case also passed on both sides as a
nonzero exit with no artifact files. The acceptance does not convert that
rejection into a success and does not treat an in-process cancellation token as
a CLI artifact case.

This supersedes neither the old PB-01/PB-02 matrix nor its historical blockers.
That matrix used an older candidate and includes a SIPI-local CTLE extension
and an invalid 16-bit PRBS7 jitter span. This record accepts only the finite,
source-owned native corpus. AMI, IBIS, GetWave, S2P, vendor models, local
extensions, Web/GUI families, performance, license, product admission and
release remain outside scope.
