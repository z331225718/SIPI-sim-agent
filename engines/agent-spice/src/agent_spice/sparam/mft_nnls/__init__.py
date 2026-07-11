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

__all__ = [
    "MFTConfig",
    "MFTDiagnostics",
    "MFTResult",
    "PoleResidueModel",
    "canonicalize_poles",
    "build_weights",
    "evaluate",
    "initialize_poles",
    "reconstruct_symmetric_residues",
    "stabilize_poles",
]
