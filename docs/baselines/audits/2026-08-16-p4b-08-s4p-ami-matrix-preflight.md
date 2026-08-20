# P4B-08b S4P-to-AMI Matrix Decision-Surface Preflight — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-08 sub-slice 08b (S4P-to-AMI_Init matrix decision surface)
- Status: delivered and mechanically bound; matrix construction
  prohibited until port mapping is established

## Why a preflight

AMI_Init's channel matrix needs victim/aggressor column semantics and
the S4P port order. The IBIS file fixes the serdes pin names (1=Tx,
2=Tx#, 3=Rx, 4=Rx#) and differential pairs (1-2, 3-4), but the S4P port
order and the mapping of ports to matrix columns require the ADS
netlist, which is not part of the authorized material set. Constructing
a matrix from the S4P alone would guess those semantics; this preflight
prohibits that (fail-closed) until the mapping is established.

## Binding

- Charter `p4b-08-s4p-ami-matrix-preflight.v1.yaml`;
- Verifier `verify_p4b_08b_s4p_ami_matrix_preflight.py` + 5 tests;
- PLAN **P4B-08b**; ledger note/gate; coverage gates 82 -> 83.

## Non-claims

not_a_port_mapping; not_victim_aggressor_semantics;
not_impulse_conversion; not_ami_matrix; not_system_parity;
not_release_evidence.
