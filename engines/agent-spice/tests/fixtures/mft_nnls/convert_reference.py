"""Convert the MATLAB reference artifact into the checked-in NumPy fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.io import loadmat


def _scalar(value: object) -> str:
    return str(np.asarray(value).squeeze().item())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = loadmat(args.source, simplify_cells=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        fixture_kind=np.array("matlab_vfdriver_reference"),
        s=np.asarray(source["s"]).reshape(-1),
        response=np.asarray(source["response"]),
        fitted_response=np.asarray(source["fitted_response"]),
        poles=np.asarray(source["poles"]).reshape(-1),
        residues=np.asarray(source["residues"]),
        constant=np.asarray(source["constant"]),
        proportional=np.asarray(source["proportional"]),
        weightparam=np.asarray(source["weightparam"]).reshape(()),
        matlab_version=np.array(_scalar(source["matlab_version"])),
        source_sha256=np.array(_scalar(source["source_sha256"])),
        vfdriver_sha256=np.array(_scalar(source["vfdriver_sha256"])),
        vectfit4_sha256=np.array(_scalar(source["vectfit4_sha256"])),
        relocation_response=np.asarray(source["relocation_response"]),
        relocation_weight=np.asarray(source["relocation_weight"]).reshape(-1),
        relocation_initial_poles=np.asarray(source["relocation_initial_poles"]).reshape(-1),
        relocation_poles=np.asarray(source["relocation_poles"]).reshape(-1),
        medium_frequencies_hz=np.asarray(source["medium_frequencies_hz"]).reshape(-1),
        medium_response=np.moveaxis(np.asarray(source["medium_response"]), -1, 0),
        medium_initial_poles=np.asarray(source["medium_initial_poles"]).reshape(-1),
        medium_relocated_poles=np.asarray(source["medium_relocated_poles"]).reshape(-1),
        medium_fitted_response=np.moveaxis(np.asarray(source["medium_fitted_response"]), -1, 0),
        medium_rms=np.asarray(source["medium_rms"]).reshape(()),
        passivity_sweep_frequencies_hz=np.asarray(source["passivity_sweep_frequencies_hz"]).reshape(-1),
        passivity_s_bands_hz=np.asarray(source["passivity_s_bands_hz"]),
        passivity_y_bands_hz=np.asarray(source["passivity_y_bands_hz"]),
        **{
            f"relocation_initial_poles_{order}": np.asarray(source["relocation_cases"][f"order_{order}"]["initial_poles"]).reshape(-1)
            for order in (4, 5, 6, 7, 9, 13)
        },
        **{
            f"relocation_poles_{order}": np.asarray(source["relocation_cases"][f"order_{order}"]["poles"]).reshape(-1)
            for order in (4, 5, 6, 7, 9, 13)
        },
        **{
            f"relocation_rms_{order}": np.asarray(source["relocation_cases"][f"order_{order}"]["rms"]).reshape(())
            for order in (4, 5, 6, 7, 9, 13)
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
