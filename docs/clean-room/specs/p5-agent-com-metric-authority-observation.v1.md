# Agent-COM metric authority observation v1

## Purpose

This observer-only record follows one already named r4.80 profile and one
already tracked reflective synthetic input. It records where Agent-COM and the
pinned r4.80 source generate `COM_dB`, `ERL`, `FOM_TDILN`, and `TD_ILN`, and
whether those fields can supply the required `COM_dB` / `ERL_dB` /
`TD_ILN_dB` bundle.

No parameter sweep, result-based input selection, MATLAB invocation, product
runtime invocation, or `ICN_mV` alias is allowed. The external run is retained
only as a hash-only scalar projection; source and generated payloads remain
outside this repository.

## Canonical tuple

The tuple is fixed by existing Agent-COM material and tests:

- profile: `r480` with the existing `BehaviorProfile.r480()` default;
- workbook: the tracked 120F C2C workbook;
- channel: the tracked `erl_reflective_10db_at_26p56ghz.s4p` THRU fixture;
- one explicit source-schema override: `COMPUTE_TDILN=1`.

The reflective fixture is used because the existing matched THRU observation
returns `ERL=Infinity`; changing only to this already tracked reflective
fixture is not a search over channel parameters. The tuple is an observation
selection, not a claim that every historical Agent-COM profile is equivalent.

## Authority map

The pinned MATLAB source initializes `output_args.FOM_TDILN` and
`output_args.TD_ILN` as empty, computes a `TD_ILN` struct in
`get_ILN_cmp_td`, and publishes `FOM_TDILN=TD_ILN.SNR_ISI_FOM_PDF` plus the
`TD_ILN` struct when `COMPUTE_TDILN` is enabled. The legacy schema therefore
identifies `TD_ILN` as a struct field, not as a scalar dB field.

Agent-COM's typed `TdIlnResult` retains the ILN arrays, PDF, phase, and two
SNR/FOM scalars. Its public case metrics add only `FOM_TDILN`; its diagnostics
may retain the typed TD-ILN object. No public `TD_ILN` or `TD_ILN_dB` scalar is
generated. ERL is a separate TDR/PTDR result and remains finite only when the
input has nonzero reflection.

## Decision boundary

The two fresh runs produce finite `COM_dB`, finite `ERL`, and finite
`FOM_TDILN`, but still no required scalar `TD_ILN_dB`. Consequently P3C-03
can move from semantics to external comparison only conditionally: the typed
same-checkpoint compare is already present, but admission remains blocked
until an authoritative TD-ILN scalar, exact input/checkpoint identity, and
per-metric acceptance policy are bound. `FOM_TDILN`, an ILN vector, and
`ICN_mV` remain distinct fields.
