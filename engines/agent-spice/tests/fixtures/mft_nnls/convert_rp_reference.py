"""Convert a MATLAB RP_QRNNLS one-step artifact to NPZ."""

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
        s=np.asarray(reference["s"]).reshape(-1),
        s_residue=np.asarray(reference["out_s"]["R"]).reshape(()),
        s_constant=np.asarray(reference["out_s"]["D"]).reshape(()),
        s2_residues=np.asarray(reference["out_s2"]["R"]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
