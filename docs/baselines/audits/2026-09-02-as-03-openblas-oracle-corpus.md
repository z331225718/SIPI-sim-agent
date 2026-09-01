# AS-03 OpenBLAS/NumPy Oracle Corpus Audit

Date: 2026-09-02
Status: diagnostic-only; numeric parity remains open

## Purpose

This audit adds a read-only numerical corpus for the AS-03 S-to-Y conversion
boundary. It does not change the Rust solver, CLI, PLAN, ledger, product
boundary, or any release claim. The Rust side is an appended private test in a
temporary immutable candidate archive; the residue least-squares fit is
intentionally not executed.

## Reproducible run

The runner was executed from the current candidate commit with the pinned
Agent-Spice checkout and the local Python 3.12 environment:

python tools/probe_as03_openblas_oracle.py --candidate-commit HEAD --cargo <cargo> --rustc <rustc> --python <agent-spice-venv-python> --report docs/baselines/as-03-openblas-oracle-corpus-v2.json

The report is a create-new JSON record. Its SHA-256 is
efff964bb1058a58da53cde5a521ce4071a4f3290e3020136b3ad5505ec7c14a and its
size is 1,461,848 bytes.

Candidate custody:
- commit: d5e87f2ac3af1a584e2bc024bf98a4d58699d3b8
- tree: 2a03d27b6f80b9ac802b09a6b08661617232be51
- source: crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs
- instrumentation: append-only private test in the temporary archive; the
  production source is unchanged

The pinned upstream is Agent-Spice commit
2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5, tree
b6bde97128030d6cea0d68b2f0a35d807be8c402. The report binds the upstream
yparam.py and native_vf.py Git objects.

## Corpus

There are 21 deterministic cases, three per dimension:
N = 1, 2, 3, 4, 8, 16, 32.

The categories are:
- well_conditioned: complex, diagonally dominant matrices
- pivot: complex matrices with a deliberately small first pivot and a
  larger lower-column entry
- near_singular: bounded condition numbers below the product's 1e12
  conversion gate

The canonical input corpus SHA-256 is
970eb4cef460a8d774dfd0ff6accc26de7b915bf528bcb877043a6a1488308dd.
All matrix values, input bits, Python oracle bits, and candidate bits are
embedded in the JSON report.

The Python oracle evaluates the same power-wave construction as the current
Rust boundary:
A = (S @ G + conj(G)) @ F, B = (I - S) @ F, then
numpy.linalg.solve(A, B), with z0 = 50 ohm and a 1e12 condition limit.
BLAS-related threads were explicitly set to one for the probe.

## Runtime facts

The actual environment reported:
- Python 3.12.13
- NumPy 2.5.1
- SciPy 1.18.0
- scikit-rf 2.0.1
- NumPy _umath_linalg.cp312-win_amd64.pyd: 112,128 bytes,
  SHA-256 99b8aabee0f2b5bb857cb2f15046680a40ed12cd39599a075cd0ae0d17dc1dc5
- OpenBLAS 0.3.33.112.0, DYNAMIC_ARCH, NO_AFFINITY, Haswell,
  MAX_THREADS=24
- NumPy OpenBLAS DLL SHA-256
  b788215d9d47792bcba3a2e2a71143205a57282828a483f1fb071ca2c159f616
- SciPy OpenBLAS DLL SHA-256
  197ee2fc9b4d071f7e048078cac741151a6585d871061cf5f88c0c73e31963a5
- NumPy SIMD dispatch: baseline X86_V2, found X86_V3

The installed scikit-rf network.py and mathFunctions.py bytes match the
pinned source-map leaves exactly. A standalone scikit-rf Git checkout was not
found, so the report records that custody limitation explicitly.

## Observed result

The candidate Rust private probe and the Python oracle both completed
successfully. Only 2 of 21 cases were bit-exact. Of 8,244 scalar f64
components, 1,302 were bit-exact; the maximum observed distance was 17,233
ULPs. The first difference was in n01-near_singular, real element (0,0),
at one ULP (candidate=3846153.784664743,
oracle=3846153.7846647426). The per-case results and complete bits are in the
report; no tolerance-based acceptance was introduced.

## Blockers and limits

The record remains diagnostic_only_numeric_parity_open with
numeric_parity=false:
- the corpus exercises S-to-Y dense solving, not the residue least-squares
  solver used by fit-yparam
- cross-runtime S-to-Y bits differ across the N/pivot/near-singular matrix
  family
- the pinned scikit-rf Git checkout is absent, although the two source leaves
  match the pinned source-map bytes and hashes

This is evidence for narrowing the AS-03 numerical investigation, not a solver
replacement, global parity result, acceptance tolerance, or release signoff.
