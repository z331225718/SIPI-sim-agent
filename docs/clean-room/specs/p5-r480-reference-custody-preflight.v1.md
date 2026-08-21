# P5 T13 R4.80 Reference Custody Preflight v1

## Purpose

This record is a longitudinal, replayability-only preflight for the selected
`com-r480-envelope-v1` profile. It binds the exact external Git source and
runner objects, the authorized material-record identities, MATLAB runner
identity/isolation observations, canonical input/default and warning surfaces,
intermediate checkpoint and metric digests, tolerances, and all recorded
artifact/report hashes. It does not implement COM, run a product, execute
MATLAB, open an external workbook/fixture, or compare product output.

The machine-readable baseline is
`docs/baselines/p5-r480-reference-custody-preflight.v1.yaml`; the fail-closed
verifier is `tools/verify_p5_r480_reference_custody_preflight.py`.

## Custody Boundary

- The only oracle authority is an authorized external MATLAB R4.80 run. The
  MATLAB source, workbook, S4P fixtures, runner, runtime, and output files
  remain outside the product and outside this repository.
- The verifier reads only repository evidence records and their hashes. A
  recorded external path is metadata, not permission to open that path.
- The capability envelope and `tools/run_matlab_oracle.py` objects are bound to
  `agent-com` commit `5272ffe74702cd585054d975559b06f8afae7b6e`, tree
  `7094ab6e84989b218730c52432c70da10261f8ea`, with their exact Git blob and
  content SHA-256 identities.
- The authorized material registry contains a second external copy of the
  capability envelope (`40f802...`, 9985 bytes), while the bound Git object is
  `9b3329...`, 9636 bytes. This identity conflict is recorded, not silently
  reconciled.
- Product Rust and product Python self-crosschecks are implementation smoke
  evidence only and are explicitly disqualified as oracle evidence.

## Observed Surfaces

The existing records provide the following hash-bound observations:

- MATLAB built-in probe identity is R2024b / `24.2.0.2712019 (R2024b)` on
  `PCWIN64`; startup isolation is unproven and the license observation is
  unknown. The static oracle invocation surface remains unauthorized and
  uninvoked.
- The canonical source inventory has 214 parameter keys and 229 calls. The
  v2 default inventory has 3 statically evaluated calls and 20 calls requiring
  oracle-dependent resolution. The normalized input surface records 214
  canonical keys, 82 config keys, and port order `[ 1 3 2 4 ]`, but no complete
  normalized-input digest.
- The source warning inventory has 25 warning calls. No warning report for the
  exact authoritative run or complete product warning contract is recorded.
- The first-run summary has two cases, six checkpoint keys, 14 output metric
  keys, and hash-bound per-case checkpoint/metric digests. The C4 reference
  binds `COM_dB`, `ICN_mV`, and `ERL` with a 1% relative policy, but the
  acceptance contract requires `com_db`, `erl_db`, and `td_iln_db`; this is not
  a full COM metric bundle.
- `matlab_oracle.mat`, `summary.json`, stdout-tail, MATLAB probe report, and
  invocation-surface report hashes are recorded. The MAT payload is not
  available in replayable custody, and the first-run materialization was
  cleaned, so hashes alone cannot feed a full array/checkpoint comparison.

## T14 Admission

T14 full compare matrix admission is **false**. The exact blockers are listed
in the baseline and are intentionally fail-closed:

1. capability-envelope registry copy mismatch;
2. MATLAB startup isolation unproven;
3. oracle invocation authorization missing;
4. replayable external custody manifest missing;
5. normalized-input digest missing;
6. caller-dependent defaults unresolved;
7. exact-run warning report missing;
8. checkpoint tolerances missing;
9. acceptance metric scope incomplete;
10. full metric tolerance/alignment policy missing;
11. reference artifact payload missing; and
12. product self-crosschecks cannot serve as the oracle.

No unauthorized MATLAB rerun or unauthorized external-asset read is permitted
to close these blockers. T14 may begin only after an authorized external
replay supplies the missing custody, semantics, payload, and tolerance records,
then a successor baseline binds those additive artifacts without rewriting this
historical preflight.
