"""QR-compressed residue perturbation using Gustavsen's homogeneous NNLS step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import qr, solve_triangular

from agent_spice.sparam.mft_nnls.model import evaluate
from agent_spice.sparam.mft_nnls.nnls import solve_homogeneous_nnls
from agent_spice.sparam.mft_nnls.passivity import PassivityAssessment, assess_s_passivity, assess_y_passivity, select_violation_extrema
from agent_spice.sparam.mft_nnls.types import MFTDiagnostics, MFTResult, PoleResidueModel
from agent_spice.sparam.mft_nnls.vector_fit import _basis, _complex_pair_index, _matlab_lower_triangle_indices


@dataclass(frozen=True)
class ResiduePerturbationConfig:
    parameter_type: Literal["S", "Y"] = "S"
    outer_iterations: int = 10
    tolerance: float = 1.0e-8
    passivity_tolerance: float = 1.0e-6
    alpha: float = 1.0
    local_violations: bool = True
    weight_mode: int = 1
    pole_indices: tuple[int, ...] | None = None
    bandwidth: int | None = None

    def __post_init__(self) -> None:
        if self.parameter_type not in {"S", "Y"}:
            raise ValueError("parameter_type must be 'S' or 'Y'")
        if self.outer_iterations < 1:
            raise ValueError("outer_iterations must be positive")
        if not np.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise ValueError("tolerance must be finite and positive")
        if not np.isfinite(self.passivity_tolerance) or self.passivity_tolerance <= 0.0:
            raise ValueError("passivity_tolerance must be finite and positive")
        if not np.isfinite(self.alpha) or self.alpha <= 0.0:
            raise ValueError("alpha must be finite and positive")
        if self.weight_mode != 1:
            raise ValueError("weight_mode must be 1; other RPdriver weighting modes are not implemented")
        if self.pole_indices is not None and (not self.pole_indices or any(index < 0 for index in self.pole_indices)):
            raise ValueError("pole_indices must be a non-empty tuple of non-negative indices")
        if self.bandwidth is not None and self.bandwidth < 0:
            raise ValueError("bandwidth must be non-negative")


@dataclass(frozen=True)
class PerturbationSystem:
    constraint_matrix: NDArray[np.float64]
    constraint_rhs: NDArray[np.float64]
    qr_blocks: tuple[NDArray[np.float64], ...]
    column_scales: tuple[NDArray[np.float64], ...]
    pair_index: NDArray[np.int_]
    lower_rows: NDArray[np.int_]
    lower_columns: NDArray[np.int_]
    pole_indices: NDArray[np.int_]
    active_column_count: int
    fit_frequencies_hz: NDArray[np.float64]


def _assessment(model: PoleResidueModel, frequencies_hz: NDArray[np.float64], parameter_type: str) -> PassivityAssessment:
    f_max = float(np.max(frequencies_hz))
    return assess_s_passivity(model, f_max=f_max) if parameter_type == "S" else assess_y_passivity(model, f_max=f_max)


def _metric_excess(value: float, parameter_type: str) -> float:
    return value - 1.0 if parameter_type == "S" else -value


def _rp_auxiliary_frequencies(
    frequencies_hz: NDArray[np.float64],
    poles: NDArray[np.complex128],
    pair_index: NDArray[np.int_],
    parameter_type: Literal["S", "Y"],
    extrema_hz: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Reproduce RP_QRNNLS's auxiliary LS samples for weight mode 1."""

    omega = 2.0 * np.pi * frequencies_hz
    lower = float(np.min(omega))
    upper = float(np.max(omega))
    outside: list[float] = []
    for index, pole in enumerate(poles):
        if pair_index[index] == 2:
            continue
        candidate = abs(float(pole.real)) if pair_index[index] == 0 else abs(float(pole.imag))
        if candidate > upper or candidate < lower:
            outside.append(candidate / (2.0 * np.pi))
    if parameter_type == "S":
        # RP_QRNNLS_S appends out-of-band samples and one DC point.  Its
        # later s_ekstra assignment is intentionally not duplicated here:
        # the reference function does not append it to s either.
        extra = outside + [0.0]
    else:
        # RP_QRNLLS_Y adds each violation frequency and s_ekstra (DC plus
        # the same frequencies), followed by another DC point when E is not
        # being perturbed.  The current residue-only path has Eflag == 0.
        extra = outside + extrema_hz.tolist() + [0.0] + extrema_hz.tolist() + [0.0]
    return np.concatenate((frequencies_hz, np.asarray(extra, dtype=float)))


