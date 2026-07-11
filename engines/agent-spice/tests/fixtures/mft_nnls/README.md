# MFT-NNLS Reference Fixtures

`ex4_s_small.npz` is a compact, checked-in contract fixture derived from the first eight frequency samples of the supplied MFT-NNLS `ex4_S.mat` example. It stores source response samples, deterministic model-contract arrays, and the SHA-256 values of the MATLAB source data and key toolbox entry points.

The fixture is not a substitute for vector-fitting parity. Task 4a adds the MATLAB `VFdriver` relocation outputs and validates them against the tolerances in the MFT-NNLS design specification.

`VFdriver.m` documents `SER.R` as `(Nc, Nc, N)`, matching `PoleResidueModel.residues`; the generator intentionally does not permute it. It does permute `bigS` and `bigSfit` from MATLAB `(Nc, Nc, Ns)` to Python `(Ns, Nc, Nc)`. Task 4a must assert both conventions when loading a regenerated fixture.

## Regeneration

Run `generate_reference.m` in MATLAB R2024b or later with the MFT-NNLS toolbox on the MATLAB path and Python configured for NumPy. The script records `version`, hashes `ex4_S.mat`, `VFdriver.m`, and `vectfit4.m`, then overwrites the NPZ fixture. Any source hash change requires a fixture review and an update to the tolerance rationale in the design specification.

The private source toolbox is never copied into this repository.
