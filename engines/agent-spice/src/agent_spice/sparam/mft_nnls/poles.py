"""Initial common-pole placement matching the MFT-NNLS VFdriver choices."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


_POLE_TYPES = {"lincmplx", "logcmplx", "linlogcmplx"}


def _complex_pairs(frequencies: NDArray[np.float64], damping: float) -> NDArray[np.complex128]:
    return np.asarray(
        [pole for omega in frequencies for pole in (-damping * omega - 1j * omega, -damping * omega + 1j * omega)],
        dtype=complex,
    )


def initialize_poles(
    frequencies_hz: NDArray[np.float64],
    order: int,
    pole_type: str,
    *,
    damping: float = 1.0e-3,
) -> NDArray[np.complex128]:
    """Generate MFT-NNLS initial poles from a frequency grid in hertz."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    if order < 1:
        raise ValueError("order must be at least one")
    if pole_type not in _POLE_TYPES:
        raise ValueError(f"pole_type must be one of {sorted(_POLE_TYPES)}")
    if not np.isfinite(frequencies).all() or np.any(frequencies < 0.0):
        raise ValueError("frequencies_hz must be finite and non-negative")
    positive = frequencies[frequencies > 0.0]
    if len(positive) == 0:
        raise ValueError("frequencies_hz must contain a positive frequency")
    if not np.isfinite(damping) or damping <= 0.0:
        raise ValueError("damping must be finite and positive")
    omega_min = 2.0 * np.pi * float(np.min(positive))
    omega_max = 2.0 * np.pi * float(np.max(positive))
    effective_type = "logcmplx" if order < 6 and pole_type == "linlogcmplx" else pole_type

    if effective_type == "lincmplx":
        pair_frequencies = np.linspace(omega_min, omega_max, order // 2)
        extra = -0.5 * (omega_min + omega_max)
    elif effective_type == "logcmplx":
        pair_frequencies = np.geomspace(omega_min, omega_max, order // 2)
        extra = -np.sqrt(omega_min * omega_max)
    else:
        linear = np.linspace(omega_min, omega_max, int(np.ceil((order - 1) / 4.0)))
        logarithmic = np.geomspace(omega_min, omega_max, 2 + order // 4)[1:-1]
        pair_frequencies = np.concatenate((linear, logarithmic))
        extra = -np.sqrt(omega_min * omega_max)

    poles = _complex_pairs(pair_frequencies, damping)
    if len(poles) < order:
        poles = np.concatenate((poles, np.array([extra + 0.0j])))
    return poles[:order]
