"""MATLAB VFdriver-compatible response weighting."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def build_weights(
    response: NDArray[np.complex128],
    mode: int,
    explicit: NDArray[np.float64] | None = None,
) -> NDArray[np.float64]:
    """Build one of VFdriver's five weight modes for `(frequency, port, port)` data."""

    values = np.asarray(response, dtype=complex)
    if values.ndim != 3 or values.shape[1] != values.shape[2]:
        raise ValueError("response must have shape (frequency, ports, ports)")
    if not np.isfinite(values).all():
        raise ValueError("response must contain only finite values")
    if explicit is not None:
        supplied = np.asarray(explicit, dtype=float)
        if supplied.shape != values.shape:
            raise ValueError("explicit weights must match response shape")
        if not np.isfinite(supplied).all() or np.any(supplied <= 0.0):
            raise ValueError("explicit weights must be finite and positive")
        return supplied
    if mode not in {1, 2, 3, 4, 5}:
        raise ValueError("mode must be an integer from 1 through 5")
    if mode == 1:
        return np.ones(values.shape, dtype=float)

    floor = np.finfo(float).eps
    magnitude = np.maximum(np.abs(values), floor)
    if mode == 2:
        return 1.0 / magnitude
    if mode == 3:
        return 1.0 / np.sqrt(magnitude)

    lower = np.tril_indices(values.shape[1])
    norms = np.linalg.norm(values[:, lower[0], lower[1]], axis=1)
    norms = np.maximum(norms, floor)
    common = 1.0 / (norms if mode == 4 else np.sqrt(norms))
    return np.broadcast_to(common[:, None, None], values.shape).copy()
