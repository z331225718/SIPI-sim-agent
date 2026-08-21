# P3C Exact Impulse Current Replay Preparation v1

This is a preparation contract for T08. It binds the exact selected S4P, the
immutable ADS canonical triple payload, the current finite-edge PRBS9 v2
candidate, and the product source tree to one clean Git archive. It does not
run ADS and it does not create or retain candidate or reference bytes.

## External Inputs

T08 supplies three paths outside the repository: the exact selected
`channel_gen5_highloss.s4p`, the exact little-endian binary64 ADS triple
payload, and a release `sipi` executable. The S4P and ADS payload must match
the byte lengths and SHA-256 values in the YAML contract. The executable hash
is recorded in the hash-only report; its bytes are never copied into the
repository.

The observer materializes commit `805ebb6bbaf588dec08685be4eb78a8ce2fff563`
with `git archive` and checks the expected tree. It invokes only the existing
ignored Rust test
`p3c_external_ads_selected_highloss_waveform_only_runner_v2` with
`--locked --offline`. The child runner reads the ADS payload as a reference,
seals and admits the exact S4P, and removes its temporary roots before it
returns.

## Fixed Impulse Route

The only product route is sealed S4P admission v2, IEEE BSD interpolation,
the raw-periodic inverse transform internal to bounded causality, bounded
causality, fixed truncation, and the current PRBS9 v2 direct full-linear
convolution. S-parameter rational fitting is prohibited. The finite-edge
source is fixed: sample zero is the first symbol, phase zero at later UI
boundaries is the prior symbol, and phases 1 through 31 are the current
symbol. No caller projection mode exists.

Comparison is strict index only on the third PRBS period `[32704,49056)`.
Alignment, delay or output-strobe search, resampling, gain fitting, DC
removal, polarity changes, and parameter sweeps over NRMSE, causality,
passivity, or truncation are prohibited. The report may contain only hashes,
counts, IEEE-754 bit patterns, and stage-qualified rejection facts.

## Two-Fresh Custody And Boundary

The ignored Rust runner creates two independent S4P and metric artifact roots
per fresh replay, uses new artifact IDs, checks source identity before staging
and after sealing, checks the reference before and after reading, and requires
distinct manifest digests with equal canonical facts. Any source/reference
drift or cleanup failure rejects the replay. The observer rejects a report
inside the worktree and deletes its temporary clean archive and child report
before success.

A strict-index mismatch is reported as
`prepared_observed_not_accepted` at the
`strict_index_waveform_only_compare_v3` stage. It is not current evidence and
cannot promote the candidate, receiver, AMI/P4B, P5, or release ledger.
