# P5-06a MATLAB Oracle First Run — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-06 sub-slice 06a (MATLAB oracle first run)
- Status: delivered and mechanically bound; required COM compare matrix
  pending

## Method

Fresh custody materialization of the authorized MATLAB r4.80 source
(com_ieee8023_480.m) and the synthetic thru/fext/next fixtures
(hash-verified copies); config sheet used from its original registered
path after xlsread basic was found unable to read Temp-directory xlsx
copies (hash verified before use). MATLAB R2024b invoked directly with
the agent-com run_com_oracle entry (external tool),
COM_ORACLE_SOURCE_DIR pointed at the custody copy; 26.56 GHz, 120g C2M
TP1a, thru+fext+next.

## Result

- First run succeeded (~11 min): outputs matlab_oracle.mat and
  summary.json, hash-bound; stdout tail hash recorded.
- stdout included FOM/TXFFE/SNR/CTLE results and the anti-causal warning
  consistent with the P5-02i warning observation.
- All outputs stayed in external custody (fresh root cleaned after).

## Debugging fixed during the run

- agent-com run_matlab_oracle.py requires its instrumented-source
  manifest (internal mechanism); the direct run_com_oracle entry was
  used instead.
- matlab.exe is a launcher: copying it to custody breaks startup (rc=2);
  the install-path executable is used (materials stay hash-pinned).
- xlsread basic cannot read Temp-directory xlsx copies; config used from
  its registered original path.

## Binding

- Evidence `p5-06-matlab-oracle-first-run-evidence.v1.yaml`;
- Verifier `verify_p5_06a_matlab_oracle_first_run.py` + 4 tests;
- PLAN **P5-06a**; ledger note/gate; coverage gates 83 -> 84.

## Non-claims

not_a_product_runtime; not_compute_parity; not_release_evidence.
