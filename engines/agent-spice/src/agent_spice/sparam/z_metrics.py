"""Strict impedance-domain metrics for comparing rational matrix fits."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def invert_y_strict(values: Any, *, condition_limit: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Invert finite square Y matrices, rejecting ill-conditioned samples."""

    matrix = np.asarray(values, dtype=complex)
    if matrix.ndim != 3 or matrix.shape[1] != matrix.shape[2] or not np.isfinite(matrix).all():
        raise ValueError("Y values must be finite (frequency, port, port) matrices")
    conditions = np.asarray([np.linalg.cond(item) for item in matrix], dtype=float)
    if not np.isfinite(conditions).all():
        raise ValueError("fitted Y is singular")
    if condition_limit is not None and np.any(conditions > condition_limit):
        raise ValueError(f"fitted Y exceeds condition limit {condition_limit:.12g}")
    return np.linalg.inv(matrix), conditions


def strict_z_log_magnitude_rms_error(original_z: Any, fitted_z: Any, *, floor: float = 1.0e-300) -> float:
    """Full-matrix RMS of ``log10(|Zfit| / |Zref|)`` without dropping failures."""

    original = np.asarray(original_z, dtype=complex)
    fitted = np.asarray(fitted_z, dtype=complex)
    if original.shape != fitted.shape:
        raise ValueError("original_z and fitted_z must have the same shape")
    if not np.isfinite(original).all() or not np.isfinite(fitted).all():
        return math.inf
    delta = np.log10(np.maximum(np.abs(fitted), floor) / np.maximum(np.abs(original), floor))
    if not np.isfinite(delta).all():
        return math.inf
    return float(np.sqrt(np.mean(delta**2)))


def z_log_metric_summary(original_z: Any, fitted_z: Any) -> dict[str, float | None]:
    original = np.asarray(original_z, dtype=complex)
    fitted = np.asarray(fitted_z, dtype=complex)
    if original.ndim != 3 or original.shape[1] != original.shape[2]:
        raise ValueError("Z values must have shape (frequency, port, port)")
    diagonal = np.eye(original.shape[1], dtype=bool)
    off_diagonal = None
    if np.any(~diagonal):
        off_diagonal = strict_z_log_magnitude_rms_error(original[:, ~diagonal], fitted[:, ~diagonal])
    return {
        "z_log_magnitude_rms_error": strict_z_log_magnitude_rms_error(original, fitted),
        "diagonal_z_log_magnitude_rms_error": strict_z_log_magnitude_rms_error(original[:, diagonal], fitted[:, diagonal]),
        "offdiagonal_z_log_magnitude_rms_error": off_diagonal,
    }
