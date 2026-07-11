# MFT-NNLS Reference Fixtures

`ex4_s_small.npz` is a compact, checked-in contract fixture derived from the complete supplied MFT-NNLS `ex4_S.mat` example. It stores source response samples, deterministic model-contract arrays, and the SHA-256 values of the MATLAB source data and key toolbox entry points.

The fixture contains two Task 4a parity classes. Raw-start `ex4_S` relocation cases are diagnostics: MATLAB's own fixed-pole response RMS remains above `0.01` through order 13, so those cases cannot prove response-quality equivalence. Orders 4 and 6 retain strict pole checks and the other raw-start cases are strict expected-failure diagnostics. The `medium_*` fields are a deterministic, symmetric, well-conditioned order-six rational matrix generated and solved by MATLAB `vectfit4`; its MATLAB fixed-pole RMS is below `0.01` and it is the strict relocation-pole and fitted-response parity gate.

`VFdriver.m` documents `SER.R` as `(Nc, Nc, N)`, matching `PoleResidueModel.residues`; the generator intentionally does not permute it. It does permute `bigS` and `bigSfit` from MATLAB `(Nc, Nc, Ns)` to Python `(Ns, Nc, Nc)`. Task 4a must assert both conventions when loading a regenerated fixture.

## Regeneration

Run `generate_reference.m` in MATLAB R2024b or later with the MFT-NNLS toolbox on the MATLAB path. It writes `ex4_s_reference.mat` with `version` plus hashes of `ex4_S.mat`, `VFdriver.m`, and `vectfit4.m`. Then run `python convert_reference.py ex4_s_reference.mat ex4_s_small.npz`. This two-step path avoids a MATLAB-to-Python ABI dependency. Any source hash change requires a fixture review and an update to the tolerance rationale in the design specification.

The private source toolbox is never copied into this repository.
