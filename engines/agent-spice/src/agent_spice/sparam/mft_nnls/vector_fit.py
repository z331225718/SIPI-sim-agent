"""One-step pole relocation equivalent to the pole-identification half of vectfit4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import lstsq, qr

from agent_spice.sparam.mft_nnls.model import stabilize_poles
from agent_spice.sparam.mft_nnls.weights import build_weights


@dataclass(frozen=True)
class RelocationOptions:
    """vectfit4 pole-identification controls used by one relocation step."""

    relaxed: bool = True
    asymptotic_order: int = 2
    stable: bool = True

    def __post_init__(self) -> None:
        if self.asymptotic_order not in {1, 2, 3}:
            raise ValueError("asymptotic_order must be 1, 2, or 3")


@dataclass(frozen=True)
class RelocationResult:
    poles: NDArray[np.complex128]
    diagnostics: dict[str, Any]


def _complex_pair_index(poles: NDArray[np.complex128], atol: float = 1.0e-8) -> NDArray[np.int_]:
    index = np.zeros(len(poles), dtype=int)
    cursor = 0
    while cursor < len(poles):
        pole = poles[cursor]
        if abs(pole.imag) <= atol:
            cursor += 1
            continue
        if cursor + 1 >= len(poles) or not np.isclose(poles[cursor + 1], pole.conjugate(), rtol=0.0, atol=atol):
            raise ValueError("complex initial poles must be adjacent conjugate pairs")
        index[cursor] = 1
        index[cursor + 1] = 2
        cursor += 2
    return index


def _basis(s: NDArray[np.complex128], poles: NDArray[np.complex128], asymptotic_order: int) -> tuple[NDArray[np.complex128], NDArray[np.int_]]:
    pair_index = _complex_pair_index(poles)
    # The relaxed sigma right block always includes a constant, even when
    # asymptotic_order=1 excludes it from the fitted-response left block.
    basis = np.zeros((len(s), len(poles) + max(asymptotic_order - 1, 1)), dtype=complex)
    for column, pole in enumerate(poles):
        if pair_index[column] == 0:
            basis[:, column] = 1.0 / (s - pole)
        elif pair_index[column] == 1:
            basis[:, column] = 1.0 / (s - pole) + 1.0 / (s - pole.conjugate())
            basis[:, column + 1] = 1j / (s - pole) - 1j / (s - pole.conjugate())
    basis[:, len(poles)] = 1.0
    if asymptotic_order == 3:
        basis[:, len(poles) + 1] = s
    return basis, pair_index


def _matlab_lower_triangle_indices(ports: int) -> tuple[NDArray[np.int_], NDArray[np.int_]]:
    """Return the column-major lower-triangle order used by VFdriver."""

    rows = np.concatenate([np.arange(column, ports) for column in range(ports)])
    columns = np.concatenate([np.full(ports - column, column) for column in range(ports)])
    return rows, columns


def _weighted_qr_right_block(
    basis: NDArray[np.complex128],
    response: NDArray[np.complex128],
    weights: NDArray[np.float64],
    *,
    asymptotic_order: int,
    relaxed: bool,
    scale: float,
    add_integral_row: bool,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    poles_count = basis.shape[1] - asymptotic_order + 1
    left_count = poles_count + asymptotic_order - 1
    sigma_count = poles_count + (1 if relaxed else 0)
    left = weights[:, None] * basis[:, :left_count]
    right_basis = basis[:, : poles_count + (1 if relaxed else 0)]
    right = -weights[:, None] * right_basis * response[:, None]
    matrix = np.concatenate((left, right), axis=1)
    matrix = np.concatenate((matrix.real, matrix.imag), axis=0)
    rhs_vector = np.concatenate(((weights * response).real, (weights * response).imag))
    if add_integral_row:
        row = np.zeros(matrix.shape[1], dtype=float)
        row[left_count:] = scale * np.real(np.sum(right_basis, axis=0))
        matrix = np.vstack((matrix, row))
    q, r = qr(matrix, mode="economic", pivoting=False, check_finite=False)
    right_block = r[left_count : left_count + sigma_count, left_count : left_count + sigma_count]
    if relaxed and add_integral_row:
        rhs = q[-1, left_count : left_count + sigma_count] * len(response) * scale
    elif not relaxed:
        rhs = q[:, left_count : left_count + sigma_count].T @ rhs_vector
    else:
        rhs = np.zeros(sigma_count, dtype=float)
    return right_block, rhs


def _realize_sigma(
    poles: NDArray[np.complex128],
    coefficients: NDArray[np.float64],
    pair_index: NDArray[np.int_],
    constant: float,
    stable: bool,
) -> NDArray[np.complex128]:
    complex_coefficients = coefficients.astype(complex)
    for index, kind in enumerate(pair_index):
        if kind == 1:
            value = coefficients[index] + 1j * coefficients[index + 1]
            complex_coefficients[index] = value
            complex_coefficients[index + 1] = value.conjugate()
    state = np.diag(poles).astype(complex)
    input_vector = np.ones((len(poles), 1), dtype=complex)
    cursor = 0
    while cursor < len(poles):
        if pair_index[cursor] == 1:
            pole = poles[cursor]
            state[cursor : cursor + 2, cursor : cursor + 2] = [[pole.real, pole.imag], [-pole.imag, pole.real]]
            input_vector[cursor : cursor + 2, 0] = [2.0, 0.0]
            complex_coefficients[cursor : cursor + 2] = [complex_coefficients[cursor].real, complex_coefficients[cursor].imag]
            cursor += 2
        else:
            cursor += 1
    if constant == 0.0:
        raise ValueError("sigma constant is zero; relocation is undefined")
    relocated = np.linalg.eigvals(state - input_vector @ complex_coefficients[None, :] / constant)
    if stable:
        relocated = stabilize_poles(relocated)
    real = np.sort(relocated[np.abs(relocated.imag) <= 1.0e-8].real).astype(complex)
    upper = np.sort_complex(relocated[relocated.imag > 1.0e-8])
    paired = np.asarray([pole for value in upper for pole in (value.conjugate(), value)], dtype=complex)
    return np.concatenate((real, paired))


def fit_fixed_poles(
    frequencies_hz: NDArray[np.float64],
    response: NDArray[np.complex128],
    poles: NDArray[np.complex128],
    *,
    weights: NDArray[np.float64] | None = None,
    asymptotic_order: int = 2,
) -> NDArray[np.complex128]:
    """Fit real pole-residue coefficients for a fixed common pole set.

    This is the `vectfit4` residue phase: it uses the real conjugate-pair
    coordinates and stacked real/imaginary equations used by MATLAB.
    """

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    values = np.asarray(response, dtype=complex)
    fixed_poles = np.asarray(poles, dtype=complex).reshape(-1)
    if values.ndim != 3 or values.shape[0] != len(frequencies) or values.shape[1] != values.shape[2]:
        raise ValueError("response must have shape (frequency, ports, ports)")
    if asymptotic_order not in {1, 2, 3}:
        raise ValueError("asymptotic_order must be 1, 2, or 3")
    if len(fixed_poles) == 0 or not np.isfinite(frequencies).all() or not np.isfinite(values).all() or not np.isfinite(fixed_poles).all():
        raise ValueError("frequencies, response, and poles must be finite and non-empty")
    s = 2j * np.pi * frequencies
    basis, _ = _basis(s, fixed_poles, asymptotic_order)
    left_count = len(fixed_poles) + asymptotic_order - 1
    matrix_weights = build_weights(values, 1) if weights is None else np.asarray(weights, dtype=float)
    if matrix_weights.shape != values.shape or not np.isfinite(matrix_weights).all() or np.any(matrix_weights <= 0.0):
        raise ValueError("weights must be finite, positive, and match response shape")

    fitted = np.empty_like(values)
    rows, columns = _matlab_lower_triangle_indices(values.shape[1])
    for row, column in zip(rows, columns, strict=True):
        weight = matrix_weights[:, row, column]
        design = weight[:, None] * basis[:, :left_count]
        target = weight * values[:, row, column]
        real_design = np.concatenate((design.real, design.imag), axis=0)
        real_target = np.concatenate((target.real, target.imag))
        coefficients, *_ = lstsq(real_design, real_target, lapack_driver="gelsy")
        fitted[:, row, column] = basis[:, :left_count] @ coefficients
        fitted[:, column, row] = fitted[:, row, column]
    return fitted


def relocate_once(
    frequencies_hz: NDArray[np.float64],
    response: NDArray[np.complex128],
    initial_poles: NDArray[np.complex128],
    *,
    weights: NDArray[np.float64] | None = None,
    options: RelocationOptions = RelocationOptions(),
) -> RelocationResult:
    """Perform one `vectfit4` common-pole relocation step for a symmetric matrix response."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    values = np.asarray(response, dtype=complex)
    poles = np.asarray(initial_poles, dtype=complex).reshape(-1)
    if values.ndim != 3 or values.shape[0] != len(frequencies) or values.shape[1] != values.shape[2]:
        raise ValueError("response must have shape (frequency, ports, ports)")
    if len(frequencies) < 2 or not np.isfinite(frequencies).all() or not np.isfinite(values).all() or not np.isfinite(poles).all():
        raise ValueError("frequencies, response, and initial_poles must be finite")
    if len(poles) == 0:
        raise ValueError("initial_poles must not be empty")
    s = 2j * np.pi * frequencies
    if np.any(np.isclose(s[:, None], poles[None, :], rtol=0.0, atol=1.0e-12)):
        raise ValueError("frequency samples must not equal initial poles")
    pair_index = _complex_pair_index(poles)
    basis, _ = _basis(s, poles, options.asymptotic_order)
    matrix_weights = build_weights(values, 1) if weights is None else np.asarray(weights, dtype=float)
    if matrix_weights.shape != values.shape or not np.isfinite(matrix_weights).all() or np.any(matrix_weights <= 0.0):
        raise ValueError("weights must be finite, positive, and match response shape")
    lower = _matlab_lower_triangle_indices(values.shape[1])
    flattened = values[:, lower[0], lower[1]].T
    flattened_weights = matrix_weights[:, lower[0], lower[1]].T
    scale = np.sqrt(sum(np.linalg.norm(flattened_weights[row] * flattened[row]) ** 2 for row in range(len(flattened)))) / len(frequencies)
    if not np.isfinite(scale) or scale == 0.0:
        raise ValueError("relocation scale must be finite and non-zero")
    sigma_count = len(poles) + (1 if options.relaxed else 0)
    compressed = np.zeros((len(flattened) * sigma_count, sigma_count), dtype=float)
    rhs = np.zeros(len(flattened) * sigma_count, dtype=float)
    for row, (response_row, weight_row) in enumerate(zip(flattened, flattened_weights, strict=True)):
        block, block_rhs = _weighted_qr_right_block(
            basis,
            response_row,
            weight_row,
            asymptotic_order=options.asymptotic_order,
            relaxed=options.relaxed,
            scale=scale,
            add_integral_row=options.relaxed and row == len(flattened) - 1,
        )
        start = row * sigma_count
        compressed[start : start + sigma_count] = block
        rhs[start : start + sigma_count] = block_rhs
    norms = np.linalg.norm(compressed, axis=0)
    if np.any(norms == 0.0):
        raise ValueError("rank-deficient relocation compression")
    scaled = compressed / norms[None, :]
    solution, _, rank, singular_values = lstsq(scaled, rhs, lapack_driver="gelsy")
    solution = solution / norms
    if options.relaxed:
        coefficients, constant = solution[:-1], float(solution[-1])
    else:
        coefficients, constant = solution, 1.0
    relocated = _realize_sigma(poles, coefficients, pair_index, constant, options.stable)
    condition = float(np.linalg.cond(scaled))
    return RelocationResult(
        poles=relocated,
        diagnostics={
            "relaxed": options.relaxed,
            "rank": int(rank),
            "condition_number": condition,
            "scale": float(scale),
            "sigma_constant": float(constant),
            "response_count": int(len(flattened)),
        },
    )
