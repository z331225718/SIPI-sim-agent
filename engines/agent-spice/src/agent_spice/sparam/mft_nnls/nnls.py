"""SciPy-backed non-negative least squares used by RPdriver's QR reduction."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import nnls


@dataclass(frozen=True)
class NNLSSolution:
    x: NDArray[np.float64]
    residual_norm: float
    kkt_stationarity_inf_norm: float
    rank: int
    dual_variables: NDArray[np.float64] | None = None
    homogeneous_residual: NDArray[np.float64] | None = None


def _validate_system(matrix: NDArray[np.float64], target: NDArray[np.float64], tolerance: float) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    system = np.asarray(matrix, dtype=float)
    rhs = np.asarray(target, dtype=float).reshape(-1)
    if system.ndim != 2 or system.shape[0] != len(rhs):
        raise ValueError("matrix rows must match target length")
    if not np.isfinite(system).all() or not np.isfinite(rhs).all():
        raise ValueError("matrix and target must be finite")
    if not np.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("tolerance must be finite and positive")
    return system, rhs


def _kkt_violation(matrix: NDArray[np.float64], residual: NDArray[np.float64], x: NDArray[np.float64], tolerance: float) -> float:
    gradient = matrix.T @ residual
    active = x > tolerance
    active_violation = np.abs(gradient[active]) if np.any(active) else np.zeros(0)
    inactive_violation = np.maximum(-gradient[~active], 0.0) if np.any(~active) else np.zeros(0)
    return float(max(np.max(active_violation, initial=0.0), np.max(inactive_violation, initial=0.0)))


def solve_least_distance_nnls(
    matrix: NDArray[np.float64],
    target: NDArray[np.float64],
    *,
    tolerance: float,
) -> NNLSSolution:
    """Solve ``min ||A x-b||`` subject to ``x >= 0`` with KKT diagnostics."""

    system, rhs = _validate_system(matrix, target, tolerance)
    solution, residual_norm = nnls(system, rhs)
    residual = system @ solution - rhs
    return NNLSSolution(
        x=solution,
        residual_norm=float(residual_norm),
        kkt_stationarity_inf_norm=_kkt_violation(system, residual, solution, tolerance),
        rank=int(np.linalg.matrix_rank(system, tol=tolerance)),
    )


def solve_homogeneous_nnls(
    constraint_matrix: NDArray[np.float64],
    constraint_rhs: NDArray[np.float64],
    *,
    tolerance: float,
) -> NNLSSolution:
    """Apply Gustavsen's homogeneous NNLS transform after QR compression.

    ``constraint_matrix`` is the row-wise transformed sensitivity matrix
    ``B R^-1`` and ``constraint_rhs`` is the corresponding RPdriver ``c``.
    """

    constraints, rhs = _validate_system(constraint_matrix, constraint_rhs, tolerance)
    transformed = np.vstack((constraints.T, -rhs[None, :]))
    target = np.zeros(constraints.shape[1] + 1, dtype=float)
    target[-1] = 1.0
    dual, _ = nnls(transformed, target)
    residual = target - transformed @ dual
    denominator = float(residual[-1])
    if not np.isfinite(denominator) or abs(denominator) <= tolerance:
        raise RuntimeError("homogeneous NNLS normalization residual is zero or non-finite")
    xbar = -residual[:-1] / denominator
    return NNLSSolution(
        x=xbar,
        residual_norm=float(np.linalg.norm(residual)),
        kkt_stationarity_inf_norm=_kkt_violation(transformed, transformed @ dual - target, dual, tolerance),
        rank=int(np.linalg.matrix_rank(transformed, tol=tolerance)),
        dual_variables=dual,
        homogeneous_residual=residual,
    )
