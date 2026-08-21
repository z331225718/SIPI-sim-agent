# P3 Original-Project Eye/Jitter Semantics Observation

## Scope

This is a read-only, hash-bound observation of the pinned PyBERT and
Agent-COM source objects. It does not copy source code or admit an original
project algorithm into SIPI.

PyBERT is pinned to commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`. The observed functions are
`find_crossing_times`, `find_crossings`, and `calc_jitter` in
`src/pybert/utility/jitter.py`, the statistical-eye phase/bin path in
`src/pybert/utility/statistical_eye.py`, and the native jitter implementation
in `native/pybert-core/src/jitter.rs`.

Agent-COM is pinned to commit `034b21b2f293b2ef97cb8be269b1bf2be38e0086`,
tree `dc6e5529612d7272f23547a796b53e1456cc49cb`. The observed eye surface is
`center_of_ui`, `eye_cdf`, `ber_contour`, and `find_eye_width` in
`src/agent_com/metrics/eye.py`; the equalizer entry surface is
`src/agent_com/equalization/apply.py`. The pinned Agent-COM commit has no
tracked `LICENSE` object. These are material observations, not legal
conclusions.

## Why no product slice is admitted

The source projects expose materially different semantic surfaces: PyBERT's
jitter path expects pre-aligned ideal/actual crossing streams and combines
pattern grouping, histogram bins, smoothing, spectral classification, and
dual-Dirac diagnostics. Agent-COM's eye path takes a two-column contour,
chooses a nearest half-UI center, and interpolates contour crossings while
rejecting flat crossings. Neither source observation selects SIPI's required
profile, receiver stage, observables, bins, tolerance, or reference binding.

The P3C-02 decision surface still explicitly marks eye folding/bins and the
bathtub estimator as pending owner decision. P3B-05 still lacks the required
jitter observable and tolerance. The equalizer subset lacks a selected Link
profile and independent stage semantics. Implementing any of these from the
source facts would invent product semantics.

## Strict mismatch evidence

The existing same-index observation remains bound at full-chain NRMSE
`0.02911956313297956` against the fixed `0.01` limit, while its source-only
interior projection is exactly `0.0`. The latter is only an independent
source-boundary observation; it does not localize or explain the full-chain
mismatch. No alignment, gain/DC,
polarity, tolerance relaxation, parameter scan, or oracle fitting was used.

The machine gate is
`tools/verify_p3_original_project_eye_jitter_semantics_observation.py` and
the complete source facts are recorded in
`docs/baselines/p3-original-project-eye-jitter-semantics-observation.v1.yaml`.
