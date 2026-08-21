# P5-06k Required COM Compare Contract Gap Audit

## Result

This additive record extracts the required COM compare contract gap from the
canonical Agent-COM commit `5272ffe74702cd585054d975559b06f8afae7b6e` and
existing hash-bound external records. It did not invoke MATLAB, read a new
oracle payload, change Rust, or modify historical evidence. It does not close
P5-06 or promote compare, acceptance, or release.

The machine-readable evidence is
`docs/baselines/p5-06k-required-com-compare-contract-gap.v1.yaml`, verified by
`tools/verify_p5_06k_required_com_compare_contract_gap.py`.

The verifier is document-only by default and reports
`source_git_object_checked=false`. With an optional `--source-root` pointing at
the external COM Git checkout, it uses `git rev-parse` and `git cat-file` to
check the pinned commit/tree, every recorded blob OID, raw content SHA-256, and
byte length; a successful external check reports
`source_git_object_checked=true`.

## What The Canonical Objects Prove

The pinned capability envelope object binds profile rule fingerprints, input
kinds, and channel role sets. The pinned `com_oracle_case_metrics.m` object
defines a stable extracted surface of fourteen scalar output keys and bounded
internal checkpoint groups, retaining `case_index`. The legacy output schema
contains `COM_dB`, `ERL`, and the legacy `TD_ILN`/`FOM_TDILN` names. These are
source and schema facts, not an acceptance policy.

The same source tree's runner checks repeated MATLAB case count/order and uses
`1e-12` for repeated-run scalar metric repeatability. Network checkpoint tests
use `rtol=1e-12` and `atol=1e-14`; an isolated MLSE test uses absolute
`2e-12`. None of those values is a required product-to-oracle tolerance.

## Required Matrix Versus Observed C4

The selected COM acceptance contract requires input identity
`normalized_input_digest`, `channel_role_manifest_digest`, and
`parameter_set_digest`; stage evidence for selected channel, equalizer
selection, and PDF axes/density; and scalar dB metrics `com_db`, `erl_db`, and
`td_iln_db`. Existing records observe `COM_dB`, `ICN_mV`, and `ERL` for the
C4 profile at a 1% relative tolerance. `ICN_mV` is not `TD_ILN`, so this C4
surface cannot satisfy the required COM/ERL/TD-ILN matrix.

The two-case oracle metric surface records six bounded checkpoint names:
`DFE_taps`, `TXLE_taps`, `itick`, `sgm_Ani__isi_xt_noise`, `sigma_N`, and
`tail_RSS`. The four-payload external custody record repeats these observations
and explicitly marks checkpoint tolerance as missing. It does not define array
axes, stage identity, selection provenance, units, or per-checkpoint alignment.

## Remaining Gap

The missing contract is the exact clean compare binding: authorized replayable
input and oracle provenance, case/channel/stage/axis alignment, explicit
`TD_ILN` value mapping, final tolerances for all three required metrics, and
per-checkpoint/stage tolerances. A checkpoint digest, a C4 1% policy, or a
repeatability tolerance cannot substitute for those fields.

## Non-Claims

- No MATLAB invocation or new external asset read was performed.
- No product-vs-oracle comparison, acceptance result, certification, or release
  eligibility is claimed.
- No `ICN_mV` to `td_iln_db` alias, tolerance, or source promotion is selected.
- The current P5-06 blocker remains unresolved; this is an evidence and audit
  leaf only.