def build_residue_perturbation_system(
    model: PoleResidueModel,
    frequencies_hz: NDArray[np.float64],
    *,
    parameter_type: Literal["S", "Y"],
    local_violations: bool = True,
    passivity_tolerance: float = 1.0e-6,
    alpha: float = 1.0,
    pole_indices: tuple[int, ...] | None = None,
    bandwidth: int | None = None,
) -> PerturbationSystem:
    """Build ``B R^-1`` constraints for residue-only RP-NNLS perturbation."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    if len(frequencies) < 2 or not np.isfinite(frequencies).all() or np.any(frequencies < 0.0):
        raise ValueError("frequencies_hz must contain finite non-negative samples")
    selected_indices = np.arange(len(model.poles), dtype=int) if pole_indices is None else np.asarray(pole_indices, dtype=int)
    if len(selected_indices) == 0 or np.any(selected_indices < 0) or np.any(selected_indices >= len(model.poles)) or len(np.unique(selected_indices)) != len(selected_indices):
        raise ValueError("pole_indices must be unique valid model pole indices")
    selected_indices.sort()
    full_pair_index = _complex_pair_index(model.poles)
    for index in selected_indices:
        if full_pair_index[index] == 1 and index + 1 not in selected_indices:
            raise ValueError("pole_indices must include complete adjacent conjugate pairs")
        if full_pair_index[index] == 2 and index - 1 not in selected_indices:
            raise ValueError("pole_indices must include complete adjacent conjugate pairs")
    selected_poles = model.poles[selected_indices]
    local_columns = len(selected_poles)
    _, pair_index = _basis(2j * np.pi * frequencies, selected_poles, 1)
    assessment = _assessment(model, frequencies, parameter_type)
    extrema = select_violation_extrema(model, assessment, local=local_violations)
    fit_frequencies = _rp_auxiliary_frequencies(
        frequencies,
        selected_poles,
        pair_index,
        parameter_type,
        np.asarray([extremum.frequency_hz for extremum in extrema], dtype=float),
    )
    basis, _ = _basis(2j * np.pi * fit_frequencies, selected_poles, 1)
    rows, columns = _matlab_lower_triangle_indices(model.ports)
    if bandwidth is not None:
        within_band = rows - columns <= bandwidth
        rows = rows[within_band]
        columns = columns[within_band]
    qr_blocks: list[NDArray[np.float64]] = []
    column_scales: list[NDArray[np.float64]] = []
    for row, column in zip(rows, columns, strict=True):
        design = np.concatenate((basis[:, :local_columns].real, basis[:, :local_columns].imag), axis=0)
        qr_scale = np.linalg.norm(design, axis=0)
        if row != column:
            # MATLAB packs symmetric off-diagonal responses with sqrt(2)
            # in the QR objective while their passivity derivative is doubled.
            scale = np.sqrt(2.0) * qr_scale
        else:
            scale = qr_scale
        if np.any(qr_scale == 0.0):
            raise ValueError("residue LS column scale is zero")
        _, r = qr(design / qr_scale, mode="economic", pivoting=False, check_finite=False)
        if np.linalg.matrix_rank(r) < local_columns:
            raise ValueError("residue QR block is rank deficient")
        qr_blocks.append(r)
        column_scales.append(scale)
    gradients = np.zeros((len(extrema), len(rows) * local_columns), dtype=float)
    rhs = np.zeros(len(extrema), dtype=float)
    for index, extremum in enumerate(extrema):
        s = 2j * np.pi * extremum.frequency_hz
        local_basis, _ = _basis(np.asarray([s]), selected_poles, 1)
        for element, (row, column) in enumerate(zip(rows, columns, strict=True)):
            for pole_column in range(local_columns):
                derivative = np.zeros((model.ports, model.ports), dtype=complex)
                derivative[row, column] = local_basis[0, pole_column]
                derivative[column, row] = local_basis[0, pole_column]
                if parameter_type == "S":
                    assert extremum.right_vector is not None
                    sensitivity = float(np.real(np.vdot(extremum.left_vector, derivative @ extremum.right_vector)))
                else:
                    sensitivity = float(np.real(np.vdot(extremum.left_vector, derivative @ extremum.left_vector)))
                gradients[index, element * local_columns + pole_column] = sensitivity
        if parameter_type == "S":
            rhs[index] = -(passivity_tolerance + alpha * max(extremum.value - 1.0, 0.0))
        else:
            # MATLAB RP_QRNNLS_Y: c=-TOLG+alpha*lambda_min.
            rhs[index] = -passivity_tolerance + alpha * extremum.value
    transformed = np.zeros_like(gradients)
    for element, block in enumerate(qr_blocks):
        start = element * local_columns
        stop = start + local_columns
        scaled_gradient = gradients[:, start:stop] / column_scales[element]
        transformed[:, start:stop] = solve_triangular(block.T, scaled_gradient.T, lower=True).T
    constraint_matrix = -transformed if parameter_type == "S" else transformed
    return PerturbationSystem(
        constraint_matrix=constraint_matrix,
        constraint_rhs=rhs,
        qr_blocks=tuple(qr_blocks),
        column_scales=tuple(column_scales),
        pair_index=pair_index,
        lower_rows=rows,
        lower_columns=columns,
        pole_indices=selected_indices,
        active_column_count=int(np.count_nonzero(np.any(np.abs(transformed) > 0.0, axis=0))),
        fit_frequencies_hz=fit_frequencies,
    )


def _recover_delta(system: PerturbationSystem, xbar: NDArray[np.float64]) -> NDArray[np.float64]:
    local_columns = len(system.pair_index)
    delta = np.empty_like(xbar)
    for element, block in enumerate(system.qr_blocks):
        start = element * local_columns
        stop = start + local_columns
        delta[start:stop] = solve_triangular(block, xbar[start:stop], lower=False) / system.column_scales[element]
    return delta


def _apply_residue_delta(model: PoleResidueModel, system: PerturbationSystem, delta: NDArray[np.float64]) -> PoleResidueModel:
    residues = np.array(model.residues, copy=True)
    local_columns = len(system.pair_index)
    for element, (row, column) in enumerate(zip(system.lower_rows, system.lower_columns, strict=True)):
        values = delta[element * local_columns : (element + 1) * local_columns]
        for pole_column, kind in enumerate(system.pair_index):
            if kind == 0:
                original_column = system.pole_indices[pole_column]
                residues[row, column, original_column] += values[pole_column]
                if row != column:
                    residues[column, row, original_column] += values[pole_column]
            elif kind == 1:
                change = values[pole_column] + 1j * values[pole_column + 1]
                original_column = system.pole_indices[pole_column]
                conjugate_column = system.pole_indices[pole_column + 1]
                residues[row, column, original_column] += change
                if row != column:
                    residues[column, row, original_column] += change
                residues[row, column, conjugate_column] += change.conjugate()
                if row != column:
                    residues[column, row, conjugate_column] += change.conjugate()
    return PoleResidueModel(model.poles, residues, model.constant, model.proportional)


def enforce_passivity(
    model: PoleResidueModel,
    frequencies_hz: NDArray[np.float64],
    config: ResiduePerturbationConfig,
) -> MFTResult:
    """Run bounded outer RP-NNLS iterations with non-regression rollback."""

    frequencies = np.asarray(frequencies_hz, dtype=float).reshape(-1)
    reference = evaluate(model, 2j * np.pi * frequencies)
    current = model
    history: list[dict[str, float | int | bool]] = []
    assessment = _assessment(current, frequencies, config.parameter_type)
    for iteration in range(config.outer_iterations):
        excess = _metric_excess(assessment.worst_value, config.parameter_type)
        if excess <= 1.0e-6:
            break
        system = build_residue_perturbation_system(
            current,
            frequencies,
            parameter_type=config.parameter_type,
            local_violations=config.local_violations,
            passivity_tolerance=config.passivity_tolerance,
            alpha=config.alpha,
            pole_indices=config.pole_indices,
            bandwidth=config.bandwidth,
        )
        if not len(system.constraint_rhs):
            break
        solution = solve_homogeneous_nnls(system.constraint_matrix, system.constraint_rhs, tolerance=config.tolerance)
        delta = _recover_delta(system, solution.x)
        candidate = _apply_residue_delta(current, system, delta)
        candidate_assessment = _assessment(candidate, frequencies, config.parameter_type)
        candidate_excess = _metric_excess(candidate_assessment.worst_value, config.parameter_type)
        accepted = bool(np.isfinite(candidate_excess) and candidate_excess < excess)
        history.append(
            {
                "iteration": iteration + 1,
                "constraint_count": int(len(system.constraint_rhs)),
                "kkt_stationarity_inf_norm": solution.kkt_stationarity_inf_norm,
                "excess_before": excess,
                "excess_after": candidate_excess,
                "accepted": accepted,
            }
        )
        if not accepted:
            break
        current = candidate
        assessment = candidate_assessment
    response = evaluate(current, 2j * np.pi * frequencies)
    rms = float(np.sqrt(np.mean(np.abs(response - reference) ** 2)))
    return MFTResult(
        current,
        MFTDiagnostics("passivity_enforcement", iterations=len(history), details={"history": history, "final_assessment": assessment}),
        rms,
    )
