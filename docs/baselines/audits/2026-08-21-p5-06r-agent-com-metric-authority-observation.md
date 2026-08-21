# P5-06r Agent-COM metric authority observation

This is an additive, external-only source and run observation. It does not
rewrite the earlier matched-THRU record and does not promote a product or
oracle acceptance claim.

## Source and canonical tuple

The source is the pinned Agent-COM commit `5272ffe74702cd585054d975559b06f8afae7b6e`
with tree `7094ab6e84989b218730c52432c70da10261f8ea`. The profile is the
existing `r480` profile. The selected workbook is the tracked
`matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx`
(`e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925`). The
selected THRU is the tracked reflective fixture
`fixtures/synthetic/erl_reflective_10db_at_26p56ghz.s4p`
(`72327f8d36cd7c51aaf64d803ac6e86b557d017fe574d7b2b05d4583e9494126`). Both
paths and the profile are already named by the source repository's F22/F05
tests and synthetic fixture documentation. No parameter or result sweep was
performed.

## Fresh external runs

Two clean-archive Agent-COM processes used `load_config(...,
overrides={'COMPUTE_TDILN': 1})` followed by `run_com(...,
RunOptions(BehaviorProfile.r480(), diagnostics=False))`. The retained payload
is a canonical JSON scalar projection only. Each projection is 398 bytes with
SHA-256
`7f62d3ed65649e3a2eed0d3f2cb6fa1891c586361dd9cb559378445ab64862e5`;
the runs were byte-identical.

The two cases were:

- case 0: `COM_dB=6.6804682852917585`, `ERL=36.59476569210085`,
  `ERL11=38.131566296755295`, `ERL22=36.59476569210085`,
  `FOM_TDILN=22.366448964047528`;
- case 1: `COM_dB=6.851887606480109`, with the same finite ERL and
  `FOM_TDILN` values.

Neither case emitted `TD_ILN` or `TD_ILN_dB` in the public scalar metrics.
`ICN_mV=0.0` was observed but is unrelated to TD-ILN.

## Authority and gap

The pinned MATLAB source publishes `FOM_TDILN` and a `TD_ILN` struct, while
the Agent-COM public metrics map publishes only `FOM_TDILN`; the typed
`TdIlnResult` contains arrays and SNR/FOM fields, not a scalar named
`TD_ILN_dB`. The required three-metric bundle therefore remains incomplete.
The existing typed P3C-03 compare is suitable for a later external compare,
but it must receive a finite scalar TD-ILN value at the same checkpoint and
the exact normalized input/case binding. No alignment, tolerance invention,
or field alias closes this gap.

The observation does not invoke MATLAB, does not invoke SIPI product code,
does not compare product against Agent-COM, and does not alter release or
publication state.
