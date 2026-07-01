from __future__ import annotations

from pathlib import Path

import skrf as rf
from skrf.vectorFitting import VectorFitting


def fit_touchstone_to_spice(touchstone_path: Path, output_path: Path) -> Path:
    network = rf.Network(str(touchstone_path))
    vector_fit = VectorFitting(network)
    vector_fit.auto_fit()
    vector_fit.passivity_enforce()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vector_fit.write_spice_subcircuit_s(str(output_path))
    return output_path
