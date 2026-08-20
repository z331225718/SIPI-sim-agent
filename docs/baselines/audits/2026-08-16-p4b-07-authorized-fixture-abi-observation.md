# P4B-07a Authorized Fixture ABI Observation — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-07 sub-slice 07a (authorized fixture raw ABI observation)
- Status: delivered and mechanically bound; P4B-07 main item stays open
  (raw ABI output compare matrix pending)

## Owner authorization

The owner directed (2026-08-16): materials are in the code folder. The
authorized-material-registry.v1.yaml registers 14 materials; the TX/RX
PCIe Gen5 DLLs match the previously observed hashes
(05d299826a9c69ae8ac3d236d88adcad5860fc7e229243f1541d1734b8ed28ea /
88a284f0967ad332f6230a8c5e791f47e9d22a05ae6778426c35707a18a3ab63).

## Observation (two fresh custodies, fixed probe surface)

- Runner `crates/sipi-ami-host/tests/p4b_authorized_fixture_abi_runner.rs`
  (harness=false) loads the hash-pinned DLL through the clean-room host
  with the caller .ami parameter text and runs the fixed matrix:
  init-only, single-1024, single-4096, multi-1024 (4x4 identity-like
  matrix, 1 ps sample interval, 31.25 ps bit time, alternating +/-1
  waveform, -1.0 clock sentinel).
- Orchestrator `tools/run_p4b_07_abi_observation.py` materializes each
  DLL twice into fresh temp roots, verifies hashes, runs all probes,
  compares hash-only reports byte-for-byte, writes evidence, and cleans
  up.
- Result: TX all four probes succeed and reproduce byte-exactly; RX
  AMI_Init crashes reproducibly (0xC0000005 access violation) on every
  probe of the fixed surface. The crash is recorded as an observation,
  not a claim about DLL internals.

## Binding

- Charter `p4b-07-authorized-fixture-abi-observation.v1.yaml`;
- Evidence `p4b-07-authorized-fixture-abi-observation-evidence.v1.yaml`
  (hash-only; raw waveforms/clocks never stored);
- Verifier `verify_p4b_07_authorized_fixture_abi_observation.py`
  cross-binds charter, evidence, registry hashes and the PLAN row;
- Tests: 5 (valid observation, TX success / RX crash statuses, registry
  hashes, PLAN row, probe-input drift rejection).
- PLAN **P4B-07a**; ledger note/gate; coverage gates 73 → 74.

## Non-claims

not_numerical_parity; not_ibis_ami_compatibility; not_tx_rx_composition;
not_worker_admission; not_product_runtime; not_rx_init_stability;
not_release_evidence.
