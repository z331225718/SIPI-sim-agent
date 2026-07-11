"""Convert the MATLAB homogeneous QR-NNLS artifact to an NPZ fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    reference = loadmat(args.source, simplify_cells=True)
    np.savez_compressed(
        args.output,
        constraint_matrix=np.asarray(reference["constraint_matrix"], dtype=float),
        constraint_rhs=np.asarray(reference["constraint_rhs"], dtype=float).reshape(-1),
        dual_variables=np.asarray(reference["dual_variables"], dtype=float).reshape(-1),
        residual=np.asarray(reference["homogeneous_residual"], dtype=float).reshape(-1),
        xbar=np.asarray(reference["xbar"], dtype=float).reshape(-1),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
