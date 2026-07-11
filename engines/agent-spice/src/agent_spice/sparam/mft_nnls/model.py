"""Small, deterministic pole-residue model operations."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from agent_spice.sparam.mft_nnls.types import PoleResidueModel


def stabilize_poles(poles: NDArray[np.complex128]) -> NDArray[np.complex128]:
    """Reflect right-half-plane poles into the closed left half plane."""

    values = np.asarray(poles, dtype=complex).reshape(-1).copy()
    values.real = -np.abs(values.real)
    return values


def canonicalize_poles(poles: NDArray[np.complex128], *, atol: float = 1.0e-12) -> NDArray[np.complex128]:
    """Return stable real poles followed by stable upper/lower conjugate pairs."""

    values = stabilize_poles(poles)
    real_poles = sorted((complex(value.real, 0.0) for value in values if abs(value.imag) <= atol), key=lambda value: value.real)
    upper = sorted(
        (complex(value.real, abs(value.imag)) for value in values if value.imag > atol),
        key=lambda value: (value.imag, value.real),
    )
    for lower in (value for value in values if value.imag < -atol):
        paired = any(
            np.isclose(candidate.real, lower.real, rtol=0.0, atol=atol)
            and np.isclose(candidate.imag, -lower.imag, rtol=0.0, atol=atol)
            for candidate in upper
        )
        if not paired:
            raise ValueError(f"unpaired lower-half-plane pole: {lower}")
    pairs = [pole for value in upper for pole in (value, value.conjugate())]
    return np.asarray([*real_poles, *pairs], dtype=complex)


def reconstruct_symmetric_residues(residues: NDArray[np.complex128]) -> NDArray[np.complex128]:
    """Symmetrize every residue matrix across its two port axes."""

    values = np.asarray(residues, dtype=complex)
    if values.ndim != 3 or values.shape[0] != values.shape[1]:
        raise ValueError("residues must have shape (ports, ports, poles)")
    return 0.5 * (values + np.swapaxes(values, 0, 1))


def evaluate(model: PoleResidueModel, s: NDArray[np.complex128]) -> NDArray[np.complex128]:
    """Evaluate `D + sE + sum(R_k / (s - a_k))` as `(frequencies, ports, ports)`."""

    points = np.asarray(s, dtype=complex).reshape(-1)
    if not np.isfinite(points).all():
        raise ValueError("s must contain only finite values")
    denominator = points[:, None] - model.poles[None, :]
    if np.any(denominator == 0.0):
        raise ValueError("s must not contain a model pole")
    dynamic = np.einsum("fpk,ijk->fij", 1.0 / denominator[:, None, :], model.residues)
    return dynamic + model.constant[None, :, :] + points[:, None, None] * model.proportional[None, :, :]
