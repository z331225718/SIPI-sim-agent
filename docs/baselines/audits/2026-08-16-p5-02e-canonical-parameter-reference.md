# P5-02e Canonical Parameter Key Reference — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-02 sub-slice 02e (canonical R480 parameter key reference)
- Status: delivered and mechanically bound; defaults/warning contract
  still pending MATLAB oracle execution

## Method

External-only observation of the owner-authorized MATLAB r4.80 source
`COM/matlab_src/com_ieee8023_480.m` (SHA-256
642b28910a6fccca4682aa0a66a6a6c00633a14c17d05d8d6ee73d2808954cad, per the
authorized-material-registry): every `xls_parameter(parameter, 'KEY', ...)`
call site is recorded with its call-line original (default expressions
kept verbatim). The generator is external observation tooling, not
product code; nothing is copied into the product tree.

## Result

- 214 canonical parameter keys, 229 xls_parameter calls.
- Reference `docs/baselines/p5-r480-canonical-parameter-reference.v1.yaml`
  hash-bound to the source; the COM repository's own
  r480-config-inventory.json claims a different source hash
  (88db14d7...) and was NOT modified.

## Scope discipline

Default expressions are recorded verbatim, not evaluated; no warning
contract, no product contract, no compute parity, no release evidence.
Expression resolution requires the MATLAB oracle (P5-02 next slice).

## Binding

- Verifier `verify_p5_02e_canonical_parameter_reference.py` + 5 tests;
- PLAN **P5-02e**; ledger note/gate; coverage gates 76 -> 77.
