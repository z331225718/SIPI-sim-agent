"""MFT-NNLS model contracts and MATLAB-parity helpers."""

from agent_spice.sparam.mft_nnls.model import (
    canonicalize_poles,
    evaluate,
    reconstruct_symmetric_residues,
    stabilize_poles,
)
from agent_spice.sparam.mft_nnls.types import MFTConfig, MFTDiagnostics, MFTResult, PoleResidueModel
from agent_spice.sparam.mft_nnls.poles import initialize_poles
from agent_spice.sparam.mft_nnls.weights import build_weights
from agent_spice.sparam.mft_nnls.vector_fit import fit_matrix
from agent_spice.sparam.mft_nnls.passivity import (
    PassivityAssessment,
    ViolationBand,
    ViolationExtremum,
    assess_s_passivity,
    assess_y_passivity,
    select_violation_extrema,
)

__all__ = [
    "MFTConfig",
    "MFTDiagnostics",
    "MFTResult",
    "PoleResidueModel",
    "canonicalize_poles",
    "build_weights",
    "evaluate",
    "fit_matrix",
    "assess_s_passivity",
    "assess_y_passivity",
    "PassivityAssessment",
    "ViolationBand",
    "ViolationExtremum",
    "select_violation_extrema",
    "initialize_poles",
    "reconstruct_symmetric_residues",
    "stabilize_poles",
]
