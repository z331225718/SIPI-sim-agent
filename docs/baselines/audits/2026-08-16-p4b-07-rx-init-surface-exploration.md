# P4B-07c RX AMI_Init Probe-Surface Exploration — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-07 sub-slice 07c (RX AMI_Init probe-surface exploration)
- Status: delivered and mechanically bound; RX init remains blocked on the
  documented call surface

## Method

The RX fixture's AMI_Init crashed on the 07a identity-like matrix. To
separate input-content sensitivity from a hard call-surface failure, four
documented matrix variants were observed (4x4, 1 ps / 31.25 ps):
identity_like (diagonal impulse), decay (2^-row victim column), uniform
(all 1.0), decay_coupled (victim decay + 0.1 coupling). Each variant ran
twice in independent fresh custodies through the hash-pinned clean-room
host.

## Result

All four variants crash identically and reproducibly (0xC0000005 access
violation, both custodies each). The crash is independent of matrix
content, indicating a hard failure of the RX AMI_Init call surface under
this host/ABI convention. This is an observation, not a claim about DLL
internals (non_claim: not_dll_internal_cause).

## Consequence

- TX surface remains the P4B-07 completed surface (07a observation + 07b
  parity: init / single / multi GetWave at legal lengths, hash-equal
  across host and independent observer).
- RX GetWave parity cannot be exercised while AMI_Init fails; a
  S4P-derived channel matrix call surface would belong to P4B-08 (typed
  edge to Channel), not to P4B-07.
- P4B-07 main item stays open pending that surface decision.

## Binding

- Evidence `p4b-07-rx-init-surface-exploration-evidence.v1.yaml`;
- Verifier `verify_p4b_07_rx_init_surface_exploration.py` + 4 tests;
- PLAN **P4B-07c**; ledger note/gate; coverage gates 75 -> 76.

## Non-claims

not_dll_internal_cause; not_ibis_ami_compatibility;
not_numerical_parity; not_worker_admission; not_release_evidence.
