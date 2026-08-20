# P4A-02b Authorized Gen5 Behavior-Spec Observation - Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-02 sub-slice 02b (authorized Gen5 behavior-spec observation)
- Status: delivered. Owner decision C1 directs behavior-spec formation at
  the authorized external ADS Gen5 profile. Observer-only; no product
  parser, AMI host, or composed receive chain is implemented.

## Method

Scan the authorized pcie_gen5.ibs for [Algorithmic Model] attachments,
bind the file hash, and cross-reference the DLL/AMI identity and
black-box probe status from the P4B-07 authorized-fixture ABI evidence.

## Result

- pcie_gen5.ibs sha256 9ff15bf9..., 5537 bytes, file_rev 0.1.
- pcie_tx (Output) -> ctspcie_tx_win64.dll + ctspcie_tx_gen5.ami;
  pcie_rx (Input) -> ctspcie_rx_win64.dll + ctspcie_rx_gen5.ami.
- DLL identity authorized_matched_record (P4B-07); TX 4 probes success,
  RX 4 probes crash (RX requires the S4P-derived matrix pipeline, P4B-08).
- Parser / AMI / composition semantics remain out of scope; no product
  runtime is incurred.

## Binding

- Observation docs/baselines/p4a-02b-gen5-behavior-spec-observation.v1.yaml.
- Verifier verify_p4a_02b_gen5_behavior_spec.py + 7 tests.
- PLAN **P4A-02b**; ledger note/gate P4A-02; coverage gates 91 -> 92.
